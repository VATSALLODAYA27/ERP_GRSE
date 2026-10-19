"""The rules as they stand right now: what the rule file says, joined with who approved each rule.

A rule is defined in the rule file and approved in the tool. The approval is tied to the rule's exact content,
so changing a rule's parameters, clause or severity puts it back to "changed" and it stops running until it is approved again.
"""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .core.rules import load_rules
from .models import RuleApproval


def content_hash(rule: dict) -> str:
    """A fingerprint of everything that defines the rule. "demo_state" is only a hint for setting up the demo."""
    definition = {k: v for k, v in rule.items() if k != "demo_state"}
    return hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()


def rulebook(session: Session) -> list:
    """Every rule with its state: "approved" (runs), "draft" (never approved) or "changed" (edited since it was approved)."""
    latest = {}
    for approval in session.scalars(select(RuleApproval).order_by(RuleApproval.id)):
        latest[approval.rule_id] = approval
    rules = []
    for rule in load_rules(config.RULES_FILE):
        approval, fingerprint = latest.get(rule["id"]), content_hash(rule)
        in_force = approval is not None and approval.withdrawn_at is None
        state = "approved" if in_force and approval.content_hash == fingerprint else "changed" if in_force else "draft"
        rules.append({k: v for k, v in rule.items() if k != "demo_state"} | {
            "state": state,
            "content_hash": fingerprint,
            "approved_by": approval.approved_by if in_force else None,
            "approved_at": approval.approved_at.isoformat() if in_force else None,
            "approval_note": approval.note if in_force else None,
        })
    return rules
