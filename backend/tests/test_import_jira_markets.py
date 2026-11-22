"""Unit tests for the additive Jira bulk-market importer."""
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import import_jira_markets as importer
from app.db import Base
from app.db_models import Market, User
from app.domain import get_issuance
from app.jira import MockJira


class FakeLiveJira:
    def __init__(self):
        self.calls = []

    def _get(self, path, params=None):
        self.calls.append((path, params))
        if "nextPageToken" not in params:
            return {
                "issues": [
                    {"id": "10011", "key": "KAN-1", "fields": {"summary": "First issue", "created": "2026-01-01T10:00:00Z", "project": {"key": "KAN"}, "status": {"id": "12", "statusCategory": {"key": "indeterminate"}}}},
                    {"id": "10012", "key": "KAN-2", "fields": {"summary": "Already done", "created": "2026-01-02T10:00:00Z", "project": {"key": "KAN"}, "status": {"id": "14", "statusCategory": {"key": "done"}}}},
                ],
                "nextPageToken": "next-page",
                "isLast": False,
            }
        return {
            "issues": [{"id": "10013", "key": "KAN-3", "fields": {"summary": "Second active issue", "created": "2026-01-03T10:00:00Z", "project": {"key": "KAN"}, "status": {"id": "13", "statusCategory": {"key": "new"}}}}],
            "isLast": True,
        }


def test_live_search_paginates_skips_done_and_uses_jql():
    jira = FakeLiveJira()
    issues = importer.search_live_jira(jira, "KAN", "Test", 100)
    assert [issue.key for issue in issues] == ["KAN-1", "KAN-3"]
    assert jira.calls[0][0] == "/rest/api/3/search/jql"
    assert 'issuetype = "Test"' in jira.calls[0][1]["jql"]
    assert jira.calls[1][1]["nextPageToken"] == "next-page"


def test_mock_discovery_can_include_all_four_fixture_cases():
    jira = MockJira()
    assert [issue.key for issue in importer.discover(jira, "KAN", None, 500, False)] == ["KAN-1", "KAN-3"]
    assert [issue.key for issue in importer.discover(jira, "KAN", None, 500, True)] == ["KAN-1", "KAN-2", "KAN-3", "KAN-4"]


def test_apply_is_idempotent_without_touching_other_data(tmp_path, monkeypatch, capsys):
    from app.db import new_engine
    engine = new_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        get_issuance(db)
        db.add(User(email="admin@example.com", password_hash="unused", role="ADMIN"))
        db.commit()
    monkeypatch.setattr(importer, "SessionLocal", sessions)
    monkeypatch.setattr(importer, "provider", lambda: MockJira())
    from app.config import Settings
    monkeypatch.setattr(importer, "get_settings", lambda: Settings(jira_mode="mock"))

    args = ["--project", "KAN", "--include-mock-done", "--days", "7", "--admin-email", "admin@example.com"]
    assert importer.main(args) == 0  # Preview only
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Market)) == 0
    assert importer.main(args + ["--apply"]) == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Market)) == 4
    assert importer.main(args + ["--apply"]) == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Market)) == 4
    engine.dispose()


def test_apply_requires_admin_email():
    assert importer.main(["--apply"]) == 2
