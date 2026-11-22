"""Persisted domain objects. All financial amounts and shares are integers in 1e-6 units."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="MEMBER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # USER, MAKER, ISSUANCE
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), unique=True)
    market_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("markets.id"), unique=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    __table_args__ = (CheckConstraint("kind IN ('USER','MAKER','ISSUANCE')", name="account_kind"),)


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    jira_issue_id: Mapped[str] = mapped_column(String(64), nullable=False)
    jira_issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    jira_project_key: Mapped[str] = mapped_column(String(32), nullable=False)
    jira_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    question: Mapped[str] = mapped_column(String(800), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    liquidity: Mapped[int] = mapped_column(BigInteger, nullable=False)  # microcredits
    q_yes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    q_no: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    winner: Mapped[str | None] = mapped_column(String(3))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_evidence: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("jira_issue_id", "cutoff", name="unique_issue_cutoff"),
        CheckConstraint("liquidity > 0 AND q_yes >= 0 AND q_no >= 0", name="market_positive"),
        Index("ix_markets_status_cutoff", "status", "cutoff"),
    )


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(3), nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    __table_args__ = (UniqueConstraint("market_id", "user_id", "outcome", name="uq_position"), CheckConstraint("shares >= 0", name="positive_shares"))


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    outcome: Mapped[str] = mapped_column(String(3), nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    execution_yes_probability: Mapped[float] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user"), Index("ix_orders_market_created", "market_id", "created_at"))


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("orders.id"))
    yes_price: Mapped[float] = mapped_column(nullable=False)
    q_yes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    q_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LedgerEvent(Base):
    __tablename__ = "ledger_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("ledger_events.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AuditLog(Base):
    __tablename__ = "admin_audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    market_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("markets.id"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
