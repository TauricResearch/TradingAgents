from tradingagents.agents.utils.report_quality import tag_report


def test_insufficient_evidence_marker_dominates_even_after_provenance():
    report = (
        "Source: Finviz Smart Money Scanner\n"
        "Scan Date: 2026-04-10\n\n"
        "[INSUFFICIENT_EVIDENCE]\n"
        "Node: smart_money_scanner\n"
        "Missing evidence: no successful tool results from required tools: "
        "get_insider_buying_stocks."
    )

    tagged = tag_report(report, node_name="smart_money_scanner")

    assert tagged.startswith("[QUALITY: empty | issues=insufficient_evidence_marker | evidence=0]")
