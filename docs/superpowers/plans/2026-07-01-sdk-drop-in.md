# SDK Universal Drop-In Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the TAPIOD Python SDK a true drop-in replacement for OpenAI, Anthropic, Google Gemini, and Groq SDKs — one import line change, zero other code changes required.

**Architecture:** A shared `_transport.py` handles all HTTP and SSE parsing. A `_core/` layer handles model name resolution and request/response shape translation. Per-provider adapter submodules (`tapiod.openai`, `tapiod.anthropic`, `tapiod.google.generativeai`, `tapiod.groq`) expose exact class names and response types matching each original SDK. The native `TapiodClient` is also fixed for bugs.

**Tech Stack:** Python 3.10+, httpx, pytest, unittest.mock (stdlib)

## Global Constraints

- All files live under `sdk/` in the repo
- No new runtime dependencies — only `httpx>=0.27` (already in pyproject.toml)
- Do not import `openai`, `anthropic`, or `google-generativeai` packages anywhere in the SDK source — all response types are hand-rolled
- Python 3.10+ syntax only (`X | Y` unions, `match` if needed)
- Every directory under `sdk/tapiod/` needs an `__init__.py` to be recognised as a package
- All tests live under `sdk/tests/` and are run with `cd sdk && pytest tests/ -v`
- Commits must not include Co-Authored-By lines

## File Map

```
sdk/
├── pyproject.toml                         MODIFY — bump version to 0.2.0
├── tests/
│   ├── __init__.py                        CREATE — empty
│   ├── conftest.py                        CREATE — shared fixtures
│   ├── test_native_bugfixes.py            CREATE — Task 1 tests
│   ├── test_transport.py                  CREATE — Task 2 tests
│   ├── test_mapping.py                    CREATE — Task 3 tests
│   ├── test_converters.py                 CREATE — Task 4 tests
│   ├── test_openai_adapter.py             CREATE — Task 5 tests
│   ├── test_groq_adapter.py               CREATE — Task 6 tests
│   ├── test_anthropic_adapter.py          CREATE — Task 7 tests
│   └── test_gemini_adapter.py             CREATE — Task 8 tests
└── tapiod/
    ├── __init__.py                        MODIFY — re-export TapiodClient (no change needed)
    ├── models.py                          MODIFY — add ToolCall, ToolCallFunction; fix Message
    ├── client.py                          MODIFY — fix async streaming type annotation
    ├── _transport.py                      CREATE — TapiodTransport, AsyncTapiodTransport
    ├── _core/
    │   ├── __init__.py                    CREATE — empty
    │   ├── mapping.py                     CREATE — resolve_model(), model maps
    │   └── converters.py                  CREATE — anthropic/gemini ↔ openai translation
    ├── openai/
    │   ├── __init__.py                    CREATE — OpenAI, AsyncOpenAI
    │   └── _models.py                     CREATE — ChatCompletion, ChatCompletionChunk, etc.
    ├── anthropic/
    │   ├── __init__.py                    CREATE — Anthropic, AsyncAnthropic
    │   └── _models.py                     CREATE — Message, TextBlock, ToolUseBlock, Usage
    ├── google/
    │   ├── __init__.py                    CREATE — empty
    │   └── generativeai/
    │       ├── __init__.py                CREATE — GenerativeModel, configure()
    │       └── _models.py                 CREATE — GenerateContentResponse, Candidate, Part
    └── groq/
        └── __init__.py                    CREATE — re-exports tapiod.openai as Groq/AsyncGroq
```

---

### Task 1: Fix Native Client Bugs

**Files:**
- Modify: `sdk/tapiod/models.py`
- Modify: `sdk/tapiod/client.py`
- Create: `sdk/tests/__init__.py`
- Create: `sdk/tests/test_native_bugfixes.py`

**Interfaces:**
- Produces: `ToolCallFunction(d: dict)` with `.name: str`, `.arguments: str`
- Produces: `ToolCall(d: dict)` with `.id: str`, `.type: str`, `.function: ToolCallFunction`
- Produces: `Message` with `.tool_calls: list[ToolCall] | None` in addition to existing fields

- [ ] **Step 1: Create the tests directory and empty `__init__.py`**

```bash
mkdir -p sdk/tests
touch sdk/tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `sdk/tests/test_native_bugfixes.py`:

```python
import pytest
from tapiod.models import Message, ToolCall, ToolCallFunction, ChatCompletion


def test_message_tool_calls_none_when_absent():
    msg = Message({"role": "assistant", "content": "Hello"})
    assert msg.tool_calls is None


def test_message_tool_calls_parsed_when_present():
    msg = Message({
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }
        ],
    })
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.id == "call_abc"
    assert tc.type == "function"
    assert tc.function.name == "get_weather"
    assert tc.function.arguments == '{"location":"NYC"}'


def test_message_content_can_be_none():
    msg = Message({"role": "assistant", "content": None})
    assert msg.content is None


def test_chat_completion_tool_calls_accessible():
    raw = {
        "id": "chatcmpl-1",
        "model": "fast-groq",
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_xyz",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"q":"test"}'},
                }],
            },
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    resp = ChatCompletion(raw)
    assert resp.choices[0].message.tool_calls is not None
    assert resp.choices[0].message.tool_calls[0].function.name == "search"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_native_bugfixes.py -v
```

Expected: `ImportError: cannot import name 'ToolCall' from 'tapiod.models'` or `AttributeError: 'Message' object has no attribute 'tool_calls'`

- [ ] **Step 4: Fix `sdk/tapiod/models.py`**

Replace the entire file:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceStep:
    layer: str
    result: str
    latency_ms: float


@dataclass
class TapiodTrace:
    pipeline: list[TraceStep]
    actual_cost_usd: float
    total_saved_usd: float
    cache_source: str | None
    provider_model: str
    memory_tokens_saved: int

    @classmethod
    def from_dict(cls, d: dict) -> "TapiodTrace":
        return cls(
            pipeline=[
                TraceStep(
                    layer=s.get("layer", ""),
                    result=s.get("result", ""),
                    latency_ms=float(s.get("latency_ms", 0)),
                )
                for s in d.get("pipeline", [])
            ],
            actual_cost_usd=float(d.get("actual_cost_usd", 0)),
            total_saved_usd=float(d.get("total_saved_usd", 0)),
            cache_source=d.get("cache_source"),
            provider_model=d.get("provider_model", ""),
            memory_tokens_saved=int(d.get("memory_tokens_saved", 0)),
        )


class ToolCallFunction:
    def __init__(self, d: dict):
        self.name: str = d.get("name", "")
        self.arguments: str = d.get("arguments", "")


class ToolCall:
    def __init__(self, d: dict):
        self.id: str = d.get("id", "")
        self.type: str = d.get("type", "function")
        self.function = ToolCallFunction(d.get("function", {}))


class Message:
    def __init__(self, d: dict):
        self.role: str = d.get("role", "assistant")
        self.content: str | None = d.get("content")
        raw_tc = d.get("tool_calls")
        self.tool_calls: list[ToolCall] | None = (
            [ToolCall(tc) for tc in raw_tc] if raw_tc else None
        )


class Choice:
    def __init__(self, d: dict):
        self.index: int = d.get("index", 0)
        self.finish_reason: str | None = d.get("finish_reason")
        self.message = Message(d.get("message", {}))


class Usage:
    def __init__(self, d: dict):
        self.prompt_tokens: int = d.get("prompt_tokens", 0)
        self.completion_tokens: int = d.get("completion_tokens", 0)
        self.total_tokens: int = d.get("total_tokens", 0)


class ChatCompletion:
    def __init__(self, data: dict):
        self._raw = data
        self.model: str = data.get("model", "")
        self.choices: list[Choice] = [Choice(c) for c in data.get("choices", [])]
        self.usage = Usage(data.get("usage", {}))
        raw_trace = data.get("_tapiod_trace")
        self.trace: TapiodTrace | None = TapiodTrace.from_dict(raw_trace) if raw_trace else None

    @property
    def content(self) -> str:
        if self.choices:
            return self.choices[0].message.content or ""
        return ""

    def __repr__(self) -> str:
        saved = f" | saved ${self.trace.total_saved_usd:.6f}" if self.trace else ""
        return f"<ChatCompletion model={self.model!r} content={self.content[:60]!r}{saved}>"
```

- [ ] **Step 5: Fix `sdk/tapiod/client.py` async streaming annotation**

In `_AsyncCompletions.create`, update the return type and add a comment:

```python
async def create(
    self,
    messages: list[dict],
    model: str = "fast-groq",
    stream: bool = False,
    **kwargs,
) -> "ChatCompletion":  # when stream=True, returns AsyncGenerator — use: async for t in await create(stream=True)
    payload = {"model": model, "messages": messages, **kwargs}
    headers = {"Authorization": f"Bearer {self._c.api_key}"}
    url = self._c.base_url + _AGENT_PATH

    if stream:
        return self._astream(url, headers, payload)  # type: ignore[return-value]

    resp = await self._c._http.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    return ChatCompletion(resp.json())
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_native_bugfixes.py -v
```

Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add sdk/tapiod/models.py sdk/tapiod/client.py sdk/tests/__init__.py sdk/tests/test_native_bugfixes.py
git commit -m "fix: add tool_calls to native Message, fix async streaming annotation"
```

---

### Task 2: Shared Transport Layer

**Files:**
- Create: `sdk/tapiod/_transport.py`
- Create: `sdk/tests/test_transport.py`

**Interfaces:**
- Produces: `TapiodTransport(base_url, api_key, timeout)` with `.post(payload: dict) -> dict` and `.stream(payload: dict) -> Iterator[dict]`
- Produces: `AsyncTapiodTransport(base_url, api_key, timeout)` with `async .post(payload: dict) -> dict` and async generator `.stream(payload: dict) -> AsyncIterator[dict]`

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_transport.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from tapiod._transport import TapiodTransport, AsyncTapiodTransport


FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "fast-groq",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


def test_transport_post_returns_dict():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        result = t.post({"model": "fast-groq", "messages": []})
        assert result == FAKE_RESPONSE
        t.close()


def test_transport_post_sends_auth_header():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        t = TapiodTransport(base_url="http://localhost:4001", api_key="my-key")
        t.post({"model": "fast-groq", "messages": []})
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-key"
        t.close()


def test_transport_stream_yields_chunk_dicts():
    chunk1 = {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None, "index": 0}]}
    chunk2 = {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop", "index": 0}]}

    sse_lines = [
        f"data: {json.dumps(chunk1)}",
        f"data: {json.dumps(chunk2)}",
        "data: [DONE]",
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = iter(sse_lines)
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client.stream", return_value=mock_resp):
        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        chunks = list(t.stream({"model": "fast-groq", "messages": []}))
        assert len(chunks) == 2
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"
        t.close()


def test_transport_stream_skips_trace_lines():
    sse_lines = [
        'data: {"choices": [{"delta": {"content": "Hi"}, "finish_reason": null, "index": 0}]}',
        "data: [DONE]",
        "data: [TRACE]{...}",
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = iter(sse_lines)
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client.stream", return_value=mock_resp):
        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        chunks = list(t.stream({"model": "fast-groq", "messages": []}))
        assert len(chunks) == 1
        t.close()


def test_transport_context_manager():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with TapiodTransport(base_url="http://localhost:4001", api_key="test") as t:
            result = t.post({"model": "fast-groq", "messages": []})
        assert result == FAKE_RESPONSE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_transport.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod._transport'`

- [ ] **Step 3: Create `sdk/tapiod/_transport.py`**

```python
from __future__ import annotations
import json
import os
from typing import Iterator, AsyncIterator
import httpx

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")
_PATH = "/api/agent/chat/completions"


class TapiodTransport:
    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def post(self, payload: dict) -> dict:
        resp = self._http.post(
            self.base_url + _PATH,
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def stream(self, payload: dict) -> Iterator[dict]:
        with self._http.stream(
            "POST",
            self.base_url + _PATH,
            json={**payload, "stream": True},
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("[DONE]", ""):
                    break
                if data.startswith("[TRACE]"):
                    continue
                try:
                    yield json.loads(data)
                except Exception:
                    continue

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TapiodTransport":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class AsyncTapiodTransport:
    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def post(self, payload: dict) -> dict:
        resp = await self._http.post(
            self.base_url + _PATH,
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def stream(self, payload: dict) -> AsyncIterator[dict]:
        async with self._http.stream(
            "POST",
            self.base_url + _PATH,
            json={**payload, "stream": True},
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("[DONE]", ""):
                    break
                if data.startswith("[TRACE]"):
                    continue
                try:
                    yield json.loads(data)
                except Exception:
                    continue

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncTapiodTransport":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_transport.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add sdk/tapiod/_transport.py sdk/tests/test_transport.py
git commit -m "feat: add shared transport layer for all SDK adapters"
```

---

### Task 3: Model Name Mapping

**Files:**
- Create: `sdk/tapiod/_core/__init__.py`
- Create: `sdk/tapiod/_core/mapping.py`
- Create: `sdk/tests/test_mapping.py`

**Interfaces:**
- Produces: `resolve_model(model: str, adapter: str) -> str`
  - Returns a TAPIOD alias (e.g. `"heavy-openai"`) for known models
  - Returns `"provider/model"` for unknown models (e.g. `"openai/gpt-5"`)
  - Passes through models already containing `"/"` unchanged

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_mapping.py`:

```python
import pytest
from tapiod._core.mapping import resolve_model


def test_known_openai_model_maps_to_tapiod_alias():
    assert resolve_model("gpt-4o", "openai") == "heavy-openai"


def test_known_openai_mini_maps_to_fast():
    assert resolve_model("gpt-4o-mini", "openai") == "fast-openai"


def test_known_anthropic_opus_maps_to_heavy():
    assert resolve_model("claude-opus-4-8", "anthropic") == "heavy-anthropic"


def test_known_anthropic_sonnet_maps_to_fast():
    assert resolve_model("claude-sonnet-4-6", "anthropic") == "fast-anthropic"


def test_known_gemini_pro_maps_to_heavy():
    assert resolve_model("gemini-pro", "gemini") == "heavy-gemini"


def test_known_gemini_flash_maps_to_fast():
    assert resolve_model("gemini-2.5-flash", "gemini") == "fast-gemini"


def test_known_groq_model_maps_to_alias():
    assert resolve_model("llama-3.1-8b-instant", "groq") == "fast-groq"


def test_unknown_model_gets_provider_prefix():
    assert resolve_model("gpt-5", "openai") == "openai/gpt-5"


def test_unknown_anthropic_model_gets_prefix():
    assert resolve_model("claude-opus-5", "anthropic") == "anthropic/claude-opus-5"


def test_unknown_gemini_model_gets_prefix():
    assert resolve_model("gemini-2.0-ultra", "gemini") == "gemini/gemini-2.0-ultra"


def test_already_prefixed_model_passes_through():
    assert resolve_model("openai/gpt-4o", "openai") == "openai/gpt-4o"


def test_already_prefixed_unknown_model_passes_through():
    assert resolve_model("anthropic/claude-opus-5", "anthropic") == "anthropic/claude-opus-5"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_mapping.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod._core'`

- [ ] **Step 3: Create `sdk/tapiod/_core/__init__.py`**

```bash
mkdir -p sdk/tapiod/_core && touch sdk/tapiod/_core/__init__.py
```

- [ ] **Step 4: Create `sdk/tapiod/_core/mapping.py`**

```python
from __future__ import annotations

OPENAI_MODEL_MAP: dict[str, str] = {
    "gpt-4o":           "heavy-openai",
    "gpt-4o-mini":      "fast-openai",
    "gpt-4-turbo":      "heavy-openai",
    "gpt-3.5-turbo":    "fast-openai",
    "o1":               "heavy-openai",
    "o1-mini":          "fast-openai",
    "o3":               "heavy-openai",
    "o3-mini":          "fast-openai",
    "o4-mini":          "fast-openai",
}

ANTHROPIC_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-8":          "heavy-anthropic",
    "claude-opus-4-7":          "heavy-anthropic",
    "claude-sonnet-4-6":        "fast-anthropic",
    "claude-sonnet-4-5":        "fast-anthropic",
    "claude-haiku-4-5":         "fast-anthropic",
    "claude-3-opus-20240229":   "heavy-anthropic",
    "claude-3-sonnet-20240229": "fast-anthropic",
    "claude-3-haiku-20240307":  "fast-anthropic",
}

GEMINI_MODEL_MAP: dict[str, str] = {
    "gemini-pro":       "heavy-gemini",
    "gemini-1.0-pro":   "heavy-gemini",
    "gemini-1.5-pro":   "heavy-gemini",
    "gemini-1.5-flash": "fast-gemini",
    "gemini-2.0-flash": "fast-gemini",
    "gemini-2.5-pro":   "heavy-gemini",
    "gemini-2.5-flash": "fast-gemini",
    "gemini-3.5-flash": "fast-gemini",
}

GROQ_MODEL_MAP: dict[str, str] = {
    "llama-3.1-8b-instant":    "fast-groq",
    "llama-3.3-70b-versatile": "heavy-groq",
    "llama3-8b-8192":          "fast-groq",
    "llama3-70b-8192":         "heavy-groq",
    "mixtral-8x7b-32768":      "heavy-groq",
    "gemma-7b-it":             "fast-groq",
}

_ADAPTER_MAPS: dict[str, dict[str, str]] = {
    "openai":    OPENAI_MODEL_MAP,
    "anthropic": ANTHROPIC_MODEL_MAP,
    "gemini":    GEMINI_MODEL_MAP,
    "groq":      GROQ_MODEL_MAP,
}

_PROVIDER_PREFIXES: dict[str, str] = {
    "openai":    "openai",
    "anthropic": "anthropic",
    "gemini":    "gemini",
    "groq":      "groq",
}


def resolve_model(model: str, adapter: str) -> str:
    """
    Resolve a provider model name to a TAPIOD routing alias or LiteLLM-prefixed name.

    Priority:
    1. Known model in adapter map → return TAPIOD alias (enables tier routing + caching)
    2. Already provider-prefixed (contains '/') → pass through unchanged
    3. Unknown model → prepend provider prefix (e.g. "gpt-5" → "openai/gpt-5")
       LiteLLM will route it; provider API returns clear error if model doesn't exist
    """
    adapter_map = _ADAPTER_MAPS.get(adapter, {})
    if model in adapter_map:
        return adapter_map[model]
    if "/" in model:
        return model
    prefix = _PROVIDER_PREFIXES.get(adapter, adapter)
    return f"{prefix}/{model}"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_mapping.py -v
```

Expected: 12 passed

- [ ] **Step 6: Commit**

```bash
git add sdk/tapiod/_core/__init__.py sdk/tapiod/_core/mapping.py sdk/tests/test_mapping.py
git commit -m "feat: add model name resolution with provider prefix fallback"
```

---

### Task 4: Request/Response Converters

**Files:**
- Create: `sdk/tapiod/_core/converters.py`
- Create: `sdk/tests/test_converters.py`

**Interfaces:**
- Produces: `anthropic_request_to_openai(model, messages, max_tokens, system, tools, **kwargs) -> dict`
- Produces: `openai_response_to_anthropic(raw: dict) -> dict`
- Produces: `gemini_request_to_openai(model, contents, system_instruction, **kwargs) -> dict`
- Produces: `openai_response_to_gemini(raw: dict) -> dict`

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_converters.py`:

```python
import json
import pytest
from tapiod._core.converters import (
    anthropic_request_to_openai,
    openai_response_to_anthropic,
    gemini_request_to_openai,
    openai_response_to_gemini,
)


# ── Anthropic request translation ─────────────────────────────────────────────

def test_anthropic_system_prepended_as_message():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
        system="You are helpful.",
    )
    assert result["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert result["messages"][1] == {"role": "user", "content": "Hi"}


def test_anthropic_no_system_no_prepend():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert result["messages"][0]["role"] == "user"


def test_anthropic_tool_converted_to_openai_format():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "What's the weather?"}],
        max_tokens=100,
        tools=[{
            "name": "get_weather",
            "description": "Get weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }],
    )
    tool = result["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "get_weather"
    assert tool["function"]["parameters"]["type"] == "object"


def test_anthropic_max_tokens_passed_through():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[],
        max_tokens=512,
    )
    assert result["max_tokens"] == 512


# ── Anthropic response translation ────────────────────────────────────────────

OPENAI_TEXT_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

OPENAI_TOOL_RESPONSE = {
    "id": "chatcmpl-2",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }],
        },
    }],
    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
}


def test_anthropic_response_text_block():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["role"] == "assistant"
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello!"


def test_anthropic_response_stop_reason_mapped():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["stop_reason"] == "end_turn"


def test_anthropic_response_tool_calls_mapped():
    result = openai_response_to_anthropic(OPENAI_TOOL_RESPONSE)
    assert result["stop_reason"] == "tool_use"
    block = result["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "get_weather"
    assert block["input"] == {"location": "NYC"}


def test_anthropic_response_usage_mapped():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


# ── Gemini request translation ─────────────────────────────────────────────────

def test_gemini_string_contents_becomes_user_message():
    result = gemini_request_to_openai(model="heavy-gemini", contents="What is 2+2?")
    assert result["messages"][-1] == {"role": "user", "content": "What is 2+2?"}


def test_gemini_system_instruction_prepended():
    result = gemini_request_to_openai(
        model="heavy-gemini",
        contents="Hi",
        system_instruction="You are a math tutor.",
    )
    assert result["messages"][0] == {"role": "system", "content": "You are a math tutor."}


def test_gemini_list_contents_with_model_role():
    result = gemini_request_to_openai(
        model="heavy-gemini",
        contents=[
            {"role": "user", "parts": ["Hello"]},
            {"role": "model", "parts": ["Hi there"]},
            {"role": "user", "parts": ["What is 2+2?"]},
        ],
    )
    messages = result["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


# ── Gemini response translation ───────────────────────────────────────────────

OPENAI_GEMINI_RESPONSE = {
    "id": "chatcmpl-3",
    "model": "heavy-gemini",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "4"},
    }],
    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
}


def test_gemini_response_candidate_text():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    candidate = result["candidates"][0]
    assert candidate["content"]["parts"][0]["text"] == "4"
    assert candidate["content"]["role"] == "model"


def test_gemini_response_finish_reason_mapped():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    assert result["candidates"][0]["finish_reason"] == "STOP"


def test_gemini_response_usage_metadata():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    meta = result["usage_metadata"]
    assert meta["prompt_token_count"] == 8
    assert meta["candidates_token_count"] == 1
    assert meta["total_token_count"] == 9
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_converters.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod._core.converters'`

- [ ] **Step 3: Create `sdk/tapiod/_core/converters.py`**

```python
from __future__ import annotations
import json


# ── Anthropic ────────────────────────────────────────────────────────────────

def anthropic_request_to_openai(
    model: str,
    messages: list[dict],
    max_tokens: int,
    system: str | None = None,
    tools: list[dict] | None = None,
    **kwargs,
) -> dict:
    oai_messages: list[dict] = []
    if system:
        oai_messages.append({"role": "system", "content": system})
    oai_messages.extend(messages)

    payload: dict = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": max_tokens,
        **kwargs,
    }
    if tools:
        payload["tools"] = [_anthropic_tool_to_openai(t) for t in tools]
    return payload


def _anthropic_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


_STOP_REASON_MAP: dict[str, str] = {
    "stop":       "end_turn",
    "tool_calls": "tool_use",
    "length":     "max_tokens",
}


def openai_response_to_anthropic(raw: dict) -> dict:
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = raw.get("usage", {})

    content: list[dict] = []
    text = message.get("content")
    if text:
        content.append({"type": "text", "text": text})

    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            inp = json.loads(fn.get("arguments", "{}"))
        except Exception:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": inp,
        })

    return {
        "id": raw.get("id", ""),
        "model": raw.get("model", ""),
        "role": "assistant",
        "content": content,
        "stop_reason": _STOP_REASON_MAP.get(finish_reason, "end_turn"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
        "_tapiod_trace": raw.get("_tapiod_trace"),
    }


# ── Gemini ───────────────────────────────────────────────────────────────────

def gemini_request_to_openai(
    model: str,
    contents,
    system_instruction: str | None = None,
    **kwargs,
) -> dict:
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        for item in contents:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
            elif isinstance(item, dict):
                role = "assistant" if item.get("role") == "model" else item.get("role", "user")
                parts = item.get("parts", [])
                text = " ".join(
                    p if isinstance(p, str) else p.get("text", "") for p in parts
                )
                messages.append({"role": role, "content": text})

    return {"model": model, "messages": messages, **kwargs}


_FINISH_REASON_GEMINI: dict[str, str] = {
    "stop":   "STOP",
    "length": "MAX_TOKENS",
    "safety": "SAFETY",
}


def openai_response_to_gemini(raw: dict) -> dict:
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = raw.get("usage", {})

    return {
        "candidates": [{
            "content": {
                "parts": [{"text": message.get("content", "")}],
                "role": "model",
            },
            "finish_reason": _FINISH_REASON_GEMINI.get(finish_reason, "STOP"),
            "index": 0,
        }],
        "usage_metadata": {
            "prompt_token_count": usage.get("prompt_tokens", 0),
            "candidates_token_count": usage.get("completion_tokens", 0),
            "total_token_count": usage.get("total_tokens", 0),
        },
        "_tapiod_trace": raw.get("_tapiod_trace"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_converters.py -v
```

Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add sdk/tapiod/_core/converters.py sdk/tests/test_converters.py
git commit -m "feat: add request/response converters for Anthropic and Gemini"
```

---

### Task 5: OpenAI Adapter

**Files:**
- Create: `sdk/tapiod/openai/__init__.py`
- Create: `sdk/tapiod/openai/_models.py`
- Create: `sdk/tests/test_openai_adapter.py`

**Interfaces:**
- Consumes: `TapiodTransport` from `tapiod._transport`, `resolve_model` from `tapiod._core.mapping`
- Produces: `OpenAI(api_key, base_url, timeout, **kwargs)` with `.chat.completions.create(model, messages, stream, **kwargs)`
- Produces: `AsyncOpenAI` with same interface, async
- Produces: `ChatCompletion` with `.choices[0].message.content`, `.choices[0].message.tool_calls`, `.usage`, `._tapiod_trace`
- Produces: `ChatCompletionChunk` with `.choices[0].delta.content`, `.choices[0].delta.role`, `.choices[0].finish_reason`

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_openai_adapter.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from tapiod.openai import OpenAI
from tapiod.openai._models import ChatCompletion, ChatCompletionChunk


FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "heavy-openai",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

FAKE_TOOL_RESPONSE = {
    "id": "chatcmpl-2",
    "object": "chat.completion",
    "model": "heavy-openai",
    "choices": [{
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }],
        },
    }],
    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
}

FAKE_CHUNKS = [
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello"}, "finish_reason": None}]},
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]},
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
]


@pytest.fixture
def mock_transport_post(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    return mock


@pytest.fixture
def mock_transport_stream(monkeypatch):
    mock = MagicMock(return_value=iter(FAKE_CHUNKS))
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", mock)
    return mock


def test_openai_create_returns_chat_completion(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert isinstance(resp, ChatCompletion)
    assert resp.choices[0].message.content == "Hello!"
    assert resp.choices[0].message.role == "assistant"
    assert resp.usage.prompt_tokens == 10
    client.close()


def test_openai_model_resolved_before_sending(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    call_payload = mock_transport_post.call_args[0][0]
    assert call_payload["model"] == "heavy-openai"
    client.close()


def test_openai_unknown_model_gets_prefixed(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Hi"}],
    )
    call_payload = mock_transport_post.call_args[0][0]
    assert call_payload["model"] == "openai/gpt-5"
    client.close()


def test_openai_tool_calls_in_response(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_TOOL_RESPONSE))
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Weather?"}],
    )
    assert resp.choices[0].message.tool_calls is not None
    tc = resp.choices[0].message.tool_calls[0]
    assert tc.id == "call_abc"
    assert tc.function.name == "get_weather"
    assert tc.function.arguments == '{"location":"NYC"}'
    client.close()


def test_openai_streaming_yields_chunks(mock_transport_stream):
    client = OpenAI(api_key="sk-fake")
    chunks = list(client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    ))
    assert len(chunks) == 3
    assert isinstance(chunks[0], ChatCompletionChunk)
    assert chunks[0].choices[0].delta.content == "Hello"
    assert chunks[1].choices[0].delta.content == " world"
    assert chunks[2].choices[0].finish_reason == "stop"
    client.close()


def test_openai_context_manager(mock_transport_post):
    with OpenAI(api_key="sk-fake") as client:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hi"}],
        )
    assert resp.choices[0].message.content == "Hello!"


def test_chat_completion_tapiod_trace_none_when_absent(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert resp._tapiod_trace is None
    client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_openai_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod.openai'`

- [ ] **Step 3: Create `sdk/tapiod/openai/_models.py`**

```python
from __future__ import annotations
from tapiod.models import TapiodTrace


class ToolCallFunction:
    def __init__(self, d: dict):
        self.name: str = d.get("name", "")
        self.arguments: str = d.get("arguments", "")


class ToolCall:
    def __init__(self, d: dict):
        self.id: str = d.get("id", "")
        self.type: str = d.get("type", "function")
        self.function = ToolCallFunction(d.get("function", {}))


class ChatCompletionMessage:
    def __init__(self, d: dict):
        self.role: str = d.get("role", "assistant")
        self.content: str | None = d.get("content")
        raw_tc = d.get("tool_calls")
        self.tool_calls: list[ToolCall] | None = (
            [ToolCall(tc) for tc in raw_tc] if raw_tc else None
        )


class Choice:
    def __init__(self, d: dict):
        self.index: int = d.get("index", 0)
        self.message = ChatCompletionMessage(d.get("message", {}))
        self.finish_reason: str | None = d.get("finish_reason")


class CompletionUsage:
    def __init__(self, d: dict):
        self.prompt_tokens: int = d.get("prompt_tokens", 0)
        self.completion_tokens: int = d.get("completion_tokens", 0)
        self.total_tokens: int = d.get("total_tokens", 0)


class ChatCompletion:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.object: str = data.get("object", "chat.completion")
        self.model: str = data.get("model", "")
        self.choices: list[Choice] = [Choice(c) for c in data.get("choices", [])]
        self.usage = CompletionUsage(data.get("usage", {}))
        raw_trace = data.get("_tapiod_trace")
        self._tapiod_trace: TapiodTrace | None = (
            TapiodTrace.from_dict(raw_trace) if raw_trace else None
        )

    def __repr__(self) -> str:
        content = self.choices[0].message.content if self.choices else ""
        return f"<ChatCompletion model={self.model!r} content={str(content)[:60]!r}>"


class ChoiceDelta:
    def __init__(self, d: dict):
        self.role: str | None = d.get("role")
        self.content: str | None = d.get("content")
        raw_tc = d.get("tool_calls")
        self.tool_calls: list | None = raw_tc if raw_tc else None


class ChunkChoice:
    def __init__(self, d: dict):
        self.index: int = d.get("index", 0)
        self.delta = ChoiceDelta(d.get("delta", {}))
        self.finish_reason: str | None = d.get("finish_reason")


class ChatCompletionChunk:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.model: str = data.get("model", "")
        self.choices: list[ChunkChoice] = [
            ChunkChoice(c) for c in data.get("choices", [])
        ]
```

- [ ] **Step 4: Create `sdk/tapiod/openai/__init__.py`**

```python
from __future__ import annotations
import os
from typing import Iterator, AsyncIterator

from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod.openai._models import ChatCompletion, ChatCompletionChunk

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")


class _Completions:
    def __init__(self, transport: TapiodTransport):
        self._t = transport

    def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        payload = {"model": resolve_model(model, "openai"), "messages": messages, **kwargs}
        if stream:
            return self._stream(payload)
        return ChatCompletion(self._t.post(payload))

    def _stream(self, payload: dict) -> Iterator[ChatCompletionChunk]:
        for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _Chat:
    def __init__(self, transport: TapiodTransport):
        self.completions = _Completions(transport)


class OpenAI:
    """
    Drop-in replacement for openai.OpenAI.

    Change only the import:
        from tapiod.openai import OpenAI

    api_key is accepted to avoid breaking existing constructor calls but is not
    forwarded to providers — TAPIOD uses its own configured provider keys.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key, timeout)
        self.chat = _Chat(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "OpenAI":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _AsyncCompletions:
    def __init__(self, transport: AsyncTapiodTransport):
        self._t = transport

    async def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion:
        # When stream=True, returns AsyncGenerator — use:
        #   async for chunk in await client.chat.completions.create(stream=True): ...
        payload = {"model": resolve_model(model, "openai"), "messages": messages, **kwargs}
        if stream:
            return self._astream(payload)  # type: ignore[return-value]
        raw = await self._t.post(payload)
        return ChatCompletion(raw)

    async def _astream(self, payload: dict) -> AsyncIterator[ChatCompletionChunk]:
        async for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _AsyncChat:
    def __init__(self, transport: AsyncTapiodTransport):
        self.completions = _AsyncCompletions(transport)


class AsyncOpenAI:
    """
    Drop-in replacement for openai.AsyncOpenAI.

    Streaming usage:
        stream = await client.chat.completions.create(stream=True, ...)
        async for chunk in stream:
            print(chunk.choices[0].delta.content)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = AsyncTapiodTransport(url, key, timeout)
        self.chat = _AsyncChat(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncOpenAI":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


__all__ = ["OpenAI", "AsyncOpenAI"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_openai_adapter.py -v
```

Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add sdk/tapiod/openai/ sdk/tests/test_openai_adapter.py
git commit -m "feat: add OpenAI drop-in adapter (OpenAI, AsyncOpenAI)"
```

---

### Task 6: Groq Adapter

**Files:**
- Create: `sdk/tapiod/groq/__init__.py`
- Create: `sdk/tests/test_groq_adapter.py`

**Interfaces:**
- Consumes: `OpenAI`, `AsyncOpenAI` from `tapiod.openai`
- Produces: `Groq` (alias for `OpenAI` with groq model resolution), `AsyncGroq`

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_groq_adapter.py`:

```python
import pytest
from unittest.mock import MagicMock
from tapiod.groq import Groq, AsyncGroq
from tapiod.openai._models import ChatCompletion

FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "fast-groq",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hi", "tool_calls": None}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def test_groq_client_exists():
    client = Groq(api_key="gsk_fake")
    assert hasattr(client, "chat")
    assert hasattr(client.chat, "completions")
    client.close()


def test_groq_model_resolved_to_tapiod_alias(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Groq(api_key="gsk_fake")
    client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "Hi"}],
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "fast-groq"
    client.close()


def test_groq_unknown_model_gets_groq_prefix(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Groq(api_key="gsk_fake")
    client.chat.completions.create(
        model="llama-4-scout",
        messages=[{"role": "user", "content": "Hi"}],
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "groq/llama-4-scout"
    client.close()


def test_async_groq_client_exists():
    client = AsyncGroq(api_key="gsk_fake")
    assert hasattr(client, "chat")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_groq_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod.groq'`

- [ ] **Step 3: Create `sdk/tapiod/groq/__init__.py`**

Groq's SDK is an OpenAI fork. Re-export the OpenAI adapter with Groq class names, overriding the adapter key so `resolve_model` uses the Groq map.

```python
from __future__ import annotations
import os
from typing import Iterator, AsyncIterator

from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod.openai._models import ChatCompletion, ChatCompletionChunk

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")


class _Completions:
    def __init__(self, transport: TapiodTransport):
        self._t = transport

    def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        payload = {"model": resolve_model(model, "groq"), "messages": messages, **kwargs}
        if stream:
            return self._stream(payload)
        return ChatCompletion(self._t.post(payload))

    def _stream(self, payload: dict) -> Iterator[ChatCompletionChunk]:
        for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _Chat:
    def __init__(self, transport: TapiodTransport):
        self.completions = _Completions(transport)


class Groq:
    """Drop-in replacement for groq.Groq. Groq's SDK is an OpenAI fork — identical interface."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key, timeout)
        self.chat = _Chat(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Groq":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _AsyncCompletions:
    def __init__(self, transport: AsyncTapiodTransport):
        self._t = transport

    async def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion:
        payload = {"model": resolve_model(model, "groq"), "messages": messages, **kwargs}
        if stream:
            return self._astream(payload)  # type: ignore[return-value]
        raw = await self._t.post(payload)
        return ChatCompletion(raw)

    async def _astream(self, payload: dict) -> AsyncIterator[ChatCompletionChunk]:
        async for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _AsyncChat:
    def __init__(self, transport: AsyncTapiodTransport):
        self.completions = _AsyncCompletions(transport)


class AsyncGroq:
    """Drop-in replacement for groq.AsyncGroq."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = AsyncTapiodTransport(url, key, timeout)
        self.chat = _AsyncChat(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncGroq":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


__all__ = ["Groq", "AsyncGroq"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_groq_adapter.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add sdk/tapiod/groq/ sdk/tests/test_groq_adapter.py
git commit -m "feat: add Groq drop-in adapter (Groq, AsyncGroq)"
```

---

### Task 7: Anthropic Adapter

**Files:**
- Create: `sdk/tapiod/anthropic/__init__.py`
- Create: `sdk/tapiod/anthropic/_models.py`
- Create: `sdk/tests/test_anthropic_adapter.py`

**Interfaces:**
- Consumes: `TapiodTransport` from `tapiod._transport`, `resolve_model` from `tapiod._core.mapping`, `anthropic_request_to_openai` and `openai_response_to_anthropic` from `tapiod._core.converters`
- Produces: `Anthropic(api_key)` with `.messages.create(model, messages, max_tokens, system, tools, **kwargs) -> Message`
- Produces: `Anthropic` with `.messages.stream(...)` context manager exposing `.text_stream: Iterator[str]` and `.get_final_message() -> Message`
- Produces: `AsyncAnthropic` with same interface, async

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_anthropic_adapter.py`:

```python
import pytest
from unittest.mock import MagicMock
from tapiod.anthropic import Anthropic
from tapiod.anthropic._models import Message, TextBlock, ToolUseBlock

FAKE_OAI_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

FAKE_OAI_TOOL_RESPONSE = {
    "id": "chatcmpl-2",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }],
        },
    }],
    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
}


def test_anthropic_create_returns_message(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert isinstance(resp, Message)
    assert resp.role == "assistant"
    client.close()


def test_anthropic_text_block_in_content(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert isinstance(resp.content[0], TextBlock)
    assert resp.content[0].text == "Hello!"
    client.close()


def test_anthropic_stop_reason_end_turn(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert resp.stop_reason == "end_turn"
    client.close()


def test_anthropic_usage_tokens(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5
    client.close()


def test_anthropic_tool_use_block(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_TOOL_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Weather?"}],
        max_tokens=100,
    )
    assert resp.stop_reason == "tool_use"
    block = resp.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.name == "get_weather"
    assert block.input == {"location": "NYC"}
    client.close()


def test_anthropic_system_passed_as_param(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Anthropic(api_key="sk-ant-fake")
    client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
        system="You are helpful.",
    )
    payload = mock.call_args[0][0]
    assert payload["messages"][0] == {"role": "system", "content": "You are helpful."}
    client.close()


def test_anthropic_model_resolved(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Anthropic(api_key="sk-ant-fake")
    client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "heavy-anthropic"
    client.close()


def test_anthropic_streaming_text_stream(monkeypatch):
    chunks = [
        {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None, "index": 0}]},
        {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop", "index": 0}]},
    ]
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", MagicMock(return_value=iter(chunks)))
    client = Anthropic(api_key="sk-ant-fake")
    with client.messages.stream(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    ) as stream:
        tokens = list(stream.text_stream)
    assert tokens == ["Hello", " world"]
    client.close()


def test_anthropic_streaming_get_final_message(monkeypatch):
    chunks = [
        {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None, "index": 0}]},
        {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
    ]
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", MagicMock(return_value=iter(chunks)))
    client = Anthropic(api_key="sk-ant-fake")
    with client.messages.stream(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    ) as stream:
        for _ in stream.text_stream:
            pass
        msg = stream.get_final_message()
    assert isinstance(msg, Message)
    assert msg.content[0].text == "Hi"
    client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_anthropic_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod.anthropic'`

- [ ] **Step 3: Create `sdk/tapiod/anthropic/_models.py`**

```python
from __future__ import annotations
from tapiod.models import TapiodTrace


class TextBlock:
    def __init__(self, d: dict):
        self.type: str = "text"
        self.text: str = d.get("text", "")


class ToolUseBlock:
    def __init__(self, d: dict):
        self.type: str = "tool_use"
        self.id: str = d.get("id", "")
        self.name: str = d.get("name", "")
        self.input: dict = d.get("input", {})


class Usage:
    def __init__(self, d: dict):
        self.input_tokens: int = d.get("input_tokens", 0)
        self.output_tokens: int = d.get("output_tokens", 0)


class Message:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.model: str = data.get("model", "")
        self.role: str = data.get("role", "assistant")
        self.stop_reason: str = data.get("stop_reason", "end_turn")
        self.usage = Usage(data.get("usage", {}))
        self._tapiod_trace: TapiodTrace | None = None

        raw_content = data.get("content", [])
        self.content: list[TextBlock | ToolUseBlock] = []
        for block in raw_content:
            if block.get("type") == "tool_use":
                self.content.append(ToolUseBlock(block))
            else:
                self.content.append(TextBlock(block))

    def __repr__(self) -> str:
        text = self.content[0].text if self.content and isinstance(self.content[0], TextBlock) else ""
        return f"<Message role={self.role!r} stop_reason={self.stop_reason!r} text={text[:60]!r}>"
```

- [ ] **Step 4: Create `sdk/tapiod/anthropic/__init__.py`**

```python
from __future__ import annotations
import os
from typing import Iterator, AsyncIterator

from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod._core.converters import anthropic_request_to_openai, openai_response_to_anthropic
from tapiod.anthropic._models import Message

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")


class _MessageStreamManager:
    def __init__(self, transport: TapiodTransport, payload: dict):
        self._t = transport
        self._payload = payload
        self._final: Message | None = None

    def __enter__(self) -> "_MessageStreamManager":
        return self

    def __exit__(self, *_) -> None:
        pass

    @property
    def text_stream(self) -> Iterator[str]:
        full_text = ""
        for chunk_dict in self._t.stream(self._payload):
            delta = (chunk_dict.get("choices") or [{}])[0].get("delta", {})
            token = delta.get("content")
            if token:
                full_text += token
                yield token
        self._final = Message({
            "id": "",
            "model": self._payload.get("model", ""),
            "role": "assistant",
            "content": [{"type": "text", "text": full_text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        return self._final  # type: ignore[return-value]


class _Messages:
    def __init__(self, transport: TapiodTransport):
        self._t = transport

    def create(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Message:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            **kwargs,
        )
        raw = self._t.post(payload)
        return Message(openai_response_to_anthropic(raw))

    def stream(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        **kwargs,
    ) -> _MessageStreamManager:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            **kwargs,
        )
        return _MessageStreamManager(self._t, payload)


class Anthropic:
    """
    Drop-in replacement for anthropic.Anthropic.

    Change only the import:
        from tapiod.anthropic import Anthropic

    Usage::
        client = Anthropic(api_key="sk-ant-...")
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hi"}],
        )
        print(resp.content[0].text)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key, timeout)
        self.messages = _Messages(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Anthropic":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _AsyncMessageStreamManager:
    def __init__(self, transport: AsyncTapiodTransport, payload: dict):
        self._t = transport
        self._payload = payload
        self._final: Message | None = None

    async def __aenter__(self) -> "_AsyncMessageStreamManager":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._astream()

    async def _astream(self) -> AsyncIterator[str]:
        full_text = ""
        async for chunk_dict in self._t.stream(self._payload):
            delta = (chunk_dict.get("choices") or [{}])[0].get("delta", {})
            token = delta.get("content")
            if token:
                full_text += token
                yield token
        self._final = Message({
            "id": "",
            "model": self._payload.get("model", ""),
            "role": "assistant",
            "content": [{"type": "text", "text": full_text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })

    async def get_final_message(self) -> Message:
        if self._final is None:
            async for _ in self._astream():
                pass
        return self._final  # type: ignore[return-value]


class _AsyncMessages:
    def __init__(self, transport: AsyncTapiodTransport):
        self._t = transport

    async def create(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Message:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            **kwargs,
        )
        raw = await self._t.post(payload)
        return Message(openai_response_to_anthropic(raw))

    def stream(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        **kwargs,
    ) -> _AsyncMessageStreamManager:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            **kwargs,
        )
        return _AsyncMessageStreamManager(self._t, payload)


class AsyncAnthropic:
    """Drop-in replacement for anthropic.AsyncAnthropic."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = AsyncTapiodTransport(url, key, timeout)
        self.messages = _AsyncMessages(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncAnthropic":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


__all__ = ["Anthropic", "AsyncAnthropic"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_anthropic_adapter.py -v
```

Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add sdk/tapiod/anthropic/ sdk/tests/test_anthropic_adapter.py
git commit -m "feat: add Anthropic drop-in adapter (Anthropic, AsyncAnthropic)"
```

---

### Task 8: Google Gemini Adapter

**Files:**
- Create: `sdk/tapiod/google/__init__.py`
- Create: `sdk/tapiod/google/generativeai/__init__.py`
- Create: `sdk/tapiod/google/generativeai/_models.py`
- Create: `sdk/tests/test_gemini_adapter.py`

**Interfaces:**
- Consumes: `TapiodTransport`, `resolve_model`, `gemini_request_to_openai`, `openai_response_to_gemini`
- Produces: `configure(api_key: str)` — module-level function, stores key (not used by gateway but accepted for drop-in compat)
- Produces: `GenerativeModel(model_name, system_instruction)` with `.generate_content(contents) -> GenerateContentResponse`
- Produces: `GenerateContentResponse` with `.text`, `.candidates[0].content.parts[0].text`, `.usage_metadata`

- [ ] **Step 1: Write failing tests**

Create `sdk/tests/test_gemini_adapter.py`:

```python
import pytest
from unittest.mock import MagicMock
import tapiod.google.generativeai as genai
from tapiod.google.generativeai import GenerativeModel
from tapiod.google.generativeai._models import GenerateContentResponse, Part

FAKE_OAI_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-gemini",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "4"},
    }],
    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
}


def test_configure_does_not_raise():
    genai.configure(api_key="AIzaSy_fake")


def test_generate_content_returns_response(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert isinstance(resp, GenerateContentResponse)


def test_response_text_shortcut(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.text == "4"


def test_response_candidates_parts(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.candidates[0].content.parts[0].text == "4"
    assert resp.candidates[0].content.role == "model"


def test_response_usage_metadata(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.usage_metadata.prompt_token_count == 8
    assert resp.usage_metadata.candidates_token_count == 1
    assert resp.usage_metadata.total_token_count == 9


def test_model_resolved_to_tapiod_alias(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["model"] == "heavy-gemini"


def test_unknown_model_gets_gemini_prefix(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-2.0-ultra")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["model"] == "gemini/gemini-2.0-ultra"


def test_system_instruction_prepended(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro", system_instruction="You are a tutor.")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["messages"][0] == {"role": "system", "content": "You are a tutor."}


def test_list_contents_with_model_role(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro")
    model.generate_content([
        {"role": "user", "parts": ["Hello"]},
        {"role": "model", "parts": ["Hi"]},
        {"role": "user", "parts": ["2+2?"]},
    ])
    payload = mock.call_args[0][0]
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["user", "assistant", "user"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sdk && pytest tests/test_gemini_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'tapiod.google'`

- [ ] **Step 3: Create empty `__init__.py` files for the package hierarchy**

```bash
mkdir -p sdk/tapiod/google/generativeai
touch sdk/tapiod/google/__init__.py
```

- [ ] **Step 4: Create `sdk/tapiod/google/generativeai/_models.py`**

```python
from __future__ import annotations
from tapiod.models import TapiodTrace


class Part:
    def __init__(self, d: dict):
        self.text: str = d.get("text", "")


class Content:
    def __init__(self, d: dict):
        self.parts: list[Part] = [Part(p) for p in d.get("parts", [])]
        self.role: str = d.get("role", "model")


class FinishReason:
    STOP = "STOP"
    MAX_TOKENS = "MAX_TOKENS"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class Candidate:
    def __init__(self, d: dict):
        self.content = Content(d.get("content", {}))
        self.finish_reason: str = d.get("finish_reason", FinishReason.STOP)
        self.index: int = d.get("index", 0)


class UsageMetadata:
    def __init__(self, d: dict):
        self.prompt_token_count: int = d.get("prompt_token_count", 0)
        self.candidates_token_count: int = d.get("candidates_token_count", 0)
        self.total_token_count: int = d.get("total_token_count", 0)


class GenerateContentResponse:
    def __init__(self, data: dict):
        self.candidates: list[Candidate] = [
            Candidate(c) for c in data.get("candidates", [])
        ]
        self.usage_metadata = UsageMetadata(data.get("usage_metadata", {}))
        raw_trace = data.get("_tapiod_trace")
        self._tapiod_trace: TapiodTrace | None = (
            TapiodTrace.from_dict(raw_trace) if raw_trace else None
        )

    @property
    def text(self) -> str:
        try:
            return self.candidates[0].content.parts[0].text
        except (IndexError, AttributeError):
            return ""

    def __repr__(self) -> str:
        return f"<GenerateContentResponse text={self.text[:60]!r}>"
```

- [ ] **Step 5: Create `sdk/tapiod/google/generativeai/__init__.py`**

```python
from __future__ import annotations
import os
from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod._core.converters import gemini_request_to_openai, openai_response_to_gemini
from tapiod.google.generativeai._models import GenerateContentResponse

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")

_configured_api_key: str | None = None


def configure(api_key: str, **kwargs) -> None:
    """Accept api_key for drop-in compatibility. TAPIOD uses its own configured provider keys."""
    global _configured_api_key
    _configured_api_key = api_key


class GenerativeModel:
    """
    Drop-in replacement for google.generativeai.GenerativeModel.

    Change only the import:
        import tapiod.google.generativeai as genai
        genai.configure(api_key="AIza...")
        model = genai.GenerativeModel("gemini-pro")
        resp = model.generate_content("Hello")
        print(resp.text)
    """

    def __init__(
        self,
        model_name: str,
        system_instruction: str | None = None,
        **kwargs,
    ):
        self._model_name = model_name
        self._system_instruction = system_instruction
        url = os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key)

    def generate_content(self, contents, **kwargs) -> GenerateContentResponse:
        resolved = resolve_model(self._model_name, "gemini")
        payload = gemini_request_to_openai(
            model=resolved,
            contents=contents,
            system_instruction=self._system_instruction,
            **kwargs,
        )
        raw = self._transport.post(payload)
        return GenerateContentResponse(openai_response_to_gemini(raw))

    def close(self) -> None:
        self._transport.close()


__all__ = ["configure", "GenerativeModel"]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd sdk && pytest tests/test_gemini_adapter.py -v
```

Expected: 9 passed

- [ ] **Step 7: Commit**

```bash
git add sdk/tapiod/google/ sdk/tests/test_gemini_adapter.py
git commit -m "feat: add Google Gemini drop-in adapter (GenerativeModel, configure)"
```

---

### Task 9: Package Wiring and Full Test Run

**Files:**
- Modify: `sdk/pyproject.toml`
- Create: `sdk/tests/conftest.py`

**Interfaces:**
- Produces: `pip install -e sdk/` installs all adapter submodules
- Produces: `cd sdk && pytest tests/ -v` runs all tests and they all pass

- [ ] **Step 1: Create `sdk/tests/conftest.py`** (shared fixtures for future use)

```python
import pytest


@pytest.fixture
def tapiod_base_url():
    return "http://localhost:4001"


@pytest.fixture
def tapiod_api_key():
    return "test-key"
```

- [ ] **Step 2: Update `sdk/pyproject.toml`**

Replace the entire file:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tapiod"
version = "0.2.0"
description = "Universal LLM SDK drop-in — replace OpenAI, Anthropic, Gemini, or Groq with one import line and get caching, routing, and observability for free"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "httpx>=0.27",
]

[project.scripts]
tapiod = "tapiod.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["tapiod*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Reinstall the package so new submodules are discovered**

```bash
cd sdk && pip install -e . -q
```

- [ ] **Step 4: Run the full test suite**

```bash
cd sdk && pytest tests/ -v
```

Expected output (all tests pass):
```
tests/test_native_bugfixes.py::test_message_tool_calls_none_when_absent PASSED
tests/test_native_bugfixes.py::test_message_tool_calls_parsed_when_present PASSED
tests/test_native_bugfixes.py::test_message_content_can_be_none PASSED
tests/test_native_bugfixes.py::test_chat_completion_tool_calls_accessible PASSED
tests/test_transport.py::test_transport_post_returns_dict PASSED
tests/test_transport.py::test_transport_post_sends_auth_header PASSED
tests/test_transport.py::test_transport_stream_yields_chunk_dicts PASSED
tests/test_transport.py::test_transport_stream_skips_trace_lines PASSED
tests/test_transport.py::test_transport_context_manager PASSED
tests/test_mapping.py::... (12 tests) PASSED
tests/test_converters.py::... (16 tests) PASSED
tests/test_openai_adapter.py::... (7 tests) PASSED
tests/test_groq_adapter.py::... (4 tests) PASSED
tests/test_anthropic_adapter.py::... (9 tests) PASSED
tests/test_gemini_adapter.py::... (9 tests) PASSED
```

- [ ] **Step 5: Verify import works as drop-in**

```bash
cd sdk && python -c "
from tapiod.openai import OpenAI
from tapiod.anthropic import Anthropic
import tapiod.google.generativeai as genai
from tapiod.groq import Groq
print('All adapters import cleanly')
print('OpenAI:', OpenAI)
print('Anthropic:', Anthropic)
print('GenerativeModel:', genai.GenerativeModel)
print('Groq:', Groq)
"
```

Expected:
```
All adapters import cleanly
OpenAI: <class 'tapiod.openai.OpenAI'>
Anthropic: <class 'tapiod.anthropic.Anthropic'>
GenerativeModel: <class 'tapiod.google.generativeai.GenerativeModel'>
Groq: <class 'tapiod.groq.Groq'>
```

- [ ] **Step 6: Commit**

```bash
git add sdk/pyproject.toml sdk/tests/conftest.py
git commit -m "feat: wire all SDK adapter submodules, bump version to 0.2.0"
```

---

## Self-Review

**Spec coverage check:**
- ✅ OpenAI: `OpenAI`, `AsyncOpenAI` — Task 5
- ✅ Anthropic: `Anthropic`, `AsyncAnthropic` — Task 7
- ✅ Gemini: `GenerativeModel`, `configure()` — Task 8
- ✅ Groq: `Groq`, `AsyncGroq` — Task 6
- ✅ `_transport.py` shared HTTP layer — Task 2
- ✅ `_core/mapping.py` with `resolve_model()` + unmapped model prefix fallback — Task 3
- ✅ `_core/converters.py` Anthropic ↔ OpenAI and Gemini ↔ OpenAI — Task 4
- ✅ Bug fix: `Message.tool_calls` — Task 1
- ✅ Bug fix: async streaming annotation — Task 1
- ✅ `google/__init__.py` empty file for Python packaging — Task 8 Step 3
- ✅ No new runtime deps (only httpx) — pyproject.toml Task 9
- ✅ `api_key` accepted but not forwarded — OpenAI, Anthropic, Gemini, Groq constructors
- ✅ Anthropic `.messages.stream()` context manager with `.text_stream` and `.get_final_message()` — Task 7
- ✅ Streaming yields chunk objects (not raw strings) for OpenAI/Groq adapters — Task 5, 6

**Type consistency check:**
- `resolve_model(model: str, adapter: str) -> str` — called correctly in Tasks 5, 6, 7, 8 with `"openai"`, `"groq"`, `"anthropic"`, `"gemini"`
- `TapiodTransport.post(payload: dict) -> dict` — called correctly in all adapters
- `TapiodTransport.stream(payload: dict) -> Iterator[dict]` — called correctly
- `openai_response_to_anthropic(raw: dict) -> dict` — called in Task 7 with raw gateway response
- `Message(data: dict)` — constructed in Task 7 from `openai_response_to_anthropic()` output
- `GenerateContentResponse(data: dict)` — constructed in Task 8 from `openai_response_to_gemini()` output
- `ChatCompletion(data: dict)` — constructed in Tasks 5, 6 from raw gateway response

No gaps or inconsistencies found.
