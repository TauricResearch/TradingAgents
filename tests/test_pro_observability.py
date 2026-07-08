"""Structured logging, metrics registry, and LLM cost tracking."""

import json
import logging

import pytest

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.pro.observability import (
    CostTrackingLLM,
    JsonFormatter,
    MetricsRegistry,
    ModelPrice,
)
from tradingagents.pro.pipeline import run_pipeline


class TestJsonLogging:
    def test_format_is_valid_json_with_extras(self):
        record = logging.LogRecord("svc", logging.INFO, __file__, 1,
                                   "iteration complete", None, None)
        record.extra_fields = {"run_id": "r1", "action": "BUY"}
        entry = json.loads(JsonFormatter().format(record))
        assert entry["level"] == "INFO"
        assert entry["message"] == "iteration complete"
        assert entry["run_id"] == "r1" and entry["action"] == "BUY"


class TestMetricsRegistry:
    def test_counters_gauges_and_labels(self):
        metrics = MetricsRegistry()
        metrics.inc("runs_total")
        metrics.inc("runs_total")
        metrics.inc("rejections_total", stage="critic")
        metrics.set_gauge("equity", 100_500.0)

        assert metrics.counter("runs_total") == 2
        assert metrics.counter("rejections_total", stage="critic") == 1
        assert metrics.gauge("equity") == 100_500.0

    def test_prometheus_exposition(self):
        metrics = MetricsRegistry()
        metrics.inc("orders_filled_total", 3)
        metrics.set_gauge("llm_est_cost_usd", 0.42)
        text = metrics.render_prometheus()
        assert "orders_filled_total 3.0" in text
        assert "llm_est_cost_usd 0.42" in text


class TestCostTracking:
    def test_pipeline_run_is_fully_costed(self):
        metrics = MetricsRegistry()
        llm = CostTrackingLLM(FakePipelineLLM(), metrics=metrics)
        run_pipeline(llm, CONFIG, pipeline_snapshot())

        report = llm.report
        assert report.calls > 40  # ~59 agents + debate/critic/reflection/judge
        assert report.est_input_tokens > 0
        assert report.est_cost_usd > 0
        assert "EvidenceDraft" in report.by_schema
        assert "JudgeVerdict" in report.by_schema
        assert metrics.counter("llm_calls_total", schema="JudgeVerdict") == 1
        assert metrics.gauge("llm_est_cost_usd") == pytest.approx(
            report.est_cost_usd
        )

    def test_cost_math_known_value(self):
        class OneShot:
            def with_structured_output(self, schema):
                class R:
                    def invoke(self, prompt):
                        from tradingagents.pro.pipeline.schemas import CriticReport

                        return CriticReport(verdict="pass", issues=[])
                return R()

        llm = CostTrackingLLM(
            OneShot(), price=ModelPrice(input_per_mtok=4.0, output_per_mtok=20.0)
        )
        from tradingagents.pro.pipeline.schemas import CriticReport

        llm.with_structured_output(CriticReport).invoke("x" * 4000)  # 1000 tokens in
        report = llm.report
        assert report.est_input_tokens == 1000
        expected = (1000 * 4.0 + report.est_output_tokens * 20.0) / 1_000_000
        assert report.est_cost_usd == pytest.approx(expected)

    def test_stacks_with_caching_llm(self, tmp_path):
        from tradingagents.pro.backtest import CachingLLM

        tracked = CostTrackingLLM(FakePipelineLLM())
        cached = CachingLLM(tracked, mode="auto", path=tmp_path / "c.jsonl")
        run_pipeline(cached, CONFIG, pipeline_snapshot())
        first_calls = tracked.report.calls
        run_pipeline(cached, CONFIG, pipeline_snapshot())
        # cache absorbed the second run: no new inner (tracked) calls
        assert tracked.report.calls == first_calls
