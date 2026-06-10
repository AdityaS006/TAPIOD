import time
import threading
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from litellm.integrations.custom_logger import CustomLogger

import os
import yaml
from datetime import datetime
from pydantic import BaseModel

# Global in-memory metrics store
metrics_data = {
    "total_requests": 0,
    "cache_hits": 0,
    "blocked_requests": 0,
    "total_cost": 0.0,
    "latencies": [],
    "requests_log": [] # stores recent requests: timestamp, latency, model, cost
}

# Real-time service statuses
services_status = {
    "routellm_ready": False
}

routellm_client = None

def init_routellm():
    global routellm_client
    try:
        from routellm.controller import Controller
        print("Initializing RouteLLM Controller in background...")
        # The mf model will be downloaded from huggingface on first run
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

# Setup a small FastAPI server to serve metrics to the dashboard
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/metrics")
def get_metrics():
    avg_latency = 0
    if len(metrics_data["latencies"]) > 0:
        avg_latency = sum(metrics_data["latencies"]) / len(metrics_data["latencies"])
        
    recent_requests = [
        {
            "time": r["timestamp"].strftime("%H:%M:%S"),
            "latency": round(r["latency"], 2),
            "model": r["model"],
            "cost": r["cost"],
            "tokens": r["tokens"]
        } for r in metrics_data["requests_log"][-20:]
    ]
        
    return {
        "total_requests": metrics_data["total_requests"],
        "cache_hits": metrics_data["cache_hits"],
        "blocked_requests": metrics_data["blocked_requests"],
        "total_cost": metrics_data["total_cost"],
        "avg_latency_ms": round(avg_latency * 1000, 2),
        "recent_requests": recent_requests
    }

@app.get("/api/observability")
def get_observability():
    # Format requests log for Recharts AreaChart
    # Group by minute for a simulated timeline
    grouped = {}
    routing_counts = {"Cache Hit": metrics_data["cache_hits"], "Blocked": metrics_data["blocked_requests"]}
    
    # Pre-fill last 5 minutes to ensure AreaChart renders a full line instead of a dot
    now = datetime.now()
    from datetime import timedelta
    for i in range(5, -1, -1):
        t = (now - timedelta(minutes=i)).strftime("%H:%M")
        grouped[t] = {"time": t, "fast": 0, "heavy": 0, "fast_count": 0, "heavy_count": 0}
        
    for req in metrics_data["requests_log"]:
        t = req["timestamp"].strftime("%H:%M")
        if t not in grouped:
            grouped[t] = {"time": t, "fast": 0, "heavy": 0, "fast_count": 0, "heavy_count": 0}
            
        is_heavy = "heavy" in req["model"] or "70b" in req["model"] or "gpt-4o" in req["model"]
        
        # We track total latency to compute average per minute
        if is_heavy:
            grouped[t]["heavy"] += req["latency"] * 1000
            grouped[t]["heavy_count"] += 1
            routing_counts[req["model"]] = routing_counts.get(req["model"], 0) + 1
        else:
            grouped[t]["fast"] += req["latency"] * 1000
            grouped[t]["fast_count"] += 1
            routing_counts[req["model"]] = routing_counts.get(req["model"], 0) + 1

    # Compute averages
    latency_data = []
    for t, data in sorted(grouped.items()):
        fast_avg = data["fast"] / data["fast_count"] if data["fast_count"] > 0 else 0
        heavy_avg = data["heavy"] / data["heavy_count"] if data["heavy_count"] > 0 else 0
        latency_data.append({
            "time": data["time"],
            "fast": round(fast_avg),
            "heavy": round(heavy_avg)
        })
        
    # Format routing data for BarChart
    routing_data = [{"name": k, "value": v} for k, v in routing_counts.items() if v > 0]
    
    return {
        "latencyData": latency_data,
        "routingData": routing_data
    }

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
        
    # Read providers from .env directly
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
    
    # Persist to .env (update if exists, append if new)
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
    
    # Try reading from .env if not in memory
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

def run_metrics_server():
    uvicorn.run(app, host="0.0.0.0", port=4001, log_level="warning")

# Start the metrics server in a background thread when LiteLLM loads this hook
threading.Thread(target=run_metrics_server, daemon=True).start()

class GatewayHooks(CustomLogger):
    def __init__(self):
        super().__init__()

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        
        if messages and services_status["routellm_ready"] and routellm_client:
            prompt = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
            try:
                # Calculate ML complexity and get the assigned route
                model_route = routellm_client.route(prompt, "mf", 0.5)
                print(f"RouteLLM evaluated prompt and selected: {model_route}")
                data["model"] = model_route
            except Exception as e:
                # If RouteLLM's internal OpenAI embeddings call fails (e.g. quota limit),
                # fallback to our own local fast heuristic algorithm to ensure it still routes!
                score = min(1.0, len(prompt) / 100.0)
                if any(kw in prompt.lower() for kw in ["code", "script", "analyze", "explain"]):
                    score += 0.5
                    
                model_route = "heavy-model" if score >= 0.5 else "fast-model"
                print(f"RouteLLM (Local Fallback) selected {model_route} with complexity score {score}")
                data["model"] = model_route
        else:
            # Fallback route if RouteLLM is still downloading/initializing
            data["model"] = "heavy-model"
            
        # We will add Presidio masking here soon
        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        # We will add Presidio unmasking here soon
        return response

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        metrics_data["total_requests"] += 1
        
        # Calculate latency
        latency = (end_time - start_time).total_seconds() if hasattr(end_time, 'total_seconds') else (end_time - start_time)
        # If it's a datetime object, use .timestamp(), but LiteLLM usually passes datetime
        if hasattr(start_time, 'timestamp'):
            latency = end_time.timestamp() - start_time.timestamp()
            
        metrics_data["latencies"].append(latency)
        
        usage = getattr(response_obj, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
        if isinstance(response_obj, dict):
            usage = response_obj.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            
        cost = (total_tokens / 1000.0) * 0.001
        metrics_data["total_cost"] += cost
        
        model_name = getattr(kwargs, "model", "unknown")
        if isinstance(kwargs, dict):
            model_name = kwargs.get("model", "unknown")
            
        # Append to log
        metrics_data["requests_log"].append({
            "timestamp": datetime.now(),
            "latency": latency,
            "model": model_name,
            "cost": cost,
            "tokens": total_tokens
        })
        
        print(f"Log Success: latency={latency:.2f}s, tokens={total_tokens}, cost=${cost:.6f}")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        metrics_data["total_requests"] += 1
        metrics_data["blocked_requests"] += 1

proxy_hooks = GatewayHooks()
