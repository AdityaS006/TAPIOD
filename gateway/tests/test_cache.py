import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
from unittest.mock import MagicMock, patch
from cache import redis_cache_key, redis_get, redis_set, qdrant_cache_get

def test_redis_key_is_deterministic():
    key1 = redis_cache_key("t1", "fast-groq", [{"role": "user", "content": "hi"}])
    key2 = redis_cache_key("t1", "fast-groq", [{"role": "user", "content": "hi"}])
    assert key1 == key2
    assert key1.startswith("tapiod:cache:")

def test_redis_key_differs_by_tenant():
    key1 = redis_cache_key("t1", "fast-groq", [{"role": "user", "content": "hi"}])
    key2 = redis_cache_key("t2", "fast-groq", [{"role": "user", "content": "hi"}])
    assert key1 != key2

def test_redis_get_returns_none_on_miss():
    mock_client = MagicMock()
    mock_client.get.return_value = None
    result = redis_get(mock_client, "t1", "fast-groq", [])
    assert result is None

def test_redis_get_returns_cached_value():
    mock_client = MagicMock()
    mock_client.get.return_value = json.dumps({"choices": [{"message": {"content": "Paris"}}]})
    result = redis_get(mock_client, "t1", "fast-groq", [{"role": "user", "content": "capital?"}])
    assert result is not None
    assert "Paris" in result

def test_qdrant_cache_get_returns_none_below_threshold():
    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.score = 0.70
    mock_point.payload = {"response": "cached answer"}
    mock_qdrant.query_points.return_value.points = [mock_point]
    result = qdrant_cache_get(mock_qdrant, [0.1] * 384, "t1", threshold=0.85)
    assert result is None

def test_qdrant_cache_get_returns_response_above_threshold():
    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.score = 0.92
    mock_point.payload = {"response": "cached answer"}
    mock_qdrant.query_points.return_value.points = [mock_point]
    result = qdrant_cache_get(mock_qdrant, [0.1] * 384, "t1", threshold=0.85)
    assert result == "cached answer"
