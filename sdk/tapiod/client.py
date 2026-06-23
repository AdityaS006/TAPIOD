from __future__ import annotations
import os
from typing import AsyncIterator, Iterator
import httpx
from .models import ChatCompletion


_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")
_AGENT_PATH = "/api/agent/chat/completions"


class _Completions:
    def __init__(self, client: "TapiodClient"):
        self._c = client

    def create(
        self,
        messages: list[dict],
        model: str = "fast-groq",
        stream: bool = False,
        **kwargs,
    ) -> ChatCompletion | Iterator[str]:
        payload = {"model": model, "messages": messages, **kwargs}
        headers = {"Authorization": f"Bearer {self._c.api_key}"}
        url = self._c.base_url + _AGENT_PATH

        if stream:
            return self._stream(url, headers, payload)

        resp = self._c._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return ChatCompletion(resp.json())

    def _stream(self, url: str, headers: dict, payload: dict) -> Iterator[str]:
        payload = {**payload, "stream": True}
        with self._c._http.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("[DONE]", ""):
                    break
                # Trace event sent after DONE
                if data.startswith("[TRACE]"):
                    continue
                import json
                try:
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except Exception:
                    continue


class _Chat:
    def __init__(self, client: "TapiodClient"):
        self.completions = _Completions(client)


class TapiodClient:
    """
    Sync client for the TAPIOD gateway.

    Usage::

        from tapiod import TapiodClient

        client = TapiodClient(base_url="https://your-server.com", api_key="sk-xxx")
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(resp.content)
        print(f"Saved ${resp.trace.total_saved_usd:.6f}")
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.Client(timeout=timeout)
        self.chat = _Chat(self)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class _AsyncCompletions:
    def __init__(self, client: "AsyncTapiodClient"):
        self._c = client

    async def create(
        self,
        messages: list[dict],
        model: str = "fast-groq",
        stream: bool = False,
        **kwargs,
    ) -> "ChatCompletion | AsyncIterator[str]":
        payload = {"model": model, "messages": messages, **kwargs}
        headers = {"Authorization": f"Bearer {self._c.api_key}"}
        url = self._c.base_url + _AGENT_PATH

        if stream:
            return self._astream(url, headers, payload)

        resp = await self._c._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return ChatCompletion(resp.json())

    async def _astream(
        self, url: str, headers: dict, payload: dict
    ) -> AsyncIterator[str]:
        import json as _json
        payload = {**payload, "stream": True}
        async with self._c._http.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("[DONE]", ""):
                    break
                if data.startswith("[TRACE]"):
                    continue
                try:
                    chunk = _json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except Exception:
                    continue


class _AsyncChat:
    def __init__(self, client: "AsyncTapiodClient"):
        self.completions = _AsyncCompletions(client)


class AsyncTapiodClient:
    """
    Async client for the TAPIOD gateway.

    Usage::

        async with AsyncTapiodClient(base_url="...", api_key="sk-xxx") as client:
            resp = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello!"}],
            )
            print(resp.content)
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.AsyncClient(timeout=timeout)
        self.chat = _AsyncChat(self)

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
