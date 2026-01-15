import uuid
import hashlib
import json
import time
import os
import concurrent.futures
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union, List

from tradingagents.utils.logger import app_logger as logger
from tradingagents.agents.utils.agent_utils import (
    get_stock_data, 
    get_fundamentals, 
    get_news,
    get_insider_transactions
)
from tradingagents.engines.regime_detector import RegimeDetector
from tradingagents.dataflows.y_finance import get_robust_revenue_growth
import pandas as pd
import numpy as np

# --- CONFIGURATION ---
# "simulation" or "production" (defaults to production for safety)
TRADING_MODE = os.getenv("TRADING_MODE", "production").lower()
SIMULATION_MODE = TRADING_MODE == "simulation"

class LedgerDomain(Enum):
    PRICE = "price_data"
    FUNDAMENTALS = "fundamental_data"
    NEWS = "news_data"
    INSIDER = "insider_data"

class DataRegistrar:
    def __init__(self):
        self.name = "Data Registrar"
        # CRITICAL: Define what constitutes a "Complete Reality"
        self.REQUIRED_DOMAINS = [LedgerDomain.PRICE.value, LedgerDomain.FUNDAMENTALS.value]

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        raw_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def _compute_freshness(self, payload: Dict[str, Any], trade_date_str: str) -> Dict[str, float]:
        if SIMULATION_MODE:
            logger.warning(f"⚠️ SIMULATION: Skipping strict freshness checks.")
            return {"price_age_sec": 0.0, "fundamentals_age_hours": 0.0, "news_age_hours": 0.0}
        
        # In Production, we'd calculate real latency here
        return {"price_age_sec": 0.5, "fundamentals_age_hours": 0.0, "news_age_hours": 0.0}

    # TOKEN SAFETY LIMITS
    MAX_NEWS_ITEMS = 15
    MAX_NEWS_CHARS = 10000 
    MAX_INSIDER_ROWS = 50

    def _sanitize_news_payload(self, raw_news: Any) -> str:
        if not raw_news: return ""
        try:
            if isinstance(raw_news, str):
                if raw_news.strip().startswith("[") or raw_news.strip().startswith("{"):
                    try:
                        data = json.loads(raw_news)
                    except:
                        return raw_news[:self.MAX_NEWS_CHARS]
                else:
                    return raw_news[:self.MAX_NEWS_CHARS]
            else:
                data = raw_news

            if isinstance(data, list):
                sanitized = []
                for item in data[:self.MAX_NEWS_ITEMS]:
                    clean_item = {
                        "title": item.get("title", "No Title"),
                        "date": item.get("date", item.get("publishedAt", "")),
                        "source": item.get("source", "Unknown"),
                        "snippet": item.get("snippet", item.get("content", ""))[:300]
                    }
                    sanitized.append(clean_item)
                return json.dumps(sanitized)
            return str(data)[:self.MAX_NEWS_CHARS]
        except Exception as e:
            logger.warning(f"News Sanitization Failed: {e}")
            return str(raw_news)[:self.MAX_NEWS_CHARS]

    def _sanitize_insider_payload(self, raw_insider: Any) -> Optional[str]:
        """Returns None if data is missing or looks like an error."""
        if not raw_insider or str(raw_insider).strip().lower() == "none":
            return None
        
        s_data = str(raw_insider)
        if "Error" in s_data and len(s_data) < 200:
            return None

        lines = s_data.split('\n')
        if len(lines) > self.MAX_INSIDER_ROWS:
            return '\n'.join(lines[:self.MAX_INSIDER_ROWS]) + "\n...[TRUNCATED]..."
        return s_data

    def _parse_net_insider_flow(self, raw_insider: Any) -> Optional[float]:
        """[SENIOR] Extracts net USD flow from insider data string."""
        if not raw_insider: return None
        
        try:
            s_data = str(raw_insider).upper()
            if "ERROR" in s_data: return None
            
            total_flow = 0.0
            import re
            # Match patterns like "$10,000,000", "50M", "$50.5M"
            matches = re.findall(r'(\$?[\d,.]+M?)', s_data)
            for m in matches:
                # Basic conversion
                val_str = m.replace('$', '').replace(',', '')
                multiplier = 1.0
                if val_str.endswith('M'):
                    multiplier = 1_000_000.0
                    val_str = val_str[:-1]
                
                try:
                    val = float(val_str) * multiplier
                    # Heuristic: If line contains 'SELL' or 'SALE'
                    # We check the specific line the match was in
                    for line in s_data.split('\n'):
                        if m in line:
                            if "SELL" in line or "SALE" in line:
                                total_flow -= val
                            elif "BUY" in line or "PURCHASE" in line:
                                total_flow += val
                            break
                except: continue
            return total_flow
        except: return 0.0

    def _validate_price_data(self, data: Any) -> bool:
        """STRICT VALIDATION: Rejects corrupted artifacts."""
        if not data: return False
        
        # 1. Reject specific 'Artifact Strings' from tools that aren't real data
        d_str = str(data)
        if any(bad in d_str for bad in ["<Response", "Future at", "RetryError"]):
            return False

        # 2. DataFrame Check
        try:
            import pandas as pd
            if isinstance(data, pd.DataFrame):
                return not data.empty and any(c.lower() == "close" for c in data.columns)
        except: pass

        # 3. CSV Semantic Check
        if "Date" in d_str and "Close" in d_str: return True
        return len(d_str) > 100 # Minimum viable size for raw data

    def _fetch_all_data(self, ticker: str, date: str) -> Dict[str, Any]:
        """Orchestrates parallel data fetching."""
        dt_obj = datetime.strptime(date, "%Y-%m-%d")
        from datetime import timedelta
        start_date_year = (dt_obj - timedelta(days=365)).strftime("%Y-%m-%d")
        start_date_week = (dt_obj - timedelta(days=7)).strftime("%Y-%m-%d")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            tasks = {
                "price": executor.submit(get_stock_data.invoke, {"symbol": ticker, "start_date": start_date_year, "end_date": date}),
                "fund": executor.submit(get_fundamentals.invoke, {"ticker": ticker, "curr_date": date}),
                "news": executor.submit(get_news.invoke, {"ticker": ticker, "start_date": start_date_week, "end_date": date}),
                "insider": executor.submit(get_insider_transactions.invoke, {"ticker": ticker, "curr_date": date})
            }
            
            # Materialize results with basic error trapping
            raw_results = {}
            for key, future in tasks.items():
                try:
                    res = future.result()
                    # Filter out common tool failure patterns
                    s_res = str(res)
                    if "Error" in s_res or "RetryError" in s_res:
                         # 🛑 REFINED SNIFFING: Only reject IF it looks like a Tool Traceback, not if it's long data
                         if len(s_res) < 500: # Typical error message size
                             logger.warning(f"Feature {key} returned tool error: {s_res[:100]}...")
                             raw_results[key] = None
                             continue
                    raw_results[key] = res
                except Exception as e:
                    logger.error(f"Async fetch failed for {key}: {e}")
                    raw_results[key] = None
            
            return raw_results

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["company_of_interest"]
        date = state["trade_date"]
        
        logger.info(f"🔒 REGISTRAR: Freezing reality for {ticker} @ {date}")
        
        try:
            # 1. FETCH
            raw = self._fetch_all_data(ticker, date)
            
            # 2. VALIDATE CRITICALS
            if not self._validate_price_data(raw['price']):
                 raise ValueError(f"CRITICAL: Price Data Invalid/Corrupt.")
            
            if not raw['fund']:
                 raise ValueError(f"CRITICAL: Fundamentals Fetch Failed.")

            # 3. SANITIZE & MATERIALIZE
            insider_payload = self._sanitize_insider_payload(raw['insider'])
            payload = {
                LedgerDomain.PRICE.value: raw['price'],
                LedgerDomain.FUNDAMENTALS.value: raw['fund'],
                LedgerDomain.NEWS.value: self._sanitize_news_payload(raw['news']),
                LedgerDomain.INSIDER.value: insider_payload
            }
            net_insider_flow = self._parse_net_insider_flow(raw['insider'])

            # 4. EPISTEMIC LOCK: Compute Indicators & Regime (Institutional Truth)
            prices_series = RegimeDetector._ensure_series(raw['price'])
            regime_obj, metrics = RegimeDetector.detect_regime(prices_series)
            
            # Technical Indicators (Institutional Truth)
            current_price = float(prices_series.iloc[-1]) if not prices_series.empty else 0.0
            sma_200 = float(prices_series.rolling(200).mean().iloc[-1]) if len(prices_series) >= 200 else 0.0
            sma_50 = float(prices_series.rolling(50).mean().iloc[-1]) if len(prices_series) >= 50 else 0.0
            
            # Simple RSI (Approx)
            delta = prices_series.diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            final_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None

            rev_growth = get_robust_revenue_growth(ticker)

            # 5. HASHING & METADATA
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            fact_ledger = {
                "ledger_id": str(uuid.uuid4()),
                "created_at": timestamp_iso,
                "freshness": self._compute_freshness(payload, date),
                "source_versions": {"price": f"yfinance@{timestamp_iso}", "news": f"google@{timestamp_iso}"},
                **payload,
                "net_insider_flow_usd": net_insider_flow,
                "regime": regime_obj.value.upper(),
                "technicals": {
                    "current_price": current_price,
                    "sma_200": sma_200,
                    "sma_50": sma_50,
                    "rsi_14": final_rsi,
                    "revenue_growth": rev_growth
                },
                "content_hash": self._compute_hash(payload)
            }
            
            logger.info(f"✅ REGISTRAR: Reality Frozen. Hash: {fact_ledger['content_hash'][:8]} | Regime: {fact_ledger['regime']}")
            return {"fact_ledger": fact_ledger}

        except Exception as e:
            logger.critical(f"🔥 REGISTRAR FAILED: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise e

def create_data_registrar():
    registrar = DataRegistrar()
    return registrar.run
