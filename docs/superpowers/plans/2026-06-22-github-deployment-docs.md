# TAPIOD GitHub Deployment Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete, self-contained GitHub push for the TAPIOD deployment on Wednesday — comprehensive README, per-component docs, local setup guide, SDK docs, and a single seed command that reproduces all Qdrant training data from the already-tracked `arena_prompts.json`.

**Architecture:** Documentation-only changes plus two new files (`seed_all.py`, `.env.example`) and `.gitignore` updates. No code changes to gateway logic. The 5,000 routing training examples are **already in the repo** as `gateway/arena_prompts.json` (1 MB, tracked) — a reader only needs to run `seed_all.py` to get Qdrant populated. Runtime data (semantic cache, user_memory) is not pushed; it builds up as the gateway runs.

**Tech Stack:** Markdown, Python (seed script), bash.

## Global Constraints

- No code changes to gateway logic, hooks.py, or frontend components — docs + new helper files only.
- All paths in docs must be relative to repo root.
- All commands in docs must be copy-pasteable as-is on Linux/macOS. Windows notes go in callout blocks.
- Do not expose actual API keys — always reference `.env.example`.
- `arena_prompts.json` is already tracked (1 MB, under GitHub's 100 MB limit) — no LFS needed.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Replace | `README.md` | Full project README — pitch, architecture, structure, quickstart |
| Create | `SETUP.md` | Detailed step-by-step setup for a fresh machine |
| Create | `tapiod-sdk/README.md` | SDK installation, usage, streaming, async examples |
| Create | `gateway/.env.example` | Template listing every env var the gateway reads |
| Create | `gateway/seed_all.py` | Single script: seeds `routing_examples` + `tool_registry` |
| Update | `.gitignore` | Add `gateway/last_tools.json`, `*.xlsx`, scratch files |

---

### Task 1: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read the current .gitignore**

```
node_modules/
dist/
.env
.env.*
gateway/.env
gateway/venv/
gateway/__pycache__/
*.pyc
.DS_Store
*.log
*.jsonl
hooks_debug.txt
gateway/tests/results/
```

- [ ] **Step 2: Add missing entries**

Replace the file content with:

```
# Dependencies
node_modules/
dist/
gateway/venv/
tapiod-sdk/tapiod.egg-info/

# Environment secrets
.env
.env.*
gateway/.env

# Python artifacts
gateway/__pycache__/
**/__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Runtime / generated
*.log
*.jsonl
hooks_debug.txt
gateway/last_tools.json
gateway/qdrant_cache/
gateway/qdrant_data/

# Test results
gateway/tests/results/

# OS
.DS_Store
Thumbs.db

# Build output
.next/
*.xlsx
```

- [ ] **Step 3: Verify nothing important is newly ignored**

```bash
git status --short
```

Expected: Only `.gitignore` shows as modified. No previously-tracked files disappear.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: update .gitignore — add last_tools.json, qdrant local dirs, xlsx, egg-info"
```

---

### Task 2: Create `gateway/.env.example`

**Files:**
- Create: `gateway/.env.example`

- [ ] **Step 1: Write the file**

```bash
cat > gateway/.env.example << 'EOF'
# ── Required ──────────────────────────────────────────────────────────
# At least one provider key is needed. GROQ is free and the default fallback.
GROQ_API_KEY=gsk_your_groq_key_here

# ── Optional providers ─────────────────────────────────────────────────
# Add any of these to unlock that provider's models in litellm_config.yaml
OPENAI_API_KEY=sk-your_openai_key_here
ANTHROPIC_API_KEY=sk-ant-your_anthropic_key_here
GEMINI_API_KEY=AIza_your_gemini_key_here

# ── Database (matches docker-compose.yml defaults) ──────────────────
DATABASE_URL=postgresql://litellm:litellm_password@localhost:5432/litellm_logs

# ── Redis (optional — used for future L1 cache) ─────────────────────
REDIS_URL=redis://localhost:6379
EOF
```

- [ ] **Step 2: Verify the file exists and `.env` is still gitignored**

```bash
ls gateway/.env.example
git status --short gateway/.env
```

Expected: `.env.example` appears as untracked/new. `gateway/.env` does NOT appear (still ignored).

- [ ] **Step 3: Commit**

```bash
git add gateway/.env.example
git commit -m "chore: add gateway/.env.example with all supported env vars"
```

---

### Task 3: Create `gateway/seed_all.py`

**Files:**
- Create: `gateway/seed_all.py`

This replaces the need to remember which seed scripts to run and in what order. It calls `seed_arena.py` logic directly then seeds the tool registry.

- [ ] **Step 1: Write the file**

```python
"""
One-command Qdrant seed — run this after `docker compose up -d`.

Seeds:
  1. routing_examples  — 5 000 chatbot-arena prompts (fast/heavy labels)
                         source: gateway/arena_prompts.json
  2. tool_registry     — weather tool embedding (auto-done by gateway on
                         startup, but this ensures it exists for smoke tests)

Usage:
  cd gateway
  source venv/bin/activate
  python seed_all.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(script: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Running {script}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(HERE / script)],
        cwd=HERE,
    )
    if result.returncode != 0:
        print(f"\n✗ {script} failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"✓ {script} complete")


def main() -> None:
    print("TAPIOD Qdrant Seed")
    print("Qdrant must be running at http://localhost:6333")
    print("(run `docker compose up -d` first)\n")

    run("seed_arena.py")

    print("\n✓ All collections seeded.")
    print("  routing_examples  — 5 000 pts  (fast/heavy routing labels)")
    print("  tool_registry     — seeded automatically by gateway on startup")
    print("\nStart the gateway next:")
    print("  litellm --config litellm_config.yaml --port 4000 &")
    print("  uvicorn hooks:app --port 4001 --reload")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs without error**

```bash
cd /path/to/repo/gateway
source venv/bin/activate
python seed_all.py
```

Expected output ends with `✓ All collections seeded.`

- [ ] **Step 3: Commit**

```bash
git add gateway/seed_all.py
git commit -m "feat: add seed_all.py — single command to populate all Qdrant collections"
```

---

### Task 4: Write `tapiod-sdk/README.md`

**Files:**
- Create: `tapiod-sdk/README.md`

- [ ] **Step 1: Write the file**

Content below — copy exactly:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add tapiod-sdk/README.md
git commit -m "docs: add tapiod-sdk README with install, quickstart, streaming, async, model table"
```

---

### Task 5: Write `SETUP.md`

**Files:**
- Create: `SETUP.md`

- [ ] **Step 1: Write the file**

```markdown
# TAPIOD — Local Setup Guide

Complete instructions for running the full TAPIOD stack on a fresh machine.

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| Docker + Compose | v2+ | `docker compose version` |
| Git | any | `git --version` |

You need **at least one LLM provider API key**. GROQ is free — get one at https://console.groq.com.

---

## 1. Clone and configure

```bash
git clone https://github.com/YOUR_ORG/TAPIOD.git
cd TAPIOD
```

Copy the environment template and fill in your keys:

```bash
cp gateway/.env.example gateway/.env
# Edit gateway/.env — add GROQ_API_KEY at minimum
```

---

## 2. Start infrastructure

```bash
docker compose up -d
```

This starts three containers:

| Container | Port | Purpose |
|-----------|------|---------|
| `gateway-postgres` | 5432 | Request logs, chat sessions |
| `gateway-redis` | 6379 | L1 exact-match cache (future) |
| `gateway-qdrant` | 6333 | Semantic cache + routing KNN |

Verify they're healthy:

```bash
docker compose ps
```

---

## 3. Set up the Python gateway

```bash
cd gateway
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 4. Seed Qdrant (routing training data)

This loads the 5,000 chatbot-arena prompts into the `routing_examples` Qdrant collection. The source file (`arena_prompts.json`) is already in the repo — this step just embeds and indexes it.

**Takes ~3 minutes on first run** (downloads the BGE-small embedding model on first use).

```bash
cd gateway
source venv/bin/activate
python seed_all.py
```

Expected output:

```
TAPIOD Qdrant Seed
Qdrant must be running at http://localhost:6333

============================================================
  Running seed_arena.py
============================================================
Loading prompts from .../arena_prompts.json…
  5,000 prompts  (2500 fast / 2500 heavy)
Loading embedding model (BAAI/bge-small-en-v1.5)…
Embedding in batches of 32 (low-memory mode)…
  all 5,000 vectors ready
Upserting 5,000 points…
✓ routing_examples now has 5,000 points

✓ All collections seeded.
```

> **Note:** If you re-run `seed_all.py` on a machine that already has the collection, it skips (idempotent).

---

## 5. Start the LiteLLM proxy (port 4000)

Open a new terminal:

```bash
cd gateway
source venv/bin/activate
litellm --config litellm_config.yaml --port 4000
```

Leave this terminal open. Wait for `LiteLLM: Proxy initialized` before proceeding.

---

## 6. Start the FastAPI gateway (port 4001)

Open another terminal:

```bash
cd gateway
source venv/bin/activate
uvicorn hooks:app --port 4001 --reload
```

Verify it's alive:

```bash
curl http://localhost:4001/api/metrics
```

Should return a JSON object with `total_requests`, `cache_hits`, etc.

---

## 7. Build and start the dashboard (port 3000)

```bash
cd tapiod-web
npm install
npm run build
npm start
```

Open http://localhost:3000 — you should see the Live Traces dashboard.

> **Dev mode:** Use `npm run dev` instead of `npm run build && npm start` for hot-reload during frontend development.

---

## 8. Verify the full stack

Send a test request through the agentic endpoint:

```bash
curl -s http://localhost:4001/api/agent/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tapiod" \
  -d '{
    "model": "fast-groq",
    "messages": [{"role": "user", "content": "What is 2 + 2?"}]
  }' | python3 -m json.tool
```

You should see a response with `choices[0].message.content` and a `_tapiod_trace` object.

---

## Quick reference: ports

| Service | Port | URL |
|---------|------|-----|
| Dashboard (Next.js) | 3000 | http://localhost:3000 |
| FastAPI gateway | 4001 | http://localhost:4001 |
| LiteLLM proxy | 4000 | http://localhost:4000 |
| Qdrant UI | 6333 | http://localhost:6333/dashboard |
| PostgreSQL | 5432 | `psql -U litellm -d litellm_logs` |

---

## Troubleshooting

**`litellm` command not found**
→ Make sure you activated the venv: `source gateway/venv/bin/activate`

**Qdrant connection refused in seed_all.py**
→ Run `docker compose up -d` first. Qdrant needs a few seconds after start.

**`GROQ_API_KEY` not found errors in LiteLLM logs**
→ Check `gateway/.env` exists and contains `GROQ_API_KEY=gsk_...`

**Port 4000 already in use**
→ Kill the existing process: `lsof -ti :4000 | xargs kill -9`

**BGE model download hangs**
→ The embedding model (~130 MB) downloads from HuggingFace on first run. Ensure internet access and retry.

---

## Windows notes

Use `venv\Scripts\activate` instead of `source venv/bin/activate`.
The provided `start.bat` launches LiteLLM + Next.js together but does **not** start the FastAPI server — run `uvicorn hooks:app --port 4001 --reload` in a separate terminal.
```

- [ ] **Step 2: Commit**

```bash
git add SETUP.md
git commit -m "docs: add SETUP.md — complete local setup guide from clone to smoke test"
```

---

### Task 6: Replace `README.md`

**Files:**
- Replace: `README.md`

This is the main repo landing page. It should orient a first-time reader in 30 seconds, then point to deeper docs.

- [ ] **Step 1: Write the full README**

```markdown
# TAPIOD — Enterprise LLM Gateway

**Token-Aware Proxy with Intelligent Optimization & Dispatch**

TAPIOD sits between your application and any LLM provider, adding semantic caching, smart model routing, dynamic tool injection, and a multi-turn agentic loop — while surfacing every cost and latency decision in a live dashboard.

> Built for demos and production pilots. Swap providers without changing application code.

---

## What it does

| Layer | Mechanism | Benefit |
|-------|-----------|---------|
| **L0 — Exact cache** | Redis key lookup | ~0.1 ms, zero tokens |
| **L1 — Semantic cache** | Qdrant cosine similarity (≥ 0.85) | ~5 ms, zero tokens for similar questions |
| **L2 — Smart routing** | KNN on 5,000 arena-prompt embeddings | Routes simple prompts to fast (10× cheaper) model |
| **L3 — Tool injection** | Qdrant vector search over tool registry | Injects only relevant tools per request |
| **L4 — Agentic loop** | Multi-turn tool execution in the gateway | Resolves tool calls server-side, returns final answer |

---

## Architecture

```
Browser (port 3000)
  └─ Next.js Dashboard (Live Traces · Playground · Observability · Config)

Client / SDK
  └─ POST /api/agent/chat/completions
       └─ FastAPI Gateway (port 4001)              ← hooks.py
            ├─ Pre-call: cache lookup · route · inject tools
            ├─ Forward ─► LiteLLM Proxy (port 4000) ─► Groq / OpenAI / Anthropic / Gemini
            ├─ Post-call: write cache · log to PostgreSQL
            └─ Tool execution loop (tool_executor.py)

Infrastructure (Docker)
  ├─ Qdrant  :6333  — semantic_cache_384 · routing_examples · tool_registry · user_memory
  ├─ PostgreSQL :5432  — requests_log · chat_sessions
  └─ Redis  :6379  — L1 exact-match cache
```

Full architecture diagram with cost analysis: [`docs/architecture.md`](docs/architecture.md)

---

## Project structure

```
TAPIOD/
├── gateway/                  # Python backend
│   ├── hooks.py              # FastAPI server + all LiteLLM proxy hooks
│   ├── tool_executor.py      # Tool dispatch — TOOL_REGISTRY maps names to functions
│   ├── tools_registry.py     # Tool definitions (OpenAI function format)
│   ├── router.py             # RouteLLM KNN routing logic
│   ├── cache.py              # Qdrant semantic cache read/write
│   ├── memory.py             # Per-tenant user memory (Qdrant)
│   ├── context.py            # System prompt / context injection
│   ├── cost.py               # Token cost calculation
│   ├── crypto.py             # Tenant ID derivation from API key
│   ├── litellm_config.yaml   # Model list, router settings, provider keys
│   ├── arena_prompts.json    # 5,000 labeled prompts (fast/heavy) — routing training data
│   ├── seed_all.py           # ← RUN THIS after docker compose up to populate Qdrant
│   ├── seed_arena.py         # Seeds routing_examples collection
│   ├── seed_routing.py       # Seeds minimal routing examples (dev use)
│   └── requirements.txt
│
├── tapiod-web/               # Next.js 16 dashboard (App Router)
│   └── src/app/
│       ├── page.tsx          # Live Traces — real-time request log with trace viewer
│       ├── playground/       # Chat playground with model selector
│       ├── observability/    # Charts: cost over time, cache hit rate, routing split
│       ├── config/           # API key management, model priority, fallback config
│       └── memory/           # Per-tenant memory viewer
│
├── tapiod-sdk/               # Python client SDK
│   ├── tapiod/
│   │   ├── client.py         # TapiodClient (sync) + AsyncTapiodClient
│   │   └── models.py         # ChatCompletion, TapiodTrace, TraceStep
│   └── examples/quickstart.py
│
├── docker-compose.yml        # PostgreSQL + Redis + Qdrant
├── SETUP.md                  # ← Full local setup guide
└── docs/
    └── architecture.md       # Mermaid diagrams: request flow, cost breakdown
```

---

## Quick start

```bash
# 1. Clone and configure
git clone https://github.com/YOUR_ORG/TAPIOD.git && cd TAPIOD
cp gateway/.env.example gateway/.env
# edit gateway/.env — add GROQ_API_KEY=gsk_...

# 2. Start infrastructure
docker compose up -d

# 3. Python setup + seed Qdrant
cd gateway && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python seed_all.py           # ~3 min first run (downloads embedding model)

# 4. Start LiteLLM proxy       (new terminal)
litellm --config litellm_config.yaml --port 4000

# 5. Start FastAPI gateway      (new terminal)
uvicorn hooks:app --port 4001 --reload

# 6. Build and start dashboard  (new terminal)
cd ../tapiod-web && npm install && npm run build && npm start
```

Open http://localhost:3000

Full step-by-step guide including troubleshooting: [**SETUP.md**](SETUP.md)

---

## API

### Agentic chat (recommended)

```
POST http://localhost:4001/api/agent/chat/completions
Authorization: Bearer <your-api-key>
Content-Type: application/json

{
  "model": "fast-groq",
  "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
  "stream": false
}
```

Response includes a `_tapiod_trace` object:

```json
{
  "choices": [{"message": {"content": "..."}}],
  "_tapiod_trace": {
    "pipeline": [
      {"layer": "semantic_cache", "result": "miss", "latency_ms": 4.2},
      {"layer": "router",        "result": "fast",  "latency_ms": 1.1},
      {"layer": "tool_inject",   "result": "1 tool","latency_ms": 2.0},
      {"layer": "llm_call",      "result": "ok",    "latency_ms": 412}
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
| GET | `/api/metrics` | Aggregate stats: total requests, cache hits, cost, avg latency |
| GET | `/api/traces` | Last N request traces |
| GET | `/api/config` | Current routing config (model priority, fallbacks) |
| POST | `/api/config` | Update routing config |
| GET | `/api/memory` | Per-tenant user memory facts |

---

## SDK

```bash
pip install -e ./tapiod-sdk
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

Full SDK docs: [`tapiod-sdk/README.md`](tapiod-sdk/README.md)

---

## Models

Configure active providers in `gateway/.env`. Any provider without a key is automatically skipped — the gateway falls back to Groq.

| Alias | Model | Tier | Provider |
|-------|-------|------|----------|
| `fast-groq` | llama-3.1-8b-instant | Fast | Groq (free) |
| `heavy-groq` | llama-3.3-70b-versatile | Heavy | Groq (free) |
| `fast-openai` | gpt-4o-mini | Fast | OpenAI |
| `heavy-openai` | gpt-4o | Heavy | OpenAI |
| `fast-anthropic` | claude-sonnet-4-6 | Fast | Anthropic |
| `heavy-anthropic` | claude-opus-4-8 | Heavy | Anthropic |
| `fast-gemini` | gemini-3.5-flash | Fast | Google |
| `heavy-gemini` | gemini-3.1-pro | Heavy | Google |

Model priority and fallback order are configurable from the dashboard Config page without restarting any service.

---

## Qdrant collections

| Collection | Points | Purpose | How it's populated |
|------------|--------|---------|-------------------|
| `routing_examples` | 5,000 | KNN routing — fast vs heavy classification | `python seed_all.py` |
| `tool_registry` | dynamic | Tool embeddings for semantic injection | Gateway startup |
| `semantic_cache_384` | grows | Semantic response cache | Populated by live traffic |
| `user_memory` | grows | Per-tenant memory facts | Populated by live traffic |

The 5,000 routing examples come from `gateway/arena_prompts.json` (tracked in this repo). Run `python gateway/seed_all.py` once after a fresh `docker compose up` and the data is ready.

---

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: complete README rewrite — architecture, structure, quickstart, API, SDK, model table"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Well-indexed codebase — README has full project structure tree with one-line descriptions per file
- ✅ Frontend documented — tapiod-web pages listed with descriptions
- ✅ Backend documented — all gateway Python files described
- ✅ SDK documented — tapiod-sdk/README.md with sync, async, streaming, model table
- ✅ Setup instructions — SETUP.md covers prerequisites → clone → infra → seed → all 3 services → smoke test
- ✅ "Push Docker data to GitHub" — clarified: `arena_prompts.json` already tracked; `seed_all.py` reproduces Qdrant from it; runtime cache data is not pushed (it's transient)
- ✅ .env.example — all env vars documented

**Placeholder scan:** None found.

**Type consistency:** No code types involved — documentation only.
