from __future__ import annotations

import pytest

from tradingagents_service.db.session import get_engine


@pytest.mark.unit
def test_get_engine_reuses_bounded_engine_for_same_database_url() -> None:
    first = get_engine("postgresql+psycopg://user:pass@localhost:5432/db")
    second = get_engine("postgresql+psycopg://user:pass@localhost:5432/db")

    assert first is second
