"""Who is affected when a drawing moves from one revision to the next?

Work orders still pointing at the old revision, and open purchase orders for parts that changed.
"""


def impact(changes: list, from_revision: str, work_orders: list, purchase_orders: list) -> dict:
    """changes: the list from diff.compare(). work_orders: those for this drawing. purchase_orders: all of them."""
    affected = {}  # part number -> what happened to it
    for change in changes:
        if change["area"] != "Parts list":
            continue
        if change["kind"] == "changed":
            label = change["what"].removeprefix(change["part_no"]).strip()
            text = f"{label} {change['old']} to {change['new']}"
        else:
            text = change["kind"]
        affected.setdefault(change["part_no"], []).append(text)

    return {
        "from_revision": from_revision,
        "work_orders": [order for order in work_orders if order["rev"] == from_revision],
        "purchase_orders": [
            {**po, "change": "; ".join(affected[po["part_no"]])}
            for po in purchase_orders if po["state"] == "OPEN" and po["part_no"] in affected
        ],
    }
