from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.news_advisor import analyze_news_coverage
from tradingagents.dataflows.news_layers import (
    DeepAnalysisCache,
    FileDeepAnalysisCache,
    build_layer1_batch,
    decide_layer2,
    layer0_filter,
    parse_layer1_sentiment,
)


def _items():
    return [
        {"id": "a", "title": "Company wins major order", "url": "https://example/a", "content": "A sufficiently detailed company announcement about a major order."},
        {"id": "b", "title": "Top 10 stocks to buy", "url": "https://example/b", "content": "A long list of stocks without a company-specific finding."},
        {"id": "c", "title": "Company wins major order", "url": "https://example/c", "content": "Duplicate title with enough content to be rejected as a duplicate."},
    ]


def test_layer0_filters_listicles_and_duplicates_before_layer1():
    decisions = layer0_filter(_items())
    assert [(item.item_id, item.accepted, item.reason) for item in decisions] == [
        ("a", True, "accepted"),
        ("b", False, "listicle"),
        ("c", False, "duplicate_title"),
    ]

    batch = build_layer1_batch(_items(), decisions)
    assert batch.item_ids == ("a",)
    assert '"i":"a"' in batch.payload
    assert '"i":"b"' not in batch.payload


def test_layer1_requires_compact_known_ids_and_has_safe_unknown_fallback():
    batch = build_layer1_batch(_items(), layer0_filter(_items()))
    result = parse_layer1_sentiment('[{"i":"a","s":"+","c":0.8},{"i":"unknown","s":"-"}]', batch)
    assert [(item.item_id, item.sentiment, item.confidence) for item in result] == [("a", "+", 0.8)]


def test_news_advisor_applies_layer0_before_any_model_invocation():
    class RecordingModel:
        prompt = ""

        def invoke(self, prompt):
            self.prompt = prompt
            return '{"should_enrich":false,"gaps":[],"reasoning":"covered","queries":[]}'

    model = RecordingModel()
    result = analyze_news_coverage(_items(), {"name": "Company", "ticker": "000001.SZ"}, model)
    assert result.should_enrich is False
    assert "Company wins major order" in model.prompt
    assert "Top 10 stocks to buy" not in model.prompt


def test_layer2_only_triggers_for_explicit_evidence_or_disagreement_conditions_and_caches_public_result():
    assert decide_layer2(evidence_status="verified").should_run is False
    trigger = decide_layer2(
        evidence_status="insufficient",
        source_alignment="Wide divergence",
        conflict_count=1,
        conflict_severity="high",
        subject="002396.SZ",
        data_as_of="2026-07-23",
    )
    assert trigger.should_run is True
    assert trigger.reasons == ("evidence_thin", "source_divergence", "material_conflict")
    assert trigger.cache_key is not None
    cache = DeepAnalysisCache()
    cache.put(trigger.cache_key, {"conclusion": "Need official filing", "reasoning": "private", "thinking": "private"})
    assert cache.get(trigger.cache_key) == {"conclusion": "Need official filing"}


def test_durable_layer2_cache_rejects_private_fields_recursively(tmp_path):
    key = "a" * 64
    cache = FileDeepAnalysisCache(tmp_path)
    cache.put(
        key,
        {
            "conclusion": "Need official filing",
            "nested": {"reasoning": "private", "safe": "retained"},
            "prompt": "private",
        },
    )
    assert cache.get(key) == {"conclusion": "Need official filing", "nested": {"safe": "retained"}}
    cache_text = (tmp_path / f"{key}.json").read_text(encoding="utf-8")
    assert "private" not in cache_text


def test_layered_runtime_is_opt_in_and_caches_only_public_conclusion(tmp_path):
    class LayeredModel:
        calls: list[str]

        def __init__(self):
            self.calls = []

        def invoke(self, prompt):
            self.calls.append(prompt)
            if "Classify the market sentiment" in prompt:
                return '[{"i":"a","s":"+","c":0.9},{"i":"d","s":"-","c":0.9}]'
            if "This deeper review was requested" in prompt:
                return (
                    '{"conclusion":"Mixed signals; check filings",'
                    '"evidence_gaps":["official filing"],'
                    '"material_risks":["guidance"],'
                    '"source_ids":["a","d"],'
                    '"reasoning":"private","prompt":"private"}'
                )
            return '{"should_enrich":true,"gaps":["missing earnings"],"reasoning":"public","queries":[]}'

    items = [
        {"id": "a", "title": "Company wins major order", "content": "Detailed public order announcement with financial implications."},
        {"id": "d", "title": "Company faces demand concern", "content": "Detailed public report describing an adverse demand trend."},
    ]
    model = LayeredModel()

    # The default is deliberately provider/cost safe: only the existing
    # advisor call is allowed when the two runtime layers are not enabled.
    result = analyze_news_coverage(items, {"name": "Company", "ticker": "000001.SZ"}, model)
    assert len(model.calls) == 1
    assert result.layer1_sentiment == []
    assert result.layer2_conclusion is None

    set_config({
        "news_layer1_enabled": True,
        "news_layer2_enabled": True,
        "news_layer2_cache_dir": str(tmp_path),
    })
    result = analyze_news_coverage(items, {"name": "Company", "ticker": "000001.SZ"}, model)
    assert len(model.calls) == 4
    assert [item.sentiment for item in result.layer1_sentiment] == ["+", "-"]
    assert result.layer2_trigger is not None and result.layer2_trigger.should_run
    assert result.layer2_conclusion == {
        "conclusion": "Mixed signals; check filings",
        "evidence_gaps": ["official filing"],
        "material_risks": ["guidance"],
        "source_ids": ["a", "d"],
    }

    # Same public inputs use the local content-addressed entry; the Layer 2
    # model call is skipped and no private fields can arrive from cache.
    cached = analyze_news_coverage(items, {"name": "Company", "ticker": "000001.SZ"}, model)
    assert len(model.calls) == 6
    assert cached.layer2_conclusion == result.layer2_conclusion
