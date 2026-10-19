"""Run by Alembic for every migration command. The database and the tables to compare against come from the app."""
from alembic import context

from app import models  # noqa: F401  (importing registers every table on Base.metadata)
from app.db import Base, engine

target = context.config.attributes.get("engine", engine)


def render_item(type_, obj, autogen_context):
    """Generated migrations name plain SQLAlchemy types, so an old migration never breaks when app code is renamed."""
    if type_ == "type" and isinstance(obj, models.UTCDateTime):
        return "sa.DateTime()"
    return False


with target.connect() as connection:
    # render_as_batch: SQLite cannot alter a column in place, so Alembic rebuilds the table and copies the rows across.
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True, compare_type=True, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()
