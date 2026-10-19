"""Read a drawing PDF into plain data.

Template-based: the title-block position, labels and box sizes below describe the MOCK sheet layout.
A real GRSE title block needs its own values here.

Two ways in, one result:
- a vector PDF has real text, which is read exactly;
- a scanned PDF is a picture, which is read by OCR. Every value then carries a confidence, and a person confirms the title block.
"""
import copy
import re
from difflib import SequenceMatcher
from functools import lru_cache

import pymupdf

from . import ocr

TITLE_BLOCK = (0.55, 0.86, 1.0, 1.0)  # where the title block sits, as fractions of the page: x0, y0, x1, y1
VALUE_HEIGHT = 18  # points of height read under each label
FIELDS = {  # field -> (label as printed, width in points of the value box under it)
    "title": ("TITLE", 295),
    "drawing_no": ("DRG.NO.", 175),
    "revision": ("REV.", 45),
    "status": ("STATUS", 125),
    "material": ("MATERIAL", 85),
    "thickness_mm": ("THK(MM)", 65),
    "date": ("DATE", 135),
    "hull_no": ("HULL.NO.", 115),
    "zone": ("ZONE", 195),          # the structural zone the drawing covers; rules that depend on location use it
    "spacing_mm": ("SPACING(MM)", 155),  # stiffener spacing
}
PARTS_COLUMNS = ["item", "part_no", "description", "material", "thickness_mm", "qty"]
PARTS_HEADERS = ["ITEM", "PART", "DESCRIPTION", "MATL", "THK", "QTY"]  # first word of each column heading
STANDARD_LINE = re.compile(r"^(?P<name>[A-Z][A-Z0-9 .\-]+?), EDITION (?P<edition>\d{4})\s*$", re.M)
STANDARD_LINE_OCR = re.compile(r"^(?P<name>[A-Z][A-Z0-9 .\-]+?)[,.]? EDITION (?P<edition>\d{4})\b")

OCR_DPI = 200
CELL_DPI = 400  # a single table cell is re-read at a larger size
REREAD = {"material": False, "thickness_mm": True, "qty": True}  # columns re-read when empty -> digits only?
ROW_PITCH = 16  # points between parts-list rows on the mock sheet
LAST_COLUMN_WIDTH = 60  # points; the last column has no next heading to end it
MIN_LINE_CONFIDENCE = 60  # loose text on the sheet needs more certainty than text found under a known label


class UnreadableDrawing(ValueError):
    pass


def key(text: str) -> str:
    """Text with everything but letters and digits removed, for comparing what OCR read with what was expected."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def extract(pdf_bytes: bytes) -> dict:
    # Reading a scan takes several seconds, and the same file is read twice (once to show what was read,
    # once to run the check), so recent results are remembered. A copy is handed out because callers change it.
    return copy.deepcopy(_extract(pdf_bytes))


@lru_cache(maxsize=8)
def _extract(pdf_bytes: bytes) -> dict:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except (RuntimeError, ValueError) as e:
        raise UnreadableDrawing("The file is not a readable PDF.") from e
    with doc:
        if doc.page_count == 0:
            raise UnreadableDrawing("The PDF has no pages.")
        page = doc[0]  # shortcut: sheet 1 only; loop over pages when multi-sheet drawings are in scope
        w, h = page.rect.width, page.rect.height
        x0, y0, x1, y1 = TITLE_BLOCK
        title_block = pymupdf.Rect(x0 * w, y0 * h, x1 * w, y1 * h)
        text = page.get_text()
        if not text.strip():
            return _extract_scan(page, title_block)
        parts, parts_table = _parts(page)
        return {
            "source": "vector",
            "fields": _title_block(page, title_block),
            "standards": _standards(page, text),
            "parts": parts,
            # Everything else written on the sheet: notes, standards, annotations on the structure.
            "lines": _lines(page, exclude=[title_block, parts_table]),
            "text": " ".join(text.upper().split()),
            "page_size": [w, h],
        }


# --- Vector PDFs: the text is in the file. ---


def _title_block(page, clip) -> dict:
    words = page.get_text("words", clip=clip)
    fields = {}
    for name, (label, width) in FIELDS.items():
        value, bbox = "", None
        hit = next((word for word in words if word[4] == label), None)
        if hit:
            box = pymupdf.Rect(hit[0] - 1, hit[3], hit[0] + width, hit[3] + VALUE_HEIGHT)
            value = " ".join(page.get_textbox(box).split())
            bbox = list(box) if value else None
        fields[name] = {"value": value, "bbox": bbox}
    return fields


def _standards(page, text) -> list:
    standards = []
    for m in STANDARD_LINE.finditer(text):
        hits = page.search_for(m.group(0).strip())
        standards.append({"name": m["name"], "edition": int(m["edition"]), "bbox": list(hits[0]) if hits else None})
    return standards


def _parts(page) -> tuple:
    """The parts list rows, and where the table sits on the sheet."""
    for table in page.find_tables().tables:
        rows = table.extract()
        if rows and "PART NO" in [(cell or "").strip() for cell in rows[0]]:
            parts = [
                dict(zip(PARTS_COLUMNS, ((cell or "").strip() for cell in cells)), bbox=list(row.bbox))
                for cells, row in zip(rows[1:], table.rows[1:])
            ]
            return parts, pymupdf.Rect(table.bbox)
    return [], None


def _lines(page, exclude) -> list:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = " ".join("".join(span["text"] for span in line["spans"]).split())
            box = pymupdf.Rect(line["bbox"])
            centre = (box.tl + box.br) / 2
            if text and not any(region and region.contains(centre) for region in exclude):
                lines.append({"text": text, "bbox": list(box)})
    return lines


# --- Scanned PDFs: the page is a picture, read by OCR. ---


def _centre(word) -> pymupdf.Point:
    x0, y0, x1, y1 = word["box"]
    return pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)


def _join(words) -> dict:
    """Words that belong together, as one piece of text with its place and the lowest confidence among them."""
    words = sorted(words, key=lambda word: word["box"][0])
    box = pymupdf.Rect()
    for word in words:
        box |= pymupdf.Rect(word["box"])
    return {"text": " ".join(word["text"] for word in words), "bbox": list(box), "confidence": min(word["confidence"] for word in words)}


def _extract_scan(page, title_block) -> dict:
    if ocr.find_tesseract() is None:
        raise UnreadableDrawing("This is a scanned drawing, and the OCR program (Tesseract) is not installed on the server.")
    png = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY).tobytes("png")
    try:
        words = ocr.read_words(png, OCR_DPI)
    except Exception as e:  # the OCR program failing must not take the server down with it
        raise UnreadableDrawing(f"The scanned drawing could not be read by OCR: {e}") from e
    if not words:
        raise UnreadableDrawing("No text could be read from this scanned drawing.")

    parts, parts_table = _parts_scan(page, words)
    elsewhere = [w for w in words if not title_block.contains(_centre(w)) and not (parts_table and parts_table.contains(_centre(w)))]
    by_line = {}
    for word in elsewhere:
        by_line.setdefault(word["line"], []).append(word)
    lines = sorted((_join(group) for group in by_line.values()), key=lambda line: (line["bbox"][1], line["bbox"][0]))
    # A lone character away from the title block and parts list is nearly always a hole or a corner mistaken for a letter.
    lines = [line for line in lines if line["confidence"] >= MIN_LINE_CONFIDENCE and (len(key(line["text"])) > 1 or line["text"].isdigit())]

    standards = []
    for line in lines:
        m = STANDARD_LINE_OCR.match(line["text"].upper())
        if m:
            standards.append({"name": m["name"].strip(), "edition": int(m["edition"]), "bbox": line["bbox"]})

    return {
        "source": "scan",
        "fields": _title_block_scan(words, title_block),
        "standards": standards,
        "parts": parts,
        "lines": lines,
        "text": " ".join(word["text"].upper() for word in words),
        "page_size": [page.rect.width, page.rect.height],
    }


def _title_block_scan(words, clip) -> dict:
    inside = [word for word in words if clip.contains(_centre(word))]
    fields = {}
    for name, (label, width) in FIELDS.items():
        # The label as OCR read it: exactly, or near enough ("THK(MM)" read as "THK[MM)").
        hit = next((w for w in inside if key(w["text"]) == key(label)), None) or next(
            (w for w in inside if SequenceMatcher(None, key(w["text"]), key(label)).ratio() >= 0.75), None)
        fields[name] = {"value": "", "bbox": None, "confidence": 0}
        if hit:
            x0, _, _, y1 = hit["box"]
            box = pymupdf.Rect(x0 - 3, y1, x0 + width, y1 + VALUE_HEIGHT + 2)
            value = [w for w in inside if w is not hit and box.contains(_centre(w))]
            if value:
                joined = _join(value)
                fields[name] = {"value": joined["text"], "bbox": joined["bbox"], "confidence": joined["confidence"]}
    return fields


def _parts_scan(page, words) -> tuple:
    """Rebuild the parts list from word positions: columns from the heading row, rows from what lies under it."""
    headers = [next((w for w in words if key(w["text"]) == heading), None) for heading in PARTS_HEADERS]
    if any(h is None for h in headers) or max(abs(h["box"][1] - headers[0]["box"][1]) for h in headers) > ROW_PITCH / 2:
        return [], None
    starts = [h["box"][0] - 3 for h in headers]
    left, right = starts[0] - 3, headers[-1]["box"][0] + 70
    top = max(h["box"][3] for h in headers)

    below = sorted((w for w in words if w["box"][1] >= top - 2 and left <= _centre(w).x <= right), key=lambda w: _centre(w).y)
    rows, last_y = [], top
    for word in below:
        y = _centre(word).y
        if y - last_y > ROW_PITCH * 1.5:
            break  # a gap bigger than a row: the table has ended
        if not rows or y - rows[-1]["y"] > ROW_PITCH / 2:
            rows.append({"y": y, "words": []})
        rows[-1]["words"].append(word)
        last_y = y

    parts = []
    for row in rows:
        cells = {column: [] for column in PARTS_COLUMNS}
        for word in row["words"]:
            column = max(i for i, start in enumerate(starts) if start <= _centre(word).x or i == 0)
            cells[PARTS_COLUMNS[column]].append(word)
        if cells["part_no"]:
            joined = _join(row["words"])
            part = {c: _join(ws)["text"] if ws else "" for c, ws in cells.items()} | {"bbox": joined["bbox"], "confidence": joined["confidence"]}
            for column, digits_only in REREAD.items():
                if part[column]:
                    continue
                # Empty after the whole-page read: look at this one cell, kept clear of the grid lines around it.
                i = PARTS_COLUMNS.index(column)
                # Height is taken from the nearest word in the row: on a crooked scan the row is not level across the table.
                y = _centre(min(row["words"], key=lambda w: abs(_centre(w).x - starts[i]))).y
                cell = pymupdf.Rect(starts[i] + 2, y - ROW_PITCH * 0.4, (starts[i + 1] if i + 1 < len(starts) else starts[i] + LAST_COLUMN_WIDTH) - 2, y + ROW_PITCH * 0.4)
                text, confidence = ocr.read_cell(page.get_pixmap(dpi=CELL_DPI, clip=cell, colorspace=pymupdf.csGRAY).tobytes("png"), CELL_DPI, digits_only)
                if text:
                    part[column], part["confidence"] = text, min(part["confidence"], confidence)
            parts.append(part)
    if not parts:
        return [], None
    return parts, pymupdf.Rect(left, min(h["box"][1] for h in headers) - 2, right, max(p["bbox"][3] for p in parts) + 4)
