"""SENTINEL ERP: the books balance, the match and the detectors work on the seeded data, and roles are enforced.

Runs against the seed (scripts/seed_erp.py). No AI service is ever called: the key is cleared for every test,
and the tests that need a model reply use a fake one.
"""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import config
from app.core import explain, intel, ledger, procure
from app.db import SessionLocal
from app.main import app
from app.models import JournalEntry, StockMove
from scripts.approve_seed_rules import approve
from scripts.load_extract import load
from scripts.seed_erp import seed as seed_erp
from scripts.seed_users import seed

PASSWORDS = {u["username"]: u["password"] for u in json.loads(config.SEED_USERS_FILE.read_text(encoding="utf-8"))}
TODAY = date.today()


def days_from_today(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture(scope="module", autouse=True)
def database():
    with TestClient(app):
        with SessionLocal() as session:
            load(session)
            seed(session)
            approve(session)
            assert seed_erp(session, fresh=True)["vendors"] == 12
            assert seed_erp(session) == {}  # a second run changes nothing
        yield


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """Tests never reach an AI service: no key, and any attempt to call one fails the test."""
    monkeypatch.setattr(config, "EXPLAINER_KEY", "")
    monkeypatch.setattr(explain.httpx, "post", lambda *a, **k: pytest.fail("an AI service was called"))


def signed_in(username):
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]}).status_code == 200
    return client


@pytest.fixture(scope="module")
def engineer():
    return signed_in("engineer")


@pytest.fixture(scope="module")
def reviewer():
    return signed_in("reviewer")


@pytest.fixture(scope="module")
def admin():
    return signed_in("Admin_123")


def assert_books_balance(client):
    with SessionLocal() as session:
        for entry in session.scalars(select(JournalEntry).options(selectinload(JournalEntry.lines))):
            assert round(sum(l.debit for l in entry.lines), 2) == round(sum(l.credit for l in entry.lines), 2), entry.je_no
        stock_value = round(sum(m.value for m in session.scalars(select(StockMove))), 2)
    trial = client.get("/api/ledger/trial-balance").json()
    assert trial["balanced"] and trial["total_debit"] == trial["total_credit"] > 0
    assert round(sum(r["debit"] for r in trial["rows"]), 2) == trial["total_debit"]
    inventory = next(a for a in client.get("/api/ledger/accounts").json() if a["code"] == "1300")
    assert abs(inventory["balance"] - stock_value) < 0.05  # the inventory account is exactly the stock ledger's value


def stock_of(client, item_code):
    return next(i for i in client.get("/api/items", params={"q": item_code}).json() if i["item_code"] == item_code)


# --- The seeded books ---


def test_seeded_books_balance_and_every_entry_balances(engineer):
    assert_books_balance(engineer)
    kinds = {e["source_type"] for e in engineer.get("/api/ledger/journal").json()}
    assert {"OPENING", "GRN", "INVOICE", "PAYMENT", "ISSUE"} <= kinds
    payables = engineer.get("/api/ledger/payables").json()
    owed = next(a for a in engineer.get("/api/ledger/accounts").json() if a["code"] == "2000")["balance"]
    assert abs(payables["total"] - owed) < 0.05
    for v in payables["vendors"]:
        assert abs(v["current"] + v["d1_30"] + v["d31_60"] + v["d61_90"] + v["over_90"] - v["balance"]) < 0.05
    # The seeded story: one bill due in three days, one overdue, all vendors invented.
    assert any(v["next_due"] == days_from_today(3) for v in payables["vendors"])
    assert any(v["d1_30"] > 0 for v in payables["vendors"])
    assert all(v["name"] for v in engineer.get("/api/vendors").json())


def test_each_anomaly_detector_fires_on_the_seeded_cases(engineer):
    flags = engineer.get("/api/intel/anomalies", params={"status": "OPEN"}).json()
    found = {(f["kind"], f["ref_no"]) for f in flags}
    assert {f["kind"] for f in flags} == {"duplicate_invoice", "price_above_po", "qty_above_accepted", "split_po", "high_rejection",
                                          "critical_low_stock", "overdue_no_receipt"}
    assert {("overdue_no_receipt", "PO-4500122"), ("split_po", "PO-4500132"), ("critical_low_stock", "VL-SEA-200"),
            ("critical_low_stock", "PL-103-01")} <= found
    bills = {i["po_no"]: i for i in engineer.get("/api/invoices", params={"status": "EXCEPTION"}).json() if i["po_no"] in ("PO-4500119", "PO-4500126")}
    assert ("price_above_po", bills["PO-4500126"]["inv_no"]) in found and ("qty_above_accepted", bills["PO-4500119"]["inv_no"]) in found
    assert all(f["kind"] in ("price_above_po", "qty_above_accepted") for b in bills.values() for f in b["flags"])
    # A second scan adds nothing: an open flag is never raised twice.
    assert engineer.post("/api/intel/anomalies/scan").json() == {"added": 0}


def test_delivery_risk_puts_a_late_vendor_above_a_reliable_one(engineer):
    risks = engineer.get("/api/intel/delivery-risk").json()
    assert [r["score"] for r in risks] == sorted((r["score"] for r in risks), reverse=True)
    late = next(r for r in risks if r["po_no"] == "PO-4500124")  # chronically late vendor, due in 3 days
    reliable = next(r for r in risks if r["po_no"] == "PO-4500123")  # always on time, due in 12 days
    assert late["score"] > reliable["score"] and late["level"] == "HIGH" and reliable["level"] == "LOW"
    assert late["predicted_date"] > late["promised_date"] and late["days_late_predicted"] > 0
    assert reliable["predicted_date"] == reliable["promised_date"]
    assert "WO-24019" in late["impacted_work_orders"] and "WO-24019" in reliable["impacted_work_orders"]
    assert all(r["reasons"] for r in risks) and any("on time" in reason for reason in late["reasons"])
    overdue = next(r for r in risks if r["po_no"] == "PO-4500122")
    assert overdue["level"] == "HIGH" and any("past the promised date" in reason for reason in overdue["reasons"])

    # The same line, scored for two vendors: only the vendor's record differs.
    facts = {"days_left": 5, "order_span": 30, "lead_time": 30, "qty": 4, "received": 0, "qty_open": 4, "uom": "NOS",
             "critical": False, "work_orders": ["WO-24019"]}
    bad, _ = intel.risk_score(facts | {"deliveries": 10, "on_time_pct": 20.0, "avg_delay": 9})
    good, _ = intel.risk_score(facts | {"deliveries": 10, "on_time_pct": 100.0, "avg_delay": 0})
    assert bad > good
    assert (intel.level(60), intel.level(59), intel.level(35), intel.level(34)) == ("HIGH", "MEDIUM", "MEDIUM", "LOW")


def test_vendor_grades_follow_the_rule(engineer):
    for v in engineer.get("/api/intel/vendor-scorecards").json():
        expected = "A" if v["on_time_pct"] >= 85 and v["rejection_pct"] <= 2 else "B" if v["on_time_pct"] >= 65 else "C"
        assert v["grade"] == expected, v["vendor_id"]
    grades = {v["vendor_id"]: v["grade"] for v in engineer.get("/api/vendors").json()}
    assert grades["V-1001"] == "A" and grades["V-1002"] == "C"  # reliable plate stockist, chronically late rolling mill
    detail = engineer.get("/api/vendors/V-1003").json()
    assert detail["scorecard"]["rejection_pct"] > 2 and detail["orders"] and "balance" in detail["payables"]


def test_reorder_net_need_and_suggested_quantity(engineer):
    assert intel.net_need(on_hand=1, on_order=6, on_requisition=0, demand_open=6, reorder_level=4) == 3
    assert intel.net_need(on_hand=10, on_order=0, on_requisition=0, demand_open=0, reorder_level=4) == -6
    assert (ledger.lots(3, 6), ledger.lots(6, 6), ledger.lots(6.5, 6), ledger.lots(2.5, 0)) == (6, 6, 12, 2.5)

    rows = engineer.get("/api/intel/reorder").json()
    assert rows
    for r in rows:
        assert r["net_need"] == round(r["demand_open"] + r["reorder_level"] - r["on_hand"] - r["on_order"] - r["on_requisition"], 6) > 0
        assert r["suggested_qty"] >= r["net_need"] and r["vendor_name"]
    hp = next(r for r in rows if r["item_code"] == "HP-101-02")
    # WO-24019 needs 7 on its bill of materials, 1 was issued; 1 in stock and 6 on order against a reorder level of 4.
    assert (hp["demand_open"], hp["on_hand"], hp["on_order"], hp["net_need"], hp["suggested_qty"]) == (6, 1, 6, 3, 6)

    # Asking for the suggestion raises a requisition, and the suggestion is then covered.
    pr = engineer.post("/api/intel/reorder/requisition", json={"item_codes": ["HP-101-02", "PT-AF-RED"]})
    assert pr.status_code == 201
    body = pr.json()
    assert body["source"] == "AI_REORDER" and body["status"] == "SUBMITTED" and {l["item_code"] for l in body["lines"]} == {"HP-101-02", "PT-AF-RED"}
    assert next(l for l in body["lines"] if l["item_code"] == "HP-101-02")["need_by"] == days_from_today(30)
    left = {r["item_code"] for r in engineer.get("/api/intel/reorder").json()}
    assert "HP-101-02" not in left and "PT-AF-RED" not in left
    assert engineer.post("/api/intel/reorder/requisition", json={"item_codes": ["HP-101-02"]}).status_code == 422


# --- The 3-way match ---


def test_three_way_match_checks_quantity_and_price_within_two_percent():
    ordered, accepted = {"A": (10, 100.0)}, {"A": 8}

    def one(qty, price, earlier=None):
        return procure.three_way_match(ordered, accepted, earlier or {}, [{"item_code": "A", "qty": qty, "unit_price": price}])

    assert one(8, 101.9)["ok"] and one(8, 98.0)["ok"] and one(8, 102.0)["ok"]
    over_price = one(8, 102.5)
    assert not over_price["ok"] and over_price["lines"][0]["price_ok"] is False and over_price["lines"][0]["price_variance_pct"] == 2.5
    over_qty = one(9, 100.0)
    assert not over_qty["ok"] and over_qty["lines"][0]["qty_ok"] is False and "only 8 accepted" in over_qty["notes"][0]
    assert not one(4, 100.0, earlier={"A": 5})["ok"]  # earlier bills count: 5 + 4 is more than the 8 accepted
    stranger = procure.three_way_match(ordered, accepted, {}, [{"item_code": "B", "qty": 1, "unit_price": 1.0}])
    assert not stranger["ok"] and "not on the purchase order" in stranger["notes"][0]


def test_purchase_to_pay_posts_balanced_entries_and_moving_average_cost(engineer, reviewer):
    before = stock_of(engineer, "OF-LAD-SS")
    created = engineer.post("/api/purchase-orders", json={"vendor_id": "V-1007", "note": "test order", "lines": [
        {"item_code": "OF-LAD-SS", "qty": 4, "unit_price": 20000, "promised_date": days_from_today(10)}]})
    assert created.status_code == 201 and created.json()["status"] == "DRAFT"
    po_no, line_id = created.json()["po_no"], created.json()["lines"][0]["id"]
    assert reviewer.post(f"/api/purchase-orders/{po_no}/approve").json()["status"] == "APPROVED"
    assert engineer.post(f"/api/purchase-orders/{po_no}/send").json()["status"] == "SENT"

    receipt = engineer.post(f"/api/purchase-orders/{po_no}/receive", json={"store_code": "FOU-OUTFIT", "lines": [
        {"line_id": line_id, "qty_received": 5, "qty_accepted": 5}]})
    assert receipt.status_code == 400 and "still open" in receipt.json()["detail"]  # only 4 were ordered
    receipt = engineer.post(f"/api/purchase-orders/{po_no}/receive", json={"store_code": "FOU-OUTFIT", "lines": [
        {"line_id": line_id, "qty_received": 4, "qty_accepted": 3}]})
    assert receipt.status_code == 400 and "why" in receipt.json()["detail"]  # a rejection needs a reason
    receipt = engineer.post(f"/api/purchase-orders/{po_no}/receive", json={"store_code": "FOU-OUTFIT", "lines": [
        {"line_id": line_id, "qty_received": 4, "qty_accepted": 3, "reject_reason": "Bent rungs"}]})
    assert receipt.status_code == 201
    grn = receipt.json()
    assert grn["qty_accepted"] == 3 and grn["value"] == 60000 and grn["journal"][0]["total"] == 60000
    assert engineer.get(f"/api/purchase-orders/{po_no}").json()["status"] == "PART_RECEIVED"

    after = stock_of(engineer, "OF-LAD-SS")
    assert after["on_hand"] == before["on_hand"] + 3
    assert abs(after["stock_value"] - (before["stock_value"] + 60000)) < 0.05
    average = after["stock_value"] / after["on_hand"]

    bill = engineer.post("/api/invoices", json={"vendor_invoice_no": "TEST/0001", "po_no": po_no, "invoice_date": TODAY.isoformat(),
                                                 "lines": [{"item_code": "OF-LAD-SS", "qty": 3, "unit_price": 20300}]})
    assert bill.status_code == 201 and bill.json()["status"] == "MATCHED"  # 1.5% above the order: within tolerance
    inv_no = bill.json()["inv_no"]
    assert engineer.post(f"/api/invoices/{inv_no}/pay").status_code == 403  # an engineer cannot pay
    assert reviewer.post(f"/api/invoices/{inv_no}/pay").status_code == 409  # not approved yet
    approved = reviewer.post(f"/api/invoices/{inv_no}/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    entry = approved.json()["journal"][0]
    lines = {l["account_code"]: l for l in entry["lines"]}
    assert lines["2100"]["debit"] == 60000 and lines["1400"]["debit"] == 10962 and lines["5200"]["debit"] == 900
    assert lines["2000"]["credit"] == 71862 == approved.json()["total"]
    paid = reviewer.post(f"/api/invoices/{inv_no}/pay", json={"mode": "NEFT"})
    assert paid.status_code == 201 and paid.json()["status"] == "PAID" and len(paid.json()["payments"]) == 1

    issued = engineer.post("/api/stock/issue", json={"item_code": "OF-LAD-SS", "store_code": "FOU-OUTFIT", "qty": 2, "work_order": "WO-24019"})
    assert issued.status_code == 201
    assert abs(issued.json()["value"] + round(2 * average, 2)) < 0.05  # out at moving-average cost
    assert engineer.post("/api/stock/issue", json={"item_code": "OF-LAD-SS", "store_code": "FOU-OUTFIT", "qty": 1,
                                                   "work_order": "WO-99999"}).status_code == 422
    moved = engineer.post("/api/stock/transfer", json={"item_code": "OF-LAD-SS", "from_store": "FOU-OUTFIT", "to_store": "MW-GEN", "qty": 1})
    assert moved.status_code == 201 and [m["kind"] for m in moved.json()] == ["TRANSFER_OUT", "TRANSFER_IN"]
    assert reviewer.post("/api/stock/adjust", json={"item_code": "OF-LAD-SS", "store_code": "MW-GEN", "qty": -1, "note": "count"}).status_code == 201
    assert reviewer.post("/api/stock/adjust", json={"item_code": "OF-LAD-SS", "store_code": "MW-GEN", "qty": 2, "note": "found"}).status_code == 201
    kinds = {e["source_type"] for e in engineer.get("/api/ledger/journal").json()}
    assert {"GRN", "INVOICE", "PAYMENT", "ISSUE", "ADJUST"} <= kinds
    assert_books_balance(engineer)
    actions = {a["action"] for a in reviewer.get("/api/audit").json()}
    assert {"po.created", "po.approved", "grn.posted", "invoice.entered", "invoice.approved", "payment.posted", "stock.issued",
            "stock.transferred", "stock.adjusted"} <= actions


def test_an_exception_needs_a_reason_and_books_the_price_variance(engineer, reviewer):
    bill = next(i for i in engineer.get("/api/invoices", params={"status": "EXCEPTION"}).json() if i["po_no"] == "PO-4500126")
    detail = engineer.get(f"/api/invoices/{bill['inv_no']}").json()
    assert detail["match"]["ok"] is False and detail["match"]["lines"][0]["price_variance_pct"] == 6.0
    assert reviewer.post(f"/api/invoices/{bill['inv_no']}/approve", json={}).status_code == 422
    approved = reviewer.post(f"/api/invoices/{bill['inv_no']}/approve", json={"reason": "Mill surcharge agreed by phone"})
    assert approved.status_code == 200 and approved.json()["approval_reason"].startswith("Mill surcharge")
    variance = next(l for l in approved.json()["journal"][0]["lines"] if l["account_code"] == "5200")
    assert variance["debit"] == 7500  # 6% of ₹1,25,000
    assert_books_balance(engineer)


def test_requisition_to_draft_orders(engineer, reviewer):
    created = engineer.post("/api/requisitions", json={"work_order": "WO-24022", "lines": [
        {"item_code": "VL-GAT-100", "qty": 2, "need_by": days_from_today(50)},
        {"item_code": "EL-LT-LED", "qty": 10, "need_by": days_from_today(30)}]})
    assert created.status_code == 201 and created.json()["status"] == "SUBMITTED" and created.json()["source"] == "WORK_ORDER"
    pr_no = created.json()["pr_no"]
    assert reviewer.post(f"/api/requisitions/{pr_no}/convert").status_code == 409  # not approved yet
    assert engineer.post(f"/api/requisitions/{pr_no}/approve", json={}).status_code == 403
    assert reviewer.post(f"/api/requisitions/{pr_no}/approve", json={}).json()["status"] == "APPROVED"
    orders = reviewer.post(f"/api/requisitions/{pr_no}/convert").json()["orders"]
    assert len(orders) == 2  # one per preferred vendor
    for po_no in orders:
        po = engineer.get(f"/api/purchase-orders/{po_no}").json()
        assert po["status"] == "DRAFT" and po["pr_no"] == pr_no
        assert po["lines"][0]["promised_date"] == days_from_today(po["vendor"]["lead_time_days"])
    assert engineer.get(f"/api/requisitions/{pr_no}").json()["status"] == "CONVERTED"


# --- Roles and limits ---


def test_roles_and_the_approval_limit(engineer, reviewer, admin):
    big = next(p for p in engineer.get("/api/purchase-orders", params={"status": "DRAFT"}).json() if p["po_no"] == "PO-4500134")
    assert big["value"] > 1_000_000 and big["needs_admin"]
    assert engineer.post("/api/purchase-orders/PO-4500134/approve").status_code == 403
    refused = reviewer.post("/api/purchase-orders/PO-4500134/approve")
    assert refused.status_code == 403 and "admin" in refused.json()["detail"] and "10,00,000" in refused.json()["detail"]
    assert admin.post("/api/purchase-orders/PO-4500134/approve").json()["status"] == "APPROVED"
    assert reviewer.post("/api/purchase-orders/PO-4500133/approve").json()["status"] == "APPROVED"  # under the limit
    assert reviewer.post("/api/purchase-orders/PO-4500133/approve").status_code == 409  # only a draft can be approved

    flag = engineer.get("/api/intel/anomalies", params={"status": "OPEN"}).json()[0]
    assert engineer.post(f"/api/intel/anomalies/{flag['id']}/resolve", json={"note": "ok"}).status_code == 403
    assert reviewer.post(f"/api/intel/anomalies/{flag['id']}/resolve", json={"note": ""}).status_code == 422
    resolved = reviewer.post(f"/api/intel/anomalies/{flag['id']}/resolve", json={"note": "Chased by phone"})
    assert resolved.json()["status"] == "RESOLVED" and resolved.json()["resolved_by"] == "reviewer"
    assert engineer.post("/api/intel/anomalies/scan").json() == {"added": 0}  # a resolved flag is not raised again
    assert engineer.post("/api/stock/adjust", json={"item_code": "OF-LAD-SS", "store_code": "MW-GEN", "qty": 1}).status_code == 403
    bill = engineer.get("/api/invoices", params={"status": "EXCEPTION"}).json()[0]
    assert engineer.post(f"/api/invoices/{bill['inv_no']}/approve", json={"reason": "x"}).status_code == 403
    assert engineer.post(f"/api/invoices/{bill['inv_no']}/reject", json={"reason": "x"}).status_code == 403
    assert reviewer.post(f"/api/invoices/{bill['inv_no']}/reject", json={"reason": ""}).status_code == 422


def test_stock_cannot_go_negative(engineer, reviewer):
    out = stock_of(engineer, "VL-SEA-200")
    assert out["on_hand"] == 0 and out["status"] == "STOCK_OUT"
    refused = engineer.post("/api/stock/issue", json={"item_code": "VL-SEA-200", "store_code": "MW-GEN", "qty": 1, "work_order": "WO-24021"})
    assert refused.status_code == 400 and "below zero" in refused.json()["detail"]
    some = stock_of(engineer, "PF-ELB-100")
    too_many = some["on_hand"] + 1
    assert engineer.post("/api/stock/issue", json={"item_code": "PF-ELB-100", "store_code": "MW-GEN", "qty": too_many,
                                                   "work_order": "WO-24021"}).status_code == 400
    assert engineer.post("/api/stock/transfer", json={"item_code": "PF-ELB-100", "from_store": "MW-GEN", "to_store": "MW-STEEL",
                                                      "qty": too_many}).status_code == 400
    assert reviewer.post("/api/stock/adjust", json={"item_code": "PF-ELB-100", "store_code": "MW-GEN", "qty": -too_many}).status_code == 400
    assert engineer.post("/api/stock/issue", json={"item_code": "PF-ELB-100", "store_code": "RBD-STEEL", "qty": 1,
                                                   "work_order": "WO-24021"}).status_code == 400  # none in that store
    assert stock_of(engineer, "PF-ELB-100")["on_hand"] == some["on_hand"]  # nothing was half-written
    with SessionLocal() as session, pytest.raises(ledger.LedgerError):
        ledger.post(session, TODAY.isoformat(), "ADJUST", "X", "unbalanced", "test", [("1300", 100, 0, None, None), ("5300", 0, 99, None, None)])


# --- Follow-ups and Navik ---


class FakeModelReply:
    def __init__(self, text):
        self.text, self.status_code = text, 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self.text}}]}


def test_followups_are_drafted_from_facts_and_never_sent(engineer, reviewer, monkeypatch):
    drafted = engineer.post("/api/intel/followups/draft", json={"all_high": True})
    assert drafted.status_code == 201
    created = drafted.json()["created"]
    high = {r["po_no"] for r in engineer.get("/api/intel/delivery-risk").json() if r["level"] == "HIGH"}
    assert {f["po_no"] for f in created} == high and all(f["written_by"] == "template" for f in created)
    first = next(f for f in created if f["po_no"] == "PO-4500124")
    assert "PO-4500124" in first["subject"] and "WO-24019" in first["body"] and first["status"] == "DRAFT"
    assert set(engineer.post("/api/intel/followups/draft", json={"all_high": True}).json()["skipped"]) == high  # one draft per order

    assert engineer.post(f"/api/intel/followups/{first['id']}/approve").status_code == 403
    assert reviewer.post(f"/api/intel/followups/{first['id']}/approve").json()["status"] == "APPROVED"
    assert reviewer.post(f"/api/intel/followups/{first['id']}/dismiss").status_code == 409
    assert engineer.get("/api/intel/overview").json()["kpis"]["followups_pending"] == len(high) - 1

    # With a model: it only words the facts it is given. A reply that adds a number falls back to the template.
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(body=json)
        return FakeModelReply(sent["reply"])

    monkeypatch.setattr(config, "EXPLAINER_KEY", "test-key-not-real")
    monkeypatch.setattr(explain.httpx, "post", fake_post)
    sent["reply"] = "Subject: PO-4500123 dispatch\n\nDear supplier, please confirm the dispatch of PL-101-01 for WO-24019.\n\nProcurement team (SENTINEL walkthrough)"
    model = engineer.post("/api/intel/followups/draft", json={"po_no": "PO-4500123"}).json()["created"][0]
    assert model["written_by"] == "model" and model["subject"] == "PO-4500123 dispatch"
    facts = sent["body"]["messages"][1]["content"]
    assert "PO-4500123" in facts and "WO-24019" in facts and "price" not in facts.lower()
    sent["reply"] = "Subject: PO-4500120\n\nPlease ship within 2 days or a 5% penalty applies."
    invented = engineer.post("/api/intel/followups/draft", json={"po_no": "PO-4500120"}).json()["created"][0]
    assert invented["written_by"] == "template"
    assert engineer.post("/api/intel/followups/draft", json={"po_no": "PO-4500118"}).status_code == 409  # nothing open on it
    assert {"followup.drafted", "followup.approved"} <= {a["action"] for a in reviewer.get("/api/audit").json()}


def test_navik_knows_the_erp_pages_and_records(engineer, monkeypatch):
    from app.api.reference import site_data
    from app.core.helper import PAGES

    assert PAGES["/"] == "Control Tower" and PAGES["/release"] == "Release Dashboard" and PAGES["/purchase-orders"] == "Purchase Orders"
    with SessionLocal() as session:
        data = site_data(session)
    assert len(data) <= 12000 and "TOTALS ERP:" in data and "PO-4500124" in data and "REORDER SUGGESTIONS" in data

    offline = engineer.post("/api/helper", json={"question": "Which purchase orders are at risk?", "page": "Items & Stock"})
    assert offline.status_code == 200 and "PO-45001" in offline.json()["answer"]

    monkeypatch.setattr(config, "EXPLAINER_KEY", "test-key-not-real")
    monkeypatch.setattr(explain.httpx, "post", lambda url, headers, json, timeout: FakeModelReply("Opening them.\nGO: /purchase-orders"))
    assert engineer.post("/api/helper", json={"question": "Take me to the purchase orders"}).json() == {"answer": "Opening them.", "go": "/purchase-orders"}
    monkeypatch.setattr(explain.httpx, "post", lambda url, headers, json, timeout: FakeModelReply("GO: /purchase-orders/PO-4500124"))
    assert engineer.post("/api/helper", json={"question": "open PO-4500124"}).json()["go"] == "/purchase-orders/PO-4500124"


def test_every_erp_page_answers(engineer):
    lists = ["/api/vendors", "/api/items", "/api/stores", "/api/stock/moves", "/api/requisitions", "/api/purchase-orders", "/api/receipts",
             "/api/invoices", "/api/ledger/accounts", "/api/ledger/journal", "/api/intel/delivery-risk", "/api/intel/followups",
             "/api/intel/reorder", "/api/intel/anomalies", "/api/intel/vendor-scorecards", "/api/ledger/vendor/V-1001"]
    for path in lists:
        response = engineer.get(path)
        assert response.status_code == 200 and response.json(), path
    first = {path: engineer.get(path).json()[0] for path in ("/api/requisitions", "/api/receipts", "/api/invoices")}
    for path in (f"/api/vendors/V-1002", "/api/items/PL-101-01", f"/api/requisitions/{first['/api/requisitions']['pr_no']}",
                 "/api/purchase-orders/PO-4500124", f"/api/receipts/{first['/api/receipts']['grn_no']}",
                 f"/api/invoices/{first['/api/invoices']['inv_no']}"):
        assert engineer.get(path).status_code == 200, path
    item = engineer.get("/api/items/PL-101-01").json()
    assert {(w["drawing_no"], w["rev"]) for w in item["where_used"]} == {("GRSE-H-101", "A"), ("GRSE-H-101", "B")}
    assert item["open_orders"][0]["po_no"] == "PO-4500123" and item["by_store"]
    overview = engineer.get("/api/intel/overview").json()
    assert overview["kpis"]["open_po_count"] > 0 and overview["spend_by_category"] and len(overview["top_risks"]) == 5
    assert engineer.get("/api/purchase-orders/PO-0000000").status_code == 404
    assert TestClient(app).get("/api/intel/overview").status_code == 401
