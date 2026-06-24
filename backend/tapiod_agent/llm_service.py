import json
import time
import uuid
import os
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

import asyncpg
import httpx
import redis as redis_lib
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

from cache import redis_get, redis_set, qdrant_cache_get, qdrant_cache_set
from memory import memory_retrieve, build_memory_system_block, memory_extract_and_store
from router import routellm_classify, knn_classify, pick_provider, compute_routing_save, get_available_providers, load_routing_config, get_costliest_available_model
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms
from context import RequestContext
from tapiod_agent.detector import execute_tool, MOCK_TOOLS

DB_DSN     = os.getenv("DATABASE_URL", "postgresql://litellm:litellm_password@localhost:5432/litellm_logs")
QDRANT_URL = os.getenv("QDRANT_URL",   "http://localhost:6333")
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://localhost:4000")
LAST_TOOLS_PATH = Path(__file__).parent.parent / "last_tools.json"

qdrant: Optional[QdrantClient] = None
embedding_model: Optional[TextEmbedding] = None
redis_client: Optional[redis_lib.Redis] = None
services_status = {"qdrant_ready": False, "redis_ready": False}

# Store RequestContext objects keyed by request ID to avoid JSON serialization issues
_ctx_store: dict[str, RequestContext] = {}

import threading
import time

def init_qdrant_proxy():
    global qdrant, embedding_model
    for attempt in range(12):
        try:
            print(f"[LiteLLM Proxy] Initializing Qdrant + FastEmbed (attempt {attempt+1})...")
            qdrant = QdrantClient(url=QDRANT_URL)
            embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            services_status["qdrant_ready"] = True
            print("[LiteLLM Proxy] Qdrant initialized successfully.")
            break
        except Exception as e:
            print(f"[LiteLLM Proxy] Qdrant init error: {e}. Retrying in 5s...")
            time.sleep(5)

def init_redis_proxy():
    global redis_client
    try:
        redis_client = redis_lib.Redis(host="localhost", port=6379, decode_responses=True)
        redis_client.ping()
        services_status["redis_ready"] = True
        print("[LiteLLM Proxy] Redis connected successfully.")
    except Exception as e:
        print(f"[LiteLLM Proxy] Redis connection failed: {e}")

threading.Thread(target=init_qdrant_proxy, daemon=True).start()
threading.Thread(target=init_redis_proxy, daemon=True).start()

def _store_ctx(req_id: str, ctx: RequestContext):
    _ctx_store[req_id] = ctx

def _pop_ctx(req_id: str) -> Optional[RequestContext]:
    return _ctx_store.pop(req_id, None)


class GatewayHooks(CustomLogger):
    def __init__(self):
        super().__init__()

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        if not messages:
            return data

        # --- Extract IDs ---
        api_key = (getattr(user_api_key_dict, "api_key", None)
                   or (user_api_key_dict.get("api_key", "") if isinstance(user_api_key_dict, dict) else ""))
        tenant_id = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "default_tenant"
        user_id = data.pop("user_id", None) or data.get("user") or tenant_id
        model = data.get("model", "heavy-groq")

        # --- Inject system prompt ---
        system_msg = {
            "role": "system",
            "content": (
                "You are TAPIOD, an advanced autonomous agent. You have dynamic access to "
                "external tools and real-time APIs. Trust your previous messages — if you "
                "fetched data via a tool in a prior turn, do not apologize for it."
            ),
        }
        if messages[0].get("role") != "system":
            messages.insert(0, system_msg)
        else:
            messages[0]["content"] = system_msg["content"] + "\n\n" + messages[0].get("content", "")

        prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""

        # --- Embed ONCE ---
        vec = []
        embed_ms = 0.0
        if qdrant is not None and embedding_model is not None and prompt:
            t0 = time.perf_counter()
            try:
                vec = list(embedding_model.embed([prompt]))[0].tolist()
                embed_ms = seconds_to_ms(time.perf_counter() - t0)
            except Exception:
                pass

        trace_id = (data.get("metadata") or {}).get("_tapiod_trace_id", "")
        ctx = RequestContext(
            prompt=prompt, messages=messages,
            tenant_id=tenant_id, user_id=user_id, vec=vec,
        )
        ctx._trace_id = trace_id
        if embed_ms > 0:
            ctx.record("embed", f"384-dim in {embed_ms:.1f}ms", embed_ms)
        else:
            ctx.record("embed", "skipped", 0.0)

        bypass_cache = data.get("metadata", {}).get("bypass_cache", False)
        if not vec:
            bypass_cache = True

        async def _write_cache_hit_trace(ctx: RequestContext):
            """Write trace to Postgres for cache hits.
            post_call_success_hook never fires for mock_response returns, so we write here."""
            ctx.compute_total_saved()
            latency = time.perf_counter() - ctx.req_start
            try:
                conn = await asyncpg.connect(DB_DSN)
                await conn.execute(
                    '''INSERT INTO requests_log
                       (timestamp, tenant_id, user_id, latency, model, provider,
                        tokens, prompt_tokens, completion_tokens, cost, actual_cost_usd,
                        cache_hit, cache_source, cache_saved_usd, routing_saved_usd,
                        memory_tokens_saved, total_saved_usd, blocked, pipeline_trace)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)''',
                    datetime.now(), ctx.tenant_id, ctx.user_id,
                    latency, "cached", ctx.cache_source,
                    0, 0, 0, 0.0, 0.0,
                    True, ctx.cache_source, ctx.cache_saved_usd, 0.0,
                    0, ctx.total_saved_usd, False,
                    json.dumps(ctx.pipeline_trace),
                )
                await conn.close()
            except Exception as e:
                print(f"DB log error (cache hit): {e}")

        # --- L1: Redis exact cache ---
        if not bypass_cache and services_status["redis_ready"] and redis_client:
            t0 = time.perf_counter()
            cached = redis_get(redis_client, tenant_id, messages)
            redis_ms = seconds_to_ms(time.perf_counter() - t0)
            if cached:
                ctx.cache_hit = True
                ctx.cache_source = "redis"
                ctx.cache_saved_usd = estimate_cache_save(
                    prompt,
                    baseline_model=get_costliest_available_model(get_available_providers()),
                )
                ctx.record("redis_cache", "HIT", redis_ms)
                asyncio.create_task(_write_cache_hit_trace(ctx))
                data["mock_response"] = json.loads(cached)
                data.setdefault("metadata", {})["_tapiod_req_id"] = trace_id
                data["tenant_id"] = tenant_id
                return data
            ctx.record("redis_cache", "miss", redis_ms)

        # --- L2: Qdrant semantic cache ---
        if not bypass_cache:
            config = load_routing_config()
            threshold = config.get("cache_similarity_threshold", 0.85)
            t0 = time.perf_counter()
            cached_text = qdrant_cache_get(qdrant, vec, tenant_id, threshold=threshold)
            qdrant_ms = seconds_to_ms(time.perf_counter() - t0)
            if cached_text:
                ctx.cache_hit = True
                ctx.cache_source = "qdrant"
                ctx.cache_saved_usd = estimate_cache_save(
                    prompt,
                    baseline_model=get_costliest_available_model(get_available_providers()),
                )
                ctx.record("qdrant_cache", "HIT", qdrant_ms)
                mock = {"choices": [{"message": {"role": "assistant", "content": cached_text}}],
                        "model": "cached", "usage": {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}}
                if services_status["redis_ready"] and redis_client:
                    redis_set(redis_client, tenant_id, messages, json.dumps(mock))
                asyncio.create_task(_write_cache_hit_trace(ctx))
                data["mock_response"] = mock
                data.setdefault("metadata", {})["_tapiod_req_id"] = trace_id
                data["tenant_id"] = tenant_id
                return data
            ctx.record("qdrant_cache", "miss", qdrant_ms)

        # --- Memory recall ---
        t0 = time.perf_counter()
        facts = memory_retrieve(qdrant, vec, user_id, tenant_id)
        mem_ms = seconds_to_ms(time.perf_counter() - t0)
        if facts:
            ctx.injected_memories = facts
            ctx.memory_tokens_saved = estimate_memory_tokens_saved(facts)
            block = build_memory_system_block(facts)
            messages[0]["content"] += block
            ctx.record("memory_recall", f"{len(facts)} facts recalled", mem_ms)
        else:
            ctx.record("memory_recall", "none", mem_ms)

        # --- RouteLLM MF routing (falls back to KNN if OpenAI key unavailable) ---
        t0 = time.perf_counter()
        complexity = routellm_classify(prompt, qdrant=qdrant, vec=vec)
        available = get_available_providers()
        chosen = pick_provider(available, complexity)
        route_ms = seconds_to_ms(time.perf_counter() - t0)
        ctx.complexity_score = complexity
        ctx.provider_model = chosen
        ctx.routing_saved_usd = compute_routing_save(
            chosen, available,
            int(len(prompt.split()) * 1.3), 150
        )
        ctx.record("knn_router", f"{chosen} (score {complexity:.2f})", route_ms)
        data["model"] = chosen

        # --- Headroom compression ---
        if HEADROOM_AVAILABLE:
            t0 = time.perf_counter()
            try:
                hr_model = _HEADROOM_MODEL_MAP.get(chosen, "gpt-4o")
                hr_result = headroom_compress(messages, model=hr_model)
                messages = hr_result.messages
                hr_ms = seconds_to_ms(time.perf_counter() - t0)
                if hr_result.tokens_saved > 0:
                    ctx.record("headroom", f"{hr_result.tokens_saved} tokens saved ({hr_result.compression_ratio:.0%})", hr_ms)
                else:
                    ctx.record("headroom", "no compression needed", hr_ms)
            except Exception as e:
                hr_ms = seconds_to_ms(time.perf_counter() - t0)
                ctx.record("headroom", f"skipped ({type(e).__name__})", hr_ms)

        # --- Tool selection ---
        t0 = time.perf_counter()
        try:
            tool_resp = qdrant.query_points(
                collection_name="tool_registry",
                query=vec,
                limit=3,
                score_threshold=0.58,
            )
            tools_to_inject = [json.loads(r.payload["tool_data"]) for r in tool_resp.points]
        except Exception:
            tools_to_inject = []
        tool_ms = seconds_to_ms(time.perf_counter() - t0)

        if tools_to_inject:
            ctx.injected_tools = tools_to_inject
            data["tools"] = tools_to_inject
            tool_names = [t["function"]["name"] for t in tools_to_inject]
            try:
                LAST_TOOLS_PATH.write_text(json.dumps({tenant_id: tool_names}))
            except Exception:
                pass
            ctx.record("tool_select", ", ".join(tool_names), tool_ms)
        else:
            ctx.record("tool_select", "none", tool_ms)

        _store_ctx(trace_id, ctx)
        data["messages"] = messages
        data["tenant_id"] = tenant_id
        data.setdefault("metadata", {})["_tapiod_req_id"] = trace_id
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        req_id = data.get("metadata", {}).get("_tapiod_req_id")
        ctx: Optional[RequestContext] = _ctx_store.get(req_id) if req_id else None
        if ctx is None:
            return response

        if isinstance(response, dict):
            response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            response_text = (response.choices[0].message.content
                             if hasattr(response, "choices") else "")

        if ctx.cache_hit:
            if isinstance(response, dict):
                response.setdefault("usage", {})
                response["usage"].update({"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0})
                response["model"] = "cached"
            if hasattr(response, "usage") and response.usage:
                response.usage.total_tokens = 0
                response.usage.prompt_tokens = 0
                response.usage.completion_tokens = 0

        ctx.compute_total_saved()

        trace_dict = ctx.to_trace_dict()
        if isinstance(response, dict):
            response["_tapiod_trace"] = trace_dict

        # Write trace to Redis side-channel for the agent endpoint (cross-process)
        trace_redis_id = (data.get("metadata") or {}).get("_tapiod_trace_id", "")
        if trace_redis_id and redis_client and services_status["redis_ready"]:
            try:
                redis_client.setex(f"tapiod:trace:{trace_redis_id}", 10, json.dumps(trace_dict))
            except Exception:
                pass

        async def _write_cache():
            if not ctx.cache_hit and response_text:
                qdrant_cache_set(qdrant, ctx.vec, ctx.tenant_id, ctx.prompt, response_text)
                if services_status["redis_ready"] and redis_client:
                    mock = {"choices": [{"message": {"role": "assistant", "content": response_text}}],
                            "model": "cached", "usage": {"total_tokens": 0}}
                    redis_set(redis_client, ctx.tenant_id, ctx.messages, json.dumps(mock))

        async def _write_memory():
            if not ctx.cache_hit and response_text:
                async def call_llm(messages, model="fast-groq"):
                    async with httpx.AsyncClient() as client:
                        r = await client.post(
                            f"{LITELLM_PROXY_URL}/v1/chat/completions",
                            json={"model": model, "messages": messages, "max_tokens": 100},
                            timeout=10.0,
                        )
                        return r.json()["choices"][0]["message"]["content"]
                await memory_extract_and_store(
                    qdrant, embedding_model, ctx.user_id, ctx.tenant_id,
                    ctx.prompt, response_text, call_llm,
                )

        asyncio.create_task(_write_cache())
        asyncio.create_task(_write_memory())

        # ── Write to DB from here (ctx is guaranteed non-None) ──────────────
        # async_log_success_event runs in LiteLLM internals and loses ctx
        # because the metadata injected by the pre_call hook doesn't survive
        # into that callback's kwargs. Post-call hook has data["metadata"] intact.
        usage = {}
        if isinstance(response, dict):
            usage = response.get("usage") or {}
        elif hasattr(response, "usage") and response.usage:
            usage = response.usage
        prompt_tokens = (getattr(usage, "prompt_tokens", None)
                         or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0))
        completion_tokens = (getattr(usage, "completion_tokens", None)
                             or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0))

        cache_hit    = ctx.cache_hit
        cache_source = ctx.cache_source or ""
        cache_saved  = ctx.cache_saved_usd or 0.0
        routing_saved = ctx.routing_saved_usd or 0.0
        total_saved  = ctx.total_saved_usd or 0.0
        mem_tokens   = ctx.memory_tokens_saved or 0
        provider_model = ctx.provider_model or "unknown"

        if cache_hit:
            prompt_tokens = 0
            completion_tokens = 0

        latency = time.perf_counter() - ctx.req_start

        async def _write_db():
            try:
                actual_cost = 0.0
                if not cache_hit and prompt_tokens + completion_tokens > 0:
                    try:
                        from litellm import cost_per_token as _cpt
                        from router import MODEL_MAP as _MODEL_MAP
                        m = _MODEL_MAP.get(provider_model, "groq/llama-3.1-8b-instant")
                        c_in, c_out = _cpt(model=m, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                        actual_cost = (c_in or 0.0) + (c_out or 0.0)
                    except Exception:
                        pass

                conn = await asyncpg.connect(DB_DSN)
                await conn.execute(
                    '''INSERT INTO requests_log
                       (timestamp, tenant_id, user_id, latency, model, provider,
                        tokens, prompt_tokens, completion_tokens, cost, actual_cost_usd,
                        cache_hit, cache_source, cache_saved_usd, routing_saved_usd,
                        memory_tokens_saved, total_saved_usd, blocked, pipeline_trace)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)''',
                    datetime.now(), ctx.tenant_id, ctx.user_id,
                    latency, provider_model,
                    provider_model.split("-")[1] if "-" in provider_model else "groq",
                    prompt_tokens + completion_tokens, prompt_tokens, completion_tokens,
                    actual_cost, actual_cost,
                    cache_hit, cache_source, cache_saved, routing_saved,
                    mem_tokens, total_saved, False,
                    json.dumps(ctx.pipeline_trace),
                )
                await conn.close()
            except Exception as e:
                print(f"DB log error (post_call): {e}")

        asyncio.create_task(_write_db())
        return response

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        # DB write happens in async_post_call_success_hook where ctx is always available.
        # This handler only back-fills response_cost from LiteLLM's built-in pricing.
        meta = kwargs.get("metadata") or {}
        req_id = meta.get("_tapiod_trace_id") or meta.get("_tapiod_req_id")
        ctx: Optional[RequestContext] = _ctx_store.get(req_id) if req_id else None
        if ctx is not None:
            ctx.actual_cost_usd = kwargs.get("response_cost", 0.0) or 0.0

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            conn = await asyncpg.connect(DB_DSN)
            await conn.execute(
                '''INSERT INTO requests_log
                   (timestamp, tenant_id, user_id, latency, model, cost, actual_cost_usd, blocked)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)''',
                datetime.now(), "unknown", "unknown", 0.0, "blocked", 0.0, 0.0, True,
            )
            await conn.close()
        except Exception:
            pass


proxy_hooks = GatewayHooks()
