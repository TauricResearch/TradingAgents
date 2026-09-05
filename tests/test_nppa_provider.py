from datetime import date, datetime, timezone

import pytest

from tradingagents.research_platform.game_approvals import GameApprovalKind
from tradingagents.research_platform.nppa_provider import NppaApprovalProvider, NppaProviderError

INDEX_HTML = """
<html><body>
  <a href="./202606/t20260630_996870.html">2026 June approvals</a>
  <a href="https://example.com/t20260630_1.html">off-site</a>
</body></html>
"""
PAGE_HTML = """
<table>
<tr><th>\u5e8f\u53f7</th><th>\u540d\u79f0</th><th>\u7533\u62a5\u7c7b\u522b</th><th>\u51fa\u7248\u5355\u4f4d</th><th>\u8fd0\u8425\u5355\u4f4d</th><th>\u6279\u590d\u6587\u53f7</th><th>\u51fa\u7248\u7269\u53f7</th><th>\u6279\u51c6\u65f6\u95f4</th></tr>
<tr><td>1</td><td>Seven Cell</td><td>Publisher A</td><td>\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8</td><td>NPPA-1</td><td>ISBN-1</td><td>2026\u5e7406\u670829\u65e5</td></tr>
<tr><td>2</td><td>Eight Cell</td><td>\u79fb\u52a8</td><td>Publisher B</td><td>Operator B</td><td>NPPA-2</td><td>ISBN-2</td><td>2026-06-28</td></tr>
</table>
"""


def _provider(fetch_text=lambda _: INDEX_HTML):
    return NppaApprovalProvider(
        fetch_text=fetch_text,
        now=lambda: datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def test_discovers_only_official_dated_pages():
    pages = _provider().discover_pages(GameApprovalKind.DOMESTIC)

    assert pages == [
        (
            "https://www.nppa.gov.cn/bsfw/jggs/yxspjg/gcwlyxspxx/202606/t20260630_996870.html",
            date(2026, 6, 30),
        )
    ]


def test_parses_seven_and_eight_cell_rows():
    records = _provider().parse_page(
        PAGE_HTML,
        source_url="https://www.nppa.gov.cn/page.html",
        kind=GameApprovalKind.DOMESTIC,
        available_as_of=date(2026, 6, 30),
    )

    assert len(records) == 2
    assert records[0].application_category is None
    assert records[0].operating_entity == "\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8"
    assert records[1].application_category == "\u79fb\u52a8"
    assert records[1].approval_date == date(2026, 6, 28)


def test_fetch_filters_rows_to_requested_date_range():
    def fetch_text(url):
        return INDEX_HTML if url.endswith("/") else PAGE_HTML

    records = _provider(fetch_text).fetch(
        date(2026, 6, 29),
        date(2026, 6, 29),
        kinds=[GameApprovalKind.DOMESTIC],
    )

    assert [item.game_name for item in records] == ["Seven Cell"]


def test_empty_approval_page_is_rejected():
    with pytest.raises(NppaProviderError, match="No approval rows"):
        _provider().parse_page(
            "<html></html>",
            source_url="https://www.nppa.gov.cn/empty.html",
            kind=GameApprovalKind.DOMESTIC,
            available_as_of=date(2026, 6, 30),
        )
