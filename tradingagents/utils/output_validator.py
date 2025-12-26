"""
Output validation utilities for agent outputs.

This module provides validation functions for:
- Report completeness (length, structure, markdown formatting)
- Decision quality (signal extraction, reasoning clarity)
- Debate state coherence (history tracking, judge decisions)
- Complete agent state validation

All validators return ValidationResult with actionable feedback.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re


@dataclass
class ValidationResult:
    """
    Result of a validation check with actionable feedback.

    Attributes:
        is_valid: True if validation passed, False otherwise
        errors: List of error messages (validation failures)
        warnings: List of warning messages (quality concerns)
        metrics: Dictionary of measured metrics (e.g., length, counts)
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """Add an error and mark validation as failed."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning (doesn't fail validation)."""
        self.warnings.append(message)

    def add_metric(self, key: str, value: Any) -> None:
        """Add a measured metric."""
        self.metrics[key] = value


def validate_report_completeness(
    report: Optional[str],
    min_length: int = 500,
    require_markdown_tables: bool = False,
    require_sections: bool = False,
) -> ValidationResult:
    """
    Validate that a report is complete and well-structured.

    Args:
        report: The report text to validate
        min_length: Minimum character count required (default: 500)
        require_markdown_tables: Whether to require markdown tables
        require_sections: Whether to require section headers (##)

    Returns:
        ValidationResult with errors, warnings, and metrics

    Example:
        >>> result = validate_report_completeness("# Report\\n\\nThis is too short")
        >>> assert not result.is_valid
        >>> assert "minimum length" in result.errors[0].lower()
    """
    result = ValidationResult(is_valid=True)

    # Check if report exists
    if report is None:
        result.add_error("Report is None")
        return result

    if not isinstance(report, str):
        result.add_error(f"Report must be string, got {type(report).__name__}")
        return result

    # Check length
    report_length = len(report.strip())
    result.add_metric("length", report_length)

    if report_length == 0:
        result.add_error("Report is empty")
        return result

    if report_length < min_length:
        result.add_error(
            f"Report length ({report_length}) below minimum ({min_length})"
        )

    # Check for markdown tables
    markdown_tables = re.findall(r'\|.*\|', report)
    result.add_metric("markdown_tables", len(markdown_tables))

    if require_markdown_tables and len(markdown_tables) == 0:
        result.add_error("Report missing required markdown tables")

    # Check for section headers (allow optional leading whitespace)
    section_headers = re.findall(r'^\s*#{1,6}\s+.+$', report, re.MULTILINE)
    result.add_metric("section_headers", len(section_headers))

    if require_sections and len(section_headers) == 0:
        result.add_error("Report missing required section headers")

    # Quality warnings
    if report_length < min_length * 1.5:
        result.add_warning(
            f"Report is relatively short ({report_length} chars). "
            f"Consider adding more detail."
        )

    # Check for basic structure indicators
    has_bullet_points = bool(re.search(r'^\s*[-*]\s+', report, re.MULTILINE))
    result.add_metric("has_bullet_points", has_bullet_points)

    if not has_bullet_points and not markdown_tables:
        result.add_warning("Report lacks structured content (no bullets or tables)")

    return result


def validate_decision_quality(decision: Optional[str]) -> ValidationResult:
    """
    Validate trading decision quality and extract signal.

    Validates:
    - Decision is not None/empty
    - Contains clear BUY/SELL/HOLD signal
    - Has reasoning/explanation
    - Signal is unambiguous

    Args:
        decision: The decision text to validate

    Returns:
        ValidationResult with extracted signal in metrics

    Example:
        >>> result = validate_decision_quality("BUY: Strong fundamentals")
        >>> assert result.is_valid
        >>> assert result.metrics["signal"] == "BUY"
    """
    result = ValidationResult(is_valid=True)

    # Check if decision exists
    if decision is None:
        result.add_error("Decision is None")
        return result

    if not isinstance(decision, str):
        result.add_error(f"Decision must be string, got {type(decision).__name__}")
        return result

    decision_clean = decision.strip()
    if not decision_clean:
        result.add_error("Decision is empty")
        return result

    result.add_metric("length", len(decision_clean))

    # Extract trading signal (case-insensitive)
    signal_pattern = r'\b(BUY|SELL|HOLD)\b'
    matches = re.findall(signal_pattern, decision_clean, re.IGNORECASE)

    if not matches:
        result.add_error(
            "No clear trading signal found (expected BUY, SELL, or HOLD)"
        )
        result.add_metric("signal", None)
        return result

    # Get first signal and normalize to uppercase
    signal = matches[0].upper()
    result.add_metric("signal", signal)
    result.add_metric("signal_count", len(matches))

    # Warn if multiple conflicting signals
    unique_signals = set(m.upper() for m in matches)
    if len(unique_signals) > 1:
        result.add_warning(
            f"Multiple conflicting signals found: {unique_signals}. "
            f"Using first occurrence: {signal}"
        )

    # Check for reasoning
    # Split by common delimiters and check if there's explanation
    has_reasoning = any([
        ':' in decision_clean,
        '.' in decision_clean,
        len(decision_clean.split()) >= 5,
    ])

    result.add_metric("has_reasoning", has_reasoning)

    if not has_reasoning:
        result.add_warning(
            "Decision lacks clear reasoning or explanation"
        )

    # Check decision length
    if len(decision_clean) < 20:
        result.add_warning(
            f"Decision is very short ({len(decision_clean)} chars). "
            f"Consider adding more rationale."
        )

    return result


def validate_debate_state(
    debate_state: Optional[Dict[str, Any]],
    debate_type: str = "invest",
) -> ValidationResult:
    """
    Validate debate state structure and coherence.

    Validates:
    - Required fields present (history, count, judge_decision)
    - History is not empty
    - Count is reasonable (>= 0)
    - Judge decision exists if debate concluded

    Args:
        debate_state: The debate state dictionary to validate
        debate_type: Type of debate ("invest" or "risk")

    Returns:
        ValidationResult with debate metrics

    Example:
        >>> state = {"history": "Round 1...", "count": 1, "judge_decision": "BUY"}
        >>> result = validate_debate_state(state)
        >>> assert result.is_valid
    """
    result = ValidationResult(is_valid=True)

    # Check if state exists
    if debate_state is None:
        result.add_error("Debate state is None")
        return result

    if not isinstance(debate_state, dict):
        result.add_error(
            f"Debate state must be dict, got {type(debate_state).__name__}"
        )
        return result

    # Define required fields based on debate type
    if debate_type == "invest":
        required_fields = ["history", "count", "judge_decision"]
        optional_fields = ["bull_history", "bear_history", "current_response"]
    elif debate_type == "risk":
        required_fields = ["history", "count", "judge_decision"]
        optional_fields = [
            "risky_history",
            "safe_history",
            "neutral_history",
            "latest_speaker",
            "current_risky_response",
            "current_safe_response",
            "current_neutral_response",
        ]
    else:
        result.add_error(f"Unknown debate type: {debate_type}")
        return result

    # Check required fields
    missing_fields = [f for f in required_fields if f not in debate_state]
    if missing_fields:
        result.add_error(f"Missing required fields: {missing_fields}")
        return result

    # Validate history
    history = debate_state.get("history")
    if history is not None:
        if not isinstance(history, str):
            result.add_error(
                f"History must be string, got {type(history).__name__}"
            )
        elif not history.strip():
            result.add_warning("History is empty")
        else:
            result.add_metric("history_length", len(history))

    # Validate count
    count = debate_state.get("count")
    if count is not None:
        if not isinstance(count, int):
            result.add_error(f"Count must be int, got {type(count).__name__}")
        elif count < 0:
            result.add_error(f"Count cannot be negative: {count}")
        else:
            result.add_metric("count", count)

            # Warn if debate went too long
            if count > 10:
                result.add_warning(
                    f"Debate count is very high ({count}). "
                    f"May indicate convergence issues."
                )

    # Validate judge decision
    judge_decision = debate_state.get("judge_decision")
    if judge_decision is not None:
        if isinstance(judge_decision, str):
            if judge_decision.strip():
                # Validate decision quality
                decision_result = validate_decision_quality(judge_decision)
                if not decision_result.is_valid:
                    result.add_warning(
                        f"Judge decision has quality issues: "
                        f"{', '.join(decision_result.errors)}"
                    )
                else:
                    result.add_metric("judge_signal", decision_result.metrics.get("signal"))
            else:
                result.add_warning("Judge decision is empty")
        else:
            result.add_error(
                f"Judge decision must be string, got {type(judge_decision).__name__}"
            )

    # Check optional fields for completeness
    present_optional = [f for f in optional_fields if f in debate_state]
    result.add_metric("optional_fields_present", len(present_optional))

    return result


def validate_agent_state(state: Optional[Dict[str, Any]]) -> ValidationResult:
    """
    Validate complete agent state structure.

    Orchestrates all validators to check:
    - Company and trade date present
    - All reports complete
    - Investment debate state valid
    - Risk debate state valid
    - Final decision quality

    Args:
        state: The complete agent state dictionary

    Returns:
        ValidationResult with comprehensive validation

    Example:
        >>> state = {
        ...     "company_of_interest": "AAPL",
        ...     "trade_date": "2024-01-15",
        ...     "market_report": "Market analysis..." * 100,
        ... }
        >>> result = validate_agent_state(state)
        >>> assert "company_of_interest" in result.metrics
    """
    result = ValidationResult(is_valid=True)

    # Check if state exists
    if state is None:
        result.add_error("Agent state is None")
        return result

    if not isinstance(state, dict):
        result.add_error(f"Agent state must be dict, got {type(state).__name__}")
        return result

    # Validate basic fields
    company = state.get("company_of_interest")
    if not company:
        result.add_error("Missing company_of_interest")
    else:
        result.add_metric("company_of_interest", company)

    trade_date = state.get("trade_date")
    if not trade_date:
        result.add_error("Missing trade_date")
    else:
        result.add_metric("trade_date", trade_date)

    # Validate reports
    report_fields = [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
    ]

    reports_present = 0
    for report_field in report_fields:
        report = state.get(report_field)
        if report:
            reports_present += 1
            report_result = validate_report_completeness(
                report,
                min_length=500,
                require_markdown_tables=False,
                require_sections=False,
            )
            if not report_result.is_valid:
                result.add_warning(
                    f"{report_field} has issues: {', '.join(report_result.errors)}"
                )

    result.add_metric("reports_present", reports_present)
    result.add_metric("total_reports_expected", len(report_fields))

    if reports_present < len(report_fields):
        result.add_warning(
            f"Only {reports_present}/{len(report_fields)} reports present"
        )

    # Validate investment debate state
    invest_debate = state.get("investment_debate_state")
    if invest_debate:
        invest_result = validate_debate_state(invest_debate, debate_type="invest")
        if not invest_result.is_valid:
            result.add_warning(
                f"Investment debate has issues: {', '.join(invest_result.errors)}"
            )
        result.add_metric("investment_debate_valid", invest_result.is_valid)

    # Validate risk debate state
    risk_debate = state.get("risk_debate_state")
    if risk_debate:
        risk_result = validate_debate_state(risk_debate, debate_type="risk")
        if not risk_result.is_valid:
            result.add_warning(
                f"Risk debate has issues: {', '.join(risk_result.errors)}"
            )
        result.add_metric("risk_debate_valid", risk_result.is_valid)

    # Validate final decision
    final_decision = state.get("final_trade_decision")
    if final_decision:
        decision_result = validate_decision_quality(final_decision)
        if not decision_result.is_valid:
            result.add_warning(
                f"Final decision has issues: {', '.join(decision_result.errors)}"
            )
        else:
            result.add_metric("final_signal", decision_result.metrics.get("signal"))

    # Overall completeness check
    if not invest_debate and not risk_debate:
        result.add_warning(
            "State appears incomplete: no debate states present"
        )

    return result
