"""Authenticated, read-only Jira status endpoints for Workbet."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import member
from app.config import get_settings
from app.db import get_db
from app.db_models import User
from app.jira import JiraError, JiraIssue, provider
from app.services import find_market

router = APIRouter(prefix="/api/jira", tags=["Jira"])


def checked_issue(jira, identifier: str, expected_id: str | None = None) -> dict:
    issue: JiraIssue = jira.issue(identifier)
    if expected_id is not None and issue.id != expected_id:
        raise JiraError("Linked Jira issue ID mismatch")
    if issue.project.upper() not in get_settings().allowed_projects:
        raise HTTPException(403, "Jira project is not allowlisted")
    category = jira.category(issue.status_id)
    return {
        "issue_id": issue.id,
        "issue_key": issue.key,
        "project_key": issue.project,
        "summary": issue.summary,
        "status_id": issue.status_id,
        "status_category": category,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": "JIRA_LIVE" if get_settings().jira_mode == "live" else "JIRA_MOCK",
    }


@router.get("/issues/{issue_key}")
def admin_issue_preview(issue_key: str, user: User = Depends(member)):
    if user.role != "ADMIN":
        raise HTTPException(403, "Admin role required")
    if not issue_key or len(issue_key) > 64 or not all(c.isalnum() or c in "-_" for c in issue_key):
        raise HTTPException(422, "Invalid Jira issue key")
    return checked_issue(provider(), issue_key)


@router.get("/markets/{market_id}/status")
def linked_market_issue_status(market_id: str, user: User = Depends(member),
                               db: Session = Depends(get_db)):
    market = find_market(db, market_id)
    return checked_issue(provider(), market.jira_issue_id, market.jira_issue_id)
