from __future__ import annotations
import json
import os
from typing import Iterator, AsyncIterator
import httpx

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")
_PATH = "/api/agent/chat/completions"


class TapiodTransport:
    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def post(self, payload: dict) -> dict:
        resp = self._http.post(
            self.base_url + _PATH,
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def stream(self, payload: dict) -> Iterator[dict]:
        with self._http.stream(
            "POST",
            self.base_url + _PATH,
            json={**payload, "stream": True},
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("[DONE]", ""):
                    break
                if data.startswith("[TRACE]"):
                    continue
                try:
                    yield json.loads(data)
                except Exception:
                    continue

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TapiodTransport":
        return self

    def __exit__(self, *_) -> None:
        self.close()


class AsyncTapiodTransport:
    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        api_key: str = _DEFAULT_KEY,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def post(self, payload: dict) -> dict:
        resp = await self._http.post(
            self.base_url + _PATH,
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def stream(self, payload: dict) -> AsyncIterator[dict]:
        async with self._http.stream(
            "POST",
            self.base_url + _PATH,
            json={**payload, "stream": True},
            headers=self._headers(),
        ) as resp:
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
                    yield json.loads(data)
                except Exception:
                    continue

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncTapiodTransport":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
