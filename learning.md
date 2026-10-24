# Learning log: Drawing Compliance Checker

This file explains what we are building, why, and what each piece does. It is updated after every phase.

## 1. The problem in one paragraph

A shipyard cuts steel from drawings. A drawing changes over time: revision A is replaced by revision B. If a work order is released to the shop floor against an old or unapproved revision, the wrong material is ordered or cut. The ERP stores which revision is current, but it does not stop anyone using the wrong one. Our tool is a **release gate**: before release, it checks the drawing and says Pass, Needs review or Blocked, with a reason for each problem.

## 2. Words you need

| Word | Meaning |
|---|---|
| **ERP / PLM** | The company's central systems. They hold the drawing register, bills of materials, work orders and purchase orders. |
| **Drawing register** | The official list: each drawing number, its current revision and its status. |
| **Title block** | The box in the corner of a drawing with its number, revision, status, material and date. |
| **Revision** | A version of a drawing (A, B, C…). Only one is current; older ones are superseded. |
| **Extract** | A read-only copy of ERP data, exported as files. We read the copy and never write to the ERP. |
| **Rule** | One fixed check, such as "plate thickness must be at least 6 mm". |
| **Clause** | The numbered paragraph in a standard that a rule comes from. Every finding cites one. |
| **Finding** | One problem found on one drawing, with severity, clause and evidence. |
| **Severity** | Critical, major or minor. |
| **Verdict** | Any critical finding → Blocked. Otherwise any major → Needs review. Otherwise → Pass. |

## 3. Decisions made so far

| Decision | Choice | Reason |
|---|---|---|
| Backend | FastAPI (Python) | Typed API with built-in test page at `/docs` |
| Database | SQLite through SQLAlchemy, with Alembic migrations | One file, nothing to install; table changes are applied without losing data; can move to PostgreSQL by setting `GRSE_DATABASE_URL` |
| PDF reading | PyMuPDF | Reads text with its position on the page, reads tables, renders pages to images |
| Scanned drawings | Tesseract (OCR program installed on the machine) and OpenCV | Tesseract reads the text in a picture and says how sure it is; OpenCV straightens two scans against each other. Both run locally |
| Frontend (Phase 2) | React + TypeScript + Ant Design, styled like our Gemini examples | Navy sidebar, white cards, walkthrough banner, coloured status pills |
| Explainer | Hosted model on Groq (`openai/gpt-oss-20b` by default) | No local model, so the laptop does not heat up; it only rewords changes and never decides; any OpenAI-style service can be swapped in by settings |
| Rules | Fixed code + a JSON file of rules | Same drawing always gives the same result; no AI opinion in the verdict |
| Data | All representative | Walkthrough does not need GRSE data; every screen and report says so |

## 4. How one check works

```
PDF upload
   │
   ▼
1. EXTRACT      read title block, parts list, notes and cited standards from the PDF
   │
   ▼
2. LOOK UP      find this drawing number in the register (our copy of the ERP extract)
   │
   ▼
3. RUN RULES    each approved rule looks at the extracted data and reports problems
   │
   ▼
4. VERDICT      worst severity decides: Blocked / Needs review / Pass
   │
   ▼
4a. COMPARE     if an earlier revision is available, list what changed (does not affect the verdict)
   │
   ▼
5. STORE        save the check, its findings and the uploaded file; return the report
   │
   ▼
6. DECIDE       a reviewer approves or rejects the release; the decision is final and logged
```

### Step 1: how the title block is read

The PDF is a vector file, so its text is real text with coordinates. We look in the bottom-right area of the sheet for known labels (`DRG.NO.`, `REV.`, `STATUS`, `MATERIAL`, `THK(MM)`) and read whatever text sits in a small box directly under each label. This is called **template-based extraction**: it works because we know the layout. A real GRSE title block has a different layout and will need its own label list and box sizes in `extract.py`.

The parts list is found by asking PyMuPDF for tables on the page and keeping the one whose header contains `PART NO`.

Each value is stored with its position on the sheet (`bbox`), so later the screen can draw a marker exactly where the problem is.

### Step 3: rules are data, checks are code

There are twelve **check types** written in Python (in `rules.py`). A **rule** in `rules.json` picks one check type and gives it parameters, a severity and a clause. To add a rule of an existing kind, you add an entry to the JSON file and write no code.

Only approved rules run. Approval is given in the tool by an admin and covers the rule exactly as written (see the progress log for 13 Oct).

| Rule | Check type | Severity | What it catches |
|---|---|---|---|
| REG-01 | `register_revision` | Critical | Superseded revision, or drawing not in the register |
| REG-02 | `register_status` | Major | Title block status disagrees with the register |
| CHK-01 | `approval_status` | Critical | Drawing not approved for production |
| CHK-02 | `standard_edition` | Major | Drawing cites an old edition of a standard |
| CHK-03 | `allowed_grades` | Critical | Material grade not on the allowed list |
| CHK-04 | `min_thickness` | Critical | Plate thinner than the minimum |
| CHK-05 | `mandatory_notes` | Major | A required note is missing |
| CHK-06 | `mandatory_notes` | Minor | A recommended note is missing |
| BOM-01 | `bom_consistency` | Major | Parts list disagrees with the ERP bill of materials |
| CHK-08 | `required_thickness` | Critical | Plate thinner than the thickness calculated for its zone |
| CHK-09 | `max_spacing` | Major | Stiffener spacing over the zone's limit |
| CHK-10 | `grade_by_zone` | Critical | Thick plate in a zone not of a higher grade |
| CHK-11 | `count_matches_parts` | Major | A count in a note disagrees with the parts list |
| CHK-07 | `mandatory_notes` | (draft) | Not run; shows that unapproved rules are skipped |

Grade and thickness are checked in the title block and on every row of the parts list, so a finding names the exact part.

## 5. The representative data

Everything a walkthrough needs is in the top-level `setup/` folder; `setup/README.md` has a step-by-step walkthrough and `setup/run.ps1` starts the tool.

**Example drawings** (`setup/drawings/`, made by `backend/scripts/make_samples.py`), numbered in walkthrough order with the scenario in the name:

| File | What is wrong with it | Verdict |
|---|---|---|
| `01_GRSE-H-101_revA_superseded-revision.pdf` | Register has moved on to revision B | Blocked |
| `02_GRSE-H-101_revB_clean-pass.pdf` | Nothing | Pass |
| `03_GRSE-H-102_revA_wrong-grade-thin-plate.pdf` | Grade S275, 5 mm plate, 2021 class edition, welding note missing, parts list disagrees with the ERP | Blocked |
| `04_GRSE-H-103_revA_old-standard-edition.pdf` | 2020 customer spec edition, "do not scale" note missing, a quantity disagrees with the ERP | Needs review |
| `05_GRSE-M-210_revA_for-information-only.pdf` | Issued "for information" only | Blocked |
| `06_GRSE-H-101_revA_scanned-copy.pdf` | A scan of drawing 01 | Blocked |
| `07_GRSE-H-101_revB_scanned-copy.pdf` | A scan of drawing 02 | Pass |
| `08_GRSE-H-102_revA_scanned-copy.pdf` | A scan of drawing 03; OCR misreads the grade `S275` as `$275` | Blocked |

**Representative ERP extract** (`setup/register/`): seven CSV files: `drawing_register`, `drawing_revisions`, `engineering_change_notes`, `bill_of_materials`, `work_orders`, `purchase_orders` and `class_approvals`. All seven are now used.

**Walkthrough logins** (`setup/logins.json`): one reviewer and two engineers.

## 6. Where things are

```
backend/
├── app/
│   ├── main.py            starts the API; also serves the built web app if frontend/dist exists
│   ├── config.py          folder locations and limits
│   ├── db.py              database connection, migrations at start-up, backups
│   ├── models.py          database tables
│   ├── schemas.py         the shape of what the API accepts and returns
│   ├── auth.py            password hashing, sessions, "who is signed in", role checks, audit helper
│   ├── api/
│   │   ├── auth.py        sign in, sign out, who am I, reviewer registration, user management
│   │   ├── checks.py      upload a drawing, list and read checks, sheet images, reviewer decision, comments
│   │   ├── erp.py         register, drawing detail, release gate, class approvals
│   │   └── reference.py   rule list, audit log
│   └── core/              the checking logic; knows nothing about the web or the database
│       ├── extract.py     PDF → plain data, for vector PDFs and for scans
│       ├── ocr.py         runs Tesseract on a picture of the sheet
│       ├── rules.py       check types, rule runner, verdict
│       ├── diff.py        what changed between two revisions: change list and overlay image
│       ├── bom.py         parts list against the ERP bill of materials
│       ├── impact.py      work orders and purchase orders affected by a revision change
│       ├── gate.py        may this work order be released? Clear / Warn / Blocked
│       └── explain.py     asks a hosted model to reword the change list (optional)
├── data/rules/rules.json  REF rules
├── .env.example           the optional settings, with no secrets in it; copy to .env to use
├── migrations/            one file per change to the database tables, applied in order
├── scripts/
│   ├── make_samples.py    draws the example PDFs
│   ├── load_extract.py    copies the CSV files into the database
│   ├── seed_users.py      creates the default users
│   └── new_migration.py   drafts a migration after the tables in models.py change
├── tests/                 automated checks of the engine and the API
└── var/                   created at run time: the database, its backups and uploaded files

setup/                      everything for a walkthrough (see setup/README.md)
├── run.ps1           starts the tool
├── logins.json       default users and their passwords
├── register/              REF ERP CSV files
└── drawings/              REF drawings to upload

frontend/
├── vite.config.ts         dev server; forwards /api to the backend
└── src/
    ├── main.tsx           starts the app: theme, data cache, router
    ├── App.tsx            decides between the sign-in page and the app; lists the routes
    ├── theme.ts           colours (navy, status colours) in one place
    ├── api.ts             data types and every call to the backend
    ├── index.css          the few styles Ant Design does not cover (banner, sheet markers, print)
    ├── components/
    │   ├── AppLayout.tsx      banner, navy sidebar, header with user and sign out
    │   ├── Tags.tsx           verdict, severity, status and decision tags
    │   ├── ChecksTable.tsx    the checks table, used on Dashboard and Checks
    │   ├── SheetViewer.tsx    drawing image with numbered markers
    │   ├── RevisionChanges.tsx  the Revision changes tab: change note, overlay, side by side, list
    │   ├── ErpChecks.tsx      the BOM tab and the Impact tab
    │   ├── Explanation.tsx    the AI-written summary card
    │   ├── DrawingForm.tsx    the admin's add / update drawing form
    │   ├── GateTable.tsx      work orders with their gate status, used on two pages
    │   ├── DecisionPanel.tsx  the reviewer's approve / reject panel
    │   └── Comments.tsx       comments on a check
    └── pages/                 one file per screen
```

Why `core/` is separate: the checking logic takes plain data in and gives plain data out. That makes it easy to test without starting a server, and it could be reused from a command line or a different web framework.

## 7. The API so far

Every route except sign-in needs a signed-in user.

| Route | Who | What it does |
|---|---|---|
| `POST /api/auth/login` | Anyone | Sign in; sets the session cookie |
| `POST /api/auth/register` | Anyone | Ask for a reviewer account; it stays pending until an admin approves it |
| `GET /api/users` | Admin | All accounts and their status |
| `POST /api/users/{username}/status` | Admin | Approve, disable or re-enable an account |
| `POST /api/auth/logout` | Signed in | Ends the session |
| `GET /api/auth/me` | Signed in | Who is signed in |
| `POST /api/checks/read` | Engineer, admin | Show what the tool reads from a PDF, without storing or checking anything |
| `POST /api/checks` | Engineer, admin | Upload a PDF (and optionally its previous revision); runs the check, stores it, returns the report |
| `GET /api/checks` | Signed in | List of past checks, newest first |
| `GET /api/checks/{id}` | Signed in | One full report |
| `GET /api/checks/{id}/sheet.png` | Signed in | The drawing's first sheet as an image |
| `GET /api/checks/{id}/previous.png` | Signed in | The previous revision's sheet |
| `GET /api/checks/{id}/diff.png` | Signed in | The two revisions overlaid, differences in red and green |
| `POST /api/checks/{id}/decision` | Reviewer, admin | Record the final approve / reject |
| `POST /api/checks/{id}/comments` | Signed in | Add a comment to a check |
| `POST /api/checks/{id}/explanation` | Signed in | Ask the hosted model to summarise the revision changes; made once and kept |
| `GET /api/settings` | Signed in | Whether the explainer is switched on, and which model it uses |
| `GET /api/register` | Signed in | The drawing register, with each drawing's class approval state |
| `POST /api/register` | Admin | Add a drawing to the register |
| `PUT /api/register/{drawing_no}` | Admin | Update a drawing's title, current revision or status |
| `GET /api/register/{drawing_no}` | Signed in | One drawing: revisions, change notes, BOM, work orders, class approvals |
| `GET /api/gate` | Signed in | Every work order with its gate status and reasons |
| `GET /api/gate/{order_no}` | Signed in | One work order's gate status: the question the ERP would ask |
| `GET /api/class-approvals` | Signed in | Drawings submitted for approval, longest wait first |
| `GET /api/rules` | Signed in | The rule list, including draft rules |
| `GET /api/audit` | Reviewer, admin | The audit log |

Uploads are refused if they are over 25 MB, are not PDFs, or have no readable text. A scanned drawing is refused unless the title block values were confirmed by the person uploading it.

## 8. Sign-in, decisions and the audit log

**Three roles.**

| Role | Can do | How the account is created |
|---|---|---|
| Engineer | Upload drawings for checking, view everything, comment | Registers on the sign-in page, then waits for an admin to approve (walkthrough ones come from the logins file) |
| Reviewer | Upload drawings for checking, view everything, comment, read the audit log, and approve or reject a check that someone else uploaded. Cannot change rules or the register | Registers on the sign-in page, then waits for an admin to approve |
| Admin | Everything, plus approve, disable and re-enable accounts, and add or update drawings in the register | From the logins file only; nobody can register as admin |

Why registration needs approval: a reviewer decides whether steel gets cut. If anyone on the network could create a reviewer account and use it straight away, the reviewer's decision would mean nothing. A disabled account is signed out at once.

**How sign-in works.** The password is never stored; only a scrambled version (a salted *scrypt hash*) is. On sign-in the server creates a long random token, stores a hash of it with an 8-hour expiry, and puts the token in a cookie the page's JavaScript cannot read (`HttpOnly`). Every later request carries that cookie, and the server looks up who it belongs to.

**The reviewer's decision.** The tool only proposes a verdict. The reviewer chooses *Approve for release* or *Reject*:

| Tool's verdict | Approve | Reject |
|---|---|---|
| Pass | No reason needed | Reason required; marked as an override |
| Needs review | Reason required | Reason required |
| Blocked | Reason required; marked as an override | No reason needed |

Three safeguards, all enforced on the server and not just in the screen:

- A check can be decided **once**. The decision cannot be edited afterwards.
- A reviewer **cannot decide a check they submitted** themselves (two different people must be involved). An admin can, because the admin has full access, and the audit log marks it.
- Going against the verdict needs a **written reason** and is flagged as an override.

**Comments.** Anyone signed in can add comments to a check; they are kept with the check and shown beside the decision.

**Audit log.** Sign-ins, failed sign-ins, sign-outs, registrations, approvals, comments, every check and every decision are written to a table that the tool only ever adds to.

## 9. The web app

Built with React and TypeScript. **Ant Design** supplies the tables, forms, tags and layout; `theme.ts` sets its colours and shapes: a white sidebar, a blue accent, and rounded white cards on soft shadows.

| Screen | What it shows |
|---|---|
| Sign in | Username and password, and a tab to register as a reviewer |
| Dashboard | A greeting banner, the split of verdicts so far, checks awaiting decision, blocked work orders, drawings awaiting class approval, recent checks, and the checks waiting for you |
| Drawing Register | The register with search and status filter, plus each drawing's class approval and latest check. An admin sees an *Add drawing* button |
| Drawing detail | One drawing: revision history with change notes, bill of materials, work orders, class approvals, checks. An admin sees an *Update drawing* button |
| Release Gate | Every work order: Clear, Warn or Blocked, with the reasons |
| Class Approvals | What is awaiting class or customer approval, and for how long |
| New Check | Drag-and-drop a PDF, see what was read from it (and confirm or correct it for a scan), run the check |
| Check report | Verdict banner, title block against register, findings with clauses, the sheet with numbered markers, revision changes, BOM comparison, impact, the reviewer's decision, print |
| Checks | All checks, filterable by verdict and decision |
| Rule Library | Read-only rule list with clause, severity and state |
| Audit Log | Reviewer and admin; searchable |
| Users | Admin only; approve, disable and re-enable accounts |

Two ideas that are worth understanding:

- **Server state lives in a cache.** A library called TanStack Query fetches data, remembers it, and refetches after a change (for example, after a decision the checks list is refreshed). Pages do not manage loading flags by hand.
- **The markers on the sheet** are drawn by the browser on top of an image. The backend stores each finding's position in PDF points; the page converts that to a percentage of the sheet, so the boxes stay in place at any zoom.

In development two servers run: the backend on port 8000 and the web app on port 5173, which forwards `/api` calls to the backend. For a real installation, `npm run build` produces `frontend/dist`, and the backend serves it, so only one process runs.

## 10. Comparing two revisions

"It shows exactly what changed" is answered in two ways, because each catches what the other misses.

**1. The change list (from the text).** Both PDFs are read into the same plain data, then compared in three parts:

| Part | How it is compared | Example |
|---|---|---|
| Title block | Field by field | Plate thickness 10 → 12 |
| Parts list | Rows matched by part number, then column by column | HP-101-02 quantity 6 → 7; BK-101-04 added |
| Other text on the sheet | Lines matched by their wording | "PLATE 10 THK AH36" → "PLATE 12 THK AH36" |

Matching other text *by wording, not by position* matters: when the parts list grows by a row, every note below it moves down. The notes did not change, so they are not reported. If a line's wording changed but it still starts at the same spot, it is shown as one "changed" entry instead of a removal plus an addition.

**2. The overlay (from the picture).** Both sheets are turned into images of the same size. Each pixel is then coloured: grey if both sheets have ink there, red if only the old one does, green if only the new one does. This catches redrawn lines, which have no text. Its weakness is the opposite of the list's: something that merely moved shows up as red and green.

Two details make the overlay trustworthy:

- **Tolerance of one pixel.** Ink counts as removed only if the new sheet has no ink within a pixel of it. Without this, tiny rendering differences show up as false changes.
- **Identical sheets give no colour at all.** This is checked by an automated test.

**Which revision is "the previous one"?** If you upload one with the drawing, that one. Otherwise the tool uses the latest earlier revision of the same drawing that has already been checked. If there is none, the tab says so.

**The ERP's side of the story.** The representative extract has engineering change notes (what changed, when, why). The matching note is shown above the comparison, so a reviewer can see whether the drawing really changed the way the ERP says it did.

The comparison is information for the reviewer. It never changes the verdict.

## 11. Connecting the drawing to the rest of the ERP

A drawing is not checked in isolation. Three questions tie it to production and purchasing.

**1. Does the drawing agree with what purchasing will order? (BOM consistency)**
The parts list on the drawing is compared with the ERP's bill of materials for the same revision, part number by part number: material, thickness, quantity. A part on one side only is also reported. Each difference is a *major* finding under rule BOM-01, so the verdict becomes at least "Needs review". The BOM tab shows every part with both values next to each other.

**2. Who is affected when a revision changes? (Change impact)**
From the list of parts that changed between the two revisions, the tool finds:

- work orders still released against the old revision, and
- open purchase orders for the parts that changed (delivered orders are ignored).

This is the "this revision change affects 1 work order and 2 open purchase orders" line. It is a snapshot taken when the check ran.

**3. May this work order be released? (Release gate)**
For each work order the gate combines four facts and reports the worst:

| Fact | Blocked when | Warn when |
|---|---|---|
| Register | The revision is superseded, the drawing is unknown, or its status is not approved | |
| Check | The latest check of that revision is Blocked and undecided | No check yet, or it awaits a decision |
| Reviewer | The reviewer rejected it | |
| Class approval | | Not submitted, awaiting, or returned with comments |

A work order is **Clear** only when the revision is current and approved, a check has been approved by a reviewer, and class approval is in place. A reviewer's override counts: if they approved a blocked check with a reason, the gate accepts it.

Unlike the snapshots above, the gate is worked out fresh every time it is asked, because a decision made a minute ago must count. It is exposed as `GET /api/gate/{order_no}`, which is how an ERP would ask the question. The tool never writes to the ERP; the ERP (or a person) acts on the answer.

**Class approval tracking** is a list of what has been submitted to class or the customer and how long it has waited; anything over 30 days is highlighted.

## 12. Keeping the data safe

**Where the data lives.** Everything the tool records (users, checks, findings, decisions, comments, audit log) is in one database file, `backend/var/app.db`, and the uploaded PDFs are in `backend/var/uploads/`. Both are on disk, so they survive a page refresh, closing the browser, and restarting the server or the computer.

**The problem that was fixed.** In the early phases, whenever a table gained a column, the only way to update the database was to delete it and start again, which threw away every check and decision. That is acceptable while sketching, and unacceptable for a real tool.

**Migrations.** A *migration* is a small script that changes the database's tables while keeping the rows in them, for example "add a `status` column to `users`, and fill it with `active` for existing users". They live in `backend/migrations/versions/`, numbered in order (`0001`, `0002`, …). The database remembers which number it has reached. Every time the server starts it:

1. looks at which migration the database is on,
2. if newer ones exist, **copies the database file to `backend/var/backups/` first**,
3. runs the newer migrations in order.

If there is nothing new, it does nothing. So the rule for the project is now: **never delete the database; write a migration.** After changing `models.py`, run `python -m scripts.new_migration 0003 "what changed"`, read the file it writes, and commit it.

An automated test compares the tables the migrations build with the tables the code expects. If someone changes a model and forgets the migration, that test fails.

**What refreshing the page keeps.** The page itself holds almost nothing; it asks the server for data each time. Three things used to reset on refresh and now do not: you stay signed in (cookie), the report stays on the tab you had open (the tab is part of the address, e.g. `?tab=bom`), and a half-typed decision reason is kept for that browser tab.

**`run.ps1 -Reset`** no longer deletes anything. It moves the old data to `backend/var-archive/<date-time>/` and starts with an empty tool.

**Limits to know.** SQLite is one file on one machine: back up `backend/var/` like any important folder. For several servers or many simultaneous users, point `GRSE_DATABASE_URL` at PostgreSQL; the migrations work there too.

## 13. Scanned drawings

**Two kinds of PDF.** A *vector* PDF comes straight from the CAD system: the letters are stored as text, so reading them is exact. A *scanned* PDF is a photograph of paper: there is no text in the file, only pixels. The tool tells them apart by asking the PDF for its text; if there is none, it is a scan.

**OCR.** Optical character recognition turns a picture of text into text. We use **Tesseract**, a program installed on the machine, so nothing leaves the building. For each word it returns the text, where it is on the sheet, and a *confidence* from 0 to 100.

How a scan is read (`core/ocr.py`, `core/extract.py`):

1. The page is turned into a picture at 200 dots per inch.
2. Tesseract reads it twice with two settings. The first finds labels scattered over the sheet; the second finds the single digits in table cells that the first one misses. The results are merged.
3. Words it was less than 50% sure of are dropped. They are nearly always dashed lines mistaken for letters.
4. The same template as before is applied to the words: find the label, read what is under it. The parts list is rebuilt from positions: the heading row gives the columns, and whatever lies beneath gives the rows.
5. A parts-list cell that is still empty is read again on its own, enlarged, with Tesseract told to expect a single line (and only digits, for thickness and quantity). A whole-page read often skips a lone digit in a table; a close look at the one cell finds it.

Reading a scan takes roughly 5 to 10 seconds.

**Why a person must confirm.** OCR makes mistakes that matter. On our example it reads the steel grade `S275` as `$275`. So for a scan the New Check screen shows the title-block values in editable boxes, marks any below 90% confidence, and shows the scan beside them. The check runs only after the person presses *Confirm these values and run the check*, and the server refuses a scan that has not been confirmed. If a value was corrected, the report shows both: the corrected value and what OCR read. The audit log lists each correction.

**What is not confirmed.** The parts list and the notes are used as OCR read them. The report says so in a banner. A misread there can produce a false finding (for example a thickness that could not be read), which is why the banner tells the reviewer to compare such findings with the sheet.

**Rules on a scan.** The rules themselves do not change, but two comparisons are made more forgiving for scans, because OCR often gets punctuation and the odd letter wrong: standard names are compared by their letters and digits only, and a mandatory note counts as present if a line on the sheet is nearly identical to it. A number is never forgiven: `10` and `12` are always different.

**Comparing two scans.** Two scans of the same sheet never line up: each is slightly shifted and turned. Before the red/green overlay, the old picture is moved and rotated until it sits on the new one (OpenCV searches for the best fit on a small copy of the pictures), and the tolerance for "the same line" is widened from one pixel to three. A test scans one drawing twice, crooked in opposite directions, and checks that almost nothing is marked as changed.

## 14. The explainer

**What it is.** A button on the *Revision changes* tab: "Explain these changes in plain words". It sends the change list to a language model run by an outside company (Groq) and shows the short summary it writes.

**What it is not.** It is not part of the check. The verdict, the findings, the gate and the reviewer's decision never look at it. This is the brief's rule: "rule checks must be fixed, expert-approved and clause-cited, not AI opinions". A language model can be wrong in fluent, convincing sentences, so it is kept to a job where being wrong is visible and harmless: rewording a list that is printed right below it.

How that is enforced, not just promised:

| Risk | What the tool does |
|---|---|
| The drawing leaves the building | Only the change list is sent (e.g. "PL-101-01 thickness changed, was '10', now '12'"). Not the PDF, not the drawing number. A test checks the exact text that is sent. |
| It runs without anyone knowing | Nothing is sent until someone presses the button. The card says where the text goes before they press. |
| The model invents a number | Every number in the summary is looked up in the change list. Any that is not there is called out in a warning under the summary. |
| Text on a drawing tries to instruct the model ("ignore your instructions...") | The model is told the list is data, not instructions, and its answer is only ever displayed as text. It cannot do anything in the tool. |
| The model gives an opinion on compliance | It is instructed not to say whether the drawing is acceptable or to recommend a decision, and the card is labelled "AI-written, not part of the compliance decision". |
| The API key leaks | The key lives only in an environment variable or `backend/.env`, which is not shared. Error messages show the status code only. |
| The service is down, or there is no key | The button reports the error, or the card does not appear at all. Everything else works. |

**Made once.** The summary is stored with the check, with the model's name, who asked and when, and is not regenerated. The audit log records the request.

**Changing the model.** Three settings, in `backend/.env` (see `.env.example`): the service address, the model name and the key. Any service that speaks the "OpenAI chat" format works, including one hosted inside GRSE's own network, which is how the on-premises claim would be kept in a real installation.

## 15. Progress log

### Phase 1 — checking engine and API (done, 12 Oct 2026)

Built: database tables, representative extract and its loader, five example drawings, title-block and parts-list reading, seven check types with nine representative rules, verdict logic, five API routes, and 15 automated tests, all passing. One example was also uploaded to the running server and returned the expected verdict.

Things worth knowing:

- **Two bugs the tests caught.** SQLite forgets the timezone on a saved time, so the same check showed two different timestamps; the API now always reports UTC. A field named `register` clashed with a name the library already uses, so it is called `register_row`.
- **Revisions are compared as text** (A < B < C). That is correct for single letters only. Schemes like P01 or A1 need a proper ordering.
- **Only sheet 1 of a PDF is read.**
- **Not built yet:** login, reviewer decisions and the audit log (Phase 2); these tables do not exist yet.

### Phase 2 — web app, sign-in, decisions, audit log (done, 12 Oct 2026)

Built: users and sessions, role checks on every route, the reviewer decision with its three safeguards, the audit log, the sheet image route, and the eight screens listed above. The backend now has 21 automated tests, all passing. The full flow was also run in the browser: sign in as engineer, upload a drawing through the page, read the report and the sheet markers, sign out, sign in as reviewer, reject the blocked drawing.

Things worth knowing:

- **A bug found by clicking through.** Sign-out ended the session on the server but the page stayed on screen, because the data cache was wiped in a way the page did not notice. Fixed, and the page now returns to sign-in.
- **Findings are sorted worst first**, so the numbering on the sheet starts with the critical ones.
- **The database had to be recreated** when the tables changed (delete `backend/var/`, then rerun the load and seed scripts). A real installation needs proper migrations so data survives an upgrade.
- **The frontend has no automated tests yet**; it was checked by type-checking, a production build and the manual run above.
- **No lockout after repeated wrong passwords.** Failed attempts are logged, but nothing blocks them yet.
- **The New Check screen runs the check in one step.** The mockup's editable "confirm what was read" form belongs with scanned drawings (Phase 5), where reading can be uncertain.
- **Not built yet:** Revision changes (Phase 3); Release Gate, Class Approvals, BOM and Impact tabs (Phase 4). They are not in the menu until they exist.

### Phase 3 — revision changes (done, 12 Oct 2026)

Built: the change list, the red/green overlay, automatic pick-up of the previous revision, an optional "previous revision" upload on New Check, and the Revision changes tab (ERP change note, overlay or side-by-side view with numbered markers, list of changes). 26 backend tests pass. Checked in the browser on GRSE-H-101 rev A against rev B: 8 changes listed, overlay and both side-by-side sheets drawn.

Things worth knowing:

- **A bug the tests caught.** Comparing a sheet with itself showed a few stray coloured pixels, because the two images were produced by slightly different scaling. Same-size sheets are now rendered identically, and a one-pixel tolerance was added.
- **A mistake of mine.** A script I used to edit a test file failed halfway and emptied the file; the tests then "passed" only because that file had none. I noticed from the test count and rewrote the file. Worth remembering: a passing run means little unless the number of tests is what you expect.
- **Number badges alternate sides** on the sheet, so markers on neighbouring table rows do not hide each other.
- **The overlay is pixel-based.** It shows where something changed, not what the change means.
- **Scanned drawings** will need the two images aligned first; that is Phase 5.
- **The database was recreated again** for the new columns.

### Walkthrough folder and Phase 4 — the ERP story (done, 12 Oct 2026)

**Walkthrough folder.** The representative register files, the example drawings and the default logins moved into `setup/`, with clearer names, a walkthrough (`setup/README.md`) and a start script (`setup/run.ps1`). The code reads them from there, so there is one copy of each file. The script was run end to end on a fresh database.

**Phase 4.** Built: BOM consistency (rule BOM-01 and the BOM tab), change impact (the Impact tab), the release gate (its own page, per-drawing view and an API for the ERP), class approval tracking, and a drawing detail page. 43 backend tests pass. Checked in the browser through the walkthrough script: all five drawings uploaded, the gate showed the expected status and reasons for each work order, and the BOM, Impact, Class Approvals and drawing detail pages showed the expected rows.

Things worth knowing:

- **Two verdicts changed.** Drawings `03` and `04` now also get BOM findings, because their parts lists really do disagree with the representative ERP. Their verdicts stayed Blocked and Needs review.
- **Rules now receive the ERP's data as one bundle** (register row plus bill of materials), so future rules can use more ERP data without changing every check.
- **The gate reads every check** to find the latest per drawing revision. Fine for a walkthrough; with thousands of checks it needs a smarter query.
- **The gate's list of releasable statuses is written twice** (in the gate and in rule CHK-01's parameters). They must be kept the same.
- **Impact is a snapshot**; the gate is live. The Impact tab links to the gate for the current state.
- **The database was recreated again.** `run.ps1 -Reset` now does this in one step.

### Durable database, admin role, registration, comments (done, 12 Oct 2026)

Built: migrations with automatic backup, an admin role with a Users page, reviewer self-registration with admin approval, comments on checks, and refresh-safe report state. 47 backend tests pass. The live database was upgraded in place by the first real migration: its 5 checks and audit log survived, and a backup was written first. Checked in the browser: registering a reviewer, signing in as admin, approving the account, adding a comment, then reloading the page and finding the tab, the comment and a half-typed reason still there.

Things worth knowing:

- **Reviewers can no longer upload drawings.** That is now for engineers and admins.
- **The admin's username and password are in `setup/logins.json` in plain text**, like the other walkthrough logins. That is fine for a walkthrough and must be changed before real use.
- **A test account `walkthrough.reviewer` exists and is disabled.** It was created while testing registration.
- **Other databases are not backed up automatically**; only the SQLite file is.

### Phase 5 — scanned drawings (done, 12 Oct 2026)

The first OCR library tried (RapidOCR) crashed on this laptop, so Tesseract was installed by hand and used instead.

Built: reading scanned PDFs by OCR, the confirm-or-correct step before a scan is checked (enforced by the server), confidence markers, a record of what was corrected, scan-tolerant rule matching, straightening of scans before the overlay, and three scanned example drawings. 53 backend tests pass; the scan tests are skipped on a machine without Tesseract. Checked in the browser: a scanned drawing was uploaded, its values appeared for confirmation, the check passed, and it was compared with the earlier vector revision (8 changes, overlay drawn).

Things worth knowing:

- **The scans read as well as the originals** on the examples: same title block, same parts list, same verdicts. Real scans are worse than our simulated ones (stamps, handwriting, folds, coffee), so expect more corrections.
- **A scan takes about 10 seconds to read.** The result is remembered briefly, so reading it for the confirmation screen and again for the check costs one read, not two.
- **Only the title block can be corrected.** A misread in the parts list or notes cannot be fixed in the tool yet. On example 08 OCR misses one thickness in the parts list, which produces a finding that is not really on the drawing.
- **The previous revision, if it is a scan, is not confirmed.** It is used as read.
- **Only scanned PDFs are accepted**, not image files such as TIFF or JPEG.
- **Tesseract must be installed on the server.** Without it, a scanned drawing is refused with a message saying so; vector drawings still work.

### Phase 6 — the explainer (done, 12 Oct 2026)

Built: the optional AI-written summary of revision changes, its safeguards, the settings for choosing a model, and `.env` support. 54 backend tests pass; the explainer test uses a stand-in for the model, so the tests never call the real service. It was also run for real against Groq from the browser on the GRSE-H-101 rev A to B change: the summary was accurate and no invented numbers were flagged.

Things worth knowing:

- **The model had to be changed.** The Groq key on this machine cannot use the Llama model first chosen (the service answered "not found"). The default is now `openai/gpt-oss-20b`, which the key can use. Which models a key may use is decided by Groq and can change.
- **A real request takes about two seconds.**
- **One real summary is stored on check 2** from testing.
- **Free-tier limits apply.** If Groq refuses a request for being over the limit, the button shows the error and can be pressed again later.
- **The number check is a safety net, not proof.** It catches invented numbers; it cannot catch a correct number attached to the wrong part. The change list under the summary remains the source of truth.

### Example video (done, 12 Oct 2026)

`setup/walkthrough.webm` (and `.mp4`) is a 4-minute captioned recording of the whole walkthrough: engineer, scanned drawing, a reviewer registering, reviewer decisions, admin. It is made by `setup/record_walkthrough.py`, which drives a real browser (Edge) through the tool with a library called Playwright and records the screen. Because it is a script, the video can be re-made after any change instead of being re-filmed by hand.

Things worth knowing:

- **The recording runs against its own temporary database** on a different port, so it never touches real data.
- **Recording found a real bug.** The sign-in form and the register form gave their Username and Password boxes the same internal id, so a label could point at the wrong box (a problem for screen readers too). Each form now has its own ids.
- **The captions are drawn by the page itself** during recording, so no video editing is needed.
- **The video shows the representative data and, briefly, the AI summary**, which is a live request to Groq when a key is set.

### Ship-style drawings and register editing (done, 12 Oct 2026)

**Drawings that look like ship structure.** The representative sheets were redrawn as isometric views, in the style of the mockup: a bow block and a midship block (bottom plating, longitudinal stiffeners, web frames with lightening holes, deck edge, an access opening, brackets), and a transverse bulkhead with vertical stiffeners and a door opening. Each has frame numbers and numbered item balloons pointing at the parts. The title block, parts list, notes and every expected verdict are unchanged, so all earlier tests still pass. They are still invented drawings, drawn by `backend/scripts/make_samples.py`.

What the busier drawings taught us:

- **OCR got worse at the parts list.** With more lines on the sheet, Tesseract stopped reading the single digits in the quantity column. This is why step 5 above (re-reading an empty cell on its own) was added. It also fixed the missed thickness on example 08 noted in Phase 5.
- **Item balloons are not reported as text changes.** A balloon repeats an item number from the parts list, so a bare one- or two-digit number on the sheet is ignored by the comparison; the parts list already reports an added or removed item.
- **A lone letter read from a scan is dropped**, and loose text needs 60% confidence, because holes and corners were being read as letters.

**An admin can add and update drawings in the register.** On the Drawing Register page an admin has *Add drawing*; on a drawing's page, *Update drawing*. The form can be filled in from a drawing PDF. Giving a drawing a new current revision marks the previous one as superseded, and work orders released against it are blocked by the gate at once.

Two things to understand about this:

- **It edits the tool's copy, not the ERP.** The brief's rule is that the tool never writes to the ERP. An edited or added drawing is tagged "Edited in the tool" so nobody mistakes it for ERP data.
- **The next ERP extract does not undo it.** Loading the extract used to replace the whole register. Now it replaces only the rows that still came from the ERP and leaves the admin's rows alone. In a real installation the proper fix for a wrong register entry is to correct the ERP; this option is for when the tool has to be right today.

Every addition and update is in the audit log with the before and after values. 55 backend tests pass. The video was re-recorded with the new drawings and the admin steps.

### Rules by zone and formula, and rule approval (done, 13 Oct 2026)

This closed three of the five gaps listed when asked "is the class and compliance checker implemented?".

**Rules that depend on location and on a calculation.** The title block now has three more boxes: hull number, structural zone and stiffener spacing. A new ERP file, `ship_particulars.csv`, gives each hull's rule length. Four new check types use them:

| Rule | What it does |
|---|---|
| CHK-08 | Works out the required plate thickness from a formula for the drawing's zone, e.g. deck: `4.5 + 0.04 * L`. The finding shows the working. |
| CHK-09 | Stiffener spacing against a limit per zone. |
| CHK-10 | Thick plate in a zone must be a higher steel grade. |
| CHK-11 | A count stated in a note ("7 NOS. HP STIFFENERS") must agree with the parts list. |

The formula is text in the rule file. It is never run as program code: `core/formula.py` reads it and allows only numbers, named quantities (`L`, `s`), arithmetic, brackets, and `sqrt`, `min`, `max`. That matters because a file that could run code would be a way to attack the server.

**Rule approval in the tool.** A rule is still *defined* in the rule file, but it is *approved* on the Rule Library screen by an admin. The approval stores a fingerprint (hash) of the rule's content, so:

- a rule that was never approved is a **draft** and does not run;
- an approved rule that is then edited becomes **changed** and stops running until approved again;
- an admin can **withdraw** a rule; checks already made keep their findings.

Approvals and withdrawals are in the audit log. The walkthrough's rules get their first approval from a setup script, recorded as "initial-setup", with a note that no naval architect reviewed them.

Things worth knowing:

- **Drawing 01 now has a second reason to be blocked** (the calculated thickness), which matches the story in the ERP change note: revision B went from 10 mm to 12 mm after a class comment on strength.
- **Drawing 04 gets a spacing finding**; its verdict is still Needs review.
- **All formulas, limits and clause numbers are invented.** The mechanism is real; the content is not.
- **One zone per drawing**, taken from the title block.
- **Still not done, and not possible to do honestly here:** real class rule content (it must come from a rule book and a naval architect), and understanding geometry such as weld symbols and dimensions.
- 60 backend tests pass. The video, the walkthrough guide and both PDFs were updated.

### Only the admin approves or rejects (done, 13 Oct 2026)

Approving or rejecting a release is now the admin's job alone. Engineers and reviewers upload drawings, run checks, read reports and comment; a reviewer can also read the audit log. The decision rules themselves did not change (decided once, a reason when going against the verdict, overrides marked).

What this means in practice:

- The decision panel on a report shows the buttons only to the admin; everyone else sees "Awaiting the admin's decision".
- The release gate's wording now says a check "awaits the admin's decision".
- The admin can decide a check they uploaded themselves; the audit log marks it. With one admin there is no second person to ask, so the earlier "two different people" safeguard no longer applies.
- Older sections of this file and the walkthrough video still say "the reviewer decides". Read that as the admin.

### Reviewers can upload (done, 13 Oct 2026)

A reviewer can now upload a drawing and run the check, the same as an engineer. Two things did not change. A reviewer still **cannot decide a check they uploaded themselves**: another reviewer or the admin must. And a reviewer still **cannot approve, withdraw or edit rules, or edit the register**: checks always run on the rules the admin approved.

### Engineers can register too (done, 13 Oct 2026)

The *Register* tab on the sign-in page now asks for an account type: Engineer or Reviewer. Either kind stays pending until the admin approves it under *Users*. An admin account still cannot be registered; the server refuses any other role. 60 backend tests pass.

### New user interface (done, 13 Oct 2026)

The whole app got a new look, chosen after browsing dashboard and table designs on collectui.com. What each screen *does* is unchanged; how it is laid out and styled is new.

- **Sidebar:** white instead of navy, with the pages in three groups (Workspace, Release control, Administration). The selected page is a soft blue pill. Your name, role and the sign-out button sit in a card at the bottom. A button in the top bar folds the sidebar down to icons.
- **Top bar:** the page title with a one-line description under it, and a *New check* button that is always one click away. (The SETUP notice that used to sit here was removed later the same day; see below.)
- **Dashboard:** a greeting banner with the two numbers that matter most, a *Verdicts so far* bar showing how many checks passed, need review or are blocked, four number tiles with coloured icons, then the recent checks and the checks waiting for you.
- **Sign-in:** split in two. The left half says what the tool is for; the right half holds the sign-in and register forms. On a narrow screen only the form shows.
- **Everywhere:** a blue accent for buttons and links, rounded corners, cards on a soft shadow, pill-shaped status tags, and small grey capitals for table headings.

**Why most pages needed no edits:** Ant Design reads its colours, corner radius and spacing from one object, called *design tokens*, in `frontend/src/theme.ts`. Changing a token restyles every button, card, table and tag at once. The frame around every page (sidebar and top bar) is one component, `AppLayout.tsx`, so rebuilding it changed all twelve screens. Only the dashboard and the sign-in page were laid out again by hand. Things tokens cannot express (shadows, the banner gradient, the split sign-in page) are plain CSS in `index.css`.

Changed files: `theme.ts`, `index.css`, `AppLayout.tsx`, `Dashboard.tsx`, `Login.tsx`, `ChecksTable.tsx`, `CheckReport.tsx`. The walkthrough video and the screenshots in `docs/` still show the old look.

### Navik, the helper (done, 13 Oct 2026)

A helper called **Navik** (a word for sailor) now sits at the bottom right of every page once you are signed in. He is a small cartoon shipyard engineer in a yellow hard hat and GRSE-blue overalls, and his panel uses the blue of the GRSE website.

- **It starts closed**, as a round button with his face that bobs gently and sends out a ring so it is noticed. Clicking it opens the panel; the minus button shrinks it back, and reopening shows the conversation still there. (It first opened by itself on every page load; that was changed the same day because it covered the page.)
- **It closes with the site.** The conversation is kept only in the browser tab's memory. Close the tab, reload or sign out and it is gone; nothing is saved on the server.
- **It only talks about this site.** Ask how to run a check, what a verdict means, who can approve or what a record shows, and it answers. Ask about anything else (general knowledge, code, jokes, even GRSE itself) and it says it can only help with the Drawing Compliance Checker.
- **It knows your role and page.** An engineer asking how to approve a check is told that only the admin can. Each page offers two or three starter questions.

- **It answers from the live records.** "How many checks are waiting?", "Which work orders are blocked and why?", "What is the status of GRSE-H-102?" get the actual answer, not directions to a page.
- **It opens a page only when asked.** "Take me to the release gate" or "open check 9" makes the site go there. A question that is not a request to go somewhere never moves you.

**How it works.** Navik uses the same hosted model as the explainer (Groq, same key). With every question the server sends the model four things: a fixed set of rules, a written guide to the screens and workflow, a text summary of what the screens currently show, and your question with your role and page. The guide lives in `backend/app/core/helper.py` as plain text; **when a screen or a rule of the workflow changes, that guide must be edited too**, or Navik will describe the old behaviour.

**What Navik is shown, and what leaves the building.** The summary (built by `site_data` in `backend/app/api/reference.py`) holds totals, the newest 25 checks with their verdict, decision and finding names, the drawing register, the release gate with its reasons, class approvals and the rule list. These are things every signed-in role can already see on the pages. It is sent to the model service with each question. Navik is never sent a drawing file, a password, the user list or the audit log. This is a change from the explainer, which sends only a change list: with real data, decide whether the register may go to a hosted service. Setting `GRSE_HELPER_DATA=0` on the server switches the summary off, and Navik goes back to explaining how the tool works without seeing any record.

**How "take me there" works.** The model is told to end its reply with a line like `GO: /gate` only when asked to open something. The server removes that line from the text, checks the path is a real page that your role may open (an engineer asking for Users gets no navigation), and passes it to the page, which then moves. The model cannot send you to any address outside the site.

**What keeps it on topic.** The rules tell the model to refuse anything outside the tool, even if the person insists or claims to be an admin. This is an instruction to a language model, not a hard lock: it held for every off-topic question tried, but a determined person might still talk it round. The limits that *are* hard: only signed-in users can reach it, questions are capped at 500 characters, the page name is restricted to letters so it cannot carry hidden instructions, and navigation is checked by the server. Because Navik reads the summary through a language model, treat a number it gives as a quick answer and the page as the record.

**If it does not answer.** No key on the server: Navik says it is switched off. The free model service allows only about two to four questions a minute (fewer now that each question carries the summary); past that Navik says the service is busy and to try again in a minute.

New files: `backend/app/core/helper.py`, `frontend/src/components/Helper.tsx`. The model call was split out of the explainer into one shared function, `chat`, in `explain.py`. One new test; 61 backend tests pass.

### Light and dark mode (done, 13 Oct 2026)

A switch with a sun and a moon sits in the top bar of every page and on the sign-in page. It flips the whole site, Navik included, between light and dark.

- **It is remembered.** The choice is saved in the browser (`localStorage`), so the site opens the same way next time on that computer. It is per browser, not per account.
- **Printing is always light.** A check report printed while in dark mode is switched to light for the print and back afterwards, because paper is white.
- **The drawing sheet stays white** in dark mode, like the paper drawing it shows.

**How it works.** Colours live in two places, and the switch changes both. Ant Design's colours come from `themeFor(dark)` in `theme.ts`, which hands Ant Design its built-in dark recipe plus our own dark values. The plain-CSS parts (sidebar border, Navik, the SETUP pill, the waiting list) use *CSS variables* such as `--surface`, defined once for light and once for dark at the top of `index.css`; the switch sets `data-theme="dark"` on the page and the variables change with it.

One thing needed care: the status colours (green, amber, red) are dark shades chosen for a white background and were hard to read on dark. In dark mode they are brightened; with the first (blue-tinted) dark palette tag text measured 5 to 1 or better, and it was not measured again after the change to black and grey.

**Dark mode is black and grey.** The first version was a dark navy; it was changed the same day to near-black pages, charcoal cards and grey borders with no blue. The greeting banner, the logo, Navik's header and the sign-in picture turn charcoal too. The main button is light grey with dark text. Switching fades over a third of a second instead of snapping.

**Buttons in light mode.** The main buttons (*New check*, *Add drawing*, *Run compliance check*, *Sign in*) were a flat blue. They are now a blue-to-indigo gradient with a soft glow, and lift slightly when the mouse is over them. Red "danger" buttons, such as approving against a block, are left alone so they still look like a warning.

**Small motions.** Each page fades up into place when it opens, and on the dashboard the cards arrive one after another. The number tiles lift under the mouse, rows in the waiting list slide slightly, table rows and menu items change colour gradually, and scrollbars are slim and match the mode. A soft ring shows which control the keyboard is on. All of this is CSS at the end of `index.css`, and all of it is switched off for people whose computer is set to reduce motion.

New file: `frontend/src/components/ModeSwitch.tsx`.

### SETUP notice removed (done, 13 Oct 2026)

The amber "SETUP — rules, clauses and ERP data shown are representative data" notice was taken off the top bar and the sign-in page at the user's request. The data is still representative data: nothing on the screens says so any more. The Rule Library page's warning that its clause numbers, limits and formulas are invented, and not reviewed by a naval architect, was removed as well; the page now only explains how rule approval works. Anyone shown the tool must be told in person that the rules and data are representative.

### One-minute video (done, 13 Oct 2026)

`setup/walkthrough.mp4` (and a smaller `.webm`) is an 82-second tour of the new interface: sign in as admin, the dashboard, one drawing uploaded and blocked, its findings and the marked-up sheet, the admin's rejection, the Release Gate, Navik answering a question and opening a page, and dark mode. It is recorded by the same script as the long video, with one extra word:

    backend\.venv\Scripts\python.exe setup\record_walkthrough.py --short

It runs on its own temporary copy of the tool, so your checks are untouched. Navik's two answers come from the live model service, so the recording needs the API key and an internet connection, and his wording differs a little each time. The long video (`walkthrough.mp4`) has not been re-recorded and still shows the old look.

### The name Sentinel, and the GAINS application (done, 13 Oct 2026)

The project is called **Sentinel** for now. The sidebar, the sign-in page and the browser tab show the name, with "Drawing compliance checker" as a small line under it, and Navik introduces the site as Sentinel.

`docs/GAINS2026_Xarka_SENTINEL.docx` and `.pdf` are a Stage-I application for GRSE's GAINS 2026 scheme. It was made from the earlier SENTINEL application: the form, the header and the eight applicant rows (name, address, contact, PAN, GST, MSME status, company profile) are untouched, and the thirteen project rows were rewritten for Sentinel. It has five figures: a workflow diagram, a diagram of how Sentinel sits beside the ERP, and three screenshots of the system (dashboard, a check report with findings marked on the drawing, the release gate).

Things in it that are statements about the future, not about the system: the on-premise deployment with models on GRSE's own hardware (the system's helper and explainer call a hosted service), and the budget and pilot timeline, which were copied in shape from the SENTINEL application and must be confirmed before it is sent. The document says plainly that the system runs on example drawings and example rules.

### Reviewers approve and reject again (done, 13 Oct 2026)

Earlier today the decision was made admin-only. That is reversed: a **reviewer** can now approve or reject a release, the same as the admin, with one limit.

- **Not their own upload.** A reviewer cannot decide a check they uploaded themselves; another reviewer or the admin must. The idea is that two different people are involved: one submits, another releases. The server refuses it, and the screen shows "You submitted this check" in place of the buttons.
- **The admin is the exception.** The admin can decide anything, including their own upload, and the audit log marks it.
- **Engineers still cannot decide.**
- Everything else about a decision is unchanged: once only, a written reason when going against the verdict, overrides marked.
- Rules, the register and user accounts are still the admin's alone.

The wording on the screens changed to match ("awaits a decision", not "awaits the admin's decision"), Navik's guide was updated so he tells reviewers they can decide, and the dashboard's *Needs your decision* list shows a reviewer only the checks they are allowed to decide. Where older sections of this file say "only the admin decides", read "a reviewer or the admin". The captions in the video script were corrected, but both recorded videos were made before this change and still say the admin decides. In the GAINS document the roles diagram (Figure 2) was updated.

### Class approvals recorded in the app (done, 14 Oct 2026)

Class approvals used to come only from the ERP extract file. Now a **reviewer or the admin** can record them on the Class Approvals page:

- **Record submission** opens a form: drawing (picked from the register), revision (filled in with the current one), submitted to (classification society or customer), date sent, and state (Awaiting, Approved, Returned with comments).
- Each row has **Mark approved**, and **Returned** while it is still awaiting, for when the answer comes back.
- **One record per drawing revision.** Recording a revision that already has a record updates it instead of adding a second one.
- Every change is in the audit log as `class_approval.recorded` or `class_approval.updated`, with the before and after.
- **The ERP extract does not undo it.** A record made in the app is marked `manual`; the next extract load keeps it, just like a drawing an admin edited. This needed one new database column, `source`, added by migration `0006` (the tool backs the database up before any migration).
- The Release Gate, register and dashboard follow straight away: once a revision is approved, its work orders lose the class-approval warning.
- Engineers can see the page but not change it. Navik knows about the new buttons.

New test: 62 backend tests pass.

### A map of the code with graphify (done, 14 Oct 2026)

`graphify-out/` holds a graph of the whole project: every file, function, class and screen as a dot, and every call, import and use as a line (805 dots, 1960 lines, grouped into 32 neighbourhoods). Open `graphify-out/graph.html` through the preview server named `graph`, search for a name, and click it to see what it touches. `GRAPH_REPORT.md` lists the most connected parts; the top ones are `User`, `extract()`, `create_check()` and `audit()`.

It is useful before a change: ask what uses a thing, and you know what the change can break. For class approvals it showed the database table `ClassApproval` is read in four places (the register, the release gate, the drawing page and the new recording route), which matched what the tests cover.

Refresh it after code changes with `graphify update .` from the project folder. `.graphifyignore` keeps installed packages, build output, the database and the videos out of it. The graph does not see a model used through a module name (`models.ClassApproval` in the extract loader), so it can miss a caller.

### Code review and fixes (done, 14 Oct 2026)

A review of the whole code base found two real mistakes and four smaller things, all fixed:

1. **Revision comparison after a corrected scan.** When a new revision was compared with an earlier *scanned* check, the tool read the old scan again and used what OCR saw, not what the person had confirmed. A corrected misreading (S275 read as $275) came back as a fake "change". It now uses the confirmed values stored with the earlier check.
2. **Names compared as patterns.** Checking whether a username or drawing number was already taken used SQL `LIKE`, where `_` means "any one character". So `eng_neer` was refused because `engineer` exists, and `GRSE_H_101` because `GRSE-H-101` exists. It now compares the names themselves, ignoring capitals.
3. **One database query per check.** Lists of checks (dashboard, Checks page, Release Gate, Navik) fetched each check's decision with its own query. They are now fetched together, so the pages stay quick as checks pile up.
4. **Two decisions at the same moment.** If two people decided the same check at once, the second got a server error. They now get "This check has already been decided."
5. **Leftovers removed:** two unused colour constants, and an "upload" permission that every role passed anyway (uploading simply needs a sign-in).

Three new tests; 65 backend tests pass.

### Navik finds before he answers, and never just fails (done, 15 Oct 2026)

**Retrieval (often called RAG, "retrieval-augmented generation").** Before, every question sent the model the whole guide and a summary of every record: about 13,300 characters each time. Now Navik first *searches*, then sends only the lines that match: the six best guide lines and the ten best record lines, plus the totals. That is 3,000 to 7,000 characters, which the model reads faster and which uses far less of the free service's per-minute allowance. In a test, seven questions in a row were answered in 1 to 2.5 seconds each with no "busy" errors; before, the fourth usually failed.

The search is plain text search (`backend/app/core/retrieve.py`), the method most search engines started from, called BM25: a line scores higher when it shares more of the question's words, when those words are rare, and when the line is short. Numbers like `GRSE-H-102` and `WO-24018` stay whole words, so asking about one record finds that record. No AI model or extra library is needed, so it is instant and works on this laptop. The previous question is searched too, so a follow-up like "and why?" still finds the right lines.

**No interruptions.**
- *Several keys:* `GRSE_EXPLAINER_KEY` may hold more than one key, separated by commas. When one is busy, the next is used.
- *A second model:* when the main model (`gpt-oss-20b`) is busy, the larger `gpt-oss-120b` is tried; it has its own allowance. Set with `GRSE_FALLBACK_MODEL`.
- *Answer without the AI:* if every attempt fails, or no key is set at all, Navik replies with the best matching guide or record lines as they are, marked "(Quick answer from Sentinel's guide and records; the AI assistant is not available right now.)" He no longer shows an error.
- Each attempt waits at most 15 seconds instead of 30.

**The API key** is now stored in `backend/.env` (copied from the `GROQ_API_KEY` Windows setting), so the server finds it however it is started. That file holds a secret: never share or send it.

The explainer on the check report uses the same key rotation and second model. Two new tests; 66 backend tests pass.

### Project documents (done, 12 Oct 2026)

Two PDFs in `docs/`, made from this file and from the code:

- `1-Project-Overview-and-Flow.pdf` (13 pages): the problem, who uses the tool, the flow of one check, the rules, the gate, scans, the AI summary, the screens, the walkthrough kit and the limits. No programming knowledge needed.
- `2-Code-Explanation.pdf` (14 pages): technology choices, a map of the files, the architecture, one upload followed through the code, the key functions, the tables, the API, the frontend, the tests, and how to change things.

They are built by `python docs/build_docs.py`. The code excerpts and the list of known shortcuts in the second document are read from the source files at build time, so rebuilding after a code change keeps them accurate. The screenshots are frames from the walkthrough video.

### All six phases are built
