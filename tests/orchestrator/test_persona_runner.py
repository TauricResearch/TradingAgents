import pytest


@pytest.mark.unit
def test_run_personas_parallel_returns_one_run_id_per_persona(monkeypatch):
    from tradingagents.secretary.persona_runner import run_personas_parallel
    from tradingagents.personas.loader import (
        Persona, LLMSettings, AnalystSettings, RiskDebateSettings,
    )

    def make_p(pid):
        return Persona(
            id=pid, name=pid, description="",
            system_prompt_fragment="frag",
            llm=LLMSettings(deep_think_llm="dt", quick_think_llm="qt"),
            analysts=AnalystSettings(include=["market"], exclude=[]),
            risk_debate=RiskDebateSettings(),
        )
    personas = [make_p("macro"), make_p("value"), make_p("momentum")]

    fake_run_ids = iter(["r1", "r2", "r3"])

    def fake_run_one(persona, ticker, trade_date, config,
                     event_context=None, queue_job_id=None):
        return next(fake_run_ids)

    monkeypatch.setattr(
        "tradingagents.secretary.persona_runner._run_one_persona",
        fake_run_one,
    )
    run_ids = run_personas_parallel(
        personas=personas, ticker="AAPL", trade_date="2026-05-27",
        config={"deep_think_llm": "x"}, parallel=True,
    )
    assert sorted(run_ids) == ["r1", "r2", "r3"]


@pytest.mark.unit
def test_run_personas_parallel_threads_event_context_and_job_id(monkeypatch):
    from tradingagents.secretary.persona_runner import run_personas_parallel
    from tradingagents.personas.loader import (
        Persona, LLMSettings, AnalystSettings, RiskDebateSettings,
    )

    captured = []

    def fake_run_one(persona, ticker, trade_date, config,
                     event_context=None, queue_job_id=None):
        captured.append((persona.id, event_context, queue_job_id))
        return f"r-{persona.id}"

    monkeypatch.setattr(
        "tradingagents.secretary.persona_runner._run_one_persona",
        fake_run_one,
    )
    p = Persona(
        id="macro", name="m", description="",
        system_prompt_fragment="frag",
        llm=LLMSettings(deep_think_llm="dt", quick_think_llm="qt"),
        analysts=AnalystSettings(include=["market"], exclude=[]),
        risk_debate=RiskDebateSettings(),
    )
    run_personas_parallel(
        personas=[p], ticker="AAPL", trade_date="2026-05-27",
        config={}, parallel=False,
        event_context="Apple beats earnings.", queue_job_id=42,
    )
    assert captured == [("macro", "Apple beats earnings.", 42)]
