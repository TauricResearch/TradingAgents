from enum import Enum


class ReasonCode(str, Enum):
    CONFIG_INVALID = "config_invalid"
    QUANT_NOT_CONFIGURED = "quant_not_configured"
    QUANT_INIT_FAILED = "quant_init_failed"
    QUANT_SIGNAL_FAILED = "quant_signal_failed"
    QUANT_NO_DATA = "quant_no_data"
    LLM_INIT_FAILED = "llm_init_failed"
    LLM_SIGNAL_FAILED = "llm_signal_failed"
    LLM_UNKNOWN_RATING = "llm_unknown_rating"
    BOTH_SIGNALS_UNAVAILABLE = "both_signals_unavailable"


def reason_code_value(value: "ReasonCode | str") -> str:
    if isinstance(value, ReasonCode):
        return value.value
    return value
