import pytest
from unittest.mock import MagicMock
from tapiod.groq import Groq, AsyncGroq
from tapiod.openai._models import ChatCompletion

FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "fast-groq",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hi", "tool_calls": None}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def test_groq_client_exists():
    client = Groq(api_key="gsk_fake")
    assert hasattr(client, "chat")
    assert hasattr(client.chat, "completions")
    client.close()


def test_groq_model_resolved_to_tapiod_alias(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Groq(api_key="gsk_fake")
    client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "Hi"}],
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "fast-groq"
    client.close()


def test_groq_unknown_model_gets_groq_prefix(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Groq(api_key="gsk_fake")
    client.chat.completions.create(
        model="llama-4-scout",
        messages=[{"role": "user", "content": "Hi"}],
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "groq/llama-4-scout"
    client.close()


def test_async_groq_client_exists():
    client = AsyncGroq(api_key="gsk_fake")
    assert hasattr(client, "chat")
