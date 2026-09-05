from datetime import date, datetime, timezone

from tradingagents.research_platform.game_approvals import (
    GameApprovalKind,
    GameApprovalRecord,
    GameCompanyMatchStatus,
    JsonGameApprovalStore,
    make_approval_id,
    match_game_approval,
)


def _record(
    operator: str,
    *,
    publisher: str = "Test Publisher Co., Ltd.",
    approved_on: date = date(2026, 6, 29),
) -> GameApprovalRecord:
    kind = GameApprovalKind.DOMESTIC
    return GameApprovalRecord(
        approval_id=make_approval_id(kind, "NPPA-2026-1", "Test Game"),
        kind=kind,
        game_name="Test Game",
        publishing_entity=publisher,
        operating_entity=operator,
        approval_number="NPPA-2026-1",
        isbn="ISBN 1",
        approval_date=approved_on,
        source_url="https://www.nppa.gov.cn/example.html",
        available_as_of=approved_on,
        retrieved_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )


def test_matches_century_huatong_exact_legal_entity():
    result = match_game_approval(_record("\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8"))

    assert result.status is GameCompanyMatchStatus.MATCHED
    assert result.symbol == "002602"
    assert result.confidence == 1.0
    assert result.relationship_source_url.endswith("1218603909.PDF")


def test_matches_perfect_world_exact_legal_entity_after_nfkc_normalization():
    result = match_game_approval(
        _record("\u5b8c\u7f8e\u4e16\u754c(\u5317\u4eac)\u8f6f\u4ef6\u79d1\u6280\u53d1\u5c55\u6709\u9650\u516c\u53f8")
    )

    assert result.status is GameCompanyMatchStatus.MATCHED
    assert result.symbol == "002624"


def test_brand_like_unknown_entity_requires_manual_review():
    result = match_game_approval(_record("\u5b8c\u7f8e\u4e16\u754c\u6d4b\u8bd5\u7f51\u7edc\u6709\u9650\u516c\u53f8"))

    assert result.status is GameCompanyMatchStatus.REVIEW_REQUIRED
    assert result.symbol is None


def test_conflicting_exact_entities_require_manual_review():
    result = match_game_approval(
        _record(
            "\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8",
            publisher="\u4e0a\u6d77\u5b8c\u7f8e\u65f6\u7a7a\u8f6f\u4ef6\u6709\u9650\u516c\u53f8",
        )
    )

    assert result.status is GameCompanyMatchStatus.REVIEW_REQUIRED
    assert result.symbol is None


def test_store_merges_records_and_enforces_point_in_time(tmp_path):
    store = JsonGameApprovalStore(tmp_path)
    older = _record("\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8", approved_on=date(2026, 5, 1))
    newer = older.model_copy(
        update={
            "approval_id": "newer",
            "approval_number": "NPPA-2026-2",
            "approval_date": date(2026, 6, 1),
            "available_as_of": date(2026, 6, 2),
        }
    )
    store.save([older])
    store.save([newer])

    assert len(store.list()) == 2
    assert len(store.list(as_of_date=date(2026, 5, 31))) == 1
    digest = store.digest("002602", as_of_date=date(2026, 6, 30))
    assert digest.matched_count == 2
    assert digest.latest_approval_date == date(2026, 6, 1)
