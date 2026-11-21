"""Authoritative mapping from engine completion/failure to typed run outcomes."""

from __future__ import annotations

from .result import CheckResult, Finding, RunResult


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, (KeyboardInterrupt, InterruptedError)):
        return "INTERRUPTED"
    name = type(exc).__name__.casefold()
    module = type(exc).__module__.casefold()
    if "tradingagents.dataflows" in module or "vendor" in module:
        return "DATA_FAILURE"
    if any(word in name for word in ("timeout", "ratelimit", "authentication", "apiconnection",
                                      "responseerror", "outputparser", "modelerror")):
        return "MODEL_FAILURE"
    if any(part in module for part in ("langchain", "openai", "anthropic", "google")):
        return "MODEL_FAILURE"
    if "vendor" in module or name in {"nomarketdataerror", "vendorunavailableerror",
                                      "vendornotconfigurederror"}:
        return "DATA_FAILURE"
    return "INTERNAL_ERROR"


class OutcomeFinalizer:
    def finalize(self, *, run_id: str, ticker: str, analysis_date: str,
                 input_mode: str, final_rating: str | None = None,
                 check_result: CheckResult | None = None,
                 exc: BaseException | None = None,
                 persistence_error: bool = False) -> RunResult:
        if persistence_error:
            exc_reason = "PERSISTENCE_ERROR"
        elif exc is not None:
            exc_reason = classify_exception(exc)
        else:
            exc_reason = None
        if exc_reason is not None or final_rating is None:
            reason = exc_reason or "INTERNAL_ERROR"
            return RunResult(
                run_id, ticker, analysis_date, input_mode, "INCOMPLETE", reason,
                None, "NOT_RUN", (), None, None,
            )
        check_result = check_result or CheckResult(
            "NEEDS_REVIEW", (Finding("CHECK_ERROR", detail="Output check was unavailable."),)
        )
        if check_result.output_check == "NOT_RUN":
            check_result = CheckResult(
                "NEEDS_REVIEW", (Finding("CHECK_ERROR", detail="Output check was unavailable."),)
            )
        return RunResult(
            run_id, ticker, analysis_date, input_mode, "COMPLETED", None,
            final_rating, check_result.output_check, check_result.findings, None, None,
        )

    def incomplete(self, *, run_id: str, ticker: str, analysis_date: str,
                   input_mode: str, reason: str) -> RunResult:
        return RunResult(run_id, ticker, analysis_date, input_mode, "INCOMPLETE",
                         reason, None, "NOT_RUN", (), None, None)
