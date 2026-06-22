# TAPIOD Claude Models + Provider Control Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Claude Opus 4.8 / Sonnet 4.6 to TAPIOD, fix the hardcoded savings baseline math, add encrypted provider key storage with drag-drop priority routing, and ship a benchmark comparison script.

**Architecture:** Six sequentially dependent tasks — model config first so later cost math has the right model strings; baseline fix second since it uses the full model list; key storage third (new table + endpoints); priority routing fourth (updates `pick_provider` + adds reorder endpoint); benchmark script fifth; frontend sixth (consumes all new endpoints). Each task ends with a passing test and a commit.

**Tech Stack:** Python 3.11, FastAPI, LiteLLM, asyncpg (PostgreSQL), `cryptography` (Fernet), `anthropic` Python SDK, `tabulate`; Next.js 16 App Router, Framer Motion `Reorder`, Tailwind CSS v4

## Global Constraints

- Claude model IDs contain NO date suffixes: `claude-opus-4-8` (heavy tier), `claude-sonnet-4-6` (fast tier)
- LiteLLM model strings: `anthropic/claude-opus-4-8`, `anthropic/claude-sonnet-4-6`
- `FERNET_SECRET` env var lives in `gateway/.env`; startup auto-generates and warns if absent
- All gateway tests run from `gateway/` directory: `cd gateway && pytest tests/ -v`
- Python path hack already present in all test files: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))`
- Frontend: Framer Motion `12.40` already installed — import from `"framer-motion"`, no new npm packages
- Frontend: All pages are `"use client"` Next.js 16 App Router components
- Frontend CSS uses `var(--token)` custom properties (`--accent-purple`, `--text-primary`, `--text-muted`, `--text-secondary`, `--accent-green`, `--accent-red`) and `glass-panel` class

---

### Task 1: Add Claude Models to Gateway Config

**Files:**
- Modify: `gateway/litellm_config.yaml`
- Modify: `gateway/router.py`
- Test: `gateway/tests/test_router.py`

**Interfaces:**
- Produces: `get_available_providers() -> list[str]` now returns `"fast-anthropic"` when `ANTHROPIC_API_KEY` is set; `PROVIDER_COST_RANK` and `MODEL_MAP` inside `compute_routing_save` updated with Anthropic entries

- [ ] **Step 1: Write the failing test**

Add to the bottom of `gateway/tests/test_router.py`:

```python
import os as _os

def test_get_available_providers_includes_anthropic_fast(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Re-import to pick up patched env
    import importlib
    import router as router_module
    importlib.reload(router_module)
    result = router_module.get_available_providers()
    assert "fast-anthropic" in result
    assert "heavy-anthropic" in result

def test_provider_cost_rank_has_anthropic():
    from router import PROVIDER_COST_RANK
    assert "fast-anthropic" in PROVIDER_COST_RANK
    assert "heavy-anthropic" in PROVIDER_COST_RANK
    assert PROVIDER_COST_RANK["heavy-anthropic"] > PROVIDER_COST_RANK["fast-anthropic"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gateway && pytest tests/test_router.py::test_get_available_providers_includes_anthropic_fast tests/test_router.py::test_provider_cost_rank_has_anthropic -v
```

Expected: FAIL — `"fast-anthropic" not in result` and `"fast-anthropic" not in PROVIDER_COST_RANK`

- [ ] **Step 3: Update `gateway/litellm_config.yaml`**

Replace the entire file with:

```yaml
litellm_settings:
  cache: false
  callbacks:
    - hooks.proxy_hooks

model_list:
  # Fast tier
  - model_name: fast-groq
    litellm_params:
      model: groq/llama-3.1-8b-instant
      api_key: os.environ/GROQ_API_KEY

  - model_name: fast-openai
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: fast-anthropic
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

  # Heavy tier
  - model_name: heavy-groq
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY

  - model_name: heavy-anthropic
    litellm_params:
      model: anthropic/claude-opus-4-8
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: heavy-openai
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 1
  fallbacks:
    - {"fast-openai": ["fast-groq"]}
    - {"fast-anthropic": ["fast-groq"]}
    - {"heavy-openai": ["heavy-groq"]}
    - {"heavy-anthropic": ["heavy-groq"]}
```

- [ ] **Step 4: Update `gateway/router.py`**

Replace the entire file with:

```python
import json
import os
from pathlib import Path

PROVIDER_COST_RANK = {
    "fast-groq":       0.06,
    "fast-openai":     0.60,
    "fast-anthropic":  15.00,
    "heavy-groq":      0.89,
    "heavy-openai":    10.00,
    "heavy-anthropic": 25.00,
}

_CONFIG_PATH = Path(__file__).parent / "routing_config.json"


def load_routing_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {
            "complexity_threshold": 0.5,
            "cache_similarity_threshold": 0.85,
            "cache_ttl_seconds": 3600,
            "tiers": {"fast": ["fast-groq"], "heavy": ["heavy-groq"]},
        }


def save_routing_config(config: dict):
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def knn_classify(qdrant, vec: list, top_k: int = 5) -> float:
    """Returns complexity score 0.0-1.0. >= threshold -> heavy tier."""
    try:
        results = qdrant.query_points(
            collection_name="routing_examples",
            query=vec,
            limit=top_k,
        )
        votes = [r.payload.get("label", "heavy") for r in results.points]
        if not votes:
            return 0.5
        return votes.count("heavy") / len(votes)
    except Exception:
        return 0.5


def get_available_providers() -> list[str]:
    available = []
    if os.getenv("GROQ_API_KEY"):
        available += ["fast-groq", "heavy-groq"]
    if os.getenv("OPENAI_API_KEY"):
        available += ["fast-openai", "heavy-openai"]
    if os.getenv("ANTHROPIC_API_KEY"):
        available += ["fast-anthropic", "heavy-anthropic"]
    return available or ["heavy-groq"]


def pick_provider(available: list[str], complexity_score: float) -> str:
    config = load_routing_config()
    threshold = config.get("complexity_threshold", 0.5)
    tier = "heavy" if complexity_score >= threshold else "fast"

    candidates = sorted(
        [p for p in available if p.startswith(tier)],
        key=lambda p: PROVIDER_COST_RANK.get(p, 999),
    )
    if not candidates:
        candidates = sorted(available, key=lambda p: PROVIDER_COST_RANK.get(p, 999))

    return candidates[0] if candidates else "heavy-groq"


def get_costliest_available_model(available: list[str]) -> str:
    """Returns the litellm model string for the most expensive model in `available`."""
    MODEL_MAP = {
        "fast-groq":       "groq/llama-3.1-8b-instant",
        "fast-openai":     "openai/gpt-4o-mini",
        "fast-anthropic":  "anthropic/claude-sonnet-4-6",
        "heavy-groq":      "groq/llama-3.3-70b-versatile",
        "heavy-openai":    "openai/gpt-4o",
        "heavy-anthropic": "anthropic/claude-opus-4-8",
    }
    try:
        from litellm import cost_per_token
        best_alias = available[0]
        best_cost = 0.0
        for alias in available:
            model = MODEL_MAP.get(alias)
            if not model:
                continue
            try:
                _, out = cost_per_token(
                    model=model, prompt_tokens=1000, completion_tokens=500
                )
                if out > best_cost:
                    best_cost = out
                    best_alias = alias
            except Exception:
                continue
        return MODEL_MAP.get(best_alias, "groq/llama-3.3-70b-versatile")
    except Exception:
        return "groq/llama-3.3-70b-versatile"


def compute_routing_save(
    chosen: str, available: list[str], prompt_tokens: int, completion_tokens: int
) -> float:
    """Estimate USD saved vs calling the costliest available model directly."""
    try:
        from litellm import cost_per_token
        MODEL_MAP = {
            "fast-groq":       "groq/llama-3.1-8b-instant",
            "fast-openai":     "openai/gpt-4o-mini",
            "fast-anthropic":  "anthropic/claude-sonnet-4-6",
            "heavy-groq":      "groq/llama-3.3-70b-versatile",
            "heavy-openai":    "openai/gpt-4o",
            "heavy-anthropic": "anthropic/claude-opus-4-8",
        }
        baseline_model = get_costliest_available_model(available)
        chosen_model = MODEL_MAP.get(chosen, "groq/llama-3.1-8b-instant")
        base_in, base_out = cost_per_token(
            model=baseline_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        cho_in, cho_out = cost_per_token(
            model=chosen_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return max(0.0, (base_in + base_out) - (cho_in + cho_out))
    except Exception:
        return 0.0
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd gateway && pytest tests/test_router.py -v
```

Expected: All 8 tests PASS (6 existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add gateway/litellm_config.yaml gateway/router.py gateway/tests/test_router.py
git commit -m "feat: add Claude Opus 4.8 (heavy) and Sonnet 4.6 (fast) to model list and routing"
```

---

### Task 2: Fix Baseline Cost Math

**Files:**
- Modify: `gateway/cost.py`
- Modify: `gateway/hooks.py` (lines 722, 742, 777)
- Test: `gateway/tests/test_cost.py`

**Interfaces:**
- Consumes: `get_costliest_available_model(available: list[str]) -> str` from `gateway/router.py` (Task 1)
- Consumes: `get_available_providers() -> list[str]` from `gateway/router.py` (Task 1)
- Produces: `estimate_cache_save(prompt: str, baseline_model: str, avg_completion_tokens: int = 150) -> float` — `baseline_model` is now required (no default)

- [ ] **Step 1: Write the failing test**

Update `gateway/tests/test_cost.py` — replace the entire file:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms


def test_estimate_memory_tokens_saved_empty():
    assert estimate_memory_tokens_saved([]) == 0


def test_estimate_memory_tokens_saved_counts_words():
    facts = ["User prefers Python", "User is building TAPIOD gateway"]
    result = estimate_memory_tokens_saved(facts)
    assert result > 0
    assert isinstance(result, int)


def test_seconds_to_ms():
    assert seconds_to_ms(1.5) == 1500.0
    assert seconds_to_ms(0.0) == 0.0


def test_estimate_cache_save_returns_float():
    result = estimate_cache_save(
        "hello world this is a test prompt",
        baseline_model="openai/gpt-4o",
    )
    assert isinstance(result, float)
    assert result >= 0.0


def test_estimate_cache_save_opus_more_expensive_than_groq():
    prompt = "Write a Python function that sorts a list."
    groq_save = estimate_cache_save(prompt, baseline_model="groq/llama-3.1-8b-instant")
    opus_save = estimate_cache_save(prompt, baseline_model="anthropic/claude-opus-4-8")
    assert opus_save > groq_save
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gateway && pytest tests/test_cost.py -v
```

Expected: FAIL — `estimate_cache_save() missing 1 required positional argument: 'baseline_model'` (after Step 3's change), or current tests pass but new ones fail.

- [ ] **Step 3: Update `gateway/cost.py`**

Replace the entire file with:

```python
def estimate_cache_save(
    prompt: str,
    baseline_model: str,
    avg_completion_tokens: int = 150,
) -> float:
    """Estimate USD saved by serving from cache instead of calling baseline_model."""
    try:
        from litellm import cost_per_token
        prompt_tokens = int(len(prompt.split()) * 1.3)
        input_cost, output_cost = cost_per_token(
            model=baseline_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=avg_completion_tokens,
        )
        return input_cost + output_cost
    except Exception:
        return 0.0


def estimate_memory_tokens_saved(facts: list[str]) -> int:
    """Estimate tokens not sent to LLM because memory recalled them."""
    return int(sum(len(f.split()) * 1.3 for f in facts))


def seconds_to_ms(seconds: float) -> float:
    return seconds * 1000.0
```

- [ ] **Step 4: Update the three call sites in `gateway/hooks.py`**

The import at line 44 already brings in `get_available_providers` and `get_costliest_available_model`. Verify the import line reads:

```python
from router import knn_classify, pick_provider, get_available_providers, compute_routing_save, load_routing_config, save_routing_config, get_costliest_available_model
```

If `get_costliest_available_model` is missing from that import, add it.

Then find the two `estimate_cache_save(prompt)` calls (around lines 722 and 742) and replace each with:

```python
ctx.cache_saved_usd = estimate_cache_save(
    prompt,
    baseline_model=get_costliest_available_model(get_available_providers()),
)
```

The `compute_routing_save` call (around line 777) already uses `available` from earlier in the same function — no change needed there because Task 1 already updated `compute_routing_save` to call `get_costliest_available_model` internally.

- [ ] **Step 5: Run all tests**

```bash
cd gateway && pytest tests/test_cost.py tests/test_router.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add gateway/cost.py gateway/hooks.py gateway/tests/test_cost.py
git commit -m "fix: baseline savings math now uses costliest available model, not hardcoded gpt-4o-mini"
```

---

### Task 3: Encrypted Provider Key Storage

**Files:**
- Create: `gateway/crypto.py`
- Modify: `gateway/hooks.py` — add `provider_keys` table to `init_db`, add 3 new endpoints
- Modify: `gateway/requirements.txt` — add `cryptography`
- Test: `gateway/tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_key(plain: str) -> str`, `decrypt_key(enc: str) -> str` from `gateway/crypto.py`
- Produces: `GET /api/config/keys` → `[{provider: str, present: bool}]`
- Produces: `POST /api/config/keys` body `{provider, key}` → `{status: "ok"}`
- Produces: `DELETE /api/config/keys/{provider}` → `{status: "ok"}`

- [ ] **Step 1: Write the failing test**

Create `gateway/tests/test_crypto.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cryptography.fernet import Fernet

# Set a fixed key before import so the module uses it consistently
_TEST_KEY = Fernet.generate_key().decode()
os.environ["FERNET_SECRET"] = _TEST_KEY

from crypto import encrypt_key, decrypt_key


def test_encrypt_decrypt_roundtrip():
    plain = "sk-ant-test-1234567890abcdef"
    enc = encrypt_key(plain)
    assert enc != plain
    assert decrypt_key(enc) == plain


def test_different_plaintexts_decrypt_correctly():
    assert decrypt_key(encrypt_key("key-A-value")) == "key-A-value"
    assert decrypt_key(encrypt_key("key-B-value")) == "key-B-value"
    assert encrypt_key("key-A-value") != encrypt_key("key-B-value")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gateway && pytest tests/test_crypto.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'crypto'`

- [ ] **Step 3: Add `cryptography` to `gateway/requirements.txt`**

Append to the file:

```
cryptography
```

Install it in the venv:

```bash
cd gateway && pip install cryptography
```

- [ ] **Step 4: Create `gateway/crypto.py`**

```python
import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    secret = os.getenv("FERNET_SECRET")
    if not secret:
        secret = Fernet.generate_key().decode()
        os.environ["FERNET_SECRET"] = secret
        print(
            f"[WARNING] FERNET_SECRET not set — generated ephemeral key: {secret}\n"
            "[WARNING] Keys stored this session will not survive a restart. "
            "Set FERNET_SECRET in gateway/.env"
        )
    return Fernet(secret.encode() if isinstance(secret, str) else secret)


def encrypt_key(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_key(enc: str) -> str:
    return _get_fernet().decrypt(enc.encode()).decode()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd gateway && pytest tests/test_crypto.py -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Add `provider_keys` table to `init_db` in `gateway/hooks.py`**

Find the `init_db` function (around line 152). Inside the `conn.execute(''' ... ''')` string, add the new table after the `chat_sessions` table:

```python
            CREATE TABLE IF NOT EXISTS provider_keys (
                tenant_id   TEXT NOT NULL,
                provider    TEXT NOT NULL,
                enc_key     TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (tenant_id, provider)
            );
```

The full execute call becomes:

```python
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS requests_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                tenant_id VARCHAR(255),
                user_id VARCHAR(255),
                latency FLOAT NOT NULL,
                model VARCHAR(255) NOT NULL,
                provider VARCHAR(50),
                prompt_tokens INT DEFAULT 0,
                completion_tokens INT DEFAULT 0,
                cost FLOAT DEFAULT 0.0,
                actual_cost_usd FLOAT DEFAULT 0.0,
                cache_hit BOOLEAN DEFAULT FALSE,
                cache_source VARCHAR(20),
                cache_saved_usd FLOAT DEFAULT 0.0,
                routing_saved_usd FLOAT DEFAULT 0.0,
                memory_tokens_saved INT DEFAULT 0,
                total_saved_usd FLOAT DEFAULT 0.0,
                blocked BOOLEAN DEFAULT FALSE,
                pipeline_trace JSONB
            );
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(255) PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                messages JSONB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_keys (
                tenant_id   TEXT NOT NULL,
                provider    TEXT NOT NULL,
                enc_key     TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (tenant_id, provider)
            );
        ''')
```

- [ ] **Step 7: Add the three key management endpoints to `gateway/hooks.py`**

Insert after the existing `delete_model` endpoint (around line 658, before the `GatewayHooks` class definition):

```python
PROVIDER_ENV_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "groq":      "GROQ_API_KEY",
    "gemini":    "GEMINI_API_KEY",
}


class ProviderKeyRequest(BaseModel):
    provider: str
    key: str


@app.get("/api/config/keys")
async def list_provider_keys():
    return [
        {"provider": p, "present": bool(os.getenv(env))}
        for p, env in PROVIDER_ENV_MAP.items()
    ]


@app.post("/api/config/keys")
async def save_provider_key(req: ProviderKeyRequest):
    from crypto import encrypt_key
    enc = encrypt_key(req.key)
    conn = await asyncpg.connect(DB_DSN)
    await conn.execute(
        """INSERT INTO provider_keys (tenant_id, provider, enc_key)
           VALUES ($1, $2, $3)
           ON CONFLICT (tenant_id, provider) DO UPDATE SET enc_key = $3, created_at = NOW()""",
        "default_tenant", req.provider, enc,
    )
    await conn.close()
    env_var = PROVIDER_ENV_MAP.get(req.provider)
    if env_var:
        os.environ[env_var] = req.key
    return {"status": "ok"}


@app.delete("/api/config/keys/{provider}")
async def delete_provider_key(provider: str):
    conn = await asyncpg.connect(DB_DSN)
    await conn.execute(
        "DELETE FROM provider_keys WHERE tenant_id = $1 AND provider = $2",
        "default_tenant", provider,
    )
    await conn.close()
    env_var = PROVIDER_ENV_MAP.get(provider)
    if env_var and env_var in os.environ:
        del os.environ[env_var]
    return {"status": "ok"}
```

- [ ] **Step 8: Restart FastAPI and verify**

```bash
cd gateway && uvicorn hooks:app --port 4001 --reload
```

In another terminal:

```bash
curl http://localhost:4001/api/config/keys
```

Expected response: `[{"provider":"anthropic","present":false},{"provider":"openai","present":false},{"provider":"groq","present":true},{"provider":"gemini","present":false}]` (groq is true because GROQ_API_KEY is in .env)

- [ ] **Step 9: Commit**

```bash
git add gateway/crypto.py gateway/hooks.py gateway/requirements.txt gateway/tests/test_crypto.py
git commit -m "feat: encrypted provider key storage with Fernet and /api/config/keys endpoints"
```

---

### Task 4: Priority-Ordered Routing

**Files:**
- Modify: `gateway/router.py` — update `pick_provider` to respect priority list from `routing_config.json`
- Modify: `gateway/hooks.py` — add `PUT /api/config/tiers/reorder` endpoint
- Test: `gateway/tests/test_router.py`

**Interfaces:**
- Consumes: `load_routing_config() -> dict` from Task 1 — `config["tiers"]["fast"]` and `config["tiers"]["heavy"]` are priority-ordered lists
- Produces: `PUT /api/config/tiers/reorder` body `{tier: "fast"|"heavy", order: [alias, ...]}` → `{tiers: {fast: [...], heavy: [...]}}`

- [ ] **Step 1: Write the failing test**

Add to `gateway/tests/test_router.py`:

```python
def test_pick_provider_respects_priority_order(monkeypatch):
    """Priority list [heavy-openai, heavy-groq] → picks heavy-openai even though groq is cheaper."""
    def mock_config():
        return {
            "complexity_threshold": 0.5,
            "tiers": {"fast": ["fast-groq"], "heavy": ["heavy-openai", "heavy-groq"]},
        }
    monkeypatch.setattr("router.load_routing_config", mock_config)
    available = ["fast-groq", "heavy-groq", "heavy-openai"]
    provider = pick_provider(available, complexity_score=0.8)
    assert provider == "heavy-openai"


def test_pick_provider_skips_unavailable_priority_entries(monkeypatch):
    """Priority list [heavy-anthropic, heavy-openai, heavy-groq] — anthropic unavailable → picks openai."""
    def mock_config():
        return {
            "complexity_threshold": 0.5,
            "tiers": {"fast": ["fast-groq"], "heavy": ["heavy-anthropic", "heavy-openai", "heavy-groq"]},
        }
    monkeypatch.setattr("router.load_routing_config", mock_config)
    available = ["fast-groq", "heavy-groq", "heavy-openai"]  # no heavy-anthropic
    provider = pick_provider(available, complexity_score=0.8)
    assert provider == "heavy-openai"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gateway && pytest tests/test_router.py::test_pick_provider_respects_priority_order tests/test_router.py::test_pick_provider_skips_unavailable_priority_entries -v
```

Expected: FAIL — current implementation ignores the priority list order, still picks cheapest

- [ ] **Step 3: Update `pick_provider` in `gateway/router.py`**

Replace the `pick_provider` function with:

```python
def pick_provider(available: list[str], complexity_score: float) -> str:
    config = load_routing_config()
    threshold = config.get("complexity_threshold", 0.5)
    tier = "heavy" if complexity_score >= threshold else "fast"

    priority_list = config.get("tiers", {}).get(tier, [])
    # Use priority order from config, filtered to only what's available
    ordered_candidates = [p for p in priority_list if p in available]

    if not ordered_candidates:
        # Fall back to cost-rank ordering when no priority entries are available
        ordered_candidates = sorted(
            [p for p in available if p.startswith(tier)],
            key=lambda p: PROVIDER_COST_RANK.get(p, 999),
        )

    if not ordered_candidates:
        ordered_candidates = sorted(available, key=lambda p: PROVIDER_COST_RANK.get(p, 999))

    return ordered_candidates[0] if ordered_candidates else "heavy-groq"
```

- [ ] **Step 4: Run all router tests**

```bash
cd gateway && pytest tests/test_router.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 5: Add `TierReorderRequest` model and `PUT /api/config/tiers/reorder` to `gateway/hooks.py`**

Insert after the existing `remove_tier_model` endpoint (around line 1211, before `proxy_hooks = GatewayHooks()`):

```python
class TierReorderRequest(BaseModel):
    tier: str
    order: list[str]


@app.put("/api/config/tiers/reorder")
async def reorder_tier(req: TierReorderRequest):
    if req.tier not in ("fast", "heavy"):
        return {"error": "tier must be 'fast' or 'heavy'"}
    config = load_routing_config()
    config.setdefault("tiers", {})[req.tier] = req.order
    save_routing_config(config)
    return {"tiers": config["tiers"]}
```

- [ ] **Step 6: Verify the endpoint works**

Restart FastAPI (`uvicorn hooks:app --port 4001 --reload`), then:

```bash
curl -X PUT http://localhost:4001/api/config/tiers/reorder \
  -H "Content-Type: application/json" \
  -d '{"tier": "heavy", "order": ["heavy-anthropic", "heavy-openai", "heavy-groq"]}'
```

Expected: `{"tiers": {"fast": ["fast-groq", "fast-openai"], "heavy": ["heavy-anthropic", "heavy-openai", "heavy-groq"]}}`

- [ ] **Step 7: Commit**

```bash
git add gateway/router.py gateway/hooks.py gateway/tests/test_router.py
git commit -m "feat: pick_provider respects priority list order from routing_config.json + reorder endpoint"
```

---

### Task 5: Benchmark Script

**Files:**
- Modify: `gateway/requirements.txt` — add `tabulate`, `anthropic`
- Create: `gateway/tests/benchmark_claude.py`

**Interfaces:**
- Consumes: TAPIOD running on `http://localhost:4001` (Tasks 1–4)
- Consumes: `ANTHROPIC_API_KEY` set in environment
- Produces: terminal table via `tabulate`, CSV at `gateway/tests/results/benchmark_YYYY-MM-DD_HH-MM.csv`

- [ ] **Step 1: Add dependencies to `gateway/requirements.txt`**

Append to the file:

```
tabulate
anthropic
```

Install them:

```bash
cd gateway && pip install tabulate anthropic
```

- [ ] **Step 2: Create `gateway/tests/benchmark_claude.py`**

```python
#!/usr/bin/env python3
"""Benchmark: TAPIOD vs direct Claude Opus 4.8 on 20 coding-workspace prompts.

Run with: cd gateway && python tests/benchmark_claude.py
Requires: ANTHROPIC_API_KEY set, TAPIOD running on http://localhost:4001
"""
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from anthropic import Anthropic
from tabulate import tabulate

TAPIOD_URL = "http://localhost:4001/api/agent/chat/completions"
OPUS_MODEL = "claude-opus-4-8"
OPUS_INPUT_COST_PER_M = 5.0    # USD per 1M input tokens
OPUS_OUTPUT_COST_PER_M = 25.0  # USD per 1M output tokens

PROMPTS = [
    # Explain errors
    "I'm getting `TypeError: 'NoneType' object is not subscriptable` in Python. What does it mean and how do I fix it?",
    "My React component throws `Cannot read properties of undefined (reading 'map')`. What's happening?",
    "What does `ECONNREFUSED 127.0.0.1:5432` mean and how do I debug it?",
    "Git says `Your branch has diverged`. How do I resolve this without losing my work?",
    # Write functions
    "Write a Python function that implements binary search on a sorted list.",
    "Write a JavaScript debounce function with TypeScript types.",
    "Write a SQL query that finds the top 5 customers by total order value in the last 30 days.",
    "Write a Python context manager that times a block of code and logs the result.",
    # Debug code
    "Here's a Python loop that should sum a list but gives the wrong answer: `total = 0; for i in range(1, len(nums)): total += nums[i]`. What's the bug?",
    "My async function returns a Promise instead of the resolved value. What am I doing wrong?",
    "Why does my Docker container exit immediately after starting? How do I debug it?",
    # Refactor / code review
    "Review this function for improvements: `def get_user(id): return db.query('SELECT * FROM users WHERE id=' + str(id))`",
    "How would you refactor a 200-line Python function that does validation, DB writes, and email sending all in one?",
    "What's the difference between `useEffect(() => {}, [])` and `useEffect(() => {})` in React?",
    # Git / DevOps
    "Explain `git rebase -i HEAD~3` and when I should use it.",
    "Write a minimal Dockerfile for a Node.js 20 Express app.",
    "Write a GitHub Actions workflow that runs pytest on every pull request.",
    # Documentation
    "Write a NumPy-style docstring for a function that calculates compound interest.",
    r"Explain what this regex does: `^(?=.*[A-Z])(?=.*\d)(?=.*[@$!])[A-Za-z\d@$!]{8,}$`",
    "Write a one-paragraph README section explaining what a vector database is to a non-technical reader.",
]

# Cost rates (USD per 1M tokens) for models TAPIOD routes to
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-opus-4-8":           (5.0,  25.0),
    "claude-sonnet-4-6":         (3.0,  15.0),
    "gpt-4o":                    (5.0,  15.0),
    "gpt-4o-mini":               (0.15,  0.60),
    "llama-3.1-8b-instant":      (0.05,  0.08),
    "llama-3.3-70b-versatile":   (0.59,  0.79),
}


def cost_usd(model_str: str, prompt_tokens: int, completion_tokens: int) -> float:
    for key, (in_rate, out_rate) in MODEL_COSTS.items():
        if key in model_str:
            return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000
    return (prompt_tokens * OPUS_INPUT_COST_PER_M + completion_tokens * OPUS_OUTPUT_COST_PER_M) / 1_000_000


def call_tapiod(prompt: str) -> dict:
    try:
        r = httpx.post(
            TAPIOD_URL,
            json={"model": "heavy-groq", "messages": [{"role": "user", "content": prompt}]},
            timeout=90.0,
        )
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        model = data.get("model", "unknown")
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        cache_hit = model == "cached"
        return {
            "model": model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cache_hit": cache_hit,
            "cost_usd": 0.0 if cache_hit else cost_usd(model, pt, ct),
        }
    except Exception as e:
        return {
            "model": f"error: {e}",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cache_hit": False,
            "cost_usd": 0.0,
        }


def call_opus_direct(client: Anthropic, prompt: str) -> dict:
    try:
        resp = client.messages.create(
            model=OPUS_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        pt = resp.usage.input_tokens
        ct = resp.usage.output_tokens
        return {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cost_usd": (pt * OPUS_INPUT_COST_PER_M + ct * OPUS_OUTPUT_COST_PER_M) / 1_000_000,
        }
    except Exception as e:
        return {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "error": str(e)}


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    results = []
    table_rows = []
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\nTAPIoD Benchmark — {run_ts}")
    print(f"Baseline: Claude Opus 4.8  (${OPUS_INPUT_COST_PER_M}/M in, ${OPUS_OUTPUT_COST_PER_M}/M out)")
    print(f"Prompts:  {len(PROMPTS)} coding-workspace scenarios\n")

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"[{i:2d}/{len(PROMPTS)}] {prompt[:55]}…", end=" ", flush=True)

        tapiod = call_tapiod(prompt)
        time.sleep(0.3)
        direct = call_opus_direct(client, prompt)

        saved_usd = max(0.0, direct["cost_usd"] - tapiod["cost_usd"])
        saved_pct = (saved_usd / direct["cost_usd"] * 100) if direct["cost_usd"] > 0 else 0.0
        print(f"→ {tapiod['model'][-20:]}  saved ${saved_usd:.5f}")

        row = {
            "num":               i,
            "prompt":            prompt[:50],
            "tapiod_model":      tapiod["model"],
            "cache":             "HIT" if tapiod["cache_hit"] else "-",
            "prompt_tokens":     tapiod["prompt_tokens"],
            "completion_tokens": tapiod["completion_tokens"],
            "tapiod_cost_usd":   tapiod["cost_usd"],
            "opus_cost_usd":     direct["cost_usd"],
            "saved_usd":         saved_usd,
            "saved_pct":         saved_pct,
        }
        results.append(row)

        table_rows.append([
            i,
            prompt[:50],
            tapiod["model"][-22:],
            "HIT" if tapiod["cache_hit"] else "-",
            tapiod["prompt_tokens"],
            tapiod["completion_tokens"],
            f"${tapiod['cost_usd']:.6f}",
            f"${direct['cost_usd']:.6f}",
            f"${saved_usd:.6f}",
            f"{saved_pct:.1f}%",
        ])

    total_tapiod = sum(r["tapiod_cost_usd"] for r in results)
    total_opus   = sum(r["opus_cost_usd"]   for r in results)
    total_saved  = sum(r["saved_usd"]        for r in results)
    total_pct    = (total_saved / total_opus * 100) if total_opus > 0 else 0.0

    table_rows.append([
        "TOTAL", "", "", "", "", "",
        f"${total_tapiod:.6f}",
        f"${total_opus:.6f}",
        f"${total_saved:.6f}",
        f"{total_pct:.1f}%",
    ])

    headers = [
        "#", "Prompt (50 chars)", "TAPIOD Model", "Cache",
        "P.Tokens", "C.Tokens", "TAPIOD Cost $", "Opus Direct $", "Saved $", "Saved %",
    ]

    print("\n" + "=" * 130)
    print(tabulate(table_rows, headers=headers, tablefmt="rounded_outline"))
    print(f"\nTotal saved via TAPIOD: ${total_saved:.6f}  ({total_pct:.1f}% vs all-Opus-4.8 baseline)")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"benchmark_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the benchmark**

Ensure TAPIOD is running (FastAPI on 4001, LiteLLM on 4000, Qdrant + PostgreSQL via docker compose).

```bash
cd gateway && python tests/benchmark_claude.py
```

Expected: terminal table with 20 rows + TOTAL row, CSV written to `gateway/tests/results/benchmark_<timestamp>.csv`

- [ ] **Step 4: Commit**

```bash
git add gateway/requirements.txt gateway/tests/benchmark_claude.py
git commit -m "feat: benchmark script comparing TAPIOD vs direct Claude Opus 4.8 on 20 prompts"
```

---

### Task 6: Frontend Config Page Overhaul

**Files:**
- Modify: `tapiod-web/src/app/config/page.tsx` — replace entire file

**Interfaces:**
- Consumes: `GET /api/config/keys` → `[{provider: str, present: bool}]` (Task 3)
- Consumes: `POST /api/config/keys` body `{provider, key}` (Task 3)
- Consumes: `DELETE /api/config/keys/{provider}` (Task 3)
- Consumes: `GET /api/config/tiers` → full routing config with `tiers.fast` and `tiers.heavy` (existing)
- Consumes: `PUT /api/config/tiers/reorder` body `{tier, order}` (Task 4)
- Consumes: `PATCH /api/config/thresholds` (existing)

- [ ] **Step 1: Replace `tapiod-web/src/app/config/page.tsx`**

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { Reorder } from "framer-motion";
import { Lock, GripVertical, CheckCircle, XCircle, Save, Trash2, ChevronRight } from "lucide-react";

const PROVIDERS = [
  { id: "anthropic", name: "Anthropic",     hint: "sk-ant-api03-..." },
  { id: "openai",    name: "OpenAI",         hint: "sk-proj-..." },
  { id: "groq",      name: "Groq",           hint: "gsk_..." },
  { id: "gemini",    name: "Google Gemini",  hint: "AIza..." },
];

const COMING_SOON_TOGGLE = ({ label }: { label: string }) => (
  <div className="flex items-center justify-between opacity-40 cursor-not-allowed">
    <span className="text-sm text-[var(--text-secondary)]">{label}</span>
    <div className="w-10 h-5 rounded-full bg-white/10 border border-white/10" />
  </div>
);

export default function Config() {
  const [tiers, setTiers]             = useState<any>(null);
  const [fastTier, setFastTier]       = useState<string[]>([]);
  const [heavyTier, setHeavyTier]     = useState<string[]>([]);
  const [keyStatuses, setKeyStatuses] = useState<{ provider: string; present: boolean }[]>([]);
  const [keyInputs, setKeyInputs]     = useState<Record<string, string>>({});
  const [saving, setSaving]           = useState<Record<string, boolean>>({});

  const fetchAll = useCallback(async () => {
    try {
      const [tiersRes, keysRes] = await Promise.all([
        fetch("/api/config/tiers"),
        fetch("/api/config/keys"),
      ]);
      if (tiersRes.ok) {
        const t = await tiersRes.json();
        setTiers(t);
        setFastTier(t.tiers?.fast ?? []);
        setHeavyTier(t.tiers?.heavy ?? []);
      }
      if (keysRes.ok) setKeyStatuses(await keysRes.json());
    } catch {}
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const saveKey = async (provider: string) => {
    const key = keyInputs[provider];
    if (!key) return;
    setSaving(s => ({ ...s, [provider]: true }));
    await fetch("/api/config/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, key }),
    });
    setKeyInputs(k => ({ ...k, [provider]: "" }));
    await fetchAll();
    setSaving(s => ({ ...s, [provider]: false }));
  };

  const deleteKey = async (provider: string) => {
    await fetch(`/api/config/keys/${provider}`, { method: "DELETE" });
    await fetchAll();
  };

  const handleReorder = async (tier: string, newOrder: string[]) => {
    if (tier === "fast") setFastTier(newOrder);
    else setHeavyTier(newOrder);
    await fetch("/api/config/tiers/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tier, order: newOrder }),
    });
  };

  const keyPresentFor = (alias: string): boolean => {
    const provider = alias.split("-")[1]; // "fast-groq" → "groq", "heavy-anthropic" → "anthropic"
    return keyStatuses.find(k => k.provider === provider)?.present ?? true;
  };

  const updateThreshold = async (key: string, value: number) => {
    await fetch("/api/config/thresholds", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    await fetchAll();
  };

  const SliderRow = ({
    label, configKey, min, max, step, unit,
  }: {
    label: string; configKey: string; min: number; max: number; step: number; unit: string;
  }) => {
    const val = tiers?.[configKey] ?? (configKey === "complexity_threshold" ? 0.5 : 0.85);
    return (
      <div className="flex items-center justify-between gap-6">
        <span className="text-sm text-[var(--text-secondary)] w-56">{label}</span>
        <div className="flex items-center gap-3 flex-1">
          <input
            type="range" min={min} max={max} step={step}
            defaultValue={val}
            className="flex-1 accent-[var(--accent-purple)]"
            onMouseUp={e => updateThreshold(configKey, parseFloat((e.target as HTMLInputElement).value))}
          />
          <span className="text-sm text-[var(--text-muted)] w-16 text-right">{val}{unit}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-8 pb-8">
      <div>
        <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Configuration</h1>
        <p className="text-[var(--text-muted)]">
          Manage API keys, model routing priority, cache settings, and guardrails.
        </p>
      </div>

      {/* API Keys */}
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          API Keys
        </h2>
        {PROVIDERS.map(({ id, name, hint }) => {
          const present = keyStatuses.find(k => k.provider === id)?.present ?? false;
          return (
            <div
              key={id}
              className="flex items-center gap-4 bg-white/5 rounded-lg p-3 border border-white/5"
            >
              <div className="flex items-center gap-2 w-40 shrink-0">
                {present
                  ? <CheckCircle size={14} className="text-[var(--accent-green)] shrink-0" />
                  : <XCircle    size={14} className="text-[var(--text-muted)]   shrink-0" />
                }
                <span className="text-sm font-medium text-[var(--text-primary)]">{name}</span>
              </div>
              <input
                type="password"
                placeholder={present ? "••••••••••••••••" : hint}
                value={keyInputs[id] ?? ""}
                onChange={e => setKeyInputs(k => ({ ...k, [id]: e.target.value }))}
                className="flex-1 bg-transparent border border-white/10 rounded-lg px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-purple)]"
              />
              <button
                onClick={() => saveKey(id)}
                disabled={!keyInputs[id] || saving[id]}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[var(--accent-purple)] text-white text-xs disabled:opacity-30 shrink-0"
              >
                <Save size={12} /> Save
              </button>
              {present && (
                <button
                  onClick={() => deleteKey(id)}
                  className="text-[var(--text-muted)] hover:text-[var(--accent-red)] p-1 shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          );
        })}
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Keys are stored encrypted in PostgreSQL. They are never shown after saving.
        </p>
      </div>

      {/* Model Priority */}
      <div className="glass-panel p-6 flex flex-col gap-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
            Model Priority
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Drag to reorder. TAPIOD uses the first available model in each tier.
            Greyed-out models are missing their API key.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-6">
          {([
            { tier: "fast",  label: "Fast Tier",  values: fastTier,  caption: "complexity < threshold" },
            { tier: "heavy", label: "Heavy Tier", values: heavyTier, caption: "complexity ≥ threshold" },
          ] as const).map(({ tier, label, values, caption }) => (
            <div key={tier}>
              <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] mb-3">
                {label} <span className="normal-case">({caption})</span>
              </h3>
              <Reorder.Group
                axis="y"
                values={values}
                onReorder={(newOrder) => handleReorder(tier, newOrder)}
                as="div"
                className="flex flex-col gap-2"
              >
                {values.map((alias: string, i: number) => {
                  const hasKey = keyPresentFor(alias);
                  return (
                    <Reorder.Item
                      key={alias}
                      value={alias}
                      as="div"
                      className="flex items-center gap-3 bg-white/5 rounded-lg p-3 border border-white/5 cursor-grab select-none"
                      style={{ opacity: hasKey ? 1 : 0.35 }}
                    >
                      <GripVertical size={14} className="text-[var(--text-muted)] shrink-0" />
                      <span className="text-xs text-[var(--text-muted)] w-4 shrink-0">{i + 1}</span>
                      <span className="flex-1 text-sm text-[var(--text-primary)]">{alias}</span>
                      {!hasKey && (
                        <span className="text-xs bg-white/10 rounded px-2 py-0.5 text-[var(--text-muted)] shrink-0">
                          No key
                        </span>
                      )}
                    </Reorder.Item>
                  );
                })}
              </Reorder.Group>
            </div>
          ))}
        </div>
      </div>

      {/* Fallback Behaviour */}
      <div className="glass-panel p-6 flex flex-col gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          Fallback Behaviour
        </h2>
        <p className="text-sm text-[var(--text-muted)]">
          When a model fails (rate limit or quota exhausted), TAPIOD automatically
          tries the next model in your priority list.
        </p>
        <div className="flex flex-col gap-3 mt-1">
          {[
            { label: "Fast tier chain",  values: fastTier  },
            { label: "Heavy tier chain", values: heavyTier },
          ].map(({ label, values }) => (
            <div key={label} className="flex items-start gap-3">
              <span className="text-xs text-[var(--text-muted)] w-36 pt-0.5 shrink-0">{label}</span>
              <div className="flex items-center gap-1 flex-wrap">
                {values.length === 0 ? (
                  <span className="text-xs text-[var(--text-muted)]">—</span>
                ) : values.map((alias: string, i: number) => (
                  <span key={alias} className="flex items-center gap-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        keyPresentFor(alias)
                          ? "bg-[var(--accent-purple)]/20 text-[var(--text-primary)]"
                          : "bg-white/5 text-[var(--text-muted)]"
                      }`}
                    >
                      {alias}
                    </span>
                    {i < values.length - 1 && (
                      <ChevronRight size={12} className="text-[var(--text-muted)]" />
                    )}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Thresholds */}
      <div className="glass-panel p-6 flex flex-col gap-5">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)]">
          Thresholds
        </h2>
        <SliderRow
          label="KNN Routing threshold (fast vs heavy)"
          configKey="complexity_threshold"
          min={0.1} max={0.9} step={0.05} unit=""
        />
        <SliderRow
          label="Semantic cache similarity threshold"
          configKey="cache_similarity_threshold"
          min={0.5} max={0.99} step={0.01} unit=""
        />
        <SliderRow
          label="Redis cache TTL"
          configKey="cache_ttl_seconds"
          min={60} max={86400} step={60} unit="s"
        />
      </div>

      {/* Guardrails — Coming Soon */}
      <div className="glass-panel p-6 flex flex-col gap-4 opacity-70">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-2">
          <Lock size={14} /> Guardrails
          <span className="text-xs bg-white/10 rounded px-2 py-0.5 ml-1">Coming Soon</span>
        </h2>
        <COMING_SOON_TOGGLE label="Block harmful content" />
        <COMING_SOON_TOGGLE label="Max tokens per request" />
        <COMING_SOON_TOGGLE label="Rate limit per tenant" />
      </div>

      {/* PII Masking — Coming Soon */}
      <div className="glass-panel p-6 flex flex-col gap-4 opacity-70">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-2">
          <Lock size={14} /> PII Masking
          <span className="text-xs bg-white/10 rounded px-2 py-0.5 ml-1">Coming Soon</span>
        </h2>
        <COMING_SOON_TOGGLE label="Mask email addresses" />
        <COMING_SOON_TOGGLE label="Mask phone numbers" />
        <COMING_SOON_TOGGLE label="Mask credit card numbers" />
        <COMING_SOON_TOGGLE label="Restore PII in response" />
        <p className="text-xs text-[var(--text-muted)] mt-2">Powered by Microsoft Presidio</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Start the dev server and verify in browser**

```bash
cd tapiod-web && npm run dev
```

Open `http://localhost:3000/config`. Verify:
1. API Keys panel shows 4 providers with status indicators
2. Saving a key updates the green/grey dot
3. Model Priority panel shows draggable cards in two columns
4. Dragging a card saves the new order (check `routing_config.json` is updated)
5. Fallback Behaviour panel shows the chain with `→` between models
6. Thresholds sliders still work
7. Coming Soon panels still render

- [ ] **Step 3: Commit**

```bash
git add tapiod-web/src/app/config/page.tsx
git commit -m "feat: config page — API key management, drag-drop model priority, fallback info panel"
```

---

## Self-Review

### Spec Coverage

| Spec section | Task that implements it |
|---|---|
| Add `fast-anthropic` + update `heavy-anthropic` | Task 1 |
| Update `PROVIDER_COST_RANK` with Anthropic pricing | Task 1 |
| Update `get_available_providers` for Anthropic | Task 1 |
| `get_costliest_available_model()` function | Task 1 (function defined) + Task 2 (call sites wired) |
| Fix `compute_routing_save` hardcoded baseline | Task 1 (internal call to `get_costliest_available_model`) |
| Fix `estimate_cache_save` hardcoded baseline | Task 2 (signature) + Task 2 (hooks.py call sites) |
| Encrypted key storage (`provider_keys` table) | Task 3 |
| Fernet `crypto.py` module | Task 3 |
| `GET/POST/DELETE /api/config/keys` endpoints | Task 3 |
| `pick_provider` priority-list ordering | Task 4 |
| `PUT /api/config/tiers/reorder` endpoint | Task 4 |
| 20-prompt benchmark script | Task 5 |
| CSV + terminal table output | Task 5 |
| Frontend API Keys panel | Task 6 |
| Frontend Model Priority drag-drop | Task 6 |
| Frontend Fallback Info panel | Task 6 |

### Type Consistency

- `get_costliest_available_model(available: list[str]) -> str` — defined in Task 1, called in Task 2 ✓
- `estimate_cache_save(prompt, baseline_model)` — `baseline_model` required (no default) in Task 2 ✓
- `TierReorderRequest.tier: str`, `.order: list[str]` — defined in Task 4, consumed by frontend in Task 6 ✓
- `ProviderKeyRequest.provider: str`, `.key: str` — defined in Task 3, consumed by frontend in Task 6 ✓
- `keyPresentFor(alias)` in frontend uses `alias.split("-")[1]` to extract provider — works for `fast-groq`, `heavy-anthropic`, `fast-openai`, `heavy-openai`, `fast-anthropic`, `heavy-groq` ✓
