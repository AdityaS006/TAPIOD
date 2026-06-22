"""
Step 1 of 2: Download 5000 Arena prompts to disk.
No embedding, no Qdrant, no torch — just streams HuggingFace and writes JSON.
Run this BEFORE starting any services.

Step 2 (embed + upsert) is in seed_arena.py — run that after services are up.
"""
import gc
import json
import time
from pathlib import Path

TARGET_PER_LABEL = 2_500   # 2500 fast + 2500 heavy = 5000 total
OUT_FILE = Path(__file__).parent / "arena_prompts.json"

STRONG = [
    "gpt-4o", "gpt-4-turbo", "gpt-4", "claude-3-opus", "claude-3-sonnet",
    "claude-2", "claude-opus", "gemini-ultra", "gemini-1.5-pro",
    "llama-3.3-70b", "llama-3.1-70b", "llama-3.1-405b", "mistral-large",
    "mixtral-8x22b", "command-r-plus", "deepseek-v2",
]
WEAK = [
    "gpt-3.5", "gpt-4o-mini", "claude-instant", "claude-haiku",
    "claude-3-haiku", "mistral-7b", "mistral-tiny", "mistral-small",
    "llama-2-7b", "llama-2-13b", "llama-3.1-8b", "llama-3-8b",
    "phi-", "gemma-", "qwen-", "yi-", "falcon-", "mpt-",
    "mixtral-8x7b", "command-r",
]

def tier(model: str):
    m = model.lower()
    if any(s in m for s in STRONG): return "heavy"
    if any(s in m for s in WEAK):   return "fast"
    return None

def main():
    print("Importing datasets (this is the only heavy import)…")
    from datasets import load_dataset
    print("Streaming lmsys/lmsys-arena-human-preference-55k…")

    ds = load_dataset(
        "lmsys/lmsys-arena-human-preference-55k",
        split="train",
        streaming=True,
    )

    fast, heavy = [], []
    scanned = 0

    for row in ds:
        if len(fast) >= TARGET_PER_LABEL and len(heavy) >= TARGET_PER_LABEL:
            break

        scanned += 1
        if scanned % 500 == 0:
            print(f"  scanned {scanned:,}  fast={len(fast)}  heavy={len(heavy)}", end="\r")
            gc.collect()   # release any row buffers

        if row.get("winner_tie"):
            continue
        winning = row["model_a"] if row.get("winner_model_a") else row["model_b"]
        label = tier(winning)
        if label is None:
            continue

        text = (row.get("prompt") or "").strip()[:400]
        if not text:
            continue

        if label == "fast"  and len(fast)  < TARGET_PER_LABEL:
            fast.append(text)
        elif label == "heavy" and len(heavy) < TARGET_PER_LABEL:
            heavy.append(text)

    print(f"\nCollected: {len(fast)} fast  +  {len(heavy)} heavy  (scanned {scanned:,} rows)")

    all_prompts = [{"text": t, "label": "fast"}  for t in fast] + \
                  [{"text": t, "label": "heavy"} for t in heavy]

    OUT_FILE.write_text(json.dumps(all_prompts, indent=2))
    print(f"Saved {len(all_prompts)} prompts → {OUT_FILE}")
    print("Done. Now boot services and run seed_arena.py to embed + upsert.")

if __name__ == "__main__":
    main()
