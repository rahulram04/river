"""River's authenticated API. All trades use server-side session identity."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth import SESSION_COOKIE, admin, create_session, get_identity, member, ph, protected, rate_limit, verify_password
from app.config import get_settings
from app.db import get_db
from app.db_models import Account, AuditLog, Market, Order, Position, PriceHistory, SessionToken, User
from app.domain import aware, display, get_issuance, now
from app.jira import JiraError, provider
from app.services import (create_market, execute_order, find_market, grant_user, market_json, order_json,
                          position, quote, settle, sync_market, user_account, void_market, prices)

settings = get_settings()
app = FastAPI(title="River Work-Item Prediction Market", version="0.2.0",
              description="Play credits only. Prices are not calibrated probabilities.")
app.add_middleware(CORSMiddleware, allow_origins=[settings.web_origin], allow_credentials=True,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])


@app.middleware("http")
async def check_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin != settings.web_origin:
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
    return await call_next(request)


@app.exception_handler(JiraError)
def jira_error_handler(request: Request, exc: JiraError):
    # Do not expose upstream response bodies, URLs with credentials or raw metadata.
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class MarketCreate(BaseModel):
    jira_issue_key: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
    cutoff: datetime
    liquidity: str = "10.000000"

    @field_validator("cutoff")
    @classmethod
    def must_be_timezone_aware(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cutoff must include a UTC offset")
        return value


class OrderRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    outcome: Literal["YES", "NO"]
    shares: str
    max_cost: str | None = None
    min_proceeds: str | None = None


class QuoteRequest(BaseModel):
    side: Literal["BUY", "SELL"]
    outcome: Literal["YES", "NO"]
    shares: str


class VoidRequest(BaseModel):
    reason: str = Field(min_length=12, max_length=500)


def public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/api/auth/register", status_code=201)
def register(data: Credentials, response: Response, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"register:{request.client.host if request.client else 'unknown'}")
    email = data.email.lower().strip()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise HTTPException(409, "Email already registered")
    user = User(email=email, password_hash=ph.hash(data.password), role="MEMBER")
    try:
        db.add(user)
        db.flush()
        grant_user(db, user, settings.initial_play_credits)
        create_session(db, user, response)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    return public_user(user)


@app.post("/api/auth/login")
def login(data: Credentials, response: Response, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"login:{request.client.host if request.client else 'unknown'}")
    user = db.execute(select(User).where(User.email == data.email.lower().strip())).scalar_one_or_none()
    if user is None or user.disabled_at is not None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    create_session(db, user, response)
    db.commit()
    return public_user(user)


@app.get("/api/auth/me")
def me(identity: tuple = Depends(get_identity)):
    user, session = identity
    return {**public_user(user), "csrf_token": session.csrf_token, "jira_mode": settings.jira_mode}


@app.post("/api/auth/logout")
def logout(response: Response, user: User = Depends(protected),
           identity: tuple = Depends(get_identity), db: Session = Depends(get_db)):
    _, session = identity
    session.revoked_at = now()
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/markets")
def markets(db: Session = Depends(get_db), user: User = Depends(member),
            status: str | None = None, project: str | None = None,
            limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    query = select(Market)
    count = select(func.count()).select_from(Market)
    if status and status != "ALL":
        if status == "OPEN":
            # Include unclosed records but market_json will surface expired markets as CLOSED.
            query = query.where(Market.status == "OPEN", Market.cutoff > now())
            count = count.where(Market.status == "OPEN", Market.cutoff > now())
        elif status == "CLOSED":
            from sqlalchemy import or_
            clause = or_(Market.status == "CLOSED", (Market.status == "OPEN") & (Market.cutoff <= now()))
            query, count = query.where(clause), count.where(clause)
        else:
            query, count = query.where(Market.status == status), count.where(Market.status == status)
    if project:
        query, count = query.where(Market.jira_project_key == project.upper()), count.where(Market.jira_project_key == project.upper())
    items = db.execute(query.order_by(Market.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [market_json(m) for m in items], "total": db.scalar(count), "limit": limit, "offset": offset}


@app.post("/api/markets", status_code=201)
def new_market(body: MarketCreate, user: User = Depends(admin), db: Session = Depends(get_db)):
    try:
        market = create_market(db, body.jira_issue_key, body.cutoff, body.liquidity, user, provider())
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Market already exists")
    return market_json(market)


@app.get("/api/markets/{market_id}")
def get_market(market_id: str, user: User = Depends(member), db: Session = Depends(get_db)):
    return market_json(find_market(db, market_id))


@app.post("/api/markets/{market_id}/quote")
def get_quote(market_id: str, body: QuoteRequest, user: User = Depends(protected), db: Session = Depends(get_db)):
    return quote(db, market_id, body.side, body.outcome, body.shares, user)


@app.post("/api/markets/{market_id}/orders", status_code=201)
def new_order(market_id: str, body: OrderRequest,
              idempotency_key: str = Header(..., alias="Idempotency-Key"),
              user: User = Depends(protected), db: Session = Depends(get_db)):
    if body.side == "BUY" and (body.max_cost is None or body.min_proceeds is not None):
        raise HTTPException(422, "BUY requires max_cost and no min_proceeds")
    if body.side == "SELL" and (body.min_proceeds is None or body.max_cost is not None):
        raise HTTPException(422, "SELL requires min_proceeds and no max_cost")
    try:
        return execute_order(db, market_id, user, body.side, body.outcome, body.shares,
                             body.max_cost if body.side == "BUY" else body.min_proceeds,
                             idempotency_key)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent order conflict; retry with same idempotency key")


@app.get("/api/markets/{market_id}/trades")
def trades(market_id: str, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
           user: User = Depends(member), db: Session = Depends(get_db)):
    find_market(db, market_id)
    query = select(Order).where(Order.market_id == market_id).order_by(Order.created_at.desc())
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return {"items": [{"side": o.side, "outcome": o.outcome, "shares": display(o.shares),
                       "amount": display(o.amount), "created_at": aware(o.created_at).isoformat()} for o in rows]}


@app.get("/api/markets/{market_id}/history")
def history(market_id: str, user: User = Depends(member), db: Session = Depends(get_db)):
    find_market(db, market_id)
    records = db.execute(select(PriceHistory).where(PriceHistory.market_id == market_id)
                         .order_by(PriceHistory.created_at.asc())).scalars().all()
    return {"items": [{"at": aware(h.created_at).isoformat(), "yes_probability": h.yes_price} for h in records]}


@app.get("/api/me/wallet")
def wallet(user: User = Depends(member), db: Session = Depends(get_db)):
    return {"balance": display(user_account(db, user.id).balance), "currency": "PLAY_CREDITS"}


@app.get("/api/me/portfolio")
def portfolio(user: User = Depends(member), db: Session = Depends(get_db)):
    holdings = db.execute(select(Position, Market).join(Market, Position.market_id == Market.id)
                          .where(Position.user_id == user.id, Position.shares > 0)).all()
    items = []
    value = 0.0
    for p, m in holdings:
        price = prices(m)[0 if p.outcome == "YES" else 1]
        # Finalized payouts were already credited to wallet, so exclude from active mark-to-market.
        current = p.shares / 1_000_000 * price if m.status in ("OPEN", "CLOSED") else 0.0
        value += current
        items.append({"market_id": m.id, "question": market_json(m)["question"], "outcome": p.outcome,
                      "shares": display(p.shares), "status": market_json(m)["status"],
                      "mark_to_market": f"{current:.6f}", "winner": m.winner})
    return {"balance": display(user_account(db, user.id).balance),
            "active_position_value": f"{value:.6f}", "holdings": items}


@app.get("/api/me/orders")
def my_orders(user: User = Depends(member), db: Session = Depends(get_db),
              limit: int = Query(50, ge=1, le=100)):
    records = db.execute(select(Order).where(Order.user_id == user.id)
                         .order_by(Order.created_at.desc()).limit(limit)).scalars().all()
    return {"items": [{"id": o.id, "market_id": o.market_id, "side": o.side,
                        "outcome": o.outcome, "shares": display(o.shares),
                        "amount": display(o.amount), "at": aware(o.created_at).isoformat()} for o in records]}


@app.post("/api/admin/markets/{market_id}/sync")
def admin_sync(market_id: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    return sync_market(db, market_id, provider(), user)


@app.post("/api/admin/markets/{market_id}/resolve")
def admin_resolve(market_id: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    return settle(db, market_id, provider(), user)


@app.post("/api/admin/markets/{market_id}/void")
def admin_void(market_id: str, body: VoidRequest, user: User = Depends(admin), db: Session = Depends(get_db)):
    return void_market(db, market_id, user, body.reason)


@app.get("/api/admin/audit")
def audit(user: User = Depends(member), db: Session = Depends(get_db)):
    if user.role != "ADMIN":
        raise HTTPException(403, "Admin role required")
    logs = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).scalars().all()
    return {"items": [{"action": l.action, "market_id": l.market_id,
                        "reason": l.reason, "at": aware(l.created_at).isoformat()} for l in logs]}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}

# Read-only Jira issue status routes
from app.jira_routes import router as jira_router
app.include_router(jira_router)
