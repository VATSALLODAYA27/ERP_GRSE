import json
from uuid import uuid4

import pymupdf
from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import config
from ..auth import audit, current_user, reviewer
from ..core.bom import compare_bom
from ..core.diff import compare, overlay_png
from ..core.explain import ExplainerError, explain
from ..core.extract import FIELDS, UnreadableDrawing, extract
from ..core.impact import impact
from ..core.rules import run_checks, verdict
from ..db import get_session
from ..models import BomItem, ChangeNote, Check, Comment, Decision, Drawing, Finding, PurchaseOrder, ShipParticulars, User, WorkOrder, as_dict, now
from ..rulebook import rulebook
from ..schemas import CheckOut, CheckSummary, CommentIn, DecisionIn

router = APIRouter(prefix="/api/checks", tags=["checks"], dependencies=[Depends(current_user)])

# Decisions that simply follow the tool's verdict; anything else needs a written reason.
AGREES = {("PASS", "APPROVED"), ("BLOCKED", "REJECTED")}
OVERRIDES = {("BLOCKED", "APPROVED"), ("PASS", "REJECTED")}


def get_or_404(session: Session, check_id: int) -> Check:
    check = session.get(Check, check_id)
    if check is None:
        raise HTTPException(404, "Check not found.")
    return check


async def read_drawing(upload: UploadFile, what: str) -> tuple[bytes, dict]:
    data = await upload.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{what}: the file is larger than 25 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, f"{what}: the upload must be a PDF file.")
    try:
        return data, extract(data)
    except UnreadableDrawing as e:
        raise HTTPException(422, f"{what}: {e}")


def store(data: bytes) -> str:
    # Stored under a generated name: the uploaded file name is shown to users but never used as a path.
    name = f"{uuid4().hex}.pdf"
    (config.UPLOAD_DIR / name).write_bytes(data)
    return name


def stored(name: str) -> bytes:
    return (config.UPLOAD_DIR / name).read_bytes()


def png(image: bytes) -> Response:
    return Response(image, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def render(pdf: bytes) -> bytes:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc[0].get_pixmap(dpi=110).tobytes("png")


@router.post("/read")
async def read_title_block(file: UploadFile, user: User = Depends(current_user)):
    """What the tool reads from a drawing, before any check is run. Nothing is stored."""
    _, drawing = await read_drawing(file, "Drawing")
    return {
        "source": drawing["source"],
        "fields": {name: {"value": f["value"], "confidence": f.get("confidence")} for name, f in drawing["fields"].items()},
        "parts": len(drawing["parts"]),
    }


def apply_confirmation(drawing: dict, confirmed: str | None, user: User) -> list:
    """Replace what OCR read with what the person confirmed. Returns a description of each correction."""
    if drawing["source"] != "scan":
        return []
    if confirmed is None:
        raise HTTPException(422, "This is a scanned drawing: the title block values read by OCR must be confirmed before it is checked.")
    try:
        values = json.loads(confirmed)
        assert isinstance(values, dict) and set(values) == set(FIELDS)
        assert all(isinstance(v, str) and len(v) <= 200 for v in values.values())
    except (ValueError, AssertionError):
        raise HTTPException(422, "The confirmed title block values are not valid.")
    corrections = []
    for name, value in values.items():
        field, value = drawing["fields"][name], " ".join(value.split())
        if value != field["value"]:
            corrections.append(f"{name} '{field['value']}' to '{value}'")
            field["read_as"], field["value"] = field["value"], value
    drawing["confirmed_by"] = user.username
    return corrections


@router.post("", response_model=CheckOut, status_code=201)
async def create_check(
    file: UploadFile,
    previous: UploadFile | None = None,
    confirmed: str | None = Form(None),
    user: User = Depends(current_user),  # every role may upload a drawing for checking
    session: Session = Depends(get_session),
):
    data, drawing = await read_drawing(file, "Drawing")
    corrections = apply_confirmation(drawing, confirmed, user)
    drawing_no, revision = drawing["fields"]["drawing_no"]["value"], drawing["fields"]["revision"]["value"]

    row = session.get(Drawing, drawing_no)
    register = {"title": row.title, "current_rev": row.current_rev, "status": row.status} if row else None
    bom = [as_dict(item) for item in session.scalars(select(BomItem).where(BomItem.drawing_no == drawing_no, BomItem.rev == revision))]
    ship = session.get(ShipParticulars, drawing["fields"]["hull_no"]["value"])
    findings = run_checks(drawing, {"register": register, "bom": bom, "ship": ship and as_dict(ship)}, rulebook(session))

    # The revision to compare with: the one uploaded alongside, else the latest earlier revision already checked.
    earlier, previous_stored_as = None, None
    if previous is not None:
        earlier_data, earlier = await read_drawing(previous, "Previous revision")
        if earlier["fields"]["drawing_no"]["value"] != drawing_no:
            raise HTTPException(422, f"Previous revision: this is a different drawing ({earlier['fields']['drawing_no']['value'] or 'unreadable number'}).")
        if earlier["fields"]["revision"]["value"] == revision:
            raise HTTPException(422, f"Previous revision: both files are revision {revision}.")
        previous_stored_as = store(earlier_data)
    elif drawing_no:
        # shortcut: revisions compared as text, as in the register check
        prior = session.scalars(
            select(Check).where(Check.drawing_no == drawing_no, Check.revision < revision).order_by(Check.revision.desc(), Check.id.desc())
        ).first()
        if prior:
            earlier, previous_stored_as = extract(stored(prior.stored_as)), prior.stored_as
            earlier["fields"] = prior.extracted["fields"]  # as confirmed at the time; re-reading a scan would bring back OCR mistakes

    revision_diff, affected = None, None
    if earlier:
        note = session.scalars(select(ChangeNote).where(ChangeNote.drawing_no == drawing_no, ChangeNote.to_rev == revision)).first()
        revision_diff = {
            "from_revision": earlier["fields"]["revision"]["value"],
            "page_size": earlier["page_size"],
            "changes": compare(earlier, drawing),
            # What the ERP says about this revision change, kept beside what the tool found.
            "change_note": note and {
                "ecn_no": note.ecn_no, "from_rev": note.from_rev, "to_rev": note.to_rev,
                "changed_on": note.changed_on, "description": note.description, "reason": note.reason,
            },
        }

        affected = impact(
            revision_diff["changes"], revision_diff["from_revision"],
            [as_dict(order) for order in session.scalars(select(WorkOrder).where(WorkOrder.drawing_no == drawing_no))],
            [as_dict(po) for po in session.scalars(select(PurchaseOrder))],
        )

    del drawing["text"], drawing["lines"]
    check = Check(
        drawing_no=drawing_no,
        revision=revision,
        filename=file.filename or "",
        stored_as=store(data),
        verdict=verdict(findings),
        extracted=drawing,
        register_row=register,
        previous_stored_as=previous_stored_as,
        revision_diff=revision_diff,
        bom_check=compare_bom(drawing["parts"], bom) if bom else None,
        impact=affected,
        submitted_by=user.username,
        findings=[Finding(**f) for f in findings],
    )
    session.add(check)
    session.flush()
    scanned = f"; scanned drawing, title block confirmed with {len(corrections)} corrections" + (f" ({'; '.join(corrections)})" if corrections else "") if drawing["source"] == "scan" else ""
    compared = f", compared with rev {revision_diff['from_revision']}: {len(revision_diff['changes'])} changes" if revision_diff else ""
    audit(session, user.username, user.role, "check.created", f"check {check.id}",
          f"{drawing_no} rev {revision}: {check.verdict}, {len(findings)} findings{compared}{scanned}")
    session.commit()
    return check


@router.get("", response_model=list[CheckSummary])
def list_checks(session: Session = Depends(get_session)):
    return session.scalars(select(Check).order_by(Check.id.desc()).options(selectinload(Check.decision))).all()


@router.get("/{check_id}", response_model=CheckOut)
def get_check(check_id: int, session: Session = Depends(get_session)):
    return get_or_404(session, check_id)


@router.get("/{check_id}/sheet.png")
def sheet_image(check_id: int, session: Session = Depends(get_session)):
    return png(render(stored(get_or_404(session, check_id).stored_as)))


def previous_or_404(session: Session, check_id: int) -> tuple[bytes, Check]:
    check = get_or_404(session, check_id)
    if check.previous_stored_as is None:
        raise HTTPException(404, "This check has no previous revision to compare with.")
    return stored(check.previous_stored_as), check


@router.get("/{check_id}/previous.png")
def previous_sheet_image(check_id: int, session: Session = Depends(get_session)):
    return png(render(previous_or_404(session, check_id)[0]))


@router.get("/{check_id}/diff.png")
def diff_image(check_id: int, session: Session = Depends(get_session)):
    previous, check = previous_or_404(session, check_id)
    return png(overlay_png(previous, stored(check.stored_as)))


@router.post("/{check_id}/decision", response_model=CheckOut, status_code=201)
def decide(check_id: int, body: DecisionIn, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    """A reviewer or the admin approves or rejects the release. Once only."""
    check = get_or_404(session, check_id)
    if check.decision is not None:
        raise HTTPException(409, "This check has already been decided.")
    own = check.submitted_by == user.username
    # Two people: whoever uploaded a drawing does not also release it. The admin has full access, and the audit log marks it.
    if own and user.role != "admin":
        raise HTTPException(403, "You submitted this check, so another reviewer or the admin must decide it.")
    reason = body.reason.strip()
    outcome = (check.verdict, body.decision)
    if outcome not in AGREES and not reason:
        raise HTTPException(422, "A reason is required when the decision does not simply follow the verdict.")

    check.decision = Decision(decision=body.decision, is_override=outcome in OVERRIDES, reason=reason, decided_by=user.username)
    audit(session, user.username, user.role, "decision.override" if outcome in OVERRIDES else "decision.recorded",
          f"check {check.id}", f"{check.drawing_no} rev {check.revision}: verdict {check.verdict}, decision {body.decision}. {reason}"
          + (" (decided by the admin who submitted it)" if own else ""))
    try:
        session.commit()
    except IntegrityError:  # someone else's decision was saved between the check above and this one
        session.rollback()
        raise HTTPException(409, "This check has already been decided.")
    return check


@router.post("/{check_id}/comments", response_model=CheckOut, status_code=201)
def add_comment(check_id: int, body: CommentIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    check = get_or_404(session, check_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "A comment cannot be empty.")
    check.comments.append(Comment(username=user.username, text=text))
    audit(session, user.username, user.role, "comment.added", f"check {check.id}", text[:200])
    session.commit()
    return check


@router.post("/{check_id}/explanation", response_model=CheckOut, status_code=201)
def explain_changes(check_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Ask the hosted model for a plain-language summary of this check's revision changes. Made once and kept."""
    check = get_or_404(session, check_id)
    if check.explanation is not None:
        return check
    if not check.revision_diff or not check.revision_diff["changes"]:
        raise HTTPException(409, "This check has no revision changes to explain.")
    if not config.EXPLAINER_KEY:
        raise HTTPException(503, "The explainer is switched off: no API key is set on the server.")
    try:
        result = explain(check.revision_diff["changes"], check.revision_diff["from_revision"], check.revision,
                         url=config.EXPLAINER_URL, model=config.EXPLAINER_MODEL, key=config.EXPLAINER_KEY)
    except ExplainerError as e:
        raise HTTPException(502, str(e))
    check.explanation = result | {"requested_by": user.username, "at": now().isoformat()}
    audit(session, user.username, user.role, "explanation.generated", f"check {check.id}", f"model {result['model']}")
    session.commit()
    return check
