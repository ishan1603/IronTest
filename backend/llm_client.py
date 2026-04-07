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
    return [item.strip() for item in raw.split(",") if item.strip()]


def _extract_model_id(name: str) -> str:
    return name.split("/", 1)[1] if name.startswith("models/") else name


def _list_generate_content_models(api_key: str) -> set[str]:
    now = time.time()
    cached = _MODELS_CACHE.get(api_key)
    if cached and (now - cached[0]) < _MODELS_CACHE_TTL_SECONDS:
        return cached[1]

    endpoint = "https://generativelanguage.googleapis.com/v1beta/models"
    page_token = ""
    discovered: set[str] = set()

    for _ in range(6):
        params = {"key": api_key, "pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token

        try:
            response = requests.get(endpoint, params=params, timeout=25)
        except requests.RequestException:
            break

        if not response.ok:
            break

        try:
            payload = response.json()
        except ValueError:
            break

        for model in payload.get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            if isinstance(methods, list) and "generateContent" in methods:
                name = model.get("name", "")
                if isinstance(name, str) and name:
                    discovered.add(_extract_model_id(name))

        page_token = payload.get("nextPageToken", "")
        if not page_token:
            break

    if discovered:
        _MODELS_CACHE[api_key] = (now, discovered)
    return discovered


def _candidate_models(primary_model_id: str, api_key: str) -> list[str]:
    configured = _parse_models(os.getenv("GEMINI_MODEL_CANDIDATES", ""))
    default_priority = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-1.5-flash-8b",
    ]
    ordered = [primary_model_id, *(configured or default_priority)]

    seen: set[str] = set()
    unique: list[str] = []
    for model in ordered:
        if model and model not in seen:
            unique.append(model)
            seen.add(model)

    available = _list_generate_content_models(api_key)
    if available:
        filtered = [model for model in unique if model in available]
        if filtered:
            return filtered
    return unique


def _build_payload(system_prompt: str, user_prompt: str, max_output_tokens: int, temperature: float, strict_json: bool = True) -> dict[str, Any]:
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if strict_json:
        generation_config["responseMimeType"] = "application/json"

    return {
        "systemInstruction": {
            "parts": [{"text": system_prompt.strip()}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt.strip()}],
            }
        ],
        "generationConfig": generation_config,
    }


def gemini_generate_json(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    *,
    max_output_tokens: int = 1024,
    temperature: float = 0.25,
) -> dict[str, Any]:
    endpoint_base = "https://generativelanguage.googleapis.com/v1beta/models"
    transient_statuses = {429, 500, 502, 503, 504}

    attempt_errors: list[str] = []
    for candidate_model in _candidate_models(model_id, api_key):
        for attempt in range(3):
            endpoint = f"{endpoint_base}/{candidate_model}:generateContent"
            strict_retry = attempt < 2
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
                max_output_tokens=max_output_tokens,
                temperature=temperature if attempt == 0 else 0.1,
                strict_json=strict_retry,
            )

            response = None
            for transient_try in range(3):
                try:
                    response = requests.post(endpoint, params={"key": api_key}, json=payload, timeout=120)
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
                compact_text = " ".join(response.text.split())
                attempt_errors.append(f"{candidate_model}: {response.status_code} {compact_text[:240]}")
                continue

            try:
                body = response.json()
            except ValueError:
                attempt_errors.append(f"{candidate_model}: invalid JSON response body")
                continue

            candidates = body.get("candidates", [])
            if not candidates:
                reason = body.get("promptFeedback", {}).get("blockReason")
                reason_text = f"blockReason={reason}" if reason else "no candidates returned"
                attempt_errors.append(f"{candidate_model}: {reason_text}")
                continue

            parts = candidates[0].get("content", {}).get("parts", [])
            text_chunks = [p.get("text", "") for p in parts if isinstance(p, dict)]
            raw_text = "\n".join(chunk for chunk in text_chunks if chunk).strip()
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
        f"Gemini request failed across model candidates: {summary}",
        model_id=model_id,
        attempts=attempt_errors,
    )
