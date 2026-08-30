"""FinRL-X weight-centric allocators: w = R(T(A(S(market))))."""
from __future__ import annotations
import logging, warnings
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)
try:
    import gymnasium as gym  # type: ignore
    _HAS_GYM = True
except ImportError:
    try:
        import gym  # type: ignore
        _HAS_GYM = True
    except ImportError:
        gym = None  # type: ignore
        _HAS_GYM = False
try:
    import stable_baselines3  # type: ignore
    _HAS_SB3 = True
except ImportError:
    _HAS_SB3 = False

def _sanitize_weights(w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, dtype=float).ravel()
    w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
    w = np.clip(w, 0, None)
    s = w.sum()
    if s <= 1e-12:
        n = len(w) if len(w) else 1
        return np.full(n, 1.0 / n, dtype=float)
    return w / s

def apply_risk_overlay(weights: np.ndarray, max_leverage: float = 1.0, stop_loss_vol: float | None = None, trailing_stop_pct: float | None = None, current_vol: float | None = None) -> np.ndarray:
    """R() cap leverage + vol stop (delevers, sum may be <1)."""
    w = _sanitize_weights(np.asarray(weights, dtype=float))
    scaled = False
    if float(w.sum()) > max_leverage > 0:
        w = w * (max_leverage / float(w.sum()))
        scaled = True
    if stop_loss_vol is not None and current_vol is not None and current_vol > stop_loss_vol:
        f = 0.5 if trailing_stop_pct is None else max(0.0, 1 - trailing_stop_pct)
        w = w * f
        scaled = True
        logger.warning("risk overlay: vol %.4f>%.4f scaled", current_vol, stop_loss_vol)
    if scaled:
        w = np.clip(np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0), 0, None)
        return w
    return w

class WeightAllocator(ABC):
    @abstractmethod
    def allocate(self, features: pd.DataFrame | np.ndarray) -> np.ndarray: ...
    def _infer_n_assets(self, features: pd.DataFrame | np.ndarray) -> int:
        if isinstance(features, pd.DataFrame):
            return features.shape[1] if features.shape[1] > 0 else 1
        arr = np.asarray(features)
        return 1 if arr.ndim == 1 else (arr.shape[1] if arr.ndim == 2 else int(arr.size))

class EqualWeightAllocator(WeightAllocator):
    def allocate(self, features: pd.DataFrame | np.ndarray) -> np.ndarray:
        n = self._infer_n_assets(features)
        return np.full(n, 1.0 / n, dtype=float)

class MeanVarianceAllocator(WeightAllocator):
    def __init__(self, risk_aversion: float = 1.0) -> None:
        self.risk_aversion = max(risk_aversion, 1e-6)
    def allocate(self, features: pd.DataFrame | np.ndarray) -> np.ndarray:
        arr = features.to_numpy(dtype=float) if isinstance(features, pd.DataFrame) else np.asarray(features, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        if arr.shape[0] < 2:
            return _sanitize_weights(np.ones(arr.shape[1]))
        mu, var = np.mean(arr, axis=0), np.clip(np.var(arr, axis=0), 1e-6, None)
        return _sanitize_weights(mu / (self.risk_aversion * var))

class DRLAllocator(WeightAllocator):
    """PPO/SAC stub; fallback equal-weight if SB3/gym missing. Obs= forecast+spread+momentum, action=weight delta. Reward = pnl_net - cost."""
    def __init__(self, n_assets: int = 3, lookback: int = 30, model_name: str = "PPO") -> None:
        self.n_assets = max(1, int(n_assets))
        self.lookback = lookback
        self.model_name = model_name
        self._model = None
        self._bias: dict[str, float] = {}
        self._reward_fn = lambda pnl_net, cost: float(pnl_net - cost)
        if not _HAS_SB3:
            warnings.warn("stable-baselines3 not installed — DRLAllocator fallback to equal-weight")
        if not _HAS_GYM:
            warnings.warn("gym/gymnasium not installed — DRLAllocator fallback to equal-weight")
    def _box(self, low, high, shape):
        if _HAS_GYM and gym is not None:
            for mod in ("gymnasium.spaces", "gym.spaces"):
                try:
                    import importlib
                    Box = importlib.import_module(mod).Box
                    return Box(low=low, high=high, shape=shape, dtype=np.float32)
                except Exception:
                    continue
        return {"shape": shape, "low": low, "high": high}
    @property
    def observation_space(self):
        return self._box(-np.inf, np.inf, (self.n_assets * 3,))
    @property
    def action_space(self):
        return self._box(-1, 1, (self.n_assets,))
    @property
    def action(self):
        return self.action_space
    def _build_observation(self, features: pd.DataFrame | np.ndarray) -> np.ndarray:
        arr = features.to_numpy(dtype=float) if isinstance(features, pd.DataFrame) else np.asarray(features, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        win = arr[-self.lookback :] if len(arr) >= self.lookback else arr
        try:
            from tradingagents.chains.forecasting import TimesFMForecaster
            fc = []
            for c in range(min(win.shape[1], self.n_assets)):
                fc.append(float(np.mean(TimesFMForecaster().predict(win[:, c], horizon=1).forecast)))
            fc += [0.0] * (self.n_assets - len(fc))
            forecast = np.array(fc[: self.n_assets], dtype=float)
        except Exception:
            forecast = np.mean(win, axis=0)[: self.n_assets]
            forecast = np.pad(forecast, (0, max(0, self.n_assets - len(forecast))))
        spread = win[-1, : self.n_assets] if win.shape[1] >= self.n_assets else np.zeros(self.n_assets)
        spread = np.pad(spread, (0, max(0, self.n_assets - len(spread))))
        rets = np.diff(win, axis=0) / np.clip(np.abs(win[:-1]), 1e-6, None) if len(win) > 1 else np.zeros((1, self.n_assets))
        mom = np.mean(rets, axis=0)[: self.n_assets] if rets.size else np.zeros(self.n_assets)
        mom = np.pad(mom, (0, max(0, self.n_assets - len(mom))))
        return np.concatenate([forecast, spread, mom]).astype(np.float32)
    def allocate(self, features: pd.DataFrame | np.ndarray) -> np.ndarray:
        if self._model is not None and _HAS_SB3:
            try:
                obs = self._build_observation(features)
                act, _ = self._model.predict(obs, deterministic=True)  # type: ignore
                w = _sanitize_weights(np.asarray(act, dtype=float))
                return self._apply_bias(w, features)
            except Exception as exc:
                logger.warning("DRL predict failed (%s)", exc)
        n = self._infer_n_assets(features)
        self.n_assets = n
        w = _sanitize_weights(np.ones(n, dtype=float))
        return self._apply_bias(w, features)

    def _apply_bias(self, w: np.ndarray, features) -> np.ndarray:
        if not self._bias:
            return w
        # heuristic: reduce weight for symbols with hit_rate <0.5
        if isinstance(features, pd.DataFrame):
            cols = list(features.columns[: len(w)])
            factors = np.array([self._bias.get(str(c), 1.0) for c in cols], dtype=float)
            w = w * factors
            return _sanitize_weights(w)
        # ndarray: apply global factor (mean bias)
        g = float(np.mean(list(self._bias.values()))) if self._bias else 1.0
        if g < 1.0:
            w = w * g
            # renormalize to keep sum 1
            return _sanitize_weights(w)
        return w

    def update_from_outcomes(self, outcomes: list) -> dict:
        """Heuristic learning: if hit_rate <0.5 reduce allocation to that currency."""
        if not outcomes:
            return {}
        groups: dict[str, list] = {}
        for o in outcomes:
            sym = str(o.get("symbol", "") or o.get("currency", "") or "unknown")
            groups.setdefault(sym, []).append(o)
        for sym, rows in groups.items():
            pnls = [float(r.get("pnl_net", 0)) for r in rows]
            hit = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0.5
            # reward = pnl_net - cost is already used for pnl_net; heuristic scales
            self._bias[sym] = 0.7 if hit < 0.5 else min(1.2, 1.0 + (hit - 0.5))
        return dict(self._bias)

    def compute_reward(self, pnl_net: float, cost: float) -> float:
        return self._reward_fn(float(pnl_net), float(cost))
    def load_model(self, path: str) -> None:
        if not _HAS_SB3:
            warnings.warn("SB3 not installed — cannot load model")
            return
        try:
            import stable_baselines3  # type: ignore
            cls = getattr(stable_baselines3, self.model_name, None)
            if cls:
                self._model = cls.load(path)  # type: ignore
        except Exception as exc:
            logger.warning("load_model failed: %s", exc)
