"""Narrative clustering, novelty, and source-family features."""

import pytest

from tradingagents.dataflows.media_features import cluster_events, source_family


def _row(source, external_id, text, created=1.0, author=None, sentiment=None):
    return {
        "source": source,
        "external_id": external_id,
        "title": text,
        "body": "",
        "created_utc": created,
        "author": author,
        "sentiment": sentiment,
    }


@pytest.mark.unit
def test_clusters_duplicate_reporting_and_preserves_source_families():
    rows = [
        _row("trendnews", "n1", "Central bank unexpectedly cuts interest rates", 3, "Reuters"),
        _row("x", "x1", "Central bank unexpectedly cuts rates today", 2, "publicvoice"),
        _row("globalnews", "n2", "Volcano closes international airport", 1, "AP"),
    ]

    clusters = cluster_events(rows, limit=10)

    rate_cluster = next(cluster for cluster in clusters if len(cluster.members) == 2)
    assert rate_cluster.source_families == ("global_news", "public_social")
    assert rate_cluster.novelty == 1.0


@pytest.mark.unit
def test_novelty_reference_demotes_repeated_narrative():
    repeated = _row("trendnews", "new", "Central bank cuts interest rates again", 3)
    genuinely_new = _row("trendnews", "novel", "Major earthquake disrupts Pacific shipping", 2)
    references = [_row("globalnews", "old", "Central bank cuts interest rates", 1)]

    clusters = cluster_events([repeated, genuinely_new], reference_rows=references, limit=2)

    assert clusters[0].representative["external_id"] == "novel"
    assert clusters[0].novelty > clusters[1].novelty


@pytest.mark.unit
def test_source_families_keep_social_opinion_separate_from_reporting():
    assert source_family("globalnews") == "global_news"
    assert source_family("stocktwits") == "retail_social"
    assert source_family("x") == "public_social"
