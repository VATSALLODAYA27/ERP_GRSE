# PRAVAH ERP: build spec (shared contract for backend and frontend)

PRAVAH turns this app (today: Sentinel, a drawing release gate) into an intelligent shipyard ERP prototype for the
GRSE GAINS 2026 entry "PRAVAH: agentic AI control tower for shipyard material flow". Sentinel stays as one module
("Engineering release"). **All data is mock data.** Never use real company names: vendors are invented and marked (mock).

Stack stays the same: FastAPI + SQLAlchemy 2 + Alembic migrations (backend/), React 18 + antd 5 + react-query + react-router
(frontend/). No new dependencies on either side. Follow the existing code style (plain words, short docstrings, `shortcut:`
comments for known simplifications). Money is INR, stored as float rupees, shown with Indian grouping (₹12,34,567).
Dates are ISO text YYYY-MM-DD like the existing extract tables.

Roles (existing `require()` in app/auth.py): **engineer** = requester/storekeeper (create requisitions, issue stock, record
receipts, enter invoices); **reviewer** = approver (approve requisitions, purchase orders, invoices, payments, stock
adjustments, follow-ups, resolve anomalies); **admin** = everything, plus master data. Purchase orders above ₹10,00,000
need an admin to approve (approval limit). Every create/approve/post is written to the audit log with `audit()`.

## 1. Data model (new tables; new migration 0007)

The existing extract tables stay untouched (`purchase_orders` there is the ERP extract that Sentinel's impact view reads).
New procurement tables use other names.

| Table | Columns |
|---|---|
| `vendors` | vendor_id PK ("V-1001"), name, city, category, gstin, msme bool, payment_terms_days int, lead_time_days int, active bool |
| `items` | item_code PK, description, category ("Steel plate", "Sections", "Pipes & fittings", "Valves", "Electrical", "Consumables", "Outfitting"), uom, grade, std_price float, reorder_level float, reorder_qty float, lead_time_days int, preferred_vendor_id FK vendors, critical bool |
| `stores` | store_code PK ("MW-STEEL", "MW-GEN", "RBD-STEEL", "FOU-OUTFIT"), name, location |
| `stock_moves` | id, on_date, item_code FK, store_code FK, kind ("OPENING","RECEIPT","ISSUE","TRANSFER_IN","TRANSFER_OUT","ADJUST"), qty float (signed: + in, - out), unit_cost float, value float (signed), ref_type ("GRN","ISSUE","TRANSFER","ADJUST","OPENING"), ref_no, work_order nullable, note, created_by, created_at |
| `requisitions` | pr_no PK ("PR-260101"), created_on, requested_by, work_order nullable, source ("MANUAL","WORK_ORDER","AI_REORDER"), status ("SUBMITTED","APPROVED","REJECTED","CONVERTED"), decided_by nullable, note |
| `requisition_lines` | id, pr_no FK, item_code FK, qty, need_by, po_no nullable (set when converted) |
| `proc_orders` | po_no PK ("PO-4500123" style), vendor_id FK, pr_no nullable, created_on, buyer, status ("DRAFT","APPROVED","SENT","PART_RECEIVED","RECEIVED","CLOSED","CANCELLED"), approved_by nullable, note |
| `proc_order_lines` | id, po_no FK, item_code FK, qty, unit_price, promised_date, received_qty float default 0, work_order nullable |
| `goods_receipts` | grn_no PK ("GRN-26xxxx"), po_no FK, received_on, store_code FK, received_by |
| `grn_lines` | id, grn_no FK, po_line_id FK, item_code, qty_received, qty_accepted, qty_rejected, reject_reason |
| `vendor_invoices` | inv_no PK ("VB-26xxxx"), vendor_invoice_no, vendor_id FK, po_no FK, invoice_date, due_date, status ("MATCHED","EXCEPTION","APPROVED","PAID","REJECTED"), match JSON, amount (before tax), tax, total, approved_by nullable, approval_reason |
| `vendor_invoice_lines` | id, inv_no FK, item_code, qty, unit_price |
| `payments` | pay_no PK ("PAY-26xxxx"), inv_no FK, vendor_id FK, paid_on, amount, mode ("NEFT","RTGS"), paid_by |
| `accounts` | code PK, name, type ("ASSET","LIABILITY","EQUITY","INCOME","EXPENSE") |
| `journal_entries` | je_no PK ("JE-26xxxxx"), on_date, source_type ("OPENING","GRN","INVOICE","PAYMENT","ISSUE","ADJUST"), source_no, narration, created_by, created_at |
| `journal_lines` | id, je_no FK, account_code FK, debit float, credit float, vendor_id nullable, item_code nullable |
| `ai_followups` | id, po_no FK, vendor_id, created_at, risk_level, subject, body, status ("DRAFT","APPROVED","DISMISSED"), decided_by nullable, written_by ("model" or "template") |
| `ai_flags` | id, kind, severity ("high","medium","low"), ref_type, ref_no, message, detected_at, status ("OPEN","RESOLVED"), resolved_by nullable, resolution_note |

Chart of accounts (seed): 1000 Bank, 1300 Inventory (raw materials and stores), 1400 Input GST, 1500 Work in progress (ship
construction), 2000 Accounts payable, 2100 Goods received not invoiced (GRNI), 3000 Opening balance equity,
5200 Purchase price variance, 5300 Inventory adjustment.

Postings (app/core/ledger.py; every entry must balance, tested):
- Opening stock: Dr 1300 / Cr 3000.
- GRN (accepted qty x PO price): Dr 1300 / Cr 2100. Stock move RECEIPT into the GRN's store at PO price.
- Invoice approved: Dr 2100 (PO price x invoiced qty), Dr 1400 (tax, 18% GST), Dr/Cr 5200 (price difference),
  Cr 2000 (total, vendor_id on the line).
- Payment: Dr 2000 (vendor_id) / Cr 1000.
- Issue to work order (moving-average cost): Dr 1500 / Cr 1300. Stock move ISSUE (cannot go below zero: 400 error).
- Adjustment: Dr or Cr 1300 against 5300.

Stock valuation is moving-average per item across stores (shortcut, documented).

## 2. API (all under /api, all need a signed-in user; JSON)

Lists return arrays of plain objects; field names below are the contract.

Master data
- `GET /api/vendors` → `[{vendor_id, name, city, category, msme, payment_terms_days, lead_time_days, grade, on_time_pct, avg_delay_days, rejection_pct, spend_ytd, open_po_value}]`
- `GET /api/vendors/{id}` → vendor fields + `{scorecard: {...same metrics, orders_closed}, orders: [po summary], payables: {balance, entries: [ledger rows]}}`
- `GET /api/items?category=&q=` → `[{item_code, description, category, uom, grade, std_price, reorder_level, critical, on_hand, on_order, stock_value, avg_cost, status}]` where status is "OK" | "REORDER" | "STOCK_OUT"
- `GET /api/items/{code}` → item fields + `{by_store: [{store_code, store_name, qty, value}], moves: [stock move rows, newest first], open_orders: [{po_no, vendor_name, qty, received_qty, promised_date, risk_level}], where_used: [{drawing_no, rev, part_no, qty}]}` (where_used: BOM rows whose part_no equals the item_code)
- `GET /api/stores` → `[{store_code, name, location, stock_value, items}]`

Inventory
- `GET /api/stock/moves?item=&store=&kind=` → newest first, `[{id, on_date, item_code, description, store_code, kind, qty, unit_cost, value, ref_type, ref_no, work_order, created_by}]`
- `POST /api/stock/issue` `{item_code, store_code, qty, work_order, note}` (engineer) → move
- `POST /api/stock/transfer` `{item_code, from_store, to_store, qty, note}` (engineer)
- `POST /api/stock/adjust` `{item_code, store_code, qty, note}` (reviewer; qty signed)

Procurement
- `GET /api/requisitions` → `[{pr_no, created_on, requested_by, work_order, source, status, lines: n, value}]`
- `GET /api/requisitions/{pr_no}` → header + `lines: [{id, item_code, description, qty, need_by, po_no, est_value}]`
- `POST /api/requisitions` `{work_order?, note?, lines: [{item_code, qty, need_by}]}` (engineer) → SUBMITTED
- `POST /api/requisitions/{pr_no}/approve` / `/reject` `{reason?}` (reviewer)
- `POST /api/requisitions/{pr_no}/convert` (reviewer; APPROVED only) → creates one DRAFT purchase order per preferred vendor at std_price, promised_date = today + vendor lead time; returns `{orders: [po_no]}`
- `GET /api/purchase-orders?status=&vendor=` → `[{po_no, vendor_id, vendor_name, created_on, status, value, lines, received_pct, next_promised, risk_level, risk_score}]`
- `GET /api/purchase-orders/{po_no}` → header + `{vendor, lines: [{id, item_code, description, qty, unit_price, value, promised_date, received_qty, work_order, risk: {score, level, predicted_date, reasons}}], receipts: [grn summary], invoices: [invoice summary], followups: [...], journal: [je summary], audit: [...]}`
- `POST /api/purchase-orders` `{vendor_id, note?, lines: [{item_code, qty, unit_price, promised_date, work_order?}]}` (engineer) → DRAFT
- `POST /api/purchase-orders/{po_no}/approve` (reviewer; above ₹10,00,000 admin only; 403 with a clear message otherwise) → APPROVED
- `POST /api/purchase-orders/{po_no}/send` → SENT (simulated; nothing leaves the system)
- `POST /api/purchase-orders/{po_no}/receive` `{store_code, received_on?, lines: [{line_id, qty_received, qty_accepted, reject_reason?}]}` (engineer) → GRN, stock moves, journal; PO becomes PART_RECEIVED or RECEIVED
- `GET /api/receipts` / `GET /api/receipts/{grn_no}`
- `GET /api/invoices?status=` → `[{inv_no, vendor_invoice_no, vendor_name, po_no, invoice_date, due_date, status, total, flags}]`
- `GET /api/invoices/{inv_no}` → header + `{lines, match: {ok, lines: [{item_code, po_qty, po_price, received_qty, invoiced_qty, invoiced_price, qty_ok, price_ok, price_variance_pct}], notes: [..]}, payments, journal, flags}`
- `POST /api/invoices` `{vendor_invoice_no, po_no, invoice_date, lines: [{item_code, qty, unit_price}]}` (engineer) → runs the 3-way match (qty invoiced ≤ qty accepted; price within ±2% of PO) and the anomaly checks; status MATCHED or EXCEPTION
- `POST /api/invoices/{inv_no}/approve` `{reason?}` (reviewer; EXCEPTION needs a reason) → APPROVED + journal
- `POST /api/invoices/{inv_no}/reject` `{reason}` (reviewer)
- `POST /api/invoices/{inv_no}/pay` `{mode?, paid_on?}` (reviewer; APPROVED only) → payment + journal, PAID

Finance
- `GET /api/ledger/accounts` → `[{code, name, type, debit, credit, balance}]`
- `GET /api/ledger/journal?source_type=&account=` → newest first `[{je_no, on_date, source_type, source_no, narration, created_by, total, lines: [{account_code, account_name, debit, credit, vendor_id, item_code}]}]`
- `GET /api/ledger/trial-balance` → `{rows: [{code, name, type, debit, credit}], total_debit, total_credit, balanced}`
- `GET /api/ledger/payables` → `{vendors: [{vendor_id, name, balance, current, d1_30, d31_60, d61_90, over_90, next_due}], total}` (ageing by invoice due date vs today)
- `GET /api/ledger/vendor/{vendor_id}` → running-balance rows

Intelligence (app/core/intel.py; explainable, deterministic numbers; the language model only writes text)
- `GET /api/intel/overview` → `{kpis: {open_po_value, open_po_count, at_risk_count, at_risk_value, stock_value, stock_outs, reorder_count, payables_due_7d, anomalies_open, followups_pending}, spend_by_category: [{category, value}] (last 6 months, from approved invoices + GRNs), stock_by_store: [{store_code, value}], top_risks: [first 5 of delivery-risk], recent_flags: [first 5 open flags]}`
- `GET /api/intel/delivery-risk` → every open PO line: `[{po_no, line_id, vendor_id, vendor_name, item_code, description, qty_open, promised_date, predicted_date, days_late_predicted, score (0-100), level ("HIGH" >= 60, "MEDIUM" >= 35, else "LOW"), reasons: [plain sentences], impacted_work_orders: [order_no], value_open}]`, highest score first.
  Score factors (each with a plain reason sentence): vendor on-time rate and average delay from closed history
  (receipt date vs promised date), days remaining vs vendor's typical lead time, part-receipt pattern, item marked critical,
  work orders waiting on the item (via work_order on the line, or BOM part_no == item_code → drawing → work orders), overdue already.
  predicted_date = promised_date + vendor's average delay (rounded).
- `POST /api/intel/followups/draft` `{po_no}` or `{all_high: true}` (engineer) → creates DRAFT follow-ups. Text is written by the
  language model through `core.explain.chat` (same config as the explainer: GRSE_EXPLAINER_URL/_MODEL/_KEY) from the facts
  only (PO, lines, promised date, predicted delay, impacted work orders); if no model or it fails, a clear template.
  `written_by` says which. Never sent anywhere.
- `GET /api/intel/followups?status=` ; `POST /api/intel/followups/{id}/approve` / `/dismiss` (reviewer). Approve = "approved to send";
  shortcut: no e-mail integration, recorded in the audit log only.
- `GET /api/intel/reorder` → `[{item_code, description, uom, on_hand, on_order, demand_open (BOM qty for open work orders + PR lines not converted), reorder_level, net_need, suggested_qty (rounded up to reorder_qty), vendor_id, vendor_name, est_value, reason}]` only where net_need > 0.
- `POST /api/intel/reorder/requisition` `{item_codes: [...]}` (engineer) → one PR with source AI_REORDER, need_by = today + lead time.
- `POST /api/intel/anomalies/scan` (any) → runs every detector, adds new OPEN flags (no duplicates of an open flag for the same kind+ref), returns `{added}`.
  Detectors: duplicate vendor invoice (same vendor + same vendor_invoice_no, or same vendor + same total within 10 days);
  invoice price above PO by more than 2%; invoiced qty above accepted qty; split purchase orders (same vendor + same item,
  2+ POs within 7 days, each below ₹10,00,000 but together above); high GRN rejection (> 10% of received); stock below
  reorder level on a critical item; PO overdue with no receipt.
- `GET /api/intel/anomalies?status=` ; `POST /api/intel/anomalies/{id}/resolve` `{note}` (reviewer)
- `GET /api/intel/vendor-scorecards` → same metrics as /api/vendors, grade A (on-time ≥ 85% and rejection ≤ 2%), B (≥ 65%), else C.

Navik (app/core/helper.py + api/reference.py): add the new pages to PAGES and a short guide section for the ERP pages, and add
compact data lines (open POs at risk, reorder suggestions, open anomalies, payables due, stock-outs) to `site_data()` so Navik can
answer "Which purchase orders are at risk?" and "Take me to the purchase orders".

## 3. Seed data (backend/scripts/seed_erp.py, idempotent; run after load_extract)

Dates are relative to today (so the demo is always current). Deterministic (random.Random(26)).
- 12 vendors with invented names marked (mock), across Kolkata, Durgapur, Jamshedpur, Visakhapatnam, Pune, Chennai, Mumbai; some MSME.
- ~40 items. Include the BOM part numbers from demo/register/bill_of_materials.csv as item codes (PL-101-01 deck plate AH36 12 mm,
  HP-101-02, FB-101-03, BK-101-04, PL-102-01, and the H-102/H-103 parts) so Sentinel's drawings and the ERP join up; plus
  sections, pipes, valves, cables, welding consumables, paint, outfitting items. Several critical items.
- 4 stores; opening stock for most items (some below reorder level, one or two at zero).
- ~30 closed historical POs over the last 8 months with GRNs, invoices and payments, built with the real posting functions so the
  ledger is consistent; vendor delays vary by vendor (one good, one chronically late, one with rejections).
- ~12 open POs: some on time, some at risk (promised soon, late vendor), one already overdue, one partly received. Include
  PO-4500123 (PL-101-01 x4), PO-4500124 (HP-101-02 x6), PO-4500126 (PL-102-01 x2) open and linked to work orders WO-24018/24019/24020
  so they match the extract Sentinel shows.
- Invoices: mostly matched and paid; one APPROVED unpaid due in 3 days; one EXCEPTION with a 6% price variance; one duplicate of
  an earlier invoice; one invoicing more than was accepted.
- 2 requisitions (one SUBMITTED from a work order, one APPROVED not yet converted).
- Issues of steel to WO-24019/WO-24020 from the steel store.
- Run the anomaly scan once at the end.
Also: demo/run-demo.ps1 and demo/record_demo.py's start_tool should run `scripts.seed_erp` after load_extract (backend agent edits
run-demo.ps1 only; the recorder is ours).

## 4. Screens (frontend)

Branding: product name "PRAVAH" with the subtitle "Shipyard ERP intelligence". Sentinel keeps its name as the
"Engineering release (Sentinel)" group. Update the sider header, the browser title, and the login page headline
("Material moves on time. Every rupee is accounted for.").

Menu (groups, in order):
- **Control tower**: Control Tower `/` (new home page), Dashboard → rename existing to "Release Dashboard" `/release`
- **Procurement**: Requisitions `/requisitions`, Purchase Orders `/purchase-orders`, Goods Receipts `/receipts`, Vendor Invoices `/invoices`, Vendors `/vendors`
- **Inventory**: Items & Stock `/items`, Stock Ledger `/stock`
- **Finance**: General Ledger `/ledger` (tabs: Journal, Trial balance, Accounts), Payables `/payables`
- **Engineering release (Sentinel)**: Drawing Register, New Check, Checks, Release Gate, Class Approvals, Rule Library (existing routes unchanged)
- **Administration**: Audit Log, Users

Control Tower `/`: KPI cards (open PO value, at-risk deliveries, stock value, payables due in 7 days, open anomalies, reorder items);
"Deliveries at risk" table (risk bar, level tag, vendor, item, promised vs predicted date, reasons as a tooltip/expandable list,
impacted work orders as tags linking to /gate) with a button "Draft follow-ups for high-risk orders"; "Follow-up outbox" (drafts
with subject/body preview, Approve / Dismiss, a tag "written by AI model" or "template"); "Anomalies" list (severity, message,
link to the record, Resolve with a note); "Reorder suggestions" (select rows → "Create requisition"); "Spend by category" and
"Stock by store" as simple CSS bar charts (no chart library). Every number links to its page.

Lists use antd Table with search/filter like the existing pages; detail pages use Descriptions + Tabs like DrawingDetail/CheckReport.
Actions open antd Modals/Forms: New requisition (item picker with on-hand shown), Convert to PO, New purchase order, Approve PO,
Receive goods (per line: received, accepted, reject reason; store), Enter vendor invoice (lines prefilled from the PO; shows the
3-way match result right after saving with green/red cells), Approve/Reject invoice (reason required for EXCEPTION), Pay, Issue
stock to a work order, Transfer, Adjust. Show who may do what with the existing `can` helpers (add `can.approve` = reviewer/admin,
`can.request` = everyone). Money with Indian grouping; dates as "19 Oct 2026". Works in light and dark mode (existing ModeSwitch).
Item detail shows "Where used" (drawings) linking to the Sentinel drawing page, and PO line work orders link to /gate, so the two
halves feel like one product.
