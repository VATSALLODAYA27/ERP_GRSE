"""The control tower: delivery risk, follow-ups to vendors, reorder suggestions, anomalies and vendor scorecards.

The numbers are worked out by plain rules in core/intel.py. The only AI step is the wording of a follow-up e-mail,
and a follow-up is never sent: a reviewer approves or dismisses the draft, and that is recorded.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..auth import audit, current_user, reviewer
from ..core import intel, procure
from ..core.ledger import plus_days, qty_text, today
from ..db import get_session
from ..models import AiFlag, AiFollowup, ProcOrder, User, Vendor
from ..schemas import FollowupDraftIn, NoteIn, ReorderRequisitionIn
from .scm import requisition_detail

router = APIRouter(prefix="/api/intel", tags=["intel"], dependencies=[Depends(current_user)])


@router.get("/overview")
def overview(session: Session = Depends(get_session)):
    return intel.overview(session)


@router.get("/delivery-risk")
def delivery_risk(session: Session = Depends(get_session)):
    return intel.delivery_risk(session)


@router.get("/vendor-scorecards")
def vendor_scorecards(session: Session = Depends(get_session)):
    return intel.vendor_rows(session)


# --- Follow-ups ---


def followup_rows(session: Session, rows) -> list:
    vendor_names = dict(session.execute(select(Vendor.vendor_id, Vendor.name)).all())
    return [{"id": f.id, "po_no": f.po_no, "vendor_id": f.vendor_id, "vendor_name": vendor_names.get(f.vendor_id, f.vendor_id),
             "created_at": f.created_at, "risk_level": f.risk_level, "subject": f.subject, "body": f.body, "status": f.status,
             "decided_by": f.decided_by, "written_by": f.written_by} for f in rows]


@router.post("/followups/draft", status_code=201)
def draft_followups(body: FollowupDraftIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Draft follow-ups for one order, or for every order with a HIGH-risk line. Orders that already have a draft waiting are skipped."""
    risks = intel.delivery_risk(session)
    if body.all_high:
        wanted = list(dict.fromkeys(r["po_no"] for r in risks if r["level"] == "HIGH"))
    elif body.po_no:
        if session.get(ProcOrder, body.po_no) is None:
            raise HTTPException(404, f"Purchase order {body.po_no} not found.")
        if not any(r["po_no"] == body.po_no for r in risks):
            raise HTTPException(409, f"{body.po_no} has nothing open with the vendor to follow up.")
        wanted = [body.po_no]
    else:
        raise HTTPException(422, "Give a purchase order number or all_high: true.")
    created, skipped = intel.draft_followups(session, wanted, user.username, url=config.EXPLAINER_URL, model=config.EXPLAINER_MODEL,
                                             key=config.EXPLAINER_KEY, fallback=config.FALLBACK_MODEL, risks=risks)
    for f in created:
        audit(session, user.username, user.role, "followup.drafted", f"purchase order {f.po_no}",
              f"follow-up {f.id} ({f.risk_level} risk), written by {'the AI model' if f.written_by == 'model' else 'the template'}")
    session.commit()
    return {"created": followup_rows(session, created), "skipped": skipped}


@router.get("/followups")
def followups(status: str | None = None, session: Session = Depends(get_session)):
    query = select(AiFollowup).order_by(AiFollowup.id.desc())
    if status:
        query = query.where(AiFollowup.status == status)
    return followup_rows(session, session.scalars(query))


def decide_followup(session: Session, followup_id: int, user: User, status: str) -> dict:
    f = session.get(AiFollowup, followup_id)
    if f is None:
        raise HTTPException(404, "Follow-up not found.")
    if f.status != "DRAFT":
        raise HTTPException(409, f"This follow-up is already {f.status}.")
    f.status, f.decided_by = status, user.username
    # shortcut: no e-mail integration; "approved to send" is recorded here and in the audit log only
    audit(session, user.username, user.role, "followup.approved" if status == "APPROVED" else "followup.dismissed",
          f"purchase order {f.po_no}", f"follow-up {f.id}: {f.subject}")
    session.commit()
    return followup_rows(session, [f])[0]


@router.post("/followups/{followup_id}/approve")
def approve_followup(followup_id: int, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    return decide_followup(session, followup_id, user, "APPROVED")


@router.post("/followups/{followup_id}/dismiss")
def dismiss_followup(followup_id: int, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    return decide_followup(session, followup_id, user, "DISMISSED")


# --- Reorder ---


@router.get("/reorder")
def reorder(session: Session = Depends(get_session)):
    return intel.reorder_suggestions(session)


@router.post("/reorder/requisition", status_code=201)
def reorder_requisition(body: ReorderRequisitionIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """One requisition for the chosen suggestions, at the suggested quantities, needed by today plus each item's lead time."""
    suggestions = {r["item_code"]: r for r in intel.reorder_suggestions(session)}
    missing = [code for code in body.item_codes if code not in suggestions]
    if missing:
        raise HTTPException(422, f"No reorder suggestion now for: {', '.join(missing)}.")
    chosen = [suggestions[code] for code in dict.fromkeys(body.item_codes)]
    pr = procure.create_requisition(session, [{"item_code": r["item_code"], "qty": r["suggested_qty"], "need_by": plus_days(today(), r["lead_time_days"])}
                                              for r in chosen], user.username, note="Raised from the reorder suggestions.", source="AI_REORDER")
    audit(session, user.username, user.role, "requisition.created", f"requisition {pr.pr_no}",
          "from reorder suggestions: " + ", ".join(f"{r['item_code']} x {qty_text(r['suggested_qty'])}" for r in chosen))
    session.commit()
    return requisition_detail(session, pr)


# --- Anomalies ---


@router.post("/anomalies/scan")
def scan(user: User = Depends(current_user), session: Session = Depends(get_session)):
    added = intel.scan(session)
    audit(session, user.username, user.role, "anomaly.scan", "anomalies", f"{len(added)} new")
    session.commit()
    return {"added": len(added)}


@router.get("/anomalies")
def anomalies(status: str | None = None, session: Session = Depends(get_session)):
    query = select(AiFlag)
    if status:
        query = query.where(AiFlag.status == status)
    rows = session.scalars(query).all()
    rows = sorted(rows, key=lambda f: (f.status != "OPEN", intel.SEVERITY_ORDER.get(f.severity, 3), -f.id))
    return [intel.flag_row(f) for f in rows]


@router.post("/anomalies/{flag_id}/resolve")
def resolve(flag_id: int, body: NoteIn, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    f = session.get(AiFlag, flag_id)
    if f is None:
        raise HTTPException(404, "Anomaly not found.")
    if f.status != "OPEN":
        raise HTTPException(409, "This anomaly is already resolved.")
    note = body.note.strip()
    if not note:
        raise HTTPException(422, "Say how it was resolved.")
    f.status, f.resolved_by, f.resolution_note = "RESOLVED", user.username, note
    audit(session, user.username, user.role, "anomaly.resolved", f"{f.ref_type.lower()} {f.ref_no}", f"{f.kind}: {note}")
    session.commit()
    return intel.flag_row(f)
