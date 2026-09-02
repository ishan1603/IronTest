"""Tolerant JSON extraction from model output.

Small models wrap JSON in prose or markdown fences, emit trailing commas, and
truncate mid-object when they hit the token ceiling. This recovers an object
from all of those, falling back to balanced-brace slicing and finally to
literal_eval for Python-dict-shaped output.
"""

import ast
import json
import re
from typing import Any


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
