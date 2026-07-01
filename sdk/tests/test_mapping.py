import pytest
from tapiod._core.mapping import resolve_model


def test_known_openai_model_maps_to_tapiod_alias():
    assert resolve_model("gpt-4o", "openai") == "heavy-openai"


def test_known_openai_mini_maps_to_fast():
    assert resolve_model("gpt-4o-mini", "openai") == "fast-openai"


def test_known_anthropic_opus_maps_to_heavy():
    assert resolve_model("claude-opus-4-8", "anthropic") == "heavy-anthropic"


def test_known_anthropic_sonnet_maps_to_fast():
    assert resolve_model("claude-sonnet-4-6", "anthropic") == "fast-anthropic"


def test_known_gemini_pro_maps_to_heavy():
    assert resolve_model("gemini-pro", "gemini") == "heavy-gemini"


def test_known_gemini_flash_maps_to_fast():
    assert resolve_model("gemini-2.5-flash", "gemini") == "fast-gemini"


def test_known_groq_model_maps_to_alias():
    assert resolve_model("llama-3.1-8b-instant", "groq") == "fast-groq"


def test_unknown_model_gets_provider_prefix():
    assert resolve_model("gpt-5", "openai") == "openai/gpt-5"


def test_unknown_anthropic_model_gets_prefix():
    assert resolve_model("claude-opus-5", "anthropic") == "anthropic/claude-opus-5"


def test_unknown_gemini_model_gets_prefix():
    assert resolve_model("gemini-2.0-ultra", "gemini") == "gemini/gemini-2.0-ultra"


def test_already_prefixed_model_passes_through():
    assert resolve_model("openai/gpt-4o", "openai") == "openai/gpt-4o"


def test_already_prefixed_unknown_model_passes_through():
    assert resolve_model("anthropic/claude-opus-5", "anthropic") == "anthropic/claude-opus-5"
