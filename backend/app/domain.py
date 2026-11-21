"""Fixed-point arithmetic, bookkeeping, and time helpers."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db_models import Account, LedgerEntry, LedgerEvent

SCALE = 1_000_000
ISSUANCE_ID = "00000000-0000-0000-0000-000000000001"


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def micro(value: str | int | Decimal, *, positive: bool = False) -> int:
    try:
        decimal_value = Decimal(str(value))
        n = decimal_value * SCALE
        if not n.is_finite() or n != n.to_integral_value() or abs(n) > 2**60:
            raise ValueError
        result = int(n)
        if positive and result <= 0:
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, "Amount must be a finite decimal with at most six places")


def display(value: int) -> str:
    return f"{Decimal(value) / SCALE:.6f}"


def rounded_micro(value: float) -> int:
    if not math.isfinite(value) or abs(value) > 1e12:
        raise HTTPException(400, "Trade exceeds supported amount")
    return int((Decimal(str(value)) * SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def subsidy_micro(liquidity: float) -> int:
    # One extra credit covers conservative rounding across a small team demo;
    # all trades enforce a post-trade solvency check as well.
    return int((Decimal(str(liquidity * math.log(2))) * SCALE).to_integral_value(rounding=ROUND_CEILING)) + SCALE


def get_issuance(db: Session) -> Account:
    account = db.get(Account, ISSUANCE_ID)
    if account is None:
        account = Account(id=ISSUANCE_ID, kind="ISSUANCE", balance=0)
        db.add(account)
        db.flush()
    return account


def post(db: Session, reference: str, kind: str, deltas: dict[str, int]) -> LedgerEvent:
    """Append one balanced event and update corresponding cached account balances."""
    if not deltas or sum(deltas.values()) != 0:
        raise ValueError("Ledger event is not balanced")
    accounts = {a.id: a for a in db.execute(
        select(Account).where(Account.id.in_(deltas)).order_by(Account.id).with_for_update()
    ).scalars()}
    if len(accounts) != len(deltas):
        raise ValueError("Missing ledger account")
    for aid, delta in deltas.items():
        updated = accounts[aid].balance + delta
        if accounts[aid].kind != "ISSUANCE" and updated < 0:
            raise HTTPException(400, "Insufficient play credits or market reserve")
        accounts[aid].balance = updated
    event = LedgerEvent(reference=reference, event_type=kind)
    db.add(event)
    db.flush()
    for aid, delta in deltas.items():
        db.add(LedgerEntry(event_id=event.id, account_id=aid, delta=delta))
    return event
