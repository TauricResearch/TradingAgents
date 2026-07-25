from tradingagents.observability.graph_tasks import _record_context_compaction_if_present


class _Observer:
    def __init__(self):
        self.calls = []

    def record_scratchpad(self, **kwargs):
        self.calls.append(kwargs)


def test_context_compaction_emits_only_safe_counted_scratchpad_marker():
    observer = _Observer()

    _record_context_compaction_if_present(
        observer,
        {"context_compaction_facts": ["prior fact"]},
        {"context_compaction_facts": ["prior fact", "new fact"]},
    )

    assert observer.calls == [
        {
            "event_type": "compaction",
            "detail_code": "public_debate_context_compacted",
            "arguments": {"previous_fact_count": 1},
            "result": {"public_fact_count": 2},
            "metadata": {"new_fact_count": 1},
        }
    ]


def test_unchanged_or_missing_context_facts_do_not_emit_a_marker():
    observer = _Observer()

    _record_context_compaction_if_present(observer, {}, {})
    _record_context_compaction_if_present(
        observer,
        {"context_compaction_facts": ["fact"]},
        {"context_compaction_facts": ["fact"]},
    )

    assert observer.calls == []
