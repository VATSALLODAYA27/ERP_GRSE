"""Fixed compliance checks.

A rule in rules.json picks one check type below and supplies its parameters, severity and clause.
Nothing here is learned or model-generated: the same drawing always gives the same findings.

Each check takes (drawing, erp, params) and yields (evidence, bbox) for every problem it finds.
`erp` is what the ERP extract holds for this drawing:
{"register": its register row or None, "bom": its bill of materials rows, "ship": the particulars of its hull or None}.
"""
import json
import re
from difflib import SequenceMatcher

from .bom import compare_bom
from .extract import key
from .formula import evaluate


def _val(d, field):
    return d["fields"][field]["value"]


def _box(d, field):
    return d["fields"][field]["bbox"]


def _everywhere(d, field):
    """A property as stated in the title block and on every parts-list row."""
    yield "Title block", _val(d, field), _box(d, field)
    for part in d["parts"]:
        yield f"Part {part['part_no']}", part[field], part["bbox"]


def register_revision(d, erp, p):
    reg = erp["register"]
    no, rev = _val(d, "drawing_no"), _val(d, "revision")
    if reg is None:
        yield f"Drawing '{no or '(unreadable)'}' is not in the drawing register", _box(d, "drawing_no")
    elif not rev:
        yield "Revision could not be read from the title block", None
    elif rev != reg["current_rev"]:
        # shortcut: revisions compared as text (A < B < C); needs a real ordering if revisions look like P01 or A1
        kind = "superseded" if rev < reg["current_rev"] else "not in the register"
        yield f"Revision {rev} is {kind}; register current revision is {reg['current_rev']}", _box(d, "revision")


def register_status(d, erp, p):
    reg = erp["register"]
    status = _val(d, "status")
    if reg and status != reg["status"]:
        yield f"Title block status is '{status}' but the register says '{reg['status']}'", _box(d, "status")


def approval_status(d, erp, p):
    reg = erp["register"]
    status = _val(d, "status")
    if status not in p["allowed"]:
        yield f"Title block status '{status or '(unreadable)'}' is not released for production", _box(d, "status")
    if reg and reg["status"] not in p["allowed"] and reg["status"] != status:
        yield f"Register status '{reg['status']}' is not released for production", None


def standard_edition(d, erp, p):
    cited = {key(s["name"]): s for s in d["standards"]}  # compared without punctuation, which OCR often gets wrong
    for name, edition in p["required"].items():
        found = cited.get(key(name))
        if found is None:
            yield f"Required standard '{name}' is not cited", None
        elif found["edition"] != edition:
            yield f"Cites '{name}' edition {found['edition']}; required edition is {edition}", found["bbox"]


def allowed_grades(d, erp, p):
    for where, grade, bbox in _everywhere(d, "material"):
        if grade not in p["grades"]:
            yield f"{where}: material grade '{grade or '(unreadable)'}' is not an allowed grade", bbox


def min_thickness(d, erp, p):
    for where, raw, bbox in _everywhere(d, "thickness_mm"):
        try:
            thickness = float(raw)
        except ValueError:
            yield f"{where}: thickness '{raw}' could not be read as a number", bbox
            continue
        if thickness < p["min_mm"]:
            yield f"{where}: thickness {thickness:g} mm is below the minimum {p['min_mm']:g} mm", bbox


def mandatory_notes(d, erp, p):
    text = key(d["text"])
    for note in p["notes"]:
        if key(note) in text:
            continue
        # On a scan one misread letter must not turn a note that is there into a finding: accept a line that is nearly the note.
        nearly = d["source"] == "scan" and any(
            SequenceMatcher(None, key(note), key(re.sub(r"^\d+\.", "", line["text"]))).ratio() >= 0.85 for line in d["lines"])
        if not nearly:
            yield f"Note not found on the drawing: '{note}'", None


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _members(d, keyword):
    """Thickness and grade of the drawing's main member: the title block, and every parts-list row of that kind (e.g. PLATE)."""
    yield "Title block", _val(d, "thickness_mm"), _val(d, "material"), _box(d, "thickness_mm")
    for part in d["parts"]:
        if keyword in part["description"].upper():
            yield f"Part {part['part_no']}", part["thickness_mm"], part["material"], part["bbox"]


def required_thickness(d, erp, p):
    """Thickness worked out from a formula that depends on the zone, the ship's length L (m) and the stiffener spacing s (mm)."""
    zone = _val(d, "zone")
    formula = p["formulas"].get(zone)
    if formula is None:
        return  # this rule sets no requirement for this zone
    ship, spacing = erp["ship"], _number(_val(d, "spacing_mm"))
    if ship is None:
        yield (f"Hull '{_val(d, 'hull_no') or '(unreadable)'}' is not in the ERP ship particulars, "
               f"so the thickness required in zone {zone} could not be calculated"), _box(d, "hull_no")
        return
    if spacing is None:
        yield f"Stiffener spacing could not be read, so the thickness required in zone {zone} could not be calculated", _box(d, "spacing_mm")
        return
    length = ship["rule_length_m"]
    required = evaluate(formula, {"L": length, "s": spacing})
    for where, raw, _, bbox in _members(d, p["member"]):
        thickness = _number(raw)
        if thickness is not None and thickness < required:
            yield (f"{where}: {thickness:g} mm is below the {required:.1f} mm required in zone {zone} "
                   f"({formula}, with L = {length:g} m and s = {spacing:g} mm)"), bbox


def max_spacing(d, erp, p):
    zone = _val(d, "zone")
    limit = p["limits_mm"].get(zone)
    if limit is None:
        return
    spacing = _number(_val(d, "spacing_mm"))
    if spacing is None:
        yield f"Stiffener spacing could not be read; the limit in zone {zone} is {limit:g} mm", _box(d, "spacing_mm")
    elif spacing > limit:
        yield f"Stiffener spacing {spacing:g} mm is over the {limit:g} mm allowed in zone {zone}", _box(d, "spacing_mm")


def grade_by_zone(d, erp, p):
    zone = _val(d, "zone")
    for band in p["zones"].get(zone, []):
        for where, raw, grade, bbox in _members(d, p["member"]):
            thickness = _number(raw)
            if thickness is not None and thickness > band["over_mm"] and grade not in band["grades"]:
                yield (f"{where}: {thickness:g} mm plate in zone {zone} is grade '{grade}'; "
                       f"over {band['over_mm']:g} mm it must be {' or '.join(band['grades'])}"), bbox


def count_matches_parts(d, erp, p):
    """A number stated in a note on the sheet (e.g. "7 NOS. HP STIFFENERS") against the quantity in the parts list."""
    stated = re.search(p["pattern"], d["text"])
    quantities = [_number(part["qty"]) for part in d["parts"] if p["part"] in part["description"].upper()]
    if stated and quantities and None not in quantities and int(stated.group(1)) != sum(quantities):
        yield (f"The sheet says {stated.group(1)} ({stated.group(0)}), "
               f"but the parts list has {sum(quantities):g} of {p['part']}"), next(part["bbox"] for part in d["parts"] if p["part"] in part["description"].upper())


def bom_consistency(d, erp, p):
    if erp["register"] is None:
        return  # a drawing the ERP does not know is already reported by the register check
    if not erp["bom"]:
        yield f"The ERP has no bill of materials for revision {_val(d, 'revision')}", None
        return
    for row in compare_bom(d["parts"], erp["bom"]):
        if row["result"] == "not_in_erp":
            yield f"{row['part_no']} is on the drawing but not in the ERP bill of materials", row["bbox"]
        elif row["result"] == "not_on_drawing":
            yield f"{row['part_no']} is in the ERP bill of materials but not on the drawing", None
        for diff in row["differences"]:
            yield f"{row['part_no']}: {diff['column']} is {diff['drawing']} on the drawing but {diff['erp']} in the ERP bill of materials", row["bbox"]


CHECKS = {
    f.__name__: f
    for f in (register_revision, register_status, approval_status, standard_edition, allowed_grades, min_thickness, mandatory_notes, bom_consistency,
              required_thickness, max_spacing, grade_by_zone, count_matches_parts)
}
SEVERITIES = ("critical", "major", "minor")


def load_rules(path) -> list:
    rules = json.loads(path.read_text(encoding="utf-8"))
    for rule in rules:
        if rule["type"] not in CHECKS or rule["severity"] not in SEVERITIES or not rule["clause"]:
            raise ValueError(f"Rule {rule.get('id')} has an unknown type or severity, or no clause")
        for formula in rule.get("params", {}).get("formulas", {}).values():
            try:
                evaluate(formula, {"L": 100.0, "s": 700.0})  # a rule with a broken formula is refused when the file is read
            except ValueError as e:
                raise ValueError(f"Rule {rule['id']}: {e}") from e
    return rules


def run_checks(drawing: dict, erp: dict, rules: list) -> list:
    findings = []
    for rule in rules:
        if rule["state"] != "approved":
            continue
        for evidence, bbox in CHECKS[rule["type"]](drawing, erp, rule.get("params", {})):
            findings.append({
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "clause": rule["clause"],
                "standard": f"{rule['standard']}, edition {rule['edition']}",
                "evidence": evidence,
                "bbox": bbox,
            })
    # Worst first; within a severity, rule order is kept.
    return sorted(findings, key=lambda f: SEVERITIES.index(f["severity"]))


def verdict(findings: list) -> str:
    severities = {f["severity"] for f in findings}
    return "BLOCKED" if "critical" in severities else "NEEDS_REVIEW" if "major" in severities else "PASS"
