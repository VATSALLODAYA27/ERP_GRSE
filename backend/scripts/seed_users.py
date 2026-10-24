"""Create or reset the default users from setup/logins.json. The passwords in that file are for local setup only.

Run from backend/:  python -m scripts.seed_users
"""
import json

from app import config
from app.auth import hash_password
from app.db import SessionLocal, migrate
from app.models import User


def seed(session, path=config.SEED_USERS_FILE) -> list:
    users = json.loads(path.read_text(encoding="utf-8"))
    for u in users:
        session.merge(User(username=u["username"], name=u["name"], role=u["role"], password_hash=hash_password(u["password"]), status="active"))
    session.commit()
    return users


if __name__ == "__main__":
    migrate()
    with SessionLocal() as session:
        for u in seed(session):
            print(f"{u['username']} ({u['role']})")
