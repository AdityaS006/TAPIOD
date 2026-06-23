"""
TAPIOD Savings Benchmark
========================
Sends 20 queries through TAPIOD and reports cache hits, routing decisions,
and estimated savings vs calling GPT-4o-mini directly.

Usage:
  cd gateway
  source venv/bin/activate
  python tests/benchmark.py
"""
import sys
import time
import json
import httpx

GATEWAY_URL = "http://localhost:4001/api/agent/chat/completions"
HEADERS = {"Authorization": "Bearer tapiod", "Content-Type": "application/json"}

# ── Query mix ──────────────────────────────────────────────────────────────────
UNIQUE = [
    "What is the tallest mountain in Africa?",
    "Explain what a monad is in functional programming.",
    "How does HTTPS certificate pinning work?",
    "What is the difference between OLTP and OLAP databases?",
    "Explain the Byzantine Generals problem in distributed systems.",
]

# Sent twice — second should hit Redis L1 cache
REPEATED = [
    "What is the capital of France?",
    "What does HTTP stand for?",
    "What is the boiling point of water in Celsius?",
    "Who invented the telephone?",
    "What is the square root of 144?",
]

# Semantically similar pairs — second should hit Qdrant L2 cache
SIMILAR_PAIRS = [
    ("What year did World War 2 end?",          "When did the Second World War finish?"),
    ("What language do people speak in Brazil?", "What is the official language of Brazil?"),
]

# Complex — should route to heavy-groq
COMPLEX = [
    "Design a scalable database schema for a multi-tenant SaaS billing system with usage-based pricing.",
    "Explain gradient descent, backpropagation, and why vanishing gradients are a problem in deep networks.",
    "Write a production-ready Redis-backed rate limiter in Python that handles burst traffic.",
]


def send(prompt: str, model: str = "fast-groq") -> dict:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        resp = httpx.post(GATEWAY_URL, json=payload, headers=HEADERS, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def run_benchmark():
    results = []

    def record(prompt, data, label=""):
        trace = data.get("_tapiod_trace", {})
        r = {
            "prompt": prompt[:60],
            "label": label,
            "cache_source": trace.get("cache_source") or "miss",
            "model": trace.get("provider_model", data.get("model", "?")),
            "cache_saved_usd": trace.get("total_saved_usd", 0.0),
            "routing_saved_usd": 0.0,
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0) if isinstance(data.get("usage"), dict) else getattr(data.get("usage"), "prompt_tokens", 0),
            "error": "error" in data,
        }
        # Parse routing save from pipeline
        for step in trace.get("pipeline", []):
            if step.get("layer") == "knn_router":
                r["router_result"] = step.get("result", "")
        results.append(r)
        status = f"{'✓ CACHE ' + r['cache_source'].upper() if r['cache_source'] != 'miss' else '  miss'}"
        print(f"  {status:20} {r['model']:25} {prompt[:50]}")

    print("\n" + "═" * 70)
    print("  TAPIOD SAVINGS BENCHMARK")
    print("═" * 70)

    print("\n[1/4] Unique queries (baseline — no cache possible)")
    for q in UNIQUE:
        record(q, send(q), "unique")

    print("\n[2/4] Repeated exact queries (Redis L1 cache expected on 2nd)")
    for q in REPEATED:
        record(q, send(q), "repeat-1st")
    print("  — sending same queries again —")
    for q in REPEATED:
        record(q, send(q), "repeat-2nd")

    print("\n[3/4] Semantically similar pairs (Qdrant L2 cache expected on 2nd)")
    for q1, q2 in SIMILAR_PAIRS:
        record(q1, send(q1), "similar-1st")
        time.sleep(0.5)
        record(q2, send(q2), "similar-2nd")

    print("\n[4/4] Complex queries (should route to heavy-groq)")
    for q in COMPLEX:
        record(q, send(q, model="heavy-groq"), "complex")

    # ── Report ─────────────────────────────────────────────────────────────────
    total = len(results)
    cache_hits = [r for r in results if r["cache_source"] != "miss"]
    redis_hits = [r for r in results if r["cache_source"] == "redis"]
    qdrant_hits = [r for r in results if r["cache_source"] == "qdrant"]
    errors = [r for r in results if r["error"]]

    models_used: dict[str, int] = {}
    for r in results:
        m = r["model"] or "unknown"
        models_used[m] = models_used.get(m, 0) + 1

    total_saved = sum(r["cache_saved_usd"] for r in results)

    # Estimate GPT-4o-mini baseline cost (what user would pay without TAPIOD)
    try:
        from litellm import cost_per_token
        baseline_cost = 0.0
        for r in results:
            pt = r["prompt_tokens"] or 50
            inp, out = cost_per_token(model="openai/gpt-4o-mini", prompt_tokens=pt, completion_tokens=150)
            baseline_cost += inp + out
    except Exception:
        baseline_cost = 0.0

    print("\n" + "═" * 70)
    print("  RESULTS")
    print("═" * 70)
    print(f"  Queries sent       : {total}")
    print(f"  Errors             : {len(errors)}")
    print(f"  Cache hits         : {len(cache_hits)} / {total}  ({100*len(cache_hits)//total}%)")
    print(f"    └─ Redis L1      : {len(redis_hits)}")
    print(f"    └─ Qdrant L2     : {len(qdrant_hits)}")
    print(f"\n  Model routing:")
    for model, count in sorted(models_used.items(), key=lambda x: -x[1]):
        print(f"    {model:30} {count} requests")
    print(f"\n  Baseline cost (GPT-4o-mini, no TAPIOD) : ${baseline_cost:.6f}")
    print(f"  TAPIOD estimated savings               : ${total_saved:.6f}")
    if baseline_cost > 0:
        pct = total_saved / baseline_cost * 100
        print(f"  Reduction                              : {pct:.1f}%")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    run_benchmark()
