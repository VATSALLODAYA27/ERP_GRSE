"""Generate the MOCK sample drawings. These are invented sheets, not GRSE documents.

Writes to demo/drawings/. Run from backend/:  python -m scripts.make_samples
"""
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from app import config

W, H = 1191, 842  # A3 landscape, in points
MARGIN = 20
RIGHT = W - MARGIN - 480  # left edge of the right-hand column: parts list, notes, title block

NOTES = ["ALL DIMENSIONS IN MM", "WELDING AS PER APPROVED WPS", "EDGE PREPARATION AS PER SHIPYARD STANDARD", "DO NOT SCALE DRAWING"]
STANDARDS = ["MOCK-CLS STEEL SHIP RULES, EDITION 2024", "MOCK-CUST HULL SPEC 100, EDITION 2023"]

SHEETS = [
    # Superseded revision of H-101: fine on its own, but the register has moved on to B.
    dict(slug="superseded-revision", hull="3030", zone="DECK", spacing=700, shape="bow", frames=(20, 28), no="GRSE-H-101", rev="A", title="FWD MAIN DECK PLATING FR 20-28", status="APPROVED", material="AH36", thk=10,
         date="2026-06-02", stiffeners=6, notes=NOTES, standards=STANDARDS, parts=[
             (1, "PL-101-01", "DECK PLATE", "AH36", 10, 4),
             (2, "HP-101-02", "HP STIFFENER 160X8", "AH36", 8, 6),
             (3, "FB-101-03", "FLAT BAR 100X10", "A", 10, 8)]),
    # Current revision of H-101: clean.
    dict(slug="clean-pass", hull="3030", zone="DECK", spacing=700, shape="bow", frames=(20, 28), no="GRSE-H-101", rev="B", title="FWD MAIN DECK PLATING FR 20-28", status="APPROVED", material="AH36", thk=12,
         date="2026-09-15", stiffeners=7, notes=NOTES, standards=STANDARDS, parts=[
             (1, "PL-101-01", "DECK PLATE", "AH36", 12, 4),
             (2, "HP-101-02", "HP STIFFENER 160X8", "AH36", 8, 7),
             (3, "FB-101-03", "FLAT BAR 100X10", "A", 10, 8),
             (4, "BK-101-04", "BRACKET 150X150", "AH36", 10, 4)]),
    # Wrong grade, plate too thin, old class edition, a mandatory note missing.
    dict(slug="wrong-grade-thin-plate", hull="3030", zone="BULKHEAD", spacing=700, shape="bulkhead", frames=(34, 34), no="GRSE-H-102", rev="A", title="BULKHEAD FR 34 STIFFENING", status="APPROVED", material="S275", thk=5,
         date="2026-07-20", stiffeners=5, notes=[NOTES[0], NOTES[2], NOTES[3]],
         standards=["MOCK-CLS STEEL SHIP RULES, EDITION 2021", STANDARDS[1]], parts=[
             (1, "PL-102-01", "BULKHEAD PLATE", "S275", 5, 2),
             (2, "HP-102-02", "HP STIFFENER 140X7", "AH36", 7, 5)]),
    # Only non-blocking problems: old customer spec edition, a recommended note missing.
    dict(slug="old-standard-edition", hull="3030", zone="SIDE SHELL", spacing=800, shape="block", frames=(40, 48), no="GRSE-H-103", rev="A", title="SIDE SHELL PLATING FR 40-48", status="APPROVED", material="DH36", thk=14,
         date="2026-08-04", stiffeners=9, notes=NOTES[:3],
         standards=[STANDARDS[0], "MOCK-CUST HULL SPEC 100, EDITION 2020"], parts=[
             (1, "PL-103-01", "SHELL PLATE", "DH36", 14, 3),
             (2, "HP-103-02", "HP STIFFENER 200X10", "DH36", 10, 9)]),
    # Issued for information only: not released for production.
    dict(slug="for-information-only", hull="3030", zone="MACHINERY SEATING", spacing=600, shape="block", frames=(52, 58), no="GRSE-M-210", rev="A", title="ENGINE ROOM SEATING DETAILS", status="FOR INFORMATION", material="AH36", thk=20,
         date="2026-09-28", stiffeners=4, notes=NOTES, standards=STANDARDS, parts=[
             (1, "PL-210-01", "SEATING TOP PLATE", "AH36", 20, 2),
             (2, "PL-210-02", "GIRDER WEB", "AH36", 12, 4)]),
]


COS30, SIN30 = 0.866, 0.5
DASHED = "[6 3] 0"


def isometric(origin_x: float, origin_y: float, scale: float):
    """A function that places a point of the structure (x along the ship, y across it, z up) on the sheet."""
    return lambda x, y, z: (origin_x + (x + y) * COS30 * scale, origin_y - z * scale - x * SIN30 * scale + y * SIN30 * scale)


def ring(centre, radius_a, radius_b, axis_a, axis_b, steps=28) -> list:
    """Points around an ellipse lying in the plane of two axes, e.g. a lightening hole in a frame."""
    points = []
    for i in range(steps):
        angle = 2 * np.pi * i / steps
        points.append(tuple(c + radius_a * np.cos(angle) * a + radius_b * np.sin(angle) * b for c, a, b in zip(centre, axis_a, axis_b)))
    return points


def balloons(page, text, targets: list):
    """Numbered item balloons along the top of the view, each with a leader line to the part it names."""
    # Balloons sit left to right in the order of the parts they point at, so the leader lines do not cross.
    order = sorted(range(len(targets)), key=lambda i: targets[i][0])
    for slot, i in enumerate(order):
        x, y, target = 95 + slot * 50, 185, targets[i]
        page.draw_circle((x, y), 11, width=0.8)
        text(x - 2.5, y + 3, i + 1, 9)
        page.draw_line((x, y + 11), target, width=0.5)
        page.draw_circle(target, 1.6, width=0.5, fill=(0, 0, 0))


def draw_hull_block(page, text, spec):
    """A hull block: bottom plating with longitudinal stiffeners, transverse web frames, side shell and deck edge."""
    tapered = spec["shape"] == "bow"  # a bow block narrows to the stem; a midship block is the same width throughout
    length, half_beam, height = 10.0, 3.0, 3.0
    at = isometric(205, 544, 48)

    def breadth(x):
        return half_beam if not tapered or x <= 6 else half_beam * (length - x) / 4

    def line(points, width=0.5, closed=False, dashes=None):
        page.draw_polyline([at(*point) for point in points], width=width, closePath=closed, dashes=dashes)

    corners = [(0, -half_beam), (6, -half_beam)] + ([(length, 0)] if tapered else [(length, -half_beam), (length, half_beam)]) + [(6, half_beam), (0, half_beam)]
    line([(x, y, 0) for x, y in corners], 0.9, closed=True)       # bottom plating
    line([(x, y, height) for x, y in corners], 1.3, closed=True)  # deck edge
    for x, y in corners:
        line([(x, y, 0), (x, y, height)], 0.9)                    # shell plating corners

    frame_positions = [0, 2, 4, 6, 8] if tapered else [0, 2.5, 5, 7.5, 10]
    for x in frame_positions:
        b = breadth(x)
        line([(x, -b, 0), (x, b, 0), (x, b, height), (x, -b, height)], 0.6, closed=True)  # web frame
        if b > 1.2:
            line(ring((x, 0, height / 2), b * 0.33, height * 0.24, (0, 1, 0), (0, 0, 1)), 0.5, closed=True)  # lightening hole
    first, last = spec["frames"]
    for i, x in enumerate(frame_positions):
        px, py = at(x, breadth(x) + 0.15, 0)
        text(px + 4, py + 10, f"FR {round(first + (last - first) * i / (len(frame_positions) - 1))}", 7)

    # Longitudinal stiffeners on the bottom plating, each running until the shell cuts it off.
    n = spec["stiffeners"]
    stiffeners = [-half_beam + (i + 1) * 2 * half_beam / (n + 1) for i in range(n)]
    for y in stiffeners:
        end = length - 4 * abs(y) / half_beam if tapered else length
        line([(0, y, 0), (end, y, 0)], 0.6, dashes=DASHED)

    opening = (7.3 if tapered else 5.0, 0, height)
    line(ring(opening, 0.5, 0.5, (1, 0, 0), (0, 1, 0)), 0.9, closed=True)  # access opening in the deck

    has_brackets = any("BRACKET" in part[2] for part in spec["parts"])
    if has_brackets:
        for x in (2, 4) if tapered else (2.5, 5):
            for side in (-1, 1):
                y = side * half_beam
                line([(x, y, 0), (x, y - side * 0.7, 0), (x, y, 0.7)], 1.1, closed=True)

    targets = [at(3, -1.6, 0), at(5, stiffeners[0], 0), at(frame_positions[1], 0.9, height)]
    if has_brackets:
        targets.append(at(frame_positions[1], -half_beam + 0.25, 0.25))
    balloons(page, text, targets[:len(spec["parts"])])


def draw_bulkhead(page, text, spec):
    """A transverse bulkhead: the plate, vertical stiffeners standing off it, a door opening, and the deck and bottom it lands on."""
    half_beam, height, depth = 4.0, 5.0, 0.45
    at = isometric(400, 500, 48)

    def line(points, width=0.5, closed=False, dashes=None):
        page.draw_polyline([at(*point) for point in points], width=width, closePath=closed, dashes=dashes)

    line([(0, -half_beam, 0), (0, half_beam, 0), (0, half_beam, height), (0, -half_beam, height)], 1.3, closed=True)  # bulkhead plate
    for y in (-half_beam, half_beam):  # the shell it joins, shown as short returns
        for z in (0, height):
            line([(0, y, z), (2.2, y, z)], 0.9)
        line([(2.2, y, 0), (2.2, y, height)], 0.6, dashes=DASHED)
    for z in (0, height):
        line([(2.2, -half_beam, z), (2.2, half_beam, z)], 0.6, dashes=DASHED)

    n = spec["stiffeners"]
    stiffeners = [-half_beam + (i + 1) * 2 * half_beam / (n + 1) for i in range(n)]
    for y in stiffeners:  # each stiffener drawn as its web standing off the plate
        line([(0, y, 0), (depth, y, 0), (depth, y, height), (0, y, height)], 0.7, closed=True)

    door_y = (stiffeners[0] + stiffeners[1]) / 2 if n > 1 else 0
    line([(0, door_y - 0.45, 0.5), (0, door_y + 0.45, 0.5), (0, door_y + 0.45, 2.4), (0, door_y - 0.45, 2.4)], 0.9, closed=True)  # door opening
    px, py = at(0, half_beam + 0.15, 0)
    text(px + 4, py + 10, f"FR {spec['frames'][0]}", 7)

    balloons(page, text, [at(0, -half_beam + 0.5, 4.2), at(depth, stiffeners[-1], 3.2)][:len(spec["parts"])])


def draw(spec: dict, out_dir: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)

    def text(x, y, s, size=8):
        page.insert_text((x, y), str(s), fontsize=size)

    page.draw_rect((MARGIN, MARGIN, W - MARGIN, H - MARGIN), width=1.5)
    text(MARGIN + 10, MARGIN + 16, "MOCK DRAWING FOR DEMONSTRATION - NOT A GRSE DOCUMENT", 9)

    # The structure, as an isometric view with item balloons.
    (draw_bulkhead if spec["shape"] == "bulkhead" else draw_hull_block)(page, text, spec)
    text(80, 150, f"PLATE {spec['thk']} THK {spec['material']}", 9)
    text(80, 636, f"{spec['stiffeners']} NOS. HP STIFFENERS EQUALLY SPACED", 9)

    # Parts list.
    y = MARGIN + 30
    for row in [("ITEM", "PART NO", "DESCRIPTION", "MATL", "THK", "QTY"), *spec["parts"]]:
        x = RIGHT
        for width, cell in zip((35, 110, 165, 60, 45, 65), row):
            page.draw_rect((x, y, x + width, y + 16), width=0.5)
            text(x + 3, y + 11, cell, 7)
            x += width
        y += 16

    # Notes and standards.
    y += 40
    text(RIGHT, y, "GENERAL NOTES", 9)
    for i, note in enumerate(spec["notes"], 1):
        y += 14
        text(RIGHT, y, f"{i}. {note}")
    y += 30
    text(RIGHT, y, "APPLICABLE STANDARDS", 9)
    for standard in spec["standards"]:
        y += 14
        text(RIGHT, y, standard)

    # Title block: small label on top, value below it.
    top = H - MARGIN - 90
    cells = [  # x offset, y offset, width, label, value
        (0, 0, 300, "TITLE", spec["title"]),
        (300, 0, 180, "DRG.NO.", spec["no"]),
        (0, 30, 50, "REV.", spec["rev"]),
        (50, 30, 130, "STATUS", spec["status"]),
        (180, 30, 90, "MATERIAL", spec["material"]),
        (270, 30, 70, "THK(MM)", spec["thk"]),
        (340, 30, 140, "DATE", spec["date"]),
        (0, 60, 120, "HULL.NO.", spec["hull"]),
        (120, 60, 200, "ZONE", spec["zone"]),
        (320, 60, 160, "SPACING(MM)", spec["spacing"]),
    ]
    for dx, dy, width, label, value in cells:
        x, y = RIGHT + dx, top + dy
        page.draw_rect((x, y, x + width, y + 30), width=0.8)
        text(x + 3, y + 9, label, 6)
        text(x + 3, y + 23, value, 10)

    # Numbered in the order the demo walks through them, with the scenario in the name.
    path = out_dir / f"{SHEETS.index(spec) + 1:02d}_{spec['no']}_rev{spec['rev']}_{spec['slug']}.pdf"
    doc.save(path)
    doc.close()
    return path


# Scanned copies: (number, drawing to scan, tilt in degrees, shift in pixels). Each is a picture with no text in the file.
SCANS = [
    (6, ("GRSE-H-101", "A"), 0.3, (5, -4)),
    (7, ("GRSE-H-101", "B"), -0.25, (-6, 3)),
    (8, ("GRSE-H-102", "A"), 0.3, (4, 5)),
]
SCAN_DPI = 200


def scan(pdf_path: Path, out_path: Path, angle: float, shift: tuple, seed: int) -> Path:
    """What a paper print of the drawing looks like after a scanner: slightly crooked, shifted and grainy."""
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        size = page.rect
        pix = page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY)
    image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    turn = cv2.getRotationMatrix2D((pix.width / 2, pix.height / 2), angle, 1.0)
    turn[:, 2] += shift
    image = cv2.warpAffine(image, turn, (pix.width, pix.height), borderValue=255)
    image = np.clip(image + np.random.default_rng(seed).normal(0, 6, image.shape), 0, 255).astype(np.uint8)
    jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()

    doc = pymupdf.open()
    doc.new_page(width=size.width, height=size.height).insert_image(size, stream=jpeg)
    doc.save(out_path)
    doc.close()
    return out_path


def make_all(out_dir: Path = config.SAMPLES_DIR) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [draw(spec, out_dir) for spec in SHEETS]
    for number, (no, rev), angle, shift in SCANS:
        source = next(path for path in paths if f"_{no}_rev{rev}_" in path.name)
        paths.append(scan(source, out_dir / f"{number:02d}_{no}_rev{rev}_scanned-copy.pdf", angle, shift, seed=number))
    return paths


if __name__ == "__main__":
    for path in make_all():
        print(path)
