from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FromRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,32}$")
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["reviewer", "engineer"] = "reviewer"  # an admin account can never be registered


class UserOut(FromRow):
    username: str
    name: str
    role: str


class UserAdminOut(UserOut):
    status: str


class UserStatusIn(BaseModel):
    status: Literal["active", "disabled"]


class RuleApprovalIn(BaseModel):
    note: str = Field(default="", max_length=500)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class HelperTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class HelperIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    # The page name goes into the prompt, so it is letters, spaces and "&" (Items & Stock) only.
    page: str = Field(default="Control Tower", max_length=40, pattern=r"^[A-Za-z &]+$")
    history: list[HelperTurn] = Field(default=[], max_length=8)


class CommentOut(FromRow):
    id: int
    username: str
    text: str
    created_at: datetime




REGISTER_STATUSES = ("APPROVED", "UNDER REVIEW", "FOR INFORMATION")


class DrawingEdit(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    current_rev: str = Field(pattern=r"^[A-Za-z0-9]{1,5}$")
    status: Literal["APPROVED", "UNDER REVIEW", "FOR INFORMATION"]


class ClassApprovalIn(BaseModel):
    drawing_no: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,39}$")
    rev: str = Field(pattern=r"^[A-Za-z0-9]{1,5}$")
    submitted_to: str = Field(min_length=1, max_length=80)
    submitted_on: date
    state: Literal["AWAITING", "APPROVED", "RETURNED WITH COMMENTS"]


class DrawingNew(DrawingEdit):
    drawing_no: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,39}$")


class FindingOut(FromRow):
    rule_id: str
    rule_name: str
    severity: str
    clause: str
    standard: str
    evidence: str
    bbox: list[float] | None


class DecisionIn(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = ""


class DecisionOut(FromRow):
    decision: str
    is_override: bool
    reason: str
    decided_by: str
    decided_at: datetime


class CheckSummary(FromRow):
    id: int
    drawing_no: str
    revision: str
    filename: str
    verdict: str
    submitted_by: str
    created_at: datetime
    decision: DecisionOut | None


class CheckOut(CheckSummary):
    extracted: dict
    register_row: dict | None
    revision_diff: dict | None
    bom_check: list | None
    impact: dict | None
    explanation: dict | None
    findings: list[FindingOut]
    comments: list[CommentOut]


# --- PRAVAH ERP inputs. Codes are checked against the master data by the route; these only check the shape. ---

CODE = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$"


class PrLineIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    qty: float = Field(gt=0, le=1_000_000)
    need_by: date


class RequisitionIn(BaseModel):
    work_order: str | None = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=500)
    lines: list[PrLineIn] = Field(min_length=1, max_length=50)


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class PoLineIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    qty: float = Field(gt=0, le=1_000_000)
    unit_price: float = Field(gt=0, le=1_000_000_000)
    promised_date: date
    work_order: str | None = Field(default=None, max_length=40)


class PurchaseOrderIn(BaseModel):
    vendor_id: str = Field(pattern=CODE)
    note: str = Field(default="", max_length=500)
    lines: list[PoLineIn] = Field(min_length=1, max_length=50)


class ReceiptLineIn(BaseModel):
    line_id: int
    qty_received: float = Field(ge=0, le=1_000_000)
    qty_accepted: float = Field(ge=0, le=1_000_000)
    reject_reason: str = Field(default="", max_length=200)


class ReceiptIn(BaseModel):
    store_code: str = Field(pattern=CODE)
    received_on: date | None = None
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=50)


class InvoiceLineIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    qty: float = Field(gt=0, le=1_000_000)
    unit_price: float = Field(gt=0, le=1_000_000_000)


class InvoiceIn(BaseModel):
    vendor_invoice_no: str = Field(min_length=1, max_length=40)
    po_no: str = Field(pattern=CODE)
    invoice_date: date
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=50)


class PayIn(BaseModel):
    mode: Literal["NEFT", "RTGS"] = "NEFT"
    paid_on: date | None = None


class IssueIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    store_code: str = Field(pattern=CODE)
    qty: float = Field(gt=0, le=1_000_000)
    work_order: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=500)


class TransferIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    from_store: str = Field(pattern=CODE)
    to_store: str = Field(pattern=CODE)
    qty: float = Field(gt=0, le=1_000_000)
    note: str = Field(default="", max_length=500)


class AdjustIn(BaseModel):
    item_code: str = Field(pattern=CODE)
    store_code: str = Field(pattern=CODE)
    qty: float = Field(ge=-1_000_000, le=1_000_000)  # signed: + found, - written off
    note: str = Field(default="", max_length=500)


class FollowupDraftIn(BaseModel):
    po_no: str | None = Field(default=None, pattern=CODE)
    all_high: bool = False


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=500)


class ReorderRequisitionIn(BaseModel):
    item_codes: list[str] = Field(min_length=1, max_length=50)


class AuditOut(FromRow):
    id: int
    at: datetime
    username: str
    role: str
    action: str
    target: str
    detail: str
