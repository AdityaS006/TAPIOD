# TAPIOD Python SDK

Lightweight Python client for the TAPIOD LLM gateway. OpenAI-compatible interface with automatic access to TAPIOD's semantic caching, smart routing, and observability trace.

## Install

```bash
pip install -e ./tapiod-sdk          # from repo root
# or, once published:
pip install tapiod
```

## Quickstart

```python
from tapiod import TapiodClient

client = TapiodClient(
    base_url="http://localhost:4001",   # your TAPIOD gateway
    api_key="tapiod",                   # set TAPIOD_API_KEY env var instead
)

resp = client.chat.completions.create(
    model="fast-groq",                  # or heavy-groq, fast-openai, etc.
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)

print(resp.content)
# → "4"

if resp.trace:
    print(f"Provider : {resp.trace.provider_model}")
    print(f"Cost     : ${resp.trace.actual_cost_usd:.6f}")
    print(f"Saved    : ${resp.trace.total_saved_usd:.6f}")
    print(f"Cache    : {resp.trace.cache_source or 'miss'}")
```

## Streaming

```python
for token in client.chat.completions.create(
    model="fast-groq",
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
    stream=True,
):
    print(token, end="", flush=True)
print()
```

## Async

```python
import asyncio
from tapiod import AsyncTapiodClient

async def main():
    async with AsyncTapiodClient() as client:
        resp = await client.chat.completions.create(
            model="heavy-groq",
            messages=[{"role": "user", "content": "Explain async/await."}],
        )
        print(resp.content)

asyncio.run(main())
```

## Configuration

| Parameter | Env var | Default |
|-----------|---------|---------|
| `base_url` | `TAPIOD_URL` | `http://localhost:4001` |
| `api_key` | `TAPIOD_API_KEY` | `tapiod` |
| `timeout` | — | `60.0` s |

## Response object

```python
resp.content          # str — assistant reply
resp.model            # str — model alias used
resp.usage.total_tokens

resp.trace            # TapiodTrace | None
resp.trace.pipeline          # list[TraceStep] — layer-by-layer breakdown
resp.trace.actual_cost_usd   # float
resp.trace.total_saved_usd   # float (vs always using heavy model)
resp.trace.cache_source      # "semantic" | None
resp.trace.provider_model    # actual model used (e.g. "groq/llama-3.1-8b-instant")
```

## Available models

| Alias | Provider | Use for |
|-------|----------|---------|
| `fast-groq` | Groq llama-3.1-8b-instant | Simple Q&A, classification, short tasks |
| `heavy-groq` | Groq llama-3.3-70b-versatile | Complex reasoning, code, long-form |
| `fast-openai` | GPT-4o-mini | OpenAI fast tier |
| `heavy-openai` | GPT-4o | OpenAI heavy tier |
| `fast-anthropic` | claude-sonnet-4-6 | Anthropic fast tier |
| `heavy-anthropic` | claude-opus-4-8 | Anthropic heavy tier |
| `fast-gemini` | gemini-3.5-flash | Google fast tier |
| `heavy-gemini` | gemini-3.1-pro | Google heavy tier |

TAPIOD's router may override your model choice if semantic cache or RouteLLM routing redirects the request.
