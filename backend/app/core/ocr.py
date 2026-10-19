"""Read the words on a picture of a drawing with Tesseract, an OCR program installed on the machine.

Each word comes back with where it is and how sure Tesseract is (0 to 100). Nothing is sent anywhere.
"""
import csv
import io
import os
import shutil
import subprocess
from pathlib import Path

MIN_CONFIDENCE = 50  # below this the "word" is usually a dashed line or a hatch pattern, not text
# Two passes over the same picture. "Sparse text" (11) finds labels scattered over a sheet;
# "single column" (4) finds the single digits in table cells that the first pass leaves out.
PASSES = ("11", "4")


def find_tesseract() -> str | None:
    default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return os.environ.get("GRSE_TESSERACT") or shutil.which("tesseract") or (str(default) if default.exists() else None)


def _run(tesseract: str, png: bytes, dpi: int, psm: str, options: tuple = ()) -> list:
    result = subprocess.run([tesseract, "stdin", "stdout", "--psm", psm, "--dpi", str(dpi), *options, "tsv"], input=png, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[:300])
    scale = 72 / dpi  # picture pixels to PDF points
    words = []
    for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8", "replace")), delimiter="\t", quoting=csv.QUOTE_NONE):
        text, confidence = (row["text"] or "").strip(), float(row["conf"])
        if confidence < MIN_CONFIDENCE or not any(c.isalnum() for c in text):
            continue
        x, y, w, h = (int(row[k]) * scale for k in ("left", "top", "width", "height"))
        words.append({
            "text": text, "confidence": round(confidence), "box": [x, y, x + w, y + h],
            "line": (psm, row["block_num"], row["par_num"], row["line_num"]),
        })
    return words


def _centre(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _inside(point, box, margin=0.0) -> bool:
    return box[0] - margin <= point[0] <= box[2] + margin and box[1] - margin <= point[1] <= box[3] + margin


def read_words(png: bytes, dpi: int) -> list:
    """Words on the picture: {"text", "confidence", "box" in PDF points, "line" (words sharing it are one line of text)}."""
    tesseract = find_tesseract()
    if tesseract is None:
        raise RuntimeError("Tesseract is not installed")
    words = _run(tesseract, png, dpi, PASSES[0])
    for extra in _run(tesseract, png, dpi, PASSES[1]):
        # Keep a word from the second pass only where the first pass found nothing.
        if not any(_inside(_centre(extra["box"]), word["box"], margin=1) for word in words):
            words.append(extra)
    return words


def read_cell(png: bytes, dpi: int, digits_only: bool) -> tuple:
    """Read one table cell on its own, as a single line of text. Returns (text, confidence); ("", 0) if nothing is there.

    A whole-page read often skips a lone digit in a cell. Looking at just the cell, and saying only digits are expected, finds it.
    """
    tesseract = find_tesseract()
    if tesseract is None:
        return "", 0
    options = ("-c", "tessedit_char_whitelist=0123456789.") if digits_only else ()
    words = _run(tesseract, png, dpi, "7", options)
    if not words:
        return "", 0
    return " ".join(word["text"] for word in words), min(word["confidence"] for word in words)
