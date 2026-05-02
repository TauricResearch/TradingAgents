import json
from unittest.mock import MagicMock


def test_pm_decision_writes_snapshot_to_run_path(tmp_path, monkeypatch):
    """After pm_decision_node returns, snapshot exists with full decision JSON."""
    from tradingagents.agents.portfolio import pm_decision_agent as mod

    fake_decision_dict = {
        "macro_regime": "risk-on",
        "buys": [{"ticker": "ET", "shares": 100, "entry_price": 20.19}],
        "sells": [],
        "holds": [],
    }

    fake_model = MagicMock()
    fake_model.model_dump_json.return_value = json.dumps(fake_decision_dict)

    fake_chain = MagicMock()
    fake_chain.invoke.return_value = fake_model

    class _FakePrompt:
        def partial(self, **_kwargs):
            return self

        def __or__(self, _structured_llm):
            return fake_chain

    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = MagicMock()

    monkeypatch.setattr(
        mod,
        "ChatPromptTemplate",
        MagicMock(from_messages=MagicMock(return_value=_FakePrompt())),
    )

    node = mod.create_pm_decision_agent(fake_llm, config={"run_path": str(tmp_path)})
    state = {
        "analysis_date": "2026-05-01",
        "portfolio_data": json.dumps(
            {
                "portfolio": {"cash": 100000.0, "total_value": 100000.0},
                "holdings": [],
            }
        ),
        "macro_brief": "RISK-ON",
        "micro_brief": "ok",
        "prioritized_candidates": "[]",
    }

    result = node(state)

    snapshot_path = tmp_path / "portfolio_decision_snapshot.json"
    assert snapshot_path.exists(), f"snapshot not written; cwd has {list(tmp_path.iterdir())}"
    written = json.loads(snapshot_path.read_text())
    assert written == fake_decision_dict
    assert result["pm_decision"] == json.dumps(fake_decision_dict)


def test_pm_decision_writes_snapshot_via_state_run_id_fallback(tmp_path, monkeypatch):
    """When cfg has no run_path, the agent must derive one from state['run_id']
    and analysis_date via create_report_store(run_id=...) — this path is the
    direct/CLI graph run that PR-B1's acceptance gate covers.
    """
    from tradingagents.agents.portfolio import pm_decision_agent as mod
    from tradingagents.portfolio import store_factory as sf_module

    # Point ReportStore at a temp base_dir so we don't write to ./reports
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))

    fake_decision_dict = {
        "macro_regime": "risk-on",
        "buys": [],
        "sells": [],
        "holds": [],
    }
    fake_model = MagicMock()
    fake_model.model_dump_json.return_value = json.dumps(fake_decision_dict)
    fake_chain = MagicMock()
    fake_chain.invoke.return_value = fake_model

    class _FakePrompt:
        def partial(self, **_kwargs):
            return self

        def __or__(self, _structured_llm):
            return fake_chain

    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = MagicMock()
    monkeypatch.setattr(
        mod,
        "ChatPromptTemplate",
        MagicMock(from_messages=MagicMock(return_value=_FakePrompt())),
    )

    # No run_path in cfg — exercises the fallback code path.
    node = mod.create_pm_decision_agent(fake_llm, config={})
    state = {
        "analysis_date": "2026-05-01",
        "run_id": "test_run_abc",
        "portfolio_data": json.dumps(
            {"portfolio": {"cash": 100000.0, "total_value": 100000.0}, "holdings": []}
        ),
        "macro_brief": "",
        "micro_brief": "",
        "prioritized_candidates": "[]",
    }

    result = node(state)
    assert result["pm_decision"] == json.dumps(fake_decision_dict)

    # Snapshot lands under the run-scoped path: <base>/daily/<date>/<run_id>/portfolio/report/
    expected = (
        tmp_path
        / "daily"
        / "2026-05-01"
        / "test_run_abc"
        / "portfolio"
        / "report"
        / "portfolio_decision_snapshot.json"
    )
    assert expected.exists(), (
        f"snapshot not written via fallback; got: {list(tmp_path.rglob('*.json'))}"
    )
    assert json.loads(expected.read_text()) == fake_decision_dict

    # Sanity: importing the module path the agent uses must succeed
    assert hasattr(sf_module, "create_report_store")
