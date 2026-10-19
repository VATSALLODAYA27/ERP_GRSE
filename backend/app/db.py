import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IS_SQLITE = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False} if IS_SQLITE else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

BASELINE = "0001"  # the schema as it was when migrations were introduced


class Base(DeclarativeBase):
    pass


def get_session():
    with SessionLocal() as session:
        yield session


def backup(label: str, target=engine) -> Path | None:
    """Copy the SQLite database file to backups/ beside it. Safe while the database is in use."""
    if target.dialect.name != "sqlite" or not target.url.database or not Path(target.url.database).exists():
        return None  # shortcut: other databases are backed up with their own tools (pg_dump); wire that in when one is used
    source_path = Path(target.url.database)
    folder = source_path.parent / "backups"
    folder.mkdir(exist_ok=True)
    copy_path = folder / f"{source_path.stem}-{datetime.now():%Y%m%d-%H%M%S}-{label}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(copy_path) as copy:
        source.backup(copy)
    return copy_path


def migrate(target=engine) -> None:
    """Bring the database up to the tables the code expects, keeping every row that is in it.

    Runs at every start. With nothing to change it does nothing; before changing anything it takes a backup.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(config.BACKEND_DIR / "migrations"))
    cfg.attributes["engine"] = target
    head = ScriptDirectory.from_config(cfg).get_current_head()

    with target.connect() as connection:
        has_tables = bool(inspect(connection).get_table_names())
        current = MigrationContext.configure(connection).get_current_revision()

    if has_tables and current is None:
        # A database created before migrations existed: its tables are exactly what the baseline creates.
        command.stamp(cfg, BASELINE)
        current = BASELINE
    if has_tables and current != head:
        backup(f"before-{head}", target)
    command.upgrade(cfg, "head")
