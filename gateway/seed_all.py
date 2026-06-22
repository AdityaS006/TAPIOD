"""
One-command Qdrant seed — run this after `docker compose up -d`.

Seeds:
  1. routing_examples  — 5 000 chatbot-arena prompts (fast/heavy labels)
                         source: gateway/arena_prompts.json
  2. tool_registry     — weather tool embedding (auto-done by gateway on
                         startup, but this ensures it exists for smoke tests)

Usage:
  cd gateway
  source venv/bin/activate
  python seed_all.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(script: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Running {script}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(HERE / script)],
        cwd=HERE,
    )
    if result.returncode != 0:
        print(f"\n✗ {script} failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"✓ {script} complete")


def main() -> None:
    print("TAPIOD Qdrant Seed")
    print("Qdrant must be running at http://localhost:6333")
    print("(run `docker compose up -d` first)\n")

    run("seed_arena.py")

    print("\n✓ All collections seeded.")
    print("  routing_examples  — 5 000 pts  (fast/heavy routing labels)")
    print("  tool_registry     — seeded automatically by gateway on startup")
    print("\nStart the gateway next:")
    print("  litellm --config litellm_config.yaml --port 4000 &")
    print("  uvicorn hooks:app --port 4001 --reload")


if __name__ == "__main__":
    main()
