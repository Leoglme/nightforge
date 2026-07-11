"""
Database configuration and session management.
"""
import logging

# Suppress SQLAlchemy INFO logs before the engine is created during import.
for _name in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
    _logger = logging.getLogger(_name)
    _logger.setLevel(logging.ERROR)
    _logger.propagate = False

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


def get_db():
    """
    Database dependency for FastAPI routes.

    Yields:
        Database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Create all tables defined in the models.
    """
    from models.user import User  # noqa: F401
    from models.machine import Machine  # noqa: F401
    from models.project import Project  # noqa: F401
    from models.project_machine_path import ProjectMachinePath  # noqa: F401
    from models.project_message import ProjectMessage  # noqa: F401
    from models.queue_item import QueueItem  # noqa: F401
    from models.run import Run  # noqa: F401
    from models.run_project import RunProject  # noqa: F401
    from models.run_event import RunEvent  # noqa: F401
    from models.run_message import RunMessage  # noqa: F401
    from models.quota_snapshot import QuotaSnapshot  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_optional_columns()


def _ensure_optional_columns() -> None:
    """Add newer nullable columns on existing databases without Alembic."""
    from sqlalchemy import inspect, text

    additions = {
        "run_messages": [
            ("claude_session_id", "VARCHAR(64) NULL"),
            ("claude_model", "VARCHAR(32) NULL"),
            ("source_item_ids", "JSON NULL"),
        ],
        "project_messages": [
            ("claude_session_id", "VARCHAR(64) NULL"),
            ("claude_model", "VARCHAR(32) NULL"),
        ],
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
