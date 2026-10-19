"""Read-only views that join the ERP extract with the tool's own checks: register, release gate, class approvals."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import admin, audit, current_user, reviewer
from ..core.gate import gate
from ..db import get_session
from ..models import BomItem, ChangeNote, Check, ClassApproval, Drawing, DrawingRevision, User, WorkOrder, as_dict
from ..schemas import ClassApprovalIn, DrawingEdit, DrawingNew

router = APIRouter(prefix="/api", tags=["erp"], dependencies=[Depends(current_user)])


def approvals_by_revision(session: Session) -> dict:
    return {(a.drawing_no, a.rev): as_dict(a) for a in session.scalars(select(ClassApproval))}


def gate_rows(session: Session, orders) -> list:
    drawings = {d.drawing_no: as_dict(d) for d in session.scalars(select(Drawing))}
    approvals = approvals_by_revision(session)
    # shortcut: reads every check to find the latest per drawing revision; query per work order when there are thousands
    latest = {}
    for check in session.scalars(select(Check).order_by(Check.id).options(selectinload(Check.decision))):
        latest[(check.drawing_no, check.revision)] = {
            "id": check.id, "verdict": check.verdict, "decision": check.decision and as_dict(check.decision),
        }
    rows = []
    for order in orders:
        key = (order.drawing_no, order.rev)
        drawing, check = drawings.get(order.drawing_no), latest.get(key)
        rows.append({
            **as_dict(order),
            "current_rev": drawing and drawing["current_rev"],
            "check_id": check and check["id"],
            **gate(as_dict(order), drawing, check, approvals.get(key)),
        })
    return rows


@router.get("/gate")
def release_gate(session: Session = Depends(get_session)):
    return gate_rows(session, session.scalars(select(WorkOrder).order_by(WorkOrder.order_no)))


@router.get("/gate/{order_no}")
def release_gate_for(order_no: str, session: Session = Depends(get_session)):
    """The question the ERP would ask before releasing one work order."""
    order = session.get(WorkOrder, order_no)
    if order is None:
        raise HTTPException(404, "Work order not found.")
    return gate_rows(session, [order])[0]


def with_waiting_days(approval: dict) -> dict:
    waiting = None if approval["state"] == "APPROVED" else (date.today() - date.fromisoformat(approval["submitted_on"])).days
    return {**approval, "days_waiting": waiting}


@router.get("/class-approvals")
def class_approvals(session: Session = Depends(get_session)):
    titles = {d.drawing_no: d.title for d in session.scalars(select(Drawing))}
    rows = [with_waiting_days(as_dict(a)) | {"title": titles.get(a.drawing_no, "")} for a in session.scalars(select(ClassApproval))]
    # Longest wait first; approved ones last.
    return sorted(rows, key=lambda r: -1 if r["days_waiting"] is None else r["days_waiting"], reverse=True)


@router.post("/class-approvals", status_code=201)
def record_class_approval(body: ClassApprovalIn, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    """Record a submission to class or the customer, or its new state. One record per drawing revision."""
    if session.get(Drawing, body.drawing_no) is None:
        raise HTTPException(422, "That drawing is not in the register.")
    if body.submitted_on > date.today():
        raise HTTPException(422, "The submission date cannot be in the future.")
    approval = session.scalars(
        select(ClassApproval).where(ClassApproval.drawing_no == body.drawing_no, ClassApproval.rev == body.rev).order_by(ClassApproval.id.desc())
    ).first()
    before = approval and f"{approval.state}, submitted to {approval.submitted_to} on {approval.submitted_on}"
    if approval is None:
        approval = ClassApproval(drawing_no=body.drawing_no, rev=body.rev)
        session.add(approval)
    approval.submitted_to, approval.submitted_on, approval.state = body.submitted_to.strip(), body.submitted_on.isoformat(), body.state
    approval.source = "manual"
    after = f"{approval.state}, submitted to {approval.submitted_to} on {approval.submitted_on}"
    audit(session, user.username, user.role, "class_approval.updated" if before else "class_approval.recorded",
          f"drawing {body.drawing_no} rev {body.rev}", f"{before}  ->  {after}" if before else after)
    session.commit()
    return with_waiting_days(as_dict(approval))


@router.get("/register")
def register(session: Session = Depends(get_session)):
    approvals = approvals_by_revision(session)
    return [
        as_dict(d) | {"class_approval": approvals.get((d.drawing_no, d.current_rev), {}).get("state")}
        for d in session.scalars(select(Drawing).order_by(Drawing.drawing_no))
    ]


@router.get("/register/{drawing_no}")
def drawing_detail(drawing_no: str, session: Session = Depends(get_session)):
    drawing = session.get(Drawing, drawing_no)
    if drawing is None:
        raise HTTPException(404, "Drawing not found in the register.")

    def rows(model, order_by):
        return [as_dict(row) for row in session.scalars(select(model).where(model.drawing_no == drawing_no).order_by(order_by))]

    return {
        "drawing": as_dict(drawing),
        "revisions": rows(DrawingRevision, DrawingRevision.issued_on.desc()),
        "change_notes": rows(ChangeNote, ChangeNote.changed_on.desc()),
        "bom": rows(BomItem, BomItem.id),
        "work_orders": gate_rows(session, session.scalars(select(WorkOrder).where(WorkOrder.drawing_no == drawing_no).order_by(WorkOrder.order_no))),
        "class_approvals": [with_waiting_days(a) for a in rows(ClassApproval, ClassApproval.submitted_on.desc())],
    }


# --- The register can be corrected by an admin. This changes the tool's copy only; nothing is written to the ERP. ---


@router.post("/register", status_code=201)
def add_drawing(body: DrawingNew, user: User = Depends(admin), session: Session = Depends(get_session)):
    if session.scalars(select(Drawing).where(func.lower(Drawing.drawing_no) == body.drawing_no.lower())).first():
        raise HTTPException(409, "A drawing with that number is already in the register.")
    drawing = Drawing(drawing_no=body.drawing_no, title=body.title.strip(), current_rev=body.current_rev, status=body.status, source="manual")
    session.add(drawing)
    session.add(DrawingRevision(drawing_no=drawing.drawing_no, rev=drawing.current_rev, status=drawing.status, issued_on=date.today().isoformat(), source="manual"))
    audit(session, user.username, user.role, "register.added", f"drawing {drawing.drawing_no}", f"rev {drawing.current_rev}, {drawing.status}: {drawing.title}")
    session.commit()
    return as_dict(drawing)


@router.put("/register/{drawing_no}")
def update_drawing(drawing_no: str, body: DrawingEdit, user: User = Depends(admin), session: Session = Depends(get_session)):
    drawing = session.get(Drawing, drawing_no)
    if drawing is None:
        raise HTTPException(404, "Drawing not found in the register.")
    before = f"rev {drawing.current_rev}, {drawing.status}: {drawing.title}"
    revisions = {r.rev: r for r in session.scalars(select(DrawingRevision).where(DrawingRevision.drawing_no == drawing_no))}

    if body.current_rev != drawing.current_rev:
        # A new current revision: the one it replaces becomes superseded in the history.
        if drawing.current_rev in revisions:
            revisions[drawing.current_rev].status, revisions[drawing.current_rev].source = "SUPERSEDED", "manual"
        if body.current_rev in revisions:
            revisions[body.current_rev].status, revisions[body.current_rev].source = body.status, "manual"
        else:
            session.add(DrawingRevision(drawing_no=drawing_no, rev=body.current_rev, status=body.status, issued_on=date.today().isoformat(), source="manual"))
    elif drawing.current_rev in revisions:
        revisions[drawing.current_rev].status, revisions[drawing.current_rev].source = body.status, "manual"

    drawing.title, drawing.current_rev, drawing.status, drawing.source = body.title.strip(), body.current_rev, body.status, "manual"
    after = f"rev {drawing.current_rev}, {drawing.status}: {drawing.title}"
    audit(session, user.username, user.role, "register.updated", f"drawing {drawing_no}", f"{before}  ->  {after}")
    session.commit()
    return as_dict(drawing)
