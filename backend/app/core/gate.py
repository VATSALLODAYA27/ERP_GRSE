"""The release gate: may this work order be released against the drawing revision it names?

This is an answer the ERP can ask for. Nothing here writes to the ERP.
"""

RELEASABLE = ("APPROVED",)  # register statuses that may go to production; keep in step with rule CHK-01
LEVELS = ("CLEAR", "WARN", "BLOCKED")


def gate(order: dict, drawing: dict | None, check: dict | None, approval: dict | None) -> dict:
    """order: the work order. drawing: its register row. check: the latest check of that drawing revision.
    approval: the class or customer approval of that revision. Any of the last three may be missing."""
    reasons = []  # (level, text)

    if drawing is None:
        reasons.append(("BLOCKED", "The drawing is not in the register"))
    else:
        if order["rev"] != drawing["current_rev"]:
            reasons.append(("BLOCKED", f"Revision {order['rev']} is superseded; the register's current revision is {drawing['current_rev']}"))
        if drawing["status"] not in RELEASABLE:
            reasons.append(("BLOCKED", f"Register status is '{drawing['status']}', not approved for production"))

    if check is None:
        reasons.append(("WARN", "This revision has not been checked"))
    elif check["decision"] is None:
        level = "BLOCKED" if check["verdict"] == "BLOCKED" else "WARN"
        reasons.append((level, f"Check #{check['id']} is {check['verdict'].replace('_', ' ')} and awaits a decision"))
    elif check["decision"]["decision"] == "REJECTED":
        reasons.append(("BLOCKED", f"Rejected by {check['decision']['decided_by']} (check #{check['id']})"))

    if approval is None:
        reasons.append(("WARN", "No class or customer approval is on record for this revision"))
    elif approval["state"] != "APPROVED":
        reasons.append(("WARN", f"{approval['submitted_to']} approval: {approval['state']}"))

    status = max((level for level, _ in reasons), key=LEVELS.index, default="CLEAR")
    return {"status": status, "reasons": [text for _, text in reasons]}
