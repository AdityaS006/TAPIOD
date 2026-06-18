import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock
from router import knn_classify, pick_provider, PROVIDER_COST_RANK

def _make_qdrant_mock(labels: list[str]):
    mock = MagicMock()
    points = []
    for label in labels:
        p = MagicMock()
        p.payload = {"label": label}
        points.append(p)
    mock.query_points.return_value.points = points
    return mock

def test_knn_classify_majority_fast():
    qdrant = _make_qdrant_mock(["fast", "fast", "fast", "heavy", "fast"])
    score = knn_classify(qdrant, [0.1] * 384)
    assert score < 0.5

def test_knn_classify_majority_heavy():
    qdrant = _make_qdrant_mock(["heavy", "heavy", "heavy", "fast", "heavy"])
    score = knn_classify(qdrant, [0.1] * 384)
    assert score >= 0.5

def test_knn_classify_defaults_on_error():
    qdrant = MagicMock()
    qdrant.query_points.side_effect = Exception("qdrant down")
    score = knn_classify(qdrant, [0.1] * 384)
    assert score == 0.5

def test_pick_provider_selects_cheapest_fast():
    available = ["fast-groq", "fast-openai", "heavy-groq"]
    provider = pick_provider(available, complexity_score=0.2)
    assert provider == "fast-groq"

def test_pick_provider_selects_cheapest_heavy():
    available = ["fast-groq", "heavy-groq", "heavy-openai"]
    provider = pick_provider(available, complexity_score=0.8)
    assert provider == "heavy-groq"

def test_pick_provider_falls_back_when_tier_unavailable():
    available = ["heavy-groq"]
    provider = pick_provider(available, complexity_score=0.1)
    assert provider == "heavy-groq"

def test_get_available_providers_includes_anthropic_fast(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from router import get_available_providers
    result = get_available_providers()
    assert "fast-anthropic" in result
    assert "heavy-anthropic" in result

def test_provider_cost_rank_has_anthropic():
    from router import PROVIDER_COST_RANK
    assert "fast-anthropic" in PROVIDER_COST_RANK
    assert "heavy-anthropic" in PROVIDER_COST_RANK
    assert PROVIDER_COST_RANK["heavy-anthropic"] > PROVIDER_COST_RANK["fast-anthropic"]
