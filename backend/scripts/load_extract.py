"""Refresh the tool's copy of the ERP extract from the CSV files.

Replaces the extract tables only. Checks and findings are never touched, and nothing is written back to the ERP.
Drawings and revisions that an admin added or edited in the tool, and class approvals recorded in the tool, are kept as they are:
the extract does not overwrite them.
Run from backend/:  python -m scripts.load_extract
"""
import csv

from sqlalchemy import select

from app import config, models
from app.db import SessionLocal, migrate

TABLES = {  # CSV file name -> table, parents before children
    "drawing_register": models.Drawing,
    "drawing_revisions": models.DrawingRevision,
    "engineering_change_notes": models.ChangeNote,
    "bill_of_materials": models.BomItem,
    "work_orders": models.WorkOrder,
    "purchase_orders": models.PurchaseOrder,
    "class_approvals": models.ClassApproval,
    "ship_particulars": models.ShipParticulars,
}


def load(session, extract_dir=config.EXTRACT_DIR) -> dict:
    counts = {}
    editable = (models.Drawing, models.DrawingRevision, models.ClassApproval)
    for model in reversed(TABLES.values()):
        rows = session.query(model)
        (rows.filter(model.source == "erp") if model in editable else rows).delete()
    kept = set(session.scalars(select(models.Drawing.drawing_no)))  # what is left is the admin's
    # shortcut: a recorded approval can point at an ERP drawing that is deleted and re-added here, which SQLite allows;
    # a database server that enforces foreign keys immediately would need the constraint made deferrable.
    recorded = {tuple(row) for row in session.execute(select(models.ClassApproval.drawing_no, models.ClassApproval.rev))}
    for stem, model in TABLES.items():
        columns = model.__table__.c
        with open(extract_dir / f"{stem}.csv", newline="", encoding="utf-8") as f:
            rows = [model(**{k: columns[k].type.python_type(v) for k, v in row.items()}) for row in csv.DictReader(f)
                    if not (model in editable and row["drawing_no"] in kept)
                    and not (model is models.ClassApproval and (row["drawing_no"], row["rev"]) in recorded)]
        session.add_all(rows)
        counts[stem] = len(rows)
    session.commit()
    return counts


if __name__ == "__main__":
    migrate()
    with SessionLocal() as session:
        for name, count in load(session).items():
            print(f"{name}: {count} rows")
