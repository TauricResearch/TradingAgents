"""Tests for backtest scoring, the scorecard, price loading and pricing."""

import json

import pandas as pd
import pytest

from tradingagents.backtest.prices import benchmark_for, load_prices
from tradingagents.backtest.pricing import estimate_cost, load_price_table
from tradingagents.backtest.report import (
    DISCLAIMER,
    render_markdown,
    score,
    write_report,
)
from tradingagents.backtest.store import DecisionRecord, DecisionStore

SIG = "analysts=market|deep=gpt-5.6"


def frame(n=40, drift=1.0):
    dates = pd.bdate_range("2026-01-05", periods=n)
    prices = [100.0 * (drift**i) for i in range(n)]
    return pd.DataFrame({"Open": prices, "Close": prices}, index=dates)


def seeded_store(tmp_path, ratings=None, **kwargs):
    ratings = ratings or ["Buy", "Hold", "Sell", "Buy"]
    store = DecisionStore(tmp_path / "decisions.jsonl")
    for offset, rating in enumerate(ratings):
        date = pd.bdate_range("2026-01-05", periods=len(ratings) * 5)[offset * 5]
        store.append(DecisionRecord(
            ticker="NVDA", date=date.strftime("%Y-%m-%d"), signature=SIG,
            rating=rating, decision=f"Rating: {rating}",
            tokens_in=1000, tokens_out=200, llm_calls=3, **kwargs,
        ))
    return store


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------

def test_score_produces_the_full_payload(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(store, {"NVDA": frame()}, signature=SIG, benchmark="SPY")

    assert payload["coverage"]["n_decisions"] == 4
    assert payload["coverage"]["tickers"] == ["NVDA"]
    assert payload["performance"]["total_return"] is not None
    assert payload["disclaimer"] == DISCLAIMER


def test_alpha_is_measured_against_the_benchmark_curve(tmp_path):
    store = seeded_store(tmp_path, ratings=["Buy"])
    rising = frame(drift=1.01)
    flat = frame(drift=1.0)

    payload = score(
        store, {"NVDA": rising}, signature=SIG,
        benchmark="SPY", benchmark_prices=flat,
    )

    assert payload["benchmark"]["total_return"] == pytest.approx(0.0, abs=1e-9)
    assert payload["alpha"] == pytest.approx(payload["performance"]["total_return"])


def test_review_decisions_are_counted_separately(tmp_path):
    store = seeded_store(tmp_path, ratings=["Buy", "REVIEW", "REVIEW", "Hold"])
    payload = score(store, {"NVDA": frame()}, signature=SIG)

    assert payload["coverage"]["n_review"] == 2
    assert payload["coverage"]["rating_mix"]["REVIEW"] == 2


def test_failed_decisions_appear_in_coverage(tmp_path):
    store = seeded_store(tmp_path)
    store.append(DecisionRecord(
        ticker="NVDA", date="2026-03-02", signature=SIG, rating=None, error="boom"
    ))

    payload = score(store, {"NVDA": frame()}, signature=SIG)

    assert payload["coverage"]["n_failed"] == 1
    assert payload["coverage"]["n_decisions"] == 4


def test_cost_totals_are_summed(tmp_path):
    store = seeded_store(tmp_path, cost_usd=0.25)
    payload = score(store, {"NVDA": frame()}, signature=SIG)

    assert payload["cost"]["tokens_in"] == 4000
    assert payload["cost"]["total_usd"] == pytest.approx(1.0)
    assert payload["cost"]["unpriced_decisions"] == 0


def test_unpriced_decisions_report_tokens_without_dollars(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(store, {"NVDA": frame()}, signature=SIG)

    assert payload["cost"]["total_usd"] is None
    assert payload["cost"]["unpriced_decisions"] == 4
    assert payload["cost"]["cost_per_alpha_point"] is None


def test_alpha_per_1k_is_computed_when_both_are_known(tmp_path):
    store = seeded_store(tmp_path, ratings=["Buy"], cost_usd=0.5)
    payload = score(
        store, {"NVDA": frame(drift=1.01)}, signature=SIG,
        benchmark="SPY", benchmark_prices=frame(drift=1.0),
    )

    assert payload["cost"]["cost_per_alpha_point"] is not None


def test_random_baseline_is_reported_for_a_single_ticker(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(
        store, {"NVDA": frame()}, signature=SIG, n_baseline_trials=10
    )

    assert payload["random_baseline"] is not None
    assert payload["random_baseline"]["n_trials"] == 10


def test_random_baseline_is_omitted_for_a_multi_ticker_run(tmp_path):
    """Shuffling across sleeves would not mean what the name implies."""
    store = seeded_store(tmp_path)
    store.append(DecisionRecord(
        ticker="AAPL", date="2026-01-05", signature=SIG, rating="Buy"
    ))

    payload = score(
        store, {"NVDA": frame(), "AAPL": frame()}, signature=SIG, n_baseline_trials=5
    )

    assert payload["random_baseline"] is None
    assert set(payload["per_ticker"]) == {"AAPL", "NVDA"}


def test_signature_filters_the_scored_decisions(tmp_path):
    store = seeded_store(tmp_path)
    store.append(DecisionRecord(
        ticker="NVDA", date="2026-01-05", signature="other", rating="Sell"
    ))

    payload = score(store, {"NVDA": frame()}, signature=SIG)

    assert payload["coverage"]["n_decisions"] == 4


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def test_markdown_leads_with_the_disclaimer(tmp_path):
    store = seeded_store(tmp_path)
    markdown = render_markdown(score(store, {"NVDA": frame()}, signature=SIG))

    assert markdown.startswith("# Backtest scorecard")
    assert DISCLAIMER in markdown


def test_markdown_shows_the_baselines_next_to_the_result(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(
        store, {"NVDA": frame()}, signature=SIG,
        benchmark="SPY", benchmark_prices=frame(), n_baseline_trials=10,
    )
    markdown = render_markdown(payload)

    assert "Against the baselines" in markdown
    assert "Buy and hold SPY" in markdown
    assert "random sequences drawn from their own rating mix" in markdown


def test_markdown_records_the_execution_rules(tmp_path):
    """The rules that produced the numbers must travel with them."""
    store = seeded_store(tmp_path)
    markdown = render_markdown(score(store, {"NVDA": frame()}, signature=SIG))

    assert "next bar's open after the decision date" in markdown
    assert "long only" in markdown
    assert "bp commission" in markdown


def test_markdown_flags_unpriced_spend(tmp_path):
    store = seeded_store(tmp_path)
    markdown = render_markdown(score(store, {"NVDA": frame()}, signature=SIG))

    assert "unpriced" in markdown
    assert "TRADINGAGENTS_LLM_PRICES" in markdown


def test_markdown_caveats_annualizing_a_short_window(tmp_path):
    """A two-month run must not present its annualized figure as a rate."""
    store = seeded_store(tmp_path)
    markdown = render_markdown(score(store, {"NVDA": frame(n=40)}, signature=SIG))

    assert "extrapolate from" in markdown
    assert "not as an expected rate" in markdown


def test_markdown_omits_the_caveat_for_a_long_window(tmp_path):
    store = seeded_store(tmp_path)
    markdown = render_markdown(score(store, {"NVDA": frame(n=300)}, signature=SIG))

    assert "not as an expected rate" not in markdown


def test_markdown_calls_spend_an_upper_bound(tmp_path):
    store = seeded_store(tmp_path, cost_usd=0.25)
    markdown = render_markdown(score(store, {"NVDA": frame()}, signature=SIG))

    assert "upper bound" in markdown


def test_markdown_handles_a_run_with_no_directional_calls(tmp_path):
    store = seeded_store(tmp_path, ratings=["Hold", "Hold"])
    markdown = render_markdown(score(store, {"NVDA": frame()}, signature=SIG))

    assert "no directional call had a full forward window" in markdown


def test_markdown_lists_per_ticker_rows_for_a_multi_ticker_run(tmp_path):
    store = seeded_store(tmp_path)
    store.append(DecisionRecord(
        ticker="AAPL", date="2026-01-05", signature=SIG, rating="Buy"
    ))
    payload = score(store, {"NVDA": frame(), "AAPL": frame()}, signature=SIG)

    markdown = render_markdown(payload)

    assert "## Per ticker" in markdown
    assert "| AAPL |" in markdown


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_write_report_emits_all_three_artifacts(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(store, {"NVDA": frame()}, signature=SIG)

    path = write_report(payload, tmp_path / "out")

    assert path.name == "scorecard.md"
    assert (tmp_path / "out" / "scorecard.json").exists()
    assert (tmp_path / "out" / "equity.csv").exists()


def test_the_json_scorecard_is_serializable_and_excludes_private_keys(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(store, {"NVDA": frame()}, signature=SIG)
    write_report(payload, tmp_path / "out")

    loaded = json.loads((tmp_path / "out" / "scorecard.json").read_text(encoding="utf-8"))
    assert "_equity" not in loaded
    assert loaded["coverage"]["n_decisions"] == 4


def test_equity_csv_includes_the_benchmark_when_present(tmp_path):
    store = seeded_store(tmp_path)
    payload = score(
        store, {"NVDA": frame()}, signature=SIG,
        benchmark="SPY", benchmark_prices=frame(),
    )
    write_report(payload, tmp_path / "out")

    csv = pd.read_csv(tmp_path / "out" / "equity.csv", index_col=0)
    assert list(csv.columns) == ["equity", "benchmark"]


# ---------------------------------------------------------------------------
# Price loading
# ---------------------------------------------------------------------------

def test_load_prices_uses_the_injected_fetcher(tmp_path):
    calls = []

    def fetcher(ticker, start, end):
        calls.append((ticker, start, end))
        return frame()

    prices = load_prices(["NVDA"], "2026-01-05", "2026-02-05",
                         cache_dir=tmp_path / "prices", fetcher=fetcher)

    assert set(prices) == {"NVDA"}
    # The window extends past the last decision so positions can be marked.
    assert calls[0][2] > "2026-02-05"


def test_prices_are_cached_so_rescoring_needs_no_network(tmp_path):
    calls = []

    def fetcher(ticker, start, end):
        calls.append(ticker)
        return frame()

    cache = tmp_path / "prices"
    load_prices(["NVDA"], "2026-01-05", "2026-02-05", cache_dir=cache, fetcher=fetcher)
    load_prices(["NVDA"], "2026-01-05", "2026-02-05", cache_dir=cache, fetcher=fetcher)

    assert calls == ["NVDA"]


def test_a_failing_symbol_is_skipped_not_fatal(tmp_path):
    def fetcher(ticker, start, end):
        if ticker == "BAD":
            raise RuntimeError("delisted")
        return frame()

    prices = load_prices(["NVDA", "BAD"], "2026-01-05", "2026-02-05",
                         cache_dir=tmp_path / "p", fetcher=fetcher)

    assert set(prices) == {"NVDA"}


def test_an_empty_history_is_omitted(tmp_path):
    empty = pd.DataFrame({"Open": [], "Close": []}, index=pd.DatetimeIndex([]))
    prices = load_prices(["NVDA"], "2026-01-05", "2026-02-05",
                         cache_dir=tmp_path / "p", fetcher=lambda *a: empty)

    assert prices == {}


def test_benchmark_for_uses_the_first_ticker():
    config = {"benchmark_map": {"": "SPY", ".T": "^N225"}}

    assert benchmark_for(["NVDA"], config) == "SPY"
    assert benchmark_for(["7203.T"], config) == "^N225"
    assert benchmark_for([], config) == "SPY"


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_prices_come_from_config():
    table = load_price_table({"llm_prices": {"gpt-5.6": {"input": 1.0, "output": 2.0}}})

    assert table["gpt-5.6"]["output"] == 2.0


def test_prices_come_from_the_env_file(tmp_path, monkeypatch):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"glm-5.3": {"input": 0.5, "output": 1.5}}), encoding="utf-8")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PRICES", str(path))

    assert load_price_table({})["glm-5.3"]["input"] == 0.5


def test_inline_config_overrides_the_file(tmp_path, monkeypatch):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"m": {"input": 1.0, "output": 1.0}}), encoding="utf-8")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PRICES", str(path))

    table = load_price_table({"llm_prices": {"m": {"input": 9.0, "output": 9.0}}})

    assert table["m"]["input"] == 9.0


@pytest.mark.parametrize("payload", ["not json", '{"m": {"input": 1}}', '["list"]'])
def test_a_bad_price_file_costs_the_cost_column_not_the_run(tmp_path, monkeypatch, payload):
    path = tmp_path / "prices.json"
    path.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PRICES", str(path))

    assert load_price_table({}) == {}


def test_a_missing_price_file_is_ignored(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PRICES", "/nonexistent/prices.json")

    assert load_price_table({}) == {}


def test_estimate_cost_applies_the_rate():
    table = {"m": {"input": 2.0, "output": 10.0}}

    # 1M in at $2 plus 0.5M out at $10 = $7.
    assert estimate_cost(1_000_000, 500_000, ["m"], table) == pytest.approx(7.0)


def test_estimate_cost_uses_the_dearer_model_as_an_upper_bound():
    table = {"cheap": {"input": 1.0, "output": 1.0}, "dear": {"input": 5.0, "output": 5.0}}

    assert estimate_cost(1_000_000, 0, ["cheap", "dear"], table) == pytest.approx(5.0)


def test_estimate_cost_is_none_for_an_unpriced_model():
    assert estimate_cost(1000, 100, ["unknown"], {}) is None


def test_estimate_cost_prices_what_it_can():
    """One known model out of two is enough to report a bound."""
    table = {"known": {"input": 1.0, "output": 1.0}}

    assert estimate_cost(1_000_000, 0, ["known", "unknown"], table) == pytest.approx(1.0)
