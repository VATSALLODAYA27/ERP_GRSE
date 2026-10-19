import csv

import numpy as np
import pymupdf
import pytest

from app import config
from app.core.bom import compare_bom
from app.core.diff import compare, overlay_png
from app.core.extract import UnreadableDrawing, extract
from app.core import ocr
from app.core.gate import gate
from app.core.impact import impact
from app.core.rules import load_rules, run_checks, verdict

# In these tests a rule counts as approved when the rule file marks it for the demo; the approval workflow itself is tested through the API.
RULES = [rule | {"state": rule["demo_state"]} for rule in load_rules(config.RULES_FILE)]
with open(config.EXTRACT_DIR / "drawing_register.csv", newline="", encoding="utf-8") as f:
    REGISTER = {row["drawing_no"]: row for row in csv.DictReader(f)}
with open(config.EXTRACT_DIR / "bill_of_materials.csv", newline="", encoding="utf-8") as f:
    BOM = list(csv.DictReader(f))
with open(config.EXTRACT_DIR / "ship_particulars.csv", newline="", encoding="utf-8") as f:
    SHIPS = {row["hull_no"]: row | {"rule_length_m": float(row["rule_length_m"])} for row in csv.DictReader(f)}


def erp_for(drawing, register="lookup"):
    """What the ERP extract holds for this drawing. Pass register=None or a row to pretend the register says otherwise."""
    no, rev = drawing["fields"]["drawing_no"]["value"], drawing["fields"]["revision"]["value"]
    return {
        "register": REGISTER.get(no) if register == "lookup" else register,
        "bom": [item for item in BOM if item["drawing_no"] == no and item["rev"] == rev],
        "ship": SHIPS.get(drawing["fields"]["hull_no"]["value"]),
    }


def check(samples, name):
    drawing = extract((samples / name).read_bytes())
    findings = run_checks(drawing, erp_for(drawing), RULES)
    return verdict(findings), {f["rule_id"] for f in findings}, findings


def test_title_block_parts_and_standards_are_read(samples):
    d = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    values = {name: field["value"] for name, field in d["fields"].items()}
    assert values == {
        "title": "FWD MAIN DECK PLATING FR 20-28", "drawing_no": "GRSE-H-101", "revision": "B", "status": "APPROVED",
        "material": "AH36", "thickness_mm": "12", "date": "2026-09-15", "hull_no": "3030", "zone": "DECK", "spacing_mm": "700",
    }
    assert [(p["part_no"], p["material"], p["thickness_mm"], p["qty"]) for p in d["parts"]] == [
        ("PL-101-01", "AH36", "12", "4"), ("HP-101-02", "AH36", "8", "7"),
        ("FB-101-03", "A", "10", "8"), ("BK-101-04", "AH36", "10", "4"),
    ]
    assert [(s["name"], s["edition"]) for s in d["standards"]] == [
        ("MOCK-CLS STEEL SHIP RULES", 2024), ("MOCK-CUST HULL SPEC 100", 2023),
    ]


@pytest.mark.parametrize("name, expected_verdict, expected_rules", [
    ("02_GRSE-H-101_revB_clean-pass.pdf", "PASS", set()),
    ("01_GRSE-H-101_revA_superseded-revision.pdf", "BLOCKED", {"REG-01", "CHK-08"}),
    ("03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf", "BLOCKED", {"CHK-02", "CHK-03", "CHK-04", "CHK-05", "BOM-01", "CHK-08"}),
    ("04_GRSE-H-103_revA_old-standard-edition.pdf", "NEEDS_REVIEW", {"CHK-02", "CHK-06", "BOM-01", "CHK-09"}),
    ("05_GRSE-M-210_revA_for-information-only.pdf", "BLOCKED", {"CHK-01"}),
])
def test_sample_verdicts(samples, name, expected_verdict, expected_rules):
    got_verdict, got_rules, findings = check(samples, name)
    assert (got_verdict, got_rules) == (expected_verdict, expected_rules)
    assert all(f["clause"] and f["evidence"] for f in findings)


def test_failures_are_reported_per_part(samples):
    _, _, findings = check(samples, "03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf")
    thin = [f["evidence"] for f in findings if f["rule_id"] == "CHK-04"]
    assert len(thin) == 2 and any("PL-102-01" in e for e in thin) and any("Title block" in e for e in thin)


def test_drawing_missing_from_register_is_blocked(samples):
    drawing = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    findings = run_checks(drawing, erp_for(drawing, register=None), RULES)
    assert verdict(findings) == "BLOCKED" and findings[0]["rule_id"] == "REG-01"


def test_revision_newer_than_register_is_blocked(samples):
    drawing = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    findings = run_checks(drawing, erp_for(drawing, register={"current_rev": "A", "status": "APPROVED"}), RULES)
    assert "not in the register" in findings[0]["evidence"]


def test_title_block_status_disagreeing_with_register_needs_review(samples):
    drawing = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    findings = run_checks(drawing, erp_for(drawing, register={"current_rev": "B", "status": "FOR INFORMATION"}), RULES)
    assert {f["rule_id"] for f in findings} == {"REG-02", "CHK-01"}


def test_pdf_without_text_is_rejected():
    doc = pymupdf.open()
    doc.new_page()
    with pytest.raises(UnreadableDrawing):
        extract(doc.tobytes())
    with pytest.raises(UnreadableDrawing):
        extract(b"%PDF-1.7 not really a pdf")


def test_revision_changes_are_listed(samples):
    old = extract((samples / "01_GRSE-H-101_revA_superseded-revision.pdf").read_bytes())
    new = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    changes = {(c["area"], c["kind"], c["what"], c["old"], c["new"]) for c in compare(old, new)}
    assert changes == {
        ("Title block", "changed", "Revision", "A", "B"),
        ("Title block", "changed", "Plate thickness (mm)", "10", "12"),
        ("Title block", "changed", "Date", "2026-06-02", "2026-09-15"),
        ("Parts list", "changed", "PL-101-01 thickness (mm)", "10", "12"),
        ("Parts list", "changed", "HP-101-02 quantity", "6", "7"),
        ("Parts list", "added", "BK-101-04", None, "BRACKET 150X150, AH36, 10 mm, qty 4"),
        ("Sheet text", "changed", "Text", "PLATE 10 THK AH36", "PLATE 12 THK AH36"),
        ("Sheet text", "changed", "Text", "6 NOS. HP STIFFENERS EQUALLY SPACED", "7 NOS. HP STIFFENERS EQUALLY SPACED"),
    }
    # The notes moved down the sheet because the parts list grew, but their wording is the same: not a change.
    assert all(c["old_bbox"] or c["new_bbox"] for c in compare(old, new))
    removed = {(c["kind"], c["what"]) for c in compare(new, old)}
    assert ("removed", "BK-101-04") in removed
    assert compare(new, new) == []


def has_colour(png, colour):
    pixmap = pymupdf.Pixmap(png)
    pixels = np.frombuffer(pixmap.samples, np.uint8).reshape(-1, pixmap.n)[:, :3]
    return bool((pixels == colour).all(axis=1).any())


def test_overlay_marks_removed_and_added_ink(samples):
    old, new = (samples / "01_GRSE-H-101_revA_superseded-revision.pdf").read_bytes(), (samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes()
    red, green = (198, 40, 40), (30, 142, 62)
    changed, same = overlay_png(old, new), overlay_png(new, new)
    assert has_colour(changed, red) and has_colour(changed, green)
    assert not has_colour(same, red) and not has_colour(same, green)


def test_parts_list_is_compared_with_the_erp_bill_of_materials(samples):
    def results(name):
        drawing = extract((samples / name).read_bytes())
        return {row["part_no"]: row for row in compare_bom(drawing["parts"], erp_for(drawing)["bom"])}

    assert {row["result"] for row in results("02_GRSE-H-101_revB_clean-pass.pdf").values()} == {"match"}
    stiffener = results("04_GRSE-H-103_revA_old-standard-edition.pdf")["HP-103-02"]
    assert stiffener["result"] == "mismatch" and stiffener["differences"] == [{"column": "quantity", "drawing": "9", "erp": "8"}]
    plate = results("03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf")["PL-102-01"]
    assert {d["column"] for d in plate["differences"]} == {"material", "thickness (mm)"}

    part = {"part_no": "X-1", "description": "ON DRAWING ONLY", "material": "A", "thickness_mm": "8", "qty": "1", "bbox": None}
    item = {"part_no": "X-2", "description": "IN ERP ONLY", "material": "A", "thickness_mm": 8.0, "qty": 1}
    assert [row["result"] for row in compare_bom([part], [item])] == ["not_in_erp", "not_on_drawing"]


def test_bom_rule_reports_each_difference(samples):
    _, _, findings = check(samples, "03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf")
    evidence = [f["evidence"] for f in findings if f["rule_id"] == "BOM-01"]
    assert evidence == [
        "PL-102-01: material is S275 on the drawing but AH36 in the ERP bill of materials",
        "PL-102-01: thickness (mm) is 5 on the drawing but 8 in the ERP bill of materials",
    ]
    drawing = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    no_bom = run_checks(drawing, erp_for(drawing) | {"bom": []}, RULES)
    assert [f["evidence"] for f in no_bom] == ["The ERP has no bill of materials for revision B"]


ORDER = {"order_no": "WO-1", "drawing_no": "D-1", "rev": "B", "state": "CREATED"}
DRAWING = {"current_rev": "B", "status": "APPROVED"}
CLASS_OK = {"submitted_to": "MOCK CLASS SOCIETY", "state": "APPROVED"}


def decided(verdict, decision=None):
    return {"id": 7, "verdict": verdict, "decision": decision and {"decision": decision, "decided_by": "reviewer"}}


@pytest.mark.parametrize("drawing, check_, approval, status", [
    (DRAWING, decided("PASS", "APPROVED"), CLASS_OK, "CLEAR"),
    (DRAWING, decided("BLOCKED", "APPROVED"), CLASS_OK, "CLEAR"),  # the reviewer's override stands
    (DRAWING, None, CLASS_OK, "WARN"),
    (DRAWING, decided("PASS"), CLASS_OK, "WARN"),
    (DRAWING, decided("PASS", "APPROVED"), None, "WARN"),
    (DRAWING, decided("PASS", "APPROVED"), CLASS_OK | {"state": "AWAITING"}, "WARN"),
    (DRAWING, decided("BLOCKED"), CLASS_OK, "BLOCKED"),
    (DRAWING, decided("PASS", "REJECTED"), CLASS_OK, "BLOCKED"),
    (DRAWING | {"current_rev": "C"}, decided("PASS", "APPROVED"), CLASS_OK, "BLOCKED"),
    (DRAWING | {"status": "FOR INFORMATION"}, decided("PASS", "APPROVED"), CLASS_OK, "BLOCKED"),
    (None, None, None, "BLOCKED"),
])
def test_release_gate(drawing, check_, approval, status):
    result = gate(ORDER, drawing, check_, approval)
    assert result["status"] == status
    assert bool(result["reasons"]) == (status != "CLEAR")


def test_impact_lists_work_orders_on_the_old_revision_and_open_orders_for_changed_parts(samples):
    old = extract((samples / "01_GRSE-H-101_revA_superseded-revision.pdf").read_bytes())
    new = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    work_orders = [{"order_no": "WO-A", "rev": "A"}, {"order_no": "WO-B", "rev": "B"}]
    purchase_orders = [
        {"po_no": "PO-1", "part_no": "PL-101-01", "state": "OPEN"},      # thickness changed
        {"po_no": "PO-2", "part_no": "HP-101-02", "state": "RECEIVED"},  # changed, but already delivered
        {"po_no": "PO-3", "part_no": "FB-101-03", "state": "OPEN"},      # unchanged part
    ]
    result = impact(compare(old, new), "A", work_orders, purchase_orders)
    assert [order["order_no"] for order in result["work_orders"]] == ["WO-A"]
    assert [(po["po_no"], po["change"]) for po in result["purchase_orders"]] == [("PO-1", "thickness (mm) 10 to 12")]


# --- Scanned drawings. These need the Tesseract program, so they are skipped on a machine without it. ---

needs_ocr = pytest.mark.skipif(ocr.find_tesseract() is None, reason="Tesseract is not installed")
SCAN_A, SCAN_B = "06_GRSE-H-101_revA_scanned-copy.pdf", "07_GRSE-H-101_revB_scanned-copy.pdf"


@needs_ocr
def test_scanned_drawing_is_read_like_the_original(samples):
    scan = extract((samples / SCAN_B).read_bytes())
    original = extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes())
    assert (scan["source"], original["source"]) == ("scan", "vector")
    assert {n: f["value"] for n, f in scan["fields"].items()} == {n: f["value"] for n, f in original["fields"].items()}
    assert all(50 <= f["confidence"] <= 100 and f["bbox"] for f in scan["fields"].values())
    columns = ("part_no", "description", "material", "thickness_mm", "qty")
    assert [[p[c] for c in columns] for p in scan["parts"]] == [[p[c] for c in columns] for p in original["parts"]]
    assert [(s["name"], s["edition"]) for s in scan["standards"]] == [(s["name"], s["edition"]) for s in original["standards"]]


@needs_ocr
def test_scanned_drawings_get_the_same_verdicts(samples):
    assert check(samples, SCAN_B)[:2] == ("PASS", set())
    assert check(samples, SCAN_A)[:2] == ("BLOCKED", {"REG-01", "CHK-08"})


@needs_ocr
def test_two_scans_are_compared_like_their_originals(samples):
    scans = compare(extract((samples / SCAN_A).read_bytes()), extract((samples / SCAN_B).read_bytes()))
    originals = compare(extract((samples / "01_GRSE-H-101_revA_superseded-revision.pdf").read_bytes()),
                        extract((samples / "02_GRSE-H-101_revB_clean-pass.pdf").read_bytes()))
    summary = lambda changes: sorted((c["area"], c["kind"], c["what"], c["old"], c["new"]) for c in changes)
    assert summary(scans) == summary(originals)


def coloured_share(png):
    """How much of the ink in an overlay is marked as removed or added."""
    pixmap = pymupdf.Pixmap(png)
    pixels = np.frombuffer(pixmap.samples, np.uint8).reshape(-1, pixmap.n)[:, :3]
    ink = (pixels != 255).any(axis=1)
    changed = ink & ~(pixels == (165, 165, 165)).all(axis=1)
    return changed.sum() / ink.sum()


def test_crooked_scans_are_straightened_before_comparing(samples, tmp_path):
    from scripts.make_samples import scan

    original = samples / "02_GRSE-H-101_revB_clean-pass.pdf"
    left = scan(original, tmp_path / "left.pdf", 0.4, (6, -5), seed=1).read_bytes()
    right = scan(original, tmp_path / "right.pdf", -0.3, (-4, 7), seed=2).read_bytes()
    # The same sheet scanned twice, crooked in opposite directions: once straightened, almost nothing is marked as changed.
    assert coloured_share(overlay_png(left, right)) < 0.03
    # Two different revisions scanned: the real changes still show.
    assert coloured_share(overlay_png((samples / SCAN_A).read_bytes(), (samples / SCAN_B).read_bytes())) > 0.10


# --- Rules that depend on where the plate is, and on a calculation. ---

def findings_of(samples, name, rule_id, **erp_changes):
    drawing = extract((samples / name).read_bytes())
    return [f["evidence"] for f in run_checks(drawing, erp_for(drawing) | erp_changes, RULES) if f["rule_id"] == rule_id]


def test_required_thickness_is_calculated_from_zone_ship_length_and_spacing(samples):
    # Deck, L = 142 m: 4.5 + 0.04 * 142 = 10.18 mm. Revision A's 10 mm plate fails; revision B's 12 mm passes.
    too_thin = findings_of(samples, "01_GRSE-H-101_revA_superseded-revision.pdf", "CHK-08")
    assert too_thin == [
        "Title block: 10 mm is below the 10.2 mm required in zone DECK (4.5 + 0.04 * L, with L = 142 m and s = 700 mm)",
        "Part PL-101-01: 10 mm is below the 10.2 mm required in zone DECK (4.5 + 0.04 * L, with L = 142 m and s = 700 mm)",
    ]
    assert findings_of(samples, "02_GRSE-H-101_revB_clean-pass.pdf", "CHK-08") == []
    # The same drawing on a longer ship needs more: 4.5 + 0.04 * 200 = 12.5 mm, so even 12 mm fails.
    longer_ship = findings_of(samples, "02_GRSE-H-101_revB_clean-pass.pdf", "CHK-08", ship={"rule_length_m": 200.0})
    assert len(longer_ship) == 2 and "12.5 mm required" in longer_ship[0]
    # Bulkhead: the formula uses spacing instead. 4.0 + 0.005 * 700 = 7.5 mm.
    assert "7.5 mm required in zone BULKHEAD" in findings_of(samples, "03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf", "CHK-08")[0]
    # A hull the ERP does not know: the rule says it could not calculate, instead of passing silently.
    unknown = findings_of(samples, "02_GRSE-H-101_revB_clean-pass.pdf", "CHK-08", ship=None)
    assert len(unknown) == 1 and "could not be calculated" in unknown[0]


def test_spacing_limit_and_grade_depend_on_the_zone(samples):
    side_shell = "04_GRSE-H-103_revA_old-standard-edition.pdf"
    assert findings_of(samples, side_shell, "CHK-09") == ["Stiffener spacing 800 mm is over the 750 mm allowed in zone SIDE SHELL"]
    assert findings_of(samples, "02_GRSE-H-101_revB_clean-pass.pdf", "CHK-09") == []
    # 14 mm side shell plate is DH36, which the zone rule accepts. The same plate in grade AH36 would not be.
    assert findings_of(samples, side_shell, "CHK-10") == []
    drawing = extract((samples / side_shell).read_bytes())
    drawing["fields"]["material"]["value"] = "AH36"
    wrong_grade = [f["evidence"] for f in run_checks(drawing, erp_for(drawing), RULES) if f["rule_id"] == "CHK-10"]
    assert wrong_grade == ["Title block: 14 mm plate in zone SIDE SHELL is grade 'AH36'; over 12.5 mm it must be DH36 or EH36"]


def test_count_in_a_note_must_agree_with_the_parts_list(samples):
    name = "02_GRSE-H-101_revB_clean-pass.pdf"
    assert findings_of(samples, name, "CHK-11") == []
    drawing = extract((samples / name).read_bytes())
    drawing["text"] = drawing["text"].replace("7 NOS. HP STIFFENERS", "9 NOS. HP STIFFENERS")
    mismatch = [f["evidence"] for f in run_checks(drawing, erp_for(drawing), RULES) if f["rule_id"] == "CHK-11"]
    assert mismatch == ["The sheet says 9 (9 NOS. HP STIFFENERS), but the parts list has 7 of HP STIFFENER"]


def test_formulas_allow_arithmetic_and_nothing_else():
    from app.core.formula import evaluate

    assert evaluate("4.5 + 0.04 * L", {"L": 142.0}) == pytest.approx(10.18)
    assert evaluate("max(6, s / 100 * sqrt(L)) - 1", {"L": 100.0, "s": 700.0}) == pytest.approx(69.0)
    for bad in ("__import__('os').system('echo hi')", "L.real", "open('x')", "[1, 2][0]", "lambda: 1", "t + 1", "1 / 0", "1 +"):
        with pytest.raises(ValueError):
            evaluate(bad, {"L": 100.0})


def test_search_finds_the_matching_lines():
    from app.core.retrieve import Index, passages

    text = "RELEASE GATE (work orders)\n- WO-24018: GRSE-H-101 rev A, BLOCKED.\n- WO-24019: GRSE-H-101 rev B, CLEAR.\nRULES\n- CHK-03 Material grade: critical"
    found = passages(text)
    assert found[0] == "RELEASE GATE (work orders): - WO-24018: GRSE-H-101 rev A, BLOCKED."
    index = Index(found)
    assert index.search("why is wo-24018 blocked", 1) == [found[0]]
    assert index.search("which rules check the grade", 1) == [found[2]]
    assert index.search("weather tomorrow", 3) == []  # nothing shares a word: nothing is sent
