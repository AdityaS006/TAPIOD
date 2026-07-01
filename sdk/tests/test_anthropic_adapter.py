from unittest.mock import MagicMock
from tapiod.anthropic import Anthropic
from tapiod.anthropic._models import Message, TextBlock, ToolUseBlock

FAKE_OAI_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

FAKE_OAI_TOOL_RESPONSE = {
    "id": "chatcmpl-2",
    "model": "heavy-anthropic",
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


def test_anthropic_create_returns_message(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert isinstance(resp, Message)
    assert resp.role == "assistant"
    client.close()


def test_anthropic_text_block_in_content(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert isinstance(resp.content[0], TextBlock)
    assert resp.content[0].text == "Hello!"
    client.close()


def test_anthropic_stop_reason_end_turn(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert resp.stop_reason == "end_turn"
    client.close()


def test_anthropic_usage_tokens(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5
    client.close()


def test_anthropic_tool_use_block(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_TOOL_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Weather?"}],
        max_tokens=100,
    )
    assert resp.stop_reason == "tool_use"
    block = resp.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.name == "get_weather"
    assert block.input == {"location": "NYC"}
    client.close()


def test_anthropic_system_passed_as_param(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Anthropic(api_key="sk-ant-fake")
    client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
        system="You are helpful.",
    )
    payload = mock.call_args[0][0]
    assert payload["messages"][0] == {"role": "system", "content": "You are helpful."}
    client.close()


def test_anthropic_model_resolved(monkeypatch):
    mock = MagicMock(return_value=FAKE_OAI_RESPONSE)
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", mock)
    client = Anthropic(api_key="sk-ant-fake")
    client.messages.create(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    payload = mock.call_args[0][0]
    assert payload["model"] == "heavy-anthropic"
    client.close()


def test_anthropic_streaming_text_stream(monkeypatch):
    chunks = [
        {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None, "index": 0}]},
        {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop", "index": 0}]},
    ]
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", MagicMock(return_value=iter(chunks)))
    client = Anthropic(api_key="sk-ant-fake")
    with client.messages.stream(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    ) as stream:
        tokens = list(stream.text_stream)
    assert tokens == ["Hello", " world"]
    client.close()


def test_anthropic_streaming_get_final_message(monkeypatch):
    chunks = [
        {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None, "index": 0}]},
        {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
    ]
    monkeypatch.setattr("tapiod._transport.TapiodTransport.stream", MagicMock(return_value=iter(chunks)))
    client = Anthropic(api_key="sk-ant-fake")
    with client.messages.stream(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    ) as stream:
        for _ in stream.text_stream:
            pass
        msg = stream.get_final_message()
    assert isinstance(msg, Message)
    assert msg.content[0].text == "Hi"
    client.close()


def test_anthropic_tapiod_trace_none_when_absent(monkeypatch):
    monkeypatch.setattr("tapiod._transport.TapiodTransport.post", MagicMock(return_value=FAKE_OAI_RESPONSE))
    client = Anthropic(api_key="sk-ant-fake")
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert resp._tapiod_trace is None
    client.close()
