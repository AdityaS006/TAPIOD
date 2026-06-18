# TAPIOD v2 Design Spec
**Date:** 2026-06-11  
**Status:** Approved for implementation  
**Audience:** Investor demo (B2B pitch)  
**Goal:** Working prototype that demonstrates three live wow moments: cost savings, persistent memory, and multi-provider arbitrage

---

## 1. Problem & Motivation

LLM API costs are high and unpredictable. Every request pays full price regardless of whether an identical or semantically similar question was asked a minute ago, whether a cheaper model could have answered it, or whether the user already explained their context three conversations ago.

TAPIOD sits between any client application and any LLM provider as a drop-in plugin — change one line (`base_url`) and every call flows through TAPIOD's intelligence layer. The client pays for fewer tokens, gets smarter responses over time, and the operator gets full observability into where every dollar goes.

---

## 2. Architecture

### 2.1 Process Layout

Two processes, unchanged from v1:

```
Client (any app, any language)
  │  base_url = "http://tapiod-host:4000/v1"
  ▼
LiteLLM Proxy  :4000   ← OpenAI-compatible, multi-provider, retries/fallbacks
  │  GatewayHooks fires on every call
  ▼
FastAPI        :4001   ← agentic loop, memory API, metrics, config
```

LiteLLM is kept intentionally. It is what makes TAPIOD a drop-in plugin for any existing LLM application. Removing it would break the enterprise story.

### 2.2 Infrastructure (docker-compose, unchanged)

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL | 5432 | `requests_log`, `chat_sessions` |
| Redis | 6379 | L1 exact-match cache (activated in v2) |
| Qdrant | 6333 | Four collections (see §2.3) |

### 2.3 Qdrant Collections

| Collection | Dimensions | Purpose |
|---|---|---|
| `semantic_cache_384` | 384 | L2 semantic response cache |
| `tool_registry` | 384 | Dynamic tool selection |
| `user_memory` | 384 | Persistent user facts across sessions |
| `routing_examples` | 384 | KNN complexity classifier training data |

All four collections are queried using the same `ctx.vec` — the prompt is embedded exactly once per request.

---

## 3. Core Pipeline

### 3.1 RequestContext

A dataclass created at the top of `async_pre_call_hook` and passed through every layer:

```python
@dataclass
class RequestContext:
    prompt: str
    messages: list
    tenant_id: str
    user_id: str
    vec: list[float]            # embedded ONCE from prompt

    # cache
    cache_hit: bool = False
    cache_source: str = ""      # "redis" | "qdrant"
    cache_saved_usd: float = 0.0

    # memory
    injected_memories: list = field(default_factory=list)
    memory_tokens_saved: int = 0

    # routing
    complexity_score: float = 0.0
    provider_model: str = ""
    routing_saved_usd: float = 0.0

    # tools
    injected_tools: list = field(default_factory=list)

    # cost
    actual_cost_usd: float = 0.0
    total_saved_usd: float = 0.0

    # trace
    pipeline_trace: list = field(default_factory=list)
```

`pipeline_trace` accumulates a record of each layer's result, latency, and outcome. It is stored as JSONB in `requests_log` and powers the live trace panel on the dashboard.

### 3.2 Pre-Call Hook — Layer Sequence

```
async_pre_call_hook(data):

  1. Parse messages, extract tenant_id (SHA256 of API key),
     user_id from data.get("user_id") or fallback to tenant_id
  2. embed(prompt) → ctx.vec                          [once, ~3ms]

  3. Redis GET sha256(tenant+model+messages)           [~0.1ms]
     └─ HIT  → return cached, record trace, done

  4. Qdrant query semantic_cache_384 (ctx.vec)         [~5ms]
     score > 0.85 AND tenant_id matches
     └─ HIT  → return cached, backfill Redis, done

  5. Qdrant query user_memory (ctx.vec, top=3)         [~5ms]
     score > 0.7, filtered by user_id
     └─ prepend recalled facts to system prompt

  6. Qdrant query routing_examples (ctx.vec, top=5)   [~2ms]
     majority vote → "fast" | "heavy"
     → pick cheapest available provider in that tier
     → record routing_saved_usd = (most_expensive_tier - chosen)

  7. Qdrant query tool_registry (ctx.vec, top=3)       [~2ms]
     score > 0.65
     └─ inject matching tools into data["tools"]

  return data  →  LiteLLM fires LLM call
```

Total overhead on cache miss: ~17ms across all layers.  
Total overhead on cache hit (Redis): ~0.2ms.

### 3.3 Post-Call Hook — Async Writes

All writes are fire-and-forget via `asyncio.create_task`. The client receives the response immediately; writes happen after:

```
async_post_call_success_hook(data, response):

  actual_cost = kwargs["response_cost"]          ← LiteLLM pricing DB
  ctx.total_saved_usd = cache_saved + routing_saved + memory_saved_est

  asyncio.create_task(write_redis(key, response, ttl=3600))
  asyncio.create_task(write_qdrant_cache(ctx.vec, response))
  asyncio.create_task(extract_and_store_memory(response, ctx))
  asyncio.create_task(log_to_postgres(ctx))

  return response
```

### 3.4 Memory Extraction

After each response, a single cheap fast-model call extracts durable facts:

```
System: Extract 0-3 concise facts about the user from this conversation turn.
        Return JSON: {"facts": ["..."]}
        Only extract stable, reusable facts. Skip one-off questions.
        If nothing durable, return {"facts": []}.
```

Cost: ~150 input + ~50 output tokens on `llama-3.1-8b-instant` ≈ $0.00001 per extraction.  
Each extracted fact is embedded (reusing the model already loaded) and upserted into `user_memory`.

---

## 4. Cost Tracking

### 4.1 Actual Cost

Use `kwargs["response_cost"]` from LiteLLM's logger hook. LiteLLM maintains a live pricing database across all providers. This replaces the fake `tokens * 0.001` formula in v1.

### 4.2 Saved Cost

Each layer that short-circuits an LLM call records what it saved:

**Cache save** — estimated using LiteLLM's `cost_per_token()` on the prompt length and default heavy model, since that's what would have been called without TAPIOD:
```python
from litellm import cost_per_token
estimated = cost_per_token("groq/llama-3.3-70b-versatile",
                           prompt_tokens=len(prompt.split()) * 1.3,  # rough but honest estimate
                           completion_tokens=150)                     # avg completion assumption
ctx.cache_saved_usd = estimated
```
This is an estimate, not exact — the dashboard labels it "est. saved" to be transparent. It uses the heaviest configured model as the baseline (worst-case cost without TAPIOD), which gives the most defensible savings figure.

**Routing save** — difference between the cheapest heavy-tier model and the chosen fast-tier model, multiplied by actual token usage:
```python
ctx.routing_saved_usd = heavy_cost_per_token - fast_cost_per_token  # × tokens
```

**Memory save** — tokens not sent because recalled facts replaced re-explanation:
```python
ctx.memory_tokens_saved = sum(len(f.split()) * 1.3 for f in ctx.injected_memories)
```

### 4.3 PostgreSQL Schema Addition

```sql
ALTER TABLE requests_log ADD COLUMNS IF NOT EXISTS:
  provider             VARCHAR(50),
  prompt_tokens        INT,
  completion_tokens    INT,
  actual_cost_usd      FLOAT,
  cache_source         VARCHAR(20),
  cache_saved_usd      FLOAT,
  routing_saved_usd    FLOAT,
  memory_tokens_saved  INT,
  total_saved_usd      FLOAT,
  pipeline_trace       JSONB
```

---

## 5. Multi-Provider Router

### 5.1 KNN Complexity Classifier

New Qdrant collection `routing_examples` — bootstrapped from LMSYS Chatbot Arena dataset (~500 labeled prompts), grows from live traffic feedback.

Classification at runtime:
```python
results = qdrant.query_points("routing_examples", query=ctx.vec, limit=5)
votes = [r.payload["label"] for r in results.points]  # "fast" | "heavy"
tier = "heavy" if votes.count("heavy") > votes.count("fast") else "fast"
ctx.complexity_score = votes.count("heavy") / len(votes)
```

No local ML model. No hardcoded keywords. Semantically trained on real data. Self-improves as labeled examples are added at runtime.

**Feedback loop:** When the fast model fails and escalates to heavy, that prompt is automatically added to `routing_examples` as a `"heavy"` example.

### 5.2 Provider Tiers

Defined in `litellm_config.yaml`. Within each tier, models are ranked by cost. The router picks the first (cheapest) available provider in the correct tier:

```
FAST TIER (score < 0.5):
  1. fast-groq      groq/llama-3.1-8b-instant     $0.06/M blended
  2. fast-openai    openai/gpt-4o-mini             $0.30/M blended

HEAVY TIER (score ≥ 0.5):
  1. heavy-groq      groq/llama-3.3-70b-versatile  $0.69/M blended
  2. heavy-anthropic anthropic/claude-3-5-sonnet   $3.00/M blended
  3. heavy-openai    openai/gpt-4o                 $6.25/M blended
```

If the top provider is unavailable or rate-limited, LiteLLM's existing fallback mechanism tries the next in the list automatically.

### 5.3 Operator Controls

KNN threshold and tier ordering are configurable at runtime via `/api/config/thresholds` and `/api/config/tiers`. Changes take effect on the next request — no restart needed.

---

## 6. Memory Layer

### 6.1 Storage

Qdrant collection `user_memory` (384 dimensions):
```json
{
  "vector": [...],
  "payload": {
    "user_id": "u_abc123",
    "tenant_id": "sha256...",
    "fact": "User is building an LLM gateway called TAPIOD",
    "timestamp": 1718123456
  }
}
```

### 6.2 Retrieval

Top-3 facts with score > 0.7, filtered by `user_id`. Prepended to system prompt as a `[Recalled context]` block. Recall runs on every non-cached request using the already-computed `ctx.vec`.

### 6.3 Extraction

Async after each response. One fast-model call, ~$0.00001. Facts embedded and upserted into `user_memory`.

### 6.4 Management API (FastAPI :4001)

```
GET    /api/memory?user_id=X&tenant_id=Y   list stored memories
DELETE /api/memory/{id}                     forget one fact
DELETE /api/memory?user_id=X               full wipe (GDPR)
```

---

## 7. Frontend — Five Pages

### 7.1 `/` — Cost Savings Command Center

**Wow moment:** Total $$$ saved vs. direct API, live and updating.

Panels:
- Four KPI cards: Total Saved, Actual Cost, Cache Rate, Request Count
- Live trace feed: last 20 requests, each showing pipeline layers fired, provider chosen, actual cost, saved cost
- Identical request demo: same prompt twice → first shows cost, second shows $0.00 Redis hit

New API: `GET /api/traces` — last 20 requests with `pipeline_trace` JSONB.

### 7.2 `/playground` — Live Pipeline Visualizer

**Wow moment:** Watch your prompt move through each layer in real time. See memories recalled. See cost.

Layout: chat panel left, pipeline visualization right.

Pipeline panel shows each layer as it fires: Redis (hit/miss + ms), Qdrant cache (hit/miss + score + ms), Memory recall (facts shown), KNN router (score + tier + provider chosen), Tool selector (tools injected), LLM call (provider + ms), async writes.

Below pipeline: cost breakdown for this request + memories stored this turn.

### 7.3 `/observability` — Provider Arbitrage

**Wow moment:** "If everything had gone to GPT-4o, you'd have paid $0.34. Actual: $0.09."

Panels:
- Routing distribution bar chart (provider + % share)
- Cost comparison: worst case vs. actual, with savings callout
- KNN accuracy: labeled examples count, accuracy on last 100 live requests
- Memory stats: facts stored, recalls today, tokens saved estimate

### 7.4 `/memory` — User Memory Browser

List of stored facts per user with timestamps. Delete individual facts or wipe all (GDPR). Shows which facts were recalled in the most recent request.

### 7.5 `/config` — Control Panel

**Section: API Providers**
- List active providers with masked key, status indicator
- Edit key, delete provider
- Add provider (name + API key)

**Section: Model Routing Tiers**
- Fast tier: ordered list of models (drag to reorder = change fallback priority)
- Heavy tier: same
- Add model to either tier (alias, provider model string, $/M cost)
- KNN threshold slider (0.0–1.0, default 0.5)

**Section: Cache Settings**
- Semantic similarity threshold slider (0.0–1.0, default 0.85)
- Redis TTL slider (60s–86400s, default 3600s)

**Section: Guardrails** *(Coming Soon — grayed out)*
- Block harmful content toggle
- Max tokens per request input
- Rate limit per tenant input

**Section: PII Masking (Presidio)** *(Coming Soon — grayed out)*
- Mask emails, phone numbers, credit card numbers toggles
- Restore PII in response toggle
- "Powered by Microsoft Presidio" attribution

---

## 8. New File Layout

```
gateway/
  hooks.py              ← GatewayHooks rewrite (single embedding, all layers)
  context.py            ← RequestContext dataclass
  cache.py              ← Redis L1 + Qdrant L2 logic
  memory.py             ← user_memory retrieval, extraction, write
  router.py             ← KNN classifier, provider tier selection
  tools.py              ← tool selection + agentic loop helpers
  cost.py               ← savings calculation helpers
  logger.py             ← async PostgreSQL write
  tool_executor.py      ← unchanged
  tools_registry.py     ← unchanged (add more real tools later)
  litellm_config.yaml   ← add OpenAI + Anthropic provider entries
  seed_routing.py       ← one-time script: load LMSYS data → routing_examples

tapiod-web/src/app/
  page.tsx              ← rewrite: Cost Savings Command Center
  playground/page.tsx   ← rewrite: Pipeline Visualizer
  observability/page.tsx ← rewrite: Provider Arbitrage
  memory/page.tsx        ← new: Memory Browser
  config/page.tsx        ← rewrite: Control Panel
```

---

## 9. Fixes Carried Forward from v1

These bugs exist in current code and must be resolved during the rewrite:

| Bug | Fix |
|---|---|
| Prompt embedded 3× per request | `RequestContext` embeds once, passes `ctx.vec` everywhere |
| Redis running but unused | L1 cache activated in `cache.py` |
| Windows hardcoded paths (`c:\Coding\TAPIOD\...`) | Use `pathlib.Path(__file__).parent` throughout |
| Fake cost formula `tokens * 0.001` | Replace with `kwargs["response_cost"]` from LiteLLM |
| RouteLLM fails to load silently | Replaced by KNN on Qdrant — no separate ML process |
| `datetime.now()` called without import | Fix import: `from datetime import datetime, timedelta` |

---

## 10. Out of Scope (Future)

- Guardrails (content filtering, rate limiting per tenant)
- Presidio PII masking/restoration
- KNN classifier trained on proprietary data (v2 uses LMSYS bootstrap only)
- Streaming responses
- Multi-region deployment
- Billing / usage metering per tenant

---

## 11. Demo Flow (Investor Pitch — 5 Minutes)

1. **Open `/`** — show `$X saved, Y% reduction` live counter. "This is what TAPIOD saved just today."
2. **Go to `/playground`** — send: *"I'm building an LLM gateway in Python called TAPIOD."* Watch pipeline: cache miss → memory extracted → fast-groq routed → $0.000089.
3. **Send same prompt again** — Redis hit, $0.00, <1ms. "Second time anyone asks this, it's free."
4. **New session, ask:** *"What am I building?"* — TAPIOD recalls from memory, answers without re-explanation. Show memory panel.
5. **Go to `/observability`** — show routing distribution. "That question scored 0.18 complexity — went to our cheapest model. A code review scores 0.82 — goes heavy. The KNN learned this from 500 real labeled prompts."
6. **Go to `/config`** — show Guardrails and PII masking sections. "These are coming. The architecture is already there."
