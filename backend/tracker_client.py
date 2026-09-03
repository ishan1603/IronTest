"""Persistent Jira / Azure DevOps connections: verify, and list my open work.

Credentials are validated on connect and then stored Fernet-encrypted on the
user. These helpers are read-only against the tracker.
"""

from __future__ import annotations

import base64
from typing import Any

import requests

from jira_client import adf_to_text

TIMEOUT = 25


class TrackerError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# -- Jira -----------------------------------------------------------------


def _jira_get(base_url: str, email: str, token: str, path: str, params: dict | None = None) -> Any:
    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        params=params,
        auth=(email, token),
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if response.status_code in (401, 403):
        raise TrackerError("Jira rejected those credentials.", status_code=401)
    if not response.ok:
        raise TrackerError(f"Jira request failed ({response.status_code}).", status_code=response.status_code)
    return response.json()


def verify_jira(base_url: str, email: str, token: str) -> dict[str, str]:
    me = _jira_get(base_url, email, token, "/rest/api/3/myself")
    return {"account_id": me.get("accountId", ""), "display_name": me.get("displayName", email)}


def list_jira_issues(base_url: str, email: str, token: str, *, limit: int = 30) -> list[dict[str, Any]]:
    data = _jira_get(
        base_url,
        email,
        token,
        "/rest/api/3/search",
        {
            "jql": "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC",
            "maxResults": limit,
            "fields": "summary,description,issuetype,status,priority,project",
        },
    )
    issues = []
    for item in data.get("issues", []):
        fields = item.get("fields", {})
        summary = fields.get("summary") or ""
        description = adf_to_text(fields.get("description"))
        issues.append(
            {
                "key": item.get("key"),
                "summary": summary,
                "status": (fields.get("status") or {}).get("name", ""),
                "type": (fields.get("issuetype") or {}).get("name", ""),
                "requirement": _compose(item.get("key"), summary, description),
            }
        )
    return issues


# -- Azure DevOps -------------------------------------------------------------


def _ado_headers(pat: str) -> dict[str, str]:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def verify_ado(org: str, pat: str) -> dict[str, str]:
    response = requests.get(
        f"https://dev.azure.com/{org}/_apis/projects?api-version=7.0&$top=1",
        headers=_ado_headers(pat),
        timeout=TIMEOUT,
    )
    if response.status_code in (401, 203):  # ADO returns 203 for a bad PAT
        raise TrackerError("Azure DevOps rejected that PAT or organization.", status_code=401)
    if not response.ok:
        raise TrackerError(f"Azure DevOps request failed ({response.status_code}).", status_code=response.status_code)
    return {"organization": org}


def list_ado_work_items(org: str, pat: str, *, limit: int = 30) -> list[dict[str, Any]]:
    wiql = {
        "query": (
            "SELECT [System.Id] FROM WorkItems "
            "WHERE [System.AssignedTo] = @Me AND [System.State] NOT IN ('Closed', 'Done', 'Removed') "
            "ORDER BY [System.ChangedDate] DESC"
        )
    }
    resp = requests.post(
        f"https://dev.azure.com/{org}/_apis/wit/wiql?api-version=7.0&$top={limit}",
        headers={**_ado_headers(pat), "Content-Type": "application/json"},
        json=wiql,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise TrackerError(f"Azure DevOps query failed ({resp.status_code}).", status_code=resp.status_code)

    ids = [str(item["id"]) for item in resp.json().get("workItems", [])][:limit]
    if not ids:
        return []

    detail = requests.get(
        f"https://dev.azure.com/{org}/_apis/wit/workitems?ids={','.join(ids)}"
        "&fields=System.Id,System.Title,System.Description,System.WorkItemType,System.State&api-version=7.0",
        headers=_ado_headers(pat),
        timeout=TIMEOUT,
    )
    if not detail.ok:
        raise TrackerError("Could not load work item details.", status_code=detail.status_code)

    from azure_devops_client import _strip_html

    items = []
    for wi in detail.json().get("value", []):
        f = wi.get("fields", {})
        title = f.get("System.Title", "")
        description = _strip_html(f.get("System.Description", ""))
        items.append(
            {
                "key": str(f.get("System.Id", wi.get("id"))),
                "summary": title,
                "status": f.get("System.State", ""),
                "type": f.get("System.WorkItemType", ""),
                "requirement": _compose(f.get("System.Id"), title, description),
            }
        )
    return items


def _compose(key: Any, summary: str, description: str) -> str:
    parts = [f"[{key}] {summary}".strip()]
    if description.strip():
        parts.append("")
        parts.append(description.strip())
    return "\n".join(parts).strip()
