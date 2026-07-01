from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceStep:
    layer: str
    result: str
    latency_ms: float


@dataclass
class TapiodTrace:
    pipeline: list[TraceStep]
    actual_cost_usd: float
    total_saved_usd: float
    cache_source: str | None
    provider_model: str
    memory_tokens_saved: int

    @classmethod
    def from_dict(cls, d: dict) -> "TapiodTrace":
        return cls(
            pipeline=[
                TraceStep(
                    layer=s.get("layer", ""),
                    result=s.get("result", ""),
                    latency_ms=float(s.get("latency_ms", 0)),
                )
                for s in d.get("pipeline", [])
            ],
            actual_cost_usd=float(d.get("actual_cost_usd", 0)),
            total_saved_usd=float(d.get("total_saved_usd", 0)),
            cache_source=d.get("cache_source"),
            provider_model=d.get("provider_model", ""),
            memory_tokens_saved=int(d.get("memory_tokens_saved", 0)),
        )


class ToolCallFunction:
    def __init__(self, d: dict):
        self.name: str = d.get("name", "")
        self.arguments: str = d.get("arguments", "")


class ToolCall:
    def __init__(self, d: dict):
        self.id: str = d.get("id", "")
        self.type: str = d.get("type", "function")
        self.function = ToolCallFunction(d.get("function", {}))


class Message:
    def __init__(self, d: dict):
        self.role: str = d.get("role", "assistant")
        self.content: str | None = d.get("content")
        raw_tc = d.get("tool_calls")
        self.tool_calls: list[ToolCall] | None = (
            [ToolCall(tc) for tc in raw_tc] if raw_tc else None
        )


class Choice:
    def __init__(self, d: dict):
        self.index: int = d.get("index", 0)
        self.finish_reason: str | None = d.get("finish_reason")
        self.message = Message(d.get("message", {}))


class Usage:
    def __init__(self, d: dict):
        self.prompt_tokens: int = d.get("prompt_tokens", 0)
        self.completion_tokens: int = d.get("completion_tokens", 0)
        self.total_tokens: int = d.get("total_tokens", 0)


class ChatCompletion:
    def __init__(self, data: dict):
        self._raw = data
        self.model: str = data.get("model", "")
        self.choices: list[Choice] = [Choice(c) for c in data.get("choices", [])]
        self.usage = Usage(data.get("usage", {}))
        raw_trace = data.get("_tapiod_trace")
        self.trace: TapiodTrace | None = TapiodTrace.from_dict(raw_trace) if raw_trace else None

    @property
    def content(self) -> str:
        if self.choices:
            return self.choices[0].message.content or ""
        return ""

    def __repr__(self) -> str:
        saved = f" | saved ${self.trace.total_saved_usd:.6f}" if self.trace else ""
        return f"<ChatCompletion model={self.model!r} content={self.content[:60]!r}{saved}>"
