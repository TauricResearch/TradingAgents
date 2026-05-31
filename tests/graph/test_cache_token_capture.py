"""P0 instrumentation tests: DeepSeek prompt-cache token capture + persistence.

Covers:
1. RunCostCallback accumulates prompt_cache_hit_tokens / prompt_cache_miss_tokens
   from response.llm_output['token_usage'] and exposes them per model.
2. store.record_cost persists the two new columns and they round-trip via the
   idempotent schema migration in db.py.
3. run_recorder.estimate_usd computes a non-zero usd_estimate for DeepSeek
   models (the F4 queue_jobs.cost_usd=$0.0000 root cause was a NULL usd_estimate).
"""

from __future__ import annotations

from langchain_core.outputs import LLMResult, ChatGeneration
from langchain_core.messages import AIMessage

from tradingagents.graph.cost_callback import RunCostCallback
from tradingagents.graph.run_recorder import estimate_usd
from tradingagents.persistence import db, store


def _llm_result(*, model, prompt, completion, cache_hit=None, cache_miss=None):
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cache_hit is not None:
        usage["prompt_cache_hit_tokens"] = cache_hit
    if cache_miss is not None:
        usage["prompt_cache_miss_tokens"] = cache_miss
    gen = ChatGeneration(message=AIMessage(content="ok"))
    return LLMResult(
        generations=[[gen]],
        llm_output={"model_name": model, "token_usage": usage},
    )


def test_callback_captures_cache_tokens():
    cb = RunCostCallback()
    cb.on_llm_end(
        _llm_result(
            model="deepseek-chat",
            prompt=1000,
            completion=200,
            cache_hit=768,
            cache_miss=232,
        )
    )
    totals = cb.totals_by_model()
    counts = totals["deepseek-chat"]
    assert counts["in_tokens"] == 1000
    assert counts["out_tokens"] == 200
    assert counts["cache_hit_tokens"] == 768
    assert counts["cache_miss_tokens"] == 232


def test_callback_defaults_cache_tokens_to_zero_when_absent():
    cb = RunCostCallback()
    cb.on_llm_end(_llm_result(model="gpt-4.1", prompt=500, completion=100))
    counts = cb.totals_by_model()["gpt-4.1"]
    assert counts["cache_hit_tokens"] == 0
    assert counts["cache_miss_tokens"] == 0


def test_callback_accumulates_across_calls():
    cb = RunCostCallback()
    for _ in range(2):
        cb.on_llm_end(
            _llm_result(
                model="deepseek-reasoner",
                prompt=100,
                completion=50,
                cache_hit=40,
                cache_miss=60,
            )
        )
    counts = cb.totals_by_model()["deepseek-reasoner"]
    assert counts["cache_hit_tokens"] == 80
    assert counts["cache_miss_tokens"] == 120


def test_record_cost_persists_cache_columns(tmp_path):
    conn = db.connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r1",
        ticker="AAPL",
        persona_id="p1",
        started_ts="2026-01-01T00:00:00+00:00",
        artifact_dir="runs/r1",
    )
    store.record_cost(
        conn,
        run_id="r1",
        provider="deepseek",
        model="deepseek-chat",
        in_tokens=1000,
        out_tokens=200,
        usd_estimate=0.001,
        cache_hit_tokens=768,
        cache_miss_tokens=232,
    )
    row = conn.execute(
        "SELECT cache_hit_tokens, cache_miss_tokens, usd_estimate FROM costs "
        "WHERE run_id = 'r1'"
    ).fetchone()
    assert row["cache_hit_tokens"] == 768
    assert row["cache_miss_tokens"] == 232
    assert row["usd_estimate"] == 0.001
    conn.close()


def test_record_cost_cache_columns_nullable(tmp_path):
    """Backward compat: omitting the new kwargs leaves them NULL."""
    conn = db.connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r2",
        ticker="MSFT",
        persona_id="p1",
        started_ts="2026-01-01T00:00:00+00:00",
        artifact_dir="runs/r2",
    )
    store.record_cost(
        conn,
        run_id="r2",
        provider="unknown",
        model="gpt-4.1",
        in_tokens=10,
        out_tokens=5,
    )
    row = conn.execute(
        "SELECT cache_hit_tokens, cache_miss_tokens FROM costs WHERE run_id = 'r2'"
    ).fetchone()
    assert row["cache_hit_tokens"] is None
    assert row["cache_miss_tokens"] is None
    conn.close()


def test_connect_migration_is_idempotent(tmp_path):
    """Re-connecting must not raise on the duplicate ALTER for cache columns."""
    p = str(tmp_path / "iic.db")
    db.connect(p).close()
    conn = db.connect(p)  # second pass replays the ALTERs
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(costs)")}
    assert "cache_hit_tokens" in cols
    assert "cache_miss_tokens" in cols
    conn.close()


def test_estimate_usd_nonzero_for_deepseek():
    # Root-cause regression: usd_estimate must be > 0 for DeepSeek so the
    # worker's SUM(costs.usd_estimate) no longer yields $0.0000.
    usd = estimate_usd(
        "deepseek-chat", in_tokens=10000, out_tokens=2000,
        cache_hit_tokens=0, cache_miss_tokens=10000,
    )
    assert usd is not None and usd > 0


def test_estimate_usd_uses_cache_hit_rate():
    full_miss = estimate_usd(
        "deepseek-chat", in_tokens=10000, out_tokens=0,
        cache_hit_tokens=0, cache_miss_tokens=10000,
    )
    all_hit = estimate_usd(
        "deepseek-chat", in_tokens=10000, out_tokens=0,
        cache_hit_tokens=10000, cache_miss_tokens=0,
    )
    # Cache hits are billed cheaper, so a fully-cached prompt costs less.
    assert all_hit < full_miss


def test_estimate_usd_none_for_unknown_model():
    assert estimate_usd("gpt-4.1", in_tokens=100, out_tokens=100) is None
