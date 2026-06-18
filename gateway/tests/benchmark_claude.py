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
