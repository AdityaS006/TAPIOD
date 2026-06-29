import re
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

# Load .env before anything reads os.environ (e.g. FERNET_SECRET, API keys)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=False)

import asyncpg
import httpx
import redis as redis_lib
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

try:
    from headroom import compress as headroom_compress
    HEADROOM_AVAILABLE = True
except Exception:
    HEADROOM_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

# Map internal model aliases to names headroom knows for token counting
_HEADROOM_MODEL_MAP = {
    "fast-groq":       "gpt-4o-mini",
    "heavy-groq":      "gpt-4o",
    "fast-openai":     "gpt-4o-mini",
    "heavy-openai":    "gpt-4o",
    "fast-anthropic":  "gpt-4o-mini",            # no headroom Haiku support; gpt-4o-mini is similar size
    "heavy-anthropic": "claude-opus-4-20250514",
    "fast-gemini":     "gpt-4o-mini",            # no headroom Gemini support
    "heavy-gemini":    "gpt-4o",
}

from context import RequestContext
from cache import redis_get, redis_set, qdrant_cache_get, qdrant_cache_set
from memory import memory_retrieve, build_memory_system_block, memory_extract_and_store
from router import (routellm_classify, knn_classify, pick_provider,
                    get_available_providers, compute_routing_save,
                    load_routing_config, save_routing_config,
                    get_costliest_available_model)
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms
from tapiod_agent.detector import execute_tool, MOCK_TOOLS

DB_DSN            = os.getenv("DATABASE_URL",      "postgresql://litellm:litellm_password@localhost:5432/litellm_logs")
QDRANT_URL        = os.getenv("QDRANT_URL",        "http://localhost:6333")
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
LAST_TOOLS_PATH   = Path(__file__).parent / "last_tools.json"

qdrant: Optional[QdrantClient] = None
embedding_model: Optional[TextEmbedding] = None
redis_client: Optional[redis_lib.Redis] = None
services_status = {"qdrant_ready": False, "redis_ready": False}

# Store RequestContext objects keyed by request ID to avoid JSON serialization issues
_ctx_store: dict[str, RequestContext] = {}

def _store_ctx(req_id: str, ctx: RequestContext):
    _ctx_store[req_id] = ctx

def _pop_ctx(req_id: str) -> Optional[RequestContext]:
    return _ctx_store.pop(req_id, None)

def init_qdrant():
    global qdrant, embedding_model
    try:
        print("Initializing Qdrant + FastEmbed...")
        qdrant = QdrantClient(url=QDRANT_URL)
        embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

        for collection, size in [
            ("semantic_cache_384", 384),
            ("tool_registry", 384),
            ("user_memory", 384),
            ("routing_examples", 384),
        ]:
            try:
                qdrant.get_collection(collection)
                print(f"Collection '{collection}' exists.")
            except Exception:
                qdrant.create_collection(
                    collection,
                    vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                )
                print(f"Created collection '{collection}'.")

        # Seed routing_examples if empty
        if qdrant.count("routing_examples").count == 0:
            print("[Init] routing_examples is empty — seeding 50 labeled examples...")
            from seed_routing import FAST_EXAMPLES, HEAVY_EXAMPLES
            import uuid as _uuid2
            all_examples = [(p, "fast") for p in FAST_EXAMPLES] + [(p, "heavy") for p in HEAVY_EXAMPLES]
            prompts = [e[0] for e in all_examples]
            labels = [e[1] for e in all_examples]
            vecs = [v.tolist() for v in embedding_model.embed(prompts)]
            from qdrant_client.models import PointStruct as _PS
            points = [
                _PS(id=str(_uuid2.uuid4()), vector=vecs[i], payload={"label": labels[i], "prompt": prompts[i]})
                for i in range(len(prompts))
            ]
            qdrant.upsert(collection_name="routing_examples", points=points)
            print(f"[Init] routing_examples seeded with {len(points)} examples ({len(FAST_EXAMPLES)} fast, {len(HEAVY_EXAMPLES)} heavy).")
        else:
            print(f"[Init] routing_examples already has {qdrant.count('routing_examples').count} points.")

        # Seed tool_registry — re-seed whenever the count doesn't match MOCK_TOOLS
        from tapiod_agent.detector import MOCK_TOOLS
        tool_count = qdrant.count("tool_registry").count
        if tool_count != len(MOCK_TOOLS):
            print(f"Seeding tool_registry ({tool_count} → {len(MOCK_TOOLS)} tools)...")
            import uuid as _uuid
            qdrant.delete_collection("tool_registry")
            qdrant.create_collection(
                "tool_registry",
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            descs = [t["function"]["description"] for t in MOCK_TOOLS]
            vecs = [v.tolist() for v in embedding_model.embed(descs)]
            points = [
                PointStruct(id=str(_uuid.uuid4()), vector=vecs[i],
                            payload={"tool_data": json.dumps(MOCK_TOOLS[i])})
                for i in range(len(MOCK_TOOLS))
            ]
            qdrant.upsert(collection_name="tool_registry", points=points)
            print(f"Tool registry seeded with {len(MOCK_TOOLS)} tools.")

        services_status["qdrant_ready"] = True
        print("Qdrant initialized successfully.")
    except Exception as e:
        print(f"Qdrant init error: {e}")

def init_redis():
    global redis_client
    try:
        redis_client = redis_lib.Redis(host="localhost", port=6379, decode_responses=True)
        redis_client.ping()
        services_status["redis_ready"] = True
        print("Redis connected successfully.")
    except Exception as e:
        print(f"Redis connection failed: {e}")

threading.Thread(target=init_qdrant, daemon=True).start()
threading.Thread(target=init_redis, daemon=True).start()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_db()
    await _restore_provider_keys()


async def _restore_provider_keys():
    """On restart, reload encrypted API keys from Postgres into os.environ
    so LiteLLM and RouteLLM pick up the real keys without user re-entering them."""
    try:
        from crypto import decrypt_key
        conn = await asyncpg.connect(DB_DSN)
        rows = await conn.fetch(
            "SELECT provider, enc_key FROM provider_keys WHERE tenant_id = 'default_tenant'"
        )
        await conn.close()
        restored = []
        for row in rows:
            env_var = PROVIDER_ENV_MAP.get(row["provider"])
            if env_var:
                try:
                    os.environ[env_var] = decrypt_key(row["enc_key"])
                    restored.append(row["provider"])
                except Exception:
                    pass
        if restored:
            print(f"[Startup] Restored API keys for: {', '.join(restored)}")
    except Exception as e:
        print(f"[Startup] Could not restore provider keys: {e}")

async def init_db():
    try:
        conn = await asyncpg.connect(DB_DSN)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS requests_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                tenant_id VARCHAR(255),
                user_id VARCHAR(255),
                latency FLOAT NOT NULL,
                model VARCHAR(255) NOT NULL,
                provider VARCHAR(50),
                tokens INT DEFAULT 0,
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
            ALTER TABLE requests_log ADD COLUMN IF NOT EXISTS tokens INT DEFAULT 0;
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
        await conn.close()
        print("PostgreSQL Database Initialized Successfully!")
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")

def _error_response(message: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": message}, "finish_reason": "stop", "index": 0}],
            "model": "error", "usage": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}}

async def _run_agent_loop(payload: dict, trace_id: str) -> dict:
    """Run the full agent loop (tool detection + execution) and return the final response dict."""
    enriched = dict(payload)
    enriched.setdefault("metadata", {})["_tapiod_trace_id"] = trace_id
    # Always non-streaming internally so we can inspect tool_calls
    enriched.pop("stream", None)

    async with httpx.AsyncClient() as client:
        res1 = await client.post(f"{LITELLM_PROXY_URL}/v1/chat/completions", json=enriched, timeout=60.0)
        if res1.status_code != 200:
            print(f"[AgentLoop] LiteLLM returned {res1.status_code}: {res1.text[:300]}")
            # Groq/Llama models sometimes emit <function=NAME>{ARGS} instead of JSON tool calls.
            # LiteLLM wraps the Groq error — parse the nested JSON to extract failed_generation.
            failed_gen = ""
            try:
                err = res1.json()
                err_msg = err.get("error", {}).get("message", "")
                # LiteLLM format: "litellm.BadRequestError: GroqException - {JSON}"
                # err_msg can have extra fallback text after the JSON — use raw_decode
                # so it stops at the first complete JSON object instead of greedy-matching too much.
                groq_json_pos = err_msg.find("GroqException - {")
                if groq_json_pos != -1:
                    json_start = groq_json_pos + len("GroqException - ")
                    try:
                        groq_err, _ = json.JSONDecoder().raw_decode(err_msg, json_start)
                        failed_gen = groq_err.get("error", {}).get("failed_generation", "")
                    except Exception:
                        pass
            except Exception:
                pass

            func_match = re.search(r"<function=(\w+)>?\s*(\{[^<>]+\})", failed_gen) if failed_gen else None
            if func_match:
                fn_name = func_match.group(1)
                try:
                    fn_args = json.loads(func_match.group(2))
                except json.JSONDecodeError:
                    fn_args = {}
                print(f"[AgentLoop] Recovering from legacy <function=...> call: {fn_name}({fn_args})")
                tool_result = execute_tool({
                    "id": "call_legacy_0",
                    "type": "function",
                    "function": {"name": fn_name, "arguments": json.dumps(fn_args)},
                })
                messages = list(payload.get("messages", []))
                messages.append({
                    "role": "user",
                    "content": f"[{fn_name} returned: {tool_result}]\n\nUsing that information, please answer my question.",
                })
                retry_payload = dict(payload)
                retry_payload["messages"] = messages
                retry_payload.setdefault("metadata", {})["_tapiod_trace_id"] = trace_id
                retry_payload["metadata"]["bypass_tool_inject"] = True
                retry_payload.pop("stream", None)
                res1 = await client.post(
                    f"{LITELLM_PROXY_URL}/v1/chat/completions", json=retry_payload, timeout=60.0
                )
                if res1.status_code == 200:
                    data1 = res1.json()
                else:
                    return _error_response(f"[Tool retry error {res1.status_code}]")
            else:
                try:
                    err = res1.json()
                    msg = (err.get("error", {}).get("message", "")
                           or err.get("detail", "")
                           or f"Gateway error {res1.status_code}")
                except Exception:
                    msg = f"Gateway error {res1.status_code}"
                return _error_response(f"[Gateway error: {msg}]")
        else:
            data1 = res1.json()

        message = data1.get("choices", [{}])[0].get("message", {})

        if "tool_calls" in message and message["tool_calls"]:
            print(f"[AgentLoop] Intercepted Tool Calls from LLM: {message['tool_calls']}")
            messages = payload.get("messages", [])
            messages.append(message)

            for tool_call in message["tool_calls"]:
                tool_result = execute_tool(tool_call)
                messages.append({
                    "tool_call_id": tool_call.get("id", "call_xyz"),
                    "role": "tool",
                    "name": tool_call.get("function", {}).get("name", ""),
                    "content": tool_result
                })

            new_payload = dict(payload)
            new_payload["messages"] = messages
            new_payload.setdefault("metadata", {})["_tapiod_trace_id"] = trace_id
            new_payload["metadata"]["bypass_tool_inject"] = True
            new_payload.pop("stream", None)
            print(f"[AgentLoop] Sending Follow-Up Request to LLM with actual tool data...")
            res2 = await client.post(f"{LITELLM_PROXY_URL}/v1/chat/completions", json=new_payload, timeout=60.0)
            if res2.status_code != 200:
                print(f"[AgentLoop] Follow-up returned {res2.status_code}: {res2.text[:300]}")
                try:
                    err = res2.json()
                    msg = err.get("error", {}).get("message", "") or f"Tool follow-up error {res2.status_code}"
                except Exception:
                    msg = f"Tool follow-up error {res2.status_code}"
                return _error_response(f"[Tool error: {msg}]")
            data1 = res2.json()

    # Fetch pipeline trace from Redis side-channel
    if redis_client and services_status["redis_ready"]:
        for _ in range(20):
            raw = redis_client.get(f"tapiod:trace:{trace_id}")
            if raw:
                try:
                    trace = json.loads(raw)
                    data1["_tapiod_trace"] = trace
                    # LiteLLM overrides model field on mock_response; fix it here
                    if trace.get("cache_source"):
                        data1["model"] = "cached"
                        if isinstance(data1.get("usage"), dict):
                            data1["usage"] = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
                except Exception:
                    pass
                redis_client.delete(f"tapiod:trace:{trace_id}")
                break
            await asyncio.sleep(0.05)

    return data1


@app.post("/api/agent/chat/completions")
async def agent_chat_completions(payload: dict):
    trace_id = str(uuid.uuid4())
    want_stream = bool(payload.get("stream", False))

    try:
        data = await _run_agent_loop(payload, trace_id)
    except httpx.TimeoutException:
        data = _error_response("[Gateway timeout — the LLM took too long to respond]")
    except httpx.ConnectError:
        data = _error_response("[Cannot reach LiteLLM proxy — is it running on port 4000?]")
    except Exception as e:
        print(f"[AgentLoop] Unexpected error: {e}")
        data = _error_response(f"[Internal error: {type(e).__name__}]")

    if not want_stream:
        return data

    # Stream the final content as SSE so CLI clients get token-by-token output
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    trace = data.get("_tapiod_trace")

    async def _sse():
        # Yield content word-by-word so the terminal feels live
        words = content.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            chunk = {
                "choices": [{"delta": {"content": token}, "finish_reason": None, "index": 0}]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0)  # yield control to event loop

        yield "data: [DONE]\n\n"

        if trace:
            yield f"data: [TRACE]{json.dumps(trace)}\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")

@app.get("/api/chats")
async def get_chats(user_id: str, tenant_id: str):
    try:
        conn = await asyncpg.connect(DB_DSN)
        rows = await conn.fetch('''
            SELECT id, title, updated_at, messages
            FROM chat_sessions
            WHERE user_id = $1 AND tenant_id = $2
            ORDER BY updated_at DESC
        ''', user_id, tenant_id)
        await conn.close()

        sessions = []
        for r in rows:
            sessions.append({
                "id": r["id"],
                "title": r["title"],
                "updatedAt": r["updated_at"].timestamp() * 1000,
                "messages": json.loads(r["messages"])
            })
        return sessions
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/chats")
async def save_chat(session: dict):
    try:
        conn = await asyncpg.connect(DB_DSN)
        await conn.execute('''
            INSERT INTO chat_sessions (id, tenant_id, user_id, title, updated_at, messages)
            VALUES ($1, $2, $3, $4, to_timestamp($5), $6)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = EXCLUDED.updated_at,
                messages = EXCLUDED.messages
        ''', session["id"], session["tenant_id"], session["user_id"], session["title"],
             session["updatedAt"] / 1000.0, json.dumps(session["messages"]))
        await conn.close()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/chats/{session_id}")
async def delete_chat(session_id: str, user_id: str, tenant_id: str):
    try:
        conn = await asyncpg.connect(DB_DSN)
        await conn.execute('''
            DELETE FROM chat_sessions
            WHERE id = $1 AND user_id = $2 AND tenant_id = $3
        ''', session_id, user_id, tenant_id)
        await conn.close()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

# ── /api/extract ─────────────────────────────────────────────────────────────

def _is_tool_def(data: object) -> bool:
    """Return True if data looks like an OpenAI tool-definition schema."""
    if isinstance(data, dict):
        return "name" in data and "parameters" in data
    if isinstance(data, list) and len(data) > 0:
        return all(isinstance(item, dict) and "name" in item and "parameters" in item for item in data)
    return False


def _to_toon(data: object) -> str:
    """Stub: pretty-print JSON with a # TOON header. Real converter is a drop-in replacement."""
    return "# TOON\n" + json.dumps(data, indent=2)


@app.post("/api/extract")
async def extract_file(file: UploadFile = File(...)):
    """Extract text from uploaded files. Handles PDF, JSON, text/code, and unknown binary."""
    raw = await file.read()
    mime = file.content_type or ""
    filename = file.filename or ""

    # ── PDF ──────────────────────────────────────────────────────────────────
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        if not PDFPLUMBER_AVAILABLE:
            return JSONResponse({"error": "PDF extraction not available (pdfplumber missing)"}, status_code=422)
        try:
            import io
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n\n".join(p for p in pages if p.strip())
            if not text.strip():
                return JSONResponse({"error": "PDF contained no extractable text"}, status_code=422)
            return {"text": text, "toon_available": False, "toon": None}
        except Exception as e:
            return JSONResponse({"error": f"PDF extraction failed: {type(e).__name__}"}, status_code=422)

    # ── JSON ─────────────────────────────────────────────────────────────────
    if mime in ("application/json", "text/json") or filename.lower().endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=422)
        if _is_tool_def(data):
            toon = _to_toon(data)
            return {"text": json.dumps(data, indent=2), "toon_available": True, "toon": toon}
        return {"text": json.dumps(data, indent=2), "toon_available": False, "toon": None}

    # ── Text / code (safety net) ──────────────────────────────────────────────
    if mime.startswith("text/"):
        try:
            return {"text": raw.decode("utf-8"), "toon_available": False, "toon": None}
        except UnicodeDecodeError:
            return JSONResponse({"error": "Could not decode file as UTF-8"}, status_code=422)

    # ── Unknown binary ────────────────────────────────────────────────────────
    return JSONResponse({"error": "Unsupported file type"}, status_code=422)


@app.get("/api/last_tools")
async def get_last_tools(tenant_id: str = "default_tenant"):
    try:
        with open(LAST_TOOLS_PATH, "r") as f:
            data = json.load(f)
            tools = data.get(tenant_id)
            if tools is None:
                tools = data.get("default_tenant", [])
            return {"tools": tools}
    except Exception as e:
        return {"tools": [], "error": str(e)}

@app.get("/api/metrics")
async def get_metrics(time_range: str = "24h"):
    try:
        conn = await asyncpg.connect(DB_DSN)

        interval = "1 day"
        if time_range == "7d": interval = "7 days"
        elif time_range == "30d": interval = "30 days"

        stats = await conn.fetchrow(f'''
            SELECT COUNT(*) as total_requests,
                   COUNT(*) FILTER (WHERE cache_hit = TRUE) as cache_hits,
                   COUNT(*) FILTER (WHERE blocked = TRUE) as blocked_requests,
                   SUM(cost) as total_cost,
                   AVG(latency) as avg_latency
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL '{interval}'
        ''')

        recent = await conn.fetch('''
            SELECT timestamp, latency, model, cost, tokens
            FROM requests_log
            ORDER BY timestamp DESC
            LIMIT 20
        ''')

        await conn.close()

        total = stats['total_requests'] or 0
        cache_hits = stats['cache_hits'] or 0
        blocked = stats['blocked_requests'] or 0
        cost = stats['total_cost'] or 0.0
        avg_latency = stats['avg_latency'] or 0.0

        recent_requests = [
            {
                "time": r['timestamp'].strftime("%H:%M:%S"),
                "latency": round(r['latency'], 2),
                "model": r['model'],
                "cost": r['cost'],
                "tokens": r['tokens']
            } for r in reversed(recent)
        ]

        return {
            "total_requests": total,
            "cache_hits": cache_hits,
            "blocked_requests": blocked,
            "total_cost": cost,
            "avg_latency_ms": round(avg_latency * 1000, 2),
            "recent_requests": recent_requests
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/observability")
async def get_observability(time_range: str = "24h"):
    try:
        conn = await asyncpg.connect(DB_DSN)

        interval = "1 day"
        if time_range == "7d": interval = "7 days"
        elif time_range == "30d": interval = "30 days"

        rows = await conn.fetch(f'''
            SELECT date_trunc('minute', timestamp) as minute,
                   model,
                   AVG(latency) as avg_lat,
                   COUNT(*) as count
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL '{interval}'
            GROUP BY 1, 2
            ORDER BY 1 ASC
        ''')

        routing_stats = await conn.fetch(f'''
            SELECT model, COUNT(*) as c
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL '{interval}'
              AND cache_hit = FALSE
              AND blocked = FALSE
            GROUP BY model
        ''')

        cache_stats = await conn.fetchrow(f'''
            SELECT COUNT(*) FILTER (WHERE cache_hit = TRUE) as hits,
                   COUNT(*) FILTER (WHERE blocked = TRUE) as blocks
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL '{interval}'
        ''')

        await conn.close()

        grouped = {}
        now = datetime.now()
        for i in range(5, -1, -1):
            t = (now - timedelta(minutes=i)).strftime("%H:%M")
            grouped[t] = {"time": t, "fast": 0, "heavy": 0, "fast_count": 0, "heavy_count": 0}

        for r in rows:
            t = r['minute'].strftime("%H:%M")
            if t not in grouped:
                grouped[t] = {"time": t, "fast": 0, "heavy": 0, "fast_count": 0, "heavy_count": 0}

            is_heavy = "heavy" in r['model'] or "70b" in r['model'] or "gpt-4o" in r['model']
            if is_heavy:
                grouped[t]["heavy"] += r['avg_lat'] * 1000 * r['count']
                grouped[t]["heavy_count"] += r['count']
            else:
                grouped[t]["fast"] += r['avg_lat'] * 1000 * r['count']
                grouped[t]["fast_count"] += r['count']

        latency_data = []
        for t, data in sorted(grouped.items()):
            f_avg = data["fast"] / data["fast_count"] if data["fast_count"] > 0 else 0
            h_avg = data["heavy"] / data["heavy_count"] if data["heavy_count"] > 0 else 0
            latency_data.append({
                "time": data["time"],
                "fast": round(f_avg),
                "heavy": round(h_avg)
            })

        routing_data = [{"name": r['model'], "value": r['c']} for r in routing_stats if r['c'] > 0]
        if cache_stats and cache_stats['hits'] > 0:
            routing_data.append({"name": "Cache Hit", "value": cache_stats['hits']})
        if cache_stats and cache_stats['blocks'] > 0:
            routing_data.append({"name": "Blocked", "value": cache_stats['blocks']})

        return {
            "latencyData": latency_data,
            "routingData": routing_data
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/config")
def get_config():
    config_path = Path(__file__).parent / "litellm_config.yaml"
    models = []
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            for i, m in enumerate(config.get("model_list", [])):
                models.append({
                    "id": i + 1,
                    "alias": m.get("model_name"),
                    "actual": m.get("litellm_params", {}).get("model", ""),
                    "provider": "Groq" if "groq" in m.get("litellm_params", {}).get("model", "") else "OpenAI",
                    "tier": "Heavy" if "heavy" in m.get("model_name") else "Fast"
                })
    except Exception as e:
        print("Error reading config:", e)

    providers = []
    pid = 1
    try:
        with open(_ENV_FILE, "r") as f:
            for line in f.readlines():
                if "=" in line and "_API_KEY" in line and not line.strip().startswith("#"):
                    key_name = line.split("=")[0].strip()
                    val = line.split("=")[1].strip()
                    if val:
                        providers.append({
                            "id": pid,
                            "name": key_name.replace("_API_KEY", "").capitalize(),
                            "apiKey": "sk-" + key_name.replace("_API_KEY", "").lower() + "-**********************",
                            "status": "active"
                        })
                        pid += 1
    except FileNotFoundError:
        pass

    return {"models": models, "providers": providers, "routing_status": services_status.get("qdrant_ready", False)}


class ModelReq(BaseModel):
    alias: str
    actual: str
    provider: str

@app.post("/api/config/model")
def add_model(req: ModelReq):
    config_path = Path(__file__).parent / "litellm_config.yaml"
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        if "model_list" not in config:
            config["model_list"] = []

        api_key_env = f"os.environ/{req.provider.upper()}_API_KEY"

        config["model_list"].append({
            "model_name": req.alias,
            "litellm_params": {
                "model": req.actual,
                "api_key": api_key_env
            }
        })

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        return {"status": "success"}
    except Exception as e:
        print("Error saving model:", e)
        return {"status": "error", "message": str(e)}

@app.delete("/api/config/model/{alias}")
def delete_model(alias: str):
    config_path = Path(__file__).parent / "litellm_config.yaml"
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        if "model_list" in config:
            config["model_list"] = [m for m in config["model_list"] if m.get("model_name") != alias]

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

        return {"status": "success"}
    except Exception as e:
        print("Error deleting model:", e)
        return {"status": "error", "message": str(e)}

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


_ENV_FILE = Path(__file__).parent / ".env"


def _write_to_env_file(env_name: str, value: str) -> None:
    try:
        lines = _ENV_FILE.read_text().splitlines(keepends=True) if _ENV_FILE.exists() else []
    except OSError:
        lines = []
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{env_name}="):
            new_lines.append(f"{env_name}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{env_name}={value}\n")
    _ENV_FILE.write_text("".join(new_lines))


def _remove_from_env_file(env_name: str) -> None:
    if not _ENV_FILE.exists():
        return
    lines = _ENV_FILE.read_text().splitlines(keepends=True)
    _ENV_FILE.write_text("".join(l for l in lines if not l.startswith(f"{env_name}=")))


async def _reload_litellm() -> None:
    """Restart the LiteLLM proxy process so it re-reads .env with the new key."""
    import signal as _signal
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "litellm.*--config"],
            capture_output=True, text=True,
        )
        pids = [int(p) for p in result.stdout.split() if p.strip()]
        for pid in pids:
            os.kill(pid, _signal.SIGTERM)
        await asyncio.sleep(2.0)
        gateway_dir = str(Path(__file__).parent)
        litellm_bin = str(Path(__file__).parent / "venv" / "bin" / "litellm")
        config_path = str(Path(__file__).parent / "litellm_config.yaml")
        subprocess.Popen(
            [litellm_bin, "--config", config_path, "--port", "4000"],
            stdout=open("/tmp/litellm.log", "a"),
            stderr=subprocess.STDOUT,
            cwd=gateway_dir,
        )
    except Exception as e:
        print(f"[reload_litellm] {e}")


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
        _write_to_env_file(env_var, req.key)
    asyncio.create_task(_reload_litellm())
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
    if env_var:
        if env_var in os.environ:
            del os.environ[env_var]
        _remove_from_env_file(env_var)
    asyncio.create_task(_reload_litellm())
    return {"status": "ok"}


# Uvicorn server is now launched independently via CLI.

@app.get("/api/traces")
async def get_traces(limit: int = 20, tenant_id: str = None):
    try:
        conn = await asyncpg.connect(DB_DSN)
        if tenant_id:
            rows = await conn.fetch(
                '''SELECT id, timestamp, model, actual_cost_usd, total_saved_usd,
                          cache_source, pipeline_trace, memory_tokens_saved
                   FROM requests_log WHERE tenant_id = $1
                   ORDER BY timestamp DESC LIMIT $2''',
                tenant_id, limit
            )
        else:
            rows = await conn.fetch(
                '''SELECT id, timestamp, model, actual_cost_usd, total_saved_usd,
                          cache_source, pipeline_trace, memory_tokens_saved
                   FROM requests_log ORDER BY timestamp DESC LIMIT $1''',
                limit
            )
        await conn.close()
        traces = []
        for r in rows:
            pipeline = json.loads(r["pipeline_trace"]) if r["pipeline_trace"] else []
            traces.append({
                "id": r["id"],
                "timestamp": r["timestamp"].strftime("%H:%M:%S"),
                "model": r["model"],
                "actual_cost_usd": r["actual_cost_usd"] or 0.0,
                "total_saved_usd": r["total_saved_usd"] or 0.0,
                "cache_source": r["cache_source"] or None,
                "memory_tokens_saved": r["memory_tokens_saved"] or 0,
                "pipeline": pipeline,
            })
        return {"traces": traces}
    except Exception as e:
        return {"traces": [], "error": str(e)}


@app.get("/api/savings")
async def get_savings(time_range: str = "24h"):
    try:
        conn = await asyncpg.connect(DB_DSN)
        interval = {"24h": "1 day", "7d": "7 days", "30d": "30 days"}.get(time_range, "1 day")
        row = await conn.fetchrow(f'''
            SELECT
                COALESCE(SUM(actual_cost_usd), 0) AS actual,
                COALESCE(SUM(total_saved_usd), 0) AS saved,
                COALESCE(SUM(cache_saved_usd), 0) AS cache_saved,
                COALESCE(SUM(routing_saved_usd), 0) AS routing_saved,
                COALESCE(SUM(memory_tokens_saved), 0) AS mem_tokens,
                COUNT(*) FILTER (WHERE cache_source = 'redis') AS redis_hits,
                COUNT(*) FILTER (WHERE cache_source = 'qdrant') AS qdrant_hits
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL \'{interval}\'
        ''')
        await conn.close()
        actual = float(row["actual"])
        saved = float(row["saved"])
        baseline = actual + saved
        pct = round((saved / baseline * 100) if baseline > 0 else 0, 1)
        return {
            "actual_cost_usd": round(actual, 6),
            "total_saved_usd": round(saved, 6),
            "baseline_usd": round(baseline, 6),
            "savings_pct": pct,
            "cache_saved_usd": round(float(row["cache_saved"]), 6),
            "routing_saved_usd": round(float(row["routing_saved"]), 6),
            "memory_tokens_saved": int(row["mem_tokens"]),
            "cache_hits_redis": int(row["redis_hits"]),
            "cache_hits_qdrant": int(row["qdrant_hits"]),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/routing-stats")
async def get_routing_stats(time_range: str = "24h"):
    try:
        conn = await asyncpg.connect(DB_DSN)
        interval = {"24h": "1 day", "7d": "7 days", "30d": "30 days"}.get(time_range, "1 day")
        rows = await conn.fetch(f'''
            SELECT model, COUNT(*) as cnt, COALESCE(SUM(actual_cost_usd), 0) as cost
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL \'{interval}\'
              AND cache_hit = FALSE AND blocked = FALSE
            GROUP BY model
        ''')
        total_row = await conn.fetchrow(f'''
            SELECT COALESCE(SUM(actual_cost_usd), 0) AS actual,
                   COALESCE(SUM(total_saved_usd), 0) AS saved
            FROM requests_log
            WHERE timestamp >= NOW() - INTERVAL \'{interval}\'
        ''')
        await conn.close()

        total_requests = sum(r["cnt"] for r in rows)
        distribution = [
            {
                "provider": r["model"],
                "count": r["cnt"],
                "pct": round(r["cnt"] / total_requests * 100) if total_requests > 0 else 0,
                "cost": round(float(r["cost"]), 6),
            }
            for r in rows
        ]
        actual = float(total_row["actual"])
        saved = float(total_row["saved"])
        baseline = actual + saved

        try:
            examples_count = qdrant.count("routing_examples").count if qdrant else 0
        except Exception:
            examples_count = 0

        return {
            "distribution": distribution,
            "baseline_usd": round(baseline, 6),
            "actual_usd": round(actual, 6),
            "arbitrage_saved_usd": round(saved, 6),
            "routing_examples_count": examples_count,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/memory")
async def list_memories(user_id: str, tenant_id: str):
    if qdrant is None:
        return {"memories": [], "error": "Qdrant not ready"}
    try:
        results = qdrant.scroll(
            collection_name="user_memory",
            scroll_filter=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            ]),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        memories = []
        now = int(time.time())
        for point in results[0]:
            ts = point.payload.get("timestamp", 0)
            age_s = now - ts
            if age_s < 3600:
                age_str = f"{age_s // 60}m ago"
            elif age_s < 86400:
                age_str = f"{age_s // 3600}h ago"
            else:
                age_str = f"{age_s // 86400}d ago"
            memories.append({
                "id": str(point.id),
                "fact": point.payload.get("fact", ""),
                "timestamp": ts,
                "age": age_str,
            })
        memories.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"memories": memories}
    except Exception as e:
        return {"memories": [], "error": str(e)}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    if qdrant is None:
        return {"status": "error", "error": "Qdrant not ready"}
    try:
        qdrant.delete(collection_name="user_memory", points_selector=[memory_id])
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory")
async def wipe_memory(user_id: str, tenant_id: str):
    if qdrant is None:
        return {"status": "error", "error": "Qdrant not ready"}
    try:
        qdrant.delete(
            collection_name="user_memory",
            points_selector=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            ]),
        )
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/config/tiers")
def get_tiers():
    return load_routing_config()


@app.patch("/api/config/thresholds")
def update_thresholds(body: dict):
    config = load_routing_config()
    if "complexity_threshold" in body:
        config["complexity_threshold"] = float(body["complexity_threshold"])
    if "cache_similarity_threshold" in body:
        config["cache_similarity_threshold"] = float(body["cache_similarity_threshold"])
    if "cache_ttl_seconds" in body:
        config["cache_ttl_seconds"] = int(body["cache_ttl_seconds"])
    save_routing_config(config)
    return config


class TierModelReq(BaseModel):
    alias: str
    actual: str
    provider: str
    cost_per_m: float
    tier: str


@app.post("/api/config/tiers")
def add_tier_model(req: TierModelReq):
    config = load_routing_config()
    if req.tier not in config["tiers"]:
        config["tiers"][req.tier] = []
    if req.alias not in config["tiers"][req.tier]:
        config["tiers"][req.tier].append(req.alias)
    save_routing_config(config)
    return config


@app.delete("/api/config/tiers/{alias}")
def remove_tier_model(alias: str):
    config = load_routing_config()
    for tier in config["tiers"].values():
        if alias in tier:
            tier.remove(alias)
    save_routing_config(config)
    return config


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

