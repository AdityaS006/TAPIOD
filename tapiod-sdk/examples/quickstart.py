"""
TAPIOD Quickstart

Before running:
  export TAPIOD_URL=http://localhost:4001
  export TAPIOD_API_KEY=tapiod          # or your real key

  pip install -e /path/to/tapiod-sdk
"""
from tapiod import TapiodClient

with TapiodClient() as client:
    # --- Non-streaming ---
    resp = client.chat.completions.create(
        model="fast-groq",
        messages=[{"role": "user", "content": "What is 2 + 2? One line answer."}],
    )
    print("Response:", resp.content)

    if resp.trace:
        print(f"Model   : {resp.trace.provider_model}")
        print(f"Cost    : ${resp.trace.actual_cost_usd:.6f}")
        print(f"Saved   : ${resp.trace.total_saved_usd:.6f}")
        print(f"Cache   : {resp.trace.cache_source or 'miss'}")
        print("Pipeline:", " → ".join(s.layer for s in resp.trace.pipeline))

    print()

    # --- Streaming ---
    print("Streaming response: ", end="", flush=True)
    for token in client.chat.completions.create(
        model="fast-groq",
        messages=[{"role": "user", "content": "Count from 1 to 5, space-separated."}],
        stream=True,
    ):
        print(token, end="", flush=True)
    print()
