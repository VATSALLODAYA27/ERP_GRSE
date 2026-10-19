import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")  # optional local settings and secrets; see .env.example

# The rule file is part of the tool.
RULES_FILE = BACKEND_DIR / "data" / "rules" / "rules.json"

# Everything a demo needs lives in demo/: the mock ERP extract, the mock drawings and the demo logins.
DEMO_DIR = BACKEND_DIR.parent / "demo"
EXTRACT_DIR = DEMO_DIR / "register"
SAMPLES_DIR = DEMO_DIR / "drawings"
SEED_USERS_FILE = DEMO_DIR / "demo_logins.json"

# Everything the tool itself writes: its database and the uploaded drawings.
VAR_DIR = Path(os.environ.get("GRSE_VAR_DIR", BACKEND_DIR / "var"))
UPLOAD_DIR = VAR_DIR / "uploads"
# One SQLite file by default. Set GRSE_DATABASE_URL to use a database server instead, e.g. postgresql+psycopg://user:pass@host/grse
DATABASE_URL = os.environ.get("GRSE_DATABASE_URL", f"sqlite:///{VAR_DIR / 'app.db'}")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
# Set GRSE_COOKIE_SECURE=1 once the tool is served over HTTPS.
COOKIE_SECURE = os.environ.get("GRSE_COOKIE_SECURE") == "1"

# The optional explainer: any service that speaks the OpenAI chat format. No key means it is switched off.
EXPLAINER_URL = os.environ.get("GRSE_EXPLAINER_URL", "https://api.groq.com/openai/v1")
EXPLAINER_MODEL = os.environ.get("GRSE_EXPLAINER_MODEL", "openai/gpt-oss-20b")
EXPLAINER_KEY = os.environ.get("GRSE_EXPLAINER_KEY") or os.environ.get("GROQ_API_KEY", "")  # several keys: separate with commas
# Tried when the main model is busy; a different model has its own per-minute allowance.
FALLBACK_MODEL = os.environ.get("GRSE_FALLBACK_MODEL", "openai/gpt-oss-120b")
# Navik, the helper, uses the same service. Set GRSE_HELPER_DATA=0 to stop it being sent what the screens show
# (checks, register, gate, class approvals, rules); it then only explains how the tool works.
HELPER_SEES_DATA = os.environ.get("GRSE_HELPER_DATA", "1") != "0"
