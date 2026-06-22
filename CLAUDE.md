# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is TAPIOD?

TAPIOD is an enterprise LLM gateway demo/platform. It sits between clients and LLM providers (Groq), adding:
- **Semantic caching** via Qdrant (vector similarity, not exact match)
- **Smart routing** via RouteLLM (routes prompts to `fast-model` or `heavy-model` based on complexity)
- **Dynamic tool injection** — tools are selected per-request from a Qdrant vector registry based on prompt intent
- **Multi-turn agentic loop** — the gateway intercepts tool calls and executes them before a follow-up LLM call
- **Observability dashboard** — Next.js frontend showing live traces, metrics, and request logs

## Architecture

```
Client → FastAPI (port 4001)
           ├── /api/agent/chat/completions  → Agentic loop (tool execution)
           └── /api/*                       → Metrics, config, chat sessions

FastAPI hooks.py → LiteLLM Proxy (port 4000)
                       ├── GatewayHooks.async_pre_call_hook
                       │     ├── Qdrant semantic cache lookup
                       │     ├── RouteLLM model selection
                       │     └── Dynamic tool injection from Qdrant
                       └── GatewayHooks.async_post_call_success_hook
                             └── Write to Qdrant cache, log to PostgreSQL
```

**Key files:**
- `gateway/hooks.py` — All LiteLLM proxy hooks + FastAPI server (port 4001). Contains `GatewayHooks` class that handles caching, routing, tool injection, and metrics.
- `gateway/tool_executor.py` — `execute_tool()` dispatches tool calls by name; `TOOL_REGISTRY` maps names to Python functions.
- `gateway/tools_registry.py` — `MOCK_TOOLS` list (OpenAI function format) that gets embedded into Qdrant at startup.
- `gateway/litellm_config.yaml` — LiteLLM proxy model list and router settings. `hooks.proxy_hooks` is registered as a callback here.
- `tapiod-web/` — Next.js 16 (App Router) dashboard with pages: Live Traces (`/`), Playground (`/playground`), Observability (`/observability`), Config (`/config`).

**Infrastructure (docker-compose.yml):**
- PostgreSQL on 5432 — stores `requests_log` and `chat_sessions` tables
- Redis on 6379 — available but not heavily used yet
- Qdrant on 6333/6334 — two collections: `semantic_cache_384` (response cache) and `tool_registry` (tool embeddings)

## Running the Stack

**Start infrastructure:**
```bash
docker compose up -d
```

**Start LiteLLM proxy (port 4000):**
```bash
cd gateway
source venv/bin/activate   # or venv\Scripts\activate on Windows
litellm --config litellm_config.yaml --port 4000
```

**Start FastAPI hooks server (port 4001):**
```bash
cd gateway
source venv/bin/activate
uvicorn hooks:app --port 4001 --reload
```

**Start Next.js frontend:**
```bash
cd tapiod-web
npm run dev   # runs on port 3000
```

On Windows, `start.bat` launches the LiteLLM proxy and Next.js together (but not the FastAPI server separately).

## Environment Setup

Create `gateway/.env` with:
```
GROQ_API_KEY=your_key_here
```

LiteLLM reads this via `os.environ/GROQ_API_KEY` references in `litellm_config.yaml`.

## Frontend Commands

```bash
cd tapiod-web
npm run dev      # development server
npm run build    # production build
npm run lint     # ESLint
```

## Important Implementation Notes

- **Port hardcoding**: The frontend fetches from `http://localhost:4001` (FastAPI) and LiteLLM runs on `4000`. These are hardcoded in the `.tsx` files.
- **Windows path bug**: `hooks.py` has hardcoded Windows paths (`c:\Coding\TAPIOD\gateway\last_tools.json`) for IPC file writes — these will fail on Linux/Mac and need updating.
- **Qdrant initialization**: On FastAPI startup, Qdrant initializes in a background thread. The `tool_registry` collection is only created on first run (when it doesn't exist); `semantic_cache_384` is created if missing.
- **Embedding model**: Uses `BAAI/bge-small-en-v1.5` via FastEmbed (384 dimensions). Downloaded on first run.
- **RouteLLM**: Initialized in a background thread; has a complexity-score fallback if it fails to load.
- **Tenant isolation**: Derived from a SHA-256 hash of the API key. Default: `"default_tenant"`.
- **Semantic cache threshold**: Score > 0.85 cosine similarity triggers a cache hit.
- **Tool injection threshold**: Score > 0.65 cosine similarity, top 3 tools injected.

## Next.js Notes

Per `tapiod-web/AGENTS.md`: This project uses Next.js 16 (App Router) with breaking API changes. Read `node_modules/next/dist/docs/` before writing Next.js code — APIs and conventions may differ from training data.

All dashboard pages are `"use client"` components. Styling uses Tailwind CSS v4 + CSS custom properties defined in `globals.css` (e.g., `var(--accent-purple-light)`, `var(--text-muted)`). Framer Motion and Recharts are available for animations and charts.
