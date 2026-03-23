"""
한국투자증권 REST API 클라이언트

- KISClient: 한국투자증권 Open API (국내/미국 시세, 잔고, 매수/매도, 순위)
- format_krw(), format_usd(): 표시 유틸리티
"""

import os
import time
import logging
import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    return int(_to_float(value))


class KISClient:
    """한국투자증권 Open API 래퍼 (REST 직접 호출)."""

    REAL_URL = "https://openapi.koreainvestment.com:9443"
    VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"

    KST = ZoneInfo("Asia/Seoul")
    NY_TZ = ZoneInfo("America/New_York")

    _holiday_cache: dict[str, bool] = {}  # KR market holiday cache

    def __init__(self):
        self.app_key = os.getenv("KIS_APP_KEY", "")
        self.app_secret = os.getenv("KIS_APP_SECRET", "")
        self.account_no = os.getenv("KIS_ACCOUNT_NO", "")
        self.virtual = os.getenv("KIS_VIRTUAL", "true").lower() == "true"

        # Manual budget caps
        self.max_order_amount = int(os.getenv("KIS_MAX_ORDER_AMOUNT", "1000000"))
        self.enable_us_trading = os.getenv("ENABLE_US_TRADING", "false").lower() == "true"
        self.us_max_order_amount = float(os.getenv("US_MAX_ORDER_AMOUNT", "5000"))

        # US exchange search order and cache
        ex_order_raw = os.getenv("US_EXCHANGE_SEARCH_ORDER", "NASD,NYSE,AMEX")
        self.us_exchange_search_order = [x.strip().upper() for x in ex_order_raw.split(",") if x.strip()]
        if not self.us_exchange_search_order:
            self.us_exchange_search_order = ["NASD", "NYSE", "AMEX"]
        self._us_exchange_cache: dict[str, str] = {}

        # KR scanning watchlist: .env의 KR_WATCHLIST에 콤마 구분으로 종목코드 설정
        kr_watchlist_raw = os.getenv("KR_WATCHLIST", "")
        self.kr_watchlist = [x.strip() for x in kr_watchlist_raw.split(",") if x.strip()]

        # US scanning watchlist (fallback source)
        watchlist_raw = os.getenv(
            "US_WATCHLIST",
            "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,AVGO,QQQ,SPY",
        )
        self.us_watchlist = [x.strip().upper() for x in watchlist_raw.split(",") if x.strip()]

        self.base_url = self.VIRTUAL_URL if self.virtual else self.REAL_URL
        self._token: str | None = None
        self._token_expires: datetime.datetime | None = None

        # 계좌번호 파싱 (12345678-01 → cano=12345678, acnt_prdt_cd=01)
        parts = self.account_no.split("-") if self.account_no else []
        self.cano = parts[0] if parts else ""
        self.acnt_prdt_cd = parts[1] if len(parts) > 1 else "01"

    @property
    def is_configured(self) -> bool:
        """KIS API 인증 정보가 설정되었는지 확인."""
        return bool(self.app_key and self.app_secret and self.account_no)

    # ── 공통 유틸 ─────────────────────────────────────────────

    def detect_market(self, ticker: str) -> Literal["KR", "US"]:
        """티커 형태로 국내/미국 시장 자동 판별."""
        t = (ticker or "").upper().strip()
        if t.endswith((".KS", ".KQ")):
            return "KR"
        if t.isdigit() and len(t) == 6:
            return "KR"
        return "US"

    def normalize_ticker(self, ticker: str, market: str | None = None) -> str:
        """시장별 티커 정규화."""
        m = (market or self.detect_market(ticker)).upper()
        t = (ticker or "").upper().strip()
        if m == "KR":
            if t.endswith((".KS", ".KQ")):
                return t.split(".", 1)[0]
            return t
        # US
        if t.endswith((".KS", ".KQ")) and len(t) > 3:
            return t.split(".", 1)[0]
        return t

    def _ranking_exchange_code(self, exchange: str) -> str:
        """해외 순위 API용 거래소 코드로 변환."""
        mapping = {
            "NASD": "NAS",
            "NASDAQ": "NAS",
            "NAS": "NAS",
            "NYSE": "NYS",
            "NYS": "NYS",
            "AMEX": "AMS",
            "AMS": "AMS",
        }
        return mapping.get((exchange or "").upper(), (exchange or "").upper())

    def _ensure_token(self):
        """Access token이 없거나 만료됐으면 재발급."""
        if (
            self._token
            and self._token_expires
            and datetime.datetime.now() < self._token_expires
        ):
            return
        self._issue_token()

    def _issue_token(self):
        """OAuth2 access token 발급."""
        resp = requests.post(
            f"{self.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = datetime.datetime.strptime(
            data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S"
        )

    def _headers(self, tr_id: str) -> dict[str, str]:
        """공통 API 헤더 생성."""
        self._ensure_token()
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
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        timeout: int = 10,
    ) -> dict:
        url = f"{self.base_url}{path}"
        if method.upper() == "GET":
            resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=timeout)
        else:
            resp = requests.post(url, headers=self._headers(tr_id), json=json_data, timeout=timeout)
        if resp.status_code >= 400:
            # KIS는 5xx에서도 JSON 본문(msg_cd/msg1)을 내려주는 경우가 있어 에러 메시지에 포함한다.
            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict):
                    rt_cd = body.get("rt_cd", "")
                    msg_cd = body.get("msg_cd", "")
                    msg1 = body.get("msg1", "") or body.get("message", "")
                    detail = f"rt_cd={rt_cd} msg_cd={msg_cd} msg1={msg1}"
                else:
                    detail = str(body)[:240]
            except Exception:
                detail = (resp.text or "").strip().replace("\n", " ")[:240]
            raise requests.HTTPError(
                f"HTTP {resp.status_code} {method.upper()} {url} {detail}".strip(),
                response=resp,
            )
        return resp.json()

    def _request_with_retry(
        self,
        method: str,
        path: str,
        tr_id: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        timeout: int = 10,
        retries: int = 1,
        base_delay_sec: float = 0.4,
    ) -> dict:
        """주문/중요 API용 재시도 래퍼 (5xx/429/네트워크 오류 대상)."""
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self._request(
                    method,
                    path,
                    tr_id,
                    params=params,
                    json_data=json_data,
                    timeout=timeout,
                )
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                last_error = e
                if status is not None and status < 500 and status != 429:
                    raise
            except Exception as e:
                last_error = e

            if attempt < retries:
                time.sleep(base_delay_sec * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError(f"request failed: {path}")

    def _ranking_request(
        self,
        path: str,
        tr_id: str,
        params: dict | None = None,
        *,
        retries: int = 2,
        base_delay_sec: float = 0.35,
    ) -> dict:
        """순위성 GET API 전용 재시도 래퍼.

        - 5xx/429/네트워크 오류는 재시도
        - 그 외 4xx는 즉시 실패
        """
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self._request("GET", path, tr_id, params=params)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                last_error = e
                if status is not None and status < 500 and status != 429:
                    raise
            except Exception as e:
                last_error = e

            if attempt < retries:
                time.sleep(base_delay_sec * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError(f"ranking request failed: {path}")

    # ── 시장 상태 ─────────────────────────────────────────────

    def is_market_open(self, dt: datetime.date | None = None, market: str = "KR") -> bool:
        """시장 개장일 여부 판별 (KR: KIS holiday API / US: weekday 기준)."""
        market = market.upper()
        if dt is None:
            if market == "US":
                dt = datetime.datetime.now(self.NY_TZ).date()
            else:
                dt = datetime.datetime.now(self.KST).date()

        if market == "US":
            return dt.weekday() < 5

        # KR
        key = dt.strftime("%Y%m%d")
        # KIS 문서상 모의투자는 chk-holiday API 미지원.
        # 모의환경에서는 불필요한 500 오류를 피하기 위해 주말만 휴장으로 간주한다.
        if self.virtual:
            is_open = dt.weekday() < 5
            self._holiday_cache[key] = is_open
            return is_open

        if dt.weekday() >= 5:
            return False
        if key in self._holiday_cache:
            return self._holiday_cache[key]

        try:
            data = self._request(
                "GET",
                "/uapi/domestic-stock/v1/quotations/chk-holiday",
                "CTCA0903R",
                params={"BASS_DT": key, "CTX_AREA_FK": "", "CTX_AREA_NK": ""},
            )
            for item in data.get("output", []):
                if item.get("bass_dt") == key:
                    is_open = item.get("opnd_yn", "N") == "Y"
                    self._holiday_cache[key] = is_open
                    return is_open
            self._holiday_cache[key] = True
            return True
        except Exception as e:
            logger.warning("KIS 휴장일 조회 실패 (KR 개장으로 간주): %s", e)
            return True

    def is_market_open_now(self, market: str = "KR") -> bool:
        """시장 정규장 시간 여부 판별."""
        market = market.upper()
        if market == "US":
            now = datetime.datetime.now(self.NY_TZ)
            if not self.is_market_open(now.date(), market="US"):
                return False
            return datetime.time(9, 30) <= now.time() <= datetime.time(16, 0)

        now = datetime.datetime.now(self.KST)
        if not self.is_market_open(now.date(), market="KR"):
            return False
        return datetime.time(9, 0) <= now.time() <= datetime.time(15, 30)

    # ── 잔고 조회 ─────────────────────────────────────────────

    def get_balance(self, market: str = "ALL") -> dict:
        """주식 잔고 + 계좌 요약 조회.

        Returns:
            {
              "holdings": [{...}],
              "summary": {
                "total_eval": <KRW total eval>,
                "total_pnl": <KRW total pnl>,
                "cash": <KRW cash>,
                "KRW": {...},
                "USD": {...}
              },
              "by_market": {"KR": {...}, "US": {...}}
            }
        """
        market = market.upper()
        holdings: list[dict] = []

        kr_summary = {"total_eval": 0.0, "total_pnl": 0.0, "cash": 0.0, "currency": "KRW"}
        us_summary = {"total_eval": 0.0, "total_pnl": 0.0, "cash": 0.0, "currency": "USD"}

        if market in ("KR", "ALL"):
            kr_data = self._get_kr_balance()
            holdings.extend(kr_data["holdings"])
            kr_summary = kr_data["summary"]

        if market in ("US", "ALL") and self.enable_us_trading:
            us_data = self._get_us_balance()
            holdings.extend(us_data["holdings"])
            us_summary = us_data["summary"]

        return {
            "holdings": holdings,
            "summary": {
                "total_eval": kr_summary["total_eval"],
                "total_pnl": kr_summary["total_pnl"],
                "cash": kr_summary["cash"],
                "KRW": kr_summary,
                "USD": us_summary,
            },
            "by_market": {
                "KR": kr_summary,
                "US": us_summary,
            },
        }

    def _get_kr_balance(self) -> dict:
        """국내 주식 잔고 조회."""
        tr_id = "VTTC8434R" if self.virtual else "TTTC8434R"
        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "01",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

        holdings: list[dict] = []
        for item in data.get("output1", []):
            qty = _to_int(item.get("hldg_qty", 0))
            if qty <= 0:
                continue
            holdings.append(
                {
                    "market": "KR",
                    "currency": "KRW",
                    "exchange": "KRX",
                    "ticker": item.get("pdno", ""),
                    "name": item.get("prdt_name", ""),
                    "qty": qty,
                    "avg_price": _to_float(item.get("pchs_avg_pric", 0)),
                    "current_price": _to_float(item.get("prpr", 0)),
                    "pnl": _to_float(item.get("evlu_pfls_amt", 0)),
                    "pnl_rate": _to_float(item.get("evlu_pfls_rt", 0)),
                }
            )

        summary = {"total_eval": 0.0, "total_pnl": 0.0, "cash": 0.0, "currency": "KRW"}
        output2 = data.get("output2", [])
        if output2:
            s = output2[0] if isinstance(output2, list) else output2
            summary = {
                "total_eval": _to_float(s.get("tot_evlu_amt", 0)),
                "total_pnl": _to_float(s.get("evlu_pfls_smtl_amt", 0)),
                "cash": _to_float(s.get("dnca_tot_amt", 0)),
                "currency": "KRW",
            }

        return {"holdings": holdings, "summary": summary}

    def _get_us_balance(self) -> dict:
        """미국 주식 잔고 조회 (거래소별 합산)."""
        if not self.enable_us_trading:
            return {
                "holdings": [],
                "summary": {"total_eval": 0.0, "total_pnl": 0.0, "cash": 0.0, "currency": "USD"},
            }

        tr_id = "VTTS3012R" if self.virtual else "TTTS3012R"
        path = "/uapi/overseas-stock/v1/trading/inquire-balance"

        holdings_map: dict[tuple[str, str], dict] = {}
        total_eval = 0.0
        total_pnl = 0.0
        total_cash = 0.0

        for exchange in self.us_exchange_search_order:
            try:
                data = self._request(
                    "GET",
                    path,
                    tr_id,
                    params={
                        "CANO": self.cano,
                        "ACNT_PRDT_CD": self.acnt_prdt_cd,
                        "OVRS_EXCG_CD": exchange,
                        "TR_CRCY_CD": "USD",
                        "CTX_AREA_FK200": "",
                        "CTX_AREA_NK200": "",
                    },
                )
            except Exception as e:
                logger.warning("US 잔고 조회 실패 exchange=%s: %s", exchange, str(e)[:120])
                continue

            for item in data.get("output1", []):
                ticker = (item.get("ovrs_pdno") or item.get("pdno") or item.get("symb") or "").strip().upper()
                if not ticker:
                    continue

                qty = _to_int(
                    item.get("ovrs_cblc_qty")
                    or item.get("cblc_qty13")
                    or item.get("hldg_qty")
                    or 0
                )
                if qty <= 0:
                    continue

                avg_price = _to_float(
                    item.get("pchs_avg_pric")
                    or item.get("avg_unpr")
                    or item.get("frcr_pchs_amt1")
                    or 0
                )
                current_price = _to_float(item.get("now_pric2") or item.get("ovrs_now_pric1") or item.get("last") or 0)
                if avg_price > 0 and _to_float(item.get("frcr_pchs_amt1", 0)) > 0 and qty > 0:
                    avg_price = _to_float(item.get("frcr_pchs_amt1", 0)) / qty
                if current_price <= 0:
                    current_price = avg_price

                pnl = _to_float(item.get("evlu_pfls_amt") or item.get("frcr_evlu_pfls_amt") or 0)
                pnl_rate = _to_float(item.get("evlu_pfls_rt") or item.get("evlu_pfls_rt1") or 0)
                name = (item.get("ovrs_item_name") or item.get("prdt_name") or ticker).strip()

                key = (exchange, ticker)
                holdings_map[key] = {
                    "market": "US",
                    "currency": "USD",
                    "exchange": exchange,
                    "ticker": ticker,
                    "name": name,
                    "qty": qty,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "pnl": pnl,
                    "pnl_rate": pnl_rate,
                }

            out2 = data.get("output2", [])
            if out2:
                s = out2[0] if isinstance(out2, list) else out2
                total_eval += _to_float(s.get("frcr_evlu_tota") or s.get("ovrs_tot_evlu_amt") or 0)
                total_pnl += _to_float(s.get("frcr_evlu_pfls_amt") or s.get("evlu_pfls_smtl_amt") or 0)
                total_cash += _to_float(s.get("frcr_dncl_amt_2") or s.get("frcr_buy_mgn_amt") or s.get("cash") or 0)

        # summary 정보가 비어도 holdings 기반으로 계산
        if total_eval == 0 and holdings_map:
            total_eval = sum(h["qty"] * h["current_price"] for h in holdings_map.values())
        if total_pnl == 0 and holdings_map:
            total_pnl = sum(h["pnl"] for h in holdings_map.values())

        return {
            "holdings": list(holdings_map.values()),
            "summary": {
                "total_eval": total_eval,
                "total_pnl": total_pnl,
                "cash": total_cash,
                "currency": "USD",
            },
        }

    # ── 현재가 조회 ──────────────────────────────────────────

    def get_price(self, ticker: str, market: str | None = None) -> float:
        """종목 현재가 조회 (KR/US 자동 분기)."""
        m = (market or self.detect_market(ticker)).upper()
        t = self.normalize_ticker(ticker, m)
        if m == "US":
            return self._get_us_price(t)
        return self._get_kr_price(t)

    def _get_kr_price(self, ticker: str) -> float:
        data = self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
            },
        )
        return _to_float(data.get("output", {}).get("stck_prpr", 0))

    def _get_us_price(self, ticker: str) -> float:
        if not self.enable_us_trading:
            raise RuntimeError("ENABLE_US_TRADING=false 상태입니다.")

        cached_exchange = self._us_exchange_cache.get(ticker)
        search_exchanges = ([cached_exchange] if cached_exchange else []) + [
            ex for ex in self.us_exchange_search_order if ex != cached_exchange
        ]

        for exchange in search_exchanges:
            if not exchange:
                continue
            px = self._get_us_price_by_exchange(ticker, exchange)
            if px > 0:
                self._us_exchange_cache[ticker] = exchange
                return px

        return 0.0

    def _get_us_price_by_exchange(self, ticker: str, exchange: str) -> float:
        path = "/uapi/overseas-price/v1/quotations/price"
        tr_id = "HHDFS00000300"

        try:
            data = self._request(
                "GET",
                path,
                tr_id,
                params={
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": ticker,
                    # 일부 계정/문서 변형 파라미터 대비
                    "OVRS_EXCG_CD": exchange,
                    "PDNO": ticker,
                },
            )
        except Exception:
            return 0.0

        out = data.get("output", {}) or {}
        price = _to_float(
            out.get("last")
            or out.get("stck_prpr")
            or out.get("ovrs_nmix_prpr")
            or out.get("clos")
            or 0
        )
        return price

    # ── 주문 (매수/매도) ─────────────────────────────────────

    def buy_stock(
        self,
        ticker: str,
        qty: int,
        price: float = 0,
        market: str | None = None,
    ) -> dict:
        """주식 매수 (price=0 → 시장가)."""
        m = (market or self.detect_market(ticker)).upper()
        t = self.normalize_ticker(ticker, m)
        if m == "US":
            return self._order_us("BUY", t, qty, price)
        return self._order_kr("BUY", t, qty, price)

    def sell_stock(
        self,
        ticker: str,
        qty: int,
        price: float = 0,
        market: str | None = None,
    ) -> dict:
        """주식 매도 (price=0 → 시장가)."""
        m = (market or self.detect_market(ticker)).upper()
        t = self.normalize_ticker(ticker, m)
        if m == "US":
            return self._order_us("SELL", t, qty, price)
        return self._order_kr("SELL", t, qty, price)

    def _order_kr(self, side: Literal["BUY", "SELL"], ticker: str, qty: int, price: float = 0) -> dict:
        primary_tr_id = "VTTC0012U" if side == "BUY" and self.virtual else "TTTC0012U"
        if side == "SELL":
            primary_tr_id = "VTTC0011U" if self.virtual else "TTTC0011U"
        fallback_tr_id = "VTTC0802U" if side == "BUY" and self.virtual else "TTTC0802U"
        if side == "SELL":
            fallback_tr_id = "VTTC0801U" if self.virtual else "TTTC0801U"

        qty_int = int(qty)
        excg_id_dvsn_cd = os.getenv("KIS_KR_EXCHANGE_ID", "KRX")
        sll_type = "00" if side == "SELL" else ""

        primary_payload = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": ticker,
            "EXCG_ID_DVSN_CD": excg_id_dvsn_cd,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty_int),
            "ORD_UNPR": str(int(price)) if price else "0",
            "SLL_TYPE": sll_type,
            "CNDT_PRIC": "",
        }
        # 일부 계정/문서 버전 호환용 최소 페이로드 fallback
        fallback_payload = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": ticker,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty_int),
            "ORD_UNPR": str(int(price)) if price else "0",
        }

        attempts = [("primary", primary_tr_id, primary_payload)]
        if fallback_tr_id != primary_tr_id:
            attempts.append(("fallback", fallback_tr_id, fallback_payload))

        errors: list[str] = []
        for mode, tr_id, payload in attempts:
            try:
                data = self._request_with_retry(
                    "POST",
                    "/uapi/domestic-stock/v1/trading/order-cash",
                    tr_id,
                    json_data=payload,
                    retries=1,
                )
                return {
                    "success": data.get("rt_cd") == "0",
                    "message": data.get("msg1", ""),
                    "order_no": data.get("output", {}).get("ODNO", ""),
                    "market": "KR",
                    "currency": "KRW",
                    "exchange": "KRX",
                }
            except Exception as e:
                logger.warning(
                    "국내 주문 실패 (%s) ticker=%s tr_id=%s: %s",
                    mode,
                    ticker,
                    tr_id,
                    e,
                )
                errors.append(f"{mode}:{str(e)}")

        return {
            "success": False,
            "message": " | ".join(errors)[:300] if errors else "국내 주문 실패",
            "order_no": "",
            "market": "KR",
            "currency": "KRW",
            "exchange": "KRX",
        }

    def _order_us(self, side: Literal["BUY", "SELL"], ticker: str, qty: int, price: float = 0) -> dict:
        if not self.enable_us_trading:
            return {
                "success": False,
                "message": "ENABLE_US_TRADING=false 상태입니다.",
                "order_no": "",
                "market": "US",
                "currency": "USD",
                "exchange": "",
            }

        exchange = self._us_exchange_cache.get(ticker)
        if not exchange:
            # 가격 조회로 거래소 자동 확정
            _ = self._get_us_price(ticker)
            exchange = self._us_exchange_cache.get(ticker)
        if not exchange:
            return {
                "success": False,
                "message": f"거래소를 찾을 수 없습니다: {ticker}",
                "order_no": "",
                "market": "US",
                "currency": "USD",
                "exchange": "",
            }

        path = "/uapi/overseas-stock/v1/trading/order"
        if side == "BUY":
            tr_id = "VTTT1002U" if self.virtual else "TTTT1002U"
        else:
            tr_id = "VTTT1006U" if self.virtual else "TTTT1006U"
        qty_int = int(qty)
        sll_type = "00" if side == "SELL" else ""

        try:
            data = self._request_with_retry(
                "POST",
                path,
                tr_id,
                json_data={
                    "CANO": self.cano,
                    "ACNT_PRDT_CD": self.acnt_prdt_cd,
                    "OVRS_EXCG_CD": exchange,
                    "PDNO": ticker,
                    "ORD_QTY": str(qty_int),
                    "OVRS_ORD_UNPR": str(price) if price else "0",
                    "ORD_SVR_DVSN_CD": "0",
                    "ORD_DVSN": "00",
                    "SLL_TYPE": sll_type,
                    "CTAC_TLNO": "",
                    "MGCO_APTM_ODNO": "",
                },
                retries=1,
            )
            return {
                "success": data.get("rt_cd") == "0",
                "message": data.get("msg1", ""),
                "order_no": data.get("output", {}).get("ODNO", ""),
                "market": "US",
                "currency": "USD",
                "exchange": exchange,
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)[:200],
                "order_no": "",
                "market": "US",
                "currency": "USD",
                "exchange": exchange,
            }

    # ── 국내 순위 분석 조회 (KR 전용) ─────────────────────────

    def get_top_market_cap(self, count: int = 5) -> list[dict]:
        """코스피 시가총액 상위 종목 조회."""
        try:
            data = self._ranking_request(
                "/uapi/domestic-stock/v1/ranking/market-cap",
                "FHPST01740000",
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "20174",
                    "fid_input_iscd": "0001",
                    "fid_div_cls_code": "1",
                    "fid_trgt_cls_code": "0",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_input_price_1": "",
                    "fid_input_price_2": "",
                    "fid_vol_cnt": "",
                },
            )
            items = data.get("output", [])
            results = []
            for item in items[:count]:
                ticker = item.get("mksc_shrn_iscd", "")
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "KR",
                        "currency": "KRW",
                        "exchange": "KRX",
                        "rank": _to_int(item.get("data_rank", len(results) + 1)),
                        "ticker": ticker,
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "price": _to_float(item.get("stck_prpr", 0)),
                        "market_cap": _to_float(item.get("stck_avls", 0)) * 1_0000_0000,
                        "volume": _to_int(item.get("acml_vol", 0)),
                    }
                )
            return results
        except Exception as e:
            logger.error("KIS 시가총액 순위 조회 실패: %s", e)
            return []

    def get_volume_rank(self, count: int = 30) -> list[dict]:
        """거래량 상위 종목 조회."""
        time.sleep(0.2)
        try:
            data = self._ranking_request(
                "/uapi/domestic-stock/v1/quotations/volume-rank",
                "FHPST01710000",
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0001",
                    "FID_DIV_CLS_CODE": "1",
                    "FID_BLNG_CLS_CODE": "0",
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "0000000000",
                    "FID_INPUT_PRICE_1": "",
                    "FID_INPUT_PRICE_2": "",
                    "FID_VOL_CNT": "",
                    "FID_INPUT_DATE_1": "",
                },
            )
            items = data.get("output", [])
            results = []
            for item in items[:count]:
                ticker = item.get("mksc_shrn_iscd", "")
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "KR",
                        "currency": "KRW",
                        "exchange": "KRX",
                        "ticker": ticker,
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "rank": _to_int(item.get("data_rank", 0)),
                        "price": _to_float(item.get("stck_prpr", 0)),
                        "prdy_ctrt": _to_float(item.get("prdy_ctrt", 0)),
                        "acml_vol": _to_int(item.get("acml_vol", 0)),
                        "vol_inrt": _to_float(item.get("vol_inrt", 0)),
                    }
                )
            return results
        except Exception as e:
            logger.error("거래량 순위 조회 실패: %s", e)
            return []

    def get_volume_power(self, count: int = 30) -> list[dict]:
        """체결강도 상위 종목 조회."""
        time.sleep(0.2)
        try:
            data = self._ranking_request(
                "/uapi/domestic-stock/v1/ranking/volume-power",
                "FHPST01680000",
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "20168",
                    "fid_input_iscd": "0001",
                    "fid_div_cls_code": "1",
                    "fid_trgt_cls_code": "0",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_input_price_1": "",
                    "fid_input_price_2": "",
                    "fid_vol_cnt": "",
                },
            )
            items = data.get("output", [])
            results = []
            for item in items[:count]:
                ticker = item.get("stck_shrn_iscd", "")
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "KR",
                        "currency": "KRW",
                        "exchange": "KRX",
                        "ticker": ticker,
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "rank": _to_int(item.get("data_rank", 0)),
                        "price": _to_float(item.get("stck_prpr", 0)),
                        "prdy_ctrt": _to_float(item.get("prdy_ctrt", 0)),
                        "tday_rltv": _to_float(item.get("tday_rltv", 0)),
                    }
                )
            return results
        except Exception as e:
            logger.error("체결강도 순위 조회 실패: %s", e)
            return []

    def get_fluctuation_rank(self, count: int = 30) -> list[dict]:
        """등락률 상위 종목 조회."""
        time.sleep(0.2)
        try:
            data = self._ranking_request(
                "/uapi/domestic-stock/v1/ranking/fluctuation",
                "FHPST01700000",
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "20170",
                    "fid_input_iscd": "0000",
                    "fid_rank_sort_cls_code": "0",
                    "fid_input_cnt_1": str(count),
                    "fid_prc_cls_code": "0",
                    "fid_input_price_1": "",
                    "fid_input_price_2": "",
                    "fid_vol_cnt": "",
                    "fid_trgt_cls_code": "0",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_div_cls_code": "0",
                    "fid_rsfl_rate1": "",
                    "fid_rsfl_rate2": "",
                },
            )
            items = data.get("output", [])
            results = []
            for item in items[:count]:
                ticker = item.get("stck_shrn_iscd", "")
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "KR",
                        "currency": "KRW",
                        "exchange": "KRX",
                        "ticker": ticker,
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "rank": _to_int(item.get("data_rank", 0)),
                        "price": _to_float(item.get("stck_prpr", 0)),
                        "prdy_ctrt": _to_float(item.get("prdy_ctrt", 0)),
                        "acml_vol": _to_int(item.get("acml_vol", 0)),
                        "cnnt_ascn_dynu": _to_int(item.get("cnnt_ascn_dynu", 0)),
                    }
                )
            return results
        except Exception as e:
            logger.error("등락률 순위 조회 실패: %s", e)
            return []

    def get_bulk_trans(self, count: int = 30) -> list[dict]:
        """대량체결건수 매수 상위 종목 조회."""
        time.sleep(0.2)
        try:
            data = self._ranking_request(
                "/uapi/domestic-stock/v1/ranking/bulk-trans-num",
                "FHKST190900C0",
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_cond_scr_div_code": "11909",
                    "fid_input_iscd": "0001",
                    "fid_rank_sort_cls_code": "0",
                    "fid_div_cls_code": "0",
                    "fid_input_price_1": "",
                    "fid_aply_rang_prc_1": "",
                    "fid_aply_rang_prc_2": "",
                    "fid_input_iscd_2": "",
                    "fid_trgt_exls_cls_code": "0",
                    "fid_trgt_cls_code": "0",
                    "fid_vol_cnt": "",
                },
            )
            items = data.get("output", [])
            results = []
            for item in items[:count]:
                ticker = item.get("mksc_shrn_iscd", "")
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "KR",
                        "currency": "KRW",
                        "exchange": "KRX",
                        "ticker": ticker,
                        "name": item.get("hts_kor_isnm", "").strip(),
                        "rank": _to_int(item.get("data_rank", 0)),
                        "price": _to_float(item.get("stck_prpr", 0)),
                        "prdy_ctrt": _to_float(item.get("prdy_ctrt", 0)),
                        "buy_cnt": _to_int(item.get("shnu_cntg_csnu", 0)),
                        "ntby_cnqn": _to_int(item.get("ntby_cnqn", 0)),
                    }
                )
            return results
        except Exception as e:
            logger.error("대량체결 순위 조회 실패: %s", e)
            return []

    # ── 미국 후보 조회 (KIS 우선, 실패 시 빈 리스트 반환) ─────

    def get_us_market_cap_rank(self, count: int = 30) -> list[dict]:
        """미국 시가총액 상위 후보 조회.

        한국투자 공식 문서 기준 이 API는 모의투자를 지원하지 않으므로
        실전 환경에서만 조회하고, 그 외에는 빈 리스트를 반환한다.
        """
        if not self.enable_us_trading or self.virtual:
            return []

        path = "/uapi/overseas-stock/v1/ranking/market-cap"
        tr_id = "HHDFS76350100"
        vol_rang = "0"

        results: list[dict] = []
        for exchange in self.us_exchange_search_order:
            ranking_exchange = self._ranking_exchange_code(exchange)
            try:
                data = self._request(
                    "GET",
                    path,
                    tr_id,
                    params={
                        "KEYB": "",
                        "AUTH": "",
                        "EXCD": ranking_exchange,
                        "VOL_RANG": vol_rang,
                    },
                )
            except Exception as e:
                logger.warning(
                    "US 시가총액 랭킹 조회 실패 exchange=%s: %s",
                    ranking_exchange,
                    str(e)[:120],
                )
                continue

            items = data.get("output2", [])
            if isinstance(items, dict):
                items = [items]

            for item in items:
                ticker = (item.get("symb") or item.get("rsym") or "").strip().upper()
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "US",
                        "currency": "USD",
                        "exchange": item.get("excd", ranking_exchange),
                        "ticker": ticker,
                        "name": (item.get("name") or item.get("ename") or ticker).strip(),
                        "rank": _to_int(item.get("rank", 0)),
                        "price": _to_float(item.get("last", 0)),
                        "prdy_ctrt": _to_float(item.get("rate", 0)),
                        "acml_vol": _to_int(item.get("tvol", 0)),
                        "market_cap": _to_float(item.get("tomv", 0)),
                        "weight": _to_float(item.get("grav", 0)),
                    }
                )

        if not results:
            return []

        # 중복 종목은 더 높은(숫자가 작은) 랭크를 우선
        deduped: dict[str, dict] = {}
        for item in results:
            existing = deduped.get(item["ticker"])
            if existing is None or (
                item.get("rank", 0) > 0
                and (
                    existing.get("rank", 0) <= 0
                    or item["rank"] < existing["rank"]
                )
            ):
                deduped[item["ticker"]] = item

        ranked = list(deduped.values())
        ranked.sort(
            key=lambda x: (
                x.get("rank", 0) <= 0,
                x.get("rank", 0) if x.get("rank", 0) > 0 else 10**9,
                -x.get("market_cap", 0),
            )
        )
        return ranked[:count]

    def get_us_volume_rank(self, count: int = 30) -> list[dict]:
        """미국 거래량 상위 후보 조회.

        한국투자 공식 문서 기준 이 API는 모의투자를 지원하지 않으므로
        실전 환경에서만 조회하고, 그 외에는 빈 리스트를 반환한다.
        """
        if not self.enable_us_trading or self.virtual:
            return []

        path = "/uapi/overseas-stock/v1/ranking/trade-vol"
        tr_id = "HHDFS76310010"
        nday = "0"
        prc1 = ""
        prc2 = ""
        vol_rang = "0"

        results: list[dict] = []
        for exchange in self.us_exchange_search_order:
            ranking_exchange = self._ranking_exchange_code(exchange)
            try:
                data = self._request(
                    "GET",
                    path,
                    tr_id,
                    params={
                        "KEYB": "",
                        "AUTH": "",
                        "EXCD": ranking_exchange,
                        "NDAY": nday,
                        "PRC1": prc1,
                        "PRC2": prc2,
                        "VOL_RANG": vol_rang,
                    },
                )
            except Exception as e:
                logger.warning(
                    "US 거래량 랭킹 조회 실패 exchange=%s: %s",
                    ranking_exchange,
                    str(e)[:120],
                )
                continue

            items = data.get("output2", [])
            if isinstance(items, dict):
                items = [items]

            for item in items:
                ticker = (item.get("symb") or item.get("rsym") or "").strip().upper()
                if not ticker:
                    continue
                results.append(
                    {
                        "market": "US",
                        "currency": "USD",
                        "exchange": item.get("excd", ranking_exchange),
                        "ticker": ticker,
                        "name": (item.get("name") or item.get("ename") or ticker).strip(),
                        "rank": _to_int(item.get("rank", 0)),
                        "price": _to_float(item.get("last", 0)),
                        "prdy_ctrt": _to_float(item.get("rate", 0)),
                        "acml_vol": _to_int(item.get("tvol", 0)),
                        "trade_amount": _to_float(item.get("tamt", 0)),
                        "avg_volume": _to_int(item.get("a_tvol", 0)),
                    }
                )

        if not results:
            return []

        deduped: dict[str, dict] = {}
        for item in results:
            existing = deduped.get(item["ticker"])
            if existing is None or (
                item.get("rank", 0) > 0
                and (
                    existing.get("rank", 0) <= 0
                    or item["rank"] < existing["rank"]
                )
            ):
                deduped[item["ticker"]] = item

        ranked = list(deduped.values())
        ranked.sort(
            key=lambda x: (
                x.get("rank", 0) <= 0,
                x.get("rank", 0) if x.get("rank", 0) > 0 else 10**9,
                -x.get("acml_vol", 0),
            )
        )
        return ranked[:count]

    # ── 보유종목 전량 매도 ────────────────────────────────────

    def sell_all_holdings(self, market: str = "ALL") -> list[dict]:
        """보유 종목 전량 시장가 매도 후 결과 리스트 반환."""
        balance = self.get_balance(market=market)
        holdings = balance.get("holdings", [])
        results: list[dict] = []

        for h in holdings:
            ticker = h["ticker"]
            qty = int(h["qty"])
            mkt = h.get("market", self.detect_market(ticker))
            if qty <= 0:
                continue

            try:
                sell_result = self.sell_stock(ticker, qty, market=mkt)
                try:
                    sell_price = self.get_price(ticker, market=mkt)
                except Exception:
                    sell_price = _to_float(h.get("current_price", 0))

                results.append(
                    {
                        "market": mkt,
                        "currency": h.get("currency", "KRW" if mkt == "KR" else "USD"),
                        "exchange": h.get("exchange", ""),
                        "ticker": ticker,
                        "name": h.get("name", ticker),
                        "qty": qty,
                        "avg_price": _to_float(h.get("avg_price", 0)),
                        "sell_price": _to_float(sell_price),
                        "success": sell_result.get("success", False),
                        "message": sell_result.get("message", ""),
                        "order_no": sell_result.get("order_no", ""),
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "market": mkt,
                        "currency": h.get("currency", "KRW" if mkt == "KR" else "USD"),
                        "exchange": h.get("exchange", ""),
                        "ticker": ticker,
                        "name": h.get("name", ticker),
                        "qty": qty,
                        "avg_price": _to_float(h.get("avg_price", 0)),
                        "sell_price": 0.0,
                        "success": False,
                        "message": str(e)[:200],
                        "order_no": "",
                    }
                )
            time.sleep(0.3)

        return results


# ── 유틸리티 ─────────────────────────────────────────────────


def format_krw(amount: float) -> str:
    """숫자를 한국 원화 축약 포맷으로 변환."""
    if abs(amount) >= 1_0000_0000_0000:
        return f"{amount / 1_0000_0000_0000:.1f}조"
    if abs(amount) >= 1_0000_0000:
        return f"{amount / 1_0000_0000:.1f}억"
    if abs(amount) >= 1_0000:
        return f"{amount / 1_0000:.0f}만"
    return f"{amount:,.0f}"


def format_usd(amount: float) -> str:
    """USD 표기 유틸리티."""
    return f"${amount:,.2f}"
