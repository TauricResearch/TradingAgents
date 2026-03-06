import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_ALLOWED_RULE_FILENAMES = {"factor_rules.json"}


def _candidate_rule_paths(config: Optional[Dict[str, Any]] = None) -> List[Path]:
    config = config or {}
    candidates = []

    project_dir = Path(config.get("project_dir", Path(__file__).resolve().parents[2])).resolve()
    allowed_dirs = {
        project_dir.resolve(),
        (project_dir / "examples").resolve(),
    }

    explicit = config.get("factor_rules_path")
    if explicit:
        candidates.append(Path(explicit))

    env_path = os.getenv("TRADINGAGENTS_FACTOR_RULES_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            project_dir / "examples" / "factor_rules.json",
            project_dir / "factor_rules.json",
        ]
    )

    safe_candidates = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved.name not in _ALLOWED_RULE_FILENAMES:
            continue
        if any(parent == resolved.parent or parent in resolved.parents for parent in allowed_dirs):
            safe_candidates.append(resolved)
    return safe_candidates


def load_factor_rules(config: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    for path in _candidate_rule_paths(config):
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            rules = data
        elif isinstance(data, dict):
            rules = data.get("rules", [])
        else:
            rules = []

        if not isinstance(rules, list):
            raise ValueError("Factor rules file must contain a list under 'rules' or be a list itself.")
        return rules, str(path)
    return [], None


def summarize_factor_rules(rules: List[Dict[str, Any]], ticker: str, trade_date: str) -> str:
    if not rules:
        return (
            f"No factor rules were loaded for {ticker} on {trade_date}. "
            "Treat this as missing custom factor context and do not fabricate rule-based signals."
        )

    lines = [
        f"Factor rule context for {ticker} on {trade_date}.",
        f"Loaded {len(rules)} manually curated factor rules.",
        "Use these as explicit analyst guidance, not as guaranteed facts.",
        "",
    ]

    for idx, rule in enumerate(rules, 1):
        name = rule.get("name", f"Rule {idx}")
        thesis = rule.get("thesis", "")
        signal = rule.get("signal", "neutral")
        weight = rule.get("weight", "medium")
        rationale = rule.get("rationale", "")
        conditions = rule.get("conditions", [])
        conditions_text = "; ".join(str(c) for c in conditions) if conditions else "No explicit conditions provided"
        lines.extend(
            [
                f"Rule {idx}: {name}",
                f"- Signal bias: {signal}",
                f"- Weight: {weight}",
                f"- Thesis: {thesis}",
                f"- Conditions: {conditions_text}",
                f"- Rationale: {rationale}",
                "",
            ]
        )

    bullish = [r for r in rules if str(r.get("signal", "")).lower() in {"bullish", "buy", "positive"}]
    bearish = [r for r in rules if str(r.get("signal", "")).lower() in {"bearish", "sell", "negative"}]
    neutral = len(rules) - len(bullish) - len(bearish)
    lines.extend(
        [
            "Portfolio-level summary:",
            f"- Bullish leaning rules: {len(bullish)}",
            f"- Bearish leaning rules: {len(bearish)}",
            f"- Neutral / mixed rules: {neutral}",
            "When these rules conflict with market/news/fundamental evidence, explicitly discuss the conflict instead of ignoring it.",
        ]
    )

    return "\n".join(lines)
