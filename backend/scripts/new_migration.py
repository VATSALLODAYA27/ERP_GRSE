"""Write a migration for whatever changed in app/models.py since the last one.

Run from backend/ after editing the models:  python -m scripts.new_migration 0002 "add scan fields to checks"
Read the generated file in migrations/versions/ before using it: it is a draft, and it is what will run on real data.
"""
import sys

from alembic import command
from alembic.config import Config

from app import config
from app.db import migrate

if __name__ == "__main__":
    revision_id, message = sys.argv[1], sys.argv[2]
    migrate()  # the comparison is against a database that is up to date
    cfg = Config()
    cfg.set_main_option("script_location", str(config.BACKEND_DIR / "migrations"))
    command.revision(cfg, message=message, rev_id=revision_id, autogenerate=True)
