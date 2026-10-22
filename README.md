# Drawing Compliance Checker

A pre-release gate for drawings: it compares each drawing with the drawing register and a fixed, clause-cited rule set, and gives a verdict before a work order is released.

**All rules, clauses, drawings and ERP data in this repository are representative data.** None of it comes from GRSE or from a real classification society.

See [learning.md](learning.md) for an explanation of how it works and what has been built so far, and [setup/README.md](setup/README.md) for a guided walkthrough.

## Documents

- [docs/1-Project-Overview-and-Flow.pdf](docs/1-Project-Overview-and-Flow.pdf): what the project is and how a drawing moves through it.
- [docs/2-Code-Explanation.pdf](docs/2-Code-Explanation.pdf): how the code is organised.
- Rebuild both with `python docs/build_docs.py` (needs `pip install reportlab`).

## What you need

Python 3.12 or newer and Node.js. To check scanned drawings, also install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (`winget install --id UB-Mannheim.TesseractOCR`); without it everything except scans works.

## Quickest way to try it

```powershell
.\setup\run.ps1
```

This installs what is missing, loads the representative data, builds the web app and opens it. The sections below are for development.

## First-time setup

From `backend/` (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.load_extract     # copies the representative ERP extract from setup/register into var/app.db
.\.venv\Scripts\python.exe -m scripts.seed_users       # creates the default users
```

From `frontend/`:

```powershell
npm install
```

## Run it

Two terminals.

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

From `frontend/`:

```powershell
npm run dev
```

Open http://localhost:5173 and sign in. The default users (an admin, a reviewer and two engineers) and their passwords are in `setup/logins.json`. Upload any PDF from `setup/drawings/` under New Check.

To run as a single process instead, run `npm run build` in `frontend/`, start only the backend, and open http://127.0.0.1:8000.

## Optional: the AI summary

The *Revision changes* tab can show a plain-language summary written by a hosted language model. It is switched on by an API key, either in the `GROQ_API_KEY` environment variable or in `backend/.env` (copy `backend/.env.example`). Without a key the feature does not appear. Only the change list is sent, never the drawing, and it never affects a verdict.

## The data

Everything the tool records is in `backend/var/` (the database `app.db` and the uploaded PDFs). It survives restarts. When the code needs different tables, the server upgrades the database at start-up and copies it to `backend/var/backups/` first. Do not delete `backend/var/`; after changing `backend/app/models.py`, run `python -m scripts.new_migration <number> "<what changed>"` from `backend/`.

## Run the tests

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
