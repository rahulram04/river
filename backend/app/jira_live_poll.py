"""Poll Jira for linked markets without modifying Jira or pricing contracts.

Run from backend/: python -m app.jira_live_poll [--once] [--interval 60]

The poller refreshes mutable Jira display metadata and resolves due markets
using their complete Jira history. It never changes market cutoff, liquidity,
question or share quantities. Jira itself is always read-only.
"""
from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.db_models import AuditLog, Market
from app.domain import aware, now
from app.jira import JiraError, JiraProvider, provider
from app.services import settle

log = logging.getLogger("riverbet.jira_sync")


def reconcile_once(jira: JiraProvider | None = None) -> dict[str, int]:
    """Refresh active linked issues and settle contracts with elapsed cutoffs.

    Each market uses a fresh session so one inaccessible Jira issue cannot
    prevent another market from syncing. A Jira network failure never results
    in an invented settlement outcome.
    """
    jira = jira if jira is not None else provider()
    settings = get_settings()
    counts = {"checked": 0, "updated": 0, "resolved": 0, "failed": 0}
    with SessionLocal() as db:
        market_ids = db.execute(
            select(Market.id).where(Market.status.in_(("OPEN", "CLOSED")))
        ).scalars().all()

    for market_id in market_ids:
        try:
            # Read the identity outside the write transaction, to avoid holding
            # row locks while Jira performs network I/O.
            with SessionLocal() as db:
                market = db.get(Market, market_id)
                if market is None or market.status not in ("OPEN", "CLOSED"):
                    continue
                jira_id = market.jira_issue_id

            issue = jira.issue(jira_id)
            if issue.id != jira_id:
                raise JiraError("Jira returned a mismatched issue ID")
            if issue.project.upper() not in settings.allowed_projects:
                raise JiraError("Issue moved outside allowlisted Jira projects")
            category = jira.category(issue.status_id)

            with SessionLocal() as db:
                market = db.execute(
                    select(Market).where(Market.id == market_id).with_for_update()
                ).scalar_one_or_none()
                if market is None or market.status not in ("OPEN", "CLOSED"):
                    continue
                if market.jira_issue_id != issue.id:
                    raise JiraError("Jira issue identity changed")
                changed = (
                    market.jira_issue_key != issue.key
                    or market.jira_summary != issue.summary
                    or market.jira_project_key != issue.project
                )
                if changed:
                    market.jira_issue_key = issue.key
                    market.jira_summary = issue.summary
                    market.jira_project_key = issue.project
                    db.add(AuditLog(
                        market_id=market.id,
                        action="SYNC",
                        evidence={"jira_issue_id": issue.id, "status_category": category},
                    ))
                    counts["updated"] += 1
                due = aware(market.cutoff) <= now()
                db.commit()

            # Settlement verifies the complete Jira status changelog as of the
            # immutable cutoff. A current 'Done' status is never enough.
            if due:
                with SessionLocal() as db:
                    result = settle(db, market_id, jira)
                if result["status"] == "RESOLVED":
                    counts["resolved"] += 1
            counts["checked"] += 1
            log.info("Jira issue %s (%s) checked; market=%s%s", issue.key, category,
                     market_id, "; metadata updated" if changed else "")
        except JiraError as exc:
            counts["failed"] += 1
            log.warning("Jira sync deferred for market %s: %s", market_id, exc)
        except Exception:
            counts["failed"] += 1
            log.exception("Jira sync failed for market %s", market_id)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only live Jira market synchronization")
    parser.add_argument("--once", action="store_true", help="Run one pass and exit")
    parser.add_argument("--interval", type=int, default=60,
                        help="Seconds between polls (30-3600; default 60)")
    args = parser.parse_args()
    if not 30 <= args.interval <= 3600:
        parser.error("--interval must be 30-3600 seconds")
    if get_settings().jira_mode != "live":
        parser.error("Set JIRA_MODE=live before starting this worker")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("Starting live Jira polling; interval=%ds", args.interval)
    while True:
        result = reconcile_once()
        log.info("Poll complete: %s", result)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
