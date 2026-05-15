"""Tests for the thread-safe ProgressTracker.

Covers:
- Initialization and dynamic agent/section setup
- Write methods (add_message, add_tool_call, update_agent_status, etc.)
- Snapshot immutability — mutations to the tracker must not leak
- Deduplication via has_seen_message()
- Thread safety — concurrent writers must not corrupt state
- Deep-copy of tool_call args (CR-01 fix)
- Logging on unknown agent/section (WR-03 fix)
"""

import threading
import time

import pytest

from tradingagents.progress import (
    ANALYST_MAPPING,
    FIXED_AGENTS,
    REPORT_SECTIONS,
    SECTION_TITLES,
    ProgressSnapshot,
    ProgressTracker,
)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInitForAnalysis:
    def test_builds_agent_status_from_selected_analysts(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market", "news"])

        snap = tracker.snapshot()
        assert "Market Analyst" in snap.agent_status
        assert "News Analyst" in snap.agent_status
        # Not selected — must be absent from analyst slots
        assert "Sentiment Analyst" not in snap.agent_status
        assert "Fundamentals Analyst" not in snap.agent_status

    def test_includes_fixed_agents(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        snap = tracker.snapshot()
        for agents in FIXED_AGENTS.values():
            for agent in agents:
                assert agent in snap.agent_status
                assert snap.agent_status[agent] == "pending"

    def test_builds_report_sections_for_selected_analysts(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market", "fundamentals"])

        snap = tracker.snapshot()
        assert "market_report" in snap.report_sections
        assert "fundamentals_report" in snap.report_sections
        # Always-included sections (analyst_key is None)
        assert "investment_plan" in snap.report_sections
        assert "trader_investment_plan" in snap.report_sections
        assert "final_trade_decision" in snap.report_sections
        # Not selected
        assert "sentiment_report" not in snap.report_sections
        assert "news_report" not in snap.report_sections

    def test_case_insensitive_analyst_keys(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["Market", "NEWS"])

        snap = tracker.snapshot()
        assert "Market Analyst" in snap.agent_status
        assert "News Analyst" in snap.agent_status

    def test_reset_clears_prior_state(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.add_message("System", "first run")
        tracker.update_agent_status("Market Analyst", "completed")

        # Second init should clear everything
        tracker.init_for_analysis(["news"])
        snap = tracker.snapshot()
        assert len(snap.messages) == 0
        assert "Market Analyst" not in snap.agent_status
        assert "News Analyst" in snap.agent_status
        assert snap.agent_status["News Analyst"] == "pending"


# ---------------------------------------------------------------------------
# Write methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWriteMethods:
    def test_add_message(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.add_message("System", "Hello world")

        snap = tracker.snapshot()
        assert len(snap.messages) == 1
        ts, msg_type, content = snap.messages[0]
        assert msg_type == "System"
        assert content == "Hello world"
        assert len(ts) == 8  # HH:MM:SS

    def test_add_tool_call(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.add_tool_call("search", {"query": "AAPL"})

        snap = tracker.snapshot()
        assert len(snap.tool_calls) == 1
        ts, name, args = snap.tool_calls[0]
        assert name == "search"
        assert args == {"query": "AAPL"}

    def test_update_agent_status(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.update_agent_status("Market Analyst", "in_progress")

        snap = tracker.snapshot()
        assert snap.agent_status["Market Analyst"] == "in_progress"
        assert snap.current_agent == "Market Analyst"

    def test_update_report_section(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.update_report_section("market_report", "# Analysis")

        snap = tracker.snapshot()
        assert snap.report_sections["market_report"] == "# Analysis"

    def test_message_deque_bounded(self) -> None:
        tracker = ProgressTracker(max_messages=3)
        tracker.init_for_analysis(["market"])
        for i in range(5):
            tracker.add_message("System", f"msg-{i}")

        snap = tracker.snapshot()
        assert len(snap.messages) == 3
        # Oldest messages evicted
        assert snap.messages[0][2] == "msg-2"

    def test_last_activity_updated_on_writes(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        secs = tracker.seconds_since_last_activity()
        assert secs is not None
        assert secs < 1.0  # just initialized


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSnapshotImmutability:
    def test_snapshot_agent_status_is_a_copy(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        snap1 = tracker.snapshot()
        tracker.update_agent_status("Market Analyst", "completed")
        snap2 = tracker.snapshot()

        # snap1 should still show old value
        assert snap1.agent_status["Market Analyst"] == "pending"
        assert snap2.agent_status["Market Analyst"] == "completed"

    def test_snapshot_messages_is_a_copy(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.add_message("System", "before")

        snap = tracker.snapshot()
        tracker.add_message("System", "after")

        assert len(snap.messages) == 1
        assert snap.messages[0][2] == "before"

    def test_tool_call_args_deep_copied(self) -> None:
        """CR-01: mutable args must not leak through snapshot."""
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        original_args = {"query": "AAPL", "nested": {"key": "value"}}
        tracker.add_tool_call("search", original_args)

        # Mutate the original — should NOT affect tracker
        original_args["nested"]["key"] = "MUTATED"

        snap = tracker.snapshot()
        assert snap.tool_calls[0][2]["nested"]["key"] == "value"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeduplication:
    def test_has_seen_message_first_call_returns_false(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        assert tracker.has_seen_message("msg-001") is False

    def test_has_seen_message_second_call_returns_true(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.has_seen_message("msg-001")
        assert tracker.has_seen_message("msg-001") is True

    def test_init_clears_dedup_set(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])
        tracker.has_seen_message("msg-001")

        tracker.init_for_analysis(["market"])
        # Same ID should return False after reset
        assert tracker.has_seen_message("msg-001") is False


# ---------------------------------------------------------------------------
# Report counting
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReportCounting:
    def test_completed_reports_requires_both_content_and_agent_done(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        # Content without agent completion -> not counted
        tracker.update_report_section("market_report", "# Report")
        assert tracker.get_completed_reports_count() == 0

        # Agent completion without content -> not counted
        tracker.update_agent_status("Market Analyst", "completed")
        # Now both conditions met
        assert tracker.get_completed_reports_count() == 1

    def test_total_reports_count(self) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market", "news"])
        # 2 analyst sections + 3 always-included = 5
        assert tracker.get_total_reports_count() == 5


# ---------------------------------------------------------------------------
# Unknown agent/section logging (WR-03)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUnknownAgentWarning:
    def test_unknown_agent_logged(self, caplog) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        with caplog.at_level("WARNING", logger="tradingagents.progress"):
            tracker.update_agent_status("Nonexistent Agent", "in_progress")

        assert "Unknown agent" in caplog.text
        assert "Nonexistent Agent" in caplog.text

    def test_unknown_section_logged(self, caplog) -> None:
        tracker = ProgressTracker()
        tracker.init_for_analysis(["market"])

        with caplog.at_level("WARNING", logger="tradingagents.progress"):
            tracker.update_report_section("nonexistent_report", "content")

        assert "Unknown report section" in caplog.text


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThreadSafety:
    def test_concurrent_writers_do_not_corrupt_state(self) -> None:
        """Hammer the tracker from multiple threads and verify consistency."""
        tracker = ProgressTracker(max_messages=500)
        tracker.init_for_analysis(["market", "news", "social", "fundamentals"])

        errors: list[str] = []
        iterations = 50

        def writer(thread_id: int) -> None:
            try:
                for i in range(iterations):
                    tracker.add_message("System", f"t{thread_id}-msg-{i}")
                    tracker.add_tool_call("tool", {"t": thread_id, "i": i})
                    # Rotate through agents
                    agents = list(ANALYST_MAPPING.values())
                    agent = agents[i % len(agents)]
                    tracker.update_agent_status(agent, "in_progress")
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"

        # Snapshot should be internally consistent
        snap = tracker.snapshot()
        assert len(snap.messages) > 0
        assert len(snap.tool_calls) > 0

    def test_snapshot_while_writing(self) -> None:
        """Reader thread takes snapshots while writer is active."""
        tracker = ProgressTracker(max_messages=200)
        tracker.init_for_analysis(["market"])

        snapshots: list[ProgressSnapshot] = []
        stop_event = threading.Event()

        def writer() -> None:
            for i in range(100):
                tracker.add_message("Agent", f"msg-{i}")
            stop_event.set()

        def reader() -> None:
            while not stop_event.is_set():
                snapshots.append(tracker.snapshot())
                time.sleep(0.001)

        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        r.start()
        w.start()
        w.join(timeout=10)
        r.join(timeout=10)

        # All snapshots must be valid ProgressSnapshot objects
        assert len(snapshots) > 0
        for snap in snapshots:
            assert isinstance(snap, ProgressSnapshot)
            assert isinstance(snap.messages, list)


# ---------------------------------------------------------------------------
# Constants consistency
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstants:
    def test_section_titles_cover_all_report_sections(self) -> None:
        for section_key in REPORT_SECTIONS:
            assert section_key in SECTION_TITLES, (
                f"SECTION_TITLES missing key {section_key!r}"
            )

    def test_analyst_mapping_values_unique(self) -> None:
        values = list(ANALYST_MAPPING.values())
        assert len(values) == len(set(values)), "Duplicate analyst display names"
