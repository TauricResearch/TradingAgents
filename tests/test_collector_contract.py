"""Compatibility boundaries for collected global-event evidence."""

from copy import deepcopy
from inspect import signature
from urllib.parse import parse_qs, urlparse

import pytest

from tradingagents import collector_contract
from tradingagents.collector_contract import (
    COLLECTOR_COMPATIBILITY_PRECEDENCE,
    DISCOVERY_POLICY,
    collection_protocol_manifest,
    collector_semantics_manifest,
    discovery_policy_manifest,
    validated_collector_identity_history,
    x_daily_cycle_shape,
)
from tradingagents.dataflows import media_sources
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
    GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY,
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
    GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES,
    GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY,
    GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES,
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    GLOBAL_EVENT_V2_PROTOCOL_MANIFEST,
    canonical_json,
    content_id,
    experiment_protocol_manifest,
)


@pytest.mark.unit
def test_protocol_canonical_json_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


@pytest.mark.unit
def test_collection_and_wire_contracts_change_independently():
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    collection = collection_protocol_manifest(evidence)
    semantics = collector_semantics_manifest(evidence)
    assert set(semantics) == {
        "schema_version",
        "normalization",
        "receipts",
        "wire_formats",
    }

    changed_request = deepcopy(evidence)
    changed_request["broad_news_queries"] = {"world": ["different query"]}
    assert collection_protocol_manifest(changed_request) != collection
    assert collector_semantics_manifest(changed_request) == semantics

    reworded_explanation = deepcopy(evidence)
    reworded_explanation["query_cycle"]["provider_response_validation"][
        "topnews_empty"
    ] = "same policy explained differently"
    reworded_explanation["company_authored_material"] = (
        "company-authored evidence remains excluded"
    )
    reworded_explanation["fetch_receipt_evidence_lineage"]["evidence_id"] = (
        "same evidence identity explained differently"
    )
    assert collection_protocol_manifest(reworded_explanation) == collection
    assert collector_semantics_manifest(reworded_explanation) == semantics

    changed_wire = deepcopy(evidence)
    changed_wire["query_cycle"]["provider_response_validation"][
        "transient_http_statuses"
    ] = [408, 425, 429, "500-599"]
    assert collection_protocol_manifest(changed_wire) == collection
    assert collector_semantics_manifest(changed_wire) != semantics


@pytest.mark.unit
def test_global_x_adapter_requests_are_projected_from_one_immutable_policy(
    monkeypatch,
):
    x_contract = collection_protocol_manifest(GLOBAL_EVENT_V2_PROTOCOL["evidence"])[
        "x"
    ]
    policy = x_contract["adapter_policy"]
    assert policy == media_sources.global_x_adapter_policy_manifest()
    with pytest.raises(TypeError):
        media_sources.GLOBAL_X_ADAPTER_POLICY["recent_search"]["result_limit"][
            "maximum"
        ] = 1

    search = policy["recent_search"]
    trends = policy["trends"]
    assert signature(media_sources.fetch_x_topic).parameters["limit"].default == (
        search["result_limit"]["default"]
    )
    assert signature(media_sources.fetch_x_trends).parameters["limit"].default == (
        trends["result_limit"]["default"]
    )

    urls = []

    def response(url, _headers, _timeout):
        urls.append(url)
        if "/trends/" in url:
            return {"data": [{"trend_name": "event", "tweet_count": 1}]}
        return {"meta": {"result_count": 0}}

    monkeypatch.setenv("X_BEARER_TOKEN", "test-token")
    monkeypatch.setattr(media_sources, "_get_json", response)

    for limit in (
        search["result_limit"]["minimum"] - 1,
        search["result_limit"]["maximum"] + 1,
    ):
        media_sources.fetch_x_topic("trend_world", "global event", 1.0, limit=limit)
    for limit in (
        trends["result_limit"]["minimum"] - 1,
        trends["result_limit"]["maximum"] + 1,
    ):
        media_sources.fetch_x_trends(1, limit=limit)

    assert all(
        url.split("?", 1)[0] == search["endpoint"].split("?", 1)[0]
        for url in urls[:2]
    )
    expected_trend_endpoint = trends["endpoint"].format(woeid=1, qs="").split(
        "?", 1
    )[0]
    assert all(url.split("?", 1)[0] == expected_trend_endpoint for url in urls[2:])
    search_params = [parse_qs(urlparse(url).query) for url in urls[:2]]
    expected_query = " ".join((
        "(global event)",
        f"lang:{search['query_language']}",
        *(f"-is:{value}" for value in search["query_exclusions"]),
    ))
    expected_search_params = {
        "query": [expected_query],
        "sort_order": [search["topic_sort_order"]],
        search["fields_parameter"]: [",".join(search["post_fields"])],
        "expansions": [",".join(search["expansions"])],
        "user.fields": [",".join(search["user_fields"])],
    }
    assert [params.pop("max_results") for params in search_params] == [
        [str(search["result_limit"]["minimum"])],
        [str(search["result_limit"]["maximum"])],
    ]
    assert search_params == [expected_search_params, expected_search_params]

    trend_params = [parse_qs(urlparse(url).query) for url in urls[2:]]
    assert [params.pop("max_trends") for params in trend_params] == [
        [str(trends["result_limit"]["minimum"])],
        [str(trends["result_limit"]["maximum"])],
    ]
    expected_trend_params = {"trend.fields": [",".join(trends["fields"])]}
    assert trend_params == [expected_trend_params, expected_trend_params]

    risk_policy = search["automation_risk"]
    user = {
        "username": "publicvoice",
        "created_at": "1970-01-02T00:00:00Z",
        "public_metrics": dict.fromkeys(
            search["required_user_metrics"].values(), 20
        ),
    }
    now = 10 * 86_400.0
    assert media_sources._automation_risk(user, now) == risk_policy[
        "young_account_weight"
    ]
    changed_policy = media_sources.global_x_adapter_policy_manifest()
    changed_weight = risk_policy["young_account_weight"] / 2
    changed_policy["recent_search"]["automation_risk"][
        "young_account_weight"
    ] = changed_weight
    monkeypatch.setattr(media_sources, "GLOBAL_X_ADAPTER_POLICY", changed_policy)
    assert media_sources._automation_risk(user, now) == changed_weight
    changed_manifest = collection_protocol_manifest(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    )
    assert changed_manifest["x"]["adapter_policy"] == changed_policy
    assert content_id(changed_manifest, prefix="protocol_") != (
        GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID
    )


@pytest.mark.unit
def test_discovery_policy_is_immutable_complete_and_identity_bound(monkeypatch):
    policy = discovery_policy_manifest()
    assert set(policy) == {
        "version",
        "inputs",
        "normalization",
        "story_grouping",
        "trend_matching",
        "query",
        "ranking",
        "allocation",
        "audit_record",
    }
    assert set(policy["normalization"]) == {
        "publisher_suffix_pattern",
        "word_pattern",
        "case",
        "stopwords",
        "semantic_min_chars",
        "semantic_short_allowlist",
        "semantic_prefix_aliases",
        "semantic_exact_aliases",
        "plural_suffix",
        "plural_min_chars",
    }
    assert set(policy["story_grouping"]) == {
        "primary_jaccard_min",
        "secondary_overlap_min",
        "secondary_jaccard_min",
        "resolution",
    }
    assert set(policy["trend_matching"]) == {
        "leading_chars_to_strip",
        "meaningful_min_chars",
        "single_term_required_overlap",
        "multiple_term_required_overlap",
    }
    assert set(policy["query"]) == {
        "token_pattern",
        "generic_capitalized_terms",
        "capitalization",
        "distinctive_token",
        "long_run_min_words",
        "long_run_word_cap",
        "phrase_word_cap",
        "qualified_phrase_min_words",
        "anchor_order",
        "anchor_cap",
        "signal_min_chars",
        "query_part_cap",
        "fallback_signal_cap",
        "phrase_quote",
        "max_query_chars",
    }
    assert set(policy["ranking"]) == {
        "default_category",
        "default_region",
        "missing_created_utc",
        "missing_rank",
        "score_base",
        "score_rank_cap",
        "score_rank_weight",
        "cross_feed_weight",
        "cross_region_weight",
        "cross_source_baseline_count",
        "trend_match_weight",
        "category_missing_rank",
        "category_rank_weight",
        "lineage_fields",
    }
    assert set(policy["allocation"]) == {
        "topic_prefix",
        "representation_order",
        "category_candidate_order",
        "remaining_candidate_order",
        "fallback_category_order",
        "search_request_grouping",
        "search_request_order",
    }
    assert set(policy["audit_record"]) == {
        "version",
        "headline_fields",
        "headline_metadata_fields",
        "trend_fields",
        "selected_topic_fields",
    }
    with pytest.raises(TypeError):
        DISCOVERY_POLICY["ranking"]["trend_match_weight"] = 31

    baseline = collection_protocol_manifest(GLOBAL_EVENT_V2_PROTOCOL["evidence"])
    changed_policy = deepcopy(policy)
    changed_policy["ranking"]["trend_match_weight"] = 31
    monkeypatch.setattr(collector_contract, "DISCOVERY_POLICY", changed_policy)
    changed = collection_protocol_manifest(GLOBAL_EVENT_V2_PROTOCOL["evidence"])
    changed_collection_id = content_id(changed, prefix="protocol_")

    assert changed != baseline
    assert changed_collection_id != GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID
    changed_full_id = content_id(
        experiment_protocol_manifest(
            GLOBAL_EVENT_V2_PROTOCOL,
            collection_protocol_id=changed_collection_id,
            collector_semantics_id=GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
            collector_identity_history=GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY,
        ),
        prefix="protocol_",
    )
    assert changed_full_id != GLOBAL_EVENT_V2_PROTOCOL_ID


@pytest.mark.unit
def test_identity_history_is_append_only_current_pinned_and_immutable():
    entries = [
        dict(identity) for identity in GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY
    ]
    current = (
        GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
        GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
    )
    shape = x_daily_cycle_shape(GLOBAL_EVENT_V2_PROTOCOL["evidence"])
    assert validated_collector_identity_history(
        entries,
        current_identity=current,
        current_x_daily_cycle_shape=shape,
    ) == tuple(
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY
    )
    assert (
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[:-1]
        == GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES
    )
    assert (
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[-1]
        == GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY
    )
    assert tuple(
        reversed(GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES)
    ) == GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES
    with pytest.raises(TypeError):
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[0]["reason"] = "changed"
    with pytest.raises(TypeError):
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[0]["x_daily_static_slots"][0] = (
            "xtrend",
            "woeid:2",
        )

    with pytest.raises(ValueError, match="must be unique"):
        validated_collector_identity_history(
            entries[:-1] + [entries[0], entries[-1]],
            current_identity=current,
            current_x_daily_cycle_shape=shape,
        )
    with pytest.raises(ValueError, match="invalid shape"):
        validated_collector_identity_history(
            [{"protocol_id": entries[0]["protocol_id"]}],
            current_identity=current,
            current_x_daily_cycle_shape=shape,
        )
    with pytest.raises(ValueError, match="must append the derived current"):
        validated_collector_identity_history(
            entries[:-1],
            current_identity=current,
            current_x_daily_cycle_shape=shape,
        )

    next_current = {
        **entries[-1],
        "protocol_id": "protocol_" + "a" * 24,
        "collector_semantics_id": "collector_" + "b" * 24,
        "reason": "next collector contract",
    }
    advanced = validated_collector_identity_history(
        entries + [next_current],
        current_identity=(
            next_current["protocol_id"],
            next_current["collector_semantics_id"],
        ),
        current_x_daily_cycle_shape=shape,
    )
    assert advanced[:-1] == tuple(GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY)


@pytest.mark.unit
def test_identity_history_has_frozen_golden_pairs_and_x_cycle_shapes():
    assert [
        (entry["protocol_id"], entry["collector_semantics_id"])
        for entry in GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY
    ] == [
        ("protocol_7382464b4f6a755d767f2699", "collector_aec83e329b85d5bf8654b2eb"),
        ("protocol_485a418d45d44de9c0f45a94", "collector_cf5b90da1cd4d7db969389ee"),
        ("protocol_1b393c51cbc64acb34fa4014", "collector_fa2421d5a25636de4f035323"),
        ("protocol_b4c36948d856e9a82e7167bb", "collector_f6aaca9c1014887d9e78da82"),
        ("protocol_09b9f5ad4b015b24a553e7f4", "collector_5d8f7d2a7c92e52be419ad17"),
        ("protocol_79b64af05d79c66399d66385", "collector_c985ba5adc18bbcbc5f329f3"),
        ("protocol_b19d2d7e9a3bdc6bd398d66c", "collector_f4ed952ec4c96058c0e7d5a8"),
    ]
    assert {
        (
            entry["x_daily_static_slots"],
            entry["x_daily_max_dynamic_slots"],
        )
        for entry in GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY
    } == {
        (
            (
                ("xtrend", "woeid:1"),
                ("xtrend", "woeid:23424977"),
                ("trendnews", "ranked-global-discovery"),
            ),
            3,
        )
    }
    assert GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID == (
        "protocol_b19d2d7e9a3bdc6bd398d66c"
    )
    assert GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID == (
        "collector_f4ed952ec4c96058c0e7d5a8"
    )
    assert GLOBAL_EVENT_V2_PROTOCOL_ID == "protocol_099de6da8205322797ef1828"


@pytest.mark.unit
def test_full_protocol_hash_tracks_semantics_and_machine_compatibility_history():
    def identity(protocol, *, collection_id=GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
                 semantics_id=GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
                 history=GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY):
        return content_id(
            experiment_protocol_manifest(
                protocol,
                collection_protocol_id=collection_id,
                collector_semantics_id=semantics_id,
                collector_identity_history=history,
            ),
            prefix="protocol_",
        )

    assert identity(GLOBAL_EVENT_V2_PROTOCOL) == GLOBAL_EVENT_V2_PROTOCOL_ID
    assert GLOBAL_EVENT_V2_PROTOCOL_MANIFEST["collection_contract"] == {
        "collection_protocol_id": GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
        "collector_semantics_id": GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
        "compatible_identity_history": [
            {
                "protocol_id": entry["protocol_id"],
                "collector_semantics_id": entry["collector_semantics_id"],
                "x_daily_cycle": {
                    "expected_static_slots": entry["x_daily_static_slots"],
                    "max_dynamic_slots": entry["x_daily_max_dynamic_slots"],
                },
            }
            for entry in GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES
        ],
        "compatibility_precedence": COLLECTOR_COMPATIBILITY_PRECEDENCE,
    }

    compatibility_only = deepcopy(GLOBAL_EVENT_V2_PROTOCOL)
    compatibility_only["evidence"]["compatible_collector_identities"] = [{
        **dict(GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES[0]),
        "reason": "same readable evidence, revised operational explanation",
    }]
    compatibility_only["evidence"]["collection_protocol_id"] = "obsolete"
    compatibility_only["evidence"]["expected_collector_semantics_id"] = "obsolete"
    assert identity(compatibility_only) == GLOBAL_EVENT_V2_PROTOCOL_ID

    reworded_history = tuple(
        {**dict(entry), "reason": f"reworded note {index}"}
        for index, entry in enumerate(GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY)
    )
    assert identity(GLOBAL_EVENT_V2_PROTOCOL, history=reworded_history) == (
        GLOBAL_EVENT_V2_PROTOCOL_ID
    )

    reordered_history = (
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[1],
        GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[0],
        *GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[2:],
    )
    assert identity(GLOBAL_EVENT_V2_PROTOCOL, history=reordered_history) != (
        GLOBAL_EVENT_V2_PROTOCOL_ID
    )
    changed_pair = list(GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY)
    changed_pair[0] = {
        **dict(changed_pair[0]),
        "protocol_id": "protocol_" + "f" * 24,
    }
    assert identity(GLOBAL_EVENT_V2_PROTOCOL, history=tuple(changed_pair)) != (
        GLOBAL_EVENT_V2_PROTOCOL_ID
    )
    changed_shape = list(GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY)
    changed_shape[0] = {
        **dict(changed_shape[0]),
        "x_daily_max_dynamic_slots": 2,
    }
    assert identity(GLOBAL_EVENT_V2_PROTOCOL, history=tuple(changed_shape)) != (
        GLOBAL_EVENT_V2_PROTOCOL_ID
    )
    assert identity(
        GLOBAL_EVENT_V2_PROTOCOL,
        history=GLOBAL_EVENT_V2_COLLECTOR_IDENTITY_HISTORY[1:],
    ) != GLOBAL_EVENT_V2_PROTOCOL_ID
    added_history = (
        *GLOBAL_EVENT_V2_LEGACY_COLLECTOR_IDENTITIES,
        {
            **dict(GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY),
            "protocol_id": "protocol_" + "c" * 24,
            "collector_semantics_id": "collector_" + "d" * 24,
        },
        GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY,
    )
    assert identity(GLOBAL_EVENT_V2_PROTOCOL, history=added_history) != (
        GLOBAL_EVENT_V2_PROTOCOL_ID
    )

    changed_forecast = deepcopy(GLOBAL_EVENT_V2_PROTOCOL)
    changed_forecast["forecast"]["temperature"] = 0.25
    assert identity(changed_forecast) != GLOBAL_EVENT_V2_PROTOCOL_ID

    changed_portfolio = deepcopy(GLOBAL_EVENT_V2_PROTOCOL)
    changed_portfolio["portfolio"]["gross_limit"] = 0.5
    assert identity(changed_portfolio) != GLOBAL_EVENT_V2_PROTOCOL_ID

    assert identity(
        GLOBAL_EVENT_V2_PROTOCOL,
        semantics_id="collector_" + "0" * 24,
    ) != GLOBAL_EVENT_V2_PROTOCOL_ID
