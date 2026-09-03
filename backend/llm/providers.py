"""Free-tier LLM provider registry.

Every provider here exposes an OpenAI-compatible /chat/completions endpoint,
including Gemini via its compatibility layer, so a single client drives all of
them and only the base URL, key, and model list differ.

Providers are tried in registry order. A provider is only eligible when its key
is present in the environment, so a developer with one key still gets a working
pipeline and adding keys only widens the fallback chain.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key_env: str
    default_models: tuple[str, ...]
    #: Env var holding a comma-separated model override.
    models_env: str = ""
    #: Providers that reject the response_format parameter outright.
    supports_json_mode: bool = True
    notes: str = ""

    @property
    def api_key(self) -> str:
        return (os.getenv(self.api_key_env) or "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def models(self) -> tuple[str, ...]:
        override = (os.getenv(self.models_env) or "").strip() if self.models_env else ""
        if override:
            parsed = tuple(item.strip() for item in override.split(",") if item.strip())
            if parsed:
                return parsed
        return self.default_models


# Ordered by free-tier generosity and latency: Groq and Cerebras are the
# fastest, Gemini has the largest daily quota, OpenRouter is the safety net.
REGISTRY: tuple[Provider, ...] = (
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models_env="GROQ_MODELS",
        default_models=(
            # Smallest first: the free tier caps tokens-per-minute low, and a
            # large request is rejected outright rather than queued.
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
        ),
        notes="Fast, but the free tier's ~8k tokens/minute is tight for repo context. Pair it with Gemini.",
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        models_env="GEMINI_MODELS",
        default_models=(
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash-lite",
        ),
        notes="Recommended primary: 1M-token context and a generous free tier handle repo context comfortably.",
    ),
    Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models_env="CEREBRAS_MODELS",
        default_models=(
            "llama-3.3-70b",
            "gpt-oss-120b",
        ),
        notes="Very low latency, smaller free quota.",
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models_env="OPENROUTER_MODELS",
        default_models=(
            "openai/gpt-oss-120b:free",
            "deepseek/deepseek-chat-v3.1:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ),
        notes="Broadest catalogue; free tier is ~50 requests/day without credits.",
    ),
)

PROVIDERS_BY_NAME = {provider.name: provider for provider in REGISTRY}


def configured_providers() -> list[Provider]:
    """Providers with a key present, honouring an explicit LLM_PROVIDER_ORDER."""
    order = (os.getenv("LLM_PROVIDER_ORDER") or "").strip()
    if order:
        names = [item.strip().lower() for item in order.split(",") if item.strip()]
        chosen = [PROVIDERS_BY_NAME[name] for name in names if name in PROVIDERS_BY_NAME]
    else:
        chosen = list(REGISTRY)

    return [provider for provider in chosen if provider.is_configured]


def provider_status() -> list[dict[str, object]]:
    """Diagnostic view for the health endpoint. Never exposes key material."""
    active = {provider.name for provider in configured_providers()}
    return [
        {
            "name": provider.name,
            "configured": provider.is_configured,
            "active": provider.name in active,
            "key_env": provider.api_key_env,
            "models": list(provider.models),
            "notes": provider.notes,
        }
        for provider in REGISTRY
    ]
