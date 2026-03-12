"""Kiwoom Securities REST API client.

Supports both 실전투자 (real) and 모의투자 (paper trading).
API docs: https://openapi.kiwoom.com
"""

import logging
import time
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Base URLs
REAL_BASE_URL = "https://api.kiwoom.com"
PAPER_BASE_URL = "https://mockapi.kiwoom.com"


class KiwoomClient:
    """Kiwoom Securities REST API client."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_paper: bool = True,
    ):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.is_paper = is_paper
        self.base_url = PAPER_BASE_URL if is_paper else REAL_BASE_URL

        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    # ── Authentication ──────────────────────────────────────────

    def _ensure_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        resp = requests.post(
            f"{self.base_url}/oauth2/token",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.app_secret,
            },
            headers={"Content-Type": "application/json;charset=UTF-8"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["token"]
        self._token_expires = datetime.strptime(data["expires_dt"], "%Y-%m-%d %H:%M:%S")
        logger.info(f"Kiwoom token acquired, expires: {data['expires_dt']}")
        return self._token

    def _headers(self, api_id: str, cont_yn: str = "N", next_key: str = "") -> dict:
        """Build request headers."""
        token = self._ensure_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": api_id,
        }
        if cont_yn:
            headers["cont-yn"] = cont_yn
        if next_key:
            headers["next-key"] = next_key
        return headers

    def _post(self, path: str, api_id: str, body: dict, **kwargs) -> dict:
        """Make authenticated POST request."""
        headers = self._headers(api_id, **kwargs)
        resp = requests.post(
            f"{self.base_url}{path}",
            json=body,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("return_code") and int(result["return_code"]) != 0:
            logger.error(f"Kiwoom API error [{api_id}]: {result.get('return_msg')}")

        return result

    # ── Orders ──────────────────────────────────────────────────

    def buy(
        self,
        stock_code: str,
        quantity: int,
        price: int = 0,
        order_type: str = "market",
    ) -> dict:
        """Place a buy order.

        Args:
            stock_code: 6-digit stock code (e.g. '005930')
            quantity: Number of shares
            price: Limit price (0 for market order)
            order_type: 'market' or 'limit'

        Returns:
            Order response with ord_no, return_code, return_msg
        """
        body = {
            "dmst_stex_tp": "SOR",
            "stk_cd": stock_code.zfill(6),
            "ord_qty": str(quantity),
            "ord_uv": str(price),
            "trde_tp": "3" if order_type == "market" else "0",
        }
        result = self._post("/api/dostk/ordr", "kt10000", body)
        logger.info(
            f"BUY {stock_code} x{quantity} @ {'시장가' if order_type == 'market' else price}: "
            f"{result.get('return_msg', '')}"
        )
        return result

    def sell(
        self,
        stock_code: str,
        quantity: int,
        price: int = 0,
        order_type: str = "market",
    ) -> dict:
        """Place a sell order.

        Args:
            stock_code: 6-digit stock code
            quantity: Number of shares
            price: Limit price (0 for market order)
            order_type: 'market' or 'limit'

        Returns:
            Order response with ord_no, return_code, return_msg
        """
        body = {
            "dmst_stex_tp": "SOR",
            "stk_cd": stock_code.zfill(6),
            "ord_qty": str(quantity),
            "ord_uv": str(price),
            "trde_tp": "3" if order_type == "market" else "0",
        }
        result = self._post("/api/dostk/ordr", "kt10001", body)
        logger.info(
            f"SELL {stock_code} x{quantity} @ {'시장가' if order_type == 'market' else price}: "
            f"{result.get('return_msg', '')}"
        )
        return result

    def cancel_order(self, original_order_no: str, stock_code: str, quantity: int) -> dict:
        """Cancel an existing order."""
        body = {
            "dmst_stex_tp": "SOR",
            "stk_cd": stock_code.zfill(6),
            "ord_qty": str(quantity),
            "orgn_ord_no": original_order_no,
        }
        return self._post("/api/dostk/ordr", "kt10003", body)

    # ── Account / Balance ───────────────────────────────────────

    def get_account_no(self) -> str:
        """Retrieve account number from API."""
        result = self._post("/api/dostk/acnt", "ka00001", {})
        acct = result.get("acctNo", self.account_no)
        logger.info(f"Account number: {acct}")
        return acct

    def get_deposit(self) -> dict:
        """Get deposit/cash balance details (예수금상세현황).

        Returns:
            Dict with deposit info including available cash.
        """
        return self._post("/api/dostk/acnt", "kt00001", {})

    def get_balance(self) -> dict:
        """Get account valuation and holdings (계좌평가현황).

        Returns:
            Dict with total valuation, P&L, and individual holdings.
        """
        return self._post("/api/dostk/acnt", "kt00004", {})

    def get_holdings(self) -> dict:
        """Get filled/settled positions (체결잔고).

        Returns:
            Dict with list of current stock holdings.
        """
        return self._post("/api/dostk/acnt", "kt00005", {})

    # ── Market Data ─────────────────────────────────────────────

    def get_current_price(self, stock_code: str) -> dict:
        """Get current price and basic stock info (주식기본정보).

        Args:
            stock_code: 6-digit stock code

        Returns:
            Dict with current price, volume, bid/ask, etc.
        """
        body = {"stk_cd": stock_code.zfill(6)}
        return self._post("/api/dostk/mrkcond", "ka10001", body)

    def get_orderbook(self, stock_code: str) -> dict:
        """Get order book / bid-ask data (호가).

        Args:
            stock_code: 6-digit stock code

        Returns:
            Dict with bid/ask prices and volumes.
        """
        body = {"stk_cd": stock_code.zfill(6)}
        return self._post("/api/dostk/mrkcond", "ka10004", body)

    # ── Helpers ──────────────────────────────────────────────────

    def get_current_price_value(self, stock_code: str) -> Optional[int]:
        """Get just the current price as an integer."""
        try:
            result = self.get_current_price(stock_code)
            # Price field varies; try common field names
            for field in ("cur_prc", "stk_prpr", "현재가"):
                if field in result:
                    return abs(int(str(result[field]).replace(",", "")))
            return None
        except Exception as e:
            logger.warning(f"Failed to get price for {stock_code}: {e}")
            return None
