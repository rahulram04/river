"""Read-only Jira Cloud integration with deterministic mock fixtures."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import httpx
from app.config import get_settings
from app.domain import aware


class JiraError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssue:
    id: str
    key: str
    project: str
    summary: str
    status_id: str
    created: datetime


@dataclass(frozen=True)
class Transition:
    at: datetime
    from_id: str
    to_id: str


class JiraProvider(Protocol):
    def issue(self, key_or_id: str) -> JiraIssue: ...
    def history(self, issue_id: str) -> list[Transition]: ...
    def category(self, status_id: str) -> str: ...


def parse_dt(value: str) -> datetime:
    try:
        return aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError) as error:
        raise JiraError("Jira returned an invalid timestamp") from error


class LiveJira:
    def __init__(self):
        settings = get_settings()
        self.base = settings.jira_base_url.rstrip("/")
        self.auth = (settings.jira_email, settings.jira_api_token)
        self._category_cache = {}

    def _get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(3):
            try:
                with httpx.Client(timeout=12, follow_redirects=False) as client:
                    result = client.get(self.base + path, params=params,
                                        auth=self.auth, headers={"Accept": "application/json"})
                if result.status_code in {401, 403, 404}:
                    raise JiraError({401: "Jira authentication failed", 403: "Jira permission denied", 404: "Jira issue or status not found"}[result.status_code], result.status_code)
                if result.status_code in {429, 500, 502, 503, 504}:
                    if attempt < 2:
                        retry = result.headers.get("Retry-After", "")
                        delay = min(float(retry), 2) if retry.replace(".", "", 1).isdigit() else 0.25 * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    raise JiraError("Jira temporarily unavailable")
                if result.is_error:
                    raise JiraError("Jira request failed", 503)
                return result.json()
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                if attempt == 2:
                    raise JiraError("Jira connection or response error") from exc
                time.sleep(0.25 * 2 ** attempt)
        raise JiraError("Jira request failed")

    def issue(self, key_or_id: str) -> JiraIssue:
        data = self._get(f"/rest/api/3/issue/{key_or_id}", {"fields": "summary,status,created,project"})
        fields = data["fields"]
        return JiraIssue(str(data["id"]), data["key"], fields["project"]["key"],
                         fields["summary"], str(fields["status"]["id"]), parse_dt(fields["created"]))

    def history(self, issue_id: str) -> list[Transition]:
        transitions = []
        start = 0
        while True:
            data = self._get(f"/rest/api/3/issue/{issue_id}/changelog", {"startAt": start, "maxResults": 100})
            values = data.get("values")
            if not isinstance(values, list) or not isinstance(data.get("total"), int):
                raise JiraError("Incomplete Jira changelog; settlement withheld")
            for item in values:
                for change in item.get("items", []):
                    if change.get("field") == "status":
                        if not change.get("from") or not change.get("to"):
                            raise JiraError("Ambiguous Jira status transition")
                        transitions.append(Transition(parse_dt(item["created"]), str(change["from"]), str(change["to"])))
            start += len(values)
            if start >= data["total"]:
                break
            if not values:
                raise JiraError("Incomplete Jira changelog; settlement withheld")
        return sorted(transitions, key=lambda t: t.at)

    def category(self, status_id: str) -> str:
        if status_id not in self._category_cache:
            item = self._get(f"/rest/api/3/status/{status_id}")
            category = item.get("statusCategory", {}).get("key")
            if category not in {"done", "new", "indeterminate"}:
                raise JiraError("Unrecognized Jira status category")
            self._category_cache[status_id] = category
        return self._category_cache[status_id]


class MockJira:
    """Deterministic sample issues; deliberately unrelated to the actual Jira site."""
    _issues = {
        "KAN-1": ("10001", "Implement project scaffold", "2", []),
        "KAN-2": ("10002", "Add test coverage", "3", [
            ("2026-11-15T15:00:00Z", "2", "3")
        ]),
        "KAN-3": ("10003", "Implement status handling", "2", [
            ("2026-11-15T15:00:00Z", "2", "3"),
            ("2026-11-16T15:00:00Z", "3", "2")
        ]),
        "KAN-4": ("10004", "Build frontend screen", "3", [
            ("2026-11-20T15:00:00Z", "2", "3")
        ]),
    }

    def issue(self, key_or_id: str) -> JiraIssue:
        for key, (issue_id, summary, state, _) in self._issues.items():
            if key_or_id in (key, issue_id):
                return JiraIssue(issue_id, key, "KAN", f"[MOCK] {summary}", state,
                                 parse_dt("2026-11-01T12:00:00Z"))
        raise JiraError("Mock Jira issue not found", 404)

    def history(self, issue_id: str) -> list[Transition]:
        for _, (iid, _, _, transitions) in self._issues.items():
            if iid == issue_id:
                return [Transition(parse_dt(t), start, end) for t, start, end in transitions]
        raise JiraError("Mock Jira issue not found", 404)

    def category(self, status_id: str) -> str:
        if status_id == "3":
            return "done"
        if status_id in ("1", "2"):
            return "indeterminate"
        raise JiraError("Unknown mock status")


def provider() -> JiraProvider:
    return MockJira() if get_settings().jira_mode == "mock" else LiveJira()


def as_of(issue: JiraIssue, changes: list[Transition], cutoff: datetime, jira: JiraProvider) -> tuple[str, dict]:
    """Fail closed unless complete transitions reconcile with the current status."""
    cutoff = aware(cutoff)
    if issue.created > cutoff:
        raise JiraError("Issue did not exist at market cutoff")
    changes = sorted(changes, key=lambda c: c.at)
    if not changes:
        # Complete zero-length changelog means current status was never changed.
        status_id = issue.status_id
    else:
        baseline = changes[0].from_id
        status_id = baseline
        current = baseline
        for change in changes:
            if change.from_id != current:
                raise JiraError("Non-contiguous Jira status history; settlement withheld")
            current = change.to_id
            if aware(change.at) <= cutoff:
                status_id = change.to_id
        if current != issue.status_id:
            raise JiraError("Jira current status conflicts with its changelog")
    category = jira.category(status_id)
    if category not in ("done", "new", "indeterminate"):
        raise JiraError("Unknown status category")
    return ("YES" if category == "done" else "NO", {"status_id": status_id, "category": category,
                                                          "checked_at": datetime.now(timezone.utc).isoformat(),
                                                          "transition_count": len(changes)})
