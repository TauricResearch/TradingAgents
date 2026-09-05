from datetime import date, datetime, timezone

from tradingagents.research_platform.research_jobs import (
    ResearchDataProvider,
    ResearchJob,
    ResearchJobStatus,
)
from tradingagents.research_platform.watchlist import JsonWatchlistStore
from tradingagents.research_platform.watchlist_refresh import (
    WatchlistRefreshRequest,
    execute_watchlist_refresh,
    submit_watchlist_refresh,
)


class RecordingJobs:
    def __init__(self):
        self.requests = []
        self.jobs = {}

    def submit(self, request):
        self.requests.append(request)
        job = ResearchJob(
            job_id=f"fixture-{len(self.requests)}",
            request=request,
            status=ResearchJobStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        self.jobs[job.job_id] = job
        return job

    def wait(self, job_id, timeout=None):
        del timeout
        return self.jobs[job_id].model_copy(update={"status": ResearchJobStatus.SUCCEEDED})


def test_watchlist_refresh_queues_one_signal_free_job_per_explicit_symbol(tmp_path):
    watchlist = JsonWatchlistStore(tmp_path)
    watchlist.add("600519")
    watchlist.add("0700.HK")
    jobs = RecordingJobs()

    batch = submit_watchlist_refresh(
        watchlist,
        jobs,
        WatchlistRefreshRequest(
            as_of_date=date(2026, 7, 10),
            lookback_days=180,
            data_provider=ResearchDataProvider.AUTO,
        ),
    )

    assert batch.symbols == ["0700.HK", "600519"]
    assert [request.symbol for request in jobs.requests] == ["0700.HK", "600519"]
    assert all(request.manual_signal is None for request in jobs.requests)
    assert all(request.lookback_days == 180 for request in jobs.requests)


def test_watchlist_refresh_returns_empty_batch_without_explicit_symbols(tmp_path):
    batch = submit_watchlist_refresh(
        JsonWatchlistStore(tmp_path),
        RecordingJobs(),
        WatchlistRefreshRequest(),
    )

    assert batch.symbols == []
    assert batch.jobs == []


def test_watchlist_refresh_can_wait_for_terminal_results(tmp_path):
    watchlist = JsonWatchlistStore(tmp_path)
    watchlist.add("600519")
    jobs = RecordingJobs()

    outcome = execute_watchlist_refresh(
        watchlist,
        jobs,
        WatchlistRefreshRequest(as_of_date=date(2026, 7, 10)),
    )

    assert outcome.symbols == ["600519"]
    assert outcome.succeeded == 1
    assert outcome.failed == 0
    assert outcome.jobs[0].status == ResearchJobStatus.SUCCEEDED
