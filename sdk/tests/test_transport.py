import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from tapiod._transport import TapiodTransport, AsyncTapiodTransport


FAKE_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "fast-groq",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


def test_transport_post_returns_dict():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        result = t.post({"model": "fast-groq", "messages": []})
        assert result == FAKE_RESPONSE
        t.close()


def test_transport_post_sends_auth_header():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        t = TapiodTransport(base_url="http://localhost:4001", api_key="my-key")
        t.post({"model": "fast-groq", "messages": []})
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-key"
        t.close()


def test_transport_stream_yields_chunk_dicts():
    chunk1 = {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None, "index": 0}]}
    chunk2 = {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop", "index": 0}]}

    sse_lines = [
        f"data: {json.dumps(chunk1)}",
        f"data: {json.dumps(chunk2)}",
        "data: [DONE]",
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = iter(sse_lines)
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client.stream", return_value=mock_resp):
        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        chunks = list(t.stream({"model": "fast-groq", "messages": []}))
        assert len(chunks) == 2
        assert chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert chunks[1]["choices"][0]["delta"]["content"] == " world"
        t.close()


def test_transport_stream_skips_trace_lines():
    sse_lines = [
        'data: {"choices": [{"delta": {"content": "Hi"}, "finish_reason": null, "index": 0}]}',
        "data: [DONE]",
        "data: [TRACE]{...}",
    ]

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = iter(sse_lines)
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client.stream", return_value=mock_resp):
        t = TapiodTransport(base_url="http://localhost:4001", api_key="test")
        chunks = list(t.stream({"model": "fast-groq", "messages": []}))
        assert len(chunks) == 1
        t.close()


def test_transport_context_manager():
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with TapiodTransport(base_url="http://localhost:4001", api_key="test") as t:
            result = t.post({"model": "fast-groq", "messages": []})
        assert result == FAKE_RESPONSE
