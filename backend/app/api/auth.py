from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..auth import COOKIE, SESSION_LIFETIME, admin, audit, current_user, hash_password, start_session, token_hash, verify_password
from ..db import get_session
from ..models import AuthSession, User
from ..schemas import LoginIn, RegisterIn, UserAdminOut, UserOut, UserStatusIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Checked when the username is unknown, so a wrong username takes as long as a wrong password.
DUMMY_HASH = hash_password("no such user")


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    # shortcut: no lockout after repeated failures (each one is in the audit log); add one before real users sign in
    user = session.get(User, body.username)
    if not verify_password(body.password, user.password_hash if user else DUMMY_HASH) or user is None:
        audit(session, body.username[:64], "", "login.failed")
        session.commit()
        raise HTTPException(401, "Wrong username or password.")
    if user.status != "active":
        # Said only after the password was right, so it tells a stranger nothing about which accounts exist.
        audit(session, user.username, user.role, "login.refused", detail=f"account is {user.status}")
        session.commit()
        raise HTTPException(403, "This account is awaiting approval by an admin." if user.status == "pending" else "This account has been disabled.")
    token = start_session(session, user)
    audit(session, user.username, user.role, "login")
    session.commit()
    response.set_cookie(COOKIE, token, max_age=int(SESSION_LIFETIME.total_seconds()), httponly=True, samesite="lax",
                        secure=config.COOKIE_SECURE)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user), session: Session = Depends(get_session)):
    session.delete(session.get(AuthSession, token_hash(request.cookies[COOKIE])))
    audit(session, user.username, user.role, "logout")
    session.commit()
    response.delete_cookie(COOKIE)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, session: Session = Depends(get_session)):
    """Anyone can ask for a reviewer or engineer account; it cannot sign in until an admin approves it."""
    taken = session.scalars(select(User).where(func.lower(User.username) == body.username.lower())).first()
    if taken:
        raise HTTPException(409, "That username is already taken.")
    user = User(username=body.username, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password), status="pending")
    session.add(user)
    audit(session, user.username, user.role, "user.registered", f"user {user.username}", "awaiting admin approval")
    session.commit()
    return user


users = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(admin)])


@users.get("", response_model=list[UserAdminOut])
def list_users(session: Session = Depends(get_session)):
    return session.scalars(select(User).order_by(User.status.desc(), User.username)).all()


@users.post("/{username}/status", response_model=UserAdminOut)
def set_status(username: str, body: UserStatusIn, me: User = Depends(admin), session: Session = Depends(get_session)):
    user = session.get(User, username)
    if user is None:
        raise HTTPException(404, "User not found.")
    if user.username == me.username:
        raise HTTPException(409, "You cannot disable your own account.")
    if body.status == "disabled":
        # Signed-in sessions of a disabled account stop working at once.
        for row in session.scalars(select(AuthSession).where(AuthSession.username == username)):
            session.delete(row)
    audit(session, me.username, me.role, "user.approved" if (user.status, body.status) == ("pending", "active") else f"user.{body.status}", f"user {username}")
    user.status = body.status
    session.commit()
    return user
