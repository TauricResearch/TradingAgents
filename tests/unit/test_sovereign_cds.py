from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

from tradingagents.dataflows.sovereign_cds import (
    SovereignCDSRow,
    SovereignCDSSnapshot,
    WorldGovernmentBondsCDSClient,
    get_todays_sovereign_cds_snapshot,
)


def _snapshot(last_update: datetime) -> SovereignCDSSnapshot:
    return SovereignCDSSnapshot(
        rows=[
            SovereignCDSRow(
                country="United States",
                rating="AA+",
                cds_5y=37.81,
                var_1m_pct=21.85,
                var_6m_pct=2.58,
                implied_pd_pct=0.63,
                date_label="30 Mar",
            ),
            SovereignCDSRow(
                country="Germany",
                rating="AAA",
                cds_5y=9.67,
                var_1m_pct=25.75,
                var_6m_pct=9.14,
                implied_pd_pct=0.16,
                date_label="30 Mar",
            ),
        ],
        last_update=last_update,
    )


def test_get_todays_sovereign_cds_snapshot_returns_markdown_when_current():
    now = datetime(2026, 3, 30, 14, 0, tzinfo=UTC)
    snapshot = _snapshot(datetime(2026, 3, 30, 13, 45, tzinfo=UTC))

    with patch.object(WorldGovernmentBondsCDSClient, "fetch_snapshot", return_value=snapshot):
        result = get_todays_sovereign_cds_snapshot(now=now)

    assert result.startswith("# Sovereign CDS Snapshot")
    assert "United States" in result
    assert "Germany" in result
    assert "Skipped:" not in result


def test_get_todays_sovereign_cds_snapshot_skips_when_stale():
    now = datetime(2026, 3, 30, 14, 0, tzinfo=UTC)
    snapshot = _snapshot(datetime(2026, 3, 29, 23, 45, tzinfo=UTC))

    with patch.object(WorldGovernmentBondsCDSClient, "fetch_snapshot", return_value=snapshot):
        result = get_todays_sovereign_cds_snapshot(now=now)

    assert result.startswith("# Sovereign CDS Snapshot")
    assert "Skipped:" in result
    assert "2026-03-29" in result
    assert "2026-03-30 UTC" in result


def test_is_current_snapshot_uses_utc_date_not_local_calendar_date():
    snapshot = _snapshot(datetime(2026, 3, 29, 23, 45, tzinfo=UTC))
    local_reference = datetime(2026, 3, 30, 1, 15, tzinfo=timezone(timedelta(hours=2)))

    assert WorldGovernmentBondsCDSClient.is_current_snapshot(snapshot, now=local_reference)
