from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite drops the timezone on stored times; every time we store is UTC, so put it back on the way out."""

    impl = DateTime
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def as_dict(row) -> dict:
    """A table row as plain data, for the checking logic and for JSON."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


# --- Copied from the ERP/PLM extract and reloaded from it. Only the register (drawings and their revisions) can also be edited by an admin. ---
# shortcut: dates are kept as ISO text (YYYY-MM-DD), which sorts correctly;
# switch to Date columns when the real extract format is known.


class Drawing(Base):
    __tablename__ = "drawings"
    drawing_no: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    current_rev: Mapped[str]
    status: Mapped[str]
    # "erp": as loaded from the extract. "manual": added or edited by an admin in the tool; the next extract load leaves it alone.
    source: Mapped[str] = mapped_column(default="erp", server_default="erp")


class DrawingRevision(Base):
    __tablename__ = "drawing_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    drawing_no: Mapped[str] = mapped_column(ForeignKey("drawings.drawing_no"))
    rev: Mapped[str]
    status: Mapped[str]
    issued_on: Mapped[str]
    source: Mapped[str] = mapped_column(default="erp", server_default="erp")


class ChangeNote(Base):
    __tablename__ = "change_notes"
    ecn_no: Mapped[str] = mapped_column(primary_key=True)
    drawing_no: Mapped[str] = mapped_column(ForeignKey("drawings.drawing_no"))
    from_rev: Mapped[str]
    to_rev: Mapped[str]
    changed_on: Mapped[str]
    description: Mapped[str]
    reason: Mapped[str]


class BomItem(Base):
    __tablename__ = "bom_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    drawing_no: Mapped[str] = mapped_column(ForeignKey("drawings.drawing_no"))
    rev: Mapped[str]
    part_no: Mapped[str]
    description: Mapped[str]
    material: Mapped[str]
    thickness_mm: Mapped[float]
    qty: Mapped[int]


class WorkOrder(Base):
    __tablename__ = "work_orders"
    order_no: Mapped[str] = mapped_column(primary_key=True)
    drawing_no: Mapped[str] = mapped_column(ForeignKey("drawings.drawing_no"))
    rev: Mapped[str]
    state: Mapped[str]


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    po_no: Mapped[str] = mapped_column(primary_key=True)
    part_no: Mapped[str]
    qty: Mapped[int]
    state: Mapped[str]


class ClassApproval(Base):
    __tablename__ = "class_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    drawing_no: Mapped[str] = mapped_column(ForeignKey("drawings.drawing_no"))
    rev: Mapped[str]
    submitted_to: Mapped[str]
    submitted_on: Mapped[str]
    state: Mapped[str]
    # "erp": as loaded from the extract. "manual": recorded in the tool; the next extract load leaves it alone.
    source: Mapped[str] = mapped_column(default="erp", server_default="erp")


class ShipParticulars(Base):
    """What a calculated rule needs to know about the ship a drawing belongs to."""

    __tablename__ = "ship_particulars"
    hull_no: Mapped[str] = mapped_column(primary_key=True)
    description: Mapped[str]
    rule_length_m: Mapped[float]


# --- Written by the tool. ---


class User(Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    # "engineer" submits drawings; "reviewer" views, comments and makes the final call; "admin" can do everything
    role: Mapped[str]
    password_hash: Mapped[str]
    # "pending" until an admin approves a self-registered account; "disabled" accounts cannot sign in
    status: Mapped[str] = mapped_column(default="active", server_default="active")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    drawing_no: Mapped[str]
    revision: Mapped[str]
    filename: Mapped[str]
    stored_as: Mapped[str]
    verdict: Mapped[str]
    extracted: Mapped[dict] = mapped_column(JSON)
    # Register values as they were when the check ran, so the report stays true after a later extract.
    register_row: Mapped[dict | None] = mapped_column(JSON)
    # The earlier revision this drawing was compared with, and what changed. Both empty when there was none.
    previous_stored_as: Mapped[str | None]
    revision_diff: Mapped[dict | None] = mapped_column(JSON)
    # Snapshots taken when the check ran: the parts list against the ERP bill of materials, and who the revision change affects.
    bom_check: Mapped[list | None] = mapped_column(JSON)
    # An AI-written summary of the revision changes, made only when someone asks for it. Never used by the verdict.
    explanation: Mapped[dict | None] = mapped_column(JSON)
    impact: Mapped[dict | None] = mapped_column(JSON)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("users.username"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    findings: Mapped[list["Finding"]] = relationship(cascade="all, delete-orphan")
    decision: Mapped["Decision | None"] = relationship()
    comments: Mapped[list["Comment"]] = relationship(order_by="Comment.id")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"))
    # Rule details are copied in, not linked, so an old report still shows the clause it was judged against.
    rule_id: Mapped[str]
    rule_name: Mapped[str]
    severity: Mapped[str]
    clause: Mapped[str]
    standard: Mapped[str]
    evidence: Mapped[str]
    bbox: Mapped[list | None] = mapped_column(JSON)


class Decision(Base):
    """The reviewer's final call on a check. One per check, never changed afterwards."""

    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), unique=True)
    decision: Mapped[str]  # APPROVED or REJECTED for release
    is_override: Mapped[bool]  # the reviewer went against the tool's verdict
    reason: Mapped[str]
    decided_by: Mapped[str] = mapped_column(ForeignKey("users.username"))
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"))
    username: Mapped[str] = mapped_column(ForeignKey("users.username"))
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class RuleApproval(Base):
    """One approval of one rule, tied to the rule's exact content. The newest row for a rule is the one that counts."""

    __tablename__ = "rule_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str]
    content_hash: Mapped[str]
    approved_by: Mapped[str]
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    note: Mapped[str] = mapped_column(default="")
    withdrawn_by: Mapped[str | None]
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    username: Mapped[str]
    role: Mapped[str]
    action: Mapped[str]
    target: Mapped[str]
    detail: Mapped[str]
