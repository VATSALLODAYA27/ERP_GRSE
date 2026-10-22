"""Builds the two project documents as PDFs, in this folder:

    1-Project-Overview-and-Flow.pdf   what the project is and how a drawing moves through it
    2-Code-Explanation.pdf            how the code is organised and what each part does

Run from the project folder:   python docs/build_docs.py      (needs: pip install reportlab)

The code excerpts and the list of known shortcuts are read from the source files when this runs,
so rebuilding after a code change keeps the second document accurate.
"""
import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
IMG = DOCS / "img"
DATE = "12 October 2026"

NAVY, INK, GREY, LINE, PALE = colors.HexColor("#12305A"), colors.HexColor("#1F2933"), colors.HexColor("#5B6770"), colors.HexColor("#D5DBE3"), colors.HexColor("#F3F5F8")
GOOD, WARN, BAD = colors.HexColor("#1E8E3E"), colors.HexColor("#B86E00"), colors.HexColor("#C62828")

# Windows fonts when present (they have arrows and proper quotes); the PDF built-ins otherwise.
FONTS = Path("C:/Windows/Fonts")
try:
    for name, file in (("Body", "segoeui.ttf"), ("Body-Bold", "segoeuib.ttf"), ("Body-Italic", "segoeuii.ttf"), ("Mono", "consola.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-Bold")
    BODY, BOLD, ITALIC, MONO = "Body", "Body-Bold", "Body-Italic", "Mono"
except Exception:
    BODY, BOLD, ITALIC, MONO = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Courier"

S = {
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10, leading=14.5, textColor=INK, spaceAfter=6),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=17, leading=22, textColor=NAVY, spaceBefore=16, spaceAfter=8, keepWithNext=True),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=12.5, leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=5, keepWithNext=True),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=10.5, leading=14, textColor=INK, spaceBefore=8, spaceAfter=3, keepWithNext=True),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8.8, leading=11.8, textColor=INK),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=8.8, leading=11.8, textColor=colors.white),
    "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=10, leading=14.5, textColor=INK, leftIndent=14, bulletIndent=3, spaceAfter=3),
    "caption": ParagraphStyle("caption", fontName=ITALIC, fontSize=8.5, leading=11, textColor=GREY, alignment=TA_CENTER, spaceBefore=4, spaceAfter=10),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=7.4, leading=9.6, textColor=INK),
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=30, leading=36, textColor=NAVY),
    "subtitle": ParagraphStyle("subtitle", fontName=BODY, fontSize=15, leading=20, textColor=INK, spaceBefore=10),
    "note": ParagraphStyle("note", fontName=BODY, fontSize=9.5, leading=13.5, textColor=INK),
    "from": ParagraphStyle("from", fontName=BODY, fontSize=8.8, leading=11.8, textColor=GREY, spaceAfter=3, keepWithNext=True),
    "toc": ParagraphStyle("toc", fontName=BODY, fontSize=10.5, leading=16, textColor=INK),
}
WIDTH = A4[0] - 40 * mm  # the text column


def c(text: str) -> str:
    """Inline code."""
    return f'<font face="{MONO}" size="8.8">{escape(text)}</font>'


def P(text: str, style: str = "body"):
    return Paragraph(text, S[style])


def H1(text): return P(text, "h1")
def H2(text): return P(text, "h2")
def H3(text): return P(text, "h3")


def bullets(items: list) -> list:
    return [Paragraph(item, S["bullet"], bulletText="•") for item in items]


def table(rows: list, widths: list, header: bool = True):
    """rows of strings (with inline markup). widths are fractions of the text column."""
    data = [[Paragraph(str(cell), S["head"] if header and r == 0 else S["cell"]) for cell in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * WIDTH for w in widths], repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, PALE]),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 8)]


def note(text: str, colour=NAVY):
    """A boxed remark with a coloured bar down its left side."""
    t = Table([[Paragraph(text, S["note"])]], colWidths=[WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEBEFORE", (0, 0), (0, -1), 3, colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [t, Spacer(1, 8)]


def steps(items: list):
    """A numbered vertical flow: each step is (title, what happens)."""
    rows = []
    for i, (title, detail) in enumerate(items, 1):
        rows.append([Paragraph(f'<font color="white"><b>{i}</b></font>', ParagraphStyle("n", parent=S["cell"], alignment=TA_CENTER, fontName=BOLD)),
                     Paragraph(f"<b>{title}</b><br/>{detail}", S["cell"])])
    t = Table(rows, colWidths=[9 * mm, WIDTH - 9 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY), ("BACKGROUND", (1, 0), (1, -1), PALE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -2), 3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (1, 0), (1, -1), 8),
    ]))
    return [t, Spacer(1, 8)]


def figure(name: str, caption: str, width: float = 1.0):
    path = IMG / name
    image = Image(str(path))
    ratio = image.imageHeight / image.imageWidth
    image.drawWidth, image.drawHeight = WIDTH * width, WIDTH * width * ratio
    frame = Table([[image]], colWidths=[WIDTH * width + 2])
    frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                               ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    frame.hAlign = "CENTER"
    return [KeepTogether([frame, P(caption, "caption")])]


def code(text: str, wrap: int = 104):
    """Source code on a pale background, one table row per line so that a long excerpt can run over a page break."""
    lines = []
    for line in text.rstrip("\n").split("\n"):
        indent = len(line) - len(line.lstrip())
        lines += textwrap.wrap(line, wrap, subsequent_indent=" " * (indent + 8), drop_whitespace=False, replace_whitespace=False) or [""]
    rows = [[Paragraph(escape(line).replace(" ", "&nbsp;") or "&nbsp;", S["code"])] for line in lines]
    t = Table(rows, colWidths=[WIDTH])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, -1), (-1, -1), 6), ("LINEBEFORE", (0, 0), (0, -1), 2, LINE)]))
    return [t, Spacer(1, 8)]


def excerpt(path: str, name: str, limit: int = 60):
    """The source of one top-level function or class, read from the file as it is now."""
    lines = (ROOT / path).read_text(encoding="utf-8").split("\n")
    start = next(i for i, line in enumerate(lines) if re.match(rf"(async def|def|class) {re.escape(name)}\b", line))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith(")")), len(lines))
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    if len(body) > limit:
        body = body[:limit] + ["    ..."]
    return [P(f'From {c(path)}:', "from")] + code("\n".join(body))


def shortcuts() -> list:
    """Every 'shortcut:' comment in the backend: the places where a known limit was accepted on purpose."""
    found = []
    for path in sorted((ROOT / "backend").rglob("*.py")):
        if ".venv" in path.parts or "tests" in path.parts or "migrations" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if "shortcut:" in line:
                found.append([c(f"{path.relative_to(ROOT / 'backend').as_posix()}:{number}"), escape(line.split("shortcut:", 1)[1].strip())])
    return found


def boxes(width: float, height: float, items: list, arrows: list):
    """A small box-and-arrow diagram. items: (x, y, w, h, title, subtitle, fill). arrows: (x1, y1, x2, y2, label)."""
    d = Drawing(width, height)
    for x, y, w, h, title, subtitle, fill in items:
        d.add(Rect(x, y, w, h, rx=4, ry=4, fillColor=fill, strokeColor=NAVY, strokeWidth=0.8))
        light = fill == NAVY
        d.add(String(x + w / 2, y + h / 2 + (2 if subtitle else -3), title, fontName=BOLD, fontSize=9, fillColor=colors.white if light else NAVY, textAnchor="middle"))
        for i, part in enumerate(subtitle.split("\n") if subtitle else []):
            d.add(String(x + w / 2, y + h / 2 - 10 - i * 9.5, part, fontName=BODY, fontSize=7.4, fillColor=colors.white if light else GREY, textAnchor="middle"))
    for x1, y1, x2, y2, label in arrows:
        d.add(Line(x1, y1, x2, y2, strokeColor=GREY, strokeWidth=1))
        dx, dy = (x2 - x1), (y2 - y1)
        length = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / length, dy / length
        d.add(Polygon([x2, y2, x2 - 6 * ux + 3 * uy, y2 - 6 * uy - 3 * ux, x2 - 6 * ux - 3 * uy, y2 - 6 * uy + 3 * ux], fillColor=GREY, strokeColor=GREY))
        if label:
            d.add(String((x1 + x2) / 2, (y1 + y2) / 2 + 4, label, fontName=ITALIC, fontSize=7.2, fillColor=GREY, textAnchor="middle"))
    d.hAlign = "CENTER"
    return d


def build(filename: str, title: str, subtitle: str, about: str, contents: list, story: list):
    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
        canvas.setFont(BODY, 8)
        canvas.setFillColor(GREY)
        canvas.drawString(20 * mm, 9.5 * mm, f"Drawing Compliance Checker  ·  {title}  ·  all data shown is representative data")
        canvas.drawRightString(A4[0] - 20 * mm, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 62 * mm, A4[0], 62 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(BOLD, 13)
        canvas.drawString(20 * mm, A4[1] - 30 * mm, "DRAWING COMPLIANCE CHECKER")
        canvas.setFont(BODY, 10.5)
        canvas.drawString(20 * mm, A4[1] - 38 * mm, "A release gate for drawings: concept walkthrough for GRSE GAINS 2026")
        canvas.drawString(20 * mm, A4[1] - 46 * mm, f"Prepared {DATE}")
        canvas.restoreState()

    front = [Spacer(1, 54 * mm), P(title, "title"), P(subtitle, "subtitle"), Spacer(1, 8 * mm)]
    front += note(about)
    front += note("<b>Everything in this project is representative data.</b> The drawings, the drawing register, the bills of materials, the work orders and the "
                  "rules with their clause numbers were invented for the walkthrough. None of it comes from GRSE or from a classification society.", WARN)
    front += [Spacer(1, 3 * mm), P("<b>Contents</b>", "h2")] + [P(f"{i}.&nbsp;&nbsp;{entry}", "toc") for i, entry in enumerate(contents, 1)]
    front += [PageBreak()]

    doc = SimpleDocTemplate(str(DOCS / filename), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                            title=f"Drawing Compliance Checker: {title}", author="Drawing Compliance Checker project")
    doc.build(front + story, onFirstPage=cover, onLaterPages=page)
    print(f"Built {DOCS / filename}")


# =====================================================================================================================
# Document 1: the project and its flow
# =====================================================================================================================

def overview():
    contents = [
        "The problem, and what the tool does about it", "Words you need", "Where it sits beside the ERP", "Who uses it",
        "The flow of one check", "The rules and the verdict", "Comparing two revisions", "Connecting the drawing to the ERP",
        "Scanned drawings", "The optional AI summary", "The release decision and the audit log", "Keeping the data safe",
        "The screens", "The walkthrough kit", "How it was built", "What is not done: honest limits",
    ]
    s = []

    s += [H1("1. The problem, and what the tool does about it")]
    s += [P("A shipyard cuts steel from drawings, and a drawing changes over time: revision A is replaced by revision B. A work order or a bill of "
            "materials is released to the shop floor against one particular revision. If that revision is out of date or was never approved, the wrong "
            "material is ordered or cut. The ERP <i>stores</i> which revision is current, but it does not <i>stop</i> anyone using the wrong one.")]
    s += [P("The Drawing Compliance Checker is a <b>release gate</b> that sits before that release. For each drawing it:")]
    s += bullets([
        "reads the drawing's title block and compares its revision and status with the approved drawing register;",
        "runs a small set of fixed compliance checks, each tied to a numbered clause of a standard;",
        "shows exactly what changed since the previous revision;",
        "checks the parts list against the ERP's bill of materials, and lists the work orders and purchase orders a revision change affects;",
        "gives a verdict (<b>Pass</b>, <b>Needs review</b> or <b>Blocked</b>) with a reason for every finding;",
        "leaves the final decision to a named human reviewer, and records it.",
    ])
    s += note("Three principles run through the whole design. <b>The ERP is never written to</b>: the tool reads an extract and answers questions. "
              "<b>Decisions are deterministic</b>: every finding comes from a fixed rule with a clause, never from an AI opinion. "
              "<b>A human closes every check</b>: the tool proposes, a reviewer decides.")

    s += [H1("2. Words you need")]
    s += table([
        ["Word", "Meaning"],
        ["ERP / PLM", "The company's central systems. They hold the drawing register, bills of materials, work orders and purchase orders."],
        ["Drawing register", "The official list: each drawing number, its current revision and its status."],
        ["Title block", "The box in the corner of a drawing with its number, revision, status, material and date."],
        ["Revision", "A version of a drawing (A, B, C ...). Only one is current; older ones are <i>superseded</i>."],
        ["Extract", "A read-only copy of ERP data, exported as files. The tool reads the copy and never writes to the ERP."],
        ["BOM", "Bill of materials: the parts, materials and quantities that belong to a drawing revision."],
        ["Work order", "An instruction to the shop floor to make something, released against a drawing revision."],
        ["Rule", "One fixed check, such as “plate thickness must be at least 6 mm”."],
        ["Clause", "The numbered paragraph in a standard that a rule comes from. Every finding cites one."],
        ["Finding", "One problem found on one drawing, with a severity, a clause and the evidence."],
        ["Verdict", "The tool's proposal for the drawing: Pass, Needs review or Blocked."],
        ["Vector PDF / scan", "A vector PDF comes from CAD and contains real text. A scan is a photograph of paper and contains only pixels."],
        ["OCR", "Optical character recognition: software that turns a picture of text into text."],
    ], [0.22, 0.78])

    s += [H1("3. Where it sits beside the ERP")]
    s += [P("The tool is an add-on beside the ERP, not a change to it. An extract of ERP data goes in; verdicts, reports and a gate answer come out.")]
    w = WIDTH
    s += [boxes(w, 150, [
        (0, 55, 98, 62, "ERP / PLM", "register · BOM\nwork orders · POs", PALE),
        (w / 2 - 78, 30, 156, 112, "", "", colors.white),
        (w / 2 - 68, 104, 136, 28, "Checking engine", "", NAVY),
        (w / 2 - 68, 68, 136, 28, "Web app and API", "", PALE),
        (w / 2 - 68, 38, 136, 24, "Own database and files", "", PALE),
        (w - 118, 92, 118, 46, "Engineer", "uploads drawings", PALE),
        (w - 118, 30, 118, 46, "Reviewer", "decides, comments", PALE),
    ], [
        (98, 96, w / 2 - 80, 96, "read-only extract"),
        (w / 2 - 80, 64, 98, 64, "gate answer"),
        (w - 118, 115, w / 2 + 80, 115, ""),
        (w / 2 + 80, 53, w - 118, 53, ""),
    ])]
    s += [P("Figure 1. The tool reads an extract from the ERP and answers the gate question. It has its own database for checks, decisions and the audit log.", "caption")]
    s += table([
        ["ERP area", "What it holds", "Used for"],
        ["Document / product data management", "Drawings, their revisions, engineering change notes", "Register check, revision history"],
        ["Production planning", "Work orders, bills of materials", "BOM consistency, release gate, change impact"],
        ["Materials management", "Purchase orders", "Change impact"],
        ["Quality / class approvals", "What was submitted to class or the customer", "Class approval tracking, a warning on the gate"],
    ], [0.30, 0.38, 0.32])
    s += [P("Which ERP GRSE runs, and the exact format of its exports, were not verified. The walkthrough uses seven invented CSV files in "
            + c("setup/register/") + " that stand in for the extract.")]

    s += [H1("4. Who uses it")]
    s += table([
        ["Role", "Can do", "How the account is created"],
        ["Engineer", "Upload drawings for checking, view everything, comment.", "Registers on the sign-in page, then waits for an admin to approve the account."],
        ["Reviewer", "Upload drawings for checking, view everything, comment, read the audit log. Cannot approve or reject a release, and cannot change rules or the register.", "Registers on the sign-in page, then waits for an admin to approve the account."],
        ["Admin", "Everything. <b>Only the admin approves or rejects a release.</b> Also approves and disables accounts, adds or updates drawings in the register, and approves or withdraws rules.", "From the logins file only. Nobody can register as admin."],
    ], [0.14, 0.50, 0.36])
    s += [P("Registration needs approval because a reviewer decides whether steel gets cut. If anyone on the network could create a reviewer account and "
            "use it at once, the reviewer's decision would mean nothing.")]

    s += [H1("5. The flow of one check")]
    s += [P("This is what happens from the moment an engineer chooses a file to the moment a work order is cleared.")]
    s += steps([
        ("Upload", "The engineer drops a PDF on the New Check screen. It must be a PDF of at most 25 MB."),
        ("Read", "The title block, parts list, notes and cited standards are read. A vector PDF is read exactly; a scan is read by OCR."),
        ("Confirm (scans only)", "For a scan, the values OCR read are shown in editable boxes with low-confidence values marked. The person corrects any "
                                 "mistakes and confirms. The server refuses a scan that was not confirmed."),
        ("Look up the register", "The drawing number is looked up in the tool's copy of the ERP register, together with its bill of materials."),
        ("Run the rules", "Each approved rule examines what was read and reports its findings, each with a severity, a clause and the evidence."),
        ("Verdict", "The worst severity decides: any critical finding means Blocked, otherwise any major means Needs review, otherwise Pass."),
        ("Compare with the previous revision", "If an earlier revision is available, the changes are listed and the two sheets are overlaid. "
                                               "This is information for the reviewer and does not change the verdict."),
        ("BOM and impact", "The parts list is set beside the ERP bill of materials, and the work orders and purchase orders affected by the revision change are listed."),
        ("Store", "The check, its findings, the uploaded file and snapshots of what the ERP said at that moment are saved. The audit log records it."),
        ("Reviewer decides", "A reviewer opens the report, may comment, and approves or rejects the release. The decision is final and logged."),
        ("Release gate", "Each work order now shows Clear, Warn or Blocked, with reasons. The ERP (or a person) acts on that answer."),
    ])
    s += figure("report-blocked.jpg", "Figure 2. A check report: the verdict, the title block beside the register, and the reviewer's panel.", 0.92)

    s += [H1("6. The rules and the verdict")]
    s += [P("There are twelve <b>check types</b> written as code. A <b>rule</b> is an entry in a file that picks one check type and gives it parameters, a "
            "severity and a clause. Adding a rule of an existing type means adding an entry, not writing code.")]
    s += [P("A rule runs only while it is <b>approved</b>. Approval is given in the tool, on the Rule Library screen, by an admin, and it covers the rule "
            "<i>exactly as written</i>: if the clause, the severity or a parameter is later edited, the rule stops running until it is approved again. Who approved "
            "what, and when, is in the audit log.")]
    s += table([
        ["Rule", "What it catches", "Severity", "Representative clause"],
        ["REG-01", "A superseded revision, or a drawing that is not in the register", "Critical", "REF-PROC 4.2"],
        ["REG-02", "The title block's status disagrees with the register", "Major", "REF-PROC 4.3"],
        ["CHK-01", "The drawing is not approved for production", "Critical", "REF-CUST 2.1"],
        ["CHK-02", "The drawing cites an old edition of a standard", "Major", "REF-CLS 1.1.4"],
        ["CHK-03", "A material grade that is not on the allowed list", "Critical", "REF-CLS 3.2.1"],
        ["CHK-04", "Plate thinner than the minimum", "Critical", "REF-CLS 3.4.2"],
        ["CHK-05", "A mandatory note is missing", "Major", "REF-CUST 5.3"],
        ["CHK-06", "A recommended note is missing", "Minor", "REF-CUST 5.4"],
        ["BOM-01", "The parts list disagrees with the ERP bill of materials", "Major", "REF-PROC 5.2"],
        ["CHK-08", "Plate thinner than the thickness <i>calculated</i> for its structural zone", "Critical", "REF-CLS 4.2.3"],
        ["CHK-09", "Stiffener spacing over the limit for its zone", "Major", "REF-CLS 4.3.1"],
        ["CHK-10", "Thick plate in a zone that is not of a higher steel grade", "Critical", "REF-CLS 3.2.4"],
        ["CHK-11", "A count stated in a note disagrees with the parts list", "Major", "REF-PROC 5.4"],
        ["CHK-07", "A draft rule, shown only to show that unapproved rules are skipped", "(not run)", "REF-CUST 5.6"],
    ], [0.11, 0.53, 0.14, 0.22])
    s += table([
        ["Worst finding", "Verdict", "Meaning"],
        ["Critical", '<font color="#C62828"><b>BLOCKED</b></font>', "The drawing must not be released as it stands."],
        ["Major", '<font color="#B86E00"><b>NEEDS REVIEW</b></font>', "A reviewer must look and give a reason either way."],
        ["Minor or none", '<font color="#1E8E3E"><b>PASS</b></font>', "Nothing stops release; the reviewer still confirms."],
    ], [0.22, 0.24, 0.54])
    s += [H2("Rules that depend on where the plate is, and on a calculation")]
    s += [P("Real class rules do not use one thickness for every plate. They depend on the structural zone (deck, side shell, bulkhead ...), on the ship, and "
            "on a formula. The tool handles that shape of rule. Each drawing's title block names its <b>zone</b>, its <b>hull number</b> and its "
            "<b>stiffener spacing</b>; the ERP extract gives the ship's rule length for that hull; and a rule can carry one formula per zone.")]
    s += table([
        ["Zone", "Representative formula for required plate thickness (mm)", "For the walkthrough ship (L = 142 m, s = 700 mm)"],
        ["Deck", "4.5 + 0.04 × L", "10.2 mm"],
        ["Side shell", "5.0 + 0.045 × L", "11.4 mm"],
        ["Bulkhead", "4.0 + 0.005 × s", "7.5 mm"],
        ["Machinery seating", "8 + 0.05 × L", "15.1 mm"],
    ], [0.22, 0.44, 0.34])
    s += [P("So revision A of the deck drawing, with a 10 mm plate, fails; revision B, at 12 mm, passes. The finding shows the working: "
            "<i>“10 mm is below the 10.2 mm required in zone DECK (4.5 + 0.04 * L, with L = 142 m and s = 700 mm)”</i>. On a longer ship the same drawing would "
            "need more. <b>These formulas and limits are invented.</b> What is real is that a naval architect can now enter true ones without any change to the code.")]
    s += figure("findings-calculated.jpg", "Figure 3a. A calculated finding: the deck plate is thinner than the zone formula requires for this ship.", 0.92)
    s += figure("findings.jpg", "Figure 3. Findings on a non-compliant drawing: severity, rule, clause and the evidence found on the sheet.", 0.92)
    s += figure("sheet-markers.jpg", "Figure 4. The same findings marked on the drawing sheet. The numbers match the rows of the findings table.", 0.92)

    s += [H1("7. Comparing two revisions")]
    s += [P("“Show exactly what changed” is answered in two ways, because each catches what the other misses.")]
    s += table([
        ["", "The change list", "The overlay"],
        ["Made from", "The text: title block field by field, parts list row by row (matched by part number), other text line by line.", "The picture: both sheets turned into images of the same size and compared pixel by pixel."],
        ["Shows", "“PL-101-01 thickness 10 → 12”, “BK-101-04 added”.", "Grey where the sheets agree, red for what is only on the old one, green for what is only on the new one."],
        ["Good at", "Saying precisely what a change is.", "Catching redrawn lines, which have no text."],
        ["Weak at", "Geometry: a moved line with no text is invisible to it.", "Meaning: something that only moved shows as red and green."],
    ], [0.14, 0.43, 0.43])
    s += [P("The previous revision is the one uploaded alongside the drawing, or else the latest earlier revision of the same drawing that has already been "
            "checked. The ERP's engineering change note for the revision is shown above the comparison, so the reviewer can see whether the drawing changed the "
            "way the ERP says it did.")]
    s += figure("overlay.jpg", "Figure 5. Revision A overlaid on revision B of a bow block: one more stiffener, new brackets and a new parts-list row.", 0.92)

    s += [H1("8. Connecting the drawing to the ERP")]
    s += [H2("Does the drawing agree with what will be ordered? (BOM consistency)")]
    s += [P("The parts list on the drawing is compared with the ERP bill of materials for the same revision, part by part: material, thickness and quantity. "
            "A part found on one side only is also reported. Each difference is a finding under rule BOM-01.")]
    s += [H2("Who is affected when a revision changes? (Change impact)")]
    s += [P("From the parts that changed between two revisions the tool lists the work orders still released against the old revision and the open purchase "
            "orders for those parts. For the example pair it reports: <i>the change from revision A to B affects 1 work order and 2 open purchase orders</i>.")]
    s += [H2("May this work order be released? (The release gate)")]
    s += table([
        ["Fact", "Blocked when", "Warn when"],
        ["Register", "The revision is superseded, the drawing is unknown, or its status is not approved.", ""],
        ["Check", "The latest check of that revision is Blocked and not yet decided.", "No check has been run, or it awaits a decision."],
        ["Reviewer", "The reviewer rejected it.", ""],
        ["Class approval", "", "Not submitted, awaiting, or returned with comments."],
    ], [0.18, 0.44, 0.38])
    s += [P("A work order is <b>Clear</b> only when the revision is current and approved, a reviewer has approved a check of it, and class approval is in place. "
            "The gate is worked out afresh every time it is asked, so a decision made a minute ago counts. It is also offered as a web address a system can call, "
            "which is how an ERP would ask the question.")]
    s += figure("gate-before.jpg", "Figure 6. The release gate before any check: two work orders are already blocked by the register alone.", 0.92)

    s += [H1("9. Scanned drawings")]
    s += [P("A scan has no text in it, so it is read by <b>Tesseract</b>, an OCR program installed on the same machine; nothing leaves the building. "
            "For each word Tesseract gives the text, its position and a confidence from 0 to 100.")]
    s += bullets([
        "The sheet is read twice with two settings and the results are merged; words below 50% confidence are dropped, because they are nearly always dashed lines mistaken for letters.",
        "An empty cell in the parts list is read again on its own, enlarged. A whole-page read often skips a lone digit in a table.",
        "The person uploading must confirm or correct the title-block values before the check runs. Corrections are kept beside what OCR read, and listed in the audit log.",
        "The parts list and notes are used as read, and the report says so in a banner.",
        "Before two scans are compared, the older one is shifted and turned until it sits on the newer one.",
    ])
    s += figure("scan-confirm.jpg", "Figure 7. A scanned drawing: OCR read the grade S275 as $275. It is marked low confidence and corrected before the check runs.", 0.92)

    s += [H1("10. The optional AI summary")]
    s += [P("On the Revision changes tab a button can ask a hosted language model for a plain-English summary of the change list. It is a reading aid only. "
            "The verdict, the findings, the gate and the decision never look at it.")]
    s += table([
        ["Risk", "What the tool does"],
        ["The drawing leaves the building", "Only the change list is sent: not the PDF and not the drawing number."],
        ["It runs without anyone knowing", "Nothing is sent until someone presses the button, and the card says where the text will go."],
        ["The model invents a number", "Every number in the summary is looked up in the change list; any that is not there is called out."],
        ["Text on a drawing tries to instruct the model", "The model is told the list is data, and its answer is only ever shown as text."],
        ["The model gives an opinion on compliance", "It is told not to, and the card is labelled “AI-written, not part of the compliance decision”."],
        ["No key, or the service is down", "The card does not appear, or the button shows the error. Everything else works."],
    ], [0.36, 0.64])

    s += [H1("11. The release decision and the audit log")]
    s += note("<b>Who decides.</b> In the current version only the <b>admin</b> approves or rejects a release. Engineers and reviewers upload drawings, read the "
              "reports and comment. Where this document says “the reviewer decides”, read it as the person holding the admin account.")
    s += table([
        ["Tool's verdict", "Approve for release", "Reject"],
        ["Pass", "No reason needed.", "Reason required; recorded as an override."],
        ["Needs review", "Reason required.", "Reason required."],
        ["Blocked", "Reason required; recorded as an override.", "No reason needed."],
    ], [0.22, 0.39, 0.39])
    s += bullets([
        "A check is decided <b>once</b>; the decision cannot be edited afterwards.",
        "A reviewer <b>cannot decide a check they submitted</b>. An admin can, and the audit log marks it.",
        "Anyone signed in can <b>comment</b> on a check.",
        "The <b>audit log</b> records sign-ins and failed sign-ins, registrations and approvals, every check, every correction to a scan, every decision, "
        "comment, AI summary request and register edit. The tool only ever adds to it.",
    ])
    s += figure("audit-log.jpg", "Figure 8. The audit log.", 0.85)

    s += [H1("12. Keeping the data safe")]
    s += bullets([
        "Everything the tool records is in one database file and one uploads folder under " + c("backend/var/") + ". It survives a page refresh, a restart of the server and a restart of the computer.",
        "When the code needs different tables, the server upgrades the database at start-up <b>without losing rows</b>, and copies the database to a backups folder first.",
        "An automated test fails if anyone changes a table without writing the matching upgrade step.",
        "Reloading the ERP extract replaces only what came from the ERP. Checks, decisions and an admin's register edits are left alone.",
        "The walkthrough's reset option moves old data to an archive folder; it does not delete it.",
    ])

    s += [H1("13. The screens")]
    s += table([
        ["Screen", "What it shows"],
        ["Sign in", "Username and password, and a tab to register as an engineer or a reviewer."],
        ["Dashboard", "Checks awaiting a decision, blocked work orders, drawings awaiting class approval, recent checks, and what is waiting for you."],
        ["Drawing Register", "The register with search and filter, each drawing's class approval and latest check. Admin: Add drawing."],
        ["Drawing detail", "Revision history with change notes, bill of materials, work orders, class approvals, checks. Admin: Update drawing."],
        ["New Check", "Upload, see what was read (confirm it for a scan), run the check."],
        ["Check report", "Verdict; title block beside register; tabs for Findings, Drawing sheet, Revision changes, BOM and Impact; decision; comments; print."],
        ["Checks", "All checks, filterable by verdict and decision."],
        ["Release Gate", "Every work order: Clear, Warn or Blocked, with reasons."],
        ["Class Approvals", "What is waiting for class or the customer, and for how long."],
        ["Rule Library", "The rules with clause, severity, parameters and who approved each. Admin: approve or withdraw a rule."],
        ["Audit Log", "Reviewer and admin."],
        ["Users", "Admin: approve, disable and re-enable accounts."],
    ], [0.22, 0.78])
    s += figure("update-drawing.jpg", "Figure 9. An admin moving a drawing to a new revision. The old revision becomes superseded and its work orders are blocked.", 0.85)

    s += [H1("14. The walkthrough kit")]
    s += [P("Everything needed to try the tool is in the " + c("setup/") + " folder: a start script, the logins, the representative ERP files, eight representative drawings, a "
            "4.5-minute captioned video and the script that records it.")]
    s += table([
        ["Drawing", "What it shows", "Verdict"],
        ["01 GRSE-H-101 rev A", "A superseded revision: the register has moved on to B.", "Blocked"],
        ["02 GRSE-H-101 rev B", "A clean drawing, compared automatically with revision A.", "Pass"],
        ["03 GRSE-H-102 rev A", "Wrong grade, plate too thin, old edition, missing note, parts list disagrees with the ERP.", "Blocked"],
        ["04 GRSE-H-103 rev A", "Old customer-spec edition, a recommended note missing, a quantity differs from the ERP.", "Needs review"],
        ["05 GRSE-M-210 rev A", "Issued for information only.", "Blocked"],
        ["06, 07", "Scans of drawings 01 and 02.", "Blocked, Pass"],
        ["08", "A scan of drawing 03; OCR misreads the grade, for the person to correct.", "Blocked"],
    ], [0.24, 0.58, 0.18])
    s += figure("drawing-bow-block.png", "Figure 10. One of the representative drawings: an invented bow block with a title block, parts list, notes and item balloons.", 0.80)
    s += [P("To start it, run " + c(r".\setup\run.ps1") + " from the project folder in PowerShell. A step-by-step walkthrough is in " + c("setup/README.md") + ".")]

    s += [H1("15. How it was built")]
    s += table([
        ["Phase", "What was added"],
        ["1", "The checking engine: reading the title block and parts list, the register check, the rules, the verdict, and an API."],
        ["2", "The web app, sign-in with roles, the reviewer's decision and the audit log."],
        ["3", "Revision comparison: the change list and the red/green overlay."],
        ["4", "BOM consistency, change impact, the release gate, class approval tracking, the drawing detail page; the walkthrough folder."],
        ["—", "A durable database with upgrades and backups; the admin role, reviewer registration and comments."],
        ["5", "Scanned drawings: OCR, confirmation, straightening two scans before comparing."],
        ["6", "The optional AI summary and its safeguards."],
        ["—", "The example video, ship-style representative drawings, and register editing for the admin."],
        ["—", "Rules that depend on zone and on a calculated formula; rule approval in the tool."],
    ], [0.10, 0.90])

    s += [H1("16. What is not done: honest limits")]
    s += bullets([
        "<b>The title-block reading is tied to the representative sheet layout.</b> A real GRSE drawing will not be read correctly until its layout is mapped.",
        "<b>The rules are representative.</b> The clause numbers, limits and formulas are invented. The tool can now apply rules by zone and by formula, and records who "
        "approved each, but real content must be written and approved by a naval architect. The walkthrough approvals were made by a setup script, not by an expert.",
        "<b>The zone comes from the title block</b>, one zone per drawing. A drawing covering several zones, or a rule needing more ship data than length, needs more work.",
        "<b>The tool reads text and compares pictures.</b> It does not understand a hull form, a weld symbol or a dimension line.",
        "<b>Only the first sheet</b> of a drawing is read, and revisions are ordered as single letters.",
        "<b>The scans tested are clean simulated ones.</b> Real scans with stamps, handwriting and folds will need more corrections.",
        "<b>Sign-in is basic:</b> no lockout after wrong passwords, and the walkthrough passwords sit in a plain file.",
        "<b>The web app has no automated tests</b>; the backend has 60.",
        "<b>Nothing was validated with GRSE data.</b> That is the next stage.",
    ])
    build("1-Project-Overview-and-Flow.pdf", "Project Overview and Flow", "What the project is, and how a drawing moves through it",
          "This document explains the project to someone who has not seen it: the problem, the idea, who uses the tool, and what happens to a drawing "
          "from upload to release. It needs no programming knowledge. The companion document, <i>Code Explanation</i>, covers how it is built.",
          contents, s)


# =====================================================================================================================
# Document 2: the code
# =====================================================================================================================

def code_explanation():
    contents = [
        "Technology choices", "Map of the repository", "Architecture in one picture", "Following one upload through the code",
        "Backend: foundations", "Backend: the checking engine", "Backend: the API", "The database", "API reference",
        "Frontend", "Tests", "How to change things", "Known shortcuts",
    ]
    s = []

    s += [H1("1. Technology choices")]
    s += table([
        ["Layer", "Choice", "Why"],
        ["API", "FastAPI on uvicorn, Pydantic for request and response shapes", "Typed contracts, and a built-in test page at /docs."],
        ["Database", "SQLite through SQLAlchemy, Alembic for migrations", "One file and nothing to install; tables change without losing data; one setting moves it to PostgreSQL."],
        ["PDF", "PyMuPDF", "Reads text with positions, finds tables, renders pages to images, and draws the representative drawings."],
        ["OCR", "Tesseract, called as a program", "Runs on the machine, gives a confidence per word. No Python OCR library is needed."],
        ["Images", "NumPy and OpenCV", "The pixel overlay, and straightening two scans against each other."],
        ["AI summary", "Any service speaking the OpenAI chat format (Groq by default), called with httpx", "Optional; the provider and model are settings."],
        ["Frontend", "React with TypeScript, built by Vite", "Typed API responses catch mistakes early."],
        ["UI components", "Ant Design, recoloured in one theme file", "Dense tables, tags, forms and layout built in."],
        ["Server state", "TanStack Query", "Fetching, caching and refetching after a change, without hand-written loading flags."],
        ["Tests", "pytest", "The engine and the API are covered; the web app is not yet."],
    ], [0.15, 0.37, 0.48])

    s += [H1("2. Map of the repository")]
    s += code("""GRSE/
  backend/
    app/
      main.py            starts the API; serves the built web app when frontend/dist exists
      config.py          folder locations, limits, optional settings read from the environment or .env
      db.py              database connection, migrations at start-up, backups
      models.py          the database tables
      schemas.py         the shape of what the API accepts and returns
      auth.py            password hashing, sessions, role checks, the audit helper
      rulebook.py        the rule file joined with who approved each rule
      api/
        auth.py          sign in/out, reviewer registration, user management
        checks.py        read a drawing, create a check, images, decision, comments, AI summary
        erp.py           register (and admin edits), drawing detail, release gate, class approvals
        reference.py     rule list, settings, audit log
      core/              the checking logic; knows nothing about the web or the database
        extract.py       PDF -> plain data, for vector PDFs and for scans
        ocr.py           runs Tesseract
        rules.py         the check types, the rule runner, the verdict
        formula.py       works out a rule's formula safely (arithmetic only)
        bom.py           parts list against the ERP bill of materials
        diff.py          what changed between two revisions: change list and overlay image
        impact.py        work orders and purchase orders affected by a change
        gate.py          may this work order be released?
        explain.py       the optional AI summary
    data/rules/rules.json   the representative rules
    migrations/             one file per change to the database tables
    scripts/                make_samples, load_extract, seed_users, approve_seed_rules, new_migration
    tests/                  test_core, test_api, test_db
    var/                    created at run time: database, backups, uploads
  frontend/
    src/
      main.tsx  App.tsx  theme.ts  api.ts  index.css
      components/          layout, tags, tables, sheet viewer, decision panel, forms
      pages/               one file per screen
  setup/                     start script, logins, representative ERP files, representative drawings, video
  docs/                     these documents and the script that builds them
  learning.md  README.md""", wrap=110)

    s += [H1("3. Architecture in one picture")]
    w = WIDTH
    s += [boxes(w, 190, [
        (w / 2 - 95, 150, 190, 34, "React web app", "pages · components · api.ts", PALE),
        (w / 2 - 95, 96, 190, 34, "API layer (app/api)", "who may call, request and response shapes", PALE),
        (w / 2 - 95, 42, 190, 34, "Core engine (app/core)", "plain data in, plain data out", NAVY),
        (0, 96, 110, 34, "Storage", "SQLite · uploads", PALE),
        (0, 42, 110, 34, "ERP extract", "CSV files, read-only", PALE),
        (w - 110, 42, 110, 34, "Tesseract", "OCR program", PALE),
        (w - 110, 96, 110, 34, "Model service", "optional AI summary", PALE),
    ], [
        (w / 2, 150, w / 2, 132, "JSON over /api"),
        (w / 2, 96, w / 2, 78, "calls"),
        (w / 2 - 95, 113, 112, 113, ""),
        (110, 59, 110, 94, ""),
        (w / 2 + 95, 59, w - 112, 59, ""),
        (w / 2 + 95, 113, w - 112, 113, ""),
    ])]
    s += [P("Figure 1. The layers. The API layer is the only part that talks to both the database and the engine.", "caption")]
    s += note("<b>The rule that keeps this tidy:</b> nothing in " + c("app/core") + " imports the web framework or the database. Each function there takes "
              "plain Python data (dictionaries and lists) and returns plain data. That is why the engine can be tested without starting a server, and "
              "could be reused from a command line or another framework.")

    s += [H1("4. Following one upload through the code")]
    s += steps([
        ("The browser sends the file", c("pages/NewCheck.tsx") + " posts the PDF to " + c("POST /api/checks/read") + " to show what was read, then to "
                                       + c("POST /api/checks") + " to run the check. For a scan it also sends the confirmed title-block values."),
        ("The request is checked", c("api/checks.py: create_check") + ". The " + c("submitter") + " dependency from " + c("auth.py") + " lets through only an engineer or an admin. "
                                   + c("read_drawing") + " refuses files over 25 MB or that do not start with the PDF signature."),
        ("The drawing is read", c("core/extract.py: extract") + " returns one dictionary: " + c("fields") + ", " + c("parts") + ", " + c("standards") + ", " + c("lines")
                                + ", " + c("text") + ", " + c("source") + ". A page with no text goes down the OCR path in the same file."),
        ("A scan is confirmed", c("apply_confirmation") + " replaces what OCR read with what the person confirmed and remembers the original as " + c("read_as") + "."),
        ("The ERP's view is gathered", "The register row, the bill of materials for this drawing revision and the particulars of its hull are read from the database and passed to the engine as one bundle called " + c("erp") + "."),
        ("The rules run", c("rulebook.py: rulebook") + " gives the rules with their approval state; " + c("core/rules.py: run_checks") + " calls the check function named by each approved rule and collects findings; " + c("verdict") + " reduces them to one word."),
        ("The previous revision is compared", c("core/diff.py: compare") + " produces the change list; " + c("core/impact.py: impact") + " turns it into affected work orders and purchase orders."),
        ("Everything is stored", "One " + c("Check") + " row with its " + c("Finding") + " rows, the uploaded file under a generated name, and snapshots (register row, BOM comparison, "
                                 "revision changes, impact) as JSON. " + c("audit(...)") + " adds a line to the audit log."),
        ("The report is shown", "The response has the shape " + c("schemas.CheckOut") + ". " + c("pages/CheckReport.tsx") + " draws it; images come from "
                                + c("GET /api/checks/{id}/sheet.png") + " and " + c("diff.png") + ", rendered on request."),
    ])

    s += [H1("5. Backend: foundations")]
    s += [H2("config.py: where things are")]
    s += [P("Paths and limits in one place. Read-only inputs live in " + c("setup/") + " and " + c("backend/data/rules/") + "; everything the tool writes lives in "
            + c("backend/var/") + ". Optional settings come from environment variables or a " + c(".env") + " file: " + c("GRSE_DATABASE_URL") + ", "
            + c("GRSE_EXPLAINER_KEY / _URL / _MODEL") + ", " + c("GRSE_TESSERACT") + ", " + c("GRSE_COOKIE_SECURE") + ", " + c("GRSE_VAR_DIR") + ".")]
    s += [H2("db.py: the database, and upgrading it safely")]
    s += [P(c("migrate()") + " runs every time the server starts. It finds which migration the database is on, takes a backup if newer ones exist, then applies them. "
            "A database from before migrations existed is recognised and marked as being on the first migration.")]
    s += excerpt("backend/app/db.py", "migrate")
    s += [H2("models.py: the tables")]
    s += [P("SQLAlchemy classes, one per table. The first group is a copy of the ERP extract; the second is what the tool itself records. Section 8 lists them. "
            "Two helpers live here: " + c("UTCDateTime") + " puts the timezone back on times read from SQLite, and " + c("as_dict") + " turns a row into plain data for the engine.")]
    s += [H2("auth.py: who is signed in, and what they may do")]
    s += bullets([
        "Passwords are stored only as a salted scrypt hash.",
        "A session is a random token in an HttpOnly cookie; the database stores a hash of the token with an 8-hour expiry.",
        c("current_user") + " is a FastAPI dependency: add it to a route and the route requires a signed-in, active user.",
        c("require(...)") + " builds a dependency that lets through certain roles. An admin passes everywhere.",
    ])
    s += excerpt("backend/app/auth.py", "require")

    s += [H1("6. Backend: the checking engine")]
    s += [H2("extract.py: from PDF to plain data")]
    s += [P("The reading is <b>template-based</b>: a few constants at the top of the file describe the representative sheet, namely where the title block sits, the labels "
            "printed in it, and how wide the value under each label is. To support a real title block, these constants are what changes.")]
    s += excerpt("backend/app/core/extract.py", "_title_block")
    s += [P("For a vector PDF the parts list comes from PyMuPDF's table finder. For a scan, " + c("_parts_scan") + " rebuilds it from word positions: the heading row gives "
            "the column positions, the words beneath give the rows, and an empty cell is read again on its own by " + c("ocr.read_cell") + ". Both paths return the same "
            "dictionary, so the rest of the code does not care which kind of file it was.")]
    s += [H2("ocr.py: calling Tesseract")]
    s += [P("Tesseract is run as a separate program: the page image goes in on standard input and a table of words comes back. Two passes with different page settings are merged.")]
    s += excerpt("backend/app/core/ocr.py", "read_words")
    s += [H2("rules.py: rules are data, checks are code")]
    s += [P("Every check type is a small function with the same signature: it receives the drawing, the ERP bundle and the rule's parameters, and <i>yields</i> one "
            "(evidence, position) pair for each problem. This one checks plate thickness in the title block and on every parts-list row:")]
    s += excerpt("backend/app/core/rules.py", "min_thickness")
    s += [P("The rule that uses it is an entry in " + c("backend/data/rules/rules.json") + ":")]
    s += code('''{
  "id": "CHK-04",
  "name": "Plate thickness meets the absolute minimum",
  "type": "min_thickness",
  "severity": "critical",
  "clause": "REF-CLS 3.4.2",
  "standard": "REF-CLS STEEL SHIP RULES",
  "edition": 2024,
  "params": { "min_mm": 6 },
  "seed_state": "approved"
}''')
    s += [P("The file <i>defines</i> a rule; it does not approve it. (" + c("seed_state") + " only tells the walkthrough's setup script which rules to approve the first time.)")]
    s += [P("The runner ties the two together, and the verdict is three lines:")]
    s += excerpt("backend/app/core/rules.py", "run_checks")
    s += excerpt("backend/app/core/rules.py", "verdict")
    s += [H2("Rules by zone and by formula")]
    s += [P("A rule can carry one formula per structural zone. The check reads the zone and stiffener spacing from the title block and the ship's length from the ERP "
            "bundle, works out the requirement, and puts the working into the evidence:")]
    s += excerpt("backend/app/core/rules.py", "required_thickness")
    s += [P("The formula is text in the rule file, so it must never be run as code. " + c("core/formula.py") + " parses it and allows only numbers, named quantities, "
            "arithmetic, brackets and three functions. Anything else is refused, and a rule with a broken formula is rejected when the rule file is read.")]
    s += excerpt("backend/app/core/formula.py", "evaluate")
    s += [H2("rulebook.py: which rules are in force")]
    s += [P("An approval is a row in the database holding a fingerprint (a hash) of the rule's content. A rule is in force only if its newest approval has not been "
            "withdrawn and its fingerprint still matches the rule file. Editing a rule therefore takes it out of use until someone approves the new content.")]
    s += excerpt("backend/app/rulebook.py", "rulebook")
    s += [H2("bom.py: parts list against the bill of materials")]
    s += excerpt("backend/app/core/bom.py", "compare_bom")
    s += [H2("diff.py: what changed between two revisions")]
    s += [P(c("compare(old, new)") + " returns a flat list of changes, each with an area (Title block, Parts list, Sheet text), a kind (added, removed, changed), the old "
            "and new values and their positions on each sheet. Other text is matched <i>by wording, not position</i>, so notes that merely moved are not reported. "
            + c("overlay_png") + " renders both sheets, straightens scans with OpenCV, and colours each pixel grey, red or green, with a tolerance so that tiny "
            "rendering differences are not shown as changes.")]
    s += excerpt("backend/app/core/diff.py", "_only_in")
    s += [H2("impact.py and gate.py: the ERP questions")]
    s += excerpt("backend/app/core/impact.py", "impact")
    s += [P("The gate takes four plain facts and returns a status with reasons. Because it is a pure function, every combination is covered by a table of test cases.")]
    s += excerpt("backend/app/core/gate.py", "gate")
    s += [H2("explain.py: the optional AI summary")]
    s += [P(c("as_text") + " builds the exact text that is sent (the change list and nothing else). " + c("explain") + " posts it with a fixed instruction, and reports errors by "
            "status code only so the key can never reach a screen. Then every number in the answer is checked against what was sent:")]
    s += excerpt("backend/app/core/explain.py", "unsupported_numbers")

    s += [H1("7. Backend: the API")]
    s += [P("Each file in " + c("app/api") + " is a FastAPI router. A route's job is to check who is calling, validate the input, fetch what the engine needs, call the "
            "engine, store the result and write the audit line. The logic itself stays in " + c("app/core") + ".")]
    s += [P("The reviewer's decision shows the pattern, including the three safeguards (decide once, not your own submission, a reason when going against the verdict):")]
    s += excerpt("backend/app/api/checks.py", "decide")
    s += [P("The release gate route gathers the facts for every work order and hands each set to the pure " + c("gate") + " function:")]
    s += excerpt("backend/app/api/erp.py", "gate_rows")

    s += [H1("8. The database")]
    s += table([
        ["Table", "Holds", "Filled by"],
        [c("drawings"), "Number, title, current revision, status, source (erp or manual)", "ERP extract; admin edits"],
        [c("drawing_revisions"), "Every revision, its status and issue date", "ERP extract; admin edits"],
        [c("change_notes"), "Engineering change notes: what, when, why", "ERP extract"],
        [c("bom_items"), "Parts per drawing revision: material, thickness, quantity", "ERP extract"],
        [c("work_orders"), "Order, drawing, revision released against, state", "ERP extract"],
        [c("purchase_orders"), "Order, part, quantity, state", "ERP extract"],
        [c("class_approvals"), "Submitted to whom, when, outcome", "ERP extract"],
        [c("ship_particulars"), "Hull number and the ship's rule length, for calculated rules", "ERP extract"],
        [c("rule_approvals"), "Who approved which rule, a fingerprint of its content, and any withdrawal", "Tool"],
        [c("users"), "Username, name, role, password hash, status", "Logins file; registration"],
        [c("auth_sessions"), "Hash of a session token, user, expiry", "Sign-in"],
        [c("checks"), "One run: drawing, verdict, what was read, and snapshots as JSON (register row, revision changes, BOM comparison, impact, AI summary)", "Tool"],
        [c("findings"), "Each finding, with a copy of the rule's name, clause and standard", "Tool"],
        [c("decisions"), "The reviewer's decision, reason, override flag (one per check)", "Tool"],
        [c("comments"), "Comments on a check", "Tool"],
        [c("audit_log"), "Who did what and when", "Tool"],
    ], [0.20, 0.56, 0.24])
    s += [P("<b>Why snapshots and copies?</b> A report must stay true after the ERP data or a rule changes. So a check keeps the register row as it was, and a finding "
            "keeps its own copy of the clause it was judged against, instead of pointing at data that may later change.")]
    s += [P("<b>Migrations.</b> " + c("backend/migrations/versions/") + " has one numbered file per change. After editing " + c("models.py") + ", run "
            + c('python -m scripts.new_migration 0005 "what changed"') + " from " + c("backend/") + ", read the generated file, and keep it. "
            + c("tests/test_db.py") + " fails if the tables the migrations build differ from the tables the code expects.")]

    s += [H1("9. API reference")]
    s += table([
        ["Route", "Who", "Does"],
        [c("POST /api/auth/login"), "Anyone", "Sign in; sets the session cookie"],
        [c("POST /api/auth/logout"), "Signed in", "End the session"],
        [c("GET /api/auth/me"), "Signed in", "Who is signed in"],
        [c("POST /api/auth/register"), "Anyone", "Ask for an engineer or reviewer account (pending until approved)"],
        [c("GET /api/users"), "Admin", "All accounts"],
        [c("POST /api/users/{u}/status"), "Admin", "Approve, disable or re-enable"],
        [c("POST /api/checks/read"), "Signed in", "What the tool reads from a PDF; stores nothing"],
        [c("POST /api/checks"), "Signed in", "Run and store a check"],
        [c("GET /api/checks"), "Signed in", "All checks, newest first"],
        [c("GET /api/checks/{id}"), "Signed in", "One report"],
        [c("GET /api/checks/{id}/sheet.png"), "Signed in", "The sheet as an image (also previous.png, diff.png)"],
        [c("POST /api/checks/{id}/decision"), "Admin", "Approve or reject"],
        [c("POST /api/checks/{id}/comments"), "Signed in", "Add a comment"],
        [c("POST /api/checks/{id}/explanation"), "Signed in", "Ask for the AI summary (made once)"],
        [c("GET /api/register"), "Signed in", "The register"],
        [c("POST /api/register"), "Admin", "Add a drawing"],
        [c("GET /api/register/{no}"), "Signed in", "One drawing with history, BOM, orders, approvals"],
        [c("PUT /api/register/{no}"), "Admin", "Update a drawing"],
        [c("GET /api/gate"), "Signed in", "Gate status of every work order"],
        [c("GET /api/gate/{order}"), "Signed in", "Gate status of one work order"],
        [c("GET /api/class-approvals"), "Signed in", "Approvals, longest wait first"],
        [c("GET /api/rules"), "Signed in", "The rules with their approval state"],
        [c("POST /api/rules/{id}/approval"), "Admin", "Approve a rule as it stands"],
        [c("POST /api/rules/{id}/withdrawal"), "Admin", "Take a rule out of use"],
        [c("GET /api/settings"), "Signed in", "Whether the AI summary is on, and its model"],
        [c("GET /api/audit"), "Reviewer, admin", "The audit log"],
    ], [0.40, 0.18, 0.42])
    s += [P("With the server running, " + c("/docs") + " shows the same list as an interactive page generated by FastAPI.")]

    s += [H1("10. Frontend")]
    s += table([
        ["File", "Role"],
        [c("main.tsx"), "Starts the app and wraps it in the theme, the data cache and the router. A 401 from any request sends the user back to sign-in."],
        [c("App.tsx"), "Shows the sign-in page or the app, and lists the routes."],
        [c("theme.ts"), "Colours in one place: the navy, and the status colours used by tags, banners and sheet markers."],
        [c("api.ts"), "The types of everything the server returns, the " + c("api()") + " fetch helper, one hook per kind of data ("
                      + c("useChecks") + ", " + c("useGate") + " ...), and " + c("can") + ", which says what each role may see."],
        [c("components/"), "Reusable parts: " + c("AppLayout") + ", " + c("Tags") + ", " + c("ChecksTable") + ", " + c("GateTable") + ", " + c("SheetViewer") + ", "
                           + c("RevisionChanges") + ", " + c("ErpChecks") + ", " + c("DecisionPanel") + ", " + c("Comments") + ", " + c("Explanation") + ", " + c("DrawingForm") + "."],
        [c("pages/"), "One file per screen. A page asks for data with a hook and arranges components."],
        [c("index.css"), "The few styles Ant Design does not cover: the walkthrough banner, sheet markers, print layout."],
    ], [0.20, 0.80])
    s += [H2("Three ideas worth understanding")]
    s += bullets([
        "<b>Server state lives in a cache.</b> A page calls a hook such as " + c("useCheck(id)") + "; TanStack Query fetches, remembers and shares the result. After a change "
        "(a decision, an upload, a register edit) the code <i>invalidates</i> the affected keys and the screens that use them refetch.",
        "<b>The server is the authority on permissions.</b> " + c("can.submit(user)") + " only decides what to show. The same rule is enforced again by the API, so hiding a button is never the only protection.",
        "<b>Markers on a sheet are percentages.</b> The server stores a finding's position in PDF points. " + c("SheetViewer") + " divides by the page size and positions a box by percentage over "
        "the image, so markers stay in place at any zoom.",
    ])
    s += [P("During development two servers run: Vite on port 5173 forwards " + c("/api") + " to uvicorn on port 8000. For a real run, " + c("npm run build")
            + " produces " + c("frontend/dist") + " and the backend serves it, so there is one process.")]

    s += [H1("11. Tests")]
    s += table([
        ["File", "What it proves"],
        [c("tests/test_core.py"), "The engine: what is read from each example; the verdict and rule set for each; per-part findings; the BOM comparison; the gate's "
                                  "decision table; change impact; the change list and the overlay; scans read like their originals; crooked scans are straightened; "
                                  "zone and formula rules, and that a formula can contain arithmetic and nothing else."],
        [c("tests/test_api.py"), "The API: everything needs a sign-in; each role's limits; uploads and bad uploads; decisions and their safeguards; registration and "
                                 "approval; comments; the gate following a decision; scan confirmation; the AI summary (with a stand-in model) and what it sends; admin register edits surviving an extract reload; "
                                 "a rule running only while an approval of its exact content stands."],
        [c("tests/test_db.py"), "Migrations build exactly the tables the code expects; upgrading keeps the data and takes a backup."],
    ], [0.24, 0.76])
    s += [P("Run them from " + c("backend/") + " with " + c(r".\.venv\Scripts\python.exe -m pytest -q") + ". Tests use a temporary database and temporary example drawings, never the real "
            "data. The OCR tests are skipped on a machine without Tesseract. The suite never calls the real model service.")]

    s += [H1("12. How to change things")]
    s += table([
        ["To do this", "Change this"],
        ["Add a rule of an existing kind", "Add an entry to " + c("backend/data/rules/rules.json") + " with a clause, severity and parameters, then approve it as admin on the Rule Library screen."],
        ["Change a rule's limit or formula", "Edit its entry in the rule file. It shows as “changed” and stops running until an admin approves it again."],
        ["Add a new kind of check", "Write a function in " + c("core/rules.py") + " with the " + c("(d, erp, p)") + " signature that yields (evidence, position); add it to " + c("CHECKS") + "; add a test."],
        ["Support a real title block", "Change " + c("TITLE_BLOCK") + ", " + c("FIELDS") + " and the parts-list headings at the top of " + c("core/extract.py") + "; regenerate or add examples; update the tests' expected values."],
        ["Add a column or a table", "Edit " + c("models.py") + ", run " + c("scripts.new_migration") + ", read the generated migration, run the tests."],
        ["Give rules more ERP data", "Add it to the " + c("erp") + " bundle built in " + c("api/checks.py: create_check") + "; every check function already receives the bundle."],
        ["Add a screen", "A file in " + c("pages/") + ", a route in " + c("App.tsx") + ", a menu entry in " + c("components/AppLayout.tsx") + ", and a hook in " + c("api.ts") + " if it needs new data."],
        ["Change the AI model or provider", "Set " + c("GRSE_EXPLAINER_MODEL") + " / " + c("GRSE_EXPLAINER_URL") + " in " + c("backend/.env") + ". No code change."],
        ["Move to PostgreSQL", "Set " + c("GRSE_DATABASE_URL") + " and install a PostgreSQL driver. The migrations run there too."],
        ["Re-record the video, rebuild these documents", c("python setup/record_walkthrough.py") + " (with the backend environment) and " + c("python docs/build_docs.py") + "."],
    ], [0.30, 0.70])

    s += [H1("13. Known shortcuts")]
    s += [P("Where a simpler solution with a known limit was chosen on purpose, the code says so in a comment beginning " + c("shortcut:") + ". This list is collected from the source when the document is built.")]
    s += table([["Where", "The limit, and when to upgrade"]] + shortcuts(), [0.30, 0.70])
    s += [P("Larger gaps that are not single lines of code (real title-block layout, real rules, directory sign-in, frontend tests) are listed at the end of the <i>Project Overview and Flow</i> document.")]

    build("2-Code-Explanation.pdf", "Code Explanation", "How the code is organised, and what each part does",
          "This document is for someone who will read or change the code. It explains the structure, follows one upload through the files, and shows the "
          "key functions. The code excerpts are copied from the source files when the document is built, so they match the code as it is. Read "
          "<i>Project Overview and Flow</i> first for what the tool does.", contents, s)


if __name__ == "__main__":
    overview()
    code_explanation()
