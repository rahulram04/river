"""Transactional market, wallet and settlement operations."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.db_models import Account, AuditLog, LedgerEntry, LedgerEvent, Market, Order, Position, PriceHistory, User
from app.domain import SCALE, aware, display, get_issuance, micro, now, post, rounded_micro, subsidy_micro
from app.markets.LMSR import LMSRMarket
from app.jira import JiraError, JiraProvider, as_of


def market_engine(m: Market) -> LMSRMarket:
    return LMSRMarket(2, m.liquidity / SCALE, (m.q_yes / SCALE, m.q_no / SCALE))


def prices(m: Market) -> tuple[float, float]:
    return market_engine(m).prices()


def friendly_market_question(summary: str, issue_key: str, cutoff: datetime) -> str:
    from zoneinfo import ZoneInfo

    local = aware(cutoff).astimezone(ZoneInfo("America/New_York"))
    task = " ".join((summary or "").split()).strip(" .?") or "this task"
    date = f"{local:%A}, {local:%b} {local.day}, {local.year}"

    if local.second or local.microsecond:
        return f"Will {task} ({issue_key}) be Done by the deadline on {date}?"

    hour = local.hour % 12 or 12
    minute = f":{local.minute:02d}" if local.minute else ""
    ampm = "AM" if local.hour < 12 else "PM"

    return f"Will {task} ({issue_key}) be Done by {date} at {hour}{minute} {ampm} ET?"


def market_json(m: Market) -> dict:
    yes, no = prices(m)
    effective = "CLOSED" if m.status == "OPEN" and aware(m.cutoff) <= now() else m.status
    return {
        "id": m.id, "jira_issue_key": m.jira_issue_key, "jira_issue_id": m.jira_issue_id,
        "jira_project_key": m.jira_project_key, "summary": m.jira_summary,
        "question": friendly_market_question(m.jira_summary, m.jira_issue_key, m.cutoff),
        "resolution_rule": m.question, "status": effective, "cutoff": aware(m.cutoff).isoformat(),
        "created_at": aware(m.created_at).isoformat(), "liquidity": display(m.liquidity),
        "q_yes": display(m.q_yes), "q_no": display(m.q_no),
        "yes_probability": yes, "no_probability": no, "winner": m.winner,
        "resolution_evidence": m.resolution_evidence,
    }


def user_account(db: Session, user_id: str, lock: bool = False) -> Account:
    query = select(Account).where(Account.user_id == user_id, Account.kind == "USER")
    if lock:
        query = query.with_for_update()
    result = db.execute(query).scalar_one_or_none()
    if result is None:
        raise HTTPException(404, "Wallet not found")
    return result


def maker_account(db: Session, market_id: str, lock: bool = False) -> Account:
    query = select(Account).where(Account.market_id == market_id, Account.kind == "MAKER")
    if lock:
        query = query.with_for_update()
    account = db.execute(query).scalar_one_or_none()
    if account is None:
        raise HTTPException(500, "Market reserve is missing")
    return account


def grant_user(db: Session, user: User, credits: int) -> None:
    issuance = get_issuance(db)
    account = Account(kind="USER", user_id=user.id, balance=0)
    db.add(account)
    db.flush()
    amount = credits * SCALE
    post(db, f"signup:{user.id}", "SIGNUP", {issuance.id: -amount, account.id: amount})


def create_market(db: Session, issue_key: str, cutoff: datetime, liquidity: str, actor: User,
                  jira: JiraProvider) -> Market:
    cutoff = aware(cutoff)
    if cutoff <= now():
        raise HTTPException(422, "Market deadline must be in the future")
    if cutoff.year > now().year + 5:
        raise HTTPException(422, "Market deadline is too far in the future")
    value = micro(liquidity, positive=True)
    if not 1 * SCALE <= value <= 1000 * SCALE:
        raise HTTPException(422, "Liquidity must be between 1 and 1000 credits")
    issue = jira.issue(issue_key.strip())
    from app.config import get_settings
    if issue.project.upper() not in get_settings().allowed_projects:
        raise HTTPException(403, "Jira project is not allowlisted")
    if issue.created > cutoff:
        raise HTTPException(422, "Jira issue did not exist at deadline")
    exists = db.execute(select(Market).where(Market.jira_issue_id == issue.id, Market.cutoff == cutoff)).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "A market for this Jira issue and cutoff already exists")
    market = Market(jira_issue_id=issue.id, jira_issue_key=issue.key,
                    jira_project_key=issue.project, jira_summary=issue.summary,
                    question=f"Will {issue.key} be in a Jira Done-category status at {cutoff.isoformat()}?",
                    status="OPEN", cutoff=cutoff, liquidity=value, q_yes=0, q_no=0)
    db.add(market)
    db.flush()
    reserve = Account(kind="MAKER", market_id=market.id, balance=0)
    db.add(reserve)
    db.flush()
    issuer = get_issuance(db)
    post(db, f"market:subsidy:{market.id}", "SUBSIDY", {issuer.id: -subsidy_micro(value/SCALE),
                                                        reserve.id: subsidy_micro(value/SCALE)})
    db.add(PriceHistory(market_id=market.id, yes_price=0.5, q_yes=0, q_no=0))
    db.add(AuditLog(user_id=actor.id, market_id=market.id, action="CREATE", evidence={"jira_id": issue.id}))
    db.commit()
    return market


def find_market(db: Session, market_id: str, lock: bool = False) -> Market:
    query = select(Market).where(Market.id == market_id)
    if lock:
        query = query.with_for_update()
    m = db.execute(query).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Market not found")
    return m


def position(db: Session, market_id: str, user_id: str, outcome: str, lock: bool = False) -> Position | None:
    query = select(Position).where(Position.market_id == market_id, Position.user_id == user_id,
                                   Position.outcome == outcome)
    if lock:
        query = query.with_for_update()
    return db.execute(query).scalar_one_or_none()


def opposing_position(db: Session, market_id: str, user_id: str, outcome: str) -> Position | None:
    other_outcome = "NO" if outcome == "YES" else "YES"
    return db.execute(select(Position).where(
        Position.market_id == market_id, Position.user_id == user_id,
        Position.outcome == other_outcome, Position.shares > 0
    )).scalar_one_or_none()


def validate_order_shares(shares: int, side: str, held_position: Position | None) -> None:
    if shares % SCALE and not (
        side == "SELL" and held_position is not None and held_position.shares % SCALE
    ):
        raise HTTPException(422, "Orders must use whole shares")


def amount_for(market: Market, side: str, outcome: str, shares: int) -> int:
    if side not in {"BUY", "SELL"} or outcome not in {"YES", "NO"} or shares <= 0:
        raise HTTPException(422, "Invalid side, outcome or share quantity")
    engine = market_engine(market)
    idx = 0 if outcome == "YES" else 1
    try:
        amount = engine.buy(idx, shares/SCALE) if side == "BUY" else engine.sell(idx, shares/SCALE)
    except (IndexError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    result = rounded_micro(amount)
    if result <= 0:
        raise HTTPException(400, "Trade is too small to price at six-decimal precision")
    return result


def quote(db: Session, market_id: str, side: str, outcome: str, shares_text: str, user: User) -> dict:
    m = find_market(db, market_id)
    if m.status != "OPEN" or aware(m.cutoff) <= now():
        raise HTTPException(409, "Market is closed")
    shares = micro(shares_text, positive=True)
    pos = position(db, market_id, user.id, outcome)
    validate_order_shares(shares, side, pos)
    if shares > 10000 * SCALE:
        raise HTTPException(422, "Maximum 10,000 shares per order")
    if side == "BUY":
        if opposing_position(db, market_id, user.id, outcome) is not None:
            raise HTTPException(409, f"Sell your existing position before buying {outcome}")
        if pos is not None and pos.shares % SCALE:
            raise HTTPException(409, "Sell your existing fractional position before buying more shares")
    if side == "SELL" and (pos is None or pos.shares < shares):
        raise HTTPException(400, "Insufficient shares to sell")
    amount = amount_for(m, side, outcome, shares)
    if side == "BUY" and user_account(db, user.id).balance < amount:
        raise HTTPException(400, "Insufficient play credits")
    return {"side": side, "outcome": outcome, "shares": display(shares),
            "amount": display(amount), "yes_probability": prices(m)[0],
            "expires_on_trade": True, "note": "Prices are indicative; send a trade limit to bound slippage."}


def execute_order(db: Session, market_id: str, user: User, side: str, outcome: str,
                  shares_text: str, limit_text: str, idempotency_key: str) -> dict:
    if len(idempotency_key) < 8 or len(idempotency_key) > 80:
        raise HTTPException(422, "Idempotency-Key must be 8-80 characters")
    shares = micro(shares_text, positive=True)
    limit = micro(limit_text, positive=(side == "BUY"))
    if shares > 10000 * SCALE:
        raise HTTPException(422, "Maximum 10,000 shares per order")
    canonical = json.dumps([market_id, side, outcome, shares, limit], separators=(",", ":"))
    bodyhash = hashlib.sha256(canonical.encode()).hexdigest()
    # All operations on a market take the market lock before locking accounts.
    m = find_market(db, market_id, lock=True)
    previous = db.execute(select(Order).where(Order.user_id == user.id,
                                              Order.idempotency_key == idempotency_key)).scalar_one_or_none()
    if previous is not None:
        if previous.payload_hash != bodyhash:
            raise HTTPException(409, "Idempotency key was already used for another order")
        return order_json(previous, m, replay=True)
    if m.status != "OPEN" or aware(m.cutoff) <= now():
        raise HTTPException(409, "Market is closed")
    wallet = user_account(db, user.id, lock=True)
    maker = maker_account(db, market_id, lock=True)
    pos = position(db, market_id, user.id, outcome, lock=True)
    validate_order_shares(shares, side, pos)
    if side == "BUY":
        if opposing_position(db, market_id, user.id, outcome) is not None:
            raise HTTPException(409, f"Sell your existing position before buying {outcome}")
        if pos is not None and pos.shares % SCALE:
            raise HTTPException(409, "Sell your existing fractional position before buying more shares")
    if side == "SELL" and (pos is None or pos.shares < shares):
        raise HTTPException(400, "Insufficient shares to sell")
    amount = amount_for(m, side, outcome, shares)
    if side == "BUY" and amount > limit:
        raise HTTPException(409, "Trade exceeds maximum cost; request a new quote")
    if side == "SELL" and amount < limit:
        raise HTTPException(409, "Trade proceeds are below minimum; request a new quote")
    if side == "BUY" and wallet.balance < amount:
        raise HTTPException(400, "Insufficient play credits")
    if pos is None:
        pos = Position(market_id=market_id, user_id=user.id, outcome=outcome, shares=0)
        db.add(pos)
    signed = shares if side == "BUY" else -shares
    next_yes = m.q_yes + (signed if outcome == "YES" else 0)
    next_no = m.q_no + (signed if outcome == "NO" else 0)
    next_maker = maker.balance + (amount if side == "BUY" else -amount)
    if min(next_yes, next_no) < 0 or next_maker < max(next_yes, next_no):
        raise HTTPException(400, "Market solvency check failed")
    order = Order(market_id=market_id, user_id=user.id, side=side, outcome=outcome,
                  shares=shares, amount=amount, execution_yes_probability=0.5,
                  idempotency_key=idempotency_key, payload_hash=bodyhash)
    db.add(order)
    db.flush()
    pos.shares += signed
    m.q_yes, m.q_no = next_yes, next_no
    order.execution_yes_probability = prices(m)[0]
    postings = {wallet.id: -amount, maker.id: amount} if side == "BUY" else {maker.id: -amount, wallet.id: amount}
    post(db, f"order:{order.id}", "ORDER", postings)
    db.add(PriceHistory(market_id=m.id, order_id=order.id, yes_price=prices(m)[0],
                        q_yes=m.q_yes, q_no=m.q_no))
    db.commit()
    return order_json(order, m, replay=False)


def order_json(o: Order, m: Market, *, replay: bool = False) -> dict:
    return {"id": o.id, "market_id": o.market_id, "side": o.side, "outcome": o.outcome,
            "shares": display(o.shares), "amount": display(o.amount),
            "yes_probability": o.execution_yes_probability, "created_at": aware(o.created_at).isoformat(),
            "idempotent_replay": replay}


def settle(db: Session, market_id: str, jira: JiraProvider, actor: User | None = None) -> dict:
    m = find_market(db, market_id, lock=True)
    if m.status in {"RESOLVED", "VOID"}:
        return market_json(m)
    if aware(m.cutoff) > now():
        raise HTTPException(409, "Deadline has not passed")
    if m.status == "OPEN":
        m.status = "CLOSED"
        db.commit()
        m = find_market(db, market_id, lock=True)
    try:
        issue = jira.issue(m.jira_issue_id)
        from app.config import get_settings
        if issue.project.upper() not in get_settings().allowed_projects:
            raise JiraError("Issue moved outside allowlisted projects")
        winner, evidence = as_of(issue, jira.history(issue.id), aware(m.cutoff), jira)
    except JiraError:
        db.rollback()
        raise
    maker = maker_account(db, m.id, lock=True)
    positions = db.execute(select(Position).where(Position.market_id == m.id,
                                                  Position.shares > 0).order_by(Position.user_id)).scalars().all()
    deltas: dict[str, int] = {maker.id: 0}
    for p in positions:
        if p.outcome == winner:
            account = user_account(db, p.user_id, lock=True)
            deltas[account.id] = deltas.get(account.id, 0) + p.shares
            deltas[maker.id] -= p.shares
    if maker.balance + deltas[maker.id] < 0:
        raise HTTPException(500, "Market reserve insufficient for settlement")
    issuer = get_issuance(db)
    residual = maker.balance + deltas[maker.id]
    deltas[issuer.id] = deltas.get(issuer.id, 0) + residual
    deltas[maker.id] -= residual
    post(db, f"settlement:{m.id}", "SETTLEMENT", deltas)
    m.winner = winner
    m.status = "RESOLVED"
    m.resolved_at = now()
    m.resolution_evidence = {**evidence, "jira_id": issue.id, "cutoff": aware(m.cutoff).isoformat()}
    m.jira_issue_key = issue.key
    m.jira_summary = issue.summary
    db.add(AuditLog(user_id=actor.id if actor else None, market_id=m.id, action="RESOLVE", evidence=m.resolution_evidence))
    db.commit()
    return market_json(m)


def void_market(db: Session, market_id: str, actor: User, reason: str) -> dict:
    if len(reason.strip()) < 12:
        raise HTTPException(422, "Provide a reason of at least 12 characters")
    m = find_market(db, market_id, lock=True)
    if m.status in {"RESOLVED", "VOID"}:
        raise HTTPException(409, "Cannot void an already finalized market")
    yes, no = prices(m)
    maker = maker_account(db, market_id, lock=True)
    deltas: dict[str, int] = {maker.id: 0}
    for p in db.execute(select(Position).where(Position.market_id == m.id, Position.shares > 0)).scalars():
        account = user_account(db, p.user_id, lock=True)
        payout = rounded_micro((p.shares / SCALE) * (yes if p.outcome == "YES" else no))
        deltas[account.id] = deltas.get(account.id, 0) + payout
        deltas[maker.id] -= payout
    if maker.balance + deltas[maker.id] < 0:
        raise HTTPException(500, "Market reserve insufficient to void")
    issuer = get_issuance(db)
    residual = maker.balance + deltas[maker.id]
    deltas[issuer.id] = deltas.get(issuer.id, 0) + residual
    deltas[maker.id] -= residual
    post(db, f"void:{m.id}", "VOID", deltas)
    m.status = "VOID"
    m.resolved_at = now()
    m.resolution_evidence = {"void_reason": reason.strip(), "yes_price": yes, "no_price": no,
                             "policy": "Outstanding shares paid at pre-void LMSR marginal prices"}
    db.add(AuditLog(user_id=actor.id, market_id=m.id, action="VOID", reason=reason.strip(),
                    evidence=m.resolution_evidence))
    db.commit()
    return market_json(m)


def sync_market(db: Session, market_id: str, jira: JiraProvider, actor: User | None = None) -> dict:
    m = find_market(db, market_id, lock=True)
    issue = jira.issue(m.jira_issue_id)
    from app.config import get_settings
    if issue.project.upper() not in get_settings().allowed_projects:
        raise JiraError("Issue moved outside allowlisted project")
    m.jira_issue_key = issue.key
    m.jira_summary = issue.summary
    db.add(AuditLog(user_id=actor.id if actor else None, market_id=m.id, action="SYNC"))
    db.commit()
    if m.status not in {"RESOLVED", "VOID"} and aware(m.cutoff) <= now():
        return settle(db, m.id, jira, actor)
    return market_json(m)
