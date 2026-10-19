from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import config
from ..auth import admin, audit, current_user, reviewer
from ..core.helper import ask
from ..db import get_session
from ..models import AuditEntry, Check, RuleApproval, User, now
from ..rulebook import rulebook
from ..schemas import AuditOut, HelperIn, RuleApprovalIn
from .erp import class_approvals, register, release_gate

router = APIRouter(prefix="/api", tags=["reference"], dependencies=[Depends(current_user)])


@router.get("/rules")
def rules(session: Session = Depends(get_session)):
    return rulebook(session)


def find_rule(session: Session, rule_id: str) -> dict:
    rule = next((r for r in rulebook(session) if r["id"] == rule_id), None)
    if rule is None:
        raise HTTPException(404, "Rule not found.")
    return rule


@router.post("/rules/{rule_id}/approval", status_code=201)
def approve_rule(rule_id: str, body: RuleApprovalIn, user: User = Depends(admin), session: Session = Depends(get_session)):
    """Approve a rule exactly as it stands in the rule file. From the next check on, it runs."""
    rule = find_rule(session, rule_id)
    if rule["state"] == "approved":
        raise HTTPException(409, "This rule is already approved as it stands.")
    session.add(RuleApproval(rule_id=rule_id, content_hash=rule["content_hash"], approved_by=user.username, note=body.note.strip()))
    audit(session, user.username, user.role, "rule.approved", f"rule {rule_id}", f"{rule['clause']}: {rule['name']}. {body.note.strip()}")
    session.commit()
    return find_rule(session, rule_id)


@router.post("/rules/{rule_id}/withdrawal", status_code=201)
def withdraw_rule(rule_id: str, user: User = Depends(admin), session: Session = Depends(get_session)):
    """Take a rule out of use. Checks already made keep their findings; new checks no longer run it."""
    rule = find_rule(session, rule_id)
    if rule["state"] == "draft":
        raise HTTPException(409, "This rule has no approval to withdraw.")
    approval = session.scalars(select(RuleApproval).where(RuleApproval.rule_id == rule_id).order_by(RuleApproval.id.desc())).first()
    approval.withdrawn_by, approval.withdrawn_at = user.username, now()
    audit(session, user.username, user.role, "rule.withdrawn", f"rule {rule_id}", f"{rule['clause']}: {rule['name']}")
    session.commit()
    return find_rule(session, rule_id)


@router.get("/settings")
def settings():
    """What the screens need to know about optional features. Never includes a secret."""
    return {"explainer": {"enabled": bool(config.EXPLAINER_KEY), "model": config.EXPLAINER_MODEL}}


def site_data(session: Session) -> str:
    """What the screens show right now, as text for the helper. Every role may see all of it on the pages."""
    checks = session.scalars(select(Check).order_by(Check.id.desc()).options(selectinload(Check.decision), selectinload(Check.findings))).all()
    gate = release_gate(session)
    verdicts, statuses = Counter(c.verdict for c in checks), Counter(row["status"] for row in gate)
    lines = [
        f"TOTALS: {len(checks)} checks, {sum(c.decision is None for c in checks)} awaiting decision. "
        f"Verdicts: {verdicts['PASS']} PASS, {verdicts['NEEDS_REVIEW']} NEEDS REVIEW, {verdicts['BLOCKED']} BLOCKED. "
        f"Work orders: {statuses['CLEAR']} Clear, {statuses['WARN']} Warn, {statuses['BLOCKED']} Blocked.",
        "CHECKS (newest first)",
    ]
    for c in checks[:25]:  # shortcut: only the newest 25 checks are described; older ones are in the totals only
        d = c.decision
        decided = f"{d.decision} by {d.decided_by}{' (override)' if d.is_override else ''}" if d else "awaiting decision"
        findings = "; ".join(f"{f.severity}: {f.rule_name}" for f in c.findings) or "none"
        lines.append(f"- check {c.id}: {c.drawing_no} rev {c.revision}, verdict {c.verdict}, {decided}, "
                     f"submitted by {c.submitted_by} on {c.created_at:%d %b %Y}. Findings: {findings}")
    lines.append("DRAWING REGISTER")
    lines += [f"- {d['drawing_no']}: {d['title']}, current rev {d['current_rev']}, status {d['status']}, "
              f"class approval {d['class_approval'] or 'not submitted'}" for d in register(session)]
    lines.append("RELEASE GATE (work orders)")
    lines += [f"- {row['order_no']}: {row['drawing_no']} rev {row['rev']}, {row['status']}. {' '.join(row['reasons'])}" for row in gate]
    lines.append("CLASS APPROVALS")
    lines += [f"- {a['drawing_no']} rev {a['rev']}: {a['state']}, submitted to {a['submitted_to']} on {a['submitted_on']}"
              + (f", waiting {a['days_waiting']} days" if a["days_waiting"] is not None else "") for a in class_approvals(session)]
    lines.append("RULES")
    lines += [f"- {r['id']} {r['name']}: {r['severity']}, {r['state']}" for r in rulebook(session)]
    return "\n".join(lines)[:12000]


@router.post("/helper")
def helper(body: HelperIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Ask Navik about the tool. Nothing is stored: the conversation lives in the browser tab."""
    # shortcut: no per-user rate limit, only signed-in users can call it; add one before exposing the tool beyond the office network
    # Without a key, or with the AI service down, Navik still answers from the matching guide and data lines.
    return ask(body.question.strip(), [turn.model_dump() for turn in body.history], user.role, body.page,
               site_data(session) if config.HELPER_SEES_DATA else "",
               url=config.EXPLAINER_URL, model=config.EXPLAINER_MODEL, key=config.EXPLAINER_KEY, fallback=config.FALLBACK_MODEL)


@router.get("/audit", response_model=list[AuditOut], dependencies=[Depends(reviewer)])
def audit_log(session: Session = Depends(get_session)):
    # shortcut: newest 500 entries, filtered in the browser; add paging when the log outgrows that
    return session.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(500)).all()
