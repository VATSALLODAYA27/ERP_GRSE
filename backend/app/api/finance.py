"""Finance: the general ledger (accounts, journal, trial balance) and what is owed to vendors. Read-only: every entry
here was posted by a receipt, bill, payment or stock movement."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..core import ledger
from ..core.ledger import money
from ..db import get_session
from ..models import Account, JournalEntry, JournalLine, Vendor, VendorInvoice

router = APIRouter(prefix="/api/ledger", tags=["finance"], dependencies=[Depends(current_user)])

DEBIT_NATURE = ("ASSET", "EXPENSE")  # accounts whose balance is debit minus credit; the others are credit minus debit


def totals(session: Session) -> dict:
    return {code: (debit, credit) for code, debit, credit in session.execute(
        select(JournalLine.account_code, func.sum(JournalLine.debit), func.sum(JournalLine.credit)).group_by(JournalLine.account_code))}


@router.get("/accounts")
def accounts(session: Session = Depends(get_session)):
    """Every account with its total debits and credits, and its balance in the account's own direction."""
    ledger.ensure_chart(session)
    sums = totals(session)
    rows = []
    for a in session.scalars(select(Account).order_by(Account.code)):
        debit, credit = (money(x) for x in sums.get(a.code, (0.0, 0.0)))
        rows.append({"code": a.code, "name": a.name, "type": a.type, "debit": debit, "credit": credit,
                     "balance": money(debit - credit if a.type in DEBIT_NATURE else credit - debit)})
    return rows


@router.get("/journal")
def journal(source_type: str | None = None, account: str | None = None, session: Session = Depends(get_session)):
    query = select(JournalEntry).options(selectinload(JournalEntry.lines)).order_by(JournalEntry.on_date.desc(), JournalEntry.je_no.desc())
    if source_type:
        query = query.where(JournalEntry.source_type == source_type)
    if account:
        query = query.where(JournalEntry.je_no.in_(select(JournalLine.je_no).where(JournalLine.account_code == account)))
    # shortcut: newest 500 entries; add paging when the journal outgrows that
    return ledger.journal_rows(session, session.scalars(query.limit(500)).all())


@router.get("/trial-balance")
def trial_balance(session: Session = Depends(get_session)):
    """Each account's net balance on its debit or credit side. The two columns must add up to the same total."""
    ledger.ensure_chart(session)
    sums = totals(session)
    rows = []
    for a in session.scalars(select(Account).order_by(Account.code)):
        debit, credit = sums.get(a.code, (0.0, 0.0))
        net = money(debit - credit)
        rows.append({"code": a.code, "name": a.name, "type": a.type, "debit": net if net > 0 else 0.0, "credit": -net if net < 0 else 0.0})
    total_debit, total_credit = money(sum(r["debit"] for r in rows)), money(sum(r["credit"] for r in rows))
    return {"rows": rows, "total_debit": total_debit, "total_credit": total_credit, "balanced": abs(total_debit - total_credit) < 0.01}


@router.get("/payables")
def payables(session: Session = Depends(get_session)):
    """What is owed to each vendor, aged by how far past its due date each approved, unpaid bill is."""
    today = date.today()
    balances = {vendor_id: money(credit - debit) for vendor_id, debit, credit in session.execute(
        select(JournalLine.vendor_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .where(JournalLine.account_code == "2000").group_by(JournalLine.vendor_id))}
    buckets = {}
    for inv in session.scalars(select(VendorInvoice).where(VendorInvoice.status == "APPROVED")):
        b = buckets.setdefault(inv.vendor_id, {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "over_90": 0.0, "next_due": None})
        late = (today - date.fromisoformat(inv.due_date)).days
        key = "current" if late <= 0 else "d1_30" if late <= 30 else "d31_60" if late <= 60 else "d61_90" if late <= 90 else "over_90"
        b[key] += inv.total
        b["next_due"] = min(filter(None, [b["next_due"], inv.due_date]))
    rows = []
    for v in session.scalars(select(Vendor).order_by(Vendor.vendor_id)):
        balance, b = balances.get(v.vendor_id, 0.0), buckets.get(v.vendor_id)
        if abs(balance) < 0.005 and not b:
            continue
        b = b or {"current": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "over_90": 0.0, "next_due": None}
        rows.append({"vendor_id": v.vendor_id, "name": v.name, "balance": balance, **{k: money(x) if k != "next_due" else x for k, x in b.items()},
                     "overdue": money(b["d1_30"] + b["d31_60"] + b["d61_90"] + b["over_90"])})
    rows.sort(key=lambda r: (r["next_due"] or "9999", -r["balance"]))
    return {"vendors": rows, "total": money(sum(r["balance"] for r in rows))}


@router.get("/vendor/{vendor_id}")
def vendor_ledger(vendor_id: str, session: Session = Depends(get_session)):
    """The vendor's payables account, oldest first, with the running balance owed."""
    if session.get(Vendor, vendor_id) is None:
        raise HTTPException(404, f"Vendor {vendor_id} not found.")
    return ledger.vendor_account(session, vendor_id)["entries"]
