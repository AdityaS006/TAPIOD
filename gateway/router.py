import json
import os
from pathlib import Path

PROVIDER_COST_RANK = {
    "fast-groq":       0.06,
    "fast-openai":     0.60,
    "fast-anthropic":  15.00,
    "heavy-groq":      0.89,
    "heavy-openai":    10.00,
    "heavy-anthropic": 25.00,
}

MODEL_MAP = {
    "fast-groq":       "groq/llama-3.1-8b-instant",
    "fast-openai":     "openai/gpt-4o-mini",
    "fast-anthropic":  "anthropic/claude-sonnet-4-6",
    "heavy-groq":      "groq/llama-3.3-70b-versatile",
    "heavy-openai":    "openai/gpt-4o",
    "heavy-anthropic": "anthropic/claude-opus-4-8",
}

_CONFIG_PATH = Path(__file__).parent / "routing_config.json"


def load_routing_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {
            "complexity_threshold": 0.5,
            "cache_similarity_threshold": 0.85,
            "cache_ttl_seconds": 3600,
            "tiers": {"fast": ["fast-groq"], "heavy": ["heavy-groq"]},
        }


def save_routing_config(config: dict):
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def knn_classify(qdrant, vec: list, top_k: int = 5) -> float:
    """Returns complexity score 0.0-1.0. >= threshold -> heavy tier."""
    try:
        results = qdrant.query_points(
            collection_name="routing_examples",
            query=vec,
            limit=top_k,
        )
        votes = [r.payload.get("label", "heavy") for r in results.points]
        if not votes:
            return 0.5
        return votes.count("heavy") / len(votes)
    except Exception:
        return 0.5


def get_available_providers() -> list[str]:
    available = []
    if os.getenv("GROQ_API_KEY"):
        available += ["fast-groq", "heavy-groq"]
    if os.getenv("OPENAI_API_KEY"):
        available += ["fast-openai", "heavy-openai"]
    if os.getenv("ANTHROPIC_API_KEY"):
        available += ["fast-anthropic", "heavy-anthropic"]
    return available or ["heavy-groq"]


def pick_provider(available: list[str], complexity_score: float) -> str:
    config = load_routing_config()
    threshold = config.get("complexity_threshold", 0.5)
    tier = "heavy" if complexity_score >= threshold else "fast"

    priority_list = config.get("tiers", {}).get(tier, [])
    # Use priority order from config, filtered to only what's available
    ordered_candidates = [p for p in priority_list if p in available]

    if not ordered_candidates:
        # Fall back to cost-rank ordering when no priority entries are available
        ordered_candidates = sorted(
            [p for p in available if p.startswith(tier)],
            key=lambda p: PROVIDER_COST_RANK.get(p, 999),
        )

    if not ordered_candidates:
        ordered_candidates = sorted(available, key=lambda p: PROVIDER_COST_RANK.get(p, 999))

    return ordered_candidates[0] if ordered_candidates else "heavy-groq"


def get_costliest_available_model(available: list[str]) -> str:
    """Returns the litellm model string for the most expensive model in `available`."""
    try:
        from litellm import cost_per_token
        best_alias = available[0]
        best_cost = 0.0
        for alias in available:
            model = MODEL_MAP.get(alias)
            if not model:
                continue
            try:
                _, out = cost_per_token(
                    model=model, prompt_tokens=1000, completion_tokens=500
                )
                if out > best_cost:
                    best_cost = out
                    best_alias = alias
            except Exception:
                continue
        return MODEL_MAP.get(best_alias, "groq/llama-3.3-70b-versatile")
    except Exception:
        return "groq/llama-3.3-70b-versatile"


def compute_routing_save(
    chosen: str, available: list[str], prompt_tokens: int, completion_tokens: int
) -> float:
    """Estimate USD saved vs calling the costliest available model directly."""
    try:
        from litellm import cost_per_token
        baseline_model = get_costliest_available_model(available)
        chosen_model = MODEL_MAP.get(chosen, "groq/llama-3.1-8b-instant")
        base_in, base_out = cost_per_token(
            model=baseline_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        cho_in, cho_out = cost_per_token(
            model=chosen_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return max(0.0, (base_in + base_out) - (cho_in + cho_out))
    except Exception:
        return 0.0
