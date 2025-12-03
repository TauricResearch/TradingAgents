from typing import Any

from pydantic import BaseModel, Field, field_validator


class QuantitativeMetrics(BaseModel):
    momentum_score: float = Field(ge=0.0, le=1.0)
    volume_score: float = Field(ge=0.0, le=1.0)
    relative_strength_score: float = Field(ge=0.0, le=1.0)
    risk_reward_score: float = Field(ge=0.0, le=1.0)

    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    price_vs_sma50: float | None = None
    price_vs_sma200: float | None = None
    ema10_direction: str | None = None

    volume_ratio: float | None = None
    volume_trend: str | None = None
    dollar_volume: float | None = None

    rs_vs_spy_5d: float | None = None
    rs_vs_spy_20d: float | None = None
    rs_vs_spy_60d: float | None = None
    rs_vs_sector: float | None = None
    sector_etf: str | None = None

    support_level: float | None = None
    resistance_level: float | None = None
    atr: float | None = None
    suggested_stop: float | None = None
    reward_target: float | None = None
    risk_reward_ratio: float | None = None

    timeframe_alignment: str | None = None
    short_term_signal: str | None = None
    medium_term_signal: str | None = None
    long_term_signal: str | None = None
    signal_strength: float | None = None

    quantitative_score: float = Field(ge=0.0, le=1.0)

    @field_validator("ema10_direction")
    @classmethod
    def validate_ema10_direction(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_directions = {"up", "down", "flat"}
        if v not in valid_directions:
            raise ValueError(f"ema10_direction must be one of {valid_directions}")
        return v

    @field_validator("volume_trend")
    @classmethod
    def validate_volume_trend(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_trends = {"increasing", "decreasing", "flat"}
        if v not in valid_trends:
            raise ValueError(f"volume_trend must be one of {valid_trends}")
        return v

    @field_validator("timeframe_alignment")
    @classmethod
    def validate_timeframe_alignment(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_alignments = {"aligned_bullish", "aligned_bearish", "mixed", "neutral"}
        if v not in valid_alignments:
            raise ValueError(f"timeframe_alignment must be one of {valid_alignments}")
        return v

    @field_validator("short_term_signal", "medium_term_signal", "long_term_signal")
    @classmethod
    def validate_signal(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_signals = {"bullish", "bearish", "neutral"}
        if v not in valid_signals:
            raise ValueError(f"signal must be one of {valid_signals}")
        return v

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuantitativeMetrics":
        return cls(**data)
