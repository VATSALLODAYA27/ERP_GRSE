"""Purchase to pay: requisitions, purchase orders, the 3-way match and vendor bills.

The money side of each step is posted by ledger.py; this module decides what may happen and keeps the records.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GoodsReceipt, GrnLine, ProcOrder, ProcOrderLine, Requisition, RequisitionLine, Vendor, VendorInvoice, VendorInvoiceLine
from .ledger import EPS, GST_RATE, LedgerError, StateError, get_item, inr, money, next_no, plus_days, qty_text, today, year_series

APPROVAL_LIMIT = 1_000_000  # ₹10,00,000: a purchase order above this needs the admin
PRICE_TOLERANCE_PCT = 2.0  # an invoiced price within ±2% of the PO price matches
OPEN_PO = ("DRAFT", "APPROVED", "SENT", "PART_RECEIVED")  # not yet fully received, closed or cancelled: still to come
WITH_VENDOR = ("APPROVED", "SENT", "PART_RECEIVED")  # approved, so the vendor is working on it: delivery risk applies
LIVE_INVOICE = ("MATCHED", "EXCEPTION", "APPROVED", "PAID")  # every bill except a rejected one


def po_value(po: ProcOrder) -> float:
    return money(sum(line.qty * line.unit_price for line in po.lines))


def open_value(po: ProcOrder) -> float:
    return money(sum(max(line.qty - line.received_qty, 0) * line.unit_price for line in po.lines))


def get_vendor(session: Session, vendor_id: str) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise LedgerError(f"Vendor {vendor_id} does not exist.")
    return vendor


# --- Requisitions ---


def create_requisition(session: Session, lines: list, user: str, work_order: str | None = None, note: str = "",
                       source: str = "MANUAL", created_on: str | None = None, pr_no: str | None = None) -> Requisition:
    """`lines` holds dicts of item_code, qty, need_by (ISO date)."""
    if not lines:
        raise LedgerError("A requisition needs at least one line.")
    pr = Requisition(pr_no=pr_no or next_no(session, Requisition.pr_no, "PR-", int(f"{year_series(6) // 10000}0101")),
                     created_on=created_on or today(), requested_by=user, work_order=work_order or None,
                     source=source if source != "MANUAL" or not work_order else "WORK_ORDER", status="SUBMITTED", note=note)
    for line in lines:
        get_item(session, line["item_code"])
        if line["qty"] <= 0:
            raise LedgerError(f"{line['item_code']}: the quantity must be above zero.")
        pr.lines.append(RequisitionLine(item_code=line["item_code"], qty=float(line["qty"]), need_by=line["need_by"]))
    session.add(pr)
    session.flush()
    return pr


def decide_requisition(pr: Requisition, approve: bool, user: str) -> None:
    if pr.status != "SUBMITTED":
        raise StateError(f"{pr.pr_no} is {pr.status}; only a submitted requisition can be approved or rejected.")
    pr.status, pr.decided_by = ("APPROVED" if approve else "REJECTED"), user


def convert_requisition(session: Session, pr: Requisition, user: str) -> list[ProcOrder]:
    """One draft purchase order per preferred vendor, at the standard price, promised after the vendor's lead time."""
    if pr.status != "APPROVED":
        raise StateError(f"{pr.pr_no} is {pr.status}; only an approved requisition can be turned into purchase orders.")
    by_vendor = defaultdict(list)
    for line in pr.lines:
        item = get_item(session, line.item_code)
        if not item.preferred_vendor_id:
            raise LedgerError(f"{item.item_code} has no preferred vendor; raise its purchase order by hand.")
        by_vendor[item.preferred_vendor_id].append((line, item))
    orders = []
    for vendor_id, pairs in sorted(by_vendor.items()):
        vendor = get_vendor(session, vendor_id)
        promised = plus_days(today(), vendor.lead_time_days)
        po = create_po(session, vendor_id, [{"item_code": item.item_code, "qty": line.qty, "unit_price": item.std_price,
                                              "promised_date": promised, "work_order": pr.work_order} for line, item in pairs],
                       user, note=f"From requisition {pr.pr_no}", pr_no=pr.pr_no)
        for line, _ in pairs:
            line.po_no = po.po_no
        orders.append(po)
    pr.status = "CONVERTED"
    return orders


# --- Purchase orders ---


def create_po(session: Session, vendor_id: str, lines: list, user: str, note: str = "", pr_no: str | None = None,
              created_on: str | None = None, po_no: str | None = None) -> ProcOrder:
    """A DRAFT purchase order. `lines` holds dicts of item_code, qty, unit_price, promised_date and optionally work_order."""
    vendor = get_vendor(session, vendor_id)
    if not vendor.active:
        raise LedgerError(f"{vendor.name} is not an active vendor.")
    if not lines:
        raise LedgerError("A purchase order needs at least one line.")
    po = ProcOrder(po_no=po_no or next_no(session, ProcOrder.po_no, "PO-", 4500001), vendor_id=vendor_id, pr_no=pr_no,
                   created_on=created_on or today(), buyer=user, status="DRAFT", note=note)
    for line in lines:
        get_item(session, line["item_code"])
        if line["qty"] <= 0 or line["unit_price"] <= 0:
            raise LedgerError(f"{line['item_code']}: quantity and price must be above zero.")
        po.lines.append(ProcOrderLine(item_code=line["item_code"], qty=float(line["qty"]), unit_price=money(line["unit_price"]),
                                      promised_date=line["promised_date"], work_order=line.get("work_order") or None))
    session.add(po)
    session.flush()
    return po


def approval_refusal(po: ProcOrder, role: str) -> str | None:
    """Why this person may not approve this order, or None when they may. Above the limit only the admin approves."""
    if role not in ("reviewer", "admin"):
        return "Your role does not allow approving purchase orders."
    if po_value(po) > APPROVAL_LIMIT and role != "admin":
        return (f"Purchase orders above {inr(APPROVAL_LIMIT)} need an admin to approve; "
                f"{po.po_no} is worth {inr(po_value(po))}.")
    return None


def approve_po(po: ProcOrder, user: str, role: str) -> None:
    if po.status != "DRAFT":
        raise StateError(f"{po.po_no} is {po.status}; only a draft order can be approved.")
    refusal = approval_refusal(po, role)
    if refusal:
        error = StateError(refusal)
        error.status = 403
        raise error
    po.status, po.approved_by = "APPROVED", user


def send_po(po: ProcOrder) -> None:
    """shortcut: simulated; nothing leaves the system. A real install would e-mail or EDI the order to the vendor."""
    if po.status != "APPROVED":
        raise StateError(f"{po.po_no} is {po.status}; only an approved order can be sent.")
    po.status = "SENT"


# --- The 3-way match: purchase order, goods receipt, vendor bill ---


def three_way_match(ordered: dict, accepted: dict, earlier: dict, billed: list) -> dict:
    """Compare a bill with the order and with what was accepted at the gate.

    ordered:  item_code -> (qty, unit_price) on the purchase order
    accepted: item_code -> quantity accepted on goods receipts so far
    earlier:  item_code -> quantity already on other bills for this order (rejected bills excluded)
    billed:   the bill's lines, dicts of item_code, qty, unit_price

    A line matches when everything billed so far for the item is no more than was accepted, and the price is
    within ±2% of the PO price.
    """
    lines, notes, so_far = [], [], dict(earlier)
    for bill in billed:
        code = bill["item_code"]
        if code not in ordered:
            lines.append({"item_code": code, "po_qty": 0, "po_price": None, "received_qty": 0, "invoiced_qty": bill["qty"],
                          "invoiced_price": bill["unit_price"], "qty_ok": False, "price_ok": False, "price_variance_pct": None})
            notes.append(f"{code} is not on the purchase order.")
            continue
        po_qty, po_price = ordered[code]
        got = accepted.get(code, 0.0)
        before = so_far.get(code, 0.0)
        so_far[code] = before + bill["qty"]
        variance = round((bill["unit_price"] - po_price) / po_price * 100, 2)
        qty_ok, price_ok = so_far[code] <= got + EPS, abs(variance) <= PRICE_TOLERANCE_PCT + 1e-9
        lines.append({"item_code": code, "po_qty": po_qty, "po_price": po_price, "received_qty": got, "invoiced_qty": bill["qty"],
                      "invoiced_price": bill["unit_price"], "qty_ok": qty_ok, "price_ok": price_ok, "price_variance_pct": variance})
        if not qty_ok:
            earlier_text = f" (plus {qty_text(before)} on earlier bills)" if before > EPS else ""
            notes.append(f"{code}: {qty_text(bill['qty'])} billed{earlier_text} but only {qty_text(got)} accepted at the gate.")
        if not price_ok:
            notes.append(f"{code}: billed at {inr(bill['unit_price'])}, {abs(variance):.1f}% {'above' if variance > 0 else 'below'} "
                         f"the PO price of {inr(po_price)} (tolerance ±{PRICE_TOLERANCE_PCT:g}%).")
    ok = bool(lines) and all(line["qty_ok"] and line["price_ok"] for line in lines)
    if ok:
        notes.append("Quantity and price agree with the order and the goods receipt.")
    return {"ok": ok, "lines": lines, "notes": notes}


def match_inputs(session: Session, po: ProcOrder, exclude_inv: str | None = None) -> tuple[dict, dict, dict]:
    """What the match compares against: ordered quantities and prices, accepted quantities, and earlier bills."""
    ordered = {}
    for line in po.lines:
        qty, price = ordered.get(line.item_code, (0.0, line.unit_price))
        # shortcut: two lines for one item at different prices are matched against their quantity-weighted price
        ordered[line.item_code] = (qty + line.qty, money((qty * price + line.qty * line.unit_price) / (qty + line.qty)))
    accepted = defaultdict(float)
    for code, qty in session.execute(select(GrnLine.item_code, GrnLine.qty_accepted).join(GoodsReceipt, GoodsReceipt.grn_no == GrnLine.grn_no)
                                     .where(GoodsReceipt.po_no == po.po_no)):
        accepted[code] += qty
    earlier = defaultdict(float)
    for code, qty in session.execute(select(VendorInvoiceLine.item_code, VendorInvoiceLine.qty)
                                     .join(VendorInvoice, VendorInvoice.inv_no == VendorInvoiceLine.inv_no)
                                     .where(VendorInvoice.po_no == po.po_no, VendorInvoice.status.in_(LIVE_INVOICE),
                                            VendorInvoice.inv_no != (exclude_inv or ""))):
        earlier[code] += qty
    return ordered, dict(accepted), dict(earlier)


def create_invoice(session: Session, po: ProcOrder, vendor_invoice_no: str, invoice_date: str, lines: list, user: str,
                   inv_no: str | None = None) -> VendorInvoice:
    """Enter a vendor bill against an order. It is matched at once: MATCHED, or EXCEPTION with the reasons."""
    if po.status in ("DRAFT", "CANCELLED"):
        raise StateError(f"{po.po_no} is {po.status}; a bill can be entered only against an approved order.")
    if not lines:
        raise LedgerError("A bill needs at least one line.")
    for line in lines:
        if line["qty"] <= 0 or line["unit_price"] <= 0:
            raise LedgerError(f"{line['item_code']}: quantity and price must be above zero.")
    vendor = get_vendor(session, po.vendor_id)
    match = three_way_match(*match_inputs(session, po), [{"item_code": l["item_code"], "qty": float(l["qty"]), "unit_price": money(l["unit_price"])} for l in lines])
    amount = money(sum(l["qty"] * money(l["unit_price"]) for l in lines))
    tax = money(amount * GST_RATE)
    invoice = VendorInvoice(inv_no=inv_no or next_no(session, VendorInvoice.inv_no, "VB-", year_series(6)),
                            vendor_invoice_no=vendor_invoice_no.strip(), vendor_id=vendor.vendor_id, po_no=po.po_no,
                            invoice_date=invoice_date, due_date=plus_days(invoice_date, vendor.payment_terms_days),
                            status="MATCHED" if match["ok"] else "EXCEPTION", match=match, amount=amount, tax=tax,
                            total=money(amount + tax),
                            lines=[VendorInvoiceLine(item_code=l["item_code"], qty=float(l["qty"]), unit_price=money(l["unit_price"])) for l in lines])
    session.add(invoice)
    session.flush()
    return invoice


def approve_invoice(invoice: VendorInvoice, user: str, reason: str) -> None:
    if invoice.status not in ("MATCHED", "EXCEPTION"):
        raise StateError(f"{invoice.inv_no} is {invoice.status}; only a matched bill or an exception can be approved.")
    if invoice.status == "EXCEPTION" and not reason:
        error = LedgerError("This bill failed the 3-way match: approving it needs a written reason.")
        error.status = 422
        raise error
    invoice.status, invoice.approved_by, invoice.approval_reason = "APPROVED", user, reason or None


def reject_invoice(invoice: VendorInvoice, user: str, reason: str) -> None:
    if invoice.status not in ("MATCHED", "EXCEPTION"):
        raise StateError(f"{invoice.inv_no} is {invoice.status}; only a bill not yet approved can be rejected.")
    if not reason:
        error = LedgerError("Rejecting a bill needs a written reason.")
        error.status = 422
        raise error
    invoice.status, invoice.approved_by, invoice.approval_reason = "REJECTED", user, reason
