"""TimesFM 2.5 wrapper with local SMA/EMA fallback (no hard dep)."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import timesfm  # type: ignore

    _HAS_TIMESFM = True
except ImportError:  # pragma: no cover
    timesfm = None  # type: ignore
    _HAS_TIMESFM = False


@dataclass
class ForecastResult:
    forecast: np.ndarray  # (horizon,) or (horizon, N)
    quantiles: Optional[np.ndarray] = None  # (horizon, 3) or None
    method: str = "unknown"


class TimesFMForecaster:
    """TimesFM 2.5 with fallback. Supports univariate and multivariate."""

    def __init__(self, checkpoint_dir: Optional[str] = None, context_len: int = 512, backend: str = "cpu") -> None:
        self.checkpoint_dir = checkpoint_dir
        self.context_len = context_len
        self.backend = backend
        self._model = None
        if _HAS_TIMESFM and checkpoint_dir:
            try:
                self._model = timesfm.TimesFm(  # type: ignore
                    hparams=timesfm.TimesFmHparams(backend=backend, per_core_batch_size=32, horizon_len=128, input_patch_len=32, context_len=context_len, use_positional_embedding=False),  # type: ignore
                    checkpoint=timesfm.TimesFmCheckpoint(hparams=timesfm.TimesFmHparams(backend=backend), path=checkpoint_dir),  # type: ignore
                )
                logger.info("TimesFM loaded from %s", checkpoint_dir)
            except Exception as exc:  # pragma: no cover
                warnings.warn(f"TimesFM load failed ({exc}); fallback.")
                logger.warning("TimesFM load failed: %s", exc)
        elif not _HAS_TIMESFM:
            logger.warning("timesfm not installed — SMA/EMA baseline")

    def predict(self, series: np.ndarray, horizon: int, quantiles: bool = False) -> ForecastResult:
        arr = np.asarray(series, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
            squeeze = True
        elif arr.ndim == 2:
            squeeze = False
        else:
            raise ValueError(f"series must be 1-D or 2-D, got {arr.shape}")
        if arr.shape[0] == 0:
            raise ValueError("series is empty")
        if horizon <= 0:
            raise ValueError("horizon must be > 0")
        arr = pd.DataFrame(arr).ffill().bfill().to_numpy()
        if arr.shape[0] > self.context_len:
            arr = arr[-self.context_len :]
        if self._model is not None:
            try:
                return self._predict_timesfm(arr, horizon, quantiles, squeeze)
            except Exception as exc:  # pragma: no cover
                logger.warning("TimesFM predict failed (%s) — fallback", exc)
        return self._predict_fallback(arr, horizon, quantiles, squeeze)

    def forecast_fx_rate(self, base: str, quote: str, horizon: int = 5, lookback_days: int = 60, quantiles: bool = False) -> ForecastResult:
        """Forecast FX rate using MultiCurrencyFXProvider history as context."""
        try:
            from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider

            p = MultiCurrencyFXProvider()
            hist = p.get_historical_rates(base, quote, days=lookback_days)
            p.close()
            if hist:
                return self.predict(np.array([r.rate for r in hist], dtype=float), horizon=horizon, quantiles=quantiles)
        except Exception as exc:
            logger.debug("forecast_fx_rate fallback: %s", exc)
        return self.predict(np.array([1.0]), horizon=horizon, quantiles=quantiles)

    def forecast_rate_spread(self, target_country: str, funding_country: str = "US", horizon: int = 5, quantiles: bool = False) -> ForecastResult:
        """Forecast interest-rate spread (target - funding) as covariates."""
        try:
            from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider

            p = GlobalInterestRatesProvider()
            rates = p.get_all_rates()
            p.close()
            tgt, fnd = rates.get(target_country.upper()), rates.get(funding_country.upper())
            if tgt and fnd:
                return self.predict(np.full(30, float(tgt.rate - fnd.rate)), horizon=horizon, quantiles=quantiles)
        except Exception as exc:
            logger.debug("forecast_rate_spread fallback: %s", exc)
        return self.predict(np.array([0.0]), horizon=horizon, quantiles=quantiles)

    def _predict_timesfm(self, arr: np.ndarray, horizon: int, quantiles: bool, squeeze: bool) -> ForecastResult:
        freq = [0] * arr.shape[0]
        forecast, q = self._model.forecast(inputs=[arr[:, i] for i in range(arr.shape[1])], freq=freq)  # type: ignore
        fc = np.asarray(forecast)
        if squeeze:
            fc = fc.reshape(horizon)
        q_arr = np.asarray(q) if quantiles and q is not None else None
        return ForecastResult(forecast=fc, quantiles=q_arr, method="timesfm")

    @staticmethod
    def _predict_fallback(arr: np.ndarray, horizon: int, quantiles: bool, squeeze: bool) -> ForecastResult:
        n_series = arr.shape[1]
        forecasts = []
        for col in range(n_series):
            d = arr[:, col]
            if len(d) >= 20:
                sma = float(np.mean(d[-20:]))
                ema = float(pd.Series(d).ewm(span=10, adjust=False).mean().iloc[-1])
                level = 0.6 * sma + 0.4 * ema
            else:
                level = float(d[-1]) if len(d) else 0.0
            forecasts.append(np.full(horizon, level, dtype=float))
        fc = forecasts[0] if n_series == 1 and squeeze else np.column_stack(forecasts)
        q_arr = None
        if quantiles:
            stds = [max(float(np.std(arr[:, c])) if len(arr) > 1 else 0.0, abs(float(np.mean(arr[:, c]))) * 0.01, 1e-6) for c in range(n_series)]
            if n_series == 1 and squeeze:
                q_arr = np.column_stack([fc - 1.28 * stds[0], fc, fc + 1.28 * stds[0]])
            else:
                qs = []
                for h in range(horizon):
                    row = []
                    for c, s in enumerate(stds):
                        row.extend([fc[h, c] - 1.28 * s, fc[h, c], fc[h, c] + 1.28 * s])
                    qs.append(row)
                q_arr = np.array(qs, dtype=float)
        method = "sma" if arr.shape[0] >= 20 else "naive"
        return ForecastResult(forecast=fc, quantiles=q_arr, method=method)
