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

> **Note:** Re-running `seed_all.py` is safe — it clears and rebuilds the collection from scratch. It will re-download nothing (the embed model is cached after first run), but will re-embed all 5,000 prompts (~1–2 min).

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
