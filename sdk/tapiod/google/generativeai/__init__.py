from __future__ import annotations
import os
from tapiod._transport import TapiodTransport, AsyncTapiodTransport
from tapiod._core.mapping import resolve_model
from tapiod._core.converters import gemini_request_to_openai, openai_response_to_gemini
from tapiod.google.generativeai._models import GenerateContentResponse

_DEFAULT_URL = os.environ.get("TAPIOD_URL", "http://localhost:4001")
_DEFAULT_KEY = os.environ.get("TAPIOD_API_KEY", "tapiod")

_configured_api_key: str | None = None


def configure(api_key: str, **kwargs) -> None:
    """Accept api_key for drop-in compatibility. TAPIOD uses its own configured provider keys."""
    global _configured_api_key
    _configured_api_key = api_key


class GenerativeModel:
    """
    Drop-in replacement for google.generativeai.GenerativeModel.

    Change only the import:
        import tapiod.google.generativeai as genai
        genai.configure(api_key="AIza...")
        model = genai.GenerativeModel("gemini-pro")
        resp = model.generate_content("Hello")
        print(resp.text)
    """

    def __init__(
        self,
        model_name: str,
        system_instruction: str | None = None,
        **kwargs,
    ):
        self._model_name = model_name
        self._system_instruction = system_instruction
        url = os.environ.get("TAPIOD_URL", _DEFAULT_URL)
        key = os.environ.get("TAPIOD_API_KEY", _DEFAULT_KEY)
        self._transport = TapiodTransport(url, key)

    def generate_content(self, contents, **kwargs) -> GenerateContentResponse:
        resolved = resolve_model(self._model_name, "gemini")
        payload = gemini_request_to_openai(
            model=resolved,
            contents=contents,
            system_instruction=self._system_instruction,
            **kwargs,
        )
        raw = self._transport.post(payload)
        return GenerateContentResponse(openai_response_to_gemini(raw))

    def close(self) -> None:
        self._transport.close()


__all__ = ["configure", "GenerativeModel"]
