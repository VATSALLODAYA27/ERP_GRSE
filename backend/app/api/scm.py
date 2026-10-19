"""Procurement and inventory: vendors, items, stores, stock, requisitions, purchase orders, goods receipts and vendor bills.

Everyone signed in may see all of it and raise requisitions, purchase orders, receipts, bills, issues and transfers.
A reviewer or the admin approves; a purchase order above ₹10,00,000 needs the admin. Every change is in the audit log.
Refusals from the books (stock below zero, a quantity that does not fit) come back as 400 with the reason.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import audit, current_user, reviewer
from ..core import intel, ledger, procure
from ..core.ledger import EPS, inr, money, qty_text
from ..db import get_session
from ..models import (AiFlag, AiFollowup, AuditEntry, BomItem, GoodsReceipt, Item, JournalEntry, Payment, ProcOrder, ProcOrderLine,
                      Requisition, StockMove, Store, User, Vendor, VendorInvoice, WorkOrder, as_dict)
from ..schemas import (AdjustIn, InvoiceIn, IssueIn, PayIn, PurchaseOrderIn, ReasonIn, ReceiptIn, RequisitionIn, TransferIn)

router = APIRouter(prefix="/api", tags=["scm"], dependencies=[Depends(current_user)])


def or_404(session: Session, model, key: str, what: str):
    row = session.get(model, key)
    if row is None:
        raise HTTPException(404, f"{what} {key} not found.")
    return row


def not_future(day: date | None, what: str) -> str:
    day = day or date.today()
    if day > date.today():
        raise HTTPException(422, f"The {what} cannot be in the future.")
    return day.isoformat()


def known_work_order(session: Session, order_no: str | None) -> None:
    if order_no and session.get(WorkOrder, order_no) is None:
        raise HTTPException(422, f"Work order {order_no} is not in the ERP extract.")


def names(session: Session, key, label) -> dict:
    return dict(session.execute(select(key, label)).all())


def descriptions(session: Session) -> dict:
    return {i.item_code: i for i in session.scalars(select(Item))}


# --- Master data ---


@router.get("/vendors")
def vendors(session: Session = Depends(get_session)):
    return intel.vendor_rows(session)


@router.get("/vendors/{vendor_id}")
def vendor_detail(vendor_id: str, session: Session = Depends(get_session)):
    or_404(session, Vendor, vendor_id, "Vendor")
    row = next(r for r in intel.vendor_rows(session) if r["vendor_id"] == vendor_id)
    metrics = ("grade", "on_time_pct", "avg_delay_days", "rejection_pct", "spend_ytd", "open_po_value", "orders_closed", "deliveries")
    orders = session.scalars(select(ProcOrder).where(ProcOrder.vendor_id == vendor_id).order_by(ProcOrder.po_no.desc())
                             .options(selectinload(ProcOrder.lines))).all()
    return row | {"scorecard": {k: row[k] for k in metrics}, "orders": po_rows(session, orders),
                  "payables": ledger.vendor_account(session, vendor_id)}


@router.get("/items")
def items(category: str | None = None, q: str | None = None, session: Session = Depends(get_session)):
    rows = intel.item_rows(session)
    if category:
        rows = [r for r in rows if r["category"] == category]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in r["item_code"].lower() or needle in r["description"].lower()]
    return rows


@router.get("/items/{item_code}")
def item_detail(item_code: str, session: Session = Depends(get_session)):
    item = or_404(session, Item, item_code, "Item")
    row = next(r for r in intel.item_rows(session) if r["item_code"] == item_code)
    stores = names(session, Store.store_code, Store.name)
    by_store = [{"store_code": code, "store_name": stores.get(code, code), "qty": round(qty, 6), "value": money(value)}
                for code, qty, value in session.execute(select(StockMove.store_code, func.sum(StockMove.qty), func.sum(StockMove.value))
                                                        .where(StockMove.item_code == item_code).group_by(StockMove.store_code)
                                                        .order_by(StockMove.store_code))
                if abs(qty) > EPS]
    moves = session.scalars(select(StockMove).where(StockMove.item_code == item_code)
                            .order_by(StockMove.on_date.desc(), StockMove.id.desc()).limit(200)).all()
    risk = {r["line_id"]: r for r in intel.delivery_risk(session)}
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    open_orders = [{"po_no": po.po_no, "line_id": line.id, "vendor_id": po.vendor_id, "vendor_name": vendor_names[po.vendor_id],
                    "status": po.status, "qty": line.qty, "received_qty": line.received_qty, "promised_date": line.promised_date,
                    "risk_level": risk[line.id]["level"] if line.id in risk else None}
                   for line, po in session.execute(select(ProcOrderLine, ProcOrder).join(ProcOrder, ProcOrder.po_no == ProcOrderLine.po_no)
                                                   .where(ProcOrderLine.item_code == item_code, ProcOrder.status.in_(procure.OPEN_PO))
                                                   .order_by(ProcOrderLine.promised_date)).all()
                   if line.qty - line.received_qty > EPS]
    where_used = [{"drawing_no": b.drawing_no, "rev": b.rev, "part_no": b.part_no, "description": b.description, "qty": b.qty}
                  for b in session.scalars(select(BomItem).where(BomItem.part_no == item_code).order_by(BomItem.drawing_no, BomItem.rev))]
    return row | {"preferred_vendor_name": vendor_names.get(item.preferred_vendor_id), "by_store": by_store,
                  "moves": move_rows(session, moves), "open_orders": open_orders, "where_used": where_used}


@router.get("/stores")
def stores(session: Session = Depends(get_session)):
    held = {}
    for code, item_code, qty, value in session.execute(select(StockMove.store_code, StockMove.item_code, func.sum(StockMove.qty),
                                                              func.sum(StockMove.value)).group_by(StockMove.store_code, StockMove.item_code)):
        value_sum, count = held.get(code, (0.0, 0))
        held[code] = (value_sum + value, count + (qty > EPS))
    return [{"store_code": s.store_code, "name": s.name, "location": s.location, "stock_value": money(held.get(s.store_code, (0, 0))[0]),
             "items": held.get(s.store_code, (0, 0))[1]} for s in session.scalars(select(Store).order_by(Store.store_code))]


# --- Inventory ---


def move_rows(session: Session, moves) -> list:
    items_ = descriptions(session)
    return [{"id": m.id, "on_date": m.on_date, "item_code": m.item_code, "description": items_[m.item_code].description,
             "uom": items_[m.item_code].uom, "store_code": m.store_code, "kind": m.kind, "qty": m.qty, "unit_cost": m.unit_cost,
             "value": m.value, "ref_type": m.ref_type, "ref_no": m.ref_no, "work_order": m.work_order, "note": m.note,
             "created_by": m.created_by} for m in moves]


@router.get("/stock/moves")
def stock_moves(item: str | None = None, store: str | None = None, kind: str | None = None, session: Session = Depends(get_session)):
    query = select(StockMove)
    if item:
        query = query.where(StockMove.item_code == item)
    if store:
        query = query.where(StockMove.store_code == store)
    if kind:
        query = query.where(StockMove.kind == kind)
    # shortcut: newest 500 moves; add paging when the stock ledger outgrows that
    return move_rows(session, session.scalars(query.order_by(StockMove.on_date.desc(), StockMove.id.desc()).limit(500)))


@router.post("/stock/issue", status_code=201)
def issue_stock(body: IssueIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    known_work_order(session, body.work_order)
    row = ledger.post_issue(session, body.item_code, body.store_code, body.qty, body.work_order, user.username, body.note.strip())
    audit(session, user.username, user.role, "stock.issued", f"item {body.item_code}",
          f"{qty_text(body.qty)} from {body.store_code} to {body.work_order} at {inr(-row.value)} ({row.ref_no})")
    session.commit()
    return move_rows(session, [row])[0]


@router.post("/stock/transfer", status_code=201)
def transfer_stock(body: TransferIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = ledger.post_transfer(session, body.item_code, body.from_store, body.to_store, body.qty, user.username, body.note.strip())
    audit(session, user.username, user.role, "stock.transferred", f"item {body.item_code}",
          f"{qty_text(body.qty)} from {body.from_store} to {body.to_store} ({rows[0].ref_no})")
    session.commit()
    return move_rows(session, rows)


@router.post("/stock/adjust", status_code=201)
def adjust_stock(body: AdjustIn, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    row = ledger.post_adjust(session, body.item_code, body.store_code, body.qty, user.username, body.note.strip())
    audit(session, user.username, user.role, "stock.adjusted", f"item {body.item_code}",
          f"{body.qty:+g} in {body.store_code} at {inr(row.value)} ({row.ref_no}). {body.note.strip()}".strip())
    session.commit()
    return move_rows(session, [row])[0]


# --- Requisitions ---


def requisition_row(pr: Requisition, items_: dict) -> dict:
    return as_dict(pr) | {"lines": len(pr.lines), "value": money(sum(l.qty * items_[l.item_code].std_price for l in pr.lines))}


def requisition_detail(session: Session, pr: Requisition) -> dict:
    items_ = descriptions(session)
    return as_dict(pr) | {
        "value": money(sum(l.qty * items_[l.item_code].std_price for l in pr.lines)),
        "lines": [{"id": l.id, "item_code": l.item_code, "description": items_[l.item_code].description, "uom": items_[l.item_code].uom,
                   "qty": l.qty, "need_by": l.need_by, "po_no": l.po_no, "est_value": money(l.qty * items_[l.item_code].std_price)}
                  for l in pr.lines],
        "audit": audit_rows(session, [f"requisition {pr.pr_no}"]),
    }


@router.get("/requisitions")
def requisitions(session: Session = Depends(get_session)):
    items_ = descriptions(session)
    return [requisition_row(pr, items_) for pr in session.scalars(select(Requisition).order_by(Requisition.pr_no.desc())
                                                                   .options(selectinload(Requisition.lines)))]


@router.get("/requisitions/{pr_no}")
def requisition(pr_no: str, session: Session = Depends(get_session)):
    return requisition_detail(session, or_404(session, Requisition, pr_no, "Requisition"))


@router.post("/requisitions", status_code=201)
def create_requisition(body: RequisitionIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    known_work_order(session, body.work_order)
    pr = procure.create_requisition(session, [l.model_dump() | {"need_by": l.need_by.isoformat()} for l in body.lines], user.username,
                                    work_order=body.work_order, note=body.note.strip())
    audit(session, user.username, user.role, "requisition.created", f"requisition {pr.pr_no}",
          f"{len(pr.lines)} lines" + (f" for {pr.work_order}" if pr.work_order else ""))
    session.commit()
    return requisition_detail(session, pr)


@router.post("/requisitions/{pr_no}/approve")
def approve_requisition(pr_no: str, body: ReasonIn | None = None, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    pr = or_404(session, Requisition, pr_no, "Requisition")
    procure.decide_requisition(pr, True, user.username)
    audit(session, user.username, user.role, "requisition.approved", f"requisition {pr_no}", (body.reason.strip() if body else ""))
    session.commit()
    return requisition_detail(session, pr)


@router.post("/requisitions/{pr_no}/reject")
def reject_requisition(pr_no: str, body: ReasonIn | None = None, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    pr = or_404(session, Requisition, pr_no, "Requisition")
    procure.decide_requisition(pr, False, user.username)
    reason = body.reason.strip() if body else ""
    if reason:
        pr.note = f"{pr.note} Rejected: {reason}".strip()
    audit(session, user.username, user.role, "requisition.rejected", f"requisition {pr_no}", reason)
    session.commit()
    return requisition_detail(session, pr)


@router.post("/requisitions/{pr_no}/convert")
def convert_requisition(pr_no: str, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    pr = or_404(session, Requisition, pr_no, "Requisition")
    orders = procure.convert_requisition(session, pr, user.username)
    for po in orders:
        audit(session, user.username, user.role, "po.created", f"purchase order {po.po_no}",
              f"draft from requisition {pr_no}: {len(po.lines)} lines, {inr(procure.po_value(po))}")
    audit(session, user.username, user.role, "requisition.converted", f"requisition {pr_no}", ", ".join(po.po_no for po in orders))
    session.commit()
    return {"orders": [po.po_no for po in orders]}


# --- Purchase orders ---


def po_rows(session: Session, orders, risks: list | None = None) -> list:
    risks = risks if risks is not None else intel.delivery_risk(session)
    worst = {}
    for r in risks:  # highest score first, so the first line seen for an order is its worst
        worst.setdefault(r["po_no"], r)
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    rows = []
    for po in orders:
        value = procure.po_value(po)
        received = sum(min(l.received_qty, l.qty) * l.unit_price for l in po.lines)
        still_open = [l for l in po.lines if l.qty - l.received_qty > EPS]
        w = worst.get(po.po_no)
        rows.append({"po_no": po.po_no, "vendor_id": po.vendor_id, "vendor_name": vendor_names[po.vendor_id], "created_on": po.created_on,
                     "status": po.status, "buyer": po.buyer, "approved_by": po.approved_by, "pr_no": po.pr_no, "value": value,
                     "open_value": procure.open_value(po), "lines": len(po.lines),
                     "received_pct": round(100 * received / value, 1) if value else 0.0,
                     "next_promised": min(l.promised_date for l in still_open) if still_open else None,
                     "risk_level": w and w["level"], "risk_score": w and w["score"], "needs_admin": value > procure.APPROVAL_LIMIT})
    return rows


def audit_rows(session: Session, targets: list) -> list:
    return [as_dict(a) for a in session.scalars(select(AuditEntry).where(AuditEntry.target.in_(targets)).order_by(AuditEntry.id.desc()))]


def grn_row(grn: GoodsReceipt, prices: dict, vendor_names: dict, vendor_id: str) -> dict:
    return {"grn_no": grn.grn_no, "po_no": grn.po_no, "vendor_id": vendor_id, "vendor_name": vendor_names[vendor_id],
            "received_on": grn.received_on, "store_code": grn.store_code, "received_by": grn.received_by, "lines": len(grn.lines),
            "qty_received": sum(l.qty_received for l in grn.lines), "qty_accepted": sum(l.qty_accepted for l in grn.lines),
            "qty_rejected": sum(l.qty_rejected for l in grn.lines),
            "value": money(sum(l.qty_accepted * prices.get(l.po_line_id, 0) for l in grn.lines))}


def flags_for(session: Session, ref_type: str, refs: list, open_only: bool = False) -> dict:
    query = select(AiFlag).where(AiFlag.ref_type == ref_type, AiFlag.ref_no.in_(refs))
    if open_only:
        query = query.where(AiFlag.status == "OPEN")
    out = {}
    for f in session.scalars(query.order_by(AiFlag.id)):
        out.setdefault(f.ref_no, []).append(intel.flag_row(f))
    return out


def invoice_row(inv: VendorInvoice, vendor_names: dict, flags: dict) -> dict:
    return {"inv_no": inv.inv_no, "vendor_invoice_no": inv.vendor_invoice_no, "vendor_id": inv.vendor_id,
            "vendor_name": vendor_names[inv.vendor_id], "po_no": inv.po_no, "invoice_date": inv.invoice_date, "due_date": inv.due_date,
            "status": inv.status, "amount": inv.amount, "tax": inv.tax, "total": inv.total, "approved_by": inv.approved_by,
            "approval_reason": inv.approval_reason, "flags": flags.get(inv.inv_no, [])}


def followup_row(f: AiFollowup, vendor_names: dict) -> dict:
    return as_dict(f) | {"vendor_name": vendor_names.get(f.vendor_id, f.vendor_id)}


def po_detail(session: Session, po: ProcOrder) -> dict:
    risks = intel.delivery_risk(session)
    by_line = {r["line_id"]: r for r in risks}
    items_ = descriptions(session)
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    vendor = next(r for r in intel.vendor_rows(session) if r["vendor_id"] == po.vendor_id)
    prices = {l.id: l.unit_price for l in po.lines}
    grns = session.scalars(select(GoodsReceipt).where(GoodsReceipt.po_no == po.po_no).order_by(GoodsReceipt.grn_no)
                           .options(selectinload(GoodsReceipt.lines))).all()
    invoices = session.scalars(select(VendorInvoice).where(VendorInvoice.po_no == po.po_no).order_by(VendorInvoice.inv_no)).all()
    pays = [p.pay_no for p in session.scalars(select(Payment).where(Payment.inv_no.in_([i.inv_no for i in invoices])))]
    sources = [g.grn_no for g in grns] + [i.inv_no for i in invoices] + pays
    journal = session.scalars(select(JournalEntry).where(JournalEntry.source_no.in_(sources)).order_by(JournalEntry.je_no.desc())
                              .options(selectinload(JournalEntry.lines))).all()
    flags = flags_for(session, "INVOICE", [i.inv_no for i in invoices])

    def risk(line):
        r = by_line.get(line.id)
        return r and {k: r[k] for k in ("score", "level", "predicted_date", "days_late_predicted", "reasons", "impacted_work_orders")}

    return as_dict(po) | po_rows(session, [po], risks)[0] | {
        "vendor": vendor,
        "lines": [{"id": l.id, "item_code": l.item_code, "description": items_[l.item_code].description, "uom": items_[l.item_code].uom,
                   "qty": l.qty, "unit_price": l.unit_price, "value": money(l.qty * l.unit_price), "promised_date": l.promised_date,
                   "received_qty": l.received_qty, "work_order": l.work_order, "risk": risk(l)} for l in po.lines],
        "receipts": [grn_row(g, prices, vendor_names, po.vendor_id) for g in grns],
        "invoices": [invoice_row(i, vendor_names, flags) for i in invoices],
        "followups": [followup_row(f, vendor_names) for f in session.scalars(select(AiFollowup).where(AiFollowup.po_no == po.po_no)
                                                                               .order_by(AiFollowup.id.desc()))],
        "journal": ledger.journal_rows(session, journal),
        "audit": audit_rows(session, [f"purchase order {po.po_no}"] + [f"goods receipt {g.grn_no}" for g in grns]
                            + [f"vendor bill {i.inv_no}" for i in invoices]),
    }


def get_po(session: Session, po_no: str) -> ProcOrder:
    return or_404(session, ProcOrder, po_no, "Purchase order")


@router.get("/purchase-orders")
def purchase_orders(status: str | None = None, vendor: str | None = None, session: Session = Depends(get_session)):
    query = select(ProcOrder).options(selectinload(ProcOrder.lines)).order_by(ProcOrder.po_no.desc())
    if status:
        query = query.where(ProcOrder.status == status)
    if vendor:
        query = query.where(ProcOrder.vendor_id == vendor)
    return po_rows(session, session.scalars(query).all())


@router.get("/purchase-orders/{po_no}")
def purchase_order(po_no: str, session: Session = Depends(get_session)):
    return po_detail(session, get_po(session, po_no))


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(body: PurchaseOrderIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    for line in body.lines:
        known_work_order(session, line.work_order)
    po = procure.create_po(session, body.vendor_id, [l.model_dump() | {"promised_date": l.promised_date.isoformat()} for l in body.lines],
                           user.username, note=body.note.strip())
    audit(session, user.username, user.role, "po.created", f"purchase order {po.po_no}",
          f"draft to {po.vendor_id}: {len(po.lines)} lines, {inr(procure.po_value(po))}")
    session.commit()
    return po_detail(session, po)


@router.post("/purchase-orders/{po_no}/approve")
def approve_purchase_order(po_no: str, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    po = get_po(session, po_no)
    procure.approve_po(po, user.username, user.role)
    audit(session, user.username, user.role, "po.approved", f"purchase order {po_no}", f"{inr(procure.po_value(po))} to {po.vendor_id}")
    session.commit()
    return po_detail(session, po)


@router.post("/purchase-orders/{po_no}/send")
def send_purchase_order(po_no: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    po = get_po(session, po_no)
    procure.send_po(po)
    audit(session, user.username, user.role, "po.sent", f"purchase order {po_no}", "marked as sent (simulated; nothing left the system)")
    session.commit()
    return po_detail(session, po)


@router.post("/purchase-orders/{po_no}/receive", status_code=201)
def receive_goods(po_no: str, body: ReceiptIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    po = get_po(session, po_no)
    received_on = not_future(body.received_on, "receipt date")
    grn = ledger.post_receipt(session, po, body.store_code, received_on, [l.model_dump() for l in body.lines], user.username)
    accepted = sum(l.qty_accepted for l in grn.lines)
    rejected = sum(l.qty_rejected for l in grn.lines)
    audit(session, user.username, user.role, "grn.posted", f"goods receipt {grn.grn_no}",
          f"against {po_no} into {body.store_code}: {qty_text(accepted)} accepted, {qty_text(rejected)} rejected; order now {po.status}")
    intel.scan(session)  # a high rejection is flagged at once
    session.commit()
    return receipt_detail(session, grn)


# --- Goods receipts ---


def receipt_detail(session: Session, grn: GoodsReceipt) -> dict:
    po = session.get(ProcOrder, grn.po_no)
    prices = {l.id: l.unit_price for l in po.lines}
    items_ = descriptions(session)
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    journal = session.scalars(select(JournalEntry).where(JournalEntry.source_no == grn.grn_no).options(selectinload(JournalEntry.lines))).all()
    return grn_row(grn, prices, vendor_names, po.vendor_id) | {
        "lines": [{"id": l.id, "po_line_id": l.po_line_id, "item_code": l.item_code, "description": items_[l.item_code].description,
                   "uom": items_[l.item_code].uom, "qty_received": l.qty_received, "qty_accepted": l.qty_accepted,
                   "qty_rejected": l.qty_rejected, "reject_reason": l.reject_reason, "unit_price": prices.get(l.po_line_id),
                   "value": money(l.qty_accepted * prices.get(l.po_line_id, 0))} for l in grn.lines],
        "line_count": len(grn.lines),
        "journal": ledger.journal_rows(session, journal),
        "flags": flags_for(session, "GRN", [grn.grn_no]).get(grn.grn_no, []),
    }


@router.get("/receipts")
def receipts(session: Session = Depends(get_session)):
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    orders = {po.po_no: po for po in session.scalars(select(ProcOrder).options(selectinload(ProcOrder.lines)))}
    prices = {l.id: l.unit_price for po in orders.values() for l in po.lines}
    grns = session.scalars(select(GoodsReceipt).order_by(GoodsReceipt.received_on.desc(), GoodsReceipt.grn_no.desc())
                           .options(selectinload(GoodsReceipt.lines)))
    return [grn_row(g, prices, vendor_names, orders[g.po_no].vendor_id) for g in grns]


@router.get("/receipts/{grn_no}")
def receipt(grn_no: str, session: Session = Depends(get_session)):
    return receipt_detail(session, or_404(session, GoodsReceipt, grn_no, "Goods receipt"))


# --- Vendor bills ---


def invoice_detail(session: Session, inv: VendorInvoice) -> dict:
    items_ = descriptions(session)
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    pays = session.scalars(select(Payment).where(Payment.inv_no == inv.inv_no).order_by(Payment.pay_no)).all()
    journal = session.scalars(select(JournalEntry).where(JournalEntry.source_no.in_([inv.inv_no] + [p.pay_no for p in pays]))
                              .order_by(JournalEntry.je_no.desc()).options(selectinload(JournalEntry.lines))).all()
    return invoice_row(inv, vendor_names, flags_for(session, "INVOICE", [inv.inv_no])) | {
        "lines": [{"id": l.id, "item_code": l.item_code, "description": items_[l.item_code].description if l.item_code in items_ else "",
                   "qty": l.qty, "unit_price": l.unit_price, "value": money(l.qty * l.unit_price)} for l in inv.lines],
        "match": inv.match,
        "payments": [as_dict(p) for p in pays],
        "journal": ledger.journal_rows(session, journal),
        "audit": audit_rows(session, [f"vendor bill {inv.inv_no}"]),
    }


def get_invoice(session: Session, inv_no: str) -> VendorInvoice:
    return or_404(session, VendorInvoice, inv_no, "Vendor bill")


@router.get("/invoices")
def invoices(status: str | None = None, session: Session = Depends(get_session)):
    query = select(VendorInvoice).order_by(VendorInvoice.invoice_date.desc(), VendorInvoice.inv_no.desc())
    if status:
        query = query.where(VendorInvoice.status == status)
    rows = session.scalars(query).all()
    flags = flags_for(session, "INVOICE", [i.inv_no for i in rows], open_only=True)
    vendor_names = names(session, Vendor.vendor_id, Vendor.name)
    return [invoice_row(i, vendor_names, flags) for i in rows]


@router.get("/invoices/{inv_no}")
def invoice(inv_no: str, session: Session = Depends(get_session)):
    return invoice_detail(session, get_invoice(session, inv_no))


@router.post("/invoices", status_code=201)
def enter_invoice(body: InvoiceIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    po = get_po(session, body.po_no)
    invoice_date = not_future(body.invoice_date, "bill date")
    inv = procure.create_invoice(session, po, body.vendor_invoice_no, invoice_date, [l.model_dump() for l in body.lines], user.username)
    audit(session, user.username, user.role, "invoice.entered", f"vendor bill {inv.inv_no}",
          f"{inv.vendor_invoice_no} against {po.po_no}, {inr(inv.total)}: {inv.status}")
    intel.scan(session)  # duplicate, price and quantity checks run as soon as the bill is in
    session.commit()
    return invoice_detail(session, inv)


@router.post("/invoices/{inv_no}/approve")
def approve_invoice(inv_no: str, body: ReasonIn | None = None, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    inv = get_invoice(session, inv_no)
    reason = body.reason.strip() if body else ""
    was = inv.status
    procure.approve_invoice(inv, user.username, reason)
    entry = ledger.post_invoice_approval(session, inv, get_po(session, inv.po_no), user.username)
    audit(session, user.username, user.role, "invoice.approved", f"vendor bill {inv_no}",
          f"{inr(inv.total)} ({was}){'. ' + reason if reason else ''}; posted {entry.je_no}")
    session.commit()
    return invoice_detail(session, inv)


@router.post("/invoices/{inv_no}/reject")
def reject_invoice(inv_no: str, body: ReasonIn, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    inv = get_invoice(session, inv_no)
    procure.reject_invoice(inv, user.username, body.reason.strip())
    audit(session, user.username, user.role, "invoice.rejected", f"vendor bill {inv_no}", body.reason.strip())
    session.commit()
    return invoice_detail(session, inv)


@router.post("/invoices/{inv_no}/pay", status_code=201)
def pay_invoice(inv_no: str, body: PayIn | None = None, user: User = Depends(reviewer), session: Session = Depends(get_session)):
    inv = get_invoice(session, inv_no)
    body = body or PayIn()
    paid_on = not_future(body.paid_on, "payment date")
    payment = ledger.post_payment(session, inv, get_po(session, inv.po_no), user.username, body.mode, paid_on)
    audit(session, user.username, user.role, "payment.posted", f"vendor bill {inv_no}",
          f"{payment.pay_no}: {body.mode} {inr(payment.amount)} to {inv.vendor_id}")
    session.commit()
    return invoice_detail(session, inv)

