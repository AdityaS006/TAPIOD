import pytest
from tapiod.models import Message, ToolCall, ToolCallFunction, ChatCompletion


def test_message_tool_calls_none_when_absent():
    msg = Message({"role": "assistant", "content": "Hello"})
    assert msg.tool_calls is None


def test_message_tool_calls_parsed_when_present():
    msg = Message({
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }
        ],
    })
    assert msg.tool_calls is not None
    assert len(msg.tool_calls) == 1
    tc = msg.tool_calls[0]
    assert tc.id == "call_abc"
    assert tc.type == "function"
    assert tc.function.name == "get_weather"
    assert tc.function.arguments == '{"location":"NYC"}'


def test_message_content_can_be_none():
    msg = Message({"role": "assistant", "content": None})
    assert msg.content is None


def test_chat_completion_tool_calls_accessible():
    raw = {
        "id": "chatcmpl-1",
        "model": "fast-groq",
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_xyz",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"q":"test"}'},
                }],
            },
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    resp = ChatCompletion(raw)
    assert resp.choices[0].message.tool_calls is not None
    assert resp.choices[0].message.tool_calls[0].function.name == "search"
