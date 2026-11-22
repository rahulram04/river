"""Live polling behavior tested without making network calls to Jira."""
from dataclasses import replace
from datetime import datetime, timezone
from sqlalchemy import func, select

from app.db_models import AuditLog, Market
from app.jira import MockJira, JiraError
from app import jira_live_poll
from tests.test_api import create, login_admin


class RevisedMockJira(MockJira):
    def issue(self, key_or_id):
        issue = super().issue(key_or_id)
        return replace(issue, key="KAN-99", summary="New Jira issue summary")


class OutOfScopeJira(MockJira):
    def issue(self, key_or_id):
        return replace(super().issue(key_or_id), project="EXTERNAL")


class UnavailableJira(MockJira):
    def issue(self, key_or_id):
        raise JiraError("Service temporarily unavailable")


def test_poll_updates_only_changed_jira_metadata(api, monkeypatch):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"], "KAN-1")
    monkeypatch.setattr(jira_live_poll, "SessionLocal", sessions)

    result = jira_live_poll.reconcile_once(RevisedMockJira())
    assert result == {"checked": 1, "updated": 1, "resolved": 0, "failed": 0}
    with sessions() as db:
        market = db.get(Market, market_id)
        assert market.jira_issue_key == "KAN-99"
        assert market.jira_summary == "New Jira issue summary"
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "SYNC")) == 1

    result = jira_live_poll.reconcile_once(RevisedMockJira())
    assert result["updated"] == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "SYNC")) == 1


def test_poll_resolves_overdue_market_from_history(api, monkeypatch):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"], "KAN-2")
    with sessions() as db:
        market = db.get(Market, market_id)
        market.cutoff = datetime(2026, 11, 17, 18, tzinfo=timezone.utc)
        db.commit()
    monkeypatch.setattr(jira_live_poll, "SessionLocal", sessions)
    result = jira_live_poll.reconcile_once(MockJira())
    assert result["resolved"] == 1
    with sessions() as db:
        assert db.get(Market, market_id).winner == "YES"


def test_poll_refuses_out_of_scope_issue(api, monkeypatch):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"], "KAN-1")
    monkeypatch.setattr(jira_live_poll, "SessionLocal", sessions)
    result = jira_live_poll.reconcile_once(OutOfScopeJira())
    assert result["failed"] == 1
    with sessions() as db:
        assert db.get(Market, market_id).jira_issue_key == "KAN-1"


def test_jira_failure_does_not_mutate_market(api, monkeypatch):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"], "KAN-1")
    monkeypatch.setattr(jira_live_poll, "SessionLocal", sessions)
    result = jira_live_poll.reconcile_once(UnavailableJira())
    assert result["failed"] == 1
    with sessions() as db:
        assert db.get(Market, market_id).status == "OPEN"
