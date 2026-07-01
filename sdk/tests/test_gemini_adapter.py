import pytest
from unittest.mock import MagicMock
import tapiod.google.generativeai as genai
from tapiod.google.generativeai import GenerativeModel
from tapiod.google.generativeai._models import GenerateContentResponse, Part

FAKE_OAI_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-gemini",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "4"},
    }],
    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
}


def test_configure_does_not_raise():
    genai.configure(api_key="AIzaSy_fake")


def test_generate_content_returns_response(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert isinstance(resp, GenerateContentResponse)


def test_response_text_shortcut(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.text == "4"


def test_response_candidates_parts(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.candidates[0].content.parts[0].text == "4"
    assert resp.candidates[0].content.role == "model"


def test_response_usage_metadata(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    model = GenerativeModel("gemini-pro")
    resp = model.generate_content("What is 2+2?")
    assert resp.usage_metadata.prompt_token_count == 8
    assert resp.usage_metadata.candidates_token_count == 1
    assert resp.usage_metadata.total_token_count == 9


def test_model_resolved_to_tapiod_alias(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["model"] == "heavy-gemini"


def test_unknown_model_gets_gemini_prefix(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-2.0-ultra")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["model"] == "gemini/gemini-2.0-ultra"


def test_system_instruction_prepended(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro", system_instruction="You are a tutor.")
    model.generate_content("Hi")
    payload = mock.call_args[0][0]
    assert payload["messages"][0] == {"role": "system", "content": "You are a tutor."}


def test_list_contents_with_model_role(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    model = GenerativeModel("gemini-pro")
    model.generate_content([
        {"role": "user", "parts": ["Hello"]},
        {"role": "model", "parts": ["Hi"]},
        {"role": "user", "parts": ["2+2?"]},
    ])
    payload = mock.call_args[0][0]
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["user", "assistant", "user"]
