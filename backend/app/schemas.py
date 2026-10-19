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
    # The page name goes into the prompt, so it is letters and spaces only.
    page: str = Field(default="Dashboard", max_length=40, pattern=r"^[A-Za-z ]+$")
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


class AuditOut(FromRow):
    id: int
    at: datetime
    username: str
    role: str
    action: str
    target: str
    detail: str
