from __future__ import annotations

OPENAI_MODEL_MAP: dict[str, str] = {
    "gpt-4o":           "heavy-openai",
    "gpt-4o-mini":      "fast-openai",
    "gpt-4-turbo":      "heavy-openai",
    "gpt-3.5-turbo":    "fast-openai",
    "o1":               "heavy-openai",
    "o1-mini":          "fast-openai",
    "o3":               "heavy-openai",
    "o3-mini":          "fast-openai",
    "o4-mini":          "fast-openai",
}

ANTHROPIC_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-8":          "heavy-anthropic",
    "claude-opus-4-7":          "heavy-anthropic",
    "claude-sonnet-4-6":        "fast-anthropic",
    "claude-sonnet-4-5":        "fast-anthropic",
    "claude-haiku-4-5":         "fast-anthropic",
    "claude-3-opus-20240229":   "heavy-anthropic",
    "claude-3-sonnet-20240229": "fast-anthropic",
    "claude-3-haiku-20240307":  "fast-anthropic",
}

GEMINI_MODEL_MAP: dict[str, str] = {
    "gemini-pro":       "heavy-gemini",
    "gemini-1.0-pro":   "heavy-gemini",
    "gemini-1.5-pro":   "heavy-gemini",
    "gemini-1.5-flash": "fast-gemini",
    "gemini-2.0-flash": "fast-gemini",
    "gemini-2.5-pro":   "heavy-gemini",
    "gemini-2.5-flash": "fast-gemini",
    "gemini-3.5-flash": "fast-gemini",
}

GROQ_MODEL_MAP: dict[str, str] = {
    "llama-3.1-8b-instant":    "fast-groq",
    "llama-3.3-70b-versatile": "heavy-groq",
    "llama3-8b-8192":          "fast-groq",
    "llama3-70b-8192":         "heavy-groq",
    "mixtral-8x7b-32768":      "heavy-groq",
    "gemma-7b-it":             "fast-groq",
}

_ADAPTER_MAPS: dict[str, dict[str, str]] = {
    "openai":    OPENAI_MODEL_MAP,
    "anthropic": ANTHROPIC_MODEL_MAP,
    "gemini":    GEMINI_MODEL_MAP,
    "groq":      GROQ_MODEL_MAP,
}

_PROVIDER_PREFIXES: dict[str, str] = {
    "openai":    "openai",
    "anthropic": "anthropic",
    "gemini":    "gemini",
    "groq":      "groq",
}


def resolve_model(model: str, adapter: str) -> str:
    """
    Resolve a provider model name to a TAPIOD routing alias or LiteLLM-prefixed name.

    Priority:
    1. Known model in adapter map → return TAPIOD alias (enables tier routing + caching)
    2. Already provider-prefixed (contains '/') → pass through unchanged
    3. Unknown model → prepend provider prefix (e.g. "gpt-5" → "openai/gpt-5")
       LiteLLM will route it; provider API returns clear error if model doesn't exist
    """
    adapter_map = _ADAPTER_MAPS.get(adapter, {})
    if model in adapter_map:
        return adapter_map[model]
    if "/" in model:
        return model
    prefix = _PROVIDER_PREFIXES.get(adapter, adapter)
    return f"{prefix}/{model}"
