# TAPIOD SDK — Universal Drop-In Replacement Design

**Date:** 2026-07-01  
**Status:** Approved

## Goal

Make the TAPIOD Python SDK a true drop-in replacement for any major LLM provider SDK. An enterprise developer changes **one import line** and every LLM call in their codebase automatically routes through TAPIOD's semantic caching, smart routing, and observability — with zero other code changes.

```python
# Before
from openai import OpenAI

# After — one line changed, nothing else
from tapiod.openai import OpenAI
```

---

## Scope

### SDKs covered
- **OpenAI** (`openai.OpenAI`, `openai.AsyncOpenAI`)
- **Anthropic** (`anthropic.Anthropic`, `anthropic.AsyncAnthropic`)
- **Google Gemini** (`google.generativeai.GenerativeModel`, `google.generativeai.configure`)
- **Groq** (`groq.Groq`, `groq.AsyncGroq`) — re-exports OpenAI adapter (identical wire format)

### Bug fixes to existing native client
- `Message.tool_calls` not exposed in response objects
- Async streaming type annotation misleading (functional but confusing)

### Out of scope
- Embeddings endpoints
- Image generation endpoints
- Audio/speech endpoints
- Mistral, Cohere, Ollama (can be added later using the same pattern)

---

## Architecture

```
sdk/tapiod/
├── __init__.py                  ← existing TapiodClient, AsyncTapiodClient (fixed)
├── client.py                    ← fixed: tool_calls in response, clean annotations
├── models.py                    ← fixed: Message.tool_calls, ToolCall, ToolCallFunction
├── _transport.py                ← NEW: shared sync+async HTTP, SSE parsing
├── _core/
│   ├── mapping.py               ← model name → TAPIOD alias, provider fallback prefixes
│   └── converters.py            ← Anthropic/Gemini ↔ OpenAI wire format translation
├── openai/
│   ├── __init__.py              ← OpenAI, AsyncOpenAI
│   └── _models.py               ← ChatCompletion, ChatCompletionChunk, all subtypes
├── anthropic/
│   ├── __init__.py              ← Anthropic, AsyncAnthropic
│   └── _models.py               ← Message, TextBlock, ToolUseBlock, Usage
├── google/
│   ├── __init__.py              ← empty, required for Python package resolution
│   └── generativeai/
│       ├── __init__.py          ← GenerativeModel, configure()
│       └── _models.py           ← GenerateContentResponse, Candidate, Part
└── groq/
    └── __init__.py              ← Groq, AsyncGroq (re-exports tapiod.openai)
```

---

## Data Flow

Every adapter follows the same pipeline:

```
User code (SDK-native call)
  → Adapter: translate request to OpenAI wire format
    → _transport.py: POST /api/agent/chat/completions
      → TAPIOD gateway: caching · routing · observability · tool execution
        → LiteLLM → provider API
      → _transport.py: raw JSON response
    → Adapter: translate response to SDK-native types
  → User code (gets back exact same types as original SDK)
```

For streaming, `_transport.py` parses SSE lines into raw chunk dicts. Each adapter wraps those dicts into its own chunk type (`ChatCompletionChunk`, `MessageStreamEvent`, etc.).

---

## Component: `_transport.py`

Single source of truth for all HTTP communication. No adapter contains HTTP code.

```python
class TapiodTransport:
    def __init__(self, base_url: str, api_key: str, timeout: float)
    def post(self, payload: dict) -> dict
    def stream(self, payload: dict) -> Iterator[dict]   # yields parsed SSE chunk dicts
    def close(self)
    def __enter__ / __exit__

class AsyncTapiodTransport:
    def __init__(self, base_url: str, api_key: str, timeout: float)
    async def post(self, payload: dict) -> dict
    async def stream(self, payload: dict) -> AsyncIterator[dict]
    async def close()
    async def __aenter__ / __aexit__
```

Both classes read `TAPIOD_URL` and `TAPIOD_API_KEY` env vars as defaults.

---

## Component: `_core/mapping.py`

Centralised model name translation. One file to update when new models release.

```python
OPENAI_MODEL_MAP = {
    "gpt-4o":        "heavy-openai",
    "gpt-4o-mini":   "fast-openai",
    "o3":            "heavy-openai",
    "o4-mini":       "fast-openai",
    # extend here for new models
}

ANTHROPIC_MODEL_MAP = {
    "claude-opus-4-8":    "heavy-anthropic",
    "claude-opus-4-7":    "heavy-anthropic",
    "claude-sonnet-4-6":  "fast-anthropic",
    "claude-haiku-4-5":   "fast-anthropic",
    # extend here for new models
}

GEMINI_MODEL_MAP = {
    "gemini-pro":          "heavy-gemini",
    "gemini-2.5-pro":      "heavy-gemini",
    "gemini-2.5-flash":    "fast-gemini",
    "gemini-3.5-flash":    "fast-gemini",
    # extend here for new models
}

# For unmapped models: auto-prefix so LiteLLM knows which provider to call
ADAPTER_PROVIDER_PREFIX = {
    "openai":    "openai",
    "anthropic": "anthropic",
    "gemini":    "gemini",
    "groq":      "groq",
}

def resolve_model(model: str, adapter: str) -> str:
    """
    1. Check adapter's MODEL_MAP — return TAPIOD alias if found.
    2. If already provider-prefixed (e.g. "openai/gpt-5"), pass through.
    3. Otherwise prepend ADAPTER_PROVIDER_PREFIX so LiteLLM routes correctly.
    Unmapped models bypass TAPIOD tier routing but still get caching + observability.
    Unknown/misspelled models surface as a clear provider API error — nothing silently breaks.
    """
```

---

## Component: `_core/converters.py`

Shape translation between each SDK's wire format and OpenAI format (which TAPIOD's gateway speaks).

### Anthropic → OpenAI (request)

| Anthropic param | OpenAI equivalent |
|---|---|
| `system` (str) | Prepend `{"role": "system", "content": system}` to messages |
| `max_tokens` | `max_tokens` (same key, pass through) |
| `tools[].input_schema` | `tools[].function.parameters` |
| `tools[].name` | `tools[].function.name` |
| `tools[].description` | `tools[].function.description` |
| Wrap each tool in `{"type": "function", "function": {...}}` | — |

### OpenAI → Anthropic (response)

| OpenAI field | Anthropic equivalent |
|---|---|
| `choices[0].message.content` | `content=[TextBlock(text=...)]` |
| `choices[0].message.tool_calls[i]` | `content=[ToolUseBlock(id, name, input=json.loads(arguments))]` |
| `choices[0].finish_reason == "stop"` | `stop_reason = "end_turn"` |
| `choices[0].finish_reason == "tool_calls"` | `stop_reason = "tool_use"` |
| `choices[0].finish_reason == "length"` | `stop_reason = "max_tokens"` |
| `usage.prompt_tokens` | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |

### Gemini → OpenAI (request)

| Gemini param | OpenAI equivalent |
|---|---|
| `contents` (str) | `[{"role": "user", "content": contents}]` |
| `contents` (list of `{"role", "parts"}`) | Map `"model"` role → `"assistant"`, join `parts[].text` into `content` |
| `system_instruction` (str) | Prepend `{"role": "system", "content": system_instruction}` |

### OpenAI → Gemini (response)

| OpenAI field | Gemini equivalent |
|---|---|
| `choices[0].message.content` | `candidates[0].content.parts[0].text` |
| `choices[0].finish_reason` | `candidates[0].finish_reason` (mapped to `FinishReason` enum) |
| `usage.prompt_tokens` | `usage_metadata.prompt_token_count` |
| `usage.completion_tokens` | `usage_metadata.candidates_token_count` |
| `usage.total_tokens` | `usage_metadata.total_token_count` |

---

## Component: `tapiod/openai/`

### Interface (exact match to `openai` SDK)

```python
from tapiod.openai import OpenAI, AsyncOpenAI

client = OpenAI(api_key="...", base_url=None, timeout=60.0)
# api_key is accepted to avoid breaking the constructor call but is NOT forwarded —
# TAPIOD uses its own provider keys configured via the Config page.
# base_url overrides the TAPIOD gateway URL (defaults to TAPIOD_URL env var or http://localhost:4001)

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    stream=False,
    tools=[...],        # optional
    tool_choice="auto", # optional
    max_tokens=1024,    # optional
    temperature=0.7,    # optional
    **kwargs,           # all other OpenAI params passed through
)
```

### Response types (`tapiod/openai/_models.py`)

```python
class ToolCallFunction:
    name: str
    arguments: str       # JSON string, same as openai SDK

class ToolCall:
    id: str
    type: str            # "function"
    function: ToolCallFunction

class ChatCompletionMessage:
    role: str
    content: str | None
    tool_calls: list[ToolCall] | None

class Choice:
    index: int
    message: ChatCompletionMessage
    finish_reason: str | None

class CompletionUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletion:
    id: str
    object: str          # "chat.completion"
    model: str
    choices: list[Choice]
    usage: CompletionUsage
    _tapiod_trace: TapiodTrace | None   # bonus field — ignored by code expecting openai types

# Streaming
class ChoiceDelta:
    role: str | None
    content: str | None
    tool_calls: list | None

class ChunkChoice:
    index: int
    delta: ChoiceDelta
    finish_reason: str | None

class ChatCompletionChunk:
    id: str
    model: str
    choices: list[ChunkChoice]
```

Streaming yields `ChatCompletionChunk` objects — not raw strings. Code that does `chunk.choices[0].delta.content` works without modification.

---

## Component: `tapiod/anthropic/`

### Interface (exact match to `anthropic` SDK)

```python
from tapiod.anthropic import Anthropic, AsyncAnthropic

client = Anthropic(api_key="...")

resp = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=1024,
    system="You are helpful.",     # optional
    messages=[...],
    tools=[...],                   # optional, Anthropic format
)
```

### Response types (`tapiod/anthropic/_models.py`)

```python
class TextBlock:
    type: str = "text"
    text: str

class ToolUseBlock:
    type: str = "tool_use"
    id: str
    name: str
    input: dict            # parsed from JSON, not a string

class Usage:
    input_tokens: int
    output_tokens: int

class Message:
    id: str
    model: str
    role: str              # "assistant"
    content: list[TextBlock | ToolUseBlock]
    stop_reason: str       # "end_turn" | "tool_use" | "max_tokens"
    usage: Usage
    _tapiod_trace: TapiodTrace | None
```

### Streaming interface

Anthropic streaming yields text delta strings (the common usage pattern) wrapped in event-like objects:

```python
with client.messages.stream(model=..., messages=..., max_tokens=...) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

`stream.text_stream` is a generator of `str` tokens. The `stream` context manager also exposes `stream.get_final_message()` which returns the complete `Message` object after iteration. This covers the most common Anthropic streaming patterns used in production code.

---

## Component: `tapiod/google/generativeai/`

### Interface (exact match to `google.generativeai` SDK)

```python
import tapiod.google.generativeai as genai

genai.configure(api_key="...")   # stored in module-level state

model = genai.GenerativeModel(
    "gemini-pro",
    system_instruction="You are helpful.",   # optional
)

resp = model.generate_content("What is 2+2?")
print(resp.text)
```

### Response types (`tapiod/google/generativeai/_models.py`)

```python
class FinishReason:
    STOP = "STOP"
    MAX_TOKENS = "MAX_TOKENS"
    SAFETY = "SAFETY"
    OTHER = "OTHER"

class Part:
    text: str

class Content:
    parts: list[Part]
    role: str

class Candidate:
    content: Content
    finish_reason: str
    index: int

class UsageMetadata:
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int

class GenerateContentResponse:
    candidates: list[Candidate]
    usage_metadata: UsageMetadata

    @property
    def text(self) -> str:
        return self.candidates[0].content.parts[0].text
```

---

## Component: `tapiod/groq/`

Groq's SDK is an OpenAI fork — identical wire format and interface. Zero translation needed.

```python
# tapiod/groq/__init__.py
from tapiod.openai import OpenAI as Groq, AsyncOpenAI as AsyncGroq
__all__ = ["Groq", "AsyncGroq"]
```

---

## Bug Fixes to Native Client

### `models.py` — add `tool_calls` to `Message`

```python
class ToolCallFunction:
    name: str
    arguments: str

class ToolCall:
    id: str
    type: str
    function: ToolCallFunction

class Message:
    role: str
    content: str
    tool_calls: list[ToolCall] | None   # NEW
```

### `client.py` — clean up async streaming annotation

`_astream` is an async generator (correct). The `create` method returns it directly from an `async def`, meaning callers do `async for token in await client.chat.completions.create(stream=True)`. Add a clear usage comment and fix the confusing return type annotation.

---

## Model Name Resolution — Full Decision Tree

```
resolve_model("gpt-4o", adapter="openai")
  → found in OPENAI_MODEL_MAP → "heavy-openai" ✓ (full TAPIOD routing)

resolve_model("gpt-5", adapter="openai")
  → not in OPENAI_MODEL_MAP
  → not already provider-prefixed
  → prepend prefix → "openai/gpt-5" (LiteLLM routes to OpenAI API directly)
  → if OpenAI API key set and model exists → works, gets caching + observability
  → if model doesn't exist → clear OpenAI API error surfaces to caller ✓

resolve_model("openai/gpt-4o", adapter="openai")
  → already provider-prefixed → pass through as-is ✓
```

---

## Adding New Models (Future)

One line in `_core/mapping.py`:

```python
OPENAI_MODEL_MAP["o5"] = "heavy-openai"         # new OpenAI model
ANTHROPIC_MODEL_MAP["claude-opus-5"] = "heavy-anthropic"  # new Anthropic model
```

## Adding New Provider SDKs (Future)

1. Create `tapiod/<provider>/` folder, follow the same pattern
2. Add entries to `_core/mapping.py`
3. Add request/response converters to `_core/converters.py` if not OpenAI-compatible

Transport layer, gateway, caching, routing — all inherited automatically.

---

## Dependency Changes

No new runtime dependencies. The SDK still only requires `httpx>=0.27`. All response types are hand-rolled dataclass-like classes — no `openai`, `anthropic`, or `google-generativeai` packages are imported inside the SDK. This eliminates dependency conflicts when users install TAPIOD alongside the original SDK.
