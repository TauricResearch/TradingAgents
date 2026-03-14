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

from abc import ABC, abstractmethod

from .models import (
    OrderRequest,
    OrderResult,
    AccountBalance,
    PortfolioSnapshot,
)


class BaseBroker(ABC):
    """Abstract broker interface for trade execution.

    Implement this interface to add support for a new broker.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and establish connection. Returns True on success."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if authenticated and token is valid."""

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        """Submit a buy/sell order. Returns execution result."""

    @abstractmethod
    def get_balance(self, account_no: str) -> AccountBalance:
        """Query account cash balance and buying power."""

    @abstractmethod
    def get_portfolio(self, account_no: str) -> PortfolioSnapshot:
        """Query current positions and their P&L."""

    @abstractmethod
    def get_current_price(self, ticker: str) -> float:
        """Get the current market price for a ticker."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResult:
        """Check status of a previously submitted order."""

    @property
    @abstractmethod
    def broker_name(self) -> str:
        """Human-readable broker name for display."""

    @property
    @abstractmethod
    def is_paper_trading(self) -> bool:
        """Whether this broker instance is in paper trading mode."""
