from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median

AB_SCHEMA_VERSION = "tradingagents.profile_ab.v1alpha1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare TradingAgents stage-profile traces for a minimal A/B workflow.",
    )
    parser.add_argument("--a", nargs="+", required=True, help="Trace file(s) or directories for cohort A")
    parser.add_argument("--b", nargs="+", required=True, help="Trace file(s) or directories for cohort B")
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--output", help="Optional path to write the comparison JSON")
    return parser


def _expand_inputs(items: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in items:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(candidate for candidate in path.glob("*.json") if candidate.is_file()))
        elif path.is_file():
            files.append(path)
    return files


def _load_trace(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"trace at {path} must be a JSON object")
    payload = dict(data)
    payload.setdefault("_source_path", str(path))
    return payload


def _phase_totals_ms(trace: dict) -> dict[str, int]:
    summary = trace.get("summary") or {}
    phase_totals = summary.get("phase_totals_seconds") or trace.get("phase_totals_seconds") or {}
    return {str(key): int(round(float(value) * 1000)) for key, value in phase_totals.items()}


def summarize_traces(traces: list[dict], label: str) -> dict:
    run_count = len(traces)
    ok_runs = [trace for trace in traces if trace.get("status") == "ok"]
    degraded_runs = [
        trace for trace in traces
        if ((trace.get("summary") or {}).get("final_research_status") not in (None, "full"))
    ]
    total_elapsed = [int((trace.get("summary") or {}).get("total_elapsed_ms", 0)) for trace in ok_runs]
    event_counts = [int((trace.get("summary") or {}).get("event_count", 0)) for trace in ok_runs]
    status_counts = Counter(str(trace.get("status") or "unknown") for trace in traces)
    schema_versions = sorted({str(trace.get("trace_schema_version") or "unknown") for trace in traces})
    source_files = sorted(str(trace.get("_source_path")) for trace in traces if trace.get("_source_path"))

    phase_values: dict[str, list[int]] = {}
    for trace in ok_runs:
        for phase, elapsed_ms in _phase_totals_ms(trace).items():
            phase_values.setdefault(phase, []).append(elapsed_ms)

    phase_medians = {phase: int(median(values)) for phase, values in sorted(phase_values.items()) if values}
    variants = sorted({str(trace.get("variant_label") or label) for trace in traces})
    return {
        "label": label,
        "run_count": run_count,
        "ok_count": len(ok_runs),
        "error_count": run_count - len(ok_runs),
        "degraded_run_count": len(degraded_runs),
        "variants": variants,
        "status_counts": dict(sorted(status_counts.items())),
        "trace_schema_versions": schema_versions,
        "source_files": source_files,
        "median_total_elapsed_ms": int(median(total_elapsed)) if total_elapsed else None,
        "median_event_count": int(median(event_counts)) if event_counts else None,
        "median_phase_elapsed_ms": phase_medians,
    }


def compare_summaries(summary_a: dict, summary_b: dict) -> dict:
    total_a = summary_a.get("median_total_elapsed_ms")
    total_b = summary_b.get("median_total_elapsed_ms")
    degraded_a = summary_a.get("degraded_run_count", 0)
    degraded_b = summary_b.get("degraded_run_count", 0)
    error_a = summary_a.get("error_count", 0)
    error_b = summary_b.get("error_count", 0)

    faster = None
    if total_a is not None and total_b is not None:
        if total_a < total_b:
            faster = summary_a["label"]
        elif total_b < total_a:
            faster = summary_b["label"]

    lower_degradation = None
    if degraded_a < degraded_b:
        lower_degradation = summary_a["label"]
    elif degraded_b < degraded_a:
        lower_degradation = summary_b["label"]

    lower_error_rate = None
    if error_a < error_b:
        lower_error_rate = summary_a["label"]
    elif error_b < error_a:
        lower_error_rate = summary_b["label"]

    recommended = None
    if faster == summary_a["label"] and lower_degradation in (None, summary_a["label"]) and lower_error_rate in (None, summary_a["label"]):
        recommended = summary_a["label"]
    elif faster == summary_b["label"] and lower_degradation in (None, summary_b["label"]) and lower_error_rate in (None, summary_b["label"]):
        recommended = summary_b["label"]
    elif lower_degradation == summary_a["label"] and total_a == total_b and lower_error_rate in (None, summary_a["label"]):
        recommended = summary_a["label"]
    elif lower_degradation == summary_b["label"] and total_a == total_b and lower_error_rate in (None, summary_b["label"]):
        recommended = summary_b["label"]

    return {
        "faster_label": faster,
        "lower_degradation_label": lower_degradation,
        "lower_error_rate_label": lower_error_rate,
        "recommended_label": recommended,
    }


def build_comparison(traces_a: list[dict], traces_b: list[dict], *, label_a: str, label_b: str) -> dict:
    summary_a = summarize_traces(traces_a, label_a)
    summary_b = summarize_traces(traces_b, label_b)
    return {
        "schema_version": AB_SCHEMA_VERSION,
        "cohorts": {
            label_a: summary_a,
            label_b: summary_b,
        },
        "comparison": compare_summaries(summary_a, summary_b),
    }


def main() -> None:
    args = build_parser().parse_args()
    files_a = _expand_inputs(args.a)
    files_b = _expand_inputs(args.b)
    if not files_a:
        raise SystemExit("no trace files found for cohort A")
    if not files_b:
        raise SystemExit("no trace files found for cohort B")

    traces_a = [_load_trace(path) for path in files_a]
    traces_b = [_load_trace(path) for path in files_b]
    payload = build_comparison(traces_a, traces_b, label_a=args.label_a, label_b=args.label_b)

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered)
    print(rendered)


if __name__ == "__main__":
    main()
