"""Run one reconciliation worker: python -m app.worker [--once]."""
import argparse
import time
from sqlalchemy import select, or_
from app.db import SessionLocal
from app.db_models import Market
from app.domain import now
from app.jira import provider, JiraError
from app.services import settle


def reconcile_once():
    with SessionLocal() as db:
        ids = db.execute(select(Market.id).where(Market.status.in_(["OPEN", "CLOSED"]),
                                                 Market.cutoff <= now())).scalars().all()
    for market_id in ids:
        with SessionLocal() as db:
            try:
                settle(db, market_id, provider())
            except JiraError as err:
                print(f"Deferred resolution for market {market_id}: {err}")
            except Exception as err:
                db.rollback()
                print(f"Failed to reconcile market {market_id}: {type(err).__name__}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        reconcile_once()
        if args.once:
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
