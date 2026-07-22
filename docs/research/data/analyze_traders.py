#!/usr/bin/env python3
"""Trader knowledge-base tooling: validate / export / mine.

Stdlib only — runs anywhere, no installs. The JSON is canonical; the CSV and
everything in derived/ are generated and never hand-edited.

Honesty rules enforced here (see 00_methodology.md §1, §6):
- null = "not disclosed" and is excluded from denominators, never coerced.
- "undisclosed" vocabulary values are reported as their own line.
- Percentages print only when N_disclosed >= MIN_N_FOR_PCT; else raw counts.
- Numeric summaries are median/quartiles over disclosed values only; no bare
  means. Disclosed vs inferred bases are split.
- Every aggregate is emitted twice: all tiers, and tiers A+B only.

Usage:
  python analyze_traders.py --validate [candidate.json ...]
  python analyze_traders.py --export-csv
  python analyze_traders.py --analyze
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRADERS_JSON = HERE / "traders.json"
TRADERS_CSV = HERE / "traders.csv"
VOCAB_JSON = HERE / "vocabularies.json"
DERIVED = HERE / "derived"

MIN_N_FOR_PCT = 10  # below this, raw counts only — no pseudo-precision
MIN_SUPPORT = 3     # co-occurrence pairs need at least this many rows

# profile path -> vocabulary name (lists handled by ITER paths)
VOCAB_FIELDS: dict[str, str] = {
    "cohort": "cohort",
    "status": "status",
    "verification.tier": "verification_tier",
    "style.primary": "style_primary",
    "style.discretion": "discretion",
    "style.typical_holding_period": "holding_period",
    "exit.initial_stop_basis": "stop_basis",
    "sizing.model": "sizing_model",
}
VOCAB_LIST_FIELDS: dict[str, str] = {
    "style.secondary": "style_primary",
    "style.markets": "markets",
    "style.timeframes": "timeframes",
    "entry.archetypes": "entry_archetype",
    "entry.confirmation": "entry_confirmation",
    "entry.filters": "entry_filter",
    "exit.profit_taking": "profit_taking",
}
SOURCED_VALUE_FIELDS = [
    "risk.risk_per_trade_pct",
    "risk.max_drawdown_rule",
    "risk.loss_limit",
    "risk.portfolio_heat_cap",
    "sizing.typical_leverage",
]
BOOL_FIELDS = [
    "exit.uses_trailing",
    "exit.scales_out",
    "exit.time_exit",
    "risk.pyramids",
    "risk.moves_to_breakeven",
]
REQUIRED_TOP = [
    "id", "name", "cohort", "status", "verification", "style", "entry",
    "exit", "risk", "sizing", "psychology_rules", "performance", "extraction",
]
# (section, required keys) — structural mirror of traders.schema.json
REQUIRED_KEYS = {
    "verification": ["tier", "tier_justification", "sources"],
    "style": ["primary", "discretion", "markets", "timeframes",
              "typical_holding_period"],
    "entry": ["archetypes", "trigger_summary", "confirmation", "filters"],
    "exit": ["initial_stop_basis", "uses_trailing", "profit_taking",
             "scales_out", "time_exit"],
    "risk": ["risk_per_trade_pct", "max_drawdown_rule", "loss_limit",
             "pyramids", "moves_to_breakeven", "portfolio_heat_cap"],
    "sizing": ["model"],
    "performance": ["claims"],
    "extraction": ["batch_id", "date", "qa_reviewed"],
}
# co-occurrence pairs mined by --analyze: (field_a, field_b) where list
# fields contribute each member
COOCCURRENCE_PAIRS = [
    ("entry.archetypes", "entry.filters"),
    ("entry.archetypes", "exit.initial_stop_basis"),
    ("style.primary", "sizing.model"),
    ("risk.pyramids", "exit.uses_trailing"),
]


def load_vocab() -> dict[str, list[str]]:
    return json.loads(VOCAB_JSON.read_text())["vocabularies"]


def load_traders(path: Path = TRADERS_JSON) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise SystemExit(f"{path.name}: expected a JSON array of profiles")
    return data


def get_path(record: dict, dotted: str):
    node = record
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# --- validate -----------------------------------------------------------------


def validate_profile(p: dict, vocab: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    who = p.get("id") or p.get("name") or "<unnamed>"

    def err(msg: str) -> None:
        errors.append(f"{who}: {msg}")

    for key in REQUIRED_TOP:
        if key not in p:
            err(f"missing required field '{key}'")
    if errors:
        return errors  # structure is too broken for the checks below

    for section, keys in REQUIRED_KEYS.items():
        node = p[section]
        if not isinstance(node, dict):
            err(f"'{section}' must be an object")
            continue
        for key in keys:
            if key not in node:
                err(f"missing '{section}.{key}' (null is legal, absent is not)")

    sources = get_path(p, "verification.sources") or []
    if not sources:
        err("verification.sources must have at least one source")
    for i, s in enumerate(sources):
        for key in ("title", "type", "year"):
            if key not in s:
                err(f"sources[{i}] missing '{key}'")
        if s.get("type") not in vocab["source_type"]:
            err(f"sources[{i}].type {s.get('type')!r} not in source_type vocab")

    tier = get_path(p, "verification.tier")
    if tier not in vocab["verification_tier"]:
        err(f"verification.tier {tier!r} must be A/B/C")
    justification = get_path(p, "verification.tier_justification") or ""
    if len(justification) < 10:
        err("verification.tier_justification required (>= 10 chars)")

    for dotted, vocab_name in VOCAB_FIELDS.items():
        value = get_path(p, dotted)
        if value is not None and value not in vocab[vocab_name]:
            err(f"{dotted} {value!r} not in {vocab_name} vocab")
    for dotted, vocab_name in VOCAB_LIST_FIELDS.items():
        values = get_path(p, dotted)
        if values is None:
            continue
        if not isinstance(values, list):
            err(f"{dotted} must be a list")
            continue
        for value in values:
            if value not in vocab[vocab_name]:
                err(f"{dotted} member {value!r} not in {vocab_name} vocab")

    n_sources = len(sources)

    def check_source_idx(label: str, idx) -> None:
        if not isinstance(idx, int) or not 0 <= idx < n_sources:
            err(f"{label} source_idx {idx!r} out of range (have {n_sources} sources)")

    for dotted in SOURCED_VALUE_FIELDS:
        sv = get_path(p, dotted)
        if sv is None:
            continue
        if not isinstance(sv, dict):
            err(f"{dotted} must be null or a sourced-value object")
            continue
        for key in ("value", "unit", "basis", "source_idx"):
            if key not in sv:
                err(f"{dotted} missing '{key}'")
        if not isinstance(sv.get("value"), (int, float)):
            err(f"{dotted}.value must be a number (null the whole field if undisclosed)")
        if sv.get("basis") not in vocab["value_basis"]:
            err(f"{dotted}.basis must be disclosed|inferred")
        check_source_idx(dotted, sv.get("source_idx"))

    for dotted in BOOL_FIELDS:
        value = get_path(p, dotted)
        if value is not None and not isinstance(value, bool):
            err(f"{dotted} must be true/false/null")

    for i, rule in enumerate(p.get("psychology_rules") or []):
        if rule.get("rule") not in vocab["psychology_rule"]:
            err(f"psychology_rules[{i}].rule {rule.get('rule')!r} not in vocab")
        if not rule.get("paraphrase"):
            err(f"psychology_rules[{i}] missing paraphrase")
        check_source_idx(f"psychology_rules[{i}]", rule.get("source_idx"))

    for i, claim in enumerate(get_path(p, "performance.claims") or []):
        for key in ("metric", "value", "period", "verification", "source_idx"):
            if key not in claim:
                err(f"performance.claims[{i}] missing '{key}'")
        if claim.get("metric") not in vocab["performance_metric"]:
            err(f"performance.claims[{i}].metric {claim.get('metric')!r} not in vocab")
        if claim.get("verification") not in vocab["performance_verification"]:
            err(f"performance.claims[{i}].verification must be "
                "audited|reported|anecdotal")
        if not isinstance(claim.get("value"), (int, float)):
            err(f"performance.claims[{i}].value must be a number")
        check_source_idx(f"performance.claims[{i}]", claim.get("source_idx"))

    return errors


def cmd_validate(extra_files: list[str]) -> int:
    vocab = load_vocab()
    failures = 0
    for path in [TRADERS_JSON, *map(Path, extra_files)]:
        if not path.exists():
            print(f"SKIP {path} (not found)")
            continue
        profiles = load_traders(path)
        errors: list[str] = []
        ids = Counter(p.get("id") for p in profiles)
        for dup, n in ids.items():
            if dup is not None and n > 1:
                errors.append(f"duplicate id {dup!r} ({n} records)")
        for p in profiles:
            errors.extend(validate_profile(p, vocab))
        if errors:
            failures += 1
            print(f"FAIL {path.name}: {len(errors)} error(s)")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"OK   {path.name}: {len(profiles)} profile(s) valid")
    return 1 if failures else 0


# --- export -------------------------------------------------------------------


def cmd_export_csv() -> int:
    profiles = load_traders()
    columns = [
        "id", "name", "cohort", "verification.tier", "status",
        "style.primary", "style.discretion", "style.typical_holding_period",
        "exit.initial_stop_basis", "exit.uses_trailing", "sizing.model",
        "risk.pyramids", "risk.moves_to_breakeven",
    ]
    with TRADERS_CSV.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([*columns, "markets", "entry_archetypes",
                         "risk_per_trade_pct", "n_sources", "caution_flags"])
        for p in profiles:
            sv = get_path(p, "risk.risk_per_trade_pct")
            writer.writerow([
                *[get_path(p, c) for c in columns],
                "|".join(get_path(p, "style.markets") or []),
                "|".join(get_path(p, "entry.archetypes") or []),
                sv["value"] if isinstance(sv, dict) else "",
                len(get_path(p, "verification.sources") or []),
                "|".join(p.get("caution_flags") or []),
            ])
    print(f"wrote {TRADERS_CSV.name}: {len(profiles)} rows")
    return 0


# --- analyze ------------------------------------------------------------------


def _fmt_share(count: int, n_disclosed: int) -> str:
    if n_disclosed >= MIN_N_FOR_PCT:
        return f"{100.0 * count / n_disclosed:.0f}%"
    return f"{count} of {n_disclosed}"  # small N: raw counts only


def _values_for(p: dict, dotted: str) -> list[str] | None:
    """Vocabulary values one profile contributes for a field, or None when
    the field is null/absent (excluded from denominators)."""
    value = get_path(p, dotted)
    if value is None:
        return None
    if dotted in BOOL_FIELDS:
        return [str(value).lower()]
    if isinstance(value, list):
        return value or None
    return [value]


def frequency_rows(profiles: list[dict], dotted: str) -> list[dict]:
    counts: Counter[str] = Counter()
    n_disclosed = 0
    for p in profiles:
        values = _values_for(p, dotted)
        if values is None:
            continue
        n_disclosed += 1
        for v in set(values):
            counts[v] += 1
    return [
        {"field": dotted, "value": value, "count": count,
         "n_disclosed": n_disclosed, "n_total": len(profiles),
         "share": _fmt_share(count, n_disclosed)}
        for value, count in counts.most_common()
    ]


def numeric_rows(profiles: list[dict], dotted: str) -> list[dict]:
    rows = []
    for basis in ("disclosed", "inferred"):
        values = []
        for p in profiles:
            sv = get_path(p, dotted)
            if isinstance(sv, dict) and sv.get("basis") == basis:
                values.append(float(sv["value"]))
        if not values:
            continue
        values.sort()
        quartiles = (statistics.quantiles(values, n=4)
                     if len(values) >= 4 else [None, None, None])
        rows.append({
            "field": dotted, "basis": basis, "n": len(values),
            "min": values[0], "q1": quartiles[0],
            "median": statistics.median(values), "q3": quartiles[2],
            "max": values[-1], "n_total": len(profiles),
        })
    return rows


def cooccurrence_rows(profiles: list[dict], field_a: str,
                      field_b: str) -> list[dict]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    a_counts: Counter[str] = Counter()
    b_counts: Counter[str] = Counter()
    n_both = 0
    for p in profiles:
        a_values, b_values = _values_for(p, field_a), _values_for(p, field_b)
        if a_values is None or b_values is None:
            continue  # lift only over rows where BOTH fields are non-null
        n_both += 1
        for a in set(a_values):
            a_counts[a] += 1
        for b in set(b_values):
            b_counts[b] += 1
        for a in set(a_values):
            for b in set(b_values):
                pair_counts[(a, b)] += 1
    rows = []
    for (a, b), support in pair_counts.most_common():
        if support < MIN_SUPPORT:
            continue
        expected = a_counts[a] * b_counts[b] / n_both if n_both else 0
        rows.append({
            "field_a": field_a, "value_a": a, "field_b": field_b, "value_b": b,
            "support": support, "n_both_disclosed": n_both,
            "lift": round(support / expected, 2) if expected else "",
        })
    return rows


def missing_data_rows(profiles: list[dict]) -> list[dict]:
    fields = ([*VOCAB_FIELDS, *VOCAB_LIST_FIELDS, *SOURCED_VALUE_FIELDS,
               *BOOL_FIELDS])
    cohorts = sorted({p.get("cohort") for p in profiles if p.get("cohort")})
    rows = []
    for cohort in cohorts:
        cohort_profiles = [p for p in profiles if p.get("cohort") == cohort]
        for field in fields:
            disclosed = sum(
                1 for p in cohort_profiles if _values_for(p, field) is not None)
            rows.append({
                "cohort": cohort, "field": field,
                "disclosed": disclosed, "n": len(cohort_profiles),
                "disclosure_rate": (f"{100.0 * disclosed / len(cohort_profiles):.0f}%"
                                    if len(cohort_profiles) >= MIN_N_FOR_PCT
                                    else f"{disclosed} of {len(cohort_profiles)}"),
            })
    return rows


def _write_csv(name: str, rows: list[dict]) -> None:
    path = DERIVED / name
    if not rows:
        path.write_text("")  # honest empty output beats a stale table
        print(f"wrote {name}: 0 rows")
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {name}: {len(rows)} rows")


def cmd_analyze() -> int:
    profiles = load_traders()
    DERIVED.mkdir(exist_ok=True)
    print(f"analyzing {len(profiles)} profiles "
          f"(honesty rules: pct only at N>={MIN_N_FOR_PCT}, nulls excluded "
          f"from denominators, no imputation)")
    tiers_ab = [p for p in profiles
                if get_path(p, "verification.tier") in ("A", "B")]
    for label, subset in (("all_tiers", profiles), ("tier_ab", tiers_ab)):
        freq: list[dict] = []
        for dotted in [*VOCAB_FIELDS, *VOCAB_LIST_FIELDS, *BOOL_FIELDS]:
            if dotted in ("cohort", "status"):
                continue
            freq.extend(frequency_rows(subset, dotted))
        _write_csv(f"frequency_{label}.csv", freq)

        numeric: list[dict] = []
        for dotted in SOURCED_VALUE_FIELDS:
            numeric.extend(numeric_rows(subset, dotted))
        _write_csv(f"numeric_{label}.csv", numeric)

        cooc: list[dict] = []
        for field_a, field_b in COOCCURRENCE_PAIRS:
            cooc.extend(cooccurrence_rows(subset, field_a, field_b))
        _write_csv(f"cooccurrence_{label}.csv", cooc)

    _write_csv("missing_data_report.csv", missing_data_rows(profiles))
    tier_counts = Counter(get_path(p, "verification.tier") for p in profiles)
    print(f"tier mix: {dict(sorted(tier_counts.items()))} "
          f"(tier A+B subset: {len(tiers_ab)})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", nargs="*", metavar="EXTRA_JSON",
                       help="validate traders.json (+ optional batch files)")
    group.add_argument("--export-csv", action="store_true")
    group.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.validate is not None:
        return cmd_validate(args.validate)
    if args.export_csv:
        return cmd_export_csv()
    return cmd_analyze()


if __name__ == "__main__":
    sys.exit(main())
