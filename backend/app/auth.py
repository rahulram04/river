"""Argon2 credentials, opaque persistent sessions, and CSRF/role checks."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import timedelta
from fastapi import Depends, Header, HTTPException, Request, Response
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import get_settings
from app.db import get_db
from app.db_models import User, SessionToken
from app.domain import aware, now

ph = PasswordHasher()
SESSION_COOKIE = "river_session"
_attempts: dict[str, list[float]] = {}
_attempt_lock = threading.Lock()


def rate_limit(key: str):
    """Small local safety net, not a substitute for a distributed rate limiter."""
    stamp = time.monotonic()
    with _attempt_lock:
        recent = [t for t in _attempts.get(key, []) if t > stamp - 60]
        if len(recent) >= 8:
            raise HTTPException(429, "Too many attempts. Try again later.")
        recent.append(stamp)
        _attempts[key] = recent
        if len(_attempts) > 10000:
            _attempts.clear()


def verify_password(password: str, stored: str) -> bool:
    try:
        return ph.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False


def session_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_session(db: Session, user: User, response: Response) -> SessionToken:
    raw = secrets.token_urlsafe(48)
    settings = get_settings()
    session = SessionToken(token_hash=session_hash(raw), user_id=user.id,
                           csrf_token=secrets.token_urlsafe(32),
                           expires_at=now() + timedelta(hours=settings.session_ttl_hours))
    db.add(session)
    response.set_cookie(SESSION_COOKIE, raw, httponly=True,
                        secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.session_ttl_hours * 3600, path="/")
    return session


def get_identity(request: Request, db: Session = Depends(get_db)) -> tuple[User, SessionToken]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(401, "Authentication required")
    session = db.get(SessionToken, session_hash(raw))
    if session is None or session.revoked_at is not None or aware(session.expires_at) <= now():
        raise HTTPException(401, "Session expired or invalid")
    user = db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(401, "Account disabled")
    return user, session


def protected(identity: tuple[User, SessionToken] = Depends(get_identity),
              x_csrf_token: str | None = Header(default=None)) -> User:
    user, session = identity
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, session.csrf_token):
        raise HTTPException(403, "CSRF token missing or invalid")
    return user


def member(identity: tuple[User, SessionToken] = Depends(get_identity)) -> User:
    return identity[0]


def admin(user: User = Depends(protected)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(403, "Admin role required")
    return user
