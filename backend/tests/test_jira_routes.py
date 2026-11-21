"""Read-only authenticated Jira route regression tests."""
from tests.test_api import create, login_admin
from tests.conftest import register


def test_admin_can_read_mock_issue(api):
    client, sessions = api
    login_admin(client, sessions)
    res = client.get("/api/jira/issues/KAN-1")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["issue_key"] == "KAN-1"
    assert body["status_category"] == "indeterminate"
    assert body["source"] == "JIRA_MOCK"


def test_member_can_read_only_linked_market_issue(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"], "KAN-2")
    register(client)
    assert client.get("/api/jira/issues/KAN-1").status_code == 403
    status = client.get(f"/api/jira/markets/{market_id}/status")
    assert status.status_code == 200, status.text
    assert status.json()["status_category"] == "done"
    assert client.get("/api/jira/markets/not-found/status").status_code == 404


def test_unauthenticated_jira_routes_are_rejected(api):
    client, sessions = api
    assert client.get("/api/jira/issues/KAN-1").status_code == 401
    assert client.get("/api/jira/markets/anything/status").status_code == 401
