import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import pytest
from io import BytesIO
from fastapi.testclient import TestClient


# ── helper function tests ────────────────────────────────────────────────────

def test_is_tool_def_single_object():
    from main import _is_tool_def
    assert _is_tool_def({"name": "get_weather", "parameters": {"type": "object"}}) is True

def test_is_tool_def_array():
    from main import _is_tool_def
    data = [
        {"name": "tool_a", "parameters": {}},
        {"name": "tool_b", "parameters": {}},
    ]
    assert _is_tool_def(data) is True

def test_is_tool_def_plain_json():
    from main import _is_tool_def
    assert _is_tool_def({"key": "value", "other": 123}) is False

def test_is_tool_def_array_missing_keys():
    from main import _is_tool_def
    assert _is_tool_def([{"name": "x"}]) is False  # missing "parameters"

def test_to_toon_returns_string_with_header():
    from main import _to_toon
    data = {"name": "greet", "parameters": {"type": "object", "properties": {}}}
    result = _to_toon(data)
    assert isinstance(result, str)
    assert "# TOON" in result
    assert "greet" in result

def test_to_toon_array():
    from main import _to_toon
    data = [{"name": "a", "parameters": {}}, {"name": "b", "parameters": {}}]
    result = _to_toon(data)
    assert "# TOON" in result
    assert '"a"' in result and '"b"' in result


# ── endpoint tests ───────────────────────────────────────────────────────────

def test_extract_text_file():
    from main import app
    client = TestClient(app)
    content = b"def hello():\n    return 'world'\n"
    resp = client.post(
        "/api/extract",
        files={"file": ("hello.py", BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "hello" in data["text"]
    assert data["toon_available"] is False

def test_extract_plain_json():
    from main import app
    client = TestClient(app)
    payload = json.dumps({"config": {"retries": 3}}).encode()
    resp = client.post(
        "/api/extract",
        files={"file": ("config.json", BytesIO(payload), "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "retries" in data["text"]
    assert data["toon_available"] is False

def test_extract_tool_def_json():
    from main import app
    client = TestClient(app)
    payload = json.dumps([
        {"name": "get_weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}},
    ]).encode()
    resp = client.post(
        "/api/extract",
        files={"file": ("tools.json", BytesIO(payload), "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["toon_available"] is True
    assert data["toon"] is not None
    assert "# TOON" in data["toon"]

def test_extract_unknown_binary_returns_422():
    from main import app
    client = TestClient(app)
    resp = client.post(
        "/api/extract",
        files={"file": ("data.bin", BytesIO(b"\x00\x01\x02\x03"), "application/octet-stream")},
    )
    assert resp.status_code == 422
