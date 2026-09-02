"""Failover chain across free-tier LLM providers.

Walks configured providers in order, and each provider's models in order,
retrying transient statuses before moving on. Rate limits are the expected
steady state on free tiers, so exhausting one provider is routine rather than
exceptional -- the chain exists so a single 429 never ends a pipeline run.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from .extraction import extract_json_object
from .providers import Provider, configured_providers

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# Statuses worth retrying against the same model before failing over.
TRANSIENT_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
TRANSIENT_RETRIES = 2
MAX_BACKOFF_SECONDS = 8.0

# Prompt nudges applied on reparse attempts, in escalating strictness.
REPAIR_SUFFIXES = (
    "",
    "\n\nIMPORTANT: Return ONLY a valid JSON object. No markdown fences, no commentary, no trailing commas.",
    "\n\nIMPORTANT: Your previous output could not be parsed. Return a shorter, compact JSON object and nothing else.",
)


class LLMError(RuntimeError):
    """Raised when every configured provider and model has been exhausted."""

    def __init__(self, message: str, *, attempts: list[str] | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts or []


class NoProviderConfigured(LLMError):
    """Raised when no provider has an API key set."""


def _headers(provider: Provider) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    if provider.name == "openrouter":
        # OpenRouter attributes free-tier usage via these.
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:5173")
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME", "IronTest")
    return headers


def _payload(
    provider: Provider,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    if provider.supports_json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def _choice_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""

    if isinstance(content, str):
        return content.strip()

    # Some gateways return content as a list of typed parts.
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()

    return ""


def _error_summary(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return " ".join(response.text.split())[:200]

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return " ".join(str(error["message"]).split())[:200]
        if isinstance(error, str):
            return " ".join(error.split())[:200]
    return " ".join(response.text.split())[:200]


def _post_with_retry(
    provider: Provider,
    url: str,
    payload: dict[str, Any],
    attempts: list[str],
) -> requests.Response | None:
    """POST, retrying transient statuses. Returns None when the model is unusable."""
    for retry in range(TRANSIENT_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=_headers(provider),
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            if retry < TRANSIENT_RETRIES:
                time.sleep(min(1.5 * (retry + 1), MAX_BACKOFF_SECONDS))
                continue
            attempts.append(f"{provider.name}/{payload['model']}: network error {exc}")
            return None

        if response.status_code in TRANSIENT_STATUSES and retry < TRANSIENT_RETRIES:
            try:
                wait = float(response.headers.get("Retry-After", ""))
            except (TypeError, ValueError):
                wait = 1.5 * (retry + 1)
            time.sleep(max(1.0, min(wait, MAX_BACKOFF_SECONDS)))
            continue

        return response

    return None


def _try_model(
    provider: Provider,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int,
    temperature: float,
    attempts: list[str],
) -> dict[str, Any] | None:
    url = provider.base_url.rstrip("/") + "/chat/completions"

    for suffix in REPAIR_SUFFIXES:
        payload = _payload(
            provider,
            model,
            system_prompt,
            f"{user_prompt.strip()}{suffix}",
            max_output_tokens,
            temperature,
        )
        response = _post_with_retry(provider, url, payload, attempts)
        if response is None:
            return None

        if not response.ok:
            attempts.append(f"{provider.name}/{model}: {response.status_code} {_error_summary(response)}")
            # A rejected response_format is a capability problem, not a repair
            # problem, so retry once without it before giving up on this model.
            if response.status_code == 400 and payload.get("response_format"):
                payload.pop("response_format")
                retry_response = _post_with_retry(provider, url, payload, attempts)
                if retry_response is not None and retry_response.ok:
                    response = retry_response
                else:
                    return None
            else:
                return None

        try:
            body = response.json()
        except ValueError:
            attempts.append(f"{provider.name}/{model}: response body was not JSON")
            return None

        text = _choice_text(body)
        if not text:
            attempts.append(f"{provider.name}/{model}: empty completion")
            continue

        try:
            return extract_json_object(text)
        except ValueError as exc:
            attempts.append(f"{provider.name}/{model}: unparseable ({exc}); preview={' '.join(text.split())[:120]}")
            continue

    return None


def generate_json(
    *,
    system_prompt: str,
    user_prompt: str,
    max_output_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Return a JSON object from the first provider/model that produces one.

    Raises NoProviderConfigured when no API key is set, and LLMError when every
    configured provider has been tried without a parseable result.
    """
    providers = configured_providers()
    if not providers:
        raise NoProviderConfigured(
            "No LLM provider is configured. Set at least one of: "
            "GROQ_API_KEY, GEMINI_API_KEY, CEREBRAS_API_KEY, OPENROUTER_API_KEY."
        )

    attempts: list[str] = []
    for provider in providers:
        for model in provider.models:
            result = _try_model(
                provider,
                model,
                system_prompt,
                user_prompt,
                max_output_tokens,
                temperature,
                attempts,
            )
            if result is not None:
                logger.info("LLM call served by %s/%s", provider.name, model)
                return result

    raise LLMError(
        "All configured LLM providers failed: " + " | ".join(attempts[-8:]),
        attempts=attempts,
    )
