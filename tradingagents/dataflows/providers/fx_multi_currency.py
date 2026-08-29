"""
Multi-Currency FX Provider
---------------------------
Real-time and historical FX rates for global carry trade.

Sources:
- ExchangeRate-API (free tier: 1500 requests/month)
- Fixer.io (free tier: 100 requests/month)
- Frankfurter (free, no key required, ECB data)
- Yahoo Finance (via yfinance for cross-rates)
"""

import os
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class FXRate:
    """FX rate data"""
    base_currency: str
    quote_currency: str
    rate: float
    timestamp: str
    source: str
    inverse_rate: Optional[float] = None


class MultiCurrencyFXProvider:
    """Provider for multi-currency FX rates"""
    
    # Free API endpoints
    FRANKFURTER_BASE = "https://api.frankfurter.app"
    EXCHANGERATE_BASE = "https://v6.exchangerate-api.com/v6"
    
    # All supported currencies
    SUPPORTED_CURRENCIES = [
        "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY",
        "ARS", "BRL", "MXN", "CLP", "INR", "TRY", "ZAR", "KRW",
        "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "ILS", "SGD",
        "HKD", "NZD", "THB", "IDR", "MYR", "PHP", "VND",
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        self.exchangerate_api_key = config.get(
            "exchangerate_api_key",
            os.getenv("EXCHANGERATE_API_KEY", "")
        )
        self.fixer_api_key = config.get(
            "fixer_api_key",
            os.getenv("FIXER_API_KEY", "")
        )
        self.timeout = config.get("timeout", 10)
        self._client = httpx.Client(timeout=self.timeout)
        
        # Cache
        self._rates_cache: Dict[str, FXRate] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)
    
    def get_health(self) -> Dict:
        """Check provider health"""
        try:
            response = self._client.get(f"{self.FRANKFURTER_BASE}/latest?from=USD")
            return {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "provider": "multi_currency_fx",
                "sources": ["frankfurter", "exchangerate-api", "fixer"],
                "api_keys_configured": {
                    "exchangerate": bool(self.exchangerate_api_key),
                    "fixer": bool(self.fixer_api_key),
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": "multi_currency_fx",
                "error": str(e),
            }
    
    def get_rate(self, base: str, quote: str) -> Optional[FXRate]:
        """Get FX rate between two currencies"""
        base = base.upper()
        quote = quote.upper()
        
        if base == quote:
            return FXRate(
                base_currency=base,
                quote_currency=quote,
                rate=1.0,
                timestamp=datetime.now().isoformat(),
                source="identity",
            )
        
        # Check cache
        cache_key = f"{base}_{quote}"
        if cache_key in self._rates_cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                return self._rates_cache[cache_key]
        
        # Try sources in order
        rate = None
        
        # 1. Frankfurter (free, no key, ECB data)
        if rate is None:
            rate = self._fetch_frankfurter(base, quote)
        
        # 2. ExchangeRate-API (free tier)
        if rate is None and self.exchangerate_api_key:
            rate = self._fetch_exchangerate(base, quote)
        
        # 3. Cross-rate calculation via USD
        if rate is None:
            rate = self._calculate_cross_rate(base, quote)
        
        # Cache the result
        if rate:
            self._rates_cache[cache_key] = rate
            self._cache_time = datetime.now()
        
        return rate
    
    def _fetch_frankfurter(self, base: str, quote: str) -> Optional[FXRate]:
        """Fetch from Frankfurter API (free, ECB data)"""
        try:
            url = f"{self.FRANKFURTER_BASE}/latest?from={base}&to={quote}"
            response = self._client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if quote in data.get("rates", {}):
                    return FXRate(
                        base_currency=base,
                        quote_currency=quote,
                        rate=data["rates"][quote],
                        timestamp=data.get("date", datetime.now().strftime("%Y-%m-%d")),
                        source="frankfurter",
                    )
        except Exception as e:
            print(f"[MultiCurrencyFX] Frankfurter error: {e}")
        
        return None
    
    def _fetch_exchangerate(self, base: str, quote: str) -> Optional[FXRate]:
        """Fetch from ExchangeRate-API (free tier)"""
        try:
            url = f"{self.EXCHANGERATE_BASE}/{self.exchangerate_api_key}/pair/{base}/{quote}"
            response = self._client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "success":
                    return FXRate(
                        base_currency=base,
                        quote_currency=quote,
                        rate=data["conversion_rate"],
                        timestamp=data.get("time_last_update_utc", ""),
                        source="exchangerate-api",
                    )
        except Exception as e:
            print(f"[MultiCurrencyFX] ExchangeRate-API error: {e}")
        
        return None
    
    def _calculate_cross_rate(self, base: str, quote: str) -> Optional[FXRate]:
        """Calculate cross rate via USD"""
        try:
            # Get both rates against USD
            base_usd = self._fetch_frankfurter("USD", base)
            quote_usd = self._fetch_frankfurter("USD", quote)
            
            if base_usd and quote_usd:
                # Cross rate = (USD->quote) / (USD->base)
                cross_rate = quote_usd.rate / base_usd.rate
                
                return FXRate(
                    base_currency=base,
                    quote_currency=quote,
                    rate=cross_rate,
                    timestamp=datetime.now().isoformat(),
                    source="cross_rate",
                    inverse_rate=1.0 / cross_rate,
                )
        except Exception as e:
            print(f"[MultiCurrencyFX] Cross rate calculation error: {e}")
        
        return None
    
    def get_all_rates(self, base: str = "USD") -> Dict[str, FXRate]:
        """Get all rates against a base currency"""
        rates = {}
        
        for currency in self.SUPPORTED_CURRENCIES:
            if currency != base:
                rate = self.get_rate(base, currency)
                if rate:
                    rates[currency] = rate
        
        return rates
    
    def get_carry_trade_rate(
        self,
        funding_currency: str,
        target_currency: str,
        funding_rate: float,
        target_rate: float,
    ) -> Dict:
        """
        Calculate carry trade return including FX impact.
        
        Returns:
            Dict with carry trade metrics
        """
        # Get current FX rate
        fx_rate = self.get_rate(funding_currency, target_currency)
        if not fx_rate:
            return {"error": "FX rate not available"}
        
        # Calculate expected carry return
        # Carry = (target_rate - funding_rate) + FX appreciation
        interest_differential = target_rate - funding_rate
        
        return {
            "funding_currency": funding_currency,
            "target_currency": target_currency,
            "current_fx_rate": fx_rate.rate,
            "fx_inverse": 1.0 / fx_rate.rate,
            "funding_rate": funding_rate,
            "target_rate": target_rate,
            "interest_differential": interest_differential,
            "interest_differential_pct": interest_differential,
            "fx_source": fx_rate.source,
            "timestamp": fx_rate.timestamp,
        }
    
    def get_historical_rates(
        self,
        base: str,
        quote: str,
        days: int = 30,
    ) -> List[FXRate]:
        """Get historical FX rates"""
        rates = []
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = (
                f"{self.FRANKFURTER_BASE}/{start_date.strftime('%Y-%m-%d')}"
                f"..{end_date.strftime('%Y-%m-%d')}"
                f"?from={base}&to={quote}"
            )
            response = self._client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                for date, rate_value in data.get("rates", {}).items():
                    rates.append(FXRate(
                        base_currency=base,
                        quote_currency=quote,
                        rate=rate_value.get(quote, 0),
                        timestamp=date,
                        source="frankfurter",
                    ))
        except Exception as e:
            print(f"[MultiCurrencyFX] Historical rates error: {e}")
        
        return rates
    
    def get_fx_volatility(
        self,
        base: str,
        quote: str,
        days: int = 30,
    ) -> Optional[float]:
        """Calculate FX volatility (standard deviation of returns)"""
        import statistics
        
        historical = self.get_historical_rates(base, quote, days)
        if len(historical) < 2:
            return None
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(historical)):
            prev_rate = historical[i-1].rate
            curr_rate = historical[i].rate
            if prev_rate > 0:
                returns.append((curr_rate - prev_rate) / prev_rate)
        
        if len(returns) < 2:
            return None
        
        return statistics.stdev(returns)
    
    def close(self):
        """Close HTTP client"""
        self._client.close()
