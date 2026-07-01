import json
import pytest
from tapiod._core.converters import (
    anthropic_request_to_openai,
    openai_response_to_anthropic,
    gemini_request_to_openai,
    openai_response_to_gemini,
)


# ── Anthropic request translation ─────────────────────────────────────────────

def test_anthropic_system_prepended_as_message():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
        system="You are helpful.",
    )
    assert result["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert result["messages"][1] == {"role": "user", "content": "Hi"}


def test_anthropic_no_system_no_prepend():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=100,
    )
    assert result["messages"][0]["role"] == "user"


def test_anthropic_tool_converted_to_openai_format():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[{"role": "user", "content": "What's the weather?"}],
        max_tokens=100,
        tools=[{
            "name": "get_weather",
            "description": "Get weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }],
    )
    tool = result["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "get_weather"
    assert tool["function"]["parameters"]["type"] == "object"


def test_anthropic_max_tokens_passed_through():
    result = anthropic_request_to_openai(
        model="heavy-anthropic",
        messages=[],
        max_tokens=512,
    )
    assert result["max_tokens"] == 512


# ── Anthropic response translation ────────────────────────────────────────────

OPENAI_TEXT_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "heavy-anthropic",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
    }],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

OPENAI_TOOL_RESPONSE = {
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


def test_anthropic_response_text_block():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["role"] == "assistant"
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello!"


def test_anthropic_response_stop_reason_mapped():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["stop_reason"] == "end_turn"


def test_anthropic_response_tool_calls_mapped():
    result = openai_response_to_anthropic(OPENAI_TOOL_RESPONSE)
    assert result["stop_reason"] == "tool_use"
    block = result["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "get_weather"
    assert block["input"] == {"location": "NYC"}


def test_anthropic_response_usage_mapped():
    result = openai_response_to_anthropic(OPENAI_TEXT_RESPONSE)
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


# ── Gemini request translation ─────────────────────────────────────────────────

def test_gemini_string_contents_becomes_user_message():
    result = gemini_request_to_openai(model="heavy-gemini", contents="What is 2+2?")
    assert result["messages"][-1] == {"role": "user", "content": "What is 2+2?"}


def test_gemini_system_instruction_prepended():
    result = gemini_request_to_openai(
        model="heavy-gemini",
        contents="Hi",
        system_instruction="You are a math tutor.",
    )
    assert result["messages"][0] == {"role": "system", "content": "You are a math tutor."}


def test_gemini_list_contents_with_model_role():
    result = gemini_request_to_openai(
        model="heavy-gemini",
        contents=[
            {"role": "user", "parts": ["Hello"]},
            {"role": "model", "parts": ["Hi there"]},
            {"role": "user", "parts": ["What is 2+2?"]},
        ],
    )
    messages = result["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


# ── Gemini response translation ───────────────────────────────────────────────

OPENAI_GEMINI_RESPONSE = {
    "id": "chatcmpl-3",
    "model": "heavy-gemini",
    "choices": [{
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": "4"},
    }],
    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
}


def test_gemini_response_candidate_text():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    candidate = result["candidates"][0]
    assert candidate["content"]["parts"][0]["text"] == "4"
    assert candidate["content"]["role"] == "model"


def test_gemini_response_finish_reason_mapped():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    assert result["candidates"][0]["finish_reason"] == "STOP"


def test_gemini_response_usage_metadata():
    result = openai_response_to_gemini(OPENAI_GEMINI_RESPONSE)
    meta = result["usage_metadata"]
    assert meta["prompt_token_count"] == 8
    assert meta["candidates_token_count"] == 1
    assert meta["total_token_count"] == 9
