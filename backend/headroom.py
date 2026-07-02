"""
Context-window compression for the TAPIOD pipeline.

compress(messages, model) trims a conversation so it fits comfortably inside
the model's context limit. Old messages are pruned from the front (keeping the
system prompt and the most recent turns) until the token count is under the
target budget. Returns a CompressResult with the (possibly shortened) message
list and savings stats.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import tiktoken

# Tokens reserved for the model's response
_RESPONSE_RESERVE = 1_024

# Context limits per tiktoken encoding name / model family
_CTX_LIMITS: dict[str, int] = {
    "gpt-4o":        128_000,
    "gpt-4o-mini":   128_000,
    "gpt-4":          8_192,
    "gpt-3.5-turbo": 16_385,
    # Anthropic – headroom uses gpt-4o-mini as a proxy; map explicitly
    "claude-opus-4-20250514": 200_000,
    "claude-sonnet-4-5":      200_000,
}

_DEFAULT_CTX = 128_000


def _get_encoding(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens(messages: list[dict[str, Any]], enc: tiktoken.Encoding) -> int:
    total = 0
    for m in messages:
        # 4 overhead tokens per message (role + framing)
        total += 4 + len(enc.encode(str(m.get("content") or "")))
    return total


@dataclass
class CompressResult:
    messages: list[dict[str, Any]]
    tokens_saved: int
    compression_ratio: float
    original_tokens: int = field(default=0, repr=False)
    final_tokens: int = field(default=0, repr=False)


def compress(messages: list[dict[str, Any]], model: str = "gpt-4o") -> CompressResult:
    """
    Trim messages to fit within the model's context window.

    Keeps:
    - All system messages (always first)
    - The most recent messages

    Drops middle turns (oldest non-system messages) until the budget is met.
    """
    enc = _get_encoding(model)
    ctx_limit = _CTX_LIMITS.get(model, _DEFAULT_CTX)
    budget = ctx_limit - _RESPONSE_RESERVE

    original_tokens = _count_tokens(messages, enc)

    if original_tokens <= budget:
        return CompressResult(
            messages=messages,
            tokens_saved=0,
            compression_ratio=1.0,
            original_tokens=original_tokens,
            final_tokens=original_tokens,
        )

    # Separate system messages from conversational turns
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conv_msgs   = [m for m in messages if m.get("role") != "system"]

    system_tokens = _count_tokens(system_msgs, enc)
    conv_budget   = budget - system_tokens

    # Greedily keep messages from the end until we exceed the budget
    kept: list[dict[str, Any]] = []
    used = 0
    for msg in reversed(conv_msgs):
        cost = 4 + len(enc.encode(str(msg.get("content") or "")))
        if used + cost > conv_budget:
            break
        kept.insert(0, msg)
        used += cost

    trimmed = system_msgs + kept
    final_tokens = _count_tokens(trimmed, enc)
    saved = original_tokens - final_tokens

    ratio = final_tokens / original_tokens if original_tokens > 0 else 1.0

    return CompressResult(
        messages=trimmed,
        tokens_saved=saved,
        compression_ratio=ratio,
        original_tokens=original_tokens,
        final_tokens=final_tokens,
    )
