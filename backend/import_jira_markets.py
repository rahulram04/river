"""Preview and bulk-create riverbet markets for Jira work items.

Place this file at backend/import_jira_markets.py and run it from backend/:

  python import_jira_markets.py --project KAN
  python import_jira_markets.py --project KAN --apply --admin-email you@example.com

By default this command is read-only. It never changes a Jira issue. Live Jira
imports only issues not in the Done status category. Mock imports can optionally
include completed fixtures, but ONLY when using a separate mock-mode database.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SessionLocal
from app.db_models import Market, User
from app.jira import JiraError, JiraIssue, LiveJira, MockJira, provider
from app.services import create_market


PROJECT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,19}$")
ISSUE_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,49}$")


def search_live_jira(jira: LiveJira, project: str, issue_type: str | None,
                     limit: int) -> list[JiraIssue]:
    """Search all not-Done project issues with Jira Cloud enhanced JQL pagination.

    The newer /rest/api/3/search/jql endpoint uses nextPageToken, not startAt.
    The existing Jira client's authenticated GET/retry handler is reused.
    """
    jql = f'project = "{project}" AND statusCategory != Done'
    if issue_type:
        jql += f' AND issuetype = "{issue_type}"'
    jql += " ORDER BY created ASC"

    results: list[JiraIssue] = []
    seen_issues: set[str] = set()
    seen_tokens: set[str] = set()
    next_token: str | None = None

    while True:
        params: dict[str, str | int] = {
            "jql": jql,
            "maxResults": 100,
            "fields": "summary,status,created,project",
        }
        if next_token:
            params["nextPageToken"] = next_token
        data = jira._get("/rest/api/3/search/jql", params=params)
        entries = data.get("issues")
        if not isinstance(entries, list):
            raise JiraError("Jira search did not return an issues list")
        for raw in entries:
            fields = raw.get("fields") or {}
            status = fields.get("status") or {}
            category = (status.get("statusCategory") or {}).get("key")
            if category == "done":
                continue
            key = raw.get("key")
            issue_id = raw.get("id")
            project_key = (fields.get("project") or {}).get("key")
            if not isinstance(key, str) or not issue_id or project_key != project:
                raise JiraError("Jira search returned incomplete or unexpected project data")
            if str(issue_id) in seen_issues:
                continue
            from app.jira import parse_dt
            issue = JiraIssue(
                id=str(issue_id),
                key=key,
                project=project_key,
                summary=str(fields.get("summary") or ""),
                status_id=str(status.get("id") or ""),
                created=parse_dt(fields.get("created")),
            )
            if not issue.status_id:
                raise JiraError("Jira issue status was missing")
            results.append(issue)
            seen_issues.add(issue.id)
            if len(results) > limit:
                raise JiraError(
                    f"More than {limit} issues matched. Increase --max-issues explicitly."
                )

        token = data.get("nextPageToken")
        if data.get("isLast") is True:
            break
        if not token:
            if data.get("isLast") is False:
                raise JiraError("Jira indicated another search page but gave no token")
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise JiraError("Jira returned an invalid or repeated page token")
        seen_tokens.add(token)
        next_token = token

    return results


def discover(jira: LiveJira | MockJira, project: str, issue_type: str | None,
             max_issues: int, include_mock_done: bool) -> list[JiraIssue]:
    if isinstance(jira, LiveJira):
        return search_live_jira(jira, project, issue_type, max_issues)

    if issue_type:
        raise ValueError("--issue-type is supported only in live Jira mode")
    issues: list[JiraIssue] = []
    for key in jira._issues:
        item = jira.issue(key)
        if item.project != project:
            continue
        if not include_mock_done and jira.category(item.status_id) == "done":
            continue
        issues.append(item)
    return issues


def plan(issues: Iterable[JiraIssue], cutoff: datetime) -> list[tuple[JiraIssue, str]]:
    """Return every issue and whether it needs a new market."""
    with SessionLocal() as db:
        existing = set(db.scalars(select(Market.jira_issue_id)).all())
    return [
        (issue, "SKIP (already linked)" if issue.id in existing
         else "SKIP (created after deadline)" if issue.created >= cutoff
         else "CREATE")
        for issue in issues
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", default="KAN", help="Allowed Jira project key (default: KAN)")
    p.add_argument("--issue-type", help="Optional Jira issue type, e.g., Test")
    p.add_argument("--days", type=int, default=7, help="Market deadline days from now (default: 7)")
    p.add_argument("--deadline", help="Explicit ISO 8601 cutoff with UTC offset")
    p.add_argument("--liquidity", default="10", help="Play-credit liquidity (default: 10)")
    p.add_argument("--max-issues", type=int, default=500, help="Safety cap (default: 500)")
    p.add_argument("--include-mock-done", action="store_true", help="Include all mock fixtures, including Done")
    p.add_argument("--apply", action="store_true", help="Actually create the previewed markets")
    p.add_argument("--admin-email", help="Required with --apply; audit actor must already be ADMIN")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    project = args.project.upper().strip()
    if not PROJECT_PATTERN.fullmatch(project):
        print("Invalid project key", file=sys.stderr)
        return 2
    if project not in settings.allowed_projects:
        print(f"Project {project} is not in JIRA_ALLOWED_PROJECT_KEYS", file=sys.stderr)
        return 2
    if args.issue_type and not ISSUE_TYPE_PATTERN.fullmatch(args.issue_type):
        print("Invalid issue type", file=sys.stderr)
        return 2
    if args.max_issues < 1 or args.max_issues > 10000:
        print("--max-issues must be between 1 and 10000", file=sys.stderr)
        return 2
    if args.days < 1 or args.days > 365:
        print("--days must be between 1 and 365", file=sys.stderr)
        return 2
    if args.include_mock_done and settings.jira_mode != "mock":
        print("--include-mock-done is only available in mock Jira mode", file=sys.stderr)
        return 2
    if args.apply and not args.admin_email:
        print("--apply requires --admin-email", file=sys.stderr)
        return 2

    try:
        if args.deadline:
            cutoff = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise ValueError("--deadline must specify an offset (e.g. -05:00)")
        else:
            eastern = ZoneInfo("America/New_York")
            day = (datetime.now(eastern) + timedelta(days=args.days)).date()
            cutoff = datetime(
                day.year, day.month, day.day,
                18, 0, 0, 0, tzinfo=eastern
            ).astimezone(timezone.utc)
        if cutoff <= datetime.now(timezone.utc):
            raise ValueError("Deadline must be in the future")
        if cutoff.year > datetime.now(timezone.utc).year + 5:
            raise ValueError("Deadline too far into the future")
    except ValueError as exc:
        print(f"Invalid deadline: {exc}", file=sys.stderr)
        return 2

    try:
        jira = provider()
        issues = discover(jira, project, args.issue_type, args.max_issues, args.include_mock_done)
        planned = plan(issues, cutoff)
    except (JiraError, ValueError) as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        return 1

    print(f"riverbet Jira market import | Jira mode: {settings.jira_mode}")
    print(f"Database: {make_url(settings.database_url).render_as_string(hide_password=True)}")
    print(f"Project: {project} | Issue type: {args.issue_type or 'all'}")
    print(f"Deadline: {cutoff.isoformat()} | Liquidity: {args.liquidity}")
    print(f"Found {len(planned)} eligible Jira work items")
    for issue, action in planned:
        sanitized = " ".join(issue.summary.split())[:75]
        print(f"  {action:28} {issue.key:12} {sanitized}")
    remaining = [issue for issue, action in planned if action == "CREATE"]
    print(f"Summary: {len(remaining)} to create, {len(planned) - len(remaining)} skipped")

    if not args.apply:
        print("PREVIEW ONLY. No markets were created. Re-run with --apply --admin-email EMAIL.")
        return 0
    if not remaining:
        print("No new markets required.")
        return 0

    successes = 0
    failures = 0
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.admin_email.lower().strip()))
        if user is None or user.role != "ADMIN" or user.disabled_at is not None:
            print("Admin email does not match an enabled ADMIN in this database", file=sys.stderr)
            return 2

    for issue in remaining:
        try:
            with SessionLocal() as db:
                actor = db.scalar(select(User).where(User.email == args.admin_email.lower().strip()))
                if actor is None:
                    raise ValueError("Admin account disappeared")
                # Recheck duplicates to make repeated imports safe.
                existing = db.scalar(select(Market.id).where(Market.jira_issue_id == issue.id))
                if existing:
                    print(f"SKIP {issue.key}: market already exists")
                    continue
                market = create_market(db, issue.key, cutoff, args.liquidity, actor, jira)
            print(f"CREATED {issue.key}: {market.id}")
            successes += 1
        except (JiraError, HTTPException, IntegrityError, ValueError) as exc:
            failures += 1
            print(f"FAILED {issue.key}: {exc}", file=sys.stderr)
    print(f"Finished: created={successes}, failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
