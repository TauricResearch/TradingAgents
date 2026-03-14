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

import os
import logging
from datetime import datetime

from ..base_broker import BaseBroker
from ..models import (
    OrderRequest,
    OrderResult,
    OrderStatus,
    AccountBalance,
    PortfolioSnapshot,
    Position,
)
from .client import KISClient

logger = logging.getLogger(__name__)


class KISBroker(BaseBroker):
    """KIS (한국투자증권) broker implementation."""

    def __init__(self, config: dict):
        broker_config = config.get("broker", {})
        self._mode = broker_config.get("mode", "paper")

        app_key = broker_config.get("kis_app_key") or os.environ.get("KIS_APP_KEY", "")
        app_secret = broker_config.get("kis_app_secret") or os.environ.get("KIS_APP_SECRET", "")
        account_no = broker_config.get("kis_account_no") or os.environ.get("KIS_ACCOUNT_NO", "")

        if not all([app_key, app_secret, account_no]):
            raise ValueError(
                "KIS broker requires KIS_APP_KEY, KIS_APP_SECRET, and KIS_ACCOUNT_NO. "
                "Set them in config['broker'] or as environment variables."
            )

        self._client = KISClient(
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            mode=self._mode,
        )
        self._connected = False

    @property
    def broker_name(self) -> str:
        return "KIS (한국투자증권)"

    @property
    def is_paper_trading(self) -> bool:
        return self._mode == "paper"

    def connect(self) -> bool:
        try:
            self._client._ensure_token()
            self._connected = True
            mode_str = "모의투자" if self.is_paper_trading else "실투자"
            logger.info("KIS broker connected (%s)", mode_str)
            return True
        except Exception as e:
            logger.error("KIS broker connection failed: %s", e)
            self._connected = False
            return False

    def is_connected(self) -> bool:
        if not self._connected or not self._client._token:
            return False
        if self._client._token_expires_at:
            return datetime.now() < self._client._token_expires_at
        return False

    def place_order(self, order: OrderRequest) -> OrderResult:
        try:
            price = int(order.limit_price) if order.limit_price else 0
            data = self._client.place_order(
                ticker=order.ticker,
                side=order.side.value,
                quantity=order.quantity,
                order_type=order.order_type.value,
                price=price,
            )

            output = data.get("output", {})
            order_id = output.get("ODNO", "")

            return OrderResult(
                success=True,
                order_id=order_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                filled_price=price,
                message=f"Order {order_id} submitted: {order.side.value} {order.quantity} shares of {order.ticker}",
                raw_response=data,
            )
        except Exception as e:
            logger.error("KIS order failed: %s", e)
            return OrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    def get_balance(self, account_no: str = None) -> AccountBalance:
        data = self._client.get_balance()
        summary = data.get("output2", [{}])
        if isinstance(summary, list):
            summary = summary[0] if summary else {}

        return AccountBalance(
            total_equity=float(summary.get("tot_evlu_amt", 0)),
            cash_balance=float(summary.get("dnca_tot_amt", 0)),
            buying_power=float(summary.get("nass_amt", 0)),
            total_unrealized_pnl=float(summary.get("evlu_pfls_smtl_amt", 0)),
        )

    def get_portfolio(self, account_no: str = None) -> PortfolioSnapshot:
        data = self._client.get_balance()

        # Parse positions from output1
        positions = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty == 0:
                continue
            positions.append(
                Position(
                    ticker=item.get("pdno", ""),
                    name=item.get("prdt_name", ""),
                    quantity=qty,
                    avg_cost=float(item.get("pchs_avg_pric", 0)),
                    current_price=float(item.get("prpr", 0)),
                    unrealized_pnl=float(item.get("evlu_pfls_amt", 0)),
                    unrealized_pnl_pct=float(item.get("evlu_pfls_rt", 0)),
                    market_value=float(item.get("evlu_amt", 0)),
                )
            )

        # Parse account summary from output2
        summary = data.get("output2", [{}])
        if isinstance(summary, list):
            summary = summary[0] if summary else {}

        balance = AccountBalance(
            total_equity=float(summary.get("tot_evlu_amt", 0)),
            cash_balance=float(summary.get("dnca_tot_amt", 0)),
            buying_power=float(summary.get("nass_amt", 0)),
            total_unrealized_pnl=float(summary.get("evlu_pfls_smtl_amt", 0)),
        )

        return PortfolioSnapshot(
            account_no=self._client.account_no,
            balance=balance,
            positions=positions,
        )

    def get_current_price(self, ticker: str) -> float:
        data = self._client.get_current_price(ticker)
        output = data.get("output", {})
        return float(output.get("stck_prpr", 0))

    def get_order_status(self, order_id: str) -> OrderResult:
        today = datetime.now().strftime("%Y%m%d")
        data = self._client.get_order_status(today, today)

        for item in data.get("output1", []):
            if item.get("odno") == order_id:
                filled_qty = int(item.get("tot_ccld_qty", 0))
                ord_qty = int(item.get("ord_qty", 0))

                if filled_qty == ord_qty:
                    status = OrderStatus.FILLED
                elif filled_qty > 0:
                    status = OrderStatus.PARTIALLY_FILLED
                else:
                    status = OrderStatus.PENDING

                return OrderResult(
                    success=True,
                    order_id=order_id,
                    status=status,
                    filled_quantity=filled_qty,
                    filled_price=float(item.get("avg_prvs", 0)),
                    message=f"Order {order_id}: {status.value}",
                    raw_response=item,
                )

        return OrderResult(
            success=False,
            order_id=order_id,
            status=OrderStatus.PENDING,
            message=f"Order {order_id} not found in today's history",
        )
