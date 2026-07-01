from __future__ import annotations
from tapiod.models import TapiodTrace


class ToolCallFunction:
    def __init__(self, d: dict):
        self.name: str = d.get("name", "")
        self.arguments: str = d.get("arguments", "")


class ToolCall:
    def __init__(self, d: dict):
        self.id: str = d.get("id", "")
        self.type: str = d.get("type", "function")
        self.function = ToolCallFunction(d.get("function", {}))


class ChatCompletionMessage:
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
        self.message = ChatCompletionMessage(d.get("message", {}))
        self.finish_reason: str | None = d.get("finish_reason")


class CompletionUsage:
    def __init__(self, d: dict):
        self.prompt_tokens: int = d.get("prompt_tokens", 0)
        self.completion_tokens: int = d.get("completion_tokens", 0)
        self.total_tokens: int = d.get("total_tokens", 0)


class ChatCompletion:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.object: str = data.get("object", "chat.completion")
        self.model: str = data.get("model", "")
        self.choices: list[Choice] = [Choice(c) for c in data.get("choices", [])]
        self.usage = CompletionUsage(data.get("usage", {}))
        raw_trace = data.get("_tapiod_trace")
        self._tapiod_trace: TapiodTrace | None = (
            TapiodTrace.from_dict(raw_trace) if raw_trace else None
        )

    def __repr__(self) -> str:
        content = self.choices[0].message.content if self.choices else ""
        return f"<ChatCompletion model={self.model!r} content={str(content)[:60]!r}>"


class ChoiceDelta:
    def __init__(self, d: dict):
        self.role: str | None = d.get("role")
        self.content: str | None = d.get("content")
        raw_tc = d.get("tool_calls")
        self.tool_calls: list | None = raw_tc if raw_tc else None


class ChunkChoice:
    def __init__(self, d: dict):
        self.index: int = d.get("index", 0)
        self.delta = ChoiceDelta(d.get("delta", {}))
        self.finish_reason: str | None = d.get("finish_reason")


class ChatCompletionChunk:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.model: str = data.get("model", "")
        self.choices: list[ChunkChoice] = [
            ChunkChoice(c) for c in data.get("choices", [])
        ]
