from __future__ import annotations

import asyncio

import pytest

from tradingagents_service.api import dependencies


class _FakeSession:
    def __init__(self) -> None:
        self.rolled_back = False
        self.closed = False

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.unit
def test_get_db_session_rolls_back_and_closes_on_exception(monkeypatch):
    async def _run() -> None:
        fake_session = _FakeSession()

        def _factory():
            return fake_session

        monkeypatch.setattr(dependencies, "_session_factory", _factory)

        agen = dependencies.get_db_session()
        yielded = await agen.__anext__()
        assert yielded is fake_session

        with pytest.raises(RuntimeError):
            await agen.athrow(RuntimeError("boom"))

        assert fake_session.rolled_back is True
        assert fake_session.closed is True

    asyncio.run(_run())
