from tradingagents.graph.setup import _compact_debate_node


class _SummaryLlm:
    def invoke(self, _prompt):
        return type("Response", (), {"content": "- Prior factual claim remains disputed."})()


def test_debate_wrapper_compacts_history_and_accumulates_public_facts():
    def node(_state):
        turns = []
        for label, body in (
            ("Bull Analyst", "Revenue growth was reported in a filing. " + "x" * 3_000),
            ("Bear Analyst", "Cash conversion weakened in the same filing. " + "y" * 3_000),
            ("Bull Analyst", "Order backlog remains visible in the report. " + "z" * 3_000),
            ("Bear Analyst", "Margin pressure remains an unresolved risk. " + "a" * 3_000),
        ):
            turns.append(f"{label}: {body}")
        return {"investment_debate_state": {"history": "\n".join(turns)}}

    wrapped = _compact_debate_node("Bull Researcher", node, _SummaryLlm())
    result = wrapped({"context_compaction_facts": ["Earlier public fact"]})

    assert "Recent debate turns" in result["investment_debate_state"]["history"]
    assert "Earlier public fact" in result["context_compaction_facts"]
    assert any("Revenue growth" in fact for fact in result["context_compaction_facts"])
