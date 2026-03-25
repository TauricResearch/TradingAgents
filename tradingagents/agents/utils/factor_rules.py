import json
import os
from pathlib import Path
from typing import Any, Optional


def _candidate_rule_paths(config: Optional[dict[str, Any]] = None) -> list[Path]:
    config = config or {}
    project_dir = Path(
        config.get("project_dir", Path(__file__).resolve().parents[2])
    ).resolve()

    candidates = []
    explicit_path = config.get("factor_rules_path")
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    env_path = os.getenv("TRADINGAGENTS_FACTOR_RULES_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        [
            project_dir / "examples" / "factor_rules.json",
            project_dir / "factor_rules.json",
        ]
    )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def load_factor_rules(
    config: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    config = config or {}

    for path in _candidate_rule_paths(config):
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, list):
            rules = data
        elif isinstance(data, dict):
            if "rules" not in data:
                raise ValueError(
                    "Factor rules file must contain a 'rules' list when using an object payload."
                )
            rules = data["rules"]
        else:
            raise ValueError(
                "Factor rules file must be a list or contain a list under 'rules'."
            )

        if not isinstance(rules, list):
            raise ValueError(
                "Factor rules file must be a list or contain a list under 'rules'."
            )
        if any(not isinstance(rule, dict) for rule in rules):
            raise ValueError("Each factor rule must be a JSON object.")

        return rules, str(path)

    return [], None


def summarize_factor_rules(
    rules: list[dict[str, Any]],
    ticker: str,
    trade_date: str,
) -> str:
    if not rules:
        return (
            f"No factor rules were loaded for {ticker} on {trade_date}. "
            "Treat this as missing custom factor context and do not fabricate rule-based signals."
        )

    lines = [
        f"Factor rule context for {ticker} on {trade_date}.",
        f"Loaded {len(rules)} manually curated factor rules.",
        "Use these as analyst guidance rather than guaranteed facts.",
        "",
    ]

    bullish = 0
    bearish = 0
    neutral = 0

    for index, rule in enumerate(rules, start=1):
        signal = str(rule.get("signal", "neutral")).lower()
        if signal in {"bullish", "buy", "positive"}:
            bullish += 1
        elif signal in {"bearish", "sell", "negative"}:
            bearish += 1
        else:
            neutral += 1

        conditions = rule.get("conditions", [])
        if isinstance(conditions, list):
            conditions_text = "; ".join(str(item) for item in conditions)
        else:
            conditions_text = str(conditions)

        lines.extend(
            [
                f"Rule {index}: {rule.get('name', f'Rule {index}')}",
                f"- Signal bias: {rule.get('signal', 'neutral')}",
                f"- Weight: {rule.get('weight', 'medium')}",
                f"- Thesis: {rule.get('thesis', '')}",
                f"- Conditions: {conditions_text or 'No explicit conditions provided'}",
                f"- Rationale: {rule.get('rationale', '')}",
                "",
            ]
        )

    lines.extend(
        [
            "Portfolio-level summary:",
            f"- Bullish leaning rules: {bullish}",
            f"- Bearish leaning rules: {bearish}",
            f"- Neutral / mixed rules: {neutral}",
            "When factor rules conflict with market, news, macro, or fundamentals evidence, explicitly discuss the conflict.",
        ]
    )

    return "\n".join(lines)
