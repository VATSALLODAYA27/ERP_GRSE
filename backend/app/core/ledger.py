"""The books: stock movements and journal entries for every event that moves material or money.

Each posting function writes the stock moves and one journal entry together, and every journal entry must
balance (debits equal credits) or nothing is written. Stock is valued at moving-average cost per item across
all stores, and a store's stock can never go below zero.

Postings:
- Opening stock:          Dr 1300 Inventory          / Cr 3000 Opening balance equity
- Goods receipt (GRN):    Dr 1300 Inventory          / Cr 2100 Goods received not invoiced, at the PO price
- Invoice approved:       Dr 2100 (PO price x qty), Dr 1400 Input GST, Dr/Cr 5200 price variance / Cr 2000 Payables
- Payment:                Dr 2000 Payables           / Cr 1000 Bank
- Issue to a work order:  Dr 1500 Work in progress   / Cr 1300 Inventory, at moving-average cost
- Adjustment:             Dr or Cr 1300 Inventory against 5300 Inventory adjustment
"""
import math
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Account, GoodsReceipt, GrnLine, Item, JournalEntry, JournalLine, Payment, ProcOrder, StockMove,
                      Store, VendorInvoice)

GST_RATE = 0.18  # shortcut: one GST rate for every item; real bills carry HSN-wise CGST/SGST/IGST
EPS = 1e-6  # quantities closer than this are equal

CHART = {
    "1000": ("Bank", "ASSET"),
    "1300": ("Inventory (raw materials and stores)", "ASSET"),
    "1400": ("Input GST", "ASSET"),
    "1500": ("Work in progress (ship construction)", "ASSET"),
    "2000": ("Accounts payable", "LIABILITY"),
    "2100": ("Goods received not invoiced (GRNI)", "LIABILITY"),
    "3000": ("Opening balance equity", "EQUITY"),
    "5200": ("Purchase price variance", "EXPENSE"),
    "5300": ("Inventory adjustment", "EXPENSE"),
}


class LedgerError(ValueError):
    """A posting that would break the books: unbalanced, more stock out than there is, a quantity that does not fit."""

    status = 400


class StateError(LedgerError):
    """The record is not in a state that allows this step (for example paying an invoice nobody approved)."""

    status = 409


def money(amount: float) -> float:
    return round(amount + 0.0, 2)


def inr(amount: float) -> str:
    """Rupees with Indian digit grouping, paise dropped: 1234567 -> ₹12,34,567."""
    digits = str(int(round(abs(amount))))
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if amount < 0 else "") + "₹" + ",".join(groups + [tail])


def qty_text(qty: float) -> str:
    return f"{qty:g}"


def today() -> str:
    return date.today().isoformat()


def plus_days(on_date: str, days: int) -> str:
    return (date.fromisoformat(on_date) + timedelta(days=days)).isoformat()


def next_no(session: Session, column, prefix: str, start: int) -> str:
    """The next number in a series such as PO-4500123: one more than the highest so far, and never below `start`.

    shortcut: two people saving at the same instant could pick the same number; the primary key then refuses the
    second save. A database sequence would avoid that once there are many users.
    """
    taken = [int(v[len(prefix):]) for v in session.scalars(select(column).where(column.like(f"{prefix}%"))) if v[len(prefix):].isdigit()]
    return f"{prefix}{max(taken + [start - 1]) + 1}"


def year_series(digits: int) -> int:
    """Where this year's series starts: 260001 for six digits in 2026, 2600001 for seven."""
    return int(f"{date.today():%y}" + "0" * (digits - 3) + "1")


def ensure_chart(session: Session) -> None:
    for code, (name, kind) in CHART.items():
        if session.get(Account, code) is None:
            session.add(Account(code=code, name=name, type=kind))


def post(session: Session, on_date: str, source_type: str, source_no: str, narration: str, user: str, lines: list) -> JournalEntry:
    """Write one journal entry. `lines` holds (account_code, debit, credit, vendor_id, item_code).

    Refuses an entry whose debits and credits differ by a paisa or more.
    """
    ensure_chart(session)
    rows = []
    for account, debit, credit, vendor_id, item_code in lines:
        debit, credit = money(debit), money(credit)
        if debit < 0 or credit < 0:
            raise LedgerError(f"A journal line cannot be negative (account {account}).")
        if account not in CHART:
            raise LedgerError(f"Account {account} is not in the chart of accounts.")
        if debit or credit:
            rows.append(JournalLine(account_code=account, debit=debit, credit=credit, vendor_id=vendor_id, item_code=item_code))
    total_debit, total_credit = money(sum(r.debit for r in rows)), money(sum(r.credit for r in rows))
    if not rows or abs(total_debit - total_credit) >= 0.005:
        raise LedgerError(f"The journal entry for {source_type} {source_no} does not balance: debit {total_debit}, credit {total_credit}.")
    entry = JournalEntry(je_no=next_no(session, JournalEntry.je_no, "JE-", year_series(7)), on_date=on_date, source_type=source_type,
                         source_no=source_no, narration=narration, created_by=user, lines=rows)
    session.add(entry)
    session.flush()
    return entry


# --- Stock ---


def get_item(session: Session, item_code: str) -> Item:
    item = session.get(Item, item_code)
    if item is None:
        raise LedgerError(f"Item {item_code} is not in the item master.")
    return item


def get_store(session: Session, store_code: str) -> Store:
    store = session.get(Store, store_code)
    if store is None:
        raise LedgerError(f"Store {store_code} does not exist.")
    return store


def stock(session: Session, item_code: str, store_code: str | None = None) -> tuple[float, float]:
    """(quantity, value) on hand for an item, in one store or across all of them."""
    query = select(func.coalesce(func.sum(StockMove.qty), 0.0), func.coalesce(func.sum(StockMove.value), 0.0)).where(StockMove.item_code == item_code)
    if store_code:
        query = query.where(StockMove.store_code == store_code)
    qty, value = session.execute(query).one()
    return float(qty), float(value)


def average_cost(session: Session, item: Item) -> float:
    """Moving-average cost: stock value over stock quantity, across every store.

    shortcut: one average per item for the whole yard, not per store; and with no stock left the standard price is used.
    """
    qty, value = stock(session, item.item_code)
    return value / qty if qty > EPS else item.std_price


def move(session: Session, on_date: str, item_code: str, store_code: str, kind: str, qty: float, value: float,
         ref_type: str, ref_no: str, user: str, work_order: str | None = None, note: str = "") -> StockMove:
    row = StockMove(on_date=on_date, item_code=item_code, store_code=store_code, kind=kind, qty=qty,
                    unit_cost=money(abs(value / qty)) if qty else 0.0, value=money(value), ref_type=ref_type, ref_no=ref_no,
                    work_order=work_order, note=note, created_by=user)
    session.add(row)
    session.flush()
    return row


def take_out(session: Session, item: Item, store_code: str, qty: float, what: str) -> float:
    """The value of `qty` leaving a store at moving-average cost. Refuses to take out more than the store holds."""
    in_store, _ = stock(session, item.item_code, store_code)
    if qty > in_store + EPS:
        raise LedgerError(f"Only {qty_text(round(in_store, 3))} {item.uom} of {item.item_code} in {store_code}; cannot {what} {qty_text(qty)}. "
                          "Stock cannot go below zero.")
    total_qty, total_value = stock(session, item.item_code)
    if abs(qty - total_qty) < EPS:
        return money(total_value)  # the last of it carries whatever value is left, so no paise linger on an empty item
    return money(qty * average_cost(session, item))


def post_opening(session: Session, item_code: str, store_code: str, qty: float, unit_cost: float, on_date: str, user: str) -> StockMove:
    item, _ = get_item(session, item_code), get_store(session, store_code)
    if qty <= 0 or unit_cost <= 0:
        raise LedgerError("Opening stock needs a quantity and a cost above zero.")
    value = money(qty * unit_cost)
    ref = f"OPEN-{item_code}-{store_code}"
    row = move(session, on_date, item_code, store_code, "OPENING", qty, value, "OPENING", ref, user, note="Opening balance")
    post(session, on_date, "OPENING", ref, f"Opening stock {qty_text(qty)} {item.uom} {item_code} in {store_code}", user,
         [("1300", value, 0, None, item_code), ("3000", 0, value, None, item_code)])
    return row


def post_issue(session: Session, item_code: str, store_code: str, qty: float, work_order: str, user: str,
               note: str = "", on_date: str | None = None) -> StockMove:
    """Issue stock to a work order: it leaves the store at moving-average cost and becomes ship construction work in progress."""
    item, _ = get_item(session, item_code), get_store(session, store_code)
    if qty <= 0:
        raise LedgerError("The quantity to issue must be above zero.")
    on_date = on_date or today()
    value = take_out(session, item, store_code, qty, "issue")
    ref = next_no(session, StockMove.ref_no, "ISS-", year_series(6))
    row = move(session, on_date, item_code, store_code, "ISSUE", -qty, -value, "ISSUE", ref, user, work_order, note)
    post(session, on_date, "ISSUE", ref, f"Issue {qty_text(qty)} {item.uom} {item_code} from {store_code} to {work_order}", user,
         [("1500", value, 0, None, item_code), ("1300", 0, value, None, item_code)])
    return row


def post_transfer(session: Session, item_code: str, from_store: str, to_store: str, qty: float, user: str,
                  note: str = "", on_date: str | None = None) -> list[StockMove]:
    """Move stock between stores. The value stays in the same account, so no journal entry is needed."""
    item, _, _ = get_item(session, item_code), get_store(session, from_store), get_store(session, to_store)
    if from_store == to_store:
        raise LedgerError("Choose two different stores.")
    if qty <= 0:
        raise LedgerError("The quantity to transfer must be above zero.")
    on_date = on_date or today()
    value = take_out(session, item, from_store, qty, "transfer")
    ref = next_no(session, StockMove.ref_no, "TRF-", year_series(6))
    return [move(session, on_date, item_code, from_store, "TRANSFER_OUT", -qty, -value, "TRANSFER", ref, user, note=note),
            move(session, on_date, item_code, to_store, "TRANSFER_IN", qty, value, "TRANSFER", ref, user, note=note)]


def post_adjust(session: Session, item_code: str, store_code: str, qty: float, user: str, note: str = "",
                on_date: str | None = None) -> StockMove:
    """Correct the stock after a count. A positive quantity adds stock, a negative one writes it off."""
    item, _ = get_item(session, item_code), get_store(session, store_code)
    if abs(qty) < EPS:
        raise LedgerError("An adjustment needs a quantity other than zero.")
    on_date = on_date or today()
    value = money(qty * average_cost(session, item)) if qty > 0 else -take_out(session, item, store_code, -qty, "write off")
    ref = next_no(session, StockMove.ref_no, "ADJ-", year_series(6))
    row = move(session, on_date, item_code, store_code, "ADJUST", qty, value, "ADJUST", ref, user, note=note)
    amount = abs(value)
    lines = ([("1300", amount, 0, None, item_code), ("5300", 0, amount, None, item_code)] if qty > 0
             else [("5300", amount, 0, None, item_code), ("1300", 0, amount, None, item_code)])
    post(session, on_date, "ADJUST", ref, f"Stock adjustment {qty:+g} {item.uom} {item_code} in {store_code}. {note}".strip(), user, lines)
    return row


# --- Purchase to pay ---

RECEIVABLE = ("APPROVED", "SENT", "PART_RECEIVED")


def post_receipt(session: Session, po: ProcOrder, store_code: str, received_on: str, lines: list, user: str,
                 grn_no: str | None = None) -> GoodsReceipt:
    """Record goods arriving against a purchase order. `lines` holds dicts of line_id, qty_received, qty_accepted, reject_reason.

    Accepted goods go into the store at the PO price and owe the vendor through GRNI until the bill arrives.
    Rejected goods go back to the vendor and stay open on the order.
    """
    if po.status not in RECEIVABLE:
        raise StateError(f"{po.po_no} is {po.status}; goods can be received only against an approved or sent order.")
    get_store(session, store_code)
    by_id = {line.id: line for line in po.lines}
    grn = GoodsReceipt(grn_no=grn_no or next_no(session, GoodsReceipt.grn_no, "GRN-", year_series(6)), po_no=po.po_no,
                       received_on=received_on, store_code=store_code, received_by=user)
    journal = []
    for given in lines:
        line = by_id.get(given["line_id"])
        if line is None:
            raise LedgerError(f"Line {given['line_id']} is not on {po.po_no}.")
        received, accepted = float(given["qty_received"]), float(given["qty_accepted"])
        if received <= 0 and accepted <= 0:
            continue
        if accepted < 0 or accepted > received + EPS:
            raise LedgerError(f"{line.item_code}: the accepted quantity must be between zero and the quantity received.")
        still_open = line.qty - line.received_qty
        if accepted > still_open + EPS:
            raise LedgerError(f"{line.item_code}: accepting {qty_text(accepted)} would exceed the {qty_text(round(still_open, 3))} still open on the order.")
        rejected = round(received - accepted, 6)
        if rejected > EPS and not (given.get("reject_reason") or "").strip():
            raise LedgerError(f"{line.item_code}: say why {qty_text(rejected)} were rejected.")
        grn.lines.append(GrnLine(po_line_id=line.id, item_code=line.item_code, qty_received=received, qty_accepted=accepted,
                                 qty_rejected=rejected, reject_reason=(given.get("reject_reason") or "").strip()))
        line.received_qty = round(line.received_qty + accepted, 6)
        if accepted > EPS:
            value = money(accepted * line.unit_price)
            move(session, received_on, line.item_code, store_code, "RECEIPT", accepted, value, "GRN", grn.grn_no, user, line.work_order)
            journal += [("1300", value, 0, None, line.item_code), ("2100", 0, value, po.vendor_id, line.item_code)]
    if not grn.lines:
        raise LedgerError("Nothing was received: enter a received quantity on at least one line.")
    session.add(grn)
    session.flush()
    if journal:
        post(session, received_on, "GRN", grn.grn_no, f"Goods received against {po.po_no} into {store_code}", user, journal)
    if all(line.received_qty >= line.qty - EPS for line in po.lines):
        po.status = "RECEIVED"
    elif any(line.received_qty > EPS for line in po.lines):
        po.status = "PART_RECEIVED"
    return grn


def post_invoice_approval(session: Session, invoice: VendorInvoice, po: ProcOrder, user: str, on_date: str | None = None) -> JournalEntry:
    """Book an approved vendor bill: clear GRNI at the PO price, claim the GST, and put any price difference to variance."""
    totals = {}
    for line in po.lines:
        qty, value = totals.get(line.item_code, (0.0, 0.0))
        totals[line.item_code] = (qty + line.qty, value + line.qty * line.unit_price)
    prices = {code: money(value / qty) for code, (qty, value) in totals.items()}  # the same weighted price the match uses
    lines = []
    cleared = 0.0
    for bill_line in invoice.lines:
        po_price = prices.get(bill_line.item_code, bill_line.unit_price)  # an item not on the order has no PO price: all of it is the bill's
        value = money(bill_line.qty * po_price)
        cleared += value
        lines.append(("2100", value, 0, invoice.vendor_id, bill_line.item_code))
    variance = money(invoice.total - money(cleared) - invoice.tax)  # whatever is left balances the entry, so rounding never breaks it
    lines.append(("1400", invoice.tax, 0, None, None))
    lines.append(("5200", variance, 0, invoice.vendor_id, None) if variance >= 0 else ("5200", 0, -variance, invoice.vendor_id, None))
    lines.append(("2000", 0, invoice.total, invoice.vendor_id, None))
    return post(session, on_date or today(), "INVOICE", invoice.inv_no,
                f"Vendor bill {invoice.vendor_invoice_no} for {po.po_no} approved", user, lines)


def post_payment(session: Session, invoice: VendorInvoice, po: ProcOrder, user: str, mode: str = "NEFT",
                 paid_on: str | None = None, pay_no: str | None = None) -> Payment:
    """Pay an approved bill in full from the bank. When the last bill of a fully received order is paid, the order closes."""
    if invoice.status != "APPROVED":
        raise StateError(f"{invoice.inv_no} is {invoice.status}; only an approved bill can be paid.")
    paid_on = paid_on or today()
    payment = Payment(pay_no=pay_no or next_no(session, Payment.pay_no, "PAY-", year_series(6)), inv_no=invoice.inv_no,
                      vendor_id=invoice.vendor_id, paid_on=paid_on, amount=invoice.total, mode=mode, paid_by=user)
    session.add(payment)
    session.flush()
    post(session, paid_on, "PAYMENT", payment.pay_no, f"{mode} payment of bill {invoice.vendor_invoice_no} ({invoice.inv_no})", user,
         [("2000", invoice.total, 0, invoice.vendor_id, None), ("1000", 0, invoice.total, None, None)])
    invoice.status = "PAID"
    session.flush()
    unpaid = session.scalars(select(VendorInvoice).where(VendorInvoice.po_no == po.po_no,
                                                         VendorInvoice.status.in_(("MATCHED", "EXCEPTION", "APPROVED")))).first()
    if po.status == "RECEIVED" and unpaid is None:
        po.status = "CLOSED"
    return payment


def journal_rows(session: Session, entries) -> list:
    """Journal entries as plain data for the screens, with account names on the lines."""
    names = {a.code: a.name for a in session.scalars(select(Account))}
    return [{"je_no": e.je_no, "on_date": e.on_date, "source_type": e.source_type, "source_no": e.source_no, "narration": e.narration,
             "created_by": e.created_by, "total": money(sum(l.debit for l in e.lines)),
             "lines": [{"account_code": l.account_code, "account_name": names.get(l.account_code, l.account_code), "debit": l.debit,
                        "credit": l.credit, "vendor_id": l.vendor_id, "item_code": l.item_code} for l in e.lines]}
            for e in entries]


def vendor_account(session: Session, vendor_id: str) -> dict:
    """The vendor's payables account line by line, oldest first, with the running balance owed (credit minus debit)."""
    rows = session.execute(
        select(JournalEntry.on_date, JournalEntry.je_no, JournalEntry.source_type, JournalEntry.source_no, JournalEntry.narration,
               JournalLine.debit, JournalLine.credit)
        .join(JournalLine, JournalLine.je_no == JournalEntry.je_no)
        .where(JournalLine.account_code == "2000", JournalLine.vendor_id == vendor_id)
        .order_by(JournalEntry.on_date, JournalEntry.je_no, JournalLine.id))
    balance, entries = 0.0, []
    for on_date, je_no, source_type, source_no, narration, debit, credit in rows:
        balance = money(balance + credit - debit)
        entries.append({"on_date": on_date, "je_no": je_no, "source_type": source_type, "source_no": source_no,
                        "narration": narration, "debit": debit, "credit": credit, "balance": balance})
    return {"balance": balance, "entries": entries}


def lots(need: float, lot: float) -> float:
    """`need` rounded up to whole lots of `lot` (the reorder quantity)."""
    return math.ceil(need / lot - 1e-9) * lot if lot > 0 else need
