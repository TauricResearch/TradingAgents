import threading
import pytest
from datetime import datetime, timezone

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator.queue_store import insert_queue_job, lease_one


@pytest.mark.unit
def test_two_leasers_race_only_one_wins(tmp_path):
    """Two threads call lease_one on the same DB; exactly one returns the job."""
    db_path = str(tmp_path / "iic.db")
    # Seed one event and one job.
    boot = connect(db_path)
    store.insert_event(boot, event_id="ev1", source="rss",
                       ingested_ts=datetime.now(timezone.utc).isoformat(),
                       salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    insert_queue_job(boot, job_type="event_alert",
                     payload="{}", trigger_event_id="ev1")
    boot.close()

    results: list = []
    barrier = threading.Barrier(2)

    def worker():
        c = connect(db_path)
        barrier.wait()
        r = lease_one(c)
        results.append(r)
        c.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1, f"expected 1 winner, got {results}"
    assert len(losers) == 1
