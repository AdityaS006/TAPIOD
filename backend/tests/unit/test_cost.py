import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cost import estimate_cache_save, estimate_memory_tokens_saved, seconds_to_ms


def test_estimate_memory_tokens_saved_empty():
    assert estimate_memory_tokens_saved([]) == 0


def test_estimate_memory_tokens_saved_counts_words():
    facts = ["User prefers Python", "User is building TAPIOD gateway"]
    result = estimate_memory_tokens_saved(facts)
    assert result > 0
    assert isinstance(result, int)


def test_seconds_to_ms():
    assert seconds_to_ms(1.5) == 1500.0
    assert seconds_to_ms(0.0) == 0.0


def test_estimate_cache_save_returns_float():
    result = estimate_cache_save(
        "hello world this is a test prompt",
        baseline_model="openai/gpt-4o",
    )
    assert isinstance(result, float)
    assert result >= 0.0


def test_estimate_cache_save_opus_more_expensive_than_groq():
    prompt = "Write a Python function that sorts a list."
    groq_save = estimate_cache_save(prompt, baseline_model="groq/llama-3.1-8b-instant")
    opus_save = estimate_cache_save(prompt, baseline_model="anthropic/claude-opus-4-8")
    assert opus_save > groq_save
