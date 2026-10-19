"""Load the DEMO ERP data: vendors, items, stores, opening stock, eight months of purchase history, open orders, bills,
requisitions and stock issues. Every vendor, price and figure is invented and marked (mock); no real company is named.

Dates count back from today, so the demo always looks current, and a fixed random seed gives the same data every time.
The history is booked through the real posting functions, so the ledger balances exactly as it would in use.
Running it again changes nothing once the data is there; --reset deletes the ERP records (never Sentinel's checks,
the register or the audit log) and loads them afresh.
Run from backend/ after load_extract:  python -m scripts.seed_erp [--reset]
"""
import random
import sys
from datetime import date, timedelta

from sqlalchemy import delete, func, select

from app import models
from app.core import intel, ledger, procure
from app.db import SessionLocal, migrate

BUYER, STOREKEEPER, APPROVER, ADMIN, SETUP = "engineer", "engineer2", "reviewer", "Admin_123", "demo-setup"

STORES = [
    ("MW-STEEL", "Main Works steel stockyard", "Main Works, Kolkata (mock)"),
    ("MW-GEN", "Main Works general stores", "Main Works, Kolkata (mock)"),
    ("RBD-STEEL", "Rajabagan steel yard", "Rajabagan Dockyard, Kolkata (mock)"),
    ("FOU-OUTFIT", "Fitting-out unit outfitting store", "Fitting-out unit, Kolkata (mock)"),
]

# vendor_id, name, city, category, MSME, payment terms (days), lead time (days), delivery behaviour
VENDORS = [
    ("V-1001", "Rupnarayan Steel Stockists (mock)", "Kolkata", "Steel plate", False, 45, 30, "good"),
    ("V-1002", "Ajay River Rolling Works (mock)", "Durgapur", "Sections", False, 30, 30, "late"),
    ("V-1003", "Kharkai Plate Mills (mock)", "Jamshedpur", "Steel plate", False, 45, 35, "rejects"),
    ("V-1004", "Rushikonda Pipe & Fittings (mock)", "Visakhapatnam", "Pipes & fittings", False, 30, 28, "fair"),
    ("V-1005", "Mula-Mutha Valves (mock)", "Pune", "Valves", False, 45, 42, "fair"),
    ("V-1006", "Adyar Cable Industries (mock)", "Chennai", "Electrical", False, 30, 21, "good"),
    ("V-1007", "Worli Marine Outfitters (mock)", "Mumbai", "Outfitting", False, 45, 35, "fair"),
    ("V-1008", "Barasat Weld Consumables (mock)", "Kolkata", "Consumables", True, 30, 10, "good"),
    ("V-1009", "Salkia Marine Coatings (mock)", "Kolkata", "Consumables", True, 30, 14, "fair"),
    ("V-1010", "Benachity Sections (mock)", "Durgapur", "Sections", True, 30, 21, "good"),
    ("V-1011", "Hinjewadi Flow Controls (mock)", "Pune", "Valves", True, 45, 35, "fair"),
    ("V-1012", "Ennore Electricals (mock)", "Chennai", "Electrical", True, 30, 18, "fair"),
]
GST_STATE = {"Kolkata": "19", "Durgapur": "19", "Jamshedpur": "20", "Visakhapatnam": "37", "Pune": "27", "Mumbai": "27", "Chennai": "33"}
# Days late against the promised date for each vendor's successive deliveries (taken in turn, so every run is the same).
DELAYS = {"good": [0, -1, 0, 0, -2, 0, 1, 0], "late": [6, 9, 14, 0, 18, 22, 11], "rejects": [0, 3, 5, 0, 8, 2, 6],
          "fair": [0, 0, 3, -1, 0, 6, 0, 0, 2, 0]}

# item_code, description, category, uom, grade, standard price, reorder level, reorder qty, lead time, preferred vendor,
# critical, store, opening quantity. The first ten are the bill-of-materials parts on Sentinel's drawings.
ITEMS = [
    ("PL-101-01", "Deck plate AH36 12 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 185000, 2, 2, 30, "V-1001", False, "MW-STEEL", 6),
    ("HP-101-02", "HP stiffener 160x8 AH36 (12 m)", "Sections", "NOS", "AH36", 18500, 4, 6, 30, "V-1002", False, "MW-STEEL", 8),
    ("FB-101-03", "Flat bar 100x10 grade A (6 m)", "Sections", "NOS", "A", 6800, 4, 8, 21, "V-1010", False, "MW-STEEL", 10),
    ("BK-101-04", "Bracket 150x150 AH36 10 mm", "Steel plate", "NOS", "AH36", 950, 4, 20, 21, "V-1010", False, "MW-STEEL", 12),
    ("PL-102-01", "Bulkhead plate AH36 8 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 125000, 1, 2, 35, "V-1003", False, "MW-STEEL", 1),
    ("HP-102-02", "HP stiffener 140x7 AH36 (12 m)", "Sections", "NOS", "AH36", 15200, 5, 10, 30, "V-1002", False, "MW-STEEL", 9),
    ("PL-103-01", "Shell plate DH36 14 mm (2.5 x 10 m)", "Steel plate", "NOS", "DH36", 235000, 3, 3, 35, "V-1003", True, "MW-STEEL", 4),
    ("HP-103-02", "HP stiffener 200x10 DH36 (12 m)", "Sections", "NOS", "DH36", 26500, 6, 10, 30, "V-1002", False, "MW-STEEL", 10),
    ("PL-210-01", "Seating top plate AH36 20 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 310000, 0, 2, 30, "V-1001", False, "MW-STEEL", 0),
    ("PL-210-02", "Girder web plate AH36 12 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 180000, 0, 2, 30, "V-1001", False, "MW-STEEL", 1),
    ("PL-AH36-06", "Plate AH36 6 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 95000, 6, 10, 35, "V-1003", False, "RBD-STEEL", 14),
    ("PL-AH36-10", "Plate AH36 10 mm (2.5 x 10 m)", "Steel plate", "NOS", "AH36", 158000, 6, 10, 35, "V-1003", False, "RBD-STEEL", 9),
    ("PL-DH36-16", "Plate DH36 16 mm (2.5 x 10 m)", "Steel plate", "NOS", "DH36", 262000, 4, 6, 30, "V-1001", True, "MW-STEEL", 5),
    ("ST-ANG-75", "Equal angle 75x75x8 (6 m)", "Sections", "NOS", "E250", 7400, 20, 40, 21, "V-1010", False, "MW-STEEL", 46),
    ("ST-CH-150", "Channel ISMC 150 (6 m)", "Sections", "NOS", "E250", 14800, 10, 20, 30, "V-1002", False, "MW-STEEL", 14),
    ("ST-TB-250", "Tee bar 250x100 AH36 (12 m)", "Sections", "NOS", "AH36", 21000, 6, 10, 30, "V-1002", False, "RBD-STEEL", 4),
    ("PP-SCH40-50", "Seamless pipe 50 NB Sch 40 (6 m)", "Pipes & fittings", "NOS", "A106 Gr B", 4200, 30, 50, 28, "V-1004", False, "MW-GEN", 62),
    ("PP-SCH80-100", "Seamless pipe 100 NB Sch 80 (6 m)", "Pipes & fittings", "NOS", "A106 Gr B", 13500, 12, 24, 28, "V-1004", False, "MW-GEN", 18),
    ("PP-CUNI-80", "Cu-Ni 90/10 pipe 80 NB (6 m)", "Pipes & fittings", "NOS", "CuNi 90/10", 46000, 8, 20, 45, "V-1004", True, "MW-GEN", 10),
    ("PF-ELB-100", "Elbow 90 deg 100 NB", "Pipes & fittings", "NOS", "A234 WPB", 1150, 40, 100, 21, "V-1004", False, "MW-GEN", 120),
    ("PF-FLG-100", "Weld-neck flange 100 NB PN16", "Pipes & fittings", "NOS", "A105", 2350, 30, 60, 21, "V-1004", False, "MW-GEN", 22),
    ("VL-GAT-100", "Gate valve 100 NB cast steel", "Valves", "NOS", "WCB", 38000, 4, 6, 42, "V-1005", False, "MW-GEN", 7),
    ("VL-BFY-150", "Butterfly valve 150 NB", "Valves", "NOS", "Ductile iron", 27500, 4, 6, 35, "V-1011", False, "MW-GEN", 9),
    ("VL-NRV-80", "Non-return valve 80 NB", "Valves", "NOS", "Bronze", 19800, 4, 6, 35, "V-1011", False, "MW-GEN", 3),
    ("VL-SEA-200", "Sea chest valve 200 NB", "Valves", "NOS", "WCB", 145000, 2, 2, 42, "V-1005", True, "MW-GEN", 0),
    ("EL-CAB-3C25", "Marine cable 3C x 25 sq mm (100 m drum)", "Electrical", "DRUM", "IEC 60092", 68000, 3, 6, 21, "V-1006", False, "MW-GEN", 5),
    ("EL-CAB-2C2-5", "Marine cable 2C x 2.5 sq mm (100 m drum)", "Electrical", "DRUM", "IEC 60092", 9800, 10, 20, 21, "V-1006", False, "MW-GEN", 26),
    ("EL-JB-IP56", "Junction box IP56", "Electrical", "NOS", "IP56", 3400, 20, 50, 18, "V-1012", False, "MW-GEN", 8),
    ("EL-LT-LED", "LED bulkhead light fitting", "Electrical", "NOS", "IP66", 5600, 20, 40, 18, "V-1012", False, "MW-GEN", 34),
    ("WC-E7018-4", "Electrode E7018 4 mm (5 kg pack)", "Consumables", "PACK", "AWS E7018", 1450, 80, 100, 10, "V-1008", False, "MW-GEN", 60),
    ("WC-FCAW-12", "Flux-cored wire E71T-1 1.2 mm (15 kg spool)", "Consumables", "SPOOL", "AWS E71T-1", 4900, 30, 40, 10, "V-1008", True, "MW-GEN", 34),
    ("WC-ARGON", "Argon cylinder 47 L", "Consumables", "CYL", "99.99%", 3200, 15, 30, 7, "V-1008", False, "MW-GEN", 18),
    ("PT-EPX-PRM", "Epoxy primer (20 L pail)", "Consumables", "PAIL", "Epoxy", 11500, 20, 40, 14, "V-1009", False, "MW-GEN", 26),
    ("PT-AF-RED", "Antifouling paint red (20 L pail)", "Consumables", "PAIL", "SPC antifouling", 24000, 10, 20, 21, "V-1009", False, "MW-GEN", 6),
    ("OF-LAD-SS", "Stainless steel vertical ladder (3 m)", "Outfitting", "NOS", "SS316", 18500, 4, 4, 35, "V-1007", False, "FOU-OUTFIT", 6),
    ("OF-HAT-600", "Watertight hatch 600x600", "Outfitting", "NOS", "Steel", 72000, 2, 4, 35, "V-1007", True, "FOU-OUTFIT", 3),
    ("OF-DOR-WT", "Watertight door 1600x600", "Outfitting", "NOS", "Steel", 240000, 1, 2, 42, "V-1007", False, "FOU-OUTFIT", 2),
    ("OF-BOL-300", "Mooring bollard 300 mm", "Outfitting", "NOS", "Cast steel", 56000, 2, 4, 35, "V-1007", False, "FOU-OUTFIT", 4),
    ("OF-FND-TYR", "Rubber fender D-type (1 m)", "Outfitting", "NOS", "EPDM", 9500, 10, 20, 28, "V-1007", False, "FOU-OUTFIT", 7),
    ("OF-RAIL-SS", "Stainless handrail (6 m)", "Outfitting", "NOS", "SS316", 7800, 10, 20, 28, "V-1007", False, "FOU-OUTFIT", 24),
]
BOM_PARTS = {row[0] for row in ITEMS[:10]}
HISTORY_WORK_ORDERS = ["WO-23944", "WO-23951", "WO-23967", "WO-23978", "WO-23990"]  # earlier hulls' work orders (mock)
REJECT_REASON = "Surface pitting beyond tolerance (mock)"
OPENING_BANK = 60_000_000  # ₹6 crore in the bank when the books open (mock)

# Open orders: po_no, vendor, created (days ago), [(item, qty, promised in days, work order)], status.
# The numbers PO-4500123/124/126/127/128 match the ERP extract that Sentinel's impact view shows.
OPEN_ORDERS = [
    ("PO-4500119", "V-1003", 42, [("PL-AH36-10", 10, -7, None)], "SENT"),
    ("PO-4500120", "V-1006", 1, [("EL-CAB-3C25", 6, 20, None)], "SENT"),
    ("PO-4500121", "V-1002", 10, [("ST-CH-150", 20, 4, None), ("ST-TB-250", 10, 4, None)], "SENT"),
    ("PO-4500122", "V-1005", 48, [("VL-SEA-200", 2, -6, None)], "SENT"),
    ("PO-4500123", "V-1001", 18, [("PL-101-01", 4, 12, "WO-24019")], "SENT"),
    ("PO-4500124", "V-1002", 27, [("HP-101-02", 6, 3, "WO-24019")], "SENT"),
    ("PO-4500126", "V-1003", 30, [("PL-102-01", 2, 5, "WO-24020")], "SENT"),
    ("PO-4500127", "V-1003", 10, [("PL-103-01", 3, 25, None)], "APPROVED"),
    ("PO-4500128", "V-1001", 5, [("PL-210-01", 2, 30, "WO-24022")], "APPROVED"),
    ("PO-4500129", "V-1008", 3, [("WC-FCAW-12", 40, 7, None)], "SENT"),
    ("PO-4500130", "V-1007", 26, [("OF-HAT-600", 4, 9, None)], "SENT"),
    ("PO-4500131", "V-1004", 6, [("PP-CUNI-80", 20, 22, None)], "APPROVED"),
    ("PO-4500132", "V-1004", 4, [("PP-CUNI-80", 18, 24, None)], "APPROVED"),
    ("PO-4500133", "V-1012", 2, [("EL-JB-IP56", 50, 16, None)], "DRAFT"),
    ("PO-4500134", "V-1001", 1, [("PL-DH36-16", 6, 29, None)], "DRAFT"),  # above ₹10,00,000: waits for the admin
]

ERP_TABLES = [models.AiFlag, models.AiFollowup, models.JournalLine, models.JournalEntry, models.Payment, models.VendorInvoiceLine,
              models.VendorInvoice, models.GrnLine, models.GoodsReceipt, models.StockMove, models.RequisitionLine, models.ProcOrderLine,
              models.ProcOrder, models.Requisition, models.Item, models.Store, models.Vendor, models.Account]


def ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def at_most_today(day: str) -> str:
    return min(day, date.today().isoformat())


class Seeder:
    def __init__(self, session):
        self.session, self.rng = session, random.Random(26)
        self.vendors = {v[0]: v for v in VENDORS}
        self.items = {i[0]: i for i in ITEMS}
        self.bill_count = {}
        self.deliveries = {}

    def delay(self, vendor_id: str) -> int:
        pattern = DELAYS[self.vendors[vendor_id][7]]
        n = self.deliveries.get(vendor_id, 0)
        self.deliveries[vendor_id] = n + 1
        return pattern[n % len(pattern)]

    # --- master data ---

    def masters(self):
        s = self.session
        ledger.ensure_chart(s)
        ledger.post(s, ago(250), "OPENING", "OPEN-BANK", "Opening bank balance (mock)", SETUP,
                    [("1000", OPENING_BANK, 0, None, None), ("3000", 0, OPENING_BANK, None, None)])
        for code, name, location in STORES:
            s.add(models.Store(store_code=code, name=name, location=location))
        for vid, name, city, category, msme, terms, lead, _ in VENDORS:
            s.add(models.Vendor(vendor_id=vid, name=name, city=city, category=category, gstin=f"{GST_STATE[city]}MOCK{vid[2:]}A1Z{vid[-1]}",
                                msme=msme, payment_terms_days=terms, lead_time_days=lead, active=True))
        s.flush()
        for code, desc, cat, uom, grade, price, level, lot, lead, vendor, critical, _, _ in ITEMS:
            s.add(models.Item(item_code=code, description=desc, category=cat, uom=uom, grade=grade, std_price=price, reorder_level=level,
                              reorder_qty=lot, lead_time_days=lead, preferred_vendor_id=vendor, critical=critical))
        s.flush()
        for code, *_, store, opening in ITEMS:
            if opening:
                ledger.post_opening(s, code, store, opening, self.items[code][5], ago(250), SETUP)

    # --- helpers that book one step through the real posting functions ---

    def order(self, po_no, vendor_id, created, lines, status="SENT"):
        po = procure.create_po(self.session, vendor_id, lines, BUYER, created_on=created, po_no=po_no)
        if status != "DRAFT":
            above_limit = procure.po_value(po) > procure.APPROVAL_LIMIT  # the admin approves those, as the limit requires
            procure.approve_po(po, ADMIN if above_limit else APPROVER, "admin" if above_limit else "reviewer")
        if status in ("SENT",):
            procure.send_po(po)
        return po

    def receive(self, po, on_date, quantities, rejects=None):
        """quantities: {line id: accepted}; rejects: {line id: rejected}. Goes into each item's home store."""
        rejects = rejects or {}
        by_store = {}
        for line in po.lines:
            if line.id in quantities or line.id in rejects:
                by_store.setdefault(self.items[line.item_code][11], []).append(line)
        grns = []
        for store, lines in by_store.items():
            grns.append(ledger.post_receipt(self.session, po, store, on_date, [
                {"line_id": l.id, "qty_received": quantities.get(l.id, 0) + rejects.get(l.id, 0), "qty_accepted": quantities.get(l.id, 0),
                 "reject_reason": REJECT_REASON if rejects.get(l.id) else ""} for l in lines], STOREKEEPER))
        return grns

    def bill_no(self, vendor_id, on_date):
        initials = "".join(w[0] for w in self.vendors[vendor_id][1].replace("(mock)", "").replace("&", "").split())
        self.bill_count[vendor_id] = self.bill_count.get(vendor_id, 100 + int(vendor_id[-2:]) * 7) + 1
        start = int(on_date[2:4]) if int(on_date[5:7]) >= 4 else int(on_date[2:4]) - 1
        return f"{initials}/{start}{start + 1}/{self.bill_count[vendor_id]:04d}"

    def bill(self, po, on_date, lines, number=None, approve=True, pay=True):
        s = self.session
        inv = procure.create_invoice(s, po, number or self.bill_no(po.vendor_id, on_date), on_date, lines, BUYER)
        if approve and inv.status == "MATCHED":
            approved_on = at_most_today(ledger.plus_days(on_date, 2))
            procure.approve_invoice(inv, APPROVER, "")
            ledger.post_invoice_approval(s, inv, po, APPROVER, approved_on)
            if pay and inv.due_date <= date.today().isoformat():
                ledger.post_payment(s, inv, po, APPROVER, "RTGS" if inv.total >= 200000 else "NEFT", inv.due_date)
        return inv

    def bill_as_received(self, po, on_date, **kw):
        accepted = {}
        for line in po.lines:
            accepted[line.item_code] = accepted.get(line.item_code, 0) + line.received_qty
        return self.bill(po, on_date, [{"item_code": l.item_code, "qty": accepted.pop(l.item_code), "unit_price": l.unit_price}
                                       for l in po.lines if l.item_code in accepted], **kw)

    def consume(self, po, on_date):
        """Issue what an order brought in to an earlier hull's work order, as the yard would have done."""
        for line in po.lines:
            order = self.rng.choice(HISTORY_WORK_ORDERS)
            line.work_order = order
            ledger.post_issue(self.session, line.item_code, self.items[line.item_code][11], line.received_qty, order, STOREKEEPER,
                              "Issued to production", on_date)

    # --- eight months of closed orders ---

    def history(self):
        sequence = [v[0] for v in VENDORS] * 3
        for k, vendor_id in enumerate(sequence):
            _, _, _, category, _, _, lead, behaviour = self.vendors[vendor_id]
            pool = [i[0] for i in ITEMS if i[9] == vendor_id and i[0] not in BOM_PARTS] or [i[0] for i in ITEMS if i[2] == category and i[0] not in BOM_PARTS]
            chosen = self.rng.sample(pool, min(len(pool), self.rng.choice([1, 1, 2])))
            created = ago(240 - round(k * 5.8))
            promised = ledger.plus_days(created, lead)
            lines = [{"item_code": code, "qty": self.items[code][7] * self.rng.choice([1, 1, 2]),
                      "unit_price": round(self.items[code][5] * self.rng.choice([0.97, 0.98, 1.0, 1.0, 1.02])), "promised_date": promised}
                     for code in chosen]
            po = self.order(f"PO-{4500081 + k}", vendor_id, created, lines)
            received_on = at_most_today(ledger.plus_days(promised, self.delay(vendor_id)))
            rejects = {l.id: 1 for l in po.lines if behaviour == "rejects" and l.qty >= 10 and self.rng.random() < 0.6}
            self.receive(po, received_on, {l.id: l.qty - rejects.get(l.id, 0) for l in po.lines}, rejects)
            last = received_on
            if rejects:  # the replacements arrive a week later
                last = at_most_today(ledger.plus_days(received_on, 7))
                self.receive(po, last, rejects)
            self.consume(po, at_most_today(ledger.plus_days(last, 3)))
            self.bill_as_received(po, at_most_today(ledger.plus_days(last, 2)))

        # Two recent closed orders with bills still to pay: one overdue, one due in three days.
        po = self.order("PO-4500117", "V-1007", ago(96), [{"item_code": "OF-BOL-300", "qty": 4, "unit_price": 56000, "promised_date": ago(61)},
                                                          {"item_code": "OF-RAIL-SS", "qty": 20, "unit_price": 7800, "promised_date": ago(61)}])
        self.receive(po, ago(61), {l.id: l.qty for l in po.lines})
        self.consume(po, ago(55))
        self.bill_as_received(po, ago(57), pay=False)  # due 12 days ago, not yet paid
        po = self.order("PO-4500118", "V-1006", ago(50), [{"item_code": "EL-CAB-2C2-5", "qty": 20, "unit_price": 9800, "promised_date": ago(29)}])
        self.receive(po, ago(29), {l.id: l.qty for l in po.lines})
        self.consume(po, ago(25))
        self.bill_as_received(po, ago(27), pay=False)  # due in 3 days

        # PO-4500125 from the extract: flat bars received for WO-24019, not yet billed.
        po = self.order("PO-4500125", "V-1010", ago(85), [{"item_code": "FB-101-03", "qty": 8, "unit_price": 6800, "promised_date": ago(64),
                                                           "work_order": "WO-24019"}])
        self.receive(po, ago(64), {l.id: l.qty for l in po.lines})

    # --- what is open today ---

    def open_orders(self):
        s = self.session
        orders = {}
        for po_no, vendor_id, created_ago, lines, status in OPEN_ORDERS:
            orders[po_no] = self.order(po_no, vendor_id, ago(created_ago), [
                {"item_code": code, "qty": qty, "unit_price": self.items[code][5], "promised_date": ago(-promised_in), "work_order": wo}
                for code, qty, promised_in, wo in lines], status)
        # Steel plates with lamination: 2 of 10 rejected at the gate, and the vendor billed all 10.
        po = orders["PO-4500119"]
        self.receive(po, ago(6), {po.lines[0].id: 8}, {po.lines[0].id: 2})
        po.lines[0].work_order = None
        self.bill(po, ago(4), [{"item_code": "PL-AH36-10", "qty": 10, "unit_price": 158000}])
        # Half of the bulkhead plates arrived early; the bill charges 6% over the order price.
        po = orders["PO-4500126"]
        self.receive(po, ago(3), {po.lines[0].id: 1})
        self.bill(po, ago(2), [{"item_code": "PL-102-01", "qty": 1, "unit_price": round(125000 * 1.06)}])
        # A paid bill from the welding consumables vendor, entered a second time.
        earlier = s.scalars(select(models.VendorInvoice).where(models.VendorInvoice.vendor_id == "V-1008", models.VendorInvoice.status == "PAID")
                            .order_by(models.VendorInvoice.invoice_date.desc())).first()
        self.bill(s.get(models.ProcOrder, earlier.po_no), ago(4), [{"item_code": l.item_code, "qty": l.qty, "unit_price": l.unit_price}
                                                                     for l in earlier.lines], number=earlier.vendor_invoice_no)

    def issues(self):
        """Steel issued to the hull work orders: WO-24018 and WO-24021 were released long ago; WO-24019/20 are being kitted."""
        s = self.session
        for code, qty, order, days in [("PL-101-01", 4, "WO-24018", 120), ("HP-101-02", 6, "WO-24018", 120), ("FB-101-03", 8, "WO-24018", 120),
                                       ("PL-103-01", 3, "WO-24021", 60), ("HP-103-02", 8, "WO-24021", 60),
                                       ("FB-101-03", 8, "WO-24019", 20), ("BK-101-04", 4, "WO-24019", 20), ("HP-101-02", 1, "WO-24019", 20),
                                       ("HP-102-02", 5, "WO-24020", 2), ("PL-102-01", 1, "WO-24020", 2)]:
            ledger.post_issue(s, code, self.items[code][11], qty, order, STOREKEEPER, "Kitting for the hull block", ago(days))

    def requisitions(self):
        s = self.session
        procure.create_requisition(s, [{"item_code": "PL-210-02", "qty": 4, "need_by": ago(-40)}], BUYER, work_order="WO-24022",
                                   note="Girder webs for the engine room seating (mock).", source="WORK_ORDER", created_on=ago(2))
        pr = procure.create_requisition(s, [{"item_code": "WC-E7018-4", "qty": 60, "need_by": ago(-12)},
                                            {"item_code": "PT-EPX-PRM", "qty": 10, "need_by": ago(-15)}], STOREKEEPER,
                                        note="Monthly consumables top-up (mock).", created_on=ago(6))
        procure.decide_requisition(pr, True, APPROVER)

    def run(self):
        self.masters()
        self.history()
        self.issues()
        self.open_orders()
        self.requisitions()
        added = intel.scan(self.session)
        self.session.commit()
        return added


def reset(session) -> None:
    for model in ERP_TABLES:
        session.execute(delete(model))
    session.commit()


def seed(session, fresh: bool = False) -> dict:
    """Load the demo ERP data unless it is already there. Returns what was loaded (empty when nothing was done)."""
    if fresh:
        reset(session)
    if session.scalar(select(func.count()).select_from(models.Vendor)):
        return {}
    added = Seeder(session).run()
    count = lambda model: session.scalar(select(func.count()).select_from(model))  # noqa: E731
    return {"vendors": count(models.Vendor), "items": count(models.Item), "purchase orders": count(models.ProcOrder),
            "goods receipts": count(models.GoodsReceipt), "vendor bills": count(models.VendorInvoice), "payments": count(models.Payment),
            "journal entries": count(models.JournalEntry), "anomalies flagged": len(added)}


if __name__ == "__main__":
    migrate()
    with SessionLocal() as session:
        loaded = seed(session, fresh="--reset" in sys.argv)
        if not loaded:
            print("ERP demo data is already loaded; nothing changed (use --reset to load it afresh).")
        for name, count in loaded.items():
            print(f"{name}: {count}")
