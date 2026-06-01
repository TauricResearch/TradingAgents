import os
import pytest
from sqlmodel import SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from web.server import db


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("TRADINGAGENTS_DASHBOARD_DB", str(db_path))
    # reload the module-level engine
    db._engine = None
    db.init_db()
    yield str(db_path)
    db._engine = None
