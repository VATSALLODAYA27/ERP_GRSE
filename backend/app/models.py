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


# --- SENTINEL ERP: procurement, inventory and finance. All written by the tool; every row in the demo is mock data. ---
# shortcut: money is float rupees rounded to paise at each posting; use Numeric columns before real money is booked.
# The extract table purchase_orders above stays as it is (the drawing gate's impact view reads it); the ERP's own orders are proc_orders.


class Vendor(Base):
    __tablename__ = "vendors"
    vendor_id: Mapped[str] = mapped_column(primary_key=True)  # "V-1001"
    name: Mapped[str]
    city: Mapped[str]
    category: Mapped[str]
    gstin: Mapped[str]
    msme: Mapped[bool]
    payment_terms_days: Mapped[int]
    lead_time_days: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)


class Item(Base):
    __tablename__ = "items"
    item_code: Mapped[str] = mapped_column(primary_key=True)
    description: Mapped[str]
    category: Mapped[str]  # "Steel plate", "Sections", "Pipes & fittings", "Valves", "Electrical", "Consumables", "Outfitting"
    uom: Mapped[str]
    grade: Mapped[str]
    std_price: Mapped[float]
    reorder_level: Mapped[float]
    reorder_qty: Mapped[float]
    lead_time_days: Mapped[int]
    preferred_vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.vendor_id"))
    critical: Mapped[bool] = mapped_column(default=False)


class Store(Base):
    __tablename__ = "stores"
    store_code: Mapped[str] = mapped_column(primary_key=True)  # "MW-STEEL"
    name: Mapped[str]
    location: Mapped[str]


class StockMove(Base):
    """One movement of stock in or out of a store. Stock on hand is the sum of these; nothing else holds a quantity."""

    __tablename__ = "stock_moves"
    id: Mapped[int] = mapped_column(primary_key=True)
    on_date: Mapped[str]
    item_code: Mapped[str] = mapped_column(ForeignKey("items.item_code"))
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.store_code"))
    kind: Mapped[str]  # OPENING, RECEIPT, ISSUE, TRANSFER_IN, TRANSFER_OUT, ADJUST
    qty: Mapped[float]  # signed: + in, - out
    unit_cost: Mapped[float]
    value: Mapped[float]  # signed, like qty
    ref_type: Mapped[str]  # GRN, ISSUE, TRANSFER, ADJUST, OPENING
    ref_no: Mapped[str]
    work_order: Mapped[str | None]
    note: Mapped[str] = mapped_column(default="")
    created_by: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Requisition(Base):
    __tablename__ = "requisitions"
    pr_no: Mapped[str] = mapped_column(primary_key=True)  # "PR-260101"
    created_on: Mapped[str]
    requested_by: Mapped[str]
    work_order: Mapped[str | None]
    source: Mapped[str]  # MANUAL, WORK_ORDER, AI_REORDER
    status: Mapped[str]  # SUBMITTED, APPROVED, REJECTED, CONVERTED
    decided_by: Mapped[str | None]
    note: Mapped[str] = mapped_column(default="")
    lines: Mapped[list["RequisitionLine"]] = relationship(order_by="RequisitionLine.id")


class RequisitionLine(Base):
    __tablename__ = "requisition_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    pr_no: Mapped[str] = mapped_column(ForeignKey("requisitions.pr_no"))
    item_code: Mapped[str] = mapped_column(ForeignKey("items.item_code"))
    qty: Mapped[float]
    need_by: Mapped[str]
    po_no: Mapped[str | None]  # set when the line is turned into a purchase order


class ProcOrder(Base):
    __tablename__ = "proc_orders"
    po_no: Mapped[str] = mapped_column(primary_key=True)  # "PO-4500123"
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.vendor_id"))
    pr_no: Mapped[str | None]
    created_on: Mapped[str]
    buyer: Mapped[str]
    status: Mapped[str]  # DRAFT, APPROVED, SENT, PART_RECEIVED, RECEIVED, CLOSED, CANCELLED
    approved_by: Mapped[str | None]
    note: Mapped[str] = mapped_column(default="")
    lines: Mapped[list["ProcOrderLine"]] = relationship(order_by="ProcOrderLine.id")


class ProcOrderLine(Base):
    __tablename__ = "proc_order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_no: Mapped[str] = mapped_column(ForeignKey("proc_orders.po_no"))
    item_code: Mapped[str] = mapped_column(ForeignKey("items.item_code"))
    qty: Mapped[float]
    unit_price: Mapped[float]
    promised_date: Mapped[str]
    received_qty: Mapped[float] = mapped_column(default=0)  # accepted quantity; rejected goods go back and stay open
    work_order: Mapped[str | None]


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    grn_no: Mapped[str] = mapped_column(primary_key=True)  # "GRN-260001"
    po_no: Mapped[str] = mapped_column(ForeignKey("proc_orders.po_no"))
    received_on: Mapped[str]
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.store_code"))
    received_by: Mapped[str]
    lines: Mapped[list["GrnLine"]] = relationship(order_by="GrnLine.id")


class GrnLine(Base):
    __tablename__ = "grn_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    grn_no: Mapped[str] = mapped_column(ForeignKey("goods_receipts.grn_no"))
    po_line_id: Mapped[int] = mapped_column(ForeignKey("proc_order_lines.id"))
    item_code: Mapped[str]
    qty_received: Mapped[float]
    qty_accepted: Mapped[float]
    qty_rejected: Mapped[float]
    reject_reason: Mapped[str] = mapped_column(default="")


class VendorInvoice(Base):
    __tablename__ = "vendor_invoices"
    inv_no: Mapped[str] = mapped_column(primary_key=True)  # "VB-260001"
    vendor_invoice_no: Mapped[str]  # the vendor's own bill number
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.vendor_id"))
    po_no: Mapped[str] = mapped_column(ForeignKey("proc_orders.po_no"))
    invoice_date: Mapped[str]
    due_date: Mapped[str]
    status: Mapped[str]  # MATCHED, EXCEPTION, APPROVED, PAID, REJECTED
    match: Mapped[dict] = mapped_column(JSON)  # the 3-way match result as it was when the bill was entered
    amount: Mapped[float]  # before tax
    tax: Mapped[float]
    total: Mapped[float]
    approved_by: Mapped[str | None]
    approval_reason: Mapped[str | None]
    lines: Mapped[list["VendorInvoiceLine"]] = relationship(order_by="VendorInvoiceLine.id")


class VendorInvoiceLine(Base):
    __tablename__ = "vendor_invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    inv_no: Mapped[str] = mapped_column(ForeignKey("vendor_invoices.inv_no"))
    item_code: Mapped[str]
    qty: Mapped[float]
    unit_price: Mapped[float]


class Payment(Base):
    __tablename__ = "payments"
    pay_no: Mapped[str] = mapped_column(primary_key=True)  # "PAY-260001"
    inv_no: Mapped[str] = mapped_column(ForeignKey("vendor_invoices.inv_no"))
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.vendor_id"))
    paid_on: Mapped[str]
    amount: Mapped[float]
    mode: Mapped[str]  # NEFT, RTGS
    paid_by: Mapped[str]


class Account(Base):
    __tablename__ = "accounts"
    code: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]  # ASSET, LIABILITY, EQUITY, INCOME, EXPENSE


class JournalEntry(Base):
    """One balanced posting. Entries are only ever added; a mistake is corrected by another entry."""

    __tablename__ = "journal_entries"
    je_no: Mapped[str] = mapped_column(primary_key=True)  # "JE-2600001"
    on_date: Mapped[str]
    source_type: Mapped[str]  # OPENING, GRN, INVOICE, PAYMENT, ISSUE, ADJUST
    source_no: Mapped[str]
    narration: Mapped[str]
    created_by: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    lines: Mapped[list["JournalLine"]] = relationship(order_by="JournalLine.id")


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    je_no: Mapped[str] = mapped_column(ForeignKey("journal_entries.je_no"))
    account_code: Mapped[str] = mapped_column(ForeignKey("accounts.code"))
    debit: Mapped[float]
    credit: Mapped[float]
    vendor_id: Mapped[str | None]
    item_code: Mapped[str | None]


class AiFollowup(Base):
    """A chaser e-mail to a vendor, drafted for a person to approve. Never sent by the tool."""

    __tablename__ = "ai_followups"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_no: Mapped[str] = mapped_column(ForeignKey("proc_orders.po_no"))
    vendor_id: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    risk_level: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str]
    status: Mapped[str]  # DRAFT, APPROVED, DISMISSED
    decided_by: Mapped[str | None]
    written_by: Mapped[str]  # "model" or "template"


class AiFlag(Base):
    """Something the anomaly scan found, for a reviewer to look at."""

    __tablename__ = "ai_flags"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]
    severity: Mapped[str]  # high, medium, low
    ref_type: Mapped[str]  # INVOICE, PO, GRN, ITEM
    ref_no: Mapped[str]
    message: Mapped[str]
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    status: Mapped[str]  # OPEN, RESOLVED
    resolved_by: Mapped[str | None]
    resolution_note: Mapped[str | None]
