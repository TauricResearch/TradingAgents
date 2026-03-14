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

import time
import logging
import threading
from datetime import datetime, timedelta

import requests

from .constants import URLS, TR_IDS, ORDER_TYPE_CODES, PATHS

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_calls: int = 18, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            # Remove timestamps outside the window
            self._timestamps = [
                t for t in self._timestamps if now - t < self.period
            ]
            if len(self._timestamps) >= self.max_calls:
                sleep_time = self.period - (now - self._timestamps[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self._timestamps = [
                    t for t in self._timestamps if time.monotonic() - t < self.period
                ]
            self._timestamps.append(time.monotonic())


class KISClient:
    """Low-level KIS REST API client with authentication management.

    Handles token lifecycle, rate limiting, and raw HTTP calls.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        mode: str = "paper",
    ):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no  # Format: "XXXXXXXX-XX"
        self.mode = mode
        self.base_url = URLS[mode]
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._token_lock = threading.Lock()
        self._rate_limiter = RateLimiter(max_calls=18, period=1.0)

    # --- Authentication ---

    def _ensure_token(self):
        """Get or refresh OAuth token if needed."""
        with self._token_lock:
            if self._token and self._token_expires_at:
                if datetime.now() < self._token_expires_at - timedelta(hours=1):
                    return
            self._request_token()

    def _request_token(self):
        """Request a new OAuth2 access token from KIS."""
        url = f"{self.base_url}{PATHS['token']}"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        self._token = data["access_token"]
        # KIS tokens typically expire in 86400 seconds (24h)
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        logger.info("KIS token acquired, expires at %s", self._token_expires_at)

    # --- HTTP helpers ---

    def _headers(self, tr_id: str) -> dict:
        """Build standard KIS API request headers."""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict:
        """Make an authenticated API request with rate limiting."""
        self._ensure_token()
        self._rate_limiter.acquire()

        url = f"{self.base_url}{path}"
        headers = self._headers(tr_id)

        logger.debug("KIS %s %s tr_id=%s", method, path, tr_id)

        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=10)
        else:
            resp = requests.post(url, headers=headers, json=body, timeout=10)

        resp.raise_for_status()
        data = resp.json()

        rt_cd = data.get("rt_cd")
        if rt_cd and rt_cd != "0":
            msg = data.get("msg1", "Unknown KIS API error")
            logger.error("KIS API error: rt_cd=%s msg=%s", rt_cd, msg)
            raise RuntimeError(f"KIS API error ({rt_cd}): {msg}")

        return data

    # --- Account number parsing ---

    @property
    def _acnt_prdt_cd(self) -> tuple[str, str]:
        """Split account_no 'XXXXXXXX-XX' into (CANO, ACNT_PRDT_CD)."""
        parts = self.account_no.split("-")
        return parts[0], parts[1] if len(parts) > 1 else "01"

    # --- Public API methods ---

    def place_order(
        self,
        ticker: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: int = 0,
    ) -> dict:
        """Place a buy or sell order.

        Args:
            ticker: 6-digit stock code (e.g. "005930")
            side: "BUY" or "SELL"
            quantity: Number of shares
            order_type: "MARKET" or "LIMIT"
            price: Price for limit orders (0 for market orders)

        Returns:
            Raw KIS API response dict
        """
        tr_id_key = "buy" if side == "BUY" else "sell"
        tr_id = TR_IDS[self.mode][tr_id_key]
        cano, acnt_prdt_cd = self._acnt_prdt_cd

        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": ticker,
            "ORD_DVSN": ORDER_TYPE_CODES[order_type],
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price),
        }

        return self._request("POST", PATHS["order"], tr_id, body=body)

    def get_balance(self) -> dict:
        """Query account balance and positions.

        Returns:
            Raw KIS API response with output1 (positions) and output2 (summary)
        """
        tr_id = TR_IDS[self.mode]["balance"]
        cano, acnt_prdt_cd = self._acnt_prdt_cd

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        return self._request("GET", PATHS["balance"], tr_id, params=params)

    def get_current_price(self, ticker: str) -> dict:
        """Get the current market price for a stock.

        Args:
            ticker: 6-digit stock code

        Returns:
            Raw KIS API response with output containing price data
        """
        tr_id = TR_IDS[self.mode]["current_price"]

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }

        return self._request("GET", PATHS["current_price"], tr_id, params=params)

    def get_order_status(self, start_date: str, end_date: str) -> dict:
        """Query recent order execution history.

        Args:
            start_date: YYYYMMDD format
            end_date: YYYYMMDD format

        Returns:
            Raw KIS API response with order history
        """
        tr_id = TR_IDS[self.mode]["order_status"]
        cano, acnt_prdt_cd = self._acnt_prdt_cd

        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "INQR_STRT_DT": start_date,
            "INQR_END_DT": end_date,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "01",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        return self._request("GET", PATHS["order_status"], tr_id, params=params)
