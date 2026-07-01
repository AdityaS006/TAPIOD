from __future__ import annotations
import os
from typing import Iterator, AsyncIterator

from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod.openai._models import ChatCompletion, ChatCompletionChunk

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")


class _Completions:
    def __init__(self, transport: TapiodTransport):
        self._t = transport

    def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]:
        payload = {"model": resolve_model(model, "groq"), "messages": messages, **kwargs}
        if stream:
            return self._stream(payload)
        return ChatCompletion(self._t.post(payload))

    def _stream(self, payload: dict) -> Iterator[ChatCompletionChunk]:
        for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _Chat:
    def __init__(self, transport: TapiodTransport):
        self.completions = _Completions(transport)


class Groq:
    """Drop-in replacement for groq.Groq. Groq's SDK is an OpenAI fork — identical interface."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key, timeout)
        self.chat = _Chat(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Groq":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _AsyncCompletions:
    def __init__(self, transport: AsyncTapiodTransport):
        self._t = transport

    async def create(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion:
        payload = {"model": resolve_model(model, "groq"), "messages": messages, **kwargs}
        if stream:
            return self._astream(payload)  # type: ignore[return-value]
        raw = await self._t.post(payload)
        return ChatCompletion(raw)

    async def _astream(self, payload: dict) -> AsyncIterator[ChatCompletionChunk]:
        async for chunk_dict in self._t.stream(payload):
            yield ChatCompletionChunk(chunk_dict)


class _AsyncChat:
    def __init__(self, transport: AsyncTapiodTransport):
        self.completions = _AsyncCompletions(transport)


class AsyncGroq:
    """Drop-in replacement for groq.AsyncGroq."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        **kwargs,
    ):
        url = base_url or os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = AsyncTapiodTransport(url, key, timeout)
        self.chat = _AsyncChat(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncGroq":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


__all__ = ["Groq", "AsyncGroq"]
