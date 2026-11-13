"""Database engine and session helpers (SQLite via SQLModel)."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from app import config

_engine = None
_engine_path = None


def get_engine():
    global _engine, _engine_path
    path = config.db_path()
    if _engine is None or _engine_path != path:
        _engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        _engine_path = path
    return _engine


def create_tables() -> None:
    from app.l1_data import models  # noqa: F401  (registers the tables)
    SQLModel.metadata.create_all(get_engine())


def drop_tables() -> None:
    from app.l1_data import models  # noqa: F401
    SQLModel.metadata.drop_all(get_engine())


def get_session():
    with Session(get_engine()) as session:
        yield session
