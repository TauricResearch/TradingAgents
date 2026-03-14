# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"  # 시장가
    LIMIT = "LIMIT"  # 지정가


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderRequest:
    ticker: str  # e.g. "005930" for Samsung
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    account_no: Optional[str] = None


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    raw_response: Optional[dict] = None


@dataclass
class Position:
    ticker: str
    name: str  # 종목명
    quantity: int
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    market_value: float


@dataclass
class AccountBalance:
    total_equity: float  # 총평가금액
    cash_balance: float  # 예수금
    buying_power: float  # 주문가능금액
    total_unrealized_pnl: float  # 총평가손익
    currency: str = "KRW"


@dataclass
class PortfolioSnapshot:
    account_no: str
    balance: AccountBalance
    positions: List[Position] = field(default_factory=list)
    snapshot_time: datetime = field(default_factory=datetime.now)
