"""Sign-in, sessions and the audit trail.

A session is a random token in an HttpOnly cookie; only its hash is stored. SameSite=Lax keeps the cookie
off cross-site POSTs, which is what protects the state-changing routes from forged requests.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_session
from .models import AuditEntry, AuthSession, User, now

COOKIE = "session"
SESSION_LIFETIME = timedelta(hours=8)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt = bytes.fromhex(stored.split("$")[0])
    return hmac.compare_digest(hash_password(password, salt), stored)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(token_hash=token_hash(token), username=user.username, expires_at=now() + SESSION_LIFETIME))
    return token


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE)
    row = session.get(AuthSession, token_hash(token)) if token else None
    if row is None or row.expires_at < now():
        raise HTTPException(401, "Not signed in.")
    user = session.get(User, row.username)
    if user.status != "active":
        raise HTTPException(401, "This account is not active.")
    return user


def require(*roles: str):
    """A dependency that lets through only the given roles. An admin is let through everywhere."""

    def allowed(user: User = Depends(current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(403, "Your role does not allow this.")
        return user

    return allowed


reviewer = require("reviewer")  # approve or reject a release and read the audit log, on top of what every signed-in user can do
admin = require()  # manage users, the register and the rules


def audit(session: Session, username: str, role: str, action: str, target: str = "", detail: str = "") -> None:
    session.add(AuditEntry(username=username, role=role, action=action, target=target, detail=detail))
