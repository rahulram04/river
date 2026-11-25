import uuid
from datetime import timedelta, datetime, timezone
import pytest
from sqlalchemy import select, func
from app.db_models import User, Market, Account, LedgerEvent, LedgerEntry, Position, Order
from app.auth import ph
from app.domain import SCALE, now
from tests.conftest import register
from app.jira import MockJira, as_of, JiraError
from app.services import settle, void_market, create_market


def make_admin(sessions, email="admin@example.com"):
    with sessions() as db:
        user = User(email=email, password_hash=ph.hash("admin-good-password-123"), role="ADMIN")
        db.add(user)
        db.commit()
        return user.id


def login_admin(client, sessions):
    make_admin(sessions)
    res = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-good-password-123"})
    assert res.status_code == 200, res.text
    return client.get("/api/auth/me").json()


def create(client, csrf, issue="KAN-2"):
    res = client.post("/api/markets", headers={"X-CSRF-Token": csrf},
                      json={"jira_issue_key": issue,
                            "cutoff": (now() + timedelta(days=1)).isoformat(),
                            "liquidity": "10.000000"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_requires_auth_csrf_and_admin(api):
    client, sessions = api
    assert client.get("/api/markets").status_code == 401
    alice = register(client)
    assert client.get("/api/me/wallet").json()["balance"] == "1000.000000"
    assert client.post("/api/markets", json={"jira_issue_key":"KAN-1", "cutoff":now().isoformat()}).status_code == 403
    assert client.post("/api/markets", headers={"X-CSRF-Token":alice["csrf_token"]},
                       json={"jira_issue_key":"KAN-1", "cutoff":(now()+timedelta(days=1)).isoformat()}).status_code == 403
    assert client.post("/api/auth/register", json={"email":"bob@example.com", "password":"simplebad"}).status_code == 422
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token":alice["csrf_token"]}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_market_trading_idempotency_slippage_and_ledger(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"])
    assert client.get(f"/api/markets/{market_id}").json()["yes_probability"] == .5
    register(client)
    alice = client.get("/api/auth/me").json()
    assert client.post(f"/api/markets/{market_id}/quote", json={"side":"BUY","outcome":"YES","shares":"2.000000"}).status_code == 403
    csrf = {"X-CSRF-Token":alice["csrf_token"]}
    quote = client.post(f"/api/markets/{market_id}/quote", headers=csrf,
                        json={"side":"BUY","outcome":"YES","shares":"2.000000"})
    assert quote.status_code == 200, quote.text
    amt = quote.json()["amount"]
    key = str(uuid.uuid4())
    req = {"side":"BUY","outcome":"YES","shares":"2.000000","max_cost":amt}
    order = client.post(f"/api/markets/{market_id}/orders", headers={**csrf, "Idempotency-Key":key}, json=req)
    assert order.status_code == 201, order.text
    assert order.json()["yes_probability"] > .5
    replay = client.post(f"/api/markets/{market_id}/orders", headers={**csrf, "Idempotency-Key":key}, json=req)
    assert replay.status_code == 201 and replay.json()["idempotent_replay"]
    assert order.json()["id"] == replay.json()["id"]
    modified = client.post(f"/api/markets/{market_id}/orders", headers={**csrf, "Idempotency-Key":key},
                           json={**req, "shares":"1.000000"})
    assert modified.status_code == 409
    fail = client.post(f"/api/markets/{market_id}/orders", headers={**csrf,"Idempotency-Key":str(uuid.uuid4())},
                       json={**req,"max_cost":"0.000001"})
    assert fail.status_code == 409
    assert client.get(f"/api/markets/{market_id}").json()["q_yes"] == "2.000000"
    sellquote = client.post(f"/api/markets/{market_id}/quote", headers=csrf,
                            json={"side":"SELL","outcome":"YES","shares":"2.000000"}).json()
    sold = client.post(f"/api/markets/{market_id}/orders", headers={**csrf,"Idempotency-Key":str(uuid.uuid4())},
                       json={"side":"SELL","outcome":"YES","shares":"2.000000","min_proceeds":sellquote["amount"]})
    assert sold.status_code == 201, sold.text
    assert client.get(f"/api/markets/{market_id}").json()["q_yes"] == "0.000000"
    assert client.get("/api/me/wallet").json()["balance"] == "1000.000000"
    with sessions() as db:
        events = db.execute(select(LedgerEvent)).scalars().all()
        for e in events:
            assert db.scalar(select(func.sum(LedgerEntry.delta)).where(LedgerEntry.event_id == e.id)) == 0
        assert db.scalar(select(func.count(Order.id))) == 2


def test_positions_are_single_sided_and_switch_only_after_closing(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"])
    register(client)
    csrf = {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}

    yes_quote = client.post(f"/api/markets/{market_id}/quote", headers=csrf,
                            json={"side":"BUY","outcome":"YES","shares":"2"}).json()
    yes_order = client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={"side":"BUY","outcome":"YES","shares":"2","max_cost":yes_quote["amount"]},
    )
    assert yes_order.status_code == 201, yes_order.text

    no_request = {"side":"BUY","outcome":"NO","shares":"1"}
    assert client.post(f"/api/markets/{market_id}/quote", headers=csrf,
                       json=no_request).status_code == 409
    assert client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={**no_request, "max_cost":"100"},
    ).status_code == 409

    sell_quote = client.post(
        f"/api/markets/{market_id}/quote", headers=csrf,
        json={"side":"SELL","outcome":"YES","shares":"2"},
    ).json()
    sold = client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={"side":"SELL","outcome":"YES","shares":"2",
              "min_proceeds":sell_quote["amount"]},
    )
    assert sold.status_code == 201, sold.text

    no_quote = client.post(f"/api/markets/{market_id}/quote", headers=csrf,
                           json=no_request)
    assert no_quote.status_code == 200, no_quote.text
    no_order = client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={**no_request, "max_cost":no_quote.json()["amount"]},
    )
    assert no_order.status_code == 201, no_order.text
    holdings = client.get("/api/me/portfolio").json()["holdings"]
    assert len(holdings) == 1
    assert holdings[0]["outcome"] == "NO"


def test_rejects_fractional_share_orders(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    market_id = create(client, admin["csrf_token"])
    register(client)
    csrf = {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}
    fractional = {"side":"BUY","outcome":"YES","shares":"1.25"}

    quote = client.post(f"/api/markets/{market_id}/quote", headers=csrf, json=fractional)
    assert quote.status_code == 422
    order = client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={**fractional, "max_cost":"100"},
    )
    assert order.status_code == 422
    assert client.get(f"/api/markets/{market_id}").json()["q_yes"] == "0.000000"

    whole_quote = client.post(
        f"/api/markets/{market_id}/quote", headers=csrf,
        json={"side":"BUY","outcome":"YES","shares":"1"},
    ).json()
    bought = client.post(
        f"/api/markets/{market_id}/orders",
        headers={**csrf, "Idempotency-Key":str(uuid.uuid4())},
        json={"side":"BUY","outcome":"YES","shares":"1","max_cost":whole_quote["amount"]},
    )
    assert bought.status_code == 201, bought.text
    fractional_sell = client.post(
        f"/api/markets/{market_id}/quote", headers=csrf,
        json={"side":"SELL","outcome":"YES","shares":"0.5"},
    )
    assert fractional_sell.status_code == 422


def test_rejects_unauthorized_mint_and_over_sell(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    mid = create(client, admin["csrf_token"])
    register(client)
    csrf = {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}
    assert client.post("/traders/malicious", json={"starting_cash":1000000}).status_code == 404
    assert client.post(f"/api/markets/{mid}/quote", headers=csrf,
                       json={"side":"SELL","outcome":"NO","shares":"1.000000"}).status_code == 400
    assert client.get("/api/me/wallet").json()["balance"] == "1000.000000"


def test_resolution_and_replay(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    mid = create(client, admin["csrf_token"])
    register(client)
    csrf = {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}
    q = client.post(f"/api/markets/{mid}/quote",headers=csrf,
                    json={"side":"BUY","outcome":"YES","shares":"5"}).json()
    order = client.post(f"/api/markets/{mid}/orders",headers={**csrf,"Idempotency-Key":str(uuid.uuid4())},
                        json={"side":"BUY","outcome":"YES","shares":"5","max_cost":q["amount"]})
    assert order.status_code == 201, order.text
    before = float(client.get("/api/me/wallet").json()["balance"])
    # Test-only database deadline adjustment to avoid sleeping for a day.
    with sessions() as db:
        m = db.get(Market, mid)
        m.cutoff = datetime(2026,11,17,18,0,tzinfo=timezone.utc)
        db.commit()
    result = client.post(f"/api/admin/markets/{mid}/resolve",headers=csrf)
    assert result.status_code == 403
    with sessions() as db:
        result = settle(db, mid, MockJira())
        assert result["winner"] == "YES"
        result2 = settle(db, mid, MockJira())
        assert result2["winner"] == "YES"
    assert float(client.get("/api/me/wallet").json()["balance"]) == pytest.approx(before+5)
    assert client.post(f"/api/markets/{mid}/orders",headers={**csrf,"Idempotency-Key":str(uuid.uuid4())},
                       json={"side":"BUY","outcome":"YES","shares":"1","max_cost":"100"}).status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count(LedgerEvent.id)).where(LedgerEvent.event_type == "SETTLEMENT")) == 1


def test_jira_status_as_of_edges():
    mock = MockJira()
    # KAN-3 done then reopened before the later cutoff: NO; between transitions: YES.
    issue = mock.issue("KAN-3")
    changes = mock.history(issue.id)
    assert as_of(issue, changes, datetime(2026,11,16,14,tzinfo=timezone.utc), mock)[0] == "YES"
    assert as_of(issue, changes, datetime(2026,11,16,16,tzinfo=timezone.utc), mock)[0] == "NO"
    issue2 = mock.issue("KAN-4")
    assert as_of(issue2, mock.history(issue2.id), datetime(2026,11,19,tzinfo=timezone.utc), mock)[0] == "NO"
    assert as_of(issue2, mock.history(issue2.id), datetime(2026,11,21,tzinfo=timezone.utc), mock)[0] == "YES"


def test_void_pays_mark_to_market(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    mid = create(client, admin["csrf_token"])
    register(client)
    csrf = {"X-CSRF-Token":client.get("/api/auth/me").json()["csrf_token"]}
    q = client.post(f"/api/markets/{mid}/quote", headers=csrf,
                    json={"side":"BUY","outcome":"NO","shares":"5"}).json()
    assert client.post(f"/api/markets/{mid}/orders", headers={**csrf,"Idempotency-Key":str(uuid.uuid4())},
                       json={"side":"BUY","outcome":"NO","shares":"5","max_cost":q["amount"]}).status_code == 201
    with sessions() as db:
        admin_user = db.execute(select(User).where(User.role == "ADMIN")).scalar_one()
        result = void_market(db, mid, admin_user, "Invalid deadline contract")
        assert result["status"] == "VOID"
        assert db.get(Market, mid).resolution_evidence["policy"]


def test_registration_cannot_mint_twice(api):
    client, sessions = api
    register(client)
    again = client.post("/api/auth/register", json={"email":"alice@example.com", "password":"correct-horse-battery-123"})
    assert again.status_code == 409
    assert client.get("/api/me/wallet").json()["balance"] == "1000.000000"
    with sessions() as db:
        assert db.scalar(select(func.count(LedgerEvent.id)).where(LedgerEvent.event_type == "SIGNUP")) == 1


def test_invalid_csrf_rejected_even_with_session(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    mid = create(client, admin["csrf_token"])
    register(client)
    malformed = client.post(f"/api/markets/{mid}/quote", headers={"X-CSRF-Token":"invalid"},
                            json={"side":"BUY","outcome":"NO","shares":"1"})
    assert malformed.status_code == 403


def test_same_issue_and_deadline_not_duplicated(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    cutoff = (now() + timedelta(days=1)).isoformat()
    body = {"jira_issue_key":"KAN-2", "cutoff":cutoff, "liquidity":"10"}
    headers = {"X-CSRF-Token": admin["csrf_token"]}
    assert client.post("/api/markets", json=body, headers=headers).status_code == 201
    assert client.post("/api/markets", json=body, headers=headers).status_code == 409


def test_ambiguous_jira_history_does_not_guess():
    from app.jira import Transition, JiraIssue
    mock = MockJira()
    issue = JiraIssue("55", "KAN-55", "KAN", "Test", "3", datetime(2026,1,1,tzinfo=timezone.utc))
    changes = [Transition(datetime(2026,11,1,tzinfo=timezone.utc), "1", "2"),
               Transition(datetime(2026,11,2,tzinfo=timezone.utc), "1", "3")]
    with pytest.raises(JiraError):
        as_of(issue, changes, datetime(2026,11,3,tzinfo=timezone.utc), mock)
