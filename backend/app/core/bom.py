"""Does the parts list on the drawing agree with the ERP bill of materials for the same revision?"""

COLUMNS = {"material": "material", "thickness_mm": "thickness (mm)", "qty": "quantity"}


def _text(value) -> str:
    """12.0 from the ERP and '12' from the drawing are the same value."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def compare_bom(parts: list, bom: list) -> list:
    """One row per part number found on either side. result: match, mismatch, not_in_erp or not_on_drawing."""
    in_erp = {item["part_no"]: item for item in bom}
    rows = []
    for part in parts:
        item = in_erp.pop(part["part_no"], None)
        drawing = {column: _text(part[column]) for column in COLUMNS}
        erp = item and {column: _text(item[column]) for column in COLUMNS}
        differences = [
            {"column": label, "drawing": drawing[column], "erp": erp[column]}
            for column, label in COLUMNS.items() if erp and drawing[column] != erp[column]
        ]
        rows.append({
            "part_no": part["part_no"], "description": part["description"], "drawing": drawing, "erp": erp,
            "result": "not_in_erp" if erp is None else "mismatch" if differences else "match",
            "differences": differences, "bbox": part["bbox"],
        })
    for item in in_erp.values():
        rows.append({
            "part_no": item["part_no"], "description": item["description"], "drawing": None,
            "erp": {column: _text(item[column]) for column in COLUMNS},
            "result": "not_on_drawing", "differences": [], "bbox": None,
        })
    return rows
