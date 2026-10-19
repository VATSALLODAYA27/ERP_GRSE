# Demo kit

Everything needed to try the Drawing Compliance Checker. **All of it is mock data**: invented drawings, an invented register, invented clause numbers. None of it comes from GRSE.

## What is in this folder

| Item | What it is |
|---|---|
| `run-demo.ps1` | Starts the tool and opens it in the browser |
| `demo_logins.json` | The demo users and their passwords: an admin, a reviewer and two engineers |
| `register/` | The mock ERP extract. The tool reads these files and never writes to them |
| `drawings/` | Mock drawings to upload under **New Check**, numbered in demo order. They are isometric views of invented hull structure |
| `sample-demo-video.webm` / `.mp4` | A 5-minute captioned recording of the walkthrough below. The WebM is smaller and opens in any web browser; the MP4 is for other players |
| `record_demo.py` | Re-records that video. It uses its own temporary copy of the tool, so your data is not touched |

### `register/`: the mock ERP extract

| File | Holds |
|---|---|
| `drawing_register.csv` | Each drawing's number, title, current revision and status |
| `drawing_revisions.csv` | Every revision of each drawing and when it was issued |
| `engineering_change_notes.csv` | What changed between revisions, when and why |
| `bill_of_materials.csv` | Parts, material, thickness and quantity per drawing revision |
| `work_orders.csv` | Which drawing revision each job was released against |
| `purchase_orders.csv` | Orders placed for parts |
| `class_approvals.csv` | Drawings submitted to class or customer, and the outcome |
| `ship_particulars.csv` | Each hull's rule length, used by the calculated thickness rule |

You can edit these in Excel or a text editor to try other situations; rerun `run-demo.ps1` to load the changes.

### `drawings/`: what each one demonstrates

| File | Expected verdict | What it shows |
|---|---|---|
| `01_GRSE-H-101_revA_superseded-revision.pdf` | Blocked | The register has moved on to revision B, and the 10 mm deck plate is below the thickness calculated for its zone |
| `02_GRSE-H-101_revB_clean-pass.pdf` | Pass | A clean drawing; compared automatically with revision A |
| `03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf` | Blocked | Grade S275, 5 mm plate, old class edition, missing note, and a parts list that disagrees with the ERP |
| `04_GRSE-H-103_revA_old-standard-edition.pdf` | Needs review | Old customer-spec edition, a missing recommended note, quantity differs from the ERP |
| `05_GRSE-M-210_revA_for-information-only.pdf` | Blocked | Issued for information, not approved for production |
| `06_GRSE-H-101_revA_scanned-copy.pdf` | Blocked | A scan of drawing 01, read by OCR |
| `07_GRSE-H-101_revB_scanned-copy.pdf` | Pass | A scan of drawing 02, read by OCR |
| `08_GRSE-H-102_revA_scanned-copy.pdf` | Blocked | A scan of drawing 03; OCR misreads the grade, for you to correct |

Drawings 06 to 08 need Tesseract installed (see the main README).

## Start it

From the project folder, in PowerShell:

```powershell
.\demo\run-demo.ps1
```

Earlier checks, decisions and comments are kept between runs. To start from an empty tool, add `-Reset`: the earlier data is moved to `backend\var-archive\`, not deleted.

The first run installs packages and takes a few minutes. The browser opens at http://127.0.0.1:8000 when the tool is ready. Press Ctrl+C in the PowerShell window to stop.

If PowerShell refuses to run the script, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\demo\run-demo.ps1
```

## Who can do what

| Role | Can do |
|---|---|
| Engineer | Upload drawings, view everything, comment |
| Reviewer | Upload drawings, view everything, comment, read the audit log. Cannot approve or reject, and cannot change rules or the register |
| Admin | Everything. Only the admin approves or rejects a release. Also approves accounts under *Users*, edits the register and approves rules |

A new engineer or reviewer can register on the sign-in page (*Register*, then choose the account type); the account works only after the admin approves it under *Users*.

## Walkthrough (about 10 minutes)

Sign in with the `engineer` login from `demo_logins.json`.

1. **Release Gate, before any check.** Open *Release Gate*. Two work orders are already blocked from the register alone: WO-24018 was released against revision A while the register is on B, and WO-24022 uses a drawing that is only "for information". The rest warn that their revision has not been checked.
2. **A superseded drawing.** *New Check* → upload drawing `01`. Verdict: **Blocked**, citing the document-control clause.
3. **The current revision.** Upload drawing `02`. Verdict: **Pass**. Then open its tabs:
   - *Revision changes*: 8 changes against revision A, the ERP change note, and the red/green overlay.
   - *BOM*: all four parts agree with the ERP.
   - *Impact*: the change affects 1 work order and 2 open purchase orders.
4. **A non-compliant drawing.** Upload drawing `03`. Verdict: **Blocked**. *Findings* lists each problem with its clause; *Drawing sheet* marks them on the drawing; *BOM* shows the plate's grade and thickness disagree with what the ERP would order.
5. **A borderline drawing.** Upload drawing `04`. Verdict: **Needs review**.
6. **Not released for production.** Upload drawing `05`. Verdict: **Blocked**.
7. **The reviewer's call.** Sign out and sign in with the `reviewer` login. The dashboard lists what needs a decision.
   - Open the check of drawing `02` and choose *Approve for release*. No reason is needed, because it follows the verdict.
   - Open the check of drawing `04`. A reason is required either way. Approve or reject it with one.
   - Open the check of drawing `03` and try to approve: the button stays disabled until a reason is given, and the decision would be recorded as an override.
8. **Release Gate again.** WO-24019 (revision B) is now **Clear**. WO-24021 still warns, because class returned that drawing with comments.
9. **Class Approvals.** GRSE-H-103 has been waiting over 30 days and is highlighted.
10. **Comments.** On any check, add a comment in the box under the decision panel. Refresh the page: it is still there.
11. **Audit Log.** Every sign-in, check, decision and comment is listed.
12. **Register a reviewer.** Sign out, choose *Register*, pick Engineer or Reviewer and create an account. Try to sign in with it: it is refused until approved. Sign in with the admin login, open *Users* and approve it.

## Scanned drawings (about 3 minutes)

Sign in as `engineer` or the admin.

1. *New Check* → upload drawing `08`. After about 10 seconds the values read by OCR appear in boxes, with the scan shown underneath.
2. **Material** reads `$275`, marked low confidence. The drawing says `S275`. Correct it.
3. Press *Confirm these values and run the check*. The report has a banner saying it was read from a scan, and the Material row shows your correction next to what OCR read.
4. Upload drawing `06`, confirm, then drawing `07`, confirm. Open the report of `07` → *Revision changes*: the two scans were straightened against each other before being compared, and the same 8 changes are listed as for the original drawings.

## Adding and updating drawings (admin)

Sign in with the admin login.

1. *Drawing Register* → *Add drawing*. Type a number, title and revision, or press *Fill in from a drawing PDF* and pick any file from `drawings/` to have them read for you. The new drawing is tagged "Edited in the tool".
2. Open GRSE-H-102 → *Update drawing* → change the current revision to `B` → *Save changes*. Revision A becomes superseded in its history.
3. *Release Gate*: WO-24020, released against revision A, is now blocked.

These edits change the tool's copy of the register only, and rerunning the demo does not undo them.

## Rules by zone, and approving rules (admin)

1. Open the check of drawing `01` → *Findings*. Rule CHK-08 shows its working: the 10 mm deck plate is below the 10.2 mm required for a deck on a 142 m ship.
2. Open the check of drawing `04`. Rule CHK-09 reports stiffener spacing of 800 mm against a 750 mm limit for side shell.
3. Sign in as admin → *Rule Library*. Each rule shows who approved it. Expand a rule to see its parameters, including the formulas.
4. *Withdraw* CHK-09, then check drawing `04` again: the spacing finding is gone. *Approve* it again and it returns.
5. CHK-07 is a draft and has never run. *Approve* it and it applies to the next check.

All clause numbers, limits and formulas are invented. Editing a rule in `backend/data/rules/rules.json` takes it out of use until it is approved again.

## The AI summary (optional)

Needs a Groq API key (see the main README). Open the report of drawing `02` → *Revision changes* and press *Explain these changes in plain words*. A short summary appears, labelled as AI-written, above the change list it was made from. The verdict does not change.

## Things to try

- Upload `01` with `02` chosen as the *previous revision*: the comparison runs the other way.
- Upload a PDF that is not a drawing, or a non-PDF file: it is refused with a reason.
- In `register/drawing_register.csv`, change GRSE-H-102's current revision to `B`, rerun the script, and upload drawing `03` again: it is now also superseded.
