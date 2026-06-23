#!/usr/bin/env python3
"""
TAPIOD vs Direct Claude Opus — Cost Comparison Benchmark
=========================================================
Baseline  : every prompt sent to heavy-anthropic (claude-opus-4-8) via TAPIOD,
            no routing — simulates what you'd pay if you always used the top model.
TAPIOD    : same prompts with routing enabled (model=fast-groq, pre-call hook overrides):
              simple  → fast-anthropic  (claude-sonnet-4-6  — $3/$15 per M tokens)
              complex → heavy-anthropic (claude-opus-4-8    — $15/$75 per M tokens)
            cache hits → $0

Output: formatted comparison table + CSV in gateway/tests/results/

Usage:
  cd gateway
  source venv/bin/activate
  python tests/benchmark_claude.py
"""
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from tabulate import tabulate

# ── Load .env ──────────────────────────────────────────────────────────────────
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

TAPIOD_URL = "http://localhost:4001/api/agent/chat/completions"
HEADERS = {"Authorization": "Bearer tapiod", "Content-Type": "application/json"}

# ── Anthropic pricing (USD per 1M tokens, June 2026) ──────────────────────────
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8":           (15.00, 75.00),
    "claude-sonnet-4-6":         ( 3.00, 15.00),
    "claude-haiku-4-5-20251001": ( 0.25,  1.25),
    "claude-haiku-4-5":          ( 0.25,  1.25),
    # TAPIOD model aliases → resolved to actual model at call time
    "heavy-anthropic":           (15.00, 75.00),   # → claude-opus-4-8
    "fast-anthropic":            ( 3.00, 15.00),   # → claude-sonnet-4-6
    # Groq (when routing falls back)
    "heavy-groq":                ( 0.59,  0.79),
    "fast-groq":                 ( 0.05,  0.08),
    "llama-3.3-70b-versatile":   ( 0.59,  0.79),
    "llama-3.1-8b-instant":      ( 0.05,  0.08),
}


def _tok_cost(model_key: str, in_tok: int, out_tok: int) -> float:
    key = model_key if model_key in PRICING else next(
        (k for k in PRICING if k in (model_key or "")), None
    )
    if not key:
        return 0.0
    in_rate, out_rate = PRICING[key]
    return (in_tok * in_rate + out_tok * out_rate) / 1_000_000


# ── Prompt suite ───────────────────────────────────────────────────────────────
PROMPTS = [
    # Simple factual — expected → fast-anthropic (Sonnet ~5x cheaper than Opus)
    ("What is the capital of Japan?",                                     "simple"),
    ("Who wrote the play Hamlet?",                                        "simple"),
    ("Convert 72 Fahrenheit to Celsius.",                                 "simple"),
    ("What does the acronym API stand for?",                              "simple"),
    ("How many days are in a leap year?",                                 "simple"),

    # Medium — could go either way depending on KNN score
    ("What is the difference between TCP and UDP?",                       "medium"),
    ("Explain what a REST API is in 3 sentences.",                        "medium"),
    ("What are Python list comprehensions and when should you use them?", "medium"),
    ("What does `git rebase` do and how does it differ from `git merge`?","medium"),

    # Complex — expected → heavy-anthropic (Opus, same cost as baseline)
    (
        "Design a scalable database schema for a multi-tenant SaaS billing system "
        "with usage-based pricing, invoicing, and audit logging.",
        "complex",
    ),
    (
        "Explain the mathematical intuition behind attention mechanisms in transformers: "
        "cover softmax, key-query-value matrices, and why multi-head attention helps.",
        "complex",
    ),
    (
        "Write a production-ready Python rate limiter backed by Redis that supports "
        "per-user quotas and handles burst traffic gracefully.",
        "complex",
    ),
    (
        "Analyze the trade-offs between eventual consistency and strong consistency "
        "in distributed systems. Give concrete real-world examples for when to pick each.",
        "complex",
    ),
    (
        "A FastAPI service randomly returns 500 errors under load. Describe your "
        "complete systematic debugging process from symptoms to root cause.",
        "complex",
    ),
]


def _post(model: str, prompt: str, bypass_cache: bool = False) -> dict:
    """POST to TAPIOD agent endpoint. Returns raw JSON."""
    try:
        t0 = time.time()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if bypass_cache:
            payload["metadata"] = {"bypass_cache": True}
        resp = httpx.post(TAPIOD_URL, json=payload, headers=HEADERS, timeout=90.0)
        resp.raise_for_status()
        return {"data": resp.json(), "ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        return {"error": str(e)}


def _parse(result: dict) -> dict:
    """Extract model alias, token counts, cache status and compute costs."""
    if result.get("error"):
        return {
            "model": "error", "model_display": "error",
            "in_tok": 0, "out_tok": 0, "total_tok": 0,
            "tapiod_cost": 0.0, "cache": "miss", "ms": 0, "error": result["error"],
        }
    data  = result["data"]
    trace = data.get("_tapiod_trace", {})
    usage = data.get("usage") or {}

    if hasattr(usage, "prompt_tokens"):
        in_tok, out_tok = usage.prompt_tokens, usage.completion_tokens
    elif isinstance(usage, dict):
        in_tok  = usage.get("prompt_tokens")    or 0
        out_tok = usage.get("completion_tokens") or 0
    else:
        in_tok = out_tok = 0

    cache_source = trace.get("cache_source") or "miss"
    raw_model    = trace.get("provider_model") or data.get("model") or "unknown"
    model_key    = raw_model.split("/")[-1] if "/" in raw_model else raw_model

    cost = 0.0 if cache_source != "miss" else _tok_cost(model_key, in_tok, out_tok)

    return {
        "model":         raw_model,
        "model_display": model_key,
        "in_tok":        in_tok,
        "out_tok":       out_tok,
        "total_tok":     in_tok + out_tok,
        "tapiod_cost":   cost,
        "cache":         cache_source,
        "ms":            result.get("ms", 0),
        "error":         None,
    }


def run():
    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'═'*74}")
    print(f"  TAPIOD vs Direct Claude Opus — Benchmark  ({run_ts})")
    print(f"  Baseline : every prompt → heavy-anthropic (claude-opus-4-8)")
    print(f"             $15/M input · $75/M output")
    print(f"  TAPIOD   : routes by complexity (KNN classifier)")
    print(f"             simple  → fast-anthropic (claude-sonnet-4-6, $3/$15/M)")
    print(f"             complex → heavy-anthropic (claude-opus-4-8, $15/$75/M)")
    print(f"             cache   → $0 (Redis L1 or Qdrant L2)")
    print(f"{'═'*74}\n")

    results = []

    for i, (prompt, category) in enumerate(PROMPTS, 1):
        short = prompt[:58] + ("…" if len(prompt) > 58 else "")
        print(f"[{i:02d}/{len(PROMPTS)}] {category.upper():7} | {short}")

        # ── Baseline: force heavy-anthropic (Opus), bypass cache ─────────────
        print("  → Baseline (Opus)… ", end="", flush=True)
        base_raw = _post("heavy-anthropic", prompt, bypass_cache=True)
        base = _parse(base_raw)
        # Baseline cost is always full Opus price (no cache benefit counted here)
        base_cost = _tok_cost("heavy-anthropic", base["in_tok"], base["out_tok"])
        if base.get("error"):
            print(f"ERROR: {base['error']}")
        else:
            print(f"{base['total_tok']:,} tok | ${base_cost:.6f} | {base['ms']}ms | {base['model_display']}")

        time.sleep(0.5)

        # ── TAPIOD: let KNN router decide which model to use ──────────────────
        print("  → TAPIOD (routed)… ", end="", flush=True)
        tapiod_raw = _post("fast-groq", prompt)   # fast-groq is a valid alias; hook overrides with KNN choice
        tapiod = _parse(tapiod_raw)
        if tapiod.get("error"):
            print(f"ERROR: {tapiod['error']}")
        else:
            cache_tag = f" [{tapiod['cache'].upper()} HIT]" if tapiod["cache"] != "miss" else ""
            savings   = max(0.0, base_cost - tapiod["tapiod_cost"])
            pct       = (savings / base_cost * 100) if base_cost > 0 else 0.0
            print(
                f"{tapiod['total_tok']:,} tok | ${tapiod['tapiod_cost']:.6f} | {tapiod['ms']}ms | "
                f"{tapiod['model_display']} → saved ${savings:.6f} ({pct:.0f}%){cache_tag}"
            )

        savings = max(0.0, base_cost - tapiod.get("tapiod_cost", 0.0))
        results.append({
            "num":           i,
            "category":      category,
            "prompt":        prompt,
            # baseline
            "base_model":    base.get("model_display", "?"),
            "base_in_tok":   base.get("in_tok", 0),
            "base_out_tok":  base.get("out_tok", 0),
            "base_total":    base.get("total_tok", 0),
            "base_cost":     base_cost,
            "base_ms":       base.get("ms", 0),
            # tapiod
            "tapiod_model":  tapiod.get("model_display", "?"),
            "tapiod_in_tok": tapiod.get("in_tok", 0),
            "tapiod_out_tok":tapiod.get("out_tok", 0),
            "tapiod_total":  tapiod.get("total_tok", 0),
            "tapiod_cost":   tapiod.get("tapiod_cost", 0.0),
            "tapiod_cache":  tapiod.get("cache", "miss"),
            "tapiod_ms":     tapiod.get("ms", 0),
            "savings_usd":   savings,
            "savings_pct":   (savings / base_cost * 100) if base_cost > 0 else 0.0,
        })

        time.sleep(0.8)

    # ── Comparison table ───────────────────────────────────────────────────────
    table_rows = []
    tot_base    = 0.0
    tot_tapiod  = 0.0
    tot_savings = 0.0
    cache_count = 0
    fast_count  = 0
    heavy_count = 0

    for r in results:
        cache_tag = r["tapiod_cache"] if r["tapiod_cache"] != "miss" else "—"
        table_rows.append([
            r["num"],
            r["category"],
            r["prompt"][:50],
            f"{r['base_in_tok']:,}+{r['base_out_tok']:,}",
            f"${r['base_cost']:.6f}",
            r["tapiod_model"][:26],
            f"{r['tapiod_in_tok']:,}+{r['tapiod_out_tok']:,}",
            f"${r['tapiod_cost']:.6f}",
            f"${r['savings_usd']:.6f}",
            f"{r['savings_pct']:.1f}%",
            cache_tag,
        ])
        tot_base    += r["base_cost"]
        tot_tapiod  += r["tapiod_cost"]
        tot_savings += r["savings_usd"]
        if r["tapiod_cache"] != "miss":
            cache_count += 1
        elif "fast" in r["tapiod_model"]:
            fast_count += 1
        elif "heavy" in r["tapiod_model"]:
            heavy_count += 1

    overall_pct = (tot_savings / tot_base * 100) if tot_base > 0 else 0.0
    table_rows.append([
        "TOTAL", "", "",
        "", f"${tot_base:.6f}",
        "", "", f"${tot_tapiod:.6f}",
        f"${tot_savings:.6f}", f"{overall_pct:.1f}%",
        f"{cache_count} hits",
    ])

    headers = [
        "#", "Cat", "Prompt (50 chars)",
        "Opus Tokens", "Opus Cost $",
        "TAPIOD Model", "TAPIOD Tokens", "TAPIOD Cost $",
        "Saved $", "Saved %", "Cache",
    ]

    print(f"\n\n{'═'*155}")
    print("  DOCUMENTED COMPARISON — Baseline: all prompts via claude-opus-4-8  |  TAPIOD: KNN-routed")
    print(f"{'═'*155}")
    print(tabulate(table_rows, headers=headers, tablefmt="rounded_outline"))

    print(f"\n  Prompts run           : {len(results)}")
    print(f"  Routing breakdown     : {fast_count} → fast-anthropic (Sonnet)  |  "
          f"{heavy_count} → heavy-anthropic (Opus)  |  {cache_count} → cache ($0)")
    print(f"  Baseline total cost   : ${tot_base:.6f}  (all {len(results)} prompts → claude-opus-4-8)")
    print(f"  TAPIOD total cost     : ${tot_tapiod:.6f}  (routed by complexity + cache)")
    print(f"  Total saved           : ${tot_savings:.6f}  ({overall_pct:.1f}% reduction vs always using Opus)")
    print(f"{'═'*155}")

    # ── Save CSV ───────────────────────────────────────────────────────────────
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"benchmark_claude_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Full results saved to: {csv_path}\n")


if __name__ == "__main__":
    run()
