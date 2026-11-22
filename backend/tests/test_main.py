"""Regression tests for the authenticated, database-backed API."""
from decimal import Decimal
from uuid import uuid4

import pytest

from tests.conftest import register
from tests.test_api import login_admin, create


@pytest.fixture
def market_case(api):
    client, sessions = api
    admin = login_admin(client, sessions)
    mid = create(client, admin["csrf_token"])
    member = register(client)
    return client, mid, {"X-CSRF-Token": member["csrf_token"]}


def market(client, mid):
    response = client.get(f"/api/markets/{mid}")
    assert response.status_code == 200, response.text
    return response.json()


def balance(client):
    return Decimal(client.get("/api/me/wallet").json()["balance"])


def trade(client, mid, headers, side):
    body = {"side": side, "outcome": "YES", "shares": "1"}
    quote = client.post(f"/api/markets/{mid}/quote", json=body, headers=headers)
    assert quote.status_code == 200, quote.text
    limit = "max_cost" if side == "BUY" else "min_proceeds"
    result = client.post(
        f"/api/markets/{mid}/orders",
        json={**body, limit: quote.json()["amount"]},
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_read_market_returns_prices_and_quantities(market_case):
    client, mid, _ = market_case
    m = market(client, mid)
    assert m["id"] == mid
    assert m["q_yes"] == m["q_no"] == "0.000000"
    assert m["yes_probability"] == m["no_probability"] == 0.5


def test_read_unknown_market_returns_not_found(api):
    client, _ = api
    register(client)
    res = client.get(f"/api/markets/{uuid4()}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Market not found"


def test_create_and_read_trader(api):
    client, _ = api
    member = register(client)
    assert member["role"] == "MEMBER"
    assert balance(client) == 1000
    assert client.get("/api/me/portfolio").json()["holdings"] == []


def test_duplicate_trader_returns_conflict(api):
    client, _ = api
    register(client)
    res = client.post("/api/auth/register", json={
        "email": "alice@example.com", "password": "correct-horse-battery-123"
    })
    assert res.status_code == 409
    assert balance(client) == 1000


def test_buy_endpoint_updates_market_and_trader(market_case):
    client, mid, headers = market_case
    before = balance(client)
    order = trade(client, mid, headers, "BUY")
    assert Decimal(order["amount"]) > 0
    assert balance(client) == before - Decimal(order["amount"])
    assert market(client, mid)["q_yes"] == "1.000000"
    assert market(client, mid)["yes_probability"] > 0.5
    holdings = client.get("/api/me/portfolio").json()["holdings"]
    assert len(holdings) == 1
    assert holdings[0]["market_id"] == mid
    assert holdings[0]["outcome"] == "YES"
    assert holdings[0]["shares"] == "1.000000"


def test_sell_endpoint_returns_revenue_and_updates_position(market_case):
    client, mid, headers = market_case
    before = balance(client)
    trade(client, mid, headers, "BUY")
    sold = trade(client, mid, headers, "SELL")
    assert Decimal(sold["amount"]) > 0
    assert balance(client) == before
    assert market(client, mid)["q_yes"] == "0.000000"
    assert client.get("/api/me/portfolio").json()["holdings"] == []


def test_trade_requires_authenticated_trader(market_case):
    client, mid, headers = market_case
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    res = client.post(f"/api/markets/{mid}/orders", json={
        "side": "BUY", "outcome": "YES", "shares": "1", "max_cost": "1"
    }, headers={"Idempotency-Key": str(uuid4())})
    assert res.status_code == 401


def test_unaffordable_buy_returns_bad_request_without_mutation(market_case):
    client, mid, headers = market_case
    before = balance(client)
    res = client.post(f"/api/markets/{mid}/orders", json={
        "side": "BUY", "outcome": "YES", "shares": "10000", "max_cost": "10000"
    }, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == "Insufficient play credits"
    assert balance(client) == before
    assert market(client, mid)["q_yes"] == "0.000000"
    assert client.get("/api/me/orders").json()["items"] == []


def test_invalid_trade_request_returns_validation_error(market_case):
    client, mid, headers = market_case
    res = client.post(f"/api/markets/{mid}/orders", json={
        "side": "BUY", "outcome": "YES", "shares": "0", "max_cost": "1"
    }, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert res.status_code == 422
    assert market(client, mid)["q_yes"] == "0.000000"
