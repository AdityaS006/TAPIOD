from __future__ import annotations
from tapiod.models import TapiodTrace


class TextBlock:
    def __init__(self, d: dict):
        self.type: str = "text"
        self.text: str = d.get("text", "")


class ToolUseBlock:
    def __init__(self, d: dict):
        self.type: str = "tool_use"
        self.id: str = d.get("id", "")
        self.name: str = d.get("name", "")
        self.input: dict = d.get("input", {})


class Usage:
    def __init__(self, d: dict):
        self.input_tokens: int = d.get("input_tokens", 0)
        self.output_tokens: int = d.get("output_tokens", 0)


class Message:
    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.model: str = data.get("model", "")
        self.role: str = data.get("role", "assistant")
        self.stop_reason: str = data.get("stop_reason", "end_turn")
        self.usage = Usage(data.get("usage", {}))
        raw_trace = data.get("_tapiod_trace")
        self._tapiod_trace: TapiodTrace | None = (
            TapiodTrace.from_dict(raw_trace) if raw_trace else None
        )

        raw_content = data.get("content", [])
        self.content: list[TextBlock | ToolUseBlock] = []
        for block in raw_content:
            if block.get("type") == "tool_use":
                self.content.append(ToolUseBlock(block))
            else:
                self.content.append(TextBlock(block))

    def __repr__(self) -> str:
        text = self.content[0].text if self.content and isinstance(self.content[0], TextBlock) else ""
        return f"<Message role={self.role!r} stop_reason={self.stop_reason!r} text={text[:60]!r}>"
