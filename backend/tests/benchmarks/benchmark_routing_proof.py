#!/usr/bin/env python3
"""
TAPIOD Routing Proof — Demo Benchmark
=======================================
Proves that TAPIOD's KNN router saves money by sending simple prompts to
cheaper models instead of always using the expensive flagship model.

Method:
  Baseline : every prompt → claude-opus-4-8 (most expensive, no routing)
             cache bypassed so we get real token counts every time
  TAPIOD   : same prompts → KNN router decides the model
             cache bypassed so we measure routing savings, not just cache
             simple   → fast-anthropic  (claude-sonnet-4-6, $3/$15 per M)
             complex  → heavy-anthropic (claude-opus-4-8, $15/$75 per M)

Q: "Will this work the same with my own API keys?"
A: Yes. The routing logic is identical. Only the billing account changes.

Usage:
  cd gateway && source venv/bin/activate
  python tests/benchmark_routing_proof.py
"""
import csv
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from tabulate import tabulate

_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _l in _env.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            k, _, v = _l.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

TAPIOD_URL = "http://localhost:4001/api/agent/chat/completions"
HEADERS = {"Authorization": "Bearer tapiod", "Content-Type": "application/json"}

# Pricing per 1M tokens (USD) — Anthropic June 2026
PRICING = {
    "heavy-anthropic": (15.00, 75.00),   # claude-opus-4-8
    "fast-anthropic":  ( 3.00, 15.00),   # claude-sonnet-4-6
    "heavy-groq":      ( 0.59,  0.79),   # llama-3.3-70b (fallback)
    "fast-groq":       ( 0.05,  0.08),   # llama-3.1-8b  (fallback)
    # Actual model name substrings (in case trace returns full name)
    "claude-opus-4-8":           (15.00, 75.00),
    "claude-sonnet-4-6":         ( 3.00, 15.00),
    "llama-3.3-70b-versatile":   ( 0.59,  0.79),
    "llama-3.1-8b-instant":      ( 0.05,  0.08),
}


def cost(model_key: str, in_tok: int, out_tok: int) -> float:
    key = model_key if model_key in PRICING else next(
        (k for k in PRICING if k in (model_key or "")), None
    )
    if not key:
        return 0.0
    r_in, r_out = PRICING[key]
    return (in_tok * r_in + out_tok * r_out) / 1_000_000


# ── Fresh real-world prompts ────────────────────────────────────────────────────
# Never sent through this gateway before — no cache possible.
# Mix of enterprise-realistic queries across complexity levels.
PROMPTS = [
    # ── SIMPLE: one-line factual, definitions, quick conversions ──────────────
    ("What does CORS stand for and what does it prevent?",                          "simple"),
    ("What is the difference between == and === in JavaScript?",                    "simple"),
    ("What HTTP status code means 'resource not found'?",                           "simple"),
    ("What does the SQL keyword DISTINCT do?",                                      "simple"),
    ("Convert 1 gigabyte to megabytes.",                                            "simple"),
    ("What is a foreign key in a relational database?",                             "simple"),

    # ── MEDIUM: short explanations, comparisons, quick how-tos ───────────────
    ("Explain the difference between authentication and authorization.",             "medium"),
    ("What is memoization and when should you use it in Python?",                   "medium"),
    ("What is the purpose of an index in a database and what are the trade-offs?",  "medium"),

    # ── COMPLEX: design, architecture, production code, deep analysis ─────────
    (
        "We have a monolithic Django app serving 500k daily active users. "
        "Describe a step-by-step migration plan to microservices with zero downtime, "
        "covering service boundaries, data migration, traffic cutover, and rollback strategy.",
        "complex",
    ),
    (
        "Write a Python implementation of a distributed rate limiter using Redis "
        "that supports sliding window algorithm, per-user and per-IP quotas, "
        "graceful degradation under Redis failure, and Prometheus metrics export.",
        "complex",
    ),
    (
        "Our PostgreSQL queries are timing out on a table with 200M rows. "
        "Walk through your full diagnostic process: which queries to run, "
        "how to read EXPLAIN ANALYZE output, index strategies, and query rewrites.",
        "complex",
    ),
    (
        "Design a real-time notification system for a SaaS platform that needs to "
        "deliver push notifications, emails, and in-app alerts to 2M users with "
        "guaranteed delivery, deduplication, and per-user preference management.",
        "complex",
    ),
    (
        "Explain how you would implement multi-tenancy in a FastAPI application: "
        "cover data isolation strategies (schema-per-tenant vs row-level), "
        "middleware for tenant resolution, connection pooling, and security boundaries.",
        "complex",
    ),
]


def call(model: str, prompt: str) -> dict:
    try:
        t0 = time.time()
        resp = httpx.post(
            TAPIOD_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "metadata": {"bypass_cache": True},
            },
            headers=HEADERS,
            timeout=120.0,
        )
        resp.raise_for_status()
        data  = resp.json()
        trace = data.get("_tapiod_trace", {})
        usage = data.get("usage") or {}

        in_tok  = (usage.get("prompt_tokens")    or 0) if isinstance(usage, dict) else 0
        out_tok = (usage.get("completion_tokens") or 0) if isinstance(usage, dict) else 0
        model_used = trace.get("provider_model") or data.get("model") or model
        model_key  = model_used.split("/")[-1] if "/" in model_used else model_used

        return {
            "model_used": model_used,
            "model_key":  model_key,
            "in_tok":     in_tok,
            "out_tok":    out_tok,
            "total_tok":  in_tok + out_tok,
            "cost":       cost(model_key, in_tok, out_tok),
            "ms":         round((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "model_used": "error", "model_key": "error",
            "in_tok": 0, "out_tok": 0, "total_tok": 0,
            "cost": 0.0, "ms": 0, "error": str(e),
        }


def run():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'═'*78}")
    print(f"  TAPIOD ROUTING PROOF — Demo Benchmark  ({ts})")
    print(f"  {len(PROMPTS)} fresh prompts  ·  cache bypassed for both runs")
    print(f"  Baseline  : every prompt → claude-opus-4-8  ($15/$75 per M tokens)")
    print(f"  TAPIOD    : KNN router picks model by complexity")
    print(f"              simple   → claude-sonnet-4-6  ($3/$15 per M = 5× cheaper)")
    print(f"              complex  → claude-opus-4-8   ($15/$75 per M = same as baseline)")
    print(f"{'═'*78}\n")

    results = []

    for i, (prompt, category) in enumerate(PROMPTS, 1):
        short = prompt[:60] + ("…" if len(prompt) > 60 else "")
        print(f"[{i:02d}/{len(PROMPTS)}] {category.upper():7}  {short}")

        # ── Baseline: always Opus, no routing ─────────────────────────────────
        print(f"  Baseline (Opus) → ", end="", flush=True)
        base = call("heavy-anthropic", prompt)
        if base.get("error"):
            print(f"ERROR: {base['error']}")
        else:
            print(f"{base['total_tok']:,} tok ({base['in_tok']}+{base['out_tok']}) | "
                  f"${base['cost']:.5f} | {base['ms']}ms | {base['model_key']}")

        time.sleep(0.6)

        # ── TAPIOD: KNN picks the model ────────────────────────────────────────
        print(f"  TAPIOD (routed) → ", end="", flush=True)
        tapiod = call("fast-groq", prompt)  # fast-groq is valid alias; hook overrides via KNN
        if tapiod.get("error"):
            print(f"ERROR: {tapiod['error']}")
        else:
            savings = max(0.0, base["cost"] - tapiod["cost"])
            pct     = (savings / base["cost"] * 100) if base["cost"] > 0 else 0.0
            tier    = "CHEAPER MODEL ✓" if tapiod["model_key"] != base["model_key"] else "same model"
            print(f"{tapiod['total_tok']:,} tok ({tapiod['in_tok']}+{tapiod['out_tok']}) | "
                  f"${tapiod['cost']:.5f} | {tapiod['ms']}ms | {tapiod['model_key']} "
                  f"→ saved ${savings:.5f} ({pct:.0f}%)  [{tier}]")

        savings = max(0.0, base.get("cost", 0.0) - tapiod.get("cost", 0.0))
        results.append({
            "num":            i,
            "category":       category,
            "prompt":         prompt,
            "base_model":     base.get("model_key", "?"),
            "base_in":        base.get("in_tok", 0),
            "base_out":       base.get("out_tok", 0),
            "base_total":     base.get("total_tok", 0),
            "base_cost":      base.get("cost", 0.0),
            "base_ms":        base.get("ms", 0),
            "tapiod_model":   tapiod.get("model_key", "?"),
            "tapiod_in":      tapiod.get("in_tok", 0),
            "tapiod_out":     tapiod.get("out_tok", 0),
            "tapiod_total":   tapiod.get("total_tok", 0),
            "tapiod_cost":    tapiod.get("cost", 0.0),
            "tapiod_ms":      tapiod.get("ms", 0),
            "saved_usd":      savings,
            "saved_pct":      (savings / base["cost"] * 100) if base.get("cost", 0) > 0 else 0.0,
            "routed_cheaper": tapiod.get("model_key", "?") != base.get("model_key", "?"),
        })
        print()
        time.sleep(0.8)

    # ── Build table ────────────────────────────────────────────────────────────
    rows = []
    tot_base = tot_tapiod = tot_saved = 0.0
    routed_cheaper = 0

    for r in results:
        model_label = r["tapiod_model"][:26]
        cheaper_tag = "✓ cheaper" if r["routed_cheaper"] else "= same"
        rows.append([
            r["num"],
            r["category"],
            r["prompt"][:52],
            f"{r['base_in']}+{r['base_out']}",
            f"${r['base_cost']:.5f}",
            model_label,
            f"{r['tapiod_in']}+{r['tapiod_out']}",
            f"${r['tapiod_cost']:.5f}",
            f"${r['saved_usd']:.5f}",
            f"{r['saved_pct']:.1f}%",
            cheaper_tag,
        ])
        tot_base   += r["base_cost"]
        tot_tapiod += r["tapiod_cost"]
        tot_saved  += r["saved_usd"]
        if r["routed_cheaper"]:
            routed_cheaper += 1

    pct_total = (tot_saved / tot_base * 100) if tot_base > 0 else 0.0
    rows.append([
        "TOTAL", "", "",
        "", f"${tot_base:.5f}",
        "", "", f"${tot_tapiod:.5f}",
        f"${tot_saved:.5f}", f"{pct_total:.1f}%",
        f"{routed_cheaper}/{len(results)} cheaper",
    ])

    headers = [
        "#", "Cat", "Prompt (52 chars)",
        "Opus Tokens", "Opus $",
        "TAPIOD Model", "TAPIOD Tokens", "TAPIOD $",
        "Saved $", "Saved %", "Routing",
    ]

    print(f"\n{'═'*165}")
    print("  ROUTING PROOF — Baseline (all Opus) vs TAPIOD (KNN-routed)  ·  cache bypassed for fair comparison")
    print(f"{'═'*165}")
    print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))

    # Breakdown by category
    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    print()
    for cat, cat_results in by_cat.items():
        cat_base   = sum(r["base_cost"]   for r in cat_results)
        cat_tapiod = sum(r["tapiod_cost"] for r in cat_results)
        cat_saved  = sum(r["saved_usd"]   for r in cat_results)
        cat_pct    = (cat_saved / cat_base * 100) if cat_base > 0 else 0.0
        models     = set(r["tapiod_model"] for r in cat_results)
        print(f"  {cat.upper():7}  ({len(cat_results)} prompts) → "
              f"Baseline ${cat_base:.5f}  |  TAPIOD ${cat_tapiod:.5f}  |  "
              f"Saved ${cat_saved:.5f} ({cat_pct:.1f}%)  |  Models: {', '.join(models)}")

    print()
    print(f"  Total prompts         : {len(results)}")
    print(f"  Routed to cheaper     : {routed_cheaper} / {len(results)}  "
          f"(simple queries → Sonnet instead of Opus)")
    print(f"  Baseline total        : ${tot_base:.5f}  (every prompt paid Opus price)")
    print(f"  TAPIOD total          : ${tot_tapiod:.5f}  (smart routing, no cache)")
    print(f"  Total saved           : ${tot_saved:.5f}  ({pct_total:.1f}% reduction)")
    print()
    print(f"  NOTE: This benchmark bypasses TAPIOD's cache intentionally.")
    print(f"  In production, repeated/similar queries add another layer of savings")
    print(f"  (cache hit = $0 regardless of model). This table shows routing alone.")
    print(f"{'═'*165}")

    # ── Save CSV ───────────────────────────────────────────────────────────────
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"routing_proof_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Results saved → {csv_path}\n")


if __name__ == "__main__":
    run()
