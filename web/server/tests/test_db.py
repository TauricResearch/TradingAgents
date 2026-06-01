from sqlmodel import select

from web.server import db
from web.server.db import Watchlist, Run, Event


def test_init_db_creates_tables(temp_db):
    # init_db already called by fixture
    with db.get_session() as s:
        assert s.exec(select(Watchlist)).first() is None
        assert s.exec(select(Run)).first() is None
        assert s.exec(select(Event)).first() is None
