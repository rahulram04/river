"""Optional real PostgreSQL concurrency test, enabled by TEST_DATABASE_URL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.orm import sessionmaker
import pytest
from fastapi import HTTPException
from app.db import Base
from app import db_models  # register models
from app.db_models import Market, User, LedgerEvent, LedgerEntry, Order
from app.auth import ph
from app.domain import now, get_issuance
from app.jira import MockJira
from app.services import create_market, execute_order, grant_user, user_account


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not configured")
def test_postgres_concurrent_spending_and_idempotency():
    url = os.environ["TEST_DATABASE_URL"]
    if not url.startswith("postgresql"):
        pytest.skip("Requires disposable PostgreSQL instance")
    namespace = "workbet_test_" + uuid.uuid4().hex[:16]
    root = create_engine(url)
    # Unique schema isolates tests and allows running against a shared test PG instance.
    with root.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {namespace}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={namespace},public"})
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        Base.metadata.create_all(engine)
        with session_factory() as db:
            admin = User(email="admin@test.invalid", password_hash=ph.hash("some-admin-password"), role="ADMIN")
            trader = User(email="member@test.invalid", password_hash=ph.hash("some-member-password"), role="MEMBER")
            db.add_all([admin, trader])
            db.flush()
            get_issuance(db)
            grant_user(db, trader, 1)  # enough for only one of two near-0.5-credit buys
            market = create_market(db, "KAN-2", now() + timedelta(days=1), "10", admin, MockJira())
            mid, uid = market.id, trader.id
        def buy(n):
            with session_factory() as db:
                trader = db.get(User, uid)
                try:
                    return execute_order(db, mid, trader, "BUY", "YES", "1", "1", str(uuid.uuid4()))
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, range(2)))
        assert sum(isinstance(x, dict) for x in results) == 1
        assert sorted(x for x in results if isinstance(x, int)) == [400]
        with session_factory() as db:
            assert db.get(Market, mid).q_yes == 1_000_000
            assert user_account(db, uid).balance >= 0
            assert db.scalar(select(func.count(Order.id))) == 1
            for event in db.execute(select(LedgerEvent)).scalars():
                assert db.scalar(select(func.sum(LedgerEntry.delta)).where(LedgerEntry.event_id == event.id)) == 0
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {namespace} CASCADE"))
        root.dispose()
