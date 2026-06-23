def estimate_cache_save(
    prompt: str,
    baseline_model: str,
    avg_completion_tokens: int = 150,
) -> float:
    """Estimate USD saved by serving from cache instead of calling baseline_model."""
    try:
        from litellm import cost_per_token
        prompt_tokens = int(len(prompt.split()) * 1.3)
        input_cost, output_cost = cost_per_token(
            model=baseline_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=avg_completion_tokens,
        )
        return input_cost + output_cost
    except Exception:
        return 0.0


def estimate_memory_tokens_saved(facts: list[str]) -> int:
    """Estimate tokens not sent to LLM because memory recalled them."""
    return int(sum(len(f.split()) * 1.3 for f in facts))


def seconds_to_ms(seconds: float) -> float:
    return seconds * 1000.0
