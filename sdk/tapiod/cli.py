from __future__ import annotations
import argparse
import json
import os
import sys
import httpx

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")
_AGENT_PATH = "/api/agent/chat/completions"

# ANSI colours
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_PURPLE = "\033[35m"


def _hr():
    print(f"{_DIM}{'─' * 60}{_RESET}")


def _trace_line(trace: dict) -> str:
    model = trace.get("provider_model", "?")
    cache = trace.get("cache_source")
    cost = trace.get("actual_cost_usd", 0)
    saved = trace.get("total_saved_usd", 0)
    if cache:
        icon = "⚡" if cache == "redis" else "🔷"
        return f"{_GREEN}{icon} {cache.upper()} HIT{_RESET}{_DIM} · {model} · $0.000000 · saved ${saved:.6f}{_RESET}"
    return f"{_DIM}cache miss · {model} · ${cost:.6f} · saved ${saved:.6f}{_RESET}"


def _send(base_url: str, api_key: str, messages: list[dict], stream: bool) -> tuple[str, dict | None]:
    """Send to gateway, return (content, trace_dict)."""
    url = base_url.rstrip("/") + _AGENT_PATH
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": "fast-groq", "messages": messages, "stream": stream}

    if stream:
        content_parts = []
        trace = None
        with httpx.Client(timeout=120.0) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            continue  # keep reading — [TRACE] comes after
                        if data.startswith("[TRACE]"):
                            try:
                                trace = json.loads(data[7:])
                            except Exception:
                                pass
                            continue
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            token = delta.get("content")
                            if token:
                                print(token, end="", flush=True)
                                content_parts.append(token)
                        except Exception:
                            continue
        print()  # newline after streamed content
        return "".join(content_parts), trace
    else:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Non-streaming: print the full response then return
        print(content)
        return content, data.get("_tapiod_trace")


def cmd_chat(args):
    """Interactive multi-turn chat session."""
    base_url = args.base_url
    api_key = args.api_key

    print(f"\n{_BOLD}{_PURPLE}  TAPIOD{_RESET}  {_DIM}connected · {base_url}{_RESET}")
    _hr()
    print(f"{_DIM}Commands: /clear  /trace  /exit{_RESET}")
    _hr()

    messages: list[dict] = []
    last_trace: dict | None = None

    while True:
        try:
            user_input = input(f"\n{_CYAN}>{_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_DIM}Bye.{_RESET}")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print(f"{_DIM}Bye.{_RESET}")
            break

        if user_input == "/clear":
            messages = []
            last_trace = None
            print(f"{_DIM}Session cleared.{_RESET}")
            continue

        if user_input == "/trace":
            if last_trace:
                print(f"\n{_BOLD}Pipeline:{_RESET}")
                for step in last_trace.get("pipeline", []):
                    print(f"  {_YELLOW}{step['layer']:20}{_RESET} {step['result']}  {_DIM}({step['latency_ms']:.1f}ms){_RESET}")
            else:
                print(f"{_DIM}No trace yet.{_RESET}")
            continue

        messages.append({"role": "user", "content": user_input})
        print()

        try:
            content, trace = _send(base_url, api_key, messages, stream=True)
            messages.append({"role": "assistant", "content": content})
            last_trace = trace

            print()
            if trace:
                print(_trace_line(trace))
            _hr()

        except httpx.ConnectError:
            print(f"{_DIM}Cannot reach {base_url} — is the gateway running?{_RESET}")
            messages.pop()
        except httpx.HTTPStatusError as e:
            print(f"{_DIM}Gateway error {e.response.status_code}{_RESET}")
            messages.pop()
        except Exception as e:
            print(f"{_DIM}Error: {e}{_RESET}")
            messages.pop()


def cmd_ask(args):
    """One-shot prompt."""
    base_url = args.base_url
    api_key = args.api_key
    prompt = " ".join(args.prompt)
    messages = [{"role": "user", "content": prompt}]

    try:
        _, trace = _send(base_url, api_key, messages, stream=True)
        if trace:
            print(f"\n{_trace_line(trace)}")
    except httpx.ConnectError:
        print(f"Cannot reach {base_url} — is the gateway running?", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Gateway error {e.response.status_code}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="tapiod",
        description="TAPIOD — smart LLM gateway client",
    )
    parser.add_argument("--base-url", default=_DEFAULT_URL, help="TAPIOD gateway URL (or set TAPIOD_URL)")
    parser.add_argument("--api-key", default=_DEFAULT_KEY, help="API key (or set TAPIOD_API_KEY)")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("chat", help="Interactive multi-turn chat session")

    ask_p = sub.add_parser("ask", help="One-shot prompt")
    ask_p.add_argument("prompt", nargs="+", help="The prompt text")

    args = parser.parse_args()

    if args.command == "chat":
        cmd_chat(args)
    elif args.command == "ask":
        cmd_ask(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
