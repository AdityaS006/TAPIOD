import pytest
from unittest.mock import MagicMock
from tapiod.openai import OpenAI
from tapiod.openai._models import ChatCompletion, ChatCompletionChunk


FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "heavy-openai",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

FAKE_TOOL_RESPONSE = {
    "id": "chatcmpl-2",
    "object": "chat.completion",
    "model": "heavy-openai",
    "choices": [{
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }],
        },
    }],
    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
}

FAKE_CHUNKS = [
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hello"}, "finish_reason": None}]},
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]},
    {"id": "1", "model": "heavy-openai", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
]


@pytest.fixture
def mock_transport_post(monkeypatch):
    mock = MagicMock(return_value=FAKE_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    return mock


@pytest.fixture
def mock_transport_stream(monkeypatch):
    mock = MagicMock(return_value=iter(FAKE_CHUNKS))
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", mock)
    return mock


def test_openai_create_returns_chat_completion(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert isinstance(resp, ChatCompletion)
    assert resp.choices[0].message.content == "Hello!"
    assert resp.choices[0].message.role == "assistant"
    assert resp.usage.prompt_tokens == 10
    client.close()


def test_openai_model_resolved_before_sending(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    call_payload = mock_transport_post.call_args[0][0]
    assert call_payload["model"] == "heavy-openai"
    client.close()


def test_openai_unknown_model_gets_prefixed(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Hi"}],
    )
    call_payload = mock_transport_post.call_args[0][0]
    assert call_payload["model"] == "openai/gpt-5"
    client.close()


def test_openai_tool_calls_in_response(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_TOOL_RESPONSE))
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Weather?"}],
    )
    assert resp.choices[0].message.tool_calls is not None
    tc = resp.choices[0].message.tool_calls[0]
    assert tc.id == "call_abc"
    assert tc.function.name == "get_weather"
    assert tc.function.arguments == '{"location":"NYC"}'
    client.close()


def test_openai_streaming_yields_chunks(mock_transport_stream):
    client = OpenAI(api_key="sk-fake")
    chunks = list(client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
        stream=True,
    ))
    assert len(chunks) == 3
    assert isinstance(chunks[0], ChatCompletionChunk)
    assert chunks[0].choices[0].delta.content == "Hello"
    assert chunks[1].choices[0].delta.content == " world"
    assert chunks[2].choices[0].finish_reason == "stop"
    client.close()


def test_openai_context_manager(mock_transport_post):
    with OpenAI(api_key="sk-fake") as client:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hi"}],
        )
    assert resp.choices[0].message.content == "Hello!"


def test_chat_completion_tapiod_trace_none_when_absent(mock_transport_post):
    client = OpenAI(api_key="sk-fake")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert resp._tapiod_trace is None
    client.close()
