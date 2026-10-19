from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from app import config
from app.db import BASELINE, Base, engine, migrate


def test_migrations_build_exactly_the_tables_the_code_expects():
    """Fails when a model changes without a migration: that change would need the database to be deleted."""
    migrate()
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata)
    assert differences == []


def test_upgrading_keeps_the_data_and_takes_a_backup(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'app.db'}")

    # A database from before migrations existed: baseline tables, a row of data, no version marker.
    cfg = Config()
    cfg.set_main_option("script_location", str(config.BACKEND_DIR / "migrations"))
    cfg.attributes["engine"] = database
    command.upgrade(cfg, BASELINE)
    with database.begin() as connection:
        connection.execute(text("INSERT INTO users (username, name, role, password_hash) VALUES ('kept', 'Kept User', 'engineer', 'x')"))
        connection.execute(text("DROP TABLE alembic_version"))

    migrate(database)
    migrate(database)  # a second start changes nothing

    with database.connect() as connection:
        assert connection.execute(text("SELECT name FROM users WHERE username = 'kept'")).scalar() == "Kept User"
        assert compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata) == []
    backups = list((tmp_path / "backups").glob("*.db")) if (tmp_path / "backups").exists() else []
    head_is_baseline = MigrationContext.configure(database.connect()).get_current_revision() == BASELINE
    assert head_is_baseline or len(backups) == 1  # one backup, taken before the first real change
