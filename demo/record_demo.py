"""Records demo/sample-demo-video.mp4: a scripted walk through the tool in a real browser, with captions.

Needs once:   backend\\.venv\\Scripts\\python.exe -m pip install playwright
Run from the project folder:   backend\\.venv\\Scripts\\python.exe demo\\record_demo.py
Add --short for the one-minute version, saved as demo/short-demo-video.mp4.

It drives the Edge browser that is already on Windows (nothing else is downloaded) and starts its own copy of the
tool on port 8020 with an empty, temporary database, so your own checks and decisions are not touched.
Drawings 08 needs Tesseract; the AI summary step is skipped when no API key is set.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BACKEND, DRAWINGS = ROOT / "backend", ROOT / "demo" / "drawings"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
PORT = 8020
BASE = f"http://127.0.0.1:{PORT}"
SIZE = {"width": 1366, "height": 768}
OUTPUT = ROOT / "demo" / "sample-demo-video.mp4"
LOGINS = {u["username"]: u["password"] for u in json.loads((ROOT / "demo" / "demo_logins.json").read_text(encoding="utf-8"))}

# A caption bar drawn by the page itself, so it is part of the recording. It survives moving between screens.
CAPTION_JS = """
if (window.top !== window) throw new Error('captions belong to the main page only, not to an embedded PDF viewer');
window.__caption = (text) => {
  sessionStorage.setItem('demoCaption', text);
  let bar = document.getElementById('demo-caption');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'demo-caption';
    bar.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);max-width:80%;z-index:99999;' +
      'background:rgba(12,34,67,.94);color:#fff;font:600 18px/1.35 Segoe UI,sans-serif;padding:10px 22px;border-radius:8px;' +
      'box-shadow:0 4px 18px rgba(0,0,0,.35);text-align:center;pointer-events:none';
    document.body.appendChild(bar);
  }
  bar.textContent = text;
  bar.style.display = text ? 'block' : 'none';
};
document.addEventListener('DOMContentLoaded', () => window.__caption(sessionStorage.getItem('demoCaption') || ''));
"""


def start_tool(var_dir: Path) -> subprocess.Popen:
    env = {**os.environ, "GRSE_VAR_DIR": str(var_dir)}
    for script in ("scripts.load_extract", "scripts.seed_users", "scripts.approve_demo_rules"):
        subprocess.run([PYTHON, "-m", script], cwd=BACKEND, env=env, check=True, capture_output=True)
    server = subprocess.Popen([PYTHON, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=BACKEND, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{BASE}/api/auth/me")
        except urllib.error.HTTPError:
            return server  # "not signed in" is an answer: the tool is up
        except OSError:
            time.sleep(0.5)
    server.kill()
    raise RuntimeError("The tool did not start.")


class Demo:
    def __init__(self, page):
        self.page = page

    def say(self, text: str, seconds: float = 3.5):
        self.page.evaluate("text => window.__caption(text)", text)
        self.page.wait_for_timeout(int(seconds * 1000))

    def pause(self, seconds: float = 1.5):
        self.page.wait_for_timeout(int(seconds * 1000))

    def sign_in(self, username: str):
        page = self.page
        page.goto(BASE)
        page.locator("#signin_username").press_sequentially(username, delay=60)
        page.locator("#signin_password").press_sequentially(LOGINS[username], delay=40)
        page.get_by_role("button", name="Sign in").click()
        page.get_by_role("link", name="Dashboard").wait_for()

    def sign_out(self):
        self.page.get_by_role("button", name="Sign out").click()
        self.page.get_by_role("button", name="Sign in").wait_for()

    def menu(self, name: str):
        self.page.get_by_role("link", name=name, exact=True).click()
        self.pause(1)

    def tab(self, name: str):
        self.page.get_by_role("tab", name=re.compile(f"^{name}")).click()
        self.pause(1)

    def scroll(self, pixels: int, seconds: float = 1.5):
        self.page.mouse.move(SIZE["width"] * 0.55, SIZE["height"] * 0.5)
        for _ in range(10):
            self.page.mouse.wheel(0, pixels / 10)
            self.page.wait_for_timeout(60)
        self.pause(seconds)

    def top(self):
        self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        self.pause(1)

    def check(self, file_name: str, before_run=None) -> str:
        """Upload a drawing under New Check and run it. Returns the address of its report."""
        page = self.page
        self.menu("New Check")
        page.locator("input[type=file]").first.set_input_files(DRAWINGS / file_name)
        page.get_by_role("button", name=re.compile("Run compliance check|Confirm these values")).wait_for(timeout=60000)
        page.wait_for_function("!document.querySelector('.ant-spin')", timeout=60000)
        self.pause(1.5)
        if before_run:
            before_run()
        run = page.get_by_role("button", name=re.compile("Run compliance check|Confirm these values"))
        run.scroll_into_view_if_needed()
        run.click()
        # The app changes screens without reloading the page, so wait for the address itself to change.
        page.wait_for_function(r"/\/checks\/\d+$/.test(location.pathname)", timeout=60000)
        page.get_by_text("Title block and register").wait_for()
        return page.url.split("?")[0]


def walkthrough(d: Demo):
    page = d.page
    page.goto(BASE)
    d.say("Drawing Compliance Checker: a release gate for drawings. All data shown is mock data.", 4.5)

    # --- Engineer ---
    d.say("An engineer signs in.", 2)
    d.sign_in("engineer")
    d.say("The dashboard: checks awaiting a decision, blocked work orders, class approvals.", 4)

    d.menu("Release Gate")
    d.say("Release Gate, before any check: two work orders are already blocked by the register alone.", 5)

    d.say("New Check: upload a drawing. Here, revision A of a deck plating drawing.", 3)
    d.check("01_GRSE-H-101_revA_superseded-revision.pdf", lambda: d.say("The title block is read from the PDF and shown before the check runs.", 4))
    d.say("Blocked: the register has moved on to revision B.", 3.5)
    d.scroll(450, 1)
    d.say("And the 10 mm deck plate is below the thickness calculated for this zone and this ship.", 5.5)

    d.say("Now the current revision, B.", 2.5)
    report_b = d.check("02_GRSE-H-101_revB_clean-pass.pdf")
    d.say("Pass: it matches the register and passes every rule.", 4)
    d.tab("Revision changes")
    d.scroll(380)
    d.say("It is compared with revision A automatically. Red was removed, green was added.", 5)
    d.scroll(520)
    if page.get_by_role("button", name="Explain these changes in plain words").count():
        d.say("Optional: an AI-written summary of the change list. It is never part of the verdict.", 3.5)
        page.get_by_role("button", name="Explain these changes in plain words").click()
        page.get_by_text(re.compile("^Written by ")).wait_for(timeout=40000)
        d.pause(4.5)
    d.scroll(420)
    d.say("Every change is listed: title block, parts list and text on the sheet.", 4.5)
    d.top()
    d.tab("BOM")
    d.scroll(380)
    d.say("BOM: the parts list on the drawing agrees with the ERP bill of materials.", 4)
    d.tab("Impact")
    d.say("Impact: the revision change affects one work order and two open purchase orders.", 5)
    d.top()

    d.say("A non-compliant drawing.", 2)
    report_bad = d.check("03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf")
    d.say("Blocked: wrong steel grade, plate too thin, old edition of a standard, a missing note.", 4.5)
    d.scroll(480)
    d.say("Each finding has a severity, the clause it comes from, and the evidence.", 5)
    d.tab("Drawing sheet")
    d.say("The findings are marked on the drawing itself.", 4.5)
    d.tab("BOM")
    d.say("And the plate's grade and thickness disagree with what the ERP would order.", 4.5)
    d.top()

    d.say("A scanned drawing has no text in it. It is read by OCR, which takes about ten seconds.", 3)

    def correct_the_grade():
        material = page.get_by_label("Material", exact=True)
        # Scrolled by the page, not the mouse wheel: with the pointer over the embedded PDF viewer, the viewer keeps the mouse.
        material.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'smooth'})")
        d.say("OCR read the grade S275 as $275. A person confirms or corrects every value first.", 4.5)
        material.fill("")
        material.press_sequentially("S275", delay=120)
        d.say("Corrected. The check runs on the confirmed values, and the correction is recorded.", 4)

    d.check("08_GRSE-H-102_revA_scanned-copy.pdf", correct_the_grade)
    d.say("The report says it came from a scan, and shows the correction next to what OCR read.", 4)
    d.scroll(420, 3)
    d.top()

    # --- A new reviewer registers ---
    d.sign_out()
    d.say("A new reviewer registers. The account cannot be used until an admin approves it.", 3.5)
    page.get_by_role("tab", name="Register", exact=True).click()
    page.locator("#register_name").press_sequentially("R. Sen", delay=50)
    page.locator("#register_username").press_sequentially("r.sen", delay=50)
    page.locator("#register_password").press_sequentially("recorded-demo-only", delay=20)
    page.locator("#register_confirm").press_sequentially("recorded-demo-only", delay=20)
    page.get_by_role("button", name="Request account").click()
    page.get_by_text("created").wait_for()
    d.pause(3)

    # --- Reviewer ---
    d.say("An existing reviewer signs in. Reviewers upload, comment, and approve or reject.", 3)
    d.sign_in("reviewer")
    page.goto(report_bad)
    d.say("A reviewer can approve or reject a drawing that someone else uploaded.", 4)
    page.get_by_label("Add a comment").press_sequentially("Plate grade must be AH36 to match the ERP. Please reissue.", delay=25)
    page.get_by_role("button", name="Add comment").click()
    d.pause(2.5)
    d.menu("Class Approvals")
    d.say("Class Approvals: what is waiting for class or the customer, and for how long.", 4.5)
    d.menu("Drawing Register")
    page.get_by_role("link", name="GRSE-H-101").first.click()
    d.say("One drawing: its revision history with the ERP change note, BOM, work orders and checks.", 5)
    d.sign_out()

    # --- Admin ---
    d.say("The admin has full access.", 3)
    d.sign_in("Admin_123")
    d.say("The dashboard lists what needs the admin's decision.", 4)

    page.goto(report_b)
    d.say("Approving a passing drawing needs no reason.", 3.5)
    page.get_by_role("button", name="Approve for release").click()
    d.pause(1.2)
    page.locator(".ant-popconfirm").get_by_role("button", name="Approve").click()
    page.get_by_text("Decided by", exact=True).first.wait_for()
    d.pause(2.5)

    page.goto(report_bad)
    d.say("Approving a blocked drawing would be an override: it stays disabled until a reason is written.", 5)
    d.say("The admin rejects it. The decision cannot be changed afterwards.", 3)
    page.get_by_role("button", name="Reject", exact=True).click()
    d.pause(1.2)
    page.locator(".ant-popconfirm").get_by_role("button", name="Reject").click()
    d.pause(3)

    d.menu("Release Gate")
    d.say("Release Gate now: the work order for revision B is clear to release.", 5.5)
    d.menu("Users")
    d.say("The reviewer who registered is waiting for the admin to approve the account.", 3.5)
    page.get_by_role("button", name="Approve").click()
    d.pause(2.5)
    d.menu("Drawing Register")
    d.say("The admin can also add a drawing to the register, or update one.", 3)
    page.get_by_role("button", name="Add drawing").click()
    page.locator("#drawing_drawing_no").press_sequentially("GRSE-H-104", delay=50)
    page.locator("#drawing_title").press_sequentially("TANK TOP PLATING FR 60-68", delay=30)
    page.locator("#drawing_current_rev").press_sequentially("A", delay=50)
    d.pause(2)
    page.locator(".ant-modal").get_by_role("button", name="Add drawing").click()
    page.get_by_role("link", name="GRSE-H-104").wait_for()
    d.pause(2)
    page.get_by_role("link", name="GRSE-H-102").first.click()
    page.get_by_role("button", name="Update drawing").click()
    d.say("Moving a drawing to a new revision makes the old one superseded.", 2.5)
    page.locator("#drawing_current_rev").fill("")
    page.locator("#drawing_current_rev").press_sequentially("B", delay=80)
    d.pause(1.5)
    page.locator(".ant-modal").get_by_role("button", name="Save changes").click()
    page.locator(".ant-modal").wait_for(state="hidden")
    d.pause(2)
    d.menu("Release Gate")
    d.say("The work order released against the old revision is blocked straight away.", 5)
    d.menu("Audit Log")
    d.say("Every sign-in, check, correction, decision and comment is in the audit log.", 5.5)
    d.menu("Rule Library")
    d.say("The rules are fixed and clause-cited. These are mock rules; real ones need a naval architect.", 5)
    d.scroll(420, 1)
    d.say("A rule runs only once it is approved. The approval covers the rule exactly as written.", 4)
    page.get_by_role("button", name="Approve", exact=True).first.click()
    page.get_by_label("Approval note").press_sequentially("Reviewed against the mock customer spec.", delay=25)
    d.pause(1.5)
    page.locator(".ant-popconfirm").get_by_role("button", name="Approve").click()
    d.pause(3)
    d.say("End of the demo.", 2.5)


def short_walkthrough(d: Demo):
    """About a minute: one check from upload to decision, the release gate, the helper and dark mode."""
    page = d.page
    page.goto(BASE)
    d.say("Drawing Compliance Checker: a release gate for drawings at GRSE.", 3.5)
    d.sign_in("Admin_123")
    d.say("The dashboard: what is waiting for a decision, and what is blocked.", 4)

    d.say("Upload a drawing. Its title block is read straight from the PDF.", 2.5)
    d.check("03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf")
    d.say("Blocked: wrong steel grade, and the plate is too thin.", 4)
    d.scroll(480, 0.5)
    d.say("Each finding has a severity, the clause it comes from, and the evidence.", 4)
    d.tab("Drawing sheet")
    d.say("The findings are marked on the drawing itself.", 4)
    d.top()

    d.say("A reviewer or the admin decides. This one is rejected, and the decision is final.", 3)
    page.get_by_role("button", name="Reject", exact=True).click()
    d.pause(1)
    page.locator(".ant-popconfirm").get_by_role("button", name="Reject").click()
    d.pause(2.5)

    d.menu("Release Gate")
    d.say("Release Gate: which work orders may be released, and why the others may not.", 4.5)

    # force: the button bobs up and down, so the browser driver never sees it standing still.
    page.get_by_role("button", name="Open Navik, the helper").click(force=True)
    d.say("Navik, the built-in helper, answers from the live records.", 2)
    question = page.get_by_label("Your question for Navik")
    question.press_sequentially("Which work orders are blocked, and why?", delay=30)
    question.press("Enter")
    # The greeting, the question and the reply (or an error, if the model service is switched off or busy).
    page.wait_for_function("document.querySelectorAll('.helper-bubble').length >= 3 && !document.querySelector('.helper-typing')", timeout=40000)
    d.pause(4.5)
    d.say("Ask, and it takes you to a page.", 1.5)
    question.press_sequentially("Take me to the drawing register", delay=35)
    question.press("Enter")
    page.wait_for_function("document.querySelectorAll('.helper-bubble').length >= 5 && !document.querySelector('.helper-typing')", timeout=40000)
    d.pause(3)
    page.get_by_role("button", name="Minimise the helper").click()

    d.say("And a dark mode.", 1)
    page.get_by_role("switch", name="Dark mode").click()
    d.menu("Dashboard")
    d.pause(3.5)
    d.say("Drawing Compliance Checker.", 2.5)


def to_mp4(webm: Path, mp4: Path) -> bool:
    """Re-save the recording as MP4, which plays everywhere on Windows. Returns False if this machine cannot read the recording."""
    source = cv2.VideoCapture(str(webm))
    if not source.isOpened():
        return False
    fps = source.get(cv2.CAP_PROP_FPS) or 25
    writer = cv2.VideoWriter(str(mp4), cv2.VideoWriter_fourcc(*"mp4v"), fps, (SIZE["width"], SIZE["height"]))
    frames = 0
    while True:
        ok, frame = source.read()
        if not ok:
            break
        writer.write(frame)
        frames += 1
    source.release()
    writer.release()
    return frames > 0


def main():
    # "--short" records the one-minute version to its own file; the full walkthrough is the default.
    short = "--short" in sys.argv
    output = OUTPUT.with_name("short-demo-video.mp4") if short else OUTPUT
    work = Path(tempfile.mkdtemp(prefix="grse-demo-video-"))
    server = start_tool(work / "var")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport=SIZE, record_video_dir=str(work / "video"), record_video_size=SIZE)
            context.add_init_script(CAPTION_JS)
            page = context.new_page()
            page.set_default_timeout(20000)
            try:
                (short_walkthrough if short else walkthrough)(Demo(page))
            finally:
                page.screenshot(path=str(work / "last-screen.png"))  # where it stopped, if a step failed
                context.close()  # this is what finishes writing the video
                browser.close()
            recording = Path(page.video.path())
        # The recording as the browser made it: small, and plays in any web browser.
        webm = output.with_suffix(".webm")
        shutil.copy(recording, webm)
        print(f"Saved {webm}")
        # The same video as MP4, for players that do not open WebM. It is several times larger.
        print(f"Saved {output}" if to_mp4(recording, output) else "Could not convert to MP4 on this machine; use the WebM file.")
    finally:
        server.kill()
        print(f"Working files: {work}")


if __name__ == "__main__":
    sys.exit(main())
