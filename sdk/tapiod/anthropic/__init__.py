from __future__ import annotations
import os
from typing import Iterator, AsyncIterator

from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod._core.converters import anthropic_request_to_openai, openai_response_to_anthropic
from tapiod.anthropic._models import Message


_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")


class _MessageStreamManager:
    def __init__(self, transport: TapiodTransport, payload: dict):
        self._t = transport
        self._payload = payload
        self._final: Message | None = None

    def __enter__(self) -> "_MessageStreamManager":
        return self

    def __exit__(self, *_) -> None:
        pass

    @property
    def text_stream(self) -> Iterator[str]:
        full_text = ""
        for chunk_dict in self._t.stream(self._payload):
            delta = (chunk_dict.get("choices") or [{}])[0].get("delta", {})
            token = delta.get("content")
            if token:
                full_text += token
                yield token
        self._final = Message({
            "id": "",
            "model": self._payload.get("model", ""),
            "role": "assistant",
            "content": [{"type": "text", "text": full_text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })

    def get_final_message(self) -> Message:
        if self._final is None:
            for _ in self.text_stream:
                pass
        return self._final  # type: ignore[return-value]


class _Messages:
    def __init__(self, transport: TapiodTransport):
        self._t = transport

    def create(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Message:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            **kwargs,
        )
        raw = self._t.post(payload)
        return Message(openai_response_to_anthropic(raw))

    def stream(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        **kwargs,
    ) -> _MessageStreamManager:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            **kwargs,
        )
        return _MessageStreamManager(self._t, payload)


class Anthropic:
    """
    Drop-in replacement for anthropic.Anthropic.

    Change only the import:
        from tapiod.anthropic import Anthropic

    Usage::
        client = Anthropic(api_key="sk-ant-...")
        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hi"}],
        )
        print(resp.content[0].text)
    """

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
        self.messages = _Messages(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Anthropic":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class _AsyncMessageStreamManager:
    def __init__(self, transport: AsyncTapiodTransport, payload: dict):
        self._t = transport
        self._payload = payload
        self._final: Message | None = None

    async def __aenter__(self) -> "_AsyncMessageStreamManager":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._astream()

    async def _astream(self) -> AsyncIterator[str]:
        full_text = ""
        async for chunk_dict in self._t.stream(self._payload):
            delta = (chunk_dict.get("choices") or [{}])[0].get("delta", {})
            token = delta.get("content")
            if token:
                full_text += token
                yield token
        self._final = Message({
            "id": "",
            "model": self._payload.get("model", ""),
            "role": "assistant",
            "content": [{"type": "text", "text": full_text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })

    async def get_final_message(self) -> Message:
        if self._final is None:
            async for _ in self._astream():
                pass
        return self._final  # type: ignore[return-value]


class _AsyncMessages:
    def __init__(self, transport: AsyncTapiodTransport):
        self._t = transport

    async def create(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Message:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            **kwargs,
        )
        raw = await self._t.post(payload)
        return Message(openai_response_to_anthropic(raw))

    def stream(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        system: str | None = None,
        **kwargs,
    ) -> _AsyncMessageStreamManager:
        resolved = resolve_model(model, "anthropic")
        payload = anthropic_request_to_openai(
            model=resolved,
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            **kwargs,
        )
        return _AsyncMessageStreamManager(self._t, payload)


class AsyncAnthropic:
    """Drop-in replacement for anthropic.AsyncAnthropic."""

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
        self.messages = _AsyncMessages(self._transport)

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncAnthropic":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()


__all__ = ["Anthropic", "AsyncAnthropic"]
