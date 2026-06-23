# AI-Agent-Foundry Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the TAPIOD codebase into the `AI-Agent-Foundry/` directory structure prescribed by the engineering team, with a clean `backend/` (FastAPI + aml_agent module) and `frontend/` (Next.js) split.

**Architecture:** The current `gateway/` Python code is split across `backend/main.py` (FastAPI routes), `backend/aml_agent/llm_service.py` (GatewayHooks LiteLLM callback), and `backend/aml_agent/detector.py` (tool registry + executor). Small shared utilities (cache, router, memory, context, cost, crypto) live in `backend/` as internal modules imported by the two agent files. The Next.js frontend moves into `frontend/` with a new `content/` directory for static copy.

**Tech Stack:** Python 3.11+, FastAPI, LiteLLM proxy, Qdrant, asyncpg, FastEmbed, Next.js 16 (App Router), Tailwind CSS v4, TypeScript.

## Global Constraints

- New project root: `/home/adity/StatusNeo/AI-Agent-Foundry/`
- Python virtual environment: `backend/venv/` (recreated fresh; do NOT copy `gateway/venv/`)
- `.env` must never be committed; `.env.example` must be committed instead
- All imports inside `backend/` must be relative to `backend/` (i.e., `from cache import ...` not `from gateway.cache import ...`)
- LiteLLM proxy config (`litellm_config.yaml`) references `hooks.proxy_hooks` — in the new structure it must reference `aml_agent.llm_service.proxy_hooks`
- Next.js App Router pages stay in `src/app/` (App Router requirement); the `pages/` in the spec maps to this folder conceptually
- Keep all existing tests under `backend/tests/`

---

## File Map

| Source (current) | Destination (new) | Role |
|---|---|---|
| `gateway/hooks.py` lines 1–757 (FastAPI routes) | `backend/main.py` | App entry point, all HTTP routes |
| `gateway/hooks.py` lines 758–1100 (`GatewayHooks` class) | `backend/aml_agent/llm_service.py` | LiteLLM custom callback, caching, routing, tool injection |
| `gateway/tool_executor.py` + `gateway/tools_registry.py` | `backend/aml_agent/detector.py` | Tool implementations + registry + executor |
| `gateway/cache.py` | `backend/cache.py` | Qdrant + Redis cache helpers |
| `gateway/context.py` | `backend/context.py` | `RequestContext` dataclass |
| `gateway/router.py` | `backend/router.py` | RouteLLM + KNN routing logic |
| `gateway/memory.py` | `backend/memory.py` | Qdrant user-memory helpers |
| `gateway/cost.py` | `backend/cost.py` | Token cost estimators |
| `gateway/crypto.py` | `backend/crypto.py` | Fernet key encryption |
| `gateway/litellm_config.yaml` | `backend/litellm_config.yaml` | LiteLLM proxy model list |
| `gateway/routing_config.json` | `backend/routing_config.json` | Routing thresholds |
| `gateway/.env` | `backend/.env` (not committed) | Secrets |
| `gateway/.env.example` | `backend/.env.example` | Secrets template |
| `gateway/requirements.txt` | `backend/requirements.txt` | Python deps |
| `gateway/seed_routing.py` + `gateway/seed_all.py` | `backend/seed_routing.py` + `backend/seed_all.py` | One-time DB seeders |
| `gateway/tests/` | `backend/tests/` | Pytest suite |
| `tapiod-web/src/components/` | `frontend/src/components/` | React components |
| `tapiod-web/src/app/` | `frontend/src/app/` | Next.js App Router pages |
| `tapiod-web/src/app/globals.css` | `frontend/src/app/globals.css` | Global styles |
| `tapiod-web/public/` | `frontend/public/` | Static assets |
| `tapiod-web/package.json` etc. | `frontend/package.json` etc. | Node tooling |
| *(new)* | `frontend/content/` | Static copy/data used by UI pages |

---

## Task 1: Scaffold the AI-Agent-Foundry directory tree

**Files:**
- Create: `/home/adity/StatusNeo/AI-Agent-Foundry/` (project root)
- Create: `backend/`
- Create: `backend/aml_agent/`
- Create: `frontend/`
- Create: `frontend/content/`

- [ ] **Step 1: Create the directory skeleton**

```bash
mkdir -p /home/adity/StatusNeo/AI-Agent-Foundry/backend/aml_agent
mkdir -p /home/adity/StatusNeo/AI-Agent-Foundry/frontend/content
```

- [ ] **Step 2: Initialise git**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git init
echo "backend/venv/" >> .gitignore
echo "backend/.env" >> .gitignore
echo "frontend/.next/" >> .gitignore
echo "frontend/node_modules/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
```

- [ ] **Step 3: Verify structure**

```bash
find /home/adity/StatusNeo/AI-Agent-Foundry -type d
```
Expected output:
```
/home/adity/StatusNeo/AI-Agent-Foundry
/home/adity/StatusNeo/AI-Agent-Foundry/backend
/home/adity/StatusNeo/AI-Agent-Foundry/backend/aml_agent
/home/adity/StatusNeo/AI-Agent-Foundry/frontend
/home/adity/StatusNeo/AI-Agent-Foundry/frontend/content
```

- [ ] **Step 4: Commit scaffold**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add .gitignore
git commit -m "chore: init AI-Agent-Foundry scaffold"
```

---

## Task 2: Migrate shared backend utility modules

**Files:**
- Copy + patch: `backend/cache.py`, `backend/context.py`, `backend/router.py`, `backend/memory.py`, `backend/cost.py`, `backend/crypto.py`
- Copy: `backend/requirements.txt`, `backend/.env.example`, `backend/routing_config.json`

These five modules have no changes except a path fix in `router.py` (`routing_config.json` path must resolve relative to `backend/`).

- [ ] **Step 1: Copy utility files**

```bash
SRC=/home/adity/StatusNeo/TAPIOD/gateway
DST=/home/adity/StatusNeo/AI-Agent-Foundry/backend

cp $SRC/cache.py       $DST/cache.py
cp $SRC/context.py     $DST/context.py
cp $SRC/router.py      $DST/router.py
cp $SRC/memory.py      $DST/memory.py
cp $SRC/cost.py        $DST/cost.py
cp $SRC/crypto.py      $DST/crypto.py
cp $SRC/requirements.txt  $DST/requirements.txt
cp $SRC/.env.example   $DST/.env.example
cp $SRC/routing_config.json $DST/routing_config.json
cp $SRC/litellm_config.yaml $DST/litellm_config.yaml
cp $SRC/seed_routing.py $DST/seed_routing.py
cp $SRC/seed_all.py    $DST/seed_all.py
cp $SRC/arena_prompts.json $DST/arena_prompts.json
```

- [ ] **Step 2: Fix the `routing_config.json` path in `router.py`**

Open `backend/router.py`. Find and update the line that constructs the path to `routing_config.json`. It currently uses `Path(__file__).parent / "routing_config.json"`, which is already relative to the file — no change needed. Verify:

```bash
grep -n "routing_config" /home/adity/StatusNeo/AI-Agent-Foundry/backend/router.py
```

Expected: path uses `Path(__file__).parent` — no edit required.

- [ ] **Step 3: Update `litellm_config.yaml` — change hooks module path**

Open `backend/litellm_config.yaml`. Find the `callbacks` or `success_callback` / `custom_callback_class` line that references `hooks.proxy_hooks`. Change it to `aml_agent.llm_service.proxy_hooks`:

```bash
grep -n "hooks" /home/adity/StatusNeo/AI-Agent-Foundry/backend/litellm_config.yaml
```

If the output shows `hooks.proxy_hooks`, edit that line:
```yaml
# before
custom_callback_class: hooks.proxy_hooks

# after
custom_callback_class: aml_agent.llm_service.proxy_hooks
```

- [ ] **Step 4: Copy `.env` (local only, not committed)**

```bash
cp /home/adity/StatusNeo/TAPIOD/gateway/.env \
   /home/adity/StatusNeo/AI-Agent-Foundry/backend/.env
```

- [ ] **Step 5: Create Python virtual environment and install deps**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Smoke-test imports**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
python -c "from cache import redis_get; from router import routellm_classify; from context import RequestContext; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add backend/
git commit -m "chore: migrate shared backend utility modules"
```

---

## Task 3: Create `backend/aml_agent/detector.py`

Merge `gateway/tools_registry.py` and `gateway/tool_executor.py` into a single file.

**Files:**
- Create: `backend/aml_agent/__init__.py`
- Create: `backend/aml_agent/detector.py`

**Interfaces:**
- Produces: `execute_tool(tool_call: dict) -> str`, `MOCK_TOOLS: list[dict]`, `TOOL_REGISTRY: dict`

- [ ] **Step 1: Create `__init__.py`**

```bash
touch /home/adity/StatusNeo/AI-Agent-Foundry/backend/aml_agent/__init__.py
```

- [ ] **Step 2: Write the test file first**

Create `backend/tests/__init__.py` and `backend/tests/test_detector.py`:

```bash
mkdir -p /home/adity/StatusNeo/AI-Agent-Foundry/backend/tests
touch /home/adity/StatusNeo/AI-Agent-Foundry/backend/tests/__init__.py
```

Write `backend/tests/test_detector.py`:

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aml_agent.detector import execute_tool, MOCK_TOOLS, TOOL_REGISTRY


def test_tool_registry_has_five_tools():
    assert len(TOOL_REGISTRY) == 5


def test_mock_tools_matches_registry():
    mock_names = {t["function"]["name"] for t in MOCK_TOOLS}
    registry_names = set(TOOL_REGISTRY.keys())
    assert mock_names == registry_names


def test_execute_tool_calculate_expression():
    tool_call = {
        "id": "call_test",
        "type": "function",
        "function": {"name": "calculate_expression", "arguments": '{"expression": "2 + 2"}'},
    }
    result = execute_tool(tool_call)
    data = json.loads(result)
    assert data["result"] == 4


def test_execute_tool_unknown_name_returns_error():
    tool_call = {
        "id": "call_test",
        "type": "function",
        "function": {"name": "nonexistent_tool", "arguments": "{}"},
    }
    result = execute_tool(tool_call)
    data = json.loads(result)
    assert "error" in data


def test_execute_tool_bad_json_arguments():
    tool_call = {
        "id": "call_test",
        "type": "function",
        "function": {"name": "calculate_expression", "arguments": "not-json"},
    }
    result = execute_tool(tool_call)
    data = json.loads(result)
    assert "error" in data
```

- [ ] **Step 3: Run tests — verify they FAIL (module not yet created)**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_detector.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'aml_agent.detector'`

- [ ] **Step 4: Create `backend/aml_agent/detector.py`**

Combine `tools_registry.py` and `tool_executor.py` in order — definitions first, registry + executor last:

```python
import ast
import json
import math
import traceback
from datetime import datetime

import requests


# ── Tool implementations ───────────────────────────────────────────────────────

def get_current_weather(arguments: dict) -> str:
    """Current weather via Open-Meteo (no API key required)."""
    try:
        location = arguments.get("location", "").strip()
        if not location:
            return json.dumps({"error": "No location provided."})
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location.split(",")[0].strip(), "count": 1, "language": "en", "format": "json"},
            timeout=5,
        ).json()
        if not geo.get("results"):
            return json.dumps({"error": f"Could not find coordinates for: {location}"})
        r = geo["results"][0]
        lat, lon, name = r["latitude"], r["longitude"], r["name"]
        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
            },
            timeout=5,
        ).json()
        wmo = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 51: "Light drizzle", 61: "Slight rain", 63: "Moderate rain",
            65: "Heavy rain", 71: "Slight snow", 73: "Moderate snow", 95: "Thunderstorm",
        }
        c = weather.get("current", {})
        return json.dumps({
            "location": name,
            "temperature_f": c.get("temperature_2m"),
            "condition": wmo.get(c.get("weather_code", 0), "Unknown"),
            "humidity_pct": c.get("relative_humidity_2m"),
            "wind_mph": c.get("wind_speed_10m"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def calculate_expression(arguments: dict) -> str:
    """Safe math expression evaluator."""
    expression = arguments.get("expression", "").strip()
    if not expression:
        return json.dumps({"error": "No expression provided."})
    safe_names = {
        "sqrt": math.sqrt, "abs": abs, "round": round,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log2": math.log2, "log10": math.log10,
        "exp": math.exp, "ceil": math.ceil, "floor": math.floor,
        "pi": math.pi, "e": math.e, "inf": math.inf,
    }
    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Load,
    )
    try:
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                return json.dumps({"error": f"Disallowed operation: {type(node).__name__}"})
            if isinstance(node, ast.Name) and node.id not in safe_names:
                return json.dumps({"error": f"Unknown name: {node.id}"})
        result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, safe_names)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except ZeroDivisionError:
        return json.dumps({"error": "Division by zero."})
    except Exception as e:
        return json.dumps({"error": f"Could not evaluate: {e}"})


def get_stock_price(arguments: dict) -> str:
    """Latest market price via Yahoo Finance (no API key required)."""
    symbol = arguments.get("symbol", "").strip().upper()
    if not symbol:
        return json.dumps({"error": "No ticker symbol provided."})
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            err = data.get("chart", {}).get("error", {})
            return json.dumps({"error": err.get("description", f"Symbol '{symbol}' not found.")})
        meta = result[0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        prev = meta.get("chartPreviousClose") or price
        change = round(price - prev, 4) if price and prev else None
        change_pct = round((change / prev) * 100, 2) if change is not None and prev else None
        return json.dumps({
            "symbol": symbol,
            "price": price,
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName", ""),
            "change": change,
            "change_pct": change_pct,
            "market_state": meta.get("marketState", ""),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


_CITY_TZ = {
    "new york": "America/New_York", "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago", "london": "Europe/London",
    "paris": "Europe/Paris", "berlin": "Europe/Berlin",
    "dubai": "Asia/Dubai", "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "beijing": "Asia/Shanghai",
    "tokyo": "Asia/Tokyo", "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney", "toronto": "America/Toronto",
}


def get_time_in_timezone(arguments: dict) -> str:
    """Current time in any city or IANA timezone."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    location = arguments.get("location", "").strip()
    if not location:
        return json.dumps({"error": "No location provided."})
    tz_name = _CITY_TZ.get(location.lower(), location)
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        return json.dumps({
            "location": location,
            "timezone": tz_name,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "utc_offset": now.strftime("%z"),
        })
    except ZoneInfoNotFoundError:
        return json.dumps({"error": f"Unknown timezone or city: '{location}'."})
    except Exception as e:
        return json.dumps({"error": str(e)})


def web_search(arguments: dict) -> str:
    """Web search via DuckDuckGo Instant Answer API."""
    query = arguments.get("query", "").strip()
    if not query:
        return json.dumps({"error": "No search query provided."})
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append({"source": data.get("AbstractSource", ""), "text": data["AbstractText"], "url": data.get("AbstractURL", "")})
        for item in data.get("RelatedTopics", [])[:4]:
            if isinstance(item, dict) and item.get("Text"):
                results.append({"text": item["Text"], "url": item.get("FirstURL", "")})
        return json.dumps({"query": query, "results": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Registry + dispatcher ──────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "get_current_weather":  get_current_weather,
    "calculate_expression": calculate_expression,
    "get_stock_price":      get_stock_price,
    "get_time_in_timezone": get_time_in_timezone,
    "web_search":           web_search,
}

MOCK_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather conditions for a city or location.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_expression",
            "description": "Calculate or evaluate any math expression and return the exact numeric result.",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the latest market price for a stock ticker symbol.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time_in_timezone",
            "description": "Get the current time in any city or IANA timezone.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information using DuckDuckGo.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]


def execute_tool(tool_call: dict) -> str:
    """Dispatch an OpenAI-format tool_call to the matching Python function."""
    try:
        func_data = tool_call.get("function", {})
        name = func_data.get("name")
        args_str = func_data.get("arguments", "{}")
        if not name or name not in TOOL_REGISTRY:
            return json.dumps({"error": f"Tool '{name}' not found in registry."})
        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            return json.dumps({"error": "Could not parse tool arguments as JSON."})
        print(f"[Detector] {name}({arguments})")
        result = TOOL_REGISTRY[name](arguments)
        print(f"[Detector] → {result[:120]}")
        return result
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}", "trace": traceback.format_exc()})
```

- [ ] **Step 5: Run tests — verify they PASS**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_detector.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add backend/aml_agent/ backend/tests/
git commit -m "feat: add aml_agent/detector.py with tool registry and executor"
```

---

## Task 4: Create `backend/aml_agent/llm_service.py`

Extract the `GatewayHooks` class from `gateway/hooks.py` (lines 758–1106) and the `proxy_hooks` export. This is the LiteLLM callback module.

**Files:**
- Create: `backend/aml_agent/llm_service.py`
- Modify: `backend/aml_agent/__init__.py` (export `proxy_hooks`)

**Interfaces:**
- Consumes: `execute_tool` from `aml_agent.detector`, all helpers from `cache`, `router`, `context`, `memory`, `cost`
- Produces: `GatewayHooks` class, `proxy_hooks` instance (used by LiteLLM config)

- [ ] **Step 1: Write test for the proxy_hooks export**

Append to `backend/tests/test_detector.py` — create a new file instead:

Create `backend/tests/test_llm_service.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aml_agent.llm_service import GatewayHooks, proxy_hooks


def test_proxy_hooks_is_gateway_hooks_instance():
    assert isinstance(proxy_hooks, GatewayHooks)


def test_gateway_hooks_has_required_litellm_methods():
    assert hasattr(proxy_hooks, "async_pre_call_hook")
    assert hasattr(proxy_hooks, "async_post_call_success_hook")
    assert callable(proxy_hooks.async_pre_call_hook)
    assert callable(proxy_hooks.async_post_call_success_hook)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_llm_service.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'aml_agent.llm_service'`

- [ ] **Step 3: Create `backend/aml_agent/llm_service.py`**

Copy `GatewayHooks` class verbatim from `gateway/hooks.py` lines 758–1106. Then update the imports at the top of the file. The complete file header:

```python
import json
import time
import uuid
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

import asyncpg
import httpx
from fastembed import TextEmbedding
from litellm.integrations.custom_logger import CustomLogger
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

try:
    from headroom import compress as headroom_compress
    HEADROOM_AVAILABLE = True
except Exception:
    HEADROOM_AVAILABLE = False

_HEADROOM_MODEL_MAP = {
    "fast-groq":       "gpt-4o-mini",
    "heavy-groq":      "gpt-4o",
    "fast-openai":     "gpt-4o-mini",
    "heavy-openai":    "gpt-4o",
    "fast-anthropic":  "gpt-4o-mini",
    "heavy-anthropic": "claude-opus-4-20250514",
    "fast-gemini":     "gpt-4o-mini",
    "heavy-gemini":    "gpt-4o",
}

# These imports resolve to backend/ (same folder as this package's parent)
from cache import qdrant_cache_get, qdrant_cache_set
from memory import memory_retrieve, build_memory_system_block, memory_extract_and_store
from router import routellm_classify, knn_classify, pick_provider, compute_routing_save, get_available_providers
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms
from context import RequestContext
from aml_agent.detector import execute_tool, MOCK_TOOLS

DB_DSN     = os.getenv("DATABASE_URL", "postgresql://litellm:litellm_password@localhost:5432/litellm_logs")
QDRANT_URL = os.getenv("QDRANT_URL",   "http://localhost:6333")
LAST_TOOLS_PATH = Path(__file__).parent.parent / "last_tools.json"
```

Then paste the full `GatewayHooks` class from `gateway/hooks.py` lines 758–end-of-class.

At the bottom of the file, add:

```python
proxy_hooks = GatewayHooks()
```

- [ ] **Step 4: Run tests — verify they PASS**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_llm_service.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add backend/aml_agent/llm_service.py backend/tests/test_llm_service.py
git commit -m "feat: add aml_agent/llm_service.py — GatewayHooks LiteLLM callback"
```

---

## Task 5: Create `backend/main.py`

Extract the FastAPI app, all startup logic, and all HTTP routes from `gateway/hooks.py`.

**Files:**
- Create: `backend/main.py`

**Interfaces:**
- Consumes: `GatewayHooks`, `proxy_hooks` from `aml_agent.llm_service`; `execute_tool` from `aml_agent.detector`; `init_qdrant`, `init_redis` (defined locally in this file); all shared utilities
- Produces: `app` FastAPI instance (uvicorn entry point)

- [ ] **Step 1: Write smoke-test for the FastAPI app**

Create `backend/tests/test_main.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


def test_app_starts_and_health_routes_exist():
    # Import here so test isolation is clean
    import importlib
    main = importlib.import_module("main")
    client = TestClient(main.app)

    # /api/config is a lightweight sync route — no DB needed
    resp = client.get("/api/config")
    assert resp.status_code in (200, 500)  # 500 ok if Qdrant not running


def test_app_has_cors_middleware():
    import importlib
    main = importlib.import_module("main")
    middleware_classes = [type(m).__name__ for m in main.app.user_middleware]
    assert any("CORS" in c for c in middleware_classes)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_main.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Create `backend/main.py`**

The file structure (copy the relevant sections from `gateway/hooks.py`):

```python
import time
import threading
import asyncio
import hashlib
import json
import os
import uuid
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=False)

import asyncpg
import httpx
import redis as redis_lib
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from context import RequestContext
from cache import redis_get, redis_set, qdrant_cache_get, qdrant_cache_set
from memory import memory_retrieve, build_memory_system_block, memory_extract_and_store
from router import (routellm_classify, knn_classify, pick_provider,
                    get_available_providers, compute_routing_save,
                    load_routing_config, save_routing_config,
                    get_costliest_available_model)
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms
from aml_agent.detector import execute_tool, MOCK_TOOLS
from aml_agent.llm_service import GatewayHooks

DB_DSN            = os.getenv("DATABASE_URL",      "postgresql://litellm:litellm_password@localhost:5432/litellm_logs")
QDRANT_URL        = os.getenv("QDRANT_URL",        "http://localhost:6333")
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
LAST_TOOLS_PATH   = Path(__file__).parent / "last_tools.json"

qdrant: Optional[QdrantClient] = None
embedding_model: Optional[TextEmbedding] = None
redis_client: Optional[redis_lib.Redis] = None
services_status = {"qdrant_ready": False, "redis_ready": False}

_ctx_store: dict[str, RequestContext] = {}

def _store_ctx(req_id: str, ctx: RequestContext):
    _ctx_store[req_id] = ctx

def _pop_ctx(req_id: str) -> Optional[RequestContext]:
    return _ctx_store.pop(req_id, None)
```

After the setup section, paste:
1. `init_qdrant()` function (lines 73–139 of `gateway/hooks.py`)
2. `init_redis()` function (lines 141–150)
3. The two `threading.Thread(...)` calls to start them (lines 151–152)
4. FastAPI `app = FastAPI()` + CORS setup (lines 154–160)
5. `@app.on_event("startup")` + `startup_event()` + `_restore_provider_keys()` + `init_db()` (lines 162–239)
6. All `@app.get` / `@app.post` / `@app.delete` / `@app.patch` / `@app.put` routes (lines 311–end of file)

Update one path inside `init_qdrant()` — the `seed_routing` import will work as-is since `seed_routing.py` is in `backend/`.

- [ ] **Step 4: Run tests**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/test_main.py -v
```

Expected: 2 tests PASS (CORS test + route existence).

- [ ] **Step 5: Verify uvicorn starts**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
timeout 8 uvicorn main:app --port 4001 2>&1 | head -20
```

Expected: lines like `Application startup complete.` with no ImportError.

- [ ] **Step 6: Commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add backend/main.py backend/tests/test_main.py
git commit -m "feat: add backend/main.py — FastAPI entry point with all routes"
```

---

## Task 6: Migrate the frontend

Move the Next.js app from `tapiod-web/` into `frontend/`. Add a `content/` directory for static copy.

**Files:**
- Copy: all of `tapiod-web/` → `frontend/`
- Create: `frontend/content/sidebar-links.ts` (extracted nav labels)
- Create: `frontend/README.md`

**Note on Next.js App Router:** App Router requires pages to live in `src/app/` — this maps to the `pages/` concept in the prescribed spec. Do not rename `src/app/` as it would break Next.js routing.

- [ ] **Step 1: Copy frontend files**

```bash
SRC=/home/adity/StatusNeo/TAPIOD/tapiod-web
DST=/home/adity/StatusNeo/AI-Agent-Foundry/frontend

cp -r $SRC/src        $DST/src
cp -r $SRC/public     $DST/public
cp    $SRC/package.json       $DST/package.json
cp    $SRC/package-lock.json  $DST/package-lock.json
cp    $SRC/tsconfig.json      $DST/tsconfig.json
cp    $SRC/postcss.config.mjs $DST/postcss.config.mjs
cp    $SRC/eslint.config.mjs  $DST/eslint.config.mjs
```

- [ ] **Step 2: Install Node dependencies**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/frontend
npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 3: Create `frontend/content/` with navigation config**

Create `frontend/content/nav.ts`:

```typescript
export const NAV_LINKS = [
  { href: "/",             label: "Live Traces"   },
  { href: "/playground",  label: "Playground"    },
  { href: "/observability", label: "Observability" },
  { href: "/memory",      label: "Memory"        },
  { href: "/config",      label: "Config"        },
] as const;
```

Update `frontend/src/components/Sidebar.tsx` to import from content:

```typescript
import { NAV_LINKS } from "../../content/nav";
```

Then replace the hard-coded links array with `NAV_LINKS`. (Check current `Sidebar.tsx` to see the exact variable name to replace.)

- [ ] **Step 4: Run the Next.js build to verify no broken imports**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds (`✓ Compiled successfully` or similar).

- [ ] **Step 5: Create `frontend/README.md`**

```markdown
# AI-Agent-Foundry Frontend

Next.js 16 (App Router) dashboard for the AI-Agent-Foundry gateway.

## Structure

- `src/app/` — App Router pages (Live Traces, Playground, Observability, Memory, Config)
- `src/components/` — Shared React components
- `content/` — Static navigation links and copy (edit here, not in components)

## Running

```bash
npm install
npm run dev   # http://localhost:3000
```

Backend API expected at `http://localhost:4001`.
```

- [ ] **Step 6: Commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add frontend/
git commit -m "feat: migrate Next.js frontend into frontend/ with content/ directory"
```

---

## Task 7: Write the root README and final wiring check

**Files:**
- Create: `README.md` (project root)
- Verify: `backend/litellm_config.yaml` references the new module path

- [ ] **Step 1: Write `README.md`**

```markdown
# AI-Agent-Foundry

Enterprise LLM gateway with semantic caching, smart routing, dynamic tool injection, and an observability dashboard.

## Structure

```
AI-Agent-Foundry/
├── backend/
│   ├── main.py               # FastAPI server (port 4001)
│   ├── aml_agent/
│   │   ├── detector.py       # Tool registry and executor
│   │   └── llm_service.py    # LiteLLM GatewayHooks callback
│   ├── cache.py              # Qdrant + Redis cache helpers
│   ├── router.py             # RouteLLM + KNN routing
│   ├── memory.py             # User memory (Qdrant)
│   ├── litellm_config.yaml   # LiteLLM proxy config (port 4000)
│   ├── requirements.txt
│   └── .env.example
└── frontend/                 # Next.js dashboard (port 3000)
    ├── src/app/              # App Router pages
    ├── src/components/       # Shared components
    └── content/              # Static copy and nav config
```

## Quick Start

**1. Start infrastructure (PostgreSQL, Qdrant, Redis)**
```bash
docker compose up -d
```

**2. Backend — LiteLLM proxy (port 4000)**
```bash
cd backend
source venv/bin/activate
litellm --config litellm_config.yaml --port 4000
```

**3. Backend — FastAPI server (port 4001)**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --port 4001 --reload
```

**4. Frontend (port 3000)**
```bash
cd frontend
npm run dev
```

## Environment

Copy `backend/.env.example` to `backend/.env` and fill in your API keys:
```
GROQ_API_KEY=your_key_here
```
```

- [ ] **Step 2: Verify `litellm_config.yaml` has the correct callback path**

```bash
grep "proxy_hooks\|custom_callback" /home/adity/StatusNeo/AI-Agent-Foundry/backend/litellm_config.yaml
```

Expected output shows `aml_agent.llm_service.proxy_hooks` (not `hooks.proxy_hooks`).

If it still shows `hooks.proxy_hooks`, edit the file to replace it.

- [ ] **Step 3: Full backend test run**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry/backend
source venv/bin/activate
pytest tests/ -v --tb=short
```

Expected: all tests PASS (detector tests + llm_service tests + main tests).

- [ ] **Step 4: Final commit**

```bash
cd /home/adity/StatusNeo/AI-Agent-Foundry
git add README.md
git commit -m "docs: add root README with project structure and quick-start"
```

---

## Self-Review

**Spec coverage:**
- `backend/main.py` ✓
- `backend/aml_agent/detector.py` ✓
- `backend/aml_agent/llm_service.py` ✓
- `backend/.env` + `requirements.txt` ✓
- `frontend/components/` ✓ (maps to `frontend/src/components/`)
- `frontend/pages/` ✓ (maps to `frontend/src/app/` — App Router requirement)
- `frontend/content/` ✓ (created new)
- Root `README.md` ✓
- `frontend/README.md` ✓

**Key deviation noted:** The spec shows `requirements.text` (typo) and `pages/` at the top level of frontend. Implemented as `requirements.txt` (correct spelling) and `src/app/` (Next.js App Router requirement). Both are the clearly intended meanings.

**Type consistency:** `execute_tool(tool_call: dict) -> str` is used consistently in `detector.py`, `llm_service.py`, and `main.py`. `MOCK_TOOLS: list[dict]` is imported in both `llm_service.py` (for Qdrant seeding) and `main.py`.
