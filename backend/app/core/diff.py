"""What changed between two revisions of a drawing.

Two views of the same question:
- compare():     a list of changes read from the text (title block, parts list, other text on the sheet)
- overlay_png(): a picture of where the ink differs, which also catches redrawn lines the text cannot show
"""
from collections import Counter

from difflib import SequenceMatcher

import cv2
import numpy as np
import pymupdf

from .extract import key

FIELD_LABELS = {
    "title": "Title", "drawing_no": "Drawing number", "revision": "Revision", "status": "Status",
    "material": "Material", "thickness_mm": "Plate thickness (mm)", "date": "Date",
    "hull_no": "Hull number", "zone": "Zone", "spacing_mm": "Stiffener spacing (mm)",
}
PART_LABELS = {"item": "item no.", "description": "description", "material": "material", "thickness_mm": "thickness (mm)", "qty": "quantity"}
SAME_PLACE = 3  # points: text that changed but starts at the same spot is one change, not a removal plus an addition
SAME_PLACE_SCAN = 14  # a scan is shifted and slightly turned, so "the same spot" is looser

REMOVED, ADDED, UNCHANGED = (198, 40, 40), (30, 142, 62), (165, 165, 165)
INK = 200  # grey level below which a pixel counts as drawn


def _change(area, kind, what, old=None, new=None, old_bbox=None, new_bbox=None, part_no=None) -> dict:
    return {"area": area, "kind": kind, "what": what, "old": old, "new": new, "old_bbox": old_bbox, "new_bbox": new_bbox, "part_no": part_no}


def _describe(part) -> str:
    return f"{part['description']}, {part['material']}, {part['thickness_mm']} mm, qty {part['qty']}"


def _digits(text: str) -> str:
    """The numbers in a line. Two lines with different numbers are never "the same line misread": 10 mm and 12 mm differ."""
    return "".join(c for c in text if c.isdigit())


def _notes(lines) -> list:
    """Lines worth reporting. A bare one- or two-digit number is an item balloon: the parts list already covers a new or removed item."""
    return [line for line in lines if not (line["text"].isdigit() and len(line["text"]) <= 2)]


def _only_in(lines, other) -> list:
    """Lines with no partner of the same text in `other`. Repeated text is matched one for one."""
    available = Counter(key(line["text"]) for line in other)  # letters and digits only: spacing and punctuation are not changes
    unmatched = []
    for line in lines:
        if available[key(line["text"])]:
            available[key(line["text"])] -= 1
        else:
            unmatched.append(line)
    return unmatched


def compare(old: dict, new: dict) -> list:
    changes = []

    for name, label in FIELD_LABELS.items():
        before, after = old["fields"][name], new["fields"][name]
        if before["value"] != after["value"]:
            changes.append(_change("Title block", "changed", label, before["value"], after["value"], before["bbox"], after["bbox"]))

    old_parts = {p["part_no"]: p for p in old["parts"]}
    new_parts = {p["part_no"]: p for p in new["parts"]}
    for part_no, part in new_parts.items():
        before = old_parts.get(part_no)
        if before is None:
            changes.append(_change("Parts list", "added", part_no, new=_describe(part), new_bbox=part["bbox"], part_no=part_no))
            continue
        for column, label in PART_LABELS.items():
            if before[column] != part[column]:
                changes.append(_change("Parts list", "changed", f"{part_no} {label}", before[column], part[column], before["bbox"], part["bbox"], part_no))
    for part_no, part in old_parts.items():
        if part_no not in new_parts:
            changes.append(_change("Parts list", "removed", part_no, old=_describe(part), old_bbox=part["bbox"], part_no=part_no))

    scanned = "scan" in (old["source"], new["source"])
    near = SAME_PLACE_SCAN if scanned else SAME_PLACE
    removed, added = (_notes(side) for side in (_only_in(old["lines"], new["lines"]), _only_in(new["lines"], old["lines"])))
    if scanned:
        # The same line read slightly differently by OCR on each sheet (one wrong letter) is not a change.
        for line in list(added):
            twin = next((r for r in removed if _digits(r["text"]) == _digits(line["text"])
                         and SequenceMatcher(None, key(r["text"]), key(line["text"])).ratio() >= 0.9), None)
            if twin:
                removed.remove(twin)
                added.remove(line)
    for line in added:
        before = next((r for r in removed if abs(r["bbox"][0] - line["bbox"][0]) < near and abs(r["bbox"][1] - line["bbox"][1]) < near), None)
        if before:
            removed.remove(before)
            changes.append(_change("Sheet text", "changed", "Text", before["text"], line["text"], before["bbox"], line["bbox"]))
        else:
            changes.append(_change("Sheet text", "added", "Text", new=line["text"], new_bbox=line["bbox"]))
    for line in removed:
        changes.append(_change("Sheet text", "removed", "Text", old=line["text"], old_bbox=line["bbox"]))

    return changes


def _thicken(mask):
    """Grow a mask by one pixel each way, so a one-pixel line that changed is still visible when the image is scaled down."""
    grown = mask.copy()
    grown[1:, :] |= mask[:-1, :]
    grown[:-1, :] |= mask[1:, :]
    grown[:, 1:] |= mask[:, :-1]
    grown[:, :-1] |= mask[:, 1:]
    return grown


def _grey(pixmap):
    return np.frombuffer(pixmap.samples, np.uint8).reshape(pixmap.height, pixmap.stride)[:, :pixmap.width]


def _straighten(old, new):
    """Shift and turn the old picture until it sits on the new one. Two scans of the same sheet never line up by themselves."""
    small = 0.25  # the fit is found on quarter-size pictures, which is much faster and accurate enough
    a = cv2.GaussianBlur(cv2.resize(old, None, fx=small, fy=small, interpolation=cv2.INTER_AREA), (5, 5), 0)
    b = cv2.GaussianBlur(cv2.resize(new, None, fx=small, fy=small, interpolation=cv2.INTER_AREA), (5, 5), 0)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
        _, warp = cv2.findTransformECC(b, a, warp, cv2.MOTION_EUCLIDEAN, criteria)
    except cv2.error:
        return old  # no fit found: compare as they are; the overlay will show the misalignment
    warp[:, 2] /= small
    return cv2.warpAffine(old, warp, (new.shape[1], new.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=255)


def overlay_png(old_pdf: bytes, new_pdf: bytes, dpi: int = 110) -> bytes:
    """Both sheets on top of each other: grey where they agree, red where only the old one has ink, green where only the new one has."""
    with pymupdf.open(stream=old_pdf, filetype="pdf") as old_doc, pymupdf.open(stream=new_pdf, filetype="pdf") as new_doc:
        new_page, old_page = new_doc[0], old_doc[0]
        scanned = not (old_page.get_text().strip() and new_page.get_text().strip())
        new = new_page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        if old_page.rect == new_page.rect:
            old = old_page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        else:
            # A different paper size is stretched to the new sheet's pixel size, so the two still line up corner to corner.
            scale = pymupdf.Matrix(new.width / old_page.rect.width, new.height / old_page.rect.height)
            old = old_page.get_pixmap(matrix=scale, colorspace=pymupdf.csGRAY)
        height, width = min(old.height, new.height), min(old.width, new.width)
        old_grey, new_grey = _grey(old)[:height, :width], _grey(new)[:height, :width]

    if scanned:
        old_grey = _straighten(old_grey, new_grey)
    before, after = old_grey < INK, new_grey < INK

    # Ink counts as removed only if the new sheet has none close to it (and the same for added), so small differences
    # between two pictures of the same line are not reported as changes. Scans get a wider margin than exact renderings.
    def nearby(mask):
        for _ in range(3 if scanned else 1):
            mask = _thicken(mask)
        return mask

    image = np.full((height, width, 3), 255, np.uint8)
    image[before | after] = UNCHANGED
    image[_thicken(before & ~nearby(after))] = REMOVED
    image[_thicken(after & ~nearby(before))] = ADDED
    return pymupdf.Pixmap(pymupdf.csRGB, width, height, image.tobytes(), False).tobytes("png")
