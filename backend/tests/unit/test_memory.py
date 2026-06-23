import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock
from memory import memory_retrieve, build_memory_system_block

def test_memory_retrieve_returns_empty_on_qdrant_error():
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.side_effect = Exception("connection error")
    result = memory_retrieve(mock_qdrant, [0.1] * 384, "u1", "t1")
    assert result == []

def test_memory_retrieve_returns_facts_above_threshold():
    mock_qdrant = MagicMock()
    mock_point = MagicMock()
    mock_point.score = 0.82
    mock_point.payload = {"fact": "User prefers Python"}
    mock_qdrant.query_points.return_value.points = [mock_point]
    result = memory_retrieve(mock_qdrant, [0.1] * 384, "u1", "t1", threshold=0.7)
    assert result == ["User prefers Python"]

def test_build_memory_block_empty():
    block = build_memory_system_block([])
    assert block == ""

def test_build_memory_block_formats_facts():
    facts = ["User prefers Python", "User is building TAPIOD"]
    block = build_memory_system_block(facts)
    assert "[Recalled context about this user]" in block
    assert "User prefers Python" in block
    assert "User is building TAPIOD" in block
