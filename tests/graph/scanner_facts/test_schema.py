from tradingagents.graph.scanner_facts.schema import (
    NODE_TYPES,
    RELATION_TYPES,
    SCHEMA_VERSION,
    validate_graph_facts,
)

# ---- constants ----


def test_schema_version():
    assert SCHEMA_VERSION == "scanner_graph_facts.v1"


def test_node_types_complete():
    assert set(NODE_TYPES) == {
        "Ticker",
        "Sector",
        "Theme",
        "RiskFactor",
        "MarketIndex",
        "MacroIndicator",
        "Commodity",
        "CurrencyPair",
        "CryptoAsset",
    }


def test_relation_types_complete():
    assert set(RELATION_TYPES) == {
        "BELONGS_TO",
        "DRIVES_SENTIMENT",
        "EXPOSED_TO",
        "IMPACTS",
        "RELATED_TO",
        "HAS_CATALYST",
    }


# ---- validate_graph_facts: valid ----

_VALID_FACTS = {
    "schema_version": "scanner_graph_facts.v1",
    "scan_date": "2026-04-16",
    "run_id": "01KPBZ79XBDWWYSXVZF0APEYPW",
    "source_dir": "reports/daily/2026-04-16/01KPBZ79XBDWWYSXVZF0APEYPW/market",
    "global_regime": {
        "summary": "Risk-On regime.",
        "bullets": ["S&P 500 at new highs."],
        "source": "macro_scan_summary.json",
    },
    "nodes": [
        {
            "id": "ON",
            "type": "Ticker",
            "label": "ON",
            "aliases": ["ON Semiconductor"],
            "provenance": ["smart_money_summary.md#Candidate Rows"],
            "evidence": ["Breakout at $79.93"],
            "confidence": 0.95,
        },
        {
            "id": "Technology",
            "type": "Sector",
            "label": "Technology",
            "aliases": [],
            "provenance": ["smart_money_summary.md#Candidate Rows"],
            "evidence": [],
            "confidence": 0.90,
        },
    ],
    "edges": [
        {
            "source": "ON",
            "relation": "BELONGS_TO",
            "target": "Technology",
            "polarity": "",
            "provenance": "smart_money_summary.md#Candidate Rows",
            "evidence": "ON | Technology | Breakout ...",
            "confidence": 0.95,
        }
    ],
    "metadata": {
        "node_count": 2,
        "edge_count": 1,
        "generated_at": "2026-04-19T00:00:00Z",
        "inputs": ["smart_money_summary.md"],
    },
}


def test_valid_facts_returns_no_errors():
    errors = validate_graph_facts(_VALID_FACTS)
    assert errors == [], errors


# ---- validate_graph_facts: invalid cases ----


def test_missing_required_top_level_key():
    bad = dict(_VALID_FACTS)
    del bad["scan_date"]
    errors = validate_graph_facts(bad)
    assert any("scan_date" in e for e in errors)


def test_invalid_node_type():
    bad = dict(_VALID_FACTS)
    bad["nodes"] = [dict(_VALID_FACTS["nodes"][0], type="UnknownType")]
    errors = validate_graph_facts(bad)
    assert any("UnknownType" in e for e in errors)


def test_invalid_relation_type():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], relation="INVENTED")]
    errors = validate_graph_facts(bad)
    assert any("INVENTED" in e for e in errors)


def test_edge_missing_source_node():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], source="MISSING_TICKER")]
    errors = validate_graph_facts(bad)
    assert any("MISSING_TICKER" in e for e in errors)


def test_edge_missing_target_node():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], target="MISSING_SECTOR")]
    errors = validate_graph_facts(bad)
    assert any("MISSING_SECTOR" in e for e in errors)


def test_edge_missing_provenance():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], provenance="")]
    errors = validate_graph_facts(bad)
    assert any("provenance" in e for e in errors)


def test_edge_missing_evidence():
    bad = dict(_VALID_FACTS)
    bad["edges"] = [dict(_VALID_FACTS["edges"][0], evidence="")]
    errors = validate_graph_facts(bad)
    assert any("evidence" in e for e in errors)


def test_confidence_out_of_range():
    bad = dict(_VALID_FACTS)
    bad["nodes"] = [dict(_VALID_FACTS["nodes"][0], confidence=1.5)]
    errors = validate_graph_facts(bad)
    assert any("confidence" in e for e in errors)


def test_wrong_schema_version():
    bad = dict(_VALID_FACTS)
    bad["schema_version"] = "scanner_graph_facts.v0"
    errors = validate_graph_facts(bad)
    assert any("schema_version" in e for e in errors)
