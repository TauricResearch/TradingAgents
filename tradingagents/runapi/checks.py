"""Deterministic, local-only checks for the rendered report body and provenance."""

from __future__ import annotations

from .result import CheckResult, Finding

DISCLAIMER = (
    "Research output only. User-supplied holdings are unverified. "
    "No order is placed and no return is guaranteed."
)
NO_PORTFOLIO_NOTICE = "Holdings and cash were not provided; no account ownership is assumed."
PROHIBITED_PHRASES = (
    "guaranteed profit", "guaranteed returns", "capital protection is guaranteed",
)


def render_provenance(metadata: dict) -> str:
    """The pre-check trusted provenance fragment, rendered from safe metadata."""
    fields = (
        ("Run ID", metadata["run_id"]), ("Ticker", metadata["ticker"]),
        ("Analysis date", metadata["analysis_date"]),
        ("Input mode", metadata["input_mode"]),
        ("Portfolio file", metadata["basename"]),
        ("Portfolio fingerprint (SHA-256)", metadata["fingerprint_sha256"]),
        ("Portfolio as-of", metadata["portfolio_as_of"]),
        ("As-of basis", metadata["as_of_basis"]),
    )
    def safe(value):
        if value is None:
            return "null"
        return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return "\n".join(f"- {label}: {safe(value)}" for label, value in fields)


class OutputChecker:
    """Assigns PASSED/NEEDS_REVIEW; never contacts a model provider."""

    def evaluate(self, trusted: dict, provenance_fragment: str,
                 final_rating: str, rendered_body: str) -> CheckResult:
        findings = []
        allowed = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}
        if final_rating not in allowed:
            findings.append(Finding("Q1", detail="Final rating is missing or unreadable; REVIEW requires human review."))
        expected = render_provenance(trusted)
        if provenance_fragment != expected:
            findings.append(Finding("Q2", detail="Report provenance does not match the frozen input metadata."))
        if DISCLAIMER not in rendered_body:
            findings.append(Finding("Q3", detail="Required research disclaimer is missing."))
        body_without_disclaimer = rendered_body.replace(DISCLAIMER, "")
        lowered = body_without_disclaimer.casefold()
        if any(phrase in lowered for phrase in PROHIBITED_PHRASES):
            findings.append(Finding("Q4", detail="Report contains prohibited guarantee wording."))
        return CheckResult("NEEDS_REVIEW", tuple(findings)) if findings else CheckResult("PASSED")

    @staticmethod
    def error_result(exc: Exception) -> CheckResult:
        return CheckResult("NEEDS_REVIEW", (Finding("CHECK_ERROR", detail="Output check failed safely."),))
