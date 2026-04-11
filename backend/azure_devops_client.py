import base64
import html
import re
from typing import Any
from urllib.parse import urlparse

import requests


_WORK_ITEM_PATTERN = re.compile(r"/_workitems/edit/(\d+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(value)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_context_from_url(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "Invalid Azure DevOps URL. Expected a full URL like "
            "https://dev.azure.com/<org>/<project>/_workitems/edit/<id>."
        )

    host = parsed.netloc.lower()
    segments = [segment for segment in parsed.path.split("/") if segment]

    organization: str | None = None
    project: str | None = None

    if host == "dev.azure.com":
        if len(segments) >= 2:
            organization = segments[0]
            project = segments[1]
    elif host.endswith(".visualstudio.com"):
        organization = host.split(".", 1)[0]
        if segments:
            project = segments[0]

    match = _WORK_ITEM_PATTERN.search(parsed.path)
    work_item_id = match.group(1) if match else None

    return organization, project, work_item_id


def _build_auth_headers(pat: str) -> dict[str, str]:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    }


def fetch_azure_devops_work_item(
    url: str,
    pat: str,
    organization: str | None = None,
    project: str | None = None,
    work_item_id: str | None = None,
) -> dict[str, Any]:
    parsed_org, parsed_project, parsed_work_item_id = _parse_context_from_url(url)

    org = (organization or parsed_org or "").strip()
    proj = (project or parsed_project or "").strip()
    wid = str(work_item_id or parsed_work_item_id or "").strip()

    if not org:
        raise ValueError("Could not infer Azure DevOps organization from URL. Provide organization explicitly.")
    if not proj:
        raise ValueError("Could not infer Azure DevOps project from URL. Provide project explicitly.")
    if not wid.isdigit():
        raise ValueError(
            "Could not infer Azure DevOps work item id from URL. "
            "Provide a URL containing .../_workitems/edit/<id> or pass work_item_id."
        )

    endpoint = f"https://dev.azure.com/{org}/{proj}/_apis/wit/workitems/{wid}"
    params = {
        "api-version": "7.1",
    }

    response = requests.get(
        endpoint,
        params=params,
        headers=_build_auth_headers(pat),
        timeout=30,
    )
    if not response.ok:
        raise requests.HTTPError(
            f"Azure DevOps API request failed: {response.status_code} {response.text}",
            response=response,
        )

    data = response.json()
    fields = data.get("fields", {})

    summary = str(fields.get("System.Title") or "")
    description_text = _strip_html(fields.get("System.Description"))
    work_item_type = str(fields.get("System.WorkItemType") or "Task")
    state = str(fields.get("System.State") or "Unknown")
    priority = fields.get("Microsoft.VSTS.Common.Priority")
    area_path = str(fields.get("System.AreaPath") or "")
    iteration_path = str(fields.get("System.IterationPath") or "")

    assigned_to_raw = fields.get("System.AssignedTo")
    if isinstance(assigned_to_raw, dict):
        assigned_to = str(assigned_to_raw.get("displayName") or "")
    else:
        assigned_to = str(assigned_to_raw or "")

    tags_raw = str(fields.get("System.Tags") or "")
    tags = [tag.strip() for tag in tags_raw.split(";") if tag.strip()]

    story_lines = [
        f"Azure DevOps Work Item: {proj}#{wid}",
        f"Organization: {org}",
        f"Project: {proj}",
        f"Work Item Type: {work_item_type}",
        f"State: {state}",
        f"Summary: {summary}",
    ]
    if priority not in (None, ""):
        story_lines.append(f"Priority: {priority}")
    if assigned_to:
        story_lines.append(f"Assigned To: {assigned_to}")
    if area_path:
        story_lines.append(f"Area Path: {area_path}")
    if iteration_path:
        story_lines.append(f"Iteration Path: {iteration_path}")
    if tags:
        story_lines.append(f"Tags: {', '.join(tags)}")
    if description_text:
        story_lines.append("Description:")
        story_lines.append(description_text)

    story_text = "\n".join(story_lines).strip()

    return {
        "issue_key": f"{proj}#{wid}",
        "summary": summary,
        "user_story": story_text,
        "metadata": {
            "source": "azure_devops",
            "organization": org,
            "project": proj,
            "work_item_id": wid,
            "work_item_type": work_item_type,
            "state": state,
            "priority": priority,
            "assigned_to": assigned_to,
            "tags": tags,
            "area_path": area_path,
            "iteration_path": iteration_path,
        },
    }
