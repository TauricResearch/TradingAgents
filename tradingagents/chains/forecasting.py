"""TimesFM 2.5 wrapper with local SMA/EMA fallback (no hard dep). Supports 2.0.2 API."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# TimesFM 2.0.2 exposes ForecastConfig and timesfm_2p5 package.
# Earlier 2.5 code used timesfm.TimesFm / TimesFmHparams which no longer exists.
# Import must succeed only if a usable backend (torch) is available; otherwise fallback.
try:
    from timesfm import ForecastConfig  # type: ignore

    try:
        from timesfm.timesfm_2p5.timesfm_2p5_torch import TimesFM_2p5_200M_torch as _TimesFM_Torch  # type: ignore
    except ImportError:
        try:
            from timesfm import TimesFM_2p5_200M_torch as _TimesFM_Torch  # type: ignore  # re-exported
        except ImportError:
            _TimesFM_Torch = None  # type: ignore

    _HAS_TIMESFM = _TimesFM_Torch is not None
    if not _HAS_TIMESFM:
        ForecastConfig = None  # type: ignore
except ImportError:  # pragma: no cover
    ForecastConfig = None  # type: ignore
    _TimesFM_Torch = None  # type: ignore
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
        self._forecast_config = None
        self._load_attempted = False
        # Eager load only if a local checkpoint is provided; otherwise lazy-load on first predict
        # so from_pretrained can auto-download without blocking init and without requiring checkpoint_dir.
        if _HAS_TIMESFM and checkpoint_dir:
            self._try_load()
        elif not _HAS_TIMESFM:
            logger.warning("timesfm not installed or torch unavailable — SMA/EMA baseline")

    def _try_load(self) -> None:
        """Attempt to instantiate and compile the TimesFM model. No hard dependency."""
        if self._load_attempted or not _HAS_TIMESFM or _TimesFM_Torch is None or ForecastConfig is None:
            return
        self._load_attempted = True
        try:
            if self.checkpoint_dir:
                m = _TimesFM_Torch(torch_compile=False)  # type: ignore
                m.load_checkpoint(self.checkpoint_dir, torch_compile=False)  # type: ignore
            else:
                # Auto-download from Hugging Face hub (may fail offline -> fallback).
                m = _TimesFM_Torch.from_pretrained()  # type: ignore
            # Clamp context to model limit and patch alignment (patch=32, output=128).
            ctx = min(self.context_len, 16384 - 128)
            ctx = max(32, (ctx // 32) * 32)
            fc = ForecastConfig(max_context=ctx, max_horizon=128, per_core_batch_size=32)  # type: ignore
            m.compile(fc)  # type: ignore
            self._model = m
            self._forecast_config = fc
            logger.info("TimesFM loaded %s", self.checkpoint_dir or "from hub")
        except Exception as exc:  # pragma: no cover
            warnings.warn(f"TimesFM load failed ({exc}); fallback.")
            logger.warning("TimesFM load failed: %s", exc)
            self._model = None
            self._forecast_config = None

    def _ensure_model(self) -> None:
        if self._model is None and _HAS_TIMESFM and not self._load_attempted:
            self._try_load()

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
        self._ensure_model()
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
        # Recompile if horizon exceeds compiled max_horizon.
        if self._forecast_config is not None and horizon > self._forecast_config.max_horizon:
            try:
                import dataclasses

                new_h = int(((horizon + 127) // 128) * 128)
                new_h = min(new_h, 16384 - self._forecast_config.max_context)
                fc = dataclasses.replace(self._forecast_config, max_horizon=new_h)  # type: ignore
                self._model.compile(fc)  # type: ignore
                self._forecast_config = fc
            except Exception as exc:
                logger.warning("TimesFM recompile failed (%s) — fallback", exc)
                raise
        inputs = [arr[:, i].astype(float) for i in range(arr.shape[1])]
        point, q = self._model.forecast(horizon, inputs)  # type: ignore
        point = np.asarray(point)
        q_full = np.asarray(q) if q is not None else None
        # point: (N, H), q_full: (N, H, Q) — transpose to (H, N) convention.
        if point.ndim == 2 and point.shape[0] == arr.shape[1]:
            fc = point[0] if squeeze else point.T
        else:
            fc = np.asarray(point).reshape(horizon, -1)
            fc = fc[:, 0] if squeeze else fc
        if squeeze:
            fc = fc.reshape(horizon)
        q_arr = None
        if quantiles and q_full is not None and q_full.ndim == 3:
            lo, hi = 0, q_full.shape[-1] - 1
            if squeeze:
                lo_s = q_full[0, :, lo]
                hi_s = q_full[0, :, hi]
                mid_s = fc if fc.shape == lo_s.shape else q_full[0, :, q_full.shape[-1] // 2]
                q_arr = np.column_stack([lo_s, mid_s, hi_s])
            else:
                cols = []
                for c in range(arr.shape[1]):
                    cols.append(q_full[c, :, lo])
                    cols.append(point[c] if point.ndim == 2 else q_full[c, :, q_full.shape[-1] // 2])
                    cols.append(q_full[c, :, hi])
                q_arr = np.column_stack(cols)
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
