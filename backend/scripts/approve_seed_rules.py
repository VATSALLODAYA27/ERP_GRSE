"""Give the starting rules their first approval, so the tool has rules to run.

Only rules that have never had an approval are touched, and only those marked "seed_state": "approved" in the rule file.
A rule that was approved and then edited is left as "changed": approving it again is a person's job, on the Rule Library screen.
Run from backend/:  python -m scripts.approve_seed_rules
"""
from sqlalchemy import select

from app import config
from app.core.rules import load_rules
from app.db import SessionLocal, migrate
from app.models import RuleApproval
from app.rulebook import content_hash

SEEDED_BY = "initial-setup"
NOTE = "Initial approval at setup. Not reviewed by a naval architect."


def approve(session) -> list:
    already = set(session.scalars(select(RuleApproval.rule_id)))
    approved = []
    for rule in load_rules(config.RULES_FILE):
        if rule["id"] not in already and rule.get("seed_state") == "approved":
            session.add(RuleApproval(rule_id=rule["id"], content_hash=content_hash(rule), approved_by=SEEDED_BY, note=NOTE))
            approved.append(rule["id"])
    session.commit()
    return approved


if __name__ == "__main__":
    migrate()
    with SessionLocal() as session:
        done = approve(session)
        print(f"approved at setup: {', '.join(done) if done else 'nothing new'}")
