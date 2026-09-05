from datetime import date, datetime, timezone
from json import loads
from threading import Thread
from urllib.request import urlopen

from tradingagents.research_platform.cockpit import create_cockpit_server
from tradingagents.research_platform.game_approvals import (
    GameApprovalKind,
    GameApprovalRecord,
    JsonGameApprovalStore,
    make_approval_id,
)


def test_cockpit_exposes_company_matched_game_approvals(tmp_path):
    kind = GameApprovalKind.DOMESTIC
    record = GameApprovalRecord(
        approval_id=make_approval_id(kind, "NPPA-1", "Tracked Game"),
        kind=kind,
        game_name="Tracked Game",
        publishing_entity="Publisher",
        operating_entity="\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8",
        approval_number="NPPA-1",
        approval_date=date(2026, 6, 29),
        source_url="https://www.nppa.gov.cn/example.html",
        available_as_of=date(2026, 6, 30),
        retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    JsonGameApprovalStore(tmp_path).save([record])
    server = create_cockpit_server(tmp_path, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urlopen(f"http://{host}:{port}/api/game-approvals?symbol=002602", timeout=2) as response:
            digest = loads(response.read().decode("utf-8"))
        with urlopen(f"http://{host}:{port}/api/snapshot?symbol=002602", timeout=2) as response:
            snapshot = loads(response.read().decode("utf-8"))
        with urlopen(f"http://{host}:{port}/api/game-opportunities", timeout=2) as response:
            opportunities = loads(response.read().decode("utf-8"))
        with urlopen(
            f"http://{host}:{port}/api/game-opportunity-history?symbol=002602", timeout=2
        ) as response:
            opportunity_history = loads(response.read().decode("utf-8"))
        with urlopen(f"http://{host}:{port}/", timeout=2) as response:
            html = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.jobs.shutdown()

    assert digest["matched_count"] == 1
    assert digest["approvals"][0]["approval"]["game_name"] == "Tracked Game"
    assert snapshot["game_approvals"]["matched_count"] == 1
    assert snapshot["game_opportunity"]["available"] is True
    assert snapshot["game_opportunity_history"]["snapshots"] == []
    assert opportunity_history["symbol"] == "002602"
    assert snapshot["has_data"] is True
    assert {item["symbol"] for item in opportunities["companies"]} == {"002602", "002624"}
    assert "游戏机会雷达" in html
    assert "最新变化" in html
    assert "游戏版号" in html
    assert html.count('data-view-target=') == 5
    assert 'id="reportDisclosure"' in html
    assert '<details id="reportDisclosure"' in html
