import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .base import Base

DEFAULT_DB_DIR = "./data"
DEFAULT_DB_NAME = "tradingagents.db"

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_database_url() -> str:
    db_dir = os.getenv("TRADINGAGENTS_DB_DIR", DEFAULT_DB_DIR)
    db_name = os.getenv("TRADINGAGENTS_DB_NAME", DEFAULT_DB_NAME)

    Path(db_dir).mkdir(parents=True, exist_ok=True)

    db_path = Path(db_dir) / db_name
    return f"sqlite:///{db_path}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            echo=os.getenv("TRADINGAGENTS_DB_ECHO", "false").lower() == "true",
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    Base.metadata.create_all(bind=get_engine())


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
