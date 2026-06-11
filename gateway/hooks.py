import time
import threading
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from litellm.integrations.custom_logger import CustomLogger
from dotenv import load_dotenv
from typing import Dict, Any, List
import asyncpg
import sys
import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding
import json
from tool_executor import execute_tool
from pydantic import BaseModel
import os
import yaml

DB_DSN = "postgresql://litellm:litellm_password@localhost:5432/litellm_logs"

# Global Real-time service statuses
services_status = {
    "routellm_ready": False
}

last_injected_tools_by_tenant = {}

routellm_client = None

from qdrant_client import QdrantClient
from litellm import embedding

# Qdrant Semantic Cache Initialization (Moved to Phase 4)
qdrant = None
embedding_model = None

def init_qdrant():
    global qdrant
    global embedding_model
    try:
        print("Initializing Qdrant Semantic Cache (FastEmbed)...")
        qdrant = QdrantClient(url="http://localhost:6333")
        print("Downloading/Loading FastEmbed model...")
        embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        try:
            qdrant.get_collection("semantic_cache_384")
        except:
            qdrant.create_collection("semantic_cache_384", vectors_config={"size": 384, "distance": "Cosine"})
        print("Qdrant Semantic Cache Initialized Successfully!")

        try:
            qdrant.get_collection("tool_registry")
            print("Tool registry collection already exists.")
        except:
            print("Creating tool registry and embedding 100 mock tools...")
            qdrant.create_collection("tool_registry", vectors_config={"size": 384, "distance": "Cosine"})
            from tools_registry import MOCK_TOOLS
            import uuid
            
            tool_descriptions = [t["function"]["description"] for t in MOCK_TOOLS]
            embeddings_gen = embedding_model.embed(tool_descriptions)
            vecs = [vec.tolist() for vec in embeddings_gen]
            
            points = []
            for i, tool in enumerate(MOCK_TOOLS):
                points.append({
                    "id": str(uuid.uuid4()),
                    "vector": vecs[i],
                    "payload": {
                        "tool_data": json.dumps(tool)
                    }
                })
            
            qdrant.upsert(
                collection_name="tool_registry",
                points=points
            )
            print("100 mock tools successfully embedded and inserted into Qdrant!")
    except Exception as e:
        print(f"Qdrant/FastEmbed Initialization Error: {e}")

threading.Thread(target=init_qdrant, daemon=True).start()

async def init_db():
    try:
        conn = await asyncpg.connect(DB_DSN)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS requests_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                latency FLOAT NOT NULL,
                model VARCHAR(255) NOT NULL,
                cost FLOAT NOT NULL,
                tokens INT NOT NULL,
                cache_hit BOOLEAN DEFAULT FALSE,
                blocked BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(255) PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                messages JSONB NOT NULL
            );
        ''')
        await conn.close()
        print("PostgreSQL Database Initialized Successfully!")
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")

def init_routellm():
    global routellm_client
    try:
        from routellm.controller import Controller
        print("Initializing RouteLLM Controller in background...")
        routellm_client = Controller(
            routers=["mf"],
            strong_model="heavy-model",
            weak_model="fast-model"
        )
        print("RouteLLM Controller initialized and loaded into memory!")
        services_status["routellm_ready"] = True
    except Exception as e:
        print(f"Failed to initialize RouteLLM: {e}")

threading.Thread(target=init_routellm, daemon=True).start()

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

@app.post("/api/agent/chat/completions")
async def agent_chat_completions(payload: dict):
    # This is the Multi-Turn Tool Execution Loop!
    async with httpx.AsyncClient() as client:
        # Step 1: Forward the original payload to LiteLLM (Port 4000)
        # LiteLLM handles the semantic cache, dynamic tool injection, and hitting Groq.
        res1 = await client.post("http://localhost:4000/v1/chat/completions", json=payload, timeout=60.0)
        if res1.status_code != 200:
            return res1.json()
            
        data1 = res1.json()
        message = data1.get("choices", [{}])[0].get("message", {})
        
        # Step 2: Check if LLM requested a Tool Call
        if "tool_calls" in message and message["tool_calls"]:
            # Print to logs so we can see the loop in action
            print(f"[AgentLoop] Intercepted Tool Calls from LLM: {message['tool_calls']}")
            
            # Step 3: Execute the tools!
            messages = payload.get("messages", [])
            messages.append(message) # Append the assistant's tool call request
            
            for tool_call in message["tool_calls"]:
                tool_result = execute_tool(tool_call)
                # Step 4: Append the real-world result as a "tool" role message
                messages.append({
                    "tool_call_id": tool_call.get("id", "call_xyz"),
                    "role": "tool",
                    "name": tool_call.get("function", {}).get("name", ""),
                    "content": tool_result
                })
            
            # Step 5: Second call to LiteLLM with the live data!
            new_payload = payload.copy()
            new_payload["messages"] = messages
            print(f"[AgentLoop] Sending Follow-Up Request to LLM with actual tool data...")
            res2 = await client.post("http://localhost:4000/v1/chat/completions", json=new_payload, timeout=60.0)
            return res2.json()
            
        # If no tool calls, just return the final text
        return data1

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

@app.get("/api/last_tools")
async def get_last_tools(tenant_id: str = "default_tenant"):
    try:
        with open(r"c:\Coding\TAPIOD\gateway\last_tools.json", "r") as f:
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
    config_path = "litellm_config.yaml"
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
        with open(".env", "r") as f:
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
            
    return {"models": models, "providers": providers, "routellm_status": services_status["routellm_ready"]}

class ProviderReq(BaseModel):
    name: str
    apiKey: str

@app.post("/api/config/provider")
def add_provider(req: ProviderReq):
    env_name = req.name.upper() + "_API_KEY"
    os.environ[env_name] = req.apiKey
    
    try:
        with open(".env", "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
        
    found = False
    with open(".env", "w") as f:
        for line in lines:
            if line.startswith(f"{env_name}="):
                f.write(f"{env_name}={req.apiKey}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"\n{env_name}={req.apiKey}\n")
            
    return {"status": "success"}

@app.get("/api/config/verify/{name}")
def verify_provider(name: str):
    env_name = name.upper() + "_API_KEY"
    key = os.environ.get(env_name)
    
    if not key:
        try:
            with open(".env", "r") as f:
                for line in f.readlines():
                    if line.startswith(f"{env_name}="):
                        key = line.split("=")[1].strip()
        except FileNotFoundError:
            pass
            
    if not key:
        return {"status": "error", "message": "Key not found"}
    if len(key) < 10:
        return {"status": "error", "message": "Key format invalid"}
    return {"status": "success"}

@app.delete("/api/config/provider/{name}")
def delete_provider(name: str):
    env_name = name.upper() + "_API_KEY"
    if env_name in os.environ:
        del os.environ[env_name]
        
    try:
        with open(".env", "r") as f:
            lines = f.readlines()
        with open(".env", "w") as f:
            for line in lines:
                if not line.startswith(f"{env_name}="):
                    f.write(line)
    except FileNotFoundError:
        pass
        
    return {"status": "success"}

class ModelReq(BaseModel):
    alias: str
    actual: str
    provider: str

@app.post("/api/config/model")
def add_model(req: ModelReq):
    config_path = "litellm_config.yaml"
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
    config_path = "litellm_config.yaml"
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

# Uvicorn server is now launched independently via CLI.

class GatewayHooks(CustomLogger):
    def __init__(self):
        super().__init__()

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        
        # Ensure LLM knows it is an Autonomous Agent
        system_msg = {
            "role": "system",
            "content": "You are TAPIOD, an advanced Autonomous Agent. You have dynamic access to external tools and real-time APIs. You may use tools on some turns and not others depending on the user's prompt. If you previously provided real-time data or specific factual information, do not apologize or claim you hallucinated it; you successfully fetched it using a tool in a previous turn. Trust your previous messages."
        }
        
        if messages and messages[0].get("role") != "system":
            messages.insert(0, system_msg)
        elif messages:
            messages[0]["content"] = system_msg["content"] + "\n\n" + messages[0].get("content", "")
            
        data["messages"] = messages
        
        # Extract tenant ID from user API key for isolation
        api_key = ""
        if hasattr(user_api_key_dict, "api_key"):
            api_key = getattr(user_api_key_dict, "api_key")
        elif isinstance(user_api_key_dict, dict):
            api_key = user_api_key_dict.get("api_key", "")
            
        import hashlib
        tenant_id = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "default_tenant"
        data["tenant_id"] = tenant_id

        # --- QDRANT SEMANTIC CACHE SIMULATION ---
        bypass_cache = data.get("metadata", {}).get("bypass_cache", False)
        
        with open("hooks_debug.txt", "a") as f:
            f.write(f"Pre-call hook triggered for tenant: {tenant_id}. bypass_cache: {bypass_cache}\n")
            
        if not bypass_cache and messages and qdrant is not None and embedding_model is not None:
            prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                
                vecs = list(embedding_model.embed([prompt]))
                if vecs:
                    vec = vecs[0].tolist()
                    response = qdrant.query_points(
                        collection_name="semantic_cache_384",
                        query=vec,
                        query_filter=Filter(
                            must=[
                                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
                            ]
                        ),
                        limit=1
                    )
                    results = response.points
                    if results and results[0].score > 0.85:
                        cached_response = results[0].payload.get("response")
                        if cached_response:
                            data["mock_response"] = cached_response
                            data["qdrant_cache_hit"] = True
                            
                            # Pass flag safely to the logger hook via metadata
                            if "litellm_params" not in data:
                                data["litellm_params"] = {}
                            if "metadata" not in data["litellm_params"]:
                                data["litellm_params"]["metadata"] = {}
                            data["litellm_params"]["metadata"]["qdrant_cache_hit"] = True
                            
                            print(f"Semantic Cache HIT for tenant {tenant_id[:8]}! Score: {results[0].score}")
                            return data
            except Exception as e:
                with open("hooks_debug.txt", "a") as f:
                    f.write(f"Semantic Cache Error: {e}\n")
                print(f"Semantic Cache Error: {e}")
                pass

        if messages and services_status["routellm_ready"] and routellm_client:
            prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""

            try:
                model_route = routellm_client.route(prompt, "mf", 0.5)
                print(f"RouteLLM evaluated prompt and selected: {model_route}")
                data["model"] = model_route
            except Exception as e:
                score = min(1.0, len(prompt) / 100.0)
                if any(kw in prompt.lower() for kw in ["code", "script", "analyze", "explain"]):
                    score += 0.5
                model_route = "heavy-model" if score >= 0.5 else "fast-model"
                print(f"RouteLLM (Local Fallback) selected {model_route} with complexity score {score}")
                data["model"] = model_route
        else:
            data["model"] = "heavy-model"
            
        # --- DYNAMIC TOOL LOADOUT ---
        if messages and qdrant is not None and embedding_model is not None:
            prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
            try:
                vecs = list(embedding_model.embed([prompt]))
                if vecs:
                    vec = vecs[0].tolist()
                    response = qdrant.query_points(
                        collection_name="tool_registry",
                        query=vec,
                        limit=3,
                        score_threshold=0.65
                    )
                    tools_to_inject = []
                    for res in response.points:
                        tool_data = json.loads(res.payload["tool_data"])
                        tools_to_inject.append(tool_data)
                    
                    if tools_to_inject:
                        data["tools"] = tools_to_inject
                        tool_names = [t["function"]["name"] for t in tools_to_inject]
                        try:
                            with open(r"c:\Coding\TAPIOD\gateway\last_tools.json", "w") as f:
                                json.dump({tenant_id: tool_names}, f)
                        except Exception as e:
                            print(f"IPC FILE WRITE ERROR: {e}")
                        print(f"Dynamic Tool Loadout injected {len(tools_to_inject)} tools for intent.")
                    else:
                        try:
                            with open(r"c:\Coding\TAPIOD\gateway\last_tools.json", "w") as f:
                                json.dump({tenant_id: []}, f)
                        except Exception as e:
                            print(f"IPC FILE WRITE ERROR: {e}")
            except Exception as e:
                print(f"Dynamic Tool Loadout Error: {e}")
            
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        with open("hooks_debug.txt", "a") as f:
            f.write(f"Post-call hook triggered. qdrant_cache_hit={data.get('qdrant_cache_hit')}\n")
            
        # --- CACHE WRITE TO QDRANT ---
        if qdrant is not None and not data.get("qdrant_cache_hit"):
            try:
                messages = data.get("messages", [])
                prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
                
                # Check if it's a litellm mock response (which is a dict) or a real ModelResponse
                if isinstance(response, dict):
                    response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                else:
                    response_text = response.choices[0].message.content if hasattr(response, "choices") else ""
                    
                tenant_id = data.get("tenant_id", "default_tenant")
                
                with open("hooks_debug.txt", "a") as f:
                    f.write(f"Post-hook vars: prompt_len={len(prompt)}, response_len={len(response_text)}, tenant={tenant_id[:8]}\n")
                
                if prompt and response_text and embedding_model is not None:
                    vecs = list(embedding_model.embed([prompt]))
                    if vecs:
                        vec = vecs[0].tolist()
                        import uuid
                        qdrant.upsert(
                            collection_name="semantic_cache_384",
                            points=[{
                                "id": str(uuid.uuid4()),
                                "vector": vec,
                                "payload": {
                                    "tenant_id": tenant_id,
                                    "prompt": prompt, 
                                    "response": response_text
                                }
                            }]
                        )
                        with open("hooks_debug.txt", "a") as f:
                            f.write(f"Semantic Cache WRITTEN to Qdrant!\n")
                        print(f"Semantic Cache WRITTEN for tenant {tenant_id[:8]}!")
            except Exception as e:
                with open("hooks_debug.txt", "a") as f:
                    f.write(f"Cache Write Error: {e}\n")
                print(f"Cache Write Error: {e}")
                pass
                
        # Zero out virtual tokens in the response sent to the client if it's a cache hit
        if data.get("qdrant_cache_hit"):
            if hasattr(response, "usage") and response.usage:
                response.usage.total_tokens = 0
                response.usage.prompt_tokens = 0
                response.usage.completion_tokens = 0
            elif isinstance(response, dict) and "usage" in response:
                response["usage"]["total_tokens"] = 0
                response["usage"]["prompt_tokens"] = 0
                response["usage"]["completion_tokens"] = 0
                
            if hasattr(response, "model"):
                response.model = "cached"
            elif isinstance(response, dict):
                response["model"] = "cached"
            
        return response

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        latency = (end_time - start_time).total_seconds() if hasattr(end_time, 'total_seconds') else (end_time - start_time)
        if hasattr(start_time, 'timestamp'):
            latency = end_time.timestamp() - start_time.timestamp()
            
        usage = getattr(response_obj, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
        if isinstance(response_obj, dict):
            usage = response_obj.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            
        cost = (total_tokens / 1000.0) * 0.001
        
        model_name = getattr(kwargs, "model", "unknown")
        if isinstance(kwargs, dict):
            model_name = kwargs.get("model", "unknown")
            
        # Determine cache hit
        cache_hit = False
        if isinstance(response_obj, dict) and response_obj.get("model") == "cached":
            cache_hit = True
        elif hasattr(response_obj, "model") and getattr(response_obj, "model") == "cached":
            cache_hit = True
        elif kwargs.get("qdrant_cache_hit"):
            cache_hit = True
        elif kwargs.get("mock_response"):
            cache_hit = True
        elif kwargs.get("cache_hit"):
            cache_hit = True
        elif kwargs.get("litellm_params", {}).get("metadata", {}).get("qdrant_cache_hit"):
            cache_hit = True
        elif total_tokens == 0 and cost == 0.0:
            cache_hit = True
            
        print(f"DEBUG_LOGGER: type(response_obj)={type(response_obj)}, model_attr={getattr(response_obj, 'model', 'NO_MODEL_ATTR')}, dict_model={response_obj.get('model') if isinstance(response_obj, dict) else 'NOT_DICT'}")
        
        if cache_hit:
            cost = 0.0
            total_tokens = 0
            model_name = "cached"
            
        try:
            conn = await asyncpg.connect(DB_DSN)
            await conn.execute('''
                INSERT INTO requests_log (timestamp, latency, model, cost, tokens, cache_hit, blocked)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', datetime.now(), latency, model_name, cost, total_tokens, cache_hit, False)
            await conn.close()
            print(f"Logged to PostgreSQL -> latency: {latency:.2f}s | model: {model_name} | cache: {cache_hit}")
        except Exception as e:
            print(f"DB Insert Error: {e}")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            conn = await asyncpg.connect(DB_DSN)
            await conn.execute('''
                INSERT INTO requests_log (timestamp, latency, model, cost, tokens, cache_hit, blocked)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            ''', datetime.now(), 0.0, "blocked", 0.0, 0, False, True)
            await conn.close()
        except Exception as e:
            print(f"DB Insert Error: {e}")

proxy_hooks = GatewayHooks()
