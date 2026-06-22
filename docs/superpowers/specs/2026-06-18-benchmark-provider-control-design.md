# TAPIOD: Claude Model Support, Baseline Cost Fix & Provider Control Panel

**Date:** 2026-06-18  
**Status:** Approved  

---

## Overview

Four tightly related changes that together make TAPIOD production-ready for multi-provider demos and accurate cost reporting:

1. Add Claude Opus 4.8 (heavy tier) and Claude Sonnet 4.6 (fast tier) to TAPIOD
2. Fix the savings baseline math — baseline is always the costliest available model, not a hardcoded `gpt-4o-mini`
3. New benchmark script that runs coding-workspace prompts through TAPIOD and raw Claude Opus 4.8 side-by-side, outputs terminal table + CSV
4. Frontend Provider & Routing Control Panel — manage API keys and model priority lists from the dashboard

---

## Section 1 — Add Claude Models

### `gateway/litellm_config.yaml`

Add two new model entries:

```yaml
- model_name: fast-anthropic
  litellm_params:
    model: anthropic/claude-sonnet-4-6
    api_key: os.environ/ANTHROPIC_API_KEY

- model_name: heavy-anthropic   # replace existing entry
  litellm_params:
    model: anthropic/claude-opus-4-8-20250514
    api_key: os.environ/ANTHROPIC_API_KEY
```

Add fallback for `fast-anthropic`:
```yaml
fallbacks:
  - {"fast-anthropic": ["fast-groq"]}
```

### `gateway/router.py`

Update `PROVIDER_COST_RANK` with accurate pricing (USD per 1M output tokens, used for ordering):
```python
PROVIDER_COST_RANK = {
    "fast-groq":       0.06,
    "fast-openai":     0.60,
    "fast-anthropic":  3.00,
    "heavy-groq":      0.89,
    "heavy-openai":    10.00,
    "heavy-anthropic": 15.00,
}
```

Update `get_available_providers()` to include `fast-anthropic` when `ANTHROPIC_API_KEY` is set.

Update `MODEL_MAP` in `compute_routing_save` to map both new aliases to their litellm model strings.

---

## Section 2 — Fix Baseline Cost Math

### The problem

Both `compute_routing_save` in `router.py` and `estimate_cache_save` in `cost.py` hardcode `openai/gpt-4o-mini` as the savings baseline. This means the dashboard shows "savings vs GPT-4o-mini", which is meaningless when a user has Anthropic or OpenAI keys for more expensive models.

### The fix

**New function in `router.py`:**

```python
def get_costliest_available_model(available: list[str]) -> str:
    """Returns the litellm model string for the most expensive model in `available`."""
```

Uses `litellm.cost_per_token` to compare all available aliases and returns the most expensive one's full model string.

**`compute_routing_save`** — replace `baseline_model = "openai/gpt-4o-mini"` with:
```python
baseline_model = get_costliest_available_model(available)
```

**`estimate_cache_save` in `cost.py`** — add a `baseline_model: str` parameter. Update call site in `hooks.py` to pass `get_costliest_available_model(get_available_providers())`.

### Result

The dashboard's "total saved" and "baseline cost" now correctly answer: *"what would you have paid if you had sent every request to your most expensive available model?"*

---

## Section 3 — Benchmark Script

### File: `gateway/tests/benchmark_claude.py`

Sends 20 real coding-workspace prompts through both TAPIOD and raw Claude Opus 4.8, then outputs a comparison sheet.

### Prompt set (20 prompts across 6 categories)

**Explain errors (4):**
- "I'm getting `TypeError: 'NoneType' object is not subscriptable` in Python. What does it mean and how do I fix it?"
- "My React component throws `Cannot read properties of undefined (reading 'map')`. What's happening?"
- "What does `ECONNREFUSED 127.0.0.1:5432` mean and how do I debug it?"
- "Git says `Your branch has diverged`. How do I resolve this without losing my work?"

**Write functions (4):**
- "Write a Python function that implements binary search on a sorted list."
- "Write a JavaScript debounce function with TypeScript types."
- "Write a SQL query that finds the top 5 customers by total order value in the last 30 days."
- "Write a Python context manager that times a block of code and logs the result."

**Debug code (3):**
- "Here's a Python loop that should sum a list but gives the wrong answer: `total = 0; for i in range(1, len(nums)): total += nums[i]`. What's the bug?"
- "My async function returns a Promise instead of the resolved value. What am I doing wrong?"
- "Why does my Docker container exit immediately after starting? How do I debug it?"

**Refactor / code review (3):**
- "Review this function for improvements: `def get_user(id): return db.query('SELECT * FROM users WHERE id=' + str(id))`"
- "How would you refactor a 200-line Python function that does validation, DB writes, and email sending all in one?"
- "What's the difference between `useEffect(() => {}, [])` and `useEffect(() => {})` in React?"

**Git / DevOps (3):**
- "Explain `git rebase -i HEAD~3` and when I should use it."
- "Write a minimal Dockerfile for a Node.js 20 Express app."
- "Write a GitHub Actions workflow that runs pytest on every pull request."

**Documentation (3):**
- "Write a NumPy-style docstring for a function that calculates compound interest."
- "Explain what this regex does: `^(?=.*[A-Z])(?=.*\d)(?=.*[@$!])[A-Za-z\d@$!]{8,}$`"
- "Write a one-paragraph README section explaining what a vector database is to a non-technical reader."

### For each prompt

1. POST to TAPIOD (`http://localhost:4001/api/agent/chat/completions`)
2. Direct Anthropic SDK call to `claude-opus-4-8-20250514`
3. Record: model routed to, cache hit, prompt tokens, completion tokens, cost for each path

### Output columns

| # | Prompt (50 chars) | TAPIOD Model | Cache | P.Tokens | C.Tokens | TAPIOD Cost $ | Opus Direct $ | Saved $ | Saved % |

### Terminal output

Formatted table using `tabulate` or manual padding. Totals row at the bottom. Header line shows test timestamp and baseline model used.

### CSV output

Saved to `gateway/tests/results/benchmark_YYYY-MM-DD_HH-MM.csv`. Full rows, all columns. Directory created if missing. Timestamp in filename prevents overwrites.

---

## Section 4 — Provider & Routing Control Panel

### 4a — Backend: encrypted key storage

**New PostgreSQL table** (created at FastAPI startup alongside existing tables):
```sql
CREATE TABLE IF NOT EXISTS provider_keys (
    tenant_id   TEXT NOT NULL,
    provider    TEXT NOT NULL,
    enc_key     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (tenant_id, provider)
);
```

Encryption: `cryptography.fernet.Fernet` with `FERNET_SECRET` from `gateway/.env`. If `FERNET_SECRET` is absent, startup generates and prints one with a warning (dev convenience).

**New FastAPI endpoints** (all require the same `Authorization: Bearer` header already used by other routes):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/config/keys` | List providers with keys set (returns `{provider, present: bool}[]`, never the raw key) |
| `POST` | `/api/config/keys` | Save or update a key `{provider, key}` |
| `DELETE` | `/api/config/keys/{provider}` | Remove a key |

When a key is saved, TAPIOD sets the corresponding `os.environ` variable in-process so LiteLLM picks it up immediately (no restart needed).

### 4b — Backend: priority-ordered routing

`routing_config.json` already stores `tiers.fast` and `tiers.heavy` as lists. The new convention: **order = priority**. `pick_provider()` is updated to respect list order when a priority list exists, falling back to cost-rank only when no explicit order is set.

Existing endpoints `POST /api/config/tiers` and `DELETE /api/config/tiers/{alias}` are extended with a `PUT /api/config/tiers/reorder` endpoint:

```json
{ "tier": "heavy", "order": ["heavy-anthropic", "heavy-openai", "heavy-groq"] }
```

### 4c — Frontend: `/config` page — three new panels

**Panel 1 — API Keys**

One row per supported provider: Anthropic, OpenAI, Groq, Google Gemini.

Each row: provider logo/name | status dot (green = key present, grey = missing) | masked password input | Save button | Delete button (only shown when key is present).

Keys are never shown in the UI after saving — only the presence indicator.

**Panel 2 — Model Priority**

Two columns: Fast Tier and Heavy Tier.

Each column shows a vertically ordered list of model cards. Models whose provider key is missing are shown greyed out with a "No key" badge. User can drag to reorder within each tier; on drop, calls `PUT /api/config/tiers/reorder` immediately.

**Panel 3 — Fallback Behaviour (read-only info panel)**

Explains: "When a model fails (rate limit or quota exhausted), TAPIOD automatically tries the next model in your priority list." Shows the current effective fallback chain for each tier as a numbered list.

---

## Section 5 — Token Math: Cache Hits

When a request is served from cache, `hooks.py` currently sets `usage` to all zeros. This is correct (no tokens were consumed) but `actual_cost_usd` must be explicitly set to `0.0` and `cache_saved_usd` must be set using the new `get_costliest_available_model` baseline — not the old `gpt-4o-mini`. This ensures cache savings are denominated in the same baseline as routing savings, giving a consistent total.

---

## Data Flow (updated)

```
Request arrives
  │
  ├─ hooks.async_pre_call_hook
  │     ├─ Load tenant's provider keys from DB → set os.environ
  │     ├─ Qdrant cache lookup
  │     │     └─ HIT → return cached, cost=0, cache_saved = costliest_model_cost(prompt)
  │     ├─ get_available_providers() → reads os.environ keys
  │     ├─ get_costliest_available_model(available) → sets baseline for this request
  │     ├─ RouteLLM complexity score → pick_provider() respects priority list order
  │     └─ Dynamic tool injection
  │
  └─ hooks.async_post_call_success_hook
        ├─ actual_cost = LiteLLM response_cost
        ├─ routing_saved = baseline_cost - actual_cost (both via cost_per_token)
        └─ Write to DB: actual_cost, routing_saved, cache_saved, total_saved
```

---

## Files Changed

| File | Change |
|------|--------|
| `gateway/litellm_config.yaml` | Add `fast-anthropic`, update `heavy-anthropic` to Opus 4.8 |
| `gateway/router.py` | Update cost rank, add `get_costliest_available_model`, fix baseline in `compute_routing_save`, update `get_available_providers`, update `MODEL_MAP` |
| `gateway/cost.py` | Add `baseline_model` param to `estimate_cache_save` |
| `gateway/hooks.py` | Pass dynamic baseline to `estimate_cache_save`; add provider key DB table init; add key management endpoints; add tier reorder endpoint |
| `gateway/tests/benchmark_claude.py` | New benchmark script |
| `tapiod-web/src/app/config/page.tsx` | Add API Keys panel, Model Priority panel, Fallback info panel |

---

## Out of Scope

- Google Gemini provider support (architecture supports it, implementation deferred — add `GEMINI_API_KEY` to `.env` and the model list when ready)
- Key rotation / audit logs (correct architecture is in place; feature deferred)
- Rate-limit detection for automatic failover (currently failover is on error; smarter quota tracking is a future feature)
