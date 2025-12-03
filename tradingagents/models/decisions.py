from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class AnalystType(str, Enum):
    MARKET = "market"
    SENTIMENT = "sentiment"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"


class AnalystReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    analyst_type: AnalystType
    ticker: str
    report_date: datetime
    signal: Optional[SignalType] = None
    confidence: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    raw_content: Optional[str] = None
    data_sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class TradingSignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str
    timestamp: datetime
    signal: SignalType
    strength: Decimal = Field(ge=0, le=1)
    source: str
    timeframe: str = Field(default="1d")
    price_at_signal: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    expiry: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str
    timestamp: datetime
    overall_risk_score: Decimal = Field(ge=0, le=1)

    market_risk: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    liquidity_risk: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    volatility_risk: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    concentration_risk: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    event_risk: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)

    max_position_size: Optional[Decimal] = None
    recommended_stop_loss: Optional[Decimal] = None
    var_95: Optional[Decimal] = None
    expected_shortfall: Optional[Decimal] = None

    risk_factors: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class TradingDecision(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str
    timestamp: datetime
    decision_date: datetime

    signal: SignalType
    confidence: Decimal = Field(ge=0, le=1)

    recommended_action: str
    recommended_quantity: Optional[int] = None
    recommended_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None

    analyst_reports: list[AnalystReport] = Field(default_factory=list)
    signals: list[TradingSignal] = Field(default_factory=list)
    risk_assessment: Optional[RiskAssessment] = None

    bull_argument: Optional[str] = None
    bear_argument: Optional[str] = None
    debate_rounds: int = Field(default=0, ge=0)
    debate_winner: Optional[str] = None

    risk_manager_approved: Optional[bool] = None
    risk_manager_notes: Optional[str] = None

    final_decision: str
    rationale: str

    execution_price: Optional[Decimal] = None
    executed_at: Optional[datetime] = None
    execution_notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def is_buy(self) -> bool:
        return self.signal in (SignalType.BUY, SignalType.STRONG_BUY)

    @property
    def is_sell(self) -> bool:
        return self.signal in (SignalType.SELL, SignalType.STRONG_SELL)

    @property
    def is_hold(self) -> bool:
        return self.signal == SignalType.HOLD

    def get_analyst_report(self, analyst_type: AnalystType) -> Optional[AnalystReport]:
        for report in self.analyst_reports:
            if report.analyst_type == analyst_type:
                return report
        return None

    def to_summary(self) -> dict:
        return {
            "ticker": self.ticker,
            "date": self.decision_date.isoformat(),
            "signal": self.signal.value,
            "confidence": float(self.confidence),
            "final_decision": self.final_decision,
            "risk_approved": self.risk_manager_approved,
            "debate_rounds": self.debate_rounds,
            "analyst_consensus": self._calculate_consensus(),
        }

    def _calculate_consensus(self) -> Optional[str]:
        if not self.analyst_reports:
            return None

        signals = [r.signal for r in self.analyst_reports if r.signal]
        if not signals:
            return None

        buy_count = sum(1 for s in signals if s in (SignalType.BUY, SignalType.STRONG_BUY))
        sell_count = sum(1 for s in signals if s in (SignalType.SELL, SignalType.STRONG_SELL))

        if buy_count > sell_count:
            return "bullish"
        elif sell_count > buy_count:
            return "bearish"
        return "neutral"
