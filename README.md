# TAPIOD — Enterprise LLM Gateway

**Token-Aware Proxy with Intelligent Optimization & Dispatch.**

TAPIOD sits between your app and any LLM provider and quietly makes every request **cheaper and faster** — semantic caching, smart model routing, and tool injection — while a live dashboard shows you exactly what it saved on every call.

> Swap providers without touching application code. Drop-in OpenAI-compatible API.

---

## ⚡ 5-Minute Setup

**One command. Everything installs, seeds, and launches automatically.**

**Linux / macOS / WSL:**
```bash
git clone https://github.com/AdityaS006/TAPIOD.git && cd TAPIOD
cp backend/.env.example backend/.env   # add your GROQ_API_KEY
chmod +x scripts/setup.sh && ./scripts/setup.sh
```

**Windows:**
```
git clone https://github.com/AdityaS006/TAPIOD.git
cd TAPIOD
copy backend\.env.example backend\.env   # add your GROQ_API_KEY
scripts\setup.bat
```

The script handles everything: Docker infra → Python venv → pip install → Qdrant seeding → production build → launch all three services. Opens the dashboard automatically when ready.

> Get a free Groq API key (no credit card) at **https://console.groq.com**

> Full step-by-step guide and troubleshooting: [**SETUP.md**](SETUP.md)

---

## 🎯 What TAPIOD adds

Five stacked layers of optimization. Each one runs only when it pays off, and short-circuits the request the moment it can.

| | Layer | Mechanism | Payoff |
|---|-------|-----------|--------|
| 🟥 | **Exact cache** | Redis key lookup | ~0.1 ms, **0 tokens** on repeat prompts |
| 🔷 | **Semantic cache** | Qdrant cosine similarity (≥ 0.85) | ~5 ms, **0 tokens** for *similar* questions |
| 🔀 | **Smart routing** | KNN over 5,000 arena prompts | Sends simple prompts to a **~10× cheaper** model |
| 🔧 | **Tool injection** | Qdrant vector search on tool registry | Injects **only the tools that matter** per request |
| 🤖 | **Agentic loop** | Multi-turn tool execution in the gateway | Runs tools server-side, returns the **final answer** |

Every response carries a `_tapiod_trace` showing the pipeline, the model chosen, and the dollars saved.

---

## 🗺️ Architecture

```
Browser  :3000   Next.js Dashboard
                 Live Traces · Playground · Observability · Config · Memory
                       │
Client / SDK  ─────────┤  POST /api/agent/chat/completions
                       ▼
              FastAPI Gateway  :4001   ← backend/main.py
                 ├─ pre-call :  exact cache → semantic cache → route → inject tools
                 ├─ forward  ─►  LiteLLM Proxy  :4000  ─►  Groq · OpenAI · Anthropic · Gemini
                 ├─ post-call:  write cache → log to PostgreSQL
                 └─ agent loop: detect tool_calls → tapiod_agent/detector.py → re-call LLM
                       │
              Infrastructure (Docker)
                 ├─ Qdrant      :6333   routing_examples · tool_registry · semantic_cache_384 · user_memory
                 ├─ PostgreSQL  :5432   requests_log · chat_sessions
                 └─ Redis       :6379   exact-match cache
```

> Deeper dive with cost analysis and request-flow diagrams: [`docs/architecture.md`](docs/architecture.md)

---

## 📡 Using the API

Point any OpenAI-style client at the gateway. The agentic endpoint runs the full pipeline and resolves tool calls for you.

```http
POST http://localhost:4001/api/agent/chat/completions
Authorization: Bearer <your-api-key>
Content-Type: application/json

{
  "model": "fast-groq",
  "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
  "stream": false
}
```

Every response includes a `_tapiod_trace`:

```jsonc
{
  "choices": [{ "message": { "content": "..." } }],
  "_tapiod_trace": {
    "pipeline": [
      { "layer": "semantic_cache", "result": "miss",   "latency_ms": 4.2 },
      { "layer": "router",         "result": "fast",   "latency_ms": 1.1 },
      { "layer": "tool_inject",    "result": "1 tool", "latency_ms": 2.0 },
      { "layer": "llm_call",       "result": "ok",     "latency_ms": 412 }
    ],
    "actual_cost_usd": 0.000021,
    "total_saved_usd": 0.000189,
    "cache_source": null,
    "provider_model": "groq/llama-3.1-8b-instant"
  }
}
```

### Other endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/metrics` | Aggregate stats: requests, cache hits, cost, latency |
| `GET`  | `/api/traces` | Recent request traces |
| `GET`  | `/api/observability` | Time-series data for the charts |
| `GET`  | `/api/savings` | Cumulative dollars saved by layer |
| `GET`  | `/api/config` | Current routing config (model priority, fallbacks) |
| `POST` | `/api/config/model` | Update model tier / priority (no restart) |
| `POST` | `/api/config/keys` | Add or rotate provider API keys |
| `GET`  | `/api/memory` | Per-tenant memory facts |

---

## 🐍 Python SDK

```bash
pip install -e ./sdk
```

```python
from tapiod import TapiodClient

with TapiodClient() as client:
    resp = client.chat.completions.create(
        model="fast-groq",
        messages=[{"role": "user", "content": "Summarize quantum entanglement."}],
    )
    print(resp.content)
    print(f"Saved ${resp.trace.total_saved_usd:.6f}")
```

`AsyncTapiodClient` is also available. Full SDK docs: [`sdk/README.md`](sdk/README.md)

---

## 🤖 Models

8 aliases across 4 providers, in **fast** and **heavy** tiers. Add only the keys you have to `backend/.env` — any provider without a key is skipped and the gateway **falls back to Groq** automatically.

| Alias | Model | Tier | Provider |
|-------|-------|------|----------|
| `fast-groq` | llama-3.1-8b-instant | Fast | Groq (free) |
| `heavy-groq` | llama-3.3-70b-versatile | Heavy | Groq (free) |
| `fast-openai` | gpt-4o-mini | Fast | OpenAI |
| `heavy-openai` | gpt-4o | Heavy | OpenAI |
| `fast-anthropic` | claude-sonnet-4-6 | Fast | Anthropic |
| `heavy-anthropic` | claude-opus-4-8 | Heavy | Anthropic |
| `fast-gemini` | gemini-3.5-flash | Fast | Gemini |
| `heavy-gemini` | gemini-3.1-pro-preview | Heavy | Gemini |

> Tier mapping, model priority, and fallback order are all editable from the dashboard **Config** page — no restart required.

---

## 🔷 Qdrant collections

| Collection | Points | Purpose | Populated by |
|------------|--------|---------|--------------|
| `routing_examples` | 5,000 | KNN routing — fast vs heavy | `python seeds/seed_all.py` (from `arena_prompts.json`) |
| `tool_registry` | dynamic | Tool embeddings for injection | Gateway startup |
| `semantic_cache_384` | grows | Semantic response cache | Live traffic |
| `user_memory` | grows | Per-tenant memory facts | Live traffic |

The routing brain is reproducible: **`backend/seeds/arena_prompts.json`** (5,000 labeled prompts) ships in this repo, and `seeds/seed_all.py` rebuilds Qdrant from it after a fresh `docker compose up`.

---

## 🧭 Project map

```
TAPIOD/
├── backend/                        # Python backend
│   ├── main.py                     # FastAPI server (:4001) + all HTTP routes
│   ├── tapiod_agent/
│   │   ├── detector.py             # Tool registry, implementations, execute_tool()
│   │   └── llm_service.py          # GatewayHooks — LiteLLM pre/post callbacks
│   ├── router.py                   # KNN routing + provider/fallback selection
│   ├── cache.py                    # Redis + Qdrant cache read/write
│   ├── memory.py                   # Per-tenant user memory (Qdrant)
│   ├── context.py                  # Per-request context & system-prompt injection
│   ├── cost.py                     # Token cost + savings calculation
│   ├── crypto.py                   # API key encryption (Fernet)
│   ├── litellm_config.yaml         # Model list, router settings, provider keys
│   ├── seeds/
│   │   ├── arena_prompts.json      # 5,000 labeled prompts — routing training data
│   │   └── seed_all.py             # ← RUN AFTER docker compose up to populate Qdrant
│   ├── tests/
│   │   ├── unit/                   # pytest unit tests (30 tests, all passing)
│   │   └── benchmarks/             # Provider benchmark scripts + results
│   └── requirements.txt
│
├── frontend/                       # Next.js 16 dashboard (App Router)
│   ├── content/
│   │   └── nav.ts                  # Centralized navigation config
│   └── src/app/
│       ├── page.tsx                # Live Traces — real-time request log + trace viewer
│       ├── playground/             # Chat playground with model selector
│       ├── observability/          # Charts: cost, cache hit rate, routing split
│       ├── config/                 # API keys, model priority, fallback config
│       └── memory/                 # Per-tenant memory viewer
│
├── sdk/                            # Python client SDK
│   └── tapiod/
│       ├── client.py               # TapiodClient (sync) + AsyncTapiodClient
│       └── models.py               # ChatCompletion · TapiodTrace · TraceStep
│
├── scripts/                        # Setup, start, and dev utility scripts
│   ├── setup.sh / setup.bat        # One-command install + launch
│   └── start.sh / start.bat        # Start all services (post-setup)
│
├── docs/architecture.md            # Request-flow + cost diagrams
├── docker-compose.yml              # Qdrant + PostgreSQL + Redis
└── SETUP.md                        # Full local setup guide
```

---

## License

MIT
