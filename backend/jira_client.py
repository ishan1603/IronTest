import re
from typing import Any
from urllib.parse import urlparse

import requests


ISSUE_KEY_PATTERN = re.compile(r"([A-Z][A-Z0-9_]+-\d+)", re.IGNORECASE)


def extract_issue_key_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path or ""

    browse_match = re.search(r"/browse/([A-Z][A-Z0-9_]+-\d+)", path, flags=re.IGNORECASE)
    if browse_match:
        return browse_match.group(1).upper()

    generic = ISSUE_KEY_PATTERN.search(url)
    if generic:
        return generic.group(1).upper()
    return None


def jira_base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid Jira URL. Expected a full URL like https://your-domain.atlassian.net/browse/PROJ-123")
    return f"{parsed.scheme}://{parsed.netloc}"


def _adf_node_to_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    text_value = node.get("text", "") if isinstance(node.get("text"), str) else ""

    if node_type in {"hardBreak", "rule"}:
        return "\n"

    child_content = node.get("content", [])
    children = "".join(_adf_node_to_text(child) for child in child_content if child)

    if node_type in {"paragraph", "heading"}:
        return f"{children}\n"
    if node_type in {"bulletList", "orderedList"}:
        return children
    if node_type == "listItem":
        clean = children.strip()
        return f"- {clean}\n" if clean else ""
    if node_type == "text":
        return text_value

    if text_value:
        return text_value
    return children


def adf_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""

    content = value.get("content", [])
    text = "".join(_adf_node_to_text(node) for node in content if node)

    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line.strip())
    return normalized.strip()


def fetch_jira_issue(url: str, email: str, token: str, issue_key: str | None = None) -> dict[str, Any]:
    key = issue_key or extract_issue_key_from_url(url)
    if not key:
        raise ValueError("Could not infer Jira issue key from URL. Provide a URL containing an issue key like PROJ-123.")

    base_url = jira_base_url(url)
    endpoint = f"{base_url}/rest/api/3/issue/{key}"
    params = {
        "fields": "summary,description,priority,labels,components,status,issuetype,project",
    }

    response = requests.get(
        endpoint,
        params=params,
        auth=(email, token),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if not response.ok:
        raise requests.HTTPError(f"Jira API request failed: {response.status_code} {response.text}", response=response)

    data = response.json()
    fields = data.get("fields", {})

    summary = fields.get("summary") or ""
    description_text = adf_to_text(fields.get("description"))
    issue_type = (fields.get("issuetype") or {}).get("name", "Task")
    project_key = (fields.get("project") or {}).get("key", "Unknown")
    status = (fields.get("status") or {}).get("name", "Unknown")
    priority = (fields.get("priority") or {}).get("name", "Not specified")
    labels = fields.get("labels") or []
    components = [c.get("name") for c in fields.get("components", []) if isinstance(c, dict) and c.get("name")]

    story_lines = [
        f"Jira Issue: {data.get('key', key)}",
        f"Project: {project_key}",
        f"Issue Type: {issue_type}",
        f"Status: {status}",
        f"Priority: {priority}",
        f"Summary: {summary}",
    ]
    if labels:
        story_lines.append(f"Labels: {', '.join(labels)}")
    if components:
        story_lines.append(f"Components: {', '.join(components)}")

    if description_text:
        story_lines.append("Description:")
        story_lines.append(description_text)

    story_text = "\n".join(story_lines).strip()

    return {
        "issue_key": data.get("key", key),
        "summary": summary,
        "user_story": story_text,
        "metadata": {
            "project": project_key,
            "issue_type": issue_type,
            "status": status,
            "priority": priority,
            "labels": labels,
            "components": components,
        },
    }
