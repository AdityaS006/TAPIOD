from __future__ import annotations
import json


# ── Anthropic ────────────────────────────────────────────────────────────────

def anthropic_request_to_openai(
    model: str,
    messages: list[dict],
    max_tokens: int,
    system: str | None = None,
    tools: list[dict] | None = None,
    **kwargs,
) -> dict:
    oai_messages: list[dict] = []
    if system:
        oai_messages.append({"role": "system", "content": system})
    oai_messages.extend(messages)

    payload: dict = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": max_tokens,
        **kwargs,
    }
    if tools:
        payload["tools"] = [_anthropic_tool_to_openai(t) for t in tools]
    return payload


def _anthropic_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


_STOP_REASON_MAP: dict[str, str] = {
    "stop":       "end_turn",
    "tool_calls": "tool_use",
    "length":     "max_tokens",
}


def openai_response_to_anthropic(raw: dict) -> dict:
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = raw.get("usage", {})

    content: list[dict] = []
    text = message.get("content")
    if text:
        content.append({"type": "text", "text": text})

    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            inp = json.loads(fn.get("arguments", "{}"))
        except Exception:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": inp,
        })

    return {
        "id": raw.get("id", ""),
        "model": raw.get("model", ""),
        "role": "assistant",
        "content": content,
        "stop_reason": _STOP_REASON_MAP.get(finish_reason, "end_turn"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
        "_tapiod_trace": raw.get("_tapiod_trace"),
    }


# ── Gemini ───────────────────────────────────────────────────────────────────

def gemini_request_to_openai(
    model: str,
    contents,
    system_instruction: str | None = None,
    **kwargs,
) -> dict:
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        for item in contents:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
            elif isinstance(item, dict):
                role = "assistant" if item.get("role") == "model" else item.get("role", "user")
                parts = item.get("parts", [])
                text = " ".join(
                    p if isinstance(p, str) else p.get("text", "") for p in parts
                )
                messages.append({"role": role, "content": text})

    return {"model": model, "messages": messages, **kwargs}


_FINISH_REASON_GEMINI: dict[str, str] = {
    "stop":   "STOP",
    "length": "MAX_TOKENS",
    "safety": "SAFETY",
}


def openai_response_to_gemini(raw: dict) -> dict:
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")
    usage = raw.get("usage", {})

    return {
        "candidates": [{
            "content": {
                "parts": [{"text": message.get("content", "")}],
                "role": "model",
            },
            "finish_reason": _FINISH_REASON_GEMINI.get(finish_reason, "STOP"),
            "index": 0,
        }],
        "usage_metadata": {
            "prompt_token_count": usage.get("prompt_tokens", 0),
            "candidates_token_count": usage.get("completion_tokens", 0),
            "total_token_count": usage.get("total_tokens", 0),
        },
        "_tapiod_trace": raw.get("_tapiod_trace"),
    }
