from __future__ import annotations
from tapiod.models import TapiodTrace


class Part:
    def __init__(self, d: dict):
        self.text: str = d.get("text", "")


class Content:
    def __init__(self, d: dict):
        self.parts: list[Part] = [Part(p) for p in d.get("parts", [])]
        self.role: str = d.get("role", "model")


class FinishReason:
    STOP = "STOP"
    MAX_TOKENS = "MAX_TOKENS"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class Candidate:
    def __init__(self, d: dict):
        self.content = Content(d.get("content", {}))
        self.finish_reason: str = d.get("finish_reason", FinishReason.STOP)
        self.index: int = d.get("index", 0)


class UsageMetadata:
    def __init__(self, d: dict):
        self.prompt_token_count: int = d.get("prompt_token_count", 0)
        self.candidates_token_count: int = d.get("candidates_token_count", 0)
        self.total_token_count: int = d.get("total_token_count", 0)


class GenerateContentResponse:
    def __init__(self, data: dict):
        self.candidates: list[Candidate] = [
            Candidate(c) for c in data.get("candidates", [])
        ]
        self.usage_metadata = UsageMetadata(data.get("usage_metadata", {}))
        raw_trace = data.get("_tapiod_trace")
        self._tapiod_trace: TapiodTrace | None = (
            TapiodTrace.from_dict(raw_trace) if raw_trace else None
        )

    @property
    def text(self) -> str:
        try:
            return self.candidates[0].content.parts[0].text
        except (IndexError, AttributeError):
            return ""

    def __repr__(self) -> str:
        return f"<GenerateContentResponse text={self.text[:60]!r}>"
