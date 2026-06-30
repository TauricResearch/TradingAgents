from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.evidence import EvidenceLedger, stable_json_hash


@pytest.mark.unit
def test_stable_json_hash_is_independent_of_dict_key_order():
    left = {
        "source": "market",
        "payload": {"close": 189.5, "volume": 123, "nested": {"b": 2, "a": 1}},
    }
    right = {
        "payload": {"nested": {"a": 1, "b": 2}, "volume": 123, "close": 189.5},
        "source": "market",
    }

    assert stable_json_hash(left) == stable_json_hash(right)


@pytest.mark.unit
def test_register_generates_stable_ids_from_content():
    first = EvidenceLedger()
    second = EvidenceLedger()

    first_item = first.register(
        source="market_data",
        title="NVDA daily close",
        as_of_date="2024-06-01",
        payload={"close": 189.5, "volume": 123},
    )
    second_item = second.register(
        source="market_data",
        title="NVDA daily close",
        as_of_date="2024-06-01",
        payload={"volume": 123, "close": 189.5},
    )

    assert first_item.evidence_id.startswith("EVD-")
    assert first_item.evidence_id == second_item.evidence_id


@pytest.mark.unit
def test_alias_resolution_and_has_support_ids_and_aliases():
    ledger = EvidenceLedger()
    item = ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["nvda-10k-2024", "latest-filing"],
        evidence_id="EVD-FILING-20240221",
    )

    assert ledger.resolve("EVD-FILING-20240221") == item.evidence_id
    assert ledger.resolve("nvda-10k-2024") == item.evidence_id
    assert ledger.resolve("latest-filing") == item.evidence_id
    assert ledger.resolve("missing") is None
    assert ledger.has("nvda-10k-2024") is True
    assert ledger.has("missing") is False


@pytest.mark.unit
def test_register_is_idempotent_for_same_id_and_identical_content():
    ledger = EvidenceLedger()
    first = ledger.register(
        source="market_data",
        title="NVDA daily close",
        as_of_date="2024-06-01",
        payload={"close": 189.5},
        aliases=["nvda-close"],
        evidence_id="EVD-MKT-20240601",
    )
    second = ledger.register(
        source="market_data",
        title="NVDA daily close",
        as_of_date="2024-06-01",
        payload={"close": 189.5},
        aliases=["nvda-close"],
        evidence_id="EVD-MKT-20240601",
    )

    assert second == first
    assert len(ledger.list_items()) == 1


@pytest.mark.unit
def test_register_rejects_same_id_with_different_content():
    ledger = EvidenceLedger()
    ledger.register(
        source="market_data",
        title="NVDA daily close",
        as_of_date="2024-06-01",
        payload={"close": 189.5},
        evidence_id="EVD-MKT-20240601",
    )

    with pytest.raises(ValueError, match="EVD-MKT-20240601"):
        ledger.register(
            source="market_data",
            title="NVDA revised close",
            as_of_date="2024-06-01",
            payload={"close": 190.0},
            evidence_id="EVD-MKT-20240601",
        )


@pytest.mark.unit
def test_register_rejects_alias_already_mapped_to_another_item():
    ledger = EvidenceLedger()
    ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["latest-filing"],
        evidence_id="EVD-FILING-20240221",
    )

    with pytest.raises(ValueError, match="latest-filing"):
        ledger.register(
            source="filing",
            title="MSFT 10-K",
            as_of_date="2024-07-30",
            payload={"form": "10-K"},
            aliases=["latest-filing"],
            evidence_id="EVD-FILING-20240730",
        )


@pytest.mark.unit
def test_register_rejects_evidence_id_that_is_existing_alias_for_another_item():
    ledger = EvidenceLedger()
    ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["EVD-SHARED-REF"],
        evidence_id="EVD-FILING-20240221",
    )

    with pytest.raises(ValueError, match="EVD-SHARED-REF"):
        ledger.register(
            source="news",
            title="Company update",
            as_of_date="2024-06-01",
            payload={"headline": "Guidance reaffirmed"},
            evidence_id="EVD-SHARED-REF",
        )


@pytest.mark.unit
def test_register_rejects_alias_that_is_existing_evidence_id_for_another_item():
    ledger = EvidenceLedger()
    ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        evidence_id="EVD-FILING-20240221",
    )

    with pytest.raises(ValueError, match="EVD-FILING-20240221"):
        ledger.register(
            source="news",
            title="Company update",
            as_of_date="2024-06-01",
            payload={"headline": "Guidance reaffirmed"},
            aliases=["EVD-FILING-20240221"],
            evidence_id="EVD-NEWS-20240601",
        )


@pytest.mark.unit
def test_register_idempotent_same_item_with_evd_alias_still_works():
    ledger = EvidenceLedger()
    first = ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["EVD-FILING-ALIAS"],
        evidence_id="EVD-FILING-20240221",
    )
    second = ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["EVD-FILING-ALIAS"],
        evidence_id="EVD-FILING-20240221",
    )

    assert second == first
    assert ledger.resolve("EVD-FILING-ALIAS") == "EVD-FILING-20240221"
    assert len(ledger.list_items()) == 1


@pytest.mark.unit
def test_mutating_registered_item_does_not_corrupt_ledger_indexes_or_snapshot():
    ledger = EvidenceLedger()
    item = ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["nvda-10k"],
        evidence_id="EVD-FILING-20240221",
    )

    item.evidence_id = "EVD-MUTATED"
    item.aliases.append("mutated-alias")
    item.payload["form"] = "MUTATED"

    [stored] = ledger.list_items()
    assert stored.evidence_id == "EVD-FILING-20240221"
    assert stored.aliases == ["nvda-10k"]
    assert stored.payload == {"form": "10-K"}
    assert ledger.resolve("nvda-10k") == "EVD-FILING-20240221"
    assert ledger.resolve("mutated-alias") is None


@pytest.mark.unit
def test_mutating_list_items_result_does_not_corrupt_ledger():
    ledger = EvidenceLedger()
    ledger.register(
        source="news",
        title="Company update",
        as_of_date="2024-06-01",
        payload={"headline": "Guidance reaffirmed"},
        aliases=["company-update"],
        evidence_id="EVD-NEWS-20240601",
    )

    [listed] = ledger.list_items()
    listed.aliases.clear()
    listed.payload["headline"] = "MUTATED"

    [stored] = ledger.list_items()
    assert stored.aliases == ["company-update"]
    assert stored.payload == {"headline": "Guidance reaffirmed"}
    assert ledger.resolve("company-update") == "EVD-NEWS-20240601"


@pytest.mark.unit
def test_stable_json_hash_supports_common_deterministic_output_types():
    value = {
        "as_datetime": datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc),
        "as_date": date(2024, 6, 1),
        "as_decimal": Decimal("189.50"),
        "as_path": Path("cache/NVDA.json"),
        "as_nan": float("nan"),
        "as_inf": float("inf"),
        "as_negative_inf": float("-inf"),
    }

    assert stable_json_hash(value) == stable_json_hash(dict(reversed(value.items())))


@pytest.mark.unit
def test_to_dict_normalizes_common_payload_types():
    ledger = EvidenceLedger()
    ledger.register(
        source="tool",
        title="Normalized payload",
        as_of_date="2024-06-01",
        payload={
            "reported_at": datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc),
            "filing_date": date(2024, 6, 1),
            "eps": Decimal("2.50"),
            "cache_path": Path("cache/NVDA.json"),
            "ratio": float("nan"),
            "upper": float("inf"),
            "lower": float("-inf"),
        },
        evidence_id="EVD-NORMALIZED",
    )

    payload = ledger.to_dict()["items"][0]["payload"]
    assert payload == {
        "reported_at": "2024-06-01T12:30:00+00:00",
        "filing_date": "2024-06-01",
        "eps": "2.50",
        "cache_path": "cache/NVDA.json",
        "ratio": "NaN",
        "upper": "Infinity",
        "lower": "-Infinity",
    }


@pytest.mark.unit
def test_ledger_serialization_round_trip_preserves_items_and_aliases():
    ledger = EvidenceLedger()
    original = ledger.register(
        source="news",
        title="Company update",
        as_of_date="2024-06-01",
        payload={"headline": "Guidance reaffirmed", "quality": "primary"},
        aliases=["company-update"],
        evidence_id="EVD-NEWS-20240601",
    )

    restored = EvidenceLedger.from_dict(ledger.to_dict())

    [restored_item] = restored.list_items()
    assert restored_item == original
    assert restored.resolve("company-update") == "EVD-NEWS-20240601"
    assert restored.has("EVD-NEWS-20240601") is True
