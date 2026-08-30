"""CarryTradeEnv — Gym-style, no hard gym dep, synthetic fallback."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Tuple
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)
try:
    import gymnasium as gym  # type: ignore
    from gymnasium.spaces import Box  # type: ignore
    _HAS_GYM = True
except ImportError:
    try:
        import gym  # type: ignore
        from gym.spaces import Box  # type: ignore
        _HAS_GYM = True
    except ImportError:
        gym = None  # type: ignore
        Box = None  # type: ignore
        _HAS_GYM = False

def _synthetic_series(n: int = 200, n_assets: int = 3, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 0.5, size=(n, n_assets)), axis=0)
    return pd.DataFrame(base, columns=[f"asset_{i}" for i in range(n_assets)])

@dataclass
class EnvConfig:
    n_assets: int = 3
    transaction_cost: float = 0.001
    max_steps: int = 200

class CarryTradeEnv:
    """State [fx_returns, rate_spread, TimesFM forecast, vol]; Action target weights; Reward PnL-cost."""
    metadata = {"render_modes": []}
    def __init__(self, price_data: pd.DataFrame | None = None, rate_spread: pd.DataFrame | np.ndarray | None = None, config: EnvConfig | None = None) -> None:
        self.config = config or EnvConfig()
        self.n_assets, self.tc = self.config.n_assets, self.config.transaction_cost
        if price_data is None:
            try:
                from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
                p = MultiCurrencyFXProvider(); price_data = _synthetic_series(n=self.config.max_steps, n_assets=self.n_assets); p.close()
            except Exception:
                price_data = _synthetic_series(n=self.config.max_steps, n_assets=self.n_assets)
        if isinstance(price_data, pd.Series):
            price_data = price_data.to_frame()
        price_data = pd.DataFrame(price_data).ffill().bfill().fillna(100.0)
        if price_data.shape[1] < self.n_assets:
            for i in range(price_data.shape[1], self.n_assets):
                price_data[f"asset_{i}"] = price_data.iloc[:, -1]
        self.price_data = price_data.iloc[:, : self.n_assets].reset_index(drop=True)
        self.n_steps = len(self.price_data)
        if rate_spread is None:
            rate_spread = np.zeros((self.n_steps, self.n_assets))
        if isinstance(rate_spread, pd.DataFrame):
            rate_spread = rate_spread.to_numpy()
        self.rate_spread = np.asarray(rate_spread, dtype=float)
        if self.rate_spread.shape[0] != self.n_steps:
            self.rate_spread = np.zeros((self.n_steps, self.n_assets))
        obs_dim = self.n_assets * 4
        if _HAS_GYM and Box is not None:
            self.observation_space = Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
            self.action_space = Box(low=0, high=1, shape=(self.n_assets,), dtype=np.float32)
        else:
            self.observation_space = {"shape": (obs_dim,), "low": -float("inf"), "high": float("inf")}
            self.action_space = {"shape": (self.n_assets,), "low": 0, "high": 1}
        self.current_step = 0
        self.prev_weights = np.full(self.n_assets, 1.0 / self.n_assets)
    def _get_forecast(self) -> np.ndarray:
        try:
            from tradingagents.chains.forecasting import TimesFMForecaster
            vals = []
            for c in range(self.n_assets):
                hist = self.price_data.iloc[max(0, self.current_step - 30): self.current_step + 1, c].to_numpy()
                if len(hist) < 2:
                    hist = self.price_data.iloc[:, c].to_numpy()[:10]
                vals.append(float(np.mean(TimesFMForecaster().predict(hist, horizon=1).forecast)))
            return np.array(vals, dtype=float)
        except Exception:
            return self.price_data.iloc[self.current_step].to_numpy(dtype=float) * 0.01
    def _get_obs(self) -> np.ndarray:
        idx = self.current_step
        if idx > 0:
            prev, cur = self.price_data.iloc[idx - 1].to_numpy(dtype=float), self.price_data.iloc[idx].to_numpy(dtype=float)
            rets = (cur - prev) / np.clip(np.abs(prev), 1e-6, None)
        else:
            rets = np.zeros(self.n_assets)
        spread = self.rate_spread[idx] if idx < len(self.rate_spread) else np.zeros(self.n_assets)
        forecast = self._get_forecast()
        w = min(20, idx + 1)
        if w > 1:
            window = self.price_data.iloc[max(0, idx - w + 1): idx + 1].to_numpy(dtype=float)
            vol = np.nan_to_num(np.std(np.diff(window, axis=0) / np.clip(np.abs(window[:-1]), 1e-6, None), axis=0), nan=0.01)
            if len(vol) < self.n_assets:
                vol = np.pad(vol, (0, self.n_assets - len(vol)), constant_values=0.01)
        else:
            vol = np.full(self.n_assets, 0.01)
        return np.concatenate([rets, spread[:self.n_assets], forecast[:self.n_assets], vol[:self.n_assets]]).astype(np.float32)
    def reset(self, seed: int | None = None, **kwargs: Any) -> Tuple[np.ndarray, dict]:
        if seed is not None:
            np.random.seed(seed)
        self.current_step, self.prev_weights = 0, np.full(self.n_assets, 1.0 / self.n_assets)
        return self._get_obs(), {}
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        w = np.clip(np.nan_to_num(np.asarray(action, dtype=float).ravel(), nan=0.0, posinf=0.0, neginf=0.0), 0, None)
        s = w.sum()
        w = w / s if s > 1e-12 else np.full(self.n_assets, 1.0 / self.n_assets)
        idx = self.current_step
        if idx + 1 < self.n_steps:
            nxt, cur = self.price_data.iloc[idx+1].to_numpy(dtype=float), self.price_data.iloc[idx].to_numpy(dtype=float)
            pnl = float(np.dot(w, (nxt - cur) / np.clip(np.abs(cur), 1e-6, None)))
        else:
            pnl = 0.0
        cost = float(np.abs(w - self.prev_weights).sum() * self.tc)
        reward = pnl - cost
        self.prev_weights = w
        self.current_step += 1
        terminated = self.current_step >= self.n_steps - 1
        shape = self.observation_space["shape"] if isinstance(self.observation_space, dict) else self.observation_space.shape
        obs = self._get_obs() if not terminated else np.zeros(shape, dtype=np.float32)
        return obs, float(reward), bool(terminated), False, {"pnl": pnl, "cost": cost, "weights": w}
    def render(self) -> None:
        pass
