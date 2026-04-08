import ast
import json
import os
import re
import time
from typing import Any

import requests


class LLMRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        model_id: str | None = None,
        response_text: str | None = None,
        attempts: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.model_id = model_id
        self.response_text = response_text
        self.attempts = attempts or []


_MODELS_CACHE: dict[str, tuple[float, set[str]]] = {}
_MODELS_CACHE_TTL_SECONDS = 600


def extract_json_object(text: str) -> dict[str, Any]:
    def _strip_code_fences(raw: str) -> str:
        stripped = raw.strip()
        fenced_single_line = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", stripped, flags=re.DOTALL)
        if fenced_single_line:
            return fenced_single_line.group(1).strip()

        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines:
                body_lines = lines[1:]
                # Only remove the last line if it is an actual closing fence.
                if body_lines and body_lines[-1].strip().startswith("```"):
                    body_lines = body_lines[:-1]
                return "\n".join(body_lines).strip()
        return stripped

    def _sanitize_json_candidate(raw: str) -> str:
        # Remove trailing commas before object/array closers.
        return re.sub(r",\s*([}\]])", r"\1", raw)

    def _close_unbalanced_structures(raw: str) -> str:
        stack: list[str] = []
        in_string = False
        escaped = False

        for ch in raw:
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch in "{[":
                stack.append(ch)
                continue
            if ch == "}" and stack and stack[-1] == "{":
                stack.pop()
                continue
            if ch == "]" and stack and stack[-1] == "[":
                stack.pop()

        repaired = raw
        if in_string:
            repaired += '"'
        while stack:
            opener = stack.pop()
            repaired += "}" if opener == "{" else "]"
        return repaired

    def _coerce_dict(candidate: str) -> dict[str, Any]:
        # Strict JSON first.
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # JSON with trailing commas and similar minor issues.
        sanitized = _sanitize_json_candidate(candidate)
        try:
            parsed = json.loads(sanitized)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Last resort for Python-like dict output.
        repaired = _close_unbalanced_structures(sanitized)
        for maybe in (candidate, sanitized, repaired):
            try:
                parsed = ast.literal_eval(maybe)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, SyntaxError):
                continue

        raise ValueError("Candidate is not a valid JSON object.")

    normalized = _strip_code_fences(text)
    try:
        return _coerce_dict(normalized)
    except ValueError:
        pass

    # Attempt largest object slice first.
    start = normalized.find("{")
    end = normalized.rfind("}")
    candidates: list[str] = []
    if start != -1 and end != -1 and end > start:
        candidates.append(normalized[start : end + 1])

    # Gather balanced object snippets as additional candidates.
    depth = 0
    snippet_start = -1
    for idx, ch in enumerate(normalized):
        if ch == "{":
            if depth == 0:
                snippet_start = idx
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and snippet_start != -1:
                    candidates.append(normalized[snippet_start : idx + 1])

    # Try longer snippets first for complete payload coverage.
    for candidate in sorted(set(candidates), key=len, reverse=True):
        try:
            return _coerce_dict(candidate)
        except ValueError:
            continue

    raise ValueError("No JSON object found in model response.")


def _parse_models(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parsed = [_normalize_model_id(item) for item in raw.split(",")]
    return [item for item in parsed if item]


def _normalize_model_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    model = raw.lower().strip()
    model = model.replace("openai:", "openai/")
    model = model.replace("(free)", ":free")
    model = re.sub(r"\s+", "", model)
    model = re.sub(r"_{2,}", "_", model)

    if model in {"gpt-oss-120b", "openai/gpt-oss-120b"}:
        return "openai/gpt-oss-120b:free"
    if model in {"gpt-oss-20b", "openai/gpt-oss-20b"}:
        return "openai/gpt-oss-20b:free"

    if "gpt-oss-120b" in model and model.endswith("free") and ":" not in model:
        return "openai/gpt-oss-120b:free"
    if "gpt-oss-20b" in model and model.endswith("free") and ":" not in model:
        return "openai/gpt-oss-20b:free"

    return model


def _list_openrouter_models(api_key: str) -> set[str]:
    now = time.time()
    cached = _MODELS_CACHE.get(api_key)
    if cached and (now - cached[0]) < _MODELS_CACHE_TTL_SECONDS:
        return cached[1]

    endpoint = "https://openrouter.ai/api/v1/models"
    discovered: set[str] = set()

    try:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=25,
        )
    except requests.RequestException:
        return discovered

    if not response.ok:
        return discovered

    try:
        payload = response.json()
    except ValueError:
        return discovered

    for model in payload.get("data", []):
        model_id = model.get("id", "")
        if isinstance(model_id, str) and model_id:
            discovered.add(_normalize_model_id(model_id))

    if discovered:
        _MODELS_CACHE[api_key] = (now, discovered)
    return discovered


def _candidate_models(primary_model_id: str, api_key: str) -> list[str]:
    # Keep user-configured priority first, then append stable free-tier fallbacks.
    configured = _parse_models(os.getenv("OPENROUTER_MODEL_CANDIDATES", ""))
    default_priority = [
        "openai/gpt-oss-120b:free",
        "openai/gpt-oss-20b:free",
    ]
    ordered = [_normalize_model_id(primary_model_id), *configured, *default_priority]

    seen: set[str] = set()
    unique: list[str] = []
    for model in ordered:
        if model and model not in seen:
            unique.append(model)
            seen.add(model)

    available = _list_openrouter_models(api_key)
    if available:
        # If model discovery succeeds, only keep models that actually exist in OpenRouter catalog.
        filtered = [model for model in unique if model in available]
        if filtered:
            return filtered
    return unique


def _build_payload(system_prompt: str, user_prompt: str, model_id: str, max_output_tokens: int, temperature: float) -> dict[str, Any]:
    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }


def _extract_choice_text(choice: dict[str, Any]) -> str:
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
            elif isinstance(item, str) and item.strip():
                chunks.append(item.strip())
        return "\n".join(chunks).strip()

    return ""


def _compact_error_text(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return " ".join(response.text.split())

    if isinstance(body, dict):
        error = body.get("error", {})
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return " ".join(message.split())

    return " ".join(response.text.split())


def llm_generate_json(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = 1024,
    temperature: float = 0.25,
) -> dict[str, Any]:
    endpoint = os.getenv("OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"
    # Retry transient gateway/quota/network states before failing over to the next model.
    transient_statuses = {408, 409, 425, 429, 500, 502, 503, 504}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost")
    app_name = os.getenv("OPENROUTER_APP_NAME", "IronTest QA Agent")
    if referer:
        headers["HTTP-Referer"] = referer
    if app_name:
        headers["X-Title"] = app_name

    attempt_errors: list[str] = []
    for candidate_model in _candidate_models(model_id, api_key):
        # Per-model retries: normal prompt, strict JSON reminder, compact JSON recovery.
        for attempt in range(3):
            if attempt == 0:
                repair_suffix = ""
            elif attempt == 1:
                repair_suffix = (
                    "\n\nIMPORTANT: Return ONLY a valid JSON object. No markdown fences, no commentary, and no trailing commas."
                )
            else:
                repair_suffix = (
                    "\n\nIMPORTANT: Your prior output was not parseable. Return a shorter, compact JSON object only."
                )
            payload = _build_payload(
                system_prompt=system_prompt,
                user_prompt=f"{user_prompt.strip()}{repair_suffix}",
                model_id=candidate_model,
                max_output_tokens=max_output_tokens,
                temperature=temperature if attempt == 0 else 0.1,
            )

            response = None
            for transient_try in range(3):
                try:
                    response = requests.post(endpoint, headers=headers, json=payload, timeout=120)
                except requests.RequestException as exc:
                    if transient_try < 2:
                        backoff = 1.5 * (transient_try + 1)
                        time.sleep(backoff)
                        continue
                    attempt_errors.append(f"{candidate_model}: request error {exc}")
                    response = None
                    break

                if response.status_code in transient_statuses and transient_try < 2:
                    retry_after_header = response.headers.get("Retry-After", "")
                    try:
                        retry_after = float(retry_after_header)
                    except (TypeError, ValueError):
                        retry_after = 1.5 * (transient_try + 1)
                    time.sleep(max(1.0, min(retry_after, 8.0)))
                    continue
                break

            if response is None:
                continue

            if not response.ok:
                compact_text = _compact_error_text(response)
                attempt_errors.append(f"{candidate_model}: {response.status_code} {compact_text[:240]}")
                continue

            try:
                body = response.json()
            except ValueError:
                attempt_errors.append(f"{candidate_model}: invalid JSON response body")
                continue

            choices = body.get("choices", [])
            if not isinstance(choices, list) or not choices:
                error = body.get("error", {}) if isinstance(body, dict) else {}
                if isinstance(error, dict) and error.get("message"):
                    reason_text = str(error.get("message"))
                else:
                    reason_text = "no choices returned"
                attempt_errors.append(f"{candidate_model}: {reason_text}")
                continue

            raw_text = _extract_choice_text(choices[0])
            if not raw_text:
                attempt_errors.append(f"{candidate_model}: empty text content")
                continue

            try:
                return extract_json_object(raw_text)
            except ValueError as exc:
                preview = " ".join(raw_text.split())[:180]
                attempt_errors.append(f"{candidate_model}: response parsing failed ({exc}); preview={preview}")
                continue

    summary = " | ".join(attempt_errors) if attempt_errors else "No model attempts recorded."
    raise LLMRequestError(
        f"OpenRouter request failed across model candidates: {summary}",
        model_id=model_id,
        attempts=attempt_errors,
    )


openrouter_generate_json = llm_generate_json
