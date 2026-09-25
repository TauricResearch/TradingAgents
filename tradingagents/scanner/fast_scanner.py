"""Fast crypto scanner for Binance OHLCV data.

The scanner is intentionally rule-based and cheap: it reduces the number of
deep LLM/analyzer calls by only emitting actionable setup candidates when basic
technical conditions are strong enough.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import _fetch_ohlcv
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG


@dataclass
class ScanSignal:
    """A scanner output that can trigger deeper analysis."""

    symbol: str
    timeframe: str
    strategy: str
    action: str
    strength: float
    entry: float
    stop_loss: float
    take_profit: float
    rsi: float
    atr: float
    volume_spike: float
    market_regime: str
    reason: str
    timestamp_utc: str

    def to_dict(self) -> Dict:
        return asdict(self)


class FastCryptoScanner:
    """Scan crypto pairs for simple reversal or breakout setups."""

    def __init__(self, config: Optional[dict] = None):
        self.config = CRYPTO_TRAIN_CONFIG.copy()
        if config:
            self.config.update(config)
        set_config(self.config)
        # scanner_timeframe defaults to 1h (hourly RSI is meaningful for swing entries).
        # Falls back to crypto_timeframe if explicitly set.
        self.timeframe = self.config.get("scanner_timeframe") or self.config.get("crypto_timeframe", "1h")
        self.min_strength = float(self.config.get("scanner_min_strength", 0.50))
        self.enable_rsi_reversal = bool(self.config.get("scanner_enable_rsi_reversal", True))
        self.enable_breakout = bool(self.config.get("scanner_enable_breakout", True))
        self.enable_ema_crossover = bool(self.config.get("scanner_enable_ema_crossover", True))
        self.enable_rsi_momentum = bool(self.config.get("scanner_enable_rsi_momentum", True))
        self.enable_trend_pullback = bool(self.config.get("scanner_enable_trend_pullback", True))
        self.enable_liquidity_sweep = bool(self.config.get("scanner_enable_liquidity_sweep", True))
        self.enable_range_bounce = bool(self.config.get("scanner_enable_range_bounce", True))
        self.enable_bb_reversion = bool(self.config.get("scanner_enable_bb_reversion", True))
        self.enable_orderflow = bool(self.config.get("scanner_enable_orderflow", True))
        self.enable_regime_flip = bool(self.config.get("scanner_enable_regime_flip", True))
        self.enable_ensemble = bool(self.config.get("scanner_enable_ensemble", True))
        self.reversal_buy_regimes = set(self.config.get("scanner_reversal_buy_regimes", ["trend_down", "sideway"]))
        self.reversal_sell_regimes = set(self.config.get("scanner_reversal_sell_regimes", []))
        self.rsi_oversold = float(self.config.get("scanner_rsi_oversold", 35))
        self.max_reversal_rsi = float(self.config.get("scanner_max_reversal_rsi", 35))
        self.max_breakout_rsi = float(self.config.get("scanner_max_breakout_rsi", 68))
        self.min_momentum_volume_spike = float(self.config.get("scanner_min_momentum_volume_spike", 0.70))
        self.rsi_extreme = float(self.config.get("scanner_rsi_extreme", 28))
        self.ensemble_min_votes = max(1, int(float(self.config.get("scanner_ensemble_min_votes", 3))))
        self.ensemble_base_bonus = float(self.config.get("scanner_ensemble_base_bonus", 0.05))
        self.ensemble_max_bonus = float(self.config.get("scanner_ensemble_max_bonus", 0.12))
        self.liquidity_sweep_lookback = max(5, int(float(self.config.get("scanner_liquidity_sweep_lookback", 20))))
        self.range_lookback = max(10, int(float(self.config.get("scanner_range_lookback", 20))))
        self.range_bounce_max_pos = min(0.45, max(0.10, float(self.config.get("scanner_range_bounce_max_pos", 0.35))))
        self.range_min_width_atr = max(1.0, float(self.config.get("scanner_range_min_width_atr", 1.6)))
        self.range_min_volume_spike = max(0.0, float(self.config.get("scanner_range_min_volume_spike", 0.20)))
        self.sideway_min_rsi = float(self.config.get("scanner_sideway_min_rsi", 28))
        self.sideway_max_rsi = float(self.config.get("scanner_sideway_max_rsi", 65))
        self.min_reward_risk = max(0.0, float(self.config.get("scanner_min_reward_risk", 1.20)))
        self.orderflow_lookback = max(3, int(float(self.config.get("scanner_orderflow_lookback", 8))))
        self.regime_flip_lookback = max(2, int(float(self.config.get("scanner_regime_flip_lookback", 8))))

    def _long_take_profit(self, entry: float, stop_loss: float, *targets: float) -> float:
        """Return the highest long target while enforcing the configured minimum R:R."""
        risk = max(entry - stop_loss, entry * 0.0001)
        min_rr_target = entry + risk * self.min_reward_risk
        return max(min_rr_target, *targets)

    def scan(self, symbols: Iterable[str], timeframes: Optional[List[str]] = None) -> List[ScanSignal]:
        """Fetch market data and return actionable signals only.

        When ``timeframes`` is passed it overrides the single ``scanner_timeframe``
        config.  The ``scanner_timeframes`` list config (e.g. ``["15m","30m","1h"]``)
        is also honoured, making the scanner check every timeframe and aggregate
        signals across all of them.

        Side-effect: populates ``self.last_rsi_map`` with the most recent RSI
        value for every symbol that was successfully enriched, whether or not
        it produced a signal.  Callers can read this after ``scan()`` returns.
        """
        signals: List[ScanSignal] = []
        self.last_rsi_map: Dict[str, float] = {}
        self.last_scan_map: Dict[str, Dict] = {}

        tf_list = timeframes or self.config.get("scanner_timeframes")
        if not tf_list:
            tf_list = [self.timeframe]
        if isinstance(tf_list, str):
            tf_list = [t.strip() for t in tf_list.split(",") if t.strip()]

        for symbol in symbols:
            best_for_symbol: Optional[ScanSignal] = None
            # Cache OHLCV per timeframe so we don't re-fetch for fallback display.
            df_cache: Dict[str, pd.DataFrame] = {}
            for tf in tf_list:
                limit = int(self.config.get("crypto_ohlcv_limit", 240))
                if tf in ("1m", "3m", "5m"):
                    limit = min(limit, 500)
                elif tf in ("15m", "30m"):
                    limit = min(limit, 200)
                df = _fetch_ohlcv(symbol, limit=limit, timeframe=tf)
                df_cache[tf] = df
                signal = self.scan_dataframe(symbol, df)
                if signal and signal.action != "WAIT":
                    cur_best = best_for_symbol
                    if cur_best is None or signal.strength > cur_best.strength:
                        best_for_symbol = signal
            if best_for_symbol is not None:
                self.last_scan_map[symbol] = best_for_symbol.to_dict()
                if best_for_symbol.strength >= self.min_strength:
                    signals.append(best_for_symbol)
            else:
                # Use cached primary-timeframe data for WAIT display (no re-fetch needed).
                primary_tf = tf_list[0]
                primary_df = df_cache.get(primary_tf)
                if primary_df is not None:
                    signal = self.scan_dataframe(symbol, primary_df)
                else:
                    signal = None
                self.last_scan_map[symbol] = signal.to_dict() if signal else {
                    "symbol": symbol,
                    "timeframe": primary_tf,
                    "strategy": "none",
                    "action": "WAIT",
                    "reason": "No usable OHLCV data or not enough enriched indicator rows.",
                }
            # Record RSI from the primary timeframe for dashboard display.
            if symbol not in self.last_rsi_map:
                primary_df = df_cache.get(tf_list[0])
                if primary_df is not None and len(primary_df) >= 60:
                    try:
                        enriched = self._enrich(primary_df).dropna()
                        if len(enriched) >= 2:
                            self.last_rsi_map[symbol] = float(enriched.iloc[-1]["rsi"])
                    except Exception:
                        pass
        return signals

    def scan_dataframe(self, symbol: str, df: pd.DataFrame) -> Optional[ScanSignal]:
        """Scan an already loaded OHLCV dataframe.

        This makes the scanner testable and allows historical backtests without
        repeated network calls. All enabled strategies are evaluated; when at
        least ``scanner_ensemble_min_votes`` BUY strategies agree, the returned
        signal receives a confluence bonus that scales with the vote ratio.
        """
        if df is None or len(df) < 60:
            return None

        enriched = self._enrich(df).dropna().copy()
        if len(enriched) < 5:
            return None

        candidates = self.scan_all_strategies(symbol, enriched)
        if candidates:
            return self._select_signal(symbol, candidates)
        return self._wait_signal(symbol, enriched, candidates)

    def scan_all_strategies(self, symbol: str, enriched: pd.DataFrame) -> List[ScanSignal]:
        """Return every strategy signal that is currently satisfied.

        The public ``scan_dataframe`` method still returns one ``ScanSignal`` to
        preserve the existing API, but this helper gives the scanner enough
        information to vote across strategies.
        """
        if enriched is None or len(enriched) < 5:
            return []

        last = enriched.iloc[-1]
        prev = enriched.iloc[-2]
        close = float(last["Close"])
        prev_close = float(prev["Close"])
        open_price = float(last["Open"])
        high = float(last["High"])
        low = float(last["Low"])
        atr = max(float(last["atr"]), close * 0.002)
        rsi = float(last["rsi"])
        prev_rsi = float(prev["rsi"])
        ema10 = float(last["close_10_ema"])
        prev_ema10 = float(prev["close_10_ema"])
        sma50 = float(last["close_50_sma"])
        prev_sma50 = float(prev["close_50_sma"])
        volume_spike = float(last["volume_spike"])
        regime = self._market_regime(last)
        ts = pd.to_datetime(last["Date"], utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")

        def make_signal(strategy: str, action: str, strength: float, stop_loss: float, take_profit: float, reason: str) -> ScanSignal:
            return ScanSignal(
                symbol=symbol,
                timeframe=self.timeframe,
                strategy=strategy,
                action=action,
                strength=round(min(1.0, max(0.0, strength)), 4),
                entry=round(close, 8),
                stop_loss=round(stop_loss, 8),
                take_profit=round(take_profit, 8),
                rsi=round(rsi, 4),
                atr=round(atr, 8),
                volume_spike=round(volume_spike, 4),
                market_regime=regime,
                reason=reason,
                timestamp_utc=ts,
            )

        candidates: List[ScanSignal] = []
        recovery_candle = close > prev_close
        is_extreme_oversold = rsi < self.rsi_extreme
        is_oversold = rsi < self.rsi_oversold

        # Mean-reversion reversal: oversold bounce or overbought rejection.
        if self.enable_rsi_reversal and is_oversold and (recovery_candle or is_extreme_oversold) and regime in self.reversal_buy_regimes:
            strength = 0.50 + (self.rsi_oversold - rsi) / 60 + min(volume_spike, 3.0) / 20
            if not recovery_candle:
                strength -= 0.05
            reason = (
                "RSI oversold" + (" (extreme — no confirmation candle yet, anticipation entry)" if not recovery_candle else " with recovery candle")
                + f" in {regime} regime. RSI={rsi:.1f}, volume_spike={volume_spike:.2f}."
            )
            candidates.append(make_signal("rsi_reversal", "BUY", strength, close - 1.5 * atr, close + 2.0 * atr, reason))

        if self.enable_rsi_reversal and rsi > 70 and close < prev_close and regime in self.reversal_sell_regimes:
            strength = 0.50 + (rsi - 70) / 50 + min(volume_spike, 3.0) / 20
            candidates.append(
                make_signal(
                    "rsi_reversal",
                    "SELL",
                    strength,
                    close + 1.5 * atr,
                    close - 2.0 * atr,
                    "RSI overbought with rejection candle; for spot this is normally reduce/avoid-long unless margin is enabled.",
                )
            )

        # Breakout: close above/below recent range with confirmed volume.
        recent_high = float(enriched["High"].iloc[-21:-1].max())
        recent_low = float(enriched["Low"].iloc[-21:-1].min())
        range_window = enriched.iloc[-self.range_lookback - 1 : -1]
        if not range_window.empty:
            range_high = float(range_window["High"].max())
            range_low = float(range_window["Low"].min())
            range_width = max(range_high - range_low, close * 0.0001)
            range_pos = (close - range_low) / range_width
            range_width_atr = range_width / atr
            range_mid = range_low + 0.50 * range_width
            range_upper_target = range_low + 0.78 * range_width

            # Sideway range bounce: buy near the lower quarter of a validated range.
            # This is intentionally not an oversold-only setup; it covers the RSI 40-55
            # "dead zone" where ranging crypto often bounces before RSI becomes extreme.
            if (
                self.enable_range_bounce
                and regime == "sideway"
                and range_width_atr >= self.range_min_width_atr
                and 0.0 <= range_pos <= self.range_bounce_max_pos
                and self.sideway_min_rsi <= rsi <= self.sideway_max_rsi
                and close >= prev_close
                and volume_spike >= self.range_min_volume_spike
            ):
                stop_loss = min(range_low - 0.25 * atr, close - 0.85 * atr)
                take_profit = self._long_take_profit(close, stop_loss, range_mid, close + 1.60 * atr)
                strength = (
                    0.54
                    + (self.range_bounce_max_pos - range_pos) / max(self.range_bounce_max_pos, 0.01) * 0.12
                    + min(range_width_atr, 8.0) / 80
                    + max(0.0, self.sideway_max_rsi - rsi) / 180
                    + min(volume_spike, 2.0) / 60
                )
                candidates.append(
                    make_signal(
                        "range_bounce",
                        "BUY",
                        strength,
                        stop_loss,
                        take_profit,
                        f"Sideway range bounce: price is in lower {range_pos * 100:.0f}% of {self.range_lookback}-candle range; RSI={rsi:.1f}, width={range_width_atr:.1f} ATR, TP enforces >= {self.min_reward_risk:.1f}R.",
                    )
                )

            # Bollinger-style mean reversion: price reclaims the lower volatility band
            # in a sideway regime, targeting the 20-candle mean/midline.
            close_window = range_window["Close"]
            close_mean = float(close_window.mean())
            close_std = float(close_window.std(ddof=0) or 0.0)
            lower_band = close_mean - 1.60 * close_std
            if (
                self.enable_bb_reversion
                and regime == "sideway"
                and close_std >= close * 0.001
                and range_width_atr >= self.range_min_width_atr
                and prev_close <= lower_band < close
                and rsi <= self.sideway_max_rsi
                and close >= prev_close
                and volume_spike >= self.range_min_volume_spike
            ):
                stop_loss = min(low - 0.25 * atr, close - 0.90 * atr)
                take_profit = self._long_take_profit(close, stop_loss, close_mean, close + 1.50 * atr)
                band_depth = max(0.0, (lower_band - prev_close) / max(close_std, close * 0.0001))
                strength = 0.55 + min(band_depth, 2.0) / 12 + min(range_width_atr, 8.0) / 90 + min(volume_spike, 2.0) / 60
                candidates.append(
                    make_signal(
                        "bb_reversion",
                        "BUY",
                        strength,
                        stop_loss,
                        take_profit,
                        f"Sideway mean reversion: price reclaimed lower volatility band; RSI={rsi:.1f}, TP enforces >= {self.min_reward_risk:.1f}R.",
                    )
                )

        if self.enable_breakout and close > recent_high and volume_spike >= 1.8 and 55 <= rsi <= self.max_breakout_rsi and regime == "trend_up":
            strength = 0.55 + min(volume_spike - 1.0, 3.0) / 8 + min(rsi - 55, 25) / 100
            candidates.append(make_signal("breakout", "BUY", strength, close - 1.2 * atr, close + 2.0 * atr, "Price closed above the recent range high with strong volume in trend_up regime."))

        if self.enable_breakout and close < recent_low and volume_spike >= 1.5 and rsi <= 45:
            strength = 0.55 + min(volume_spike - 1.0, 3.0) / 8 + min(45 - rsi, 25) / 100
            candidates.append(make_signal("breakout", "SELL", strength, min(recent_low + atr, close + 2 * atr), close - 2.5 * atr, "Price closed below the recent range low with volume confirmation."))

        # EMA crossover: captures new uptrends earlier than waiting for oversold pullbacks.
        if self.enable_ema_crossover and prev_ema10 <= prev_sma50 and ema10 > sma50 and close > ema10 and 55 <= rsi <= self.max_breakout_rsi and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike:
            strength = 0.58 + max(0.0, rsi - 50) / 120 + min(volume_spike, 3.0) / 30 + 0.05
            candidates.append(make_signal("ema_crossover", "BUY", strength, close - 1.4 * atr, close + 2.1 * atr, f"EMA10 crossed above SMA50 with price above EMA10. RSI={rsi:.1f}, volume_spike={volume_spike:.2f}."))

        # Trend pullback: buys a confirmed continuation after price reclaims EMA10 in an uptrend.
        if self.enable_trend_pullback and regime == "trend_up" and prev_close <= prev_ema10 and close > ema10 and 45 <= rsi <= 65 and volume_spike >= self.min_momentum_volume_spike:
            strength = 0.56 + max(0.0, rsi - 45) / 150 + min(volume_spike, 2.5) / 35
            candidates.append(make_signal("trend_pullback", "BUY", strength, min(ema10 - 1.0 * atr, close - 1.5 * atr), close + 2.0 * atr, f"Trend pullback confirmed: price reclaimed EMA10 in trend_up regime. RSI={rsi:.1f}, volume_spike={volume_spike:.2f}."))

        # RSI momentum: more frequent than oversold reversal, but still requires price confirmation.
        if self.enable_rsi_momentum and prev_rsi <= 50 < rsi and close > ema10 and close >= prev_close and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike:
            strength = 0.54 + max(0.0, rsi - 50) / 140 + min(volume_spike, 2.5) / 35 + 0.04
            candidates.append(make_signal("rsi_momentum", "BUY", strength, close - 1.2 * atr, close + 1.8 * atr, f"RSI crossed above 50 with price above EMA10. RSI={rsi:.1f}, volume_spike={volume_spike:.2f}."))

        # Liquidity sweep: wick takes prior swing low, then closes back above it.
        if self.enable_liquidity_sweep:
            sweep_window = enriched.iloc[-self.liquidity_sweep_lookback - 1 : -1]
            if not sweep_window.empty:
                swing_low = float(sweep_window["Low"].min())
                candle_range = max(high - low, close * 0.0001)
                lower_wick = max(0.0, min(open_price, close) - low)
                wick_ratio = lower_wick / candle_range
                swept_distance_atr = max(0.0, swing_low - low) / atr
                if low < swing_low and close > swing_low and wick_ratio >= 0.35 and rsi <= 55 and volume_spike >= max(0.50, self.min_momentum_volume_spike * 0.8):
                    strength = 0.57 + min(wick_ratio, 0.9) / 6 + min(volume_spike, 3.0) / 35 + min(swept_distance_atr, 2.0) / 25
                    if close > open_price:
                        strength += 0.03
                    stop_loss = min(low - 0.30 * atr, close - 1.4 * atr)
                    take_profit = self._long_take_profit(close, stop_loss, close + 2.2 * atr)
                    candidates.append(
                        make_signal(
                            "liquidity_sweep",
                            "BUY",
                            strength,
                            stop_loss,
                            take_profit,
                            f"Liquidity sweep: low swept prior {self.liquidity_sweep_lookback}-candle swing low and closed back above it. wick_ratio={wick_ratio:.2f}, RSI={rsi:.1f}.",
                        )
                    )

        # Orderflow approximation from OHLCV only: volume-weighted candle delta.
        if self.enable_orderflow:
            flow_window = enriched.iloc[-self.orderflow_lookback :]
            ranges = (flow_window["High"] - flow_window["Low"]).clip(lower=close * 0.0001)
            buying_pressure = ((flow_window["Close"] - flow_window["Low"]) / ranges).clip(0, 1)
            candle_delta = ((buying_pressure * 2) - 1) * flow_window["Volume"]
            delta_ratio = float(candle_delta.sum() / max(float(flow_window["Volume"].sum()), 1.0))
            if delta_ratio >= 0.18 and close > ema10 and close >= prev_close and 45 <= rsi <= self.max_breakout_rsi and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike:
                strength = 0.55 + min(delta_ratio, 0.60) / 3 + max(0.0, rsi - 45) / 180 + min(volume_spike, 2.5) / 40
                candidates.append(make_signal("orderflow_approx", "BUY", strength, close - 1.25 * atr, close + 2.0 * atr, f"OHLCV orderflow approximation: {self.orderflow_lookback}-candle cumulative delta ratio={delta_ratio:.2f} with price above EMA10."))

        # Regime flip: market structure just flipped into trend_up.
        if self.enable_regime_flip:
            prior_idx = max(0, len(enriched) - self.regime_flip_lookback - 1)
            prior_regime = self._market_regime(enriched.iloc[prior_idx])
            if prior_regime != "trend_up" and regime == "trend_up" and close > ema10 and rsi >= 50 and volume_spike >= max(0.50, self.min_momentum_volume_spike):
                strength = 0.55 + max(0.0, rsi - 50) / 160 + min(volume_spike, 2.5) / 45
                candidates.append(make_signal("regime_flip", "BUY", strength, close - 1.35 * atr, close + 2.0 * atr, f"Regime flipped from {prior_regime} to trend_up over the last {self.regime_flip_lookback} candles."))

        return candidates

    def _select_signal(self, symbol: str, candidates: List[ScanSignal]) -> ScanSignal:
        buy_candidates = [candidate for candidate in candidates if candidate.action == "BUY"]
        if self.enable_ensemble and len(buy_candidates) >= self.ensemble_min_votes:
            return self._ensemble_signal(symbol, buy_candidates)
        return max(candidates, key=lambda candidate: float(candidate.strength or 0.0))

    def _ensemble_signal(self, symbol: str, buy_candidates: List[ScanSignal]) -> ScanSignal:
        best = max(buy_candidates, key=lambda candidate: float(candidate.strength or 0.0))
        vote_count = len(buy_candidates)
        total_votes = max(vote_count, self._enabled_buy_strategy_count())
        vote_ratio = vote_count / max(total_votes, 1)
        min_ratio = min(self.ensemble_min_votes, total_votes) / max(total_votes, 1)
        if min_ratio >= 1.0:
            bonus = self.ensemble_max_bonus
        else:
            bonus_scale = max(0.0, min(1.0, (vote_ratio - min_ratio) / (1.0 - min_ratio)))
            bonus = self.ensemble_base_bonus + bonus_scale * (self.ensemble_max_bonus - self.ensemble_base_bonus)
        mean_strength = sum(float(candidate.strength or 0.0) for candidate in buy_candidates) / vote_count
        strength = min(1.0, mean_strength + bonus)
        contributors = ", ".join(f"{candidate.strategy}:{candidate.strength:.2f}" for candidate in sorted(buy_candidates, key=lambda candidate: candidate.strategy))
        return ScanSignal(
            symbol=symbol,
            timeframe=self.timeframe,
            strategy="ensemble",
            action="BUY",
            strength=round(strength, 4),
            entry=best.entry,
            stop_loss=best.stop_loss,
            take_profit=best.take_profit,
            rsi=best.rsi,
            atr=best.atr,
            volume_spike=best.volume_spike,
            market_regime=best.market_regime,
            reason=f"Ensemble confluence: {vote_count}/{total_votes} BUY strategies agreed; bonus=+{bonus:.2f}. Contributors: {contributors}. Best setup: {best.strategy}.",
            timestamp_utc=best.timestamp_utc,
        )

    def _enabled_buy_strategy_count(self) -> int:
        count = 1 if self.enable_rsi_reversal and self.reversal_buy_regimes else 0
        count += int(self.enable_breakout)
        count += int(self.enable_ema_crossover)
        count += int(self.enable_rsi_momentum)
        count += int(self.enable_trend_pullback)
        count += int(self.enable_liquidity_sweep)
        count += int(self.enable_range_bounce)
        count += int(self.enable_bb_reversion)
        count += int(self.enable_orderflow)
        count += int(self.enable_regime_flip)
        return max(count, 1)

    def _wait_signal(self, symbol: str, enriched: pd.DataFrame,
                     candidates: Optional[List[ScanSignal]] = None) -> ScanSignal:
        """Build a WAIT result with per-strategy status so callers can see why nothing triggered.

        When ``candidates`` is passed (from :meth:`scan_dataframe`), ensemble-block
        information is included without re-calling :meth:`scan_all_strategies`.
        """
        last = enriched.iloc[-1]
        prev = enriched.iloc[-2]
        close = float(last["Close"])
        prev_close = float(prev["Close"])
        atr = max(float(last["atr"]), close * 0.002)
        rsi = float(last["rsi"])
        prev_rsi = float(prev["rsi"])
        ema10 = float(last["close_10_ema"])
        prev_ema10 = float(prev["close_10_ema"])
        sma50 = float(last["close_50_sma"])
        prev_sma50 = float(prev["close_50_sma"])
        volume_spike = float(last["volume_spike"])
        regime = self._market_regime(last)
        ts = pd.to_datetime(last["Date"], utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
        open_price = float(last["Open"])
        high = float(last["High"])
        low = float(last["Low"])

        # Pre-compute windows used by multiple strategies.
        range_window = enriched.iloc[-self.range_lookback - 1 : -1]
        sweep_window = enriched.iloc[-self.liquidity_sweep_lookback - 1 : -1]
        swing_low = float(sweep_window["Low"].min()) if not sweep_window.empty else 0.0
        candle_range = max(high - low, close * 0.0001)
        lower_wick = max(0.0, min(open_price, close) - low)
        wick_ratio = lower_wick / candle_range
        recent_high = float(enriched["High"].iloc[-21:-1].max())
        recent_low = float(enriched["Low"].iloc[-21:-1].min())
        flow_window = enriched.iloc[-self.orderflow_lookback :]
        franges = (flow_window["High"] - flow_window["Low"]).clip(lower=close * 0.0001)
        buying_pressure = ((flow_window["Close"] - flow_window["Low"]) / franges).clip(0, 1)
        candle_delta = ((buying_pressure * 2) - 1) * flow_window["Volume"]
        delta_ratio = float(candle_delta.sum() / max(float(flow_window["Volume"].sum()), 1.0))
        if not range_window.empty:
            range_high = float(range_window["High"].max())
            range_low_v = float(range_window["Low"].min())
            range_width = max(range_high - range_low_v, close * 0.0001)
            range_pos = (close - range_low_v) / range_width
            range_width_atr = range_width / atr
        else:
            range_high = range_low_v = range_width = range_pos = range_width_atr = 0.0
        close_window = range_window["Close"]
        close_mean = float(close_window.mean())
        close_std = float(close_window.std(ddof=0) or 0.0)
        lower_band = close_mean - 1.60 * close_std
        prior_idx = max(0, len(enriched) - self.regime_flip_lookback - 1)
        prior_regime = self._market_regime(enriched.iloc[prior_idx])

        checks: List[str] = []
        reco_candle = close > prev_close
        min_liq_vol = max(0.50, self.min_momentum_volume_spike * 0.8)
        min_rf_vol = max(0.50, self.min_momentum_volume_spike)

        if self.enable_rsi_reversal:
            blocked_by_regime = regime not in self.reversal_buy_regimes
            rsi_ok = rsi < self.rsi_oversold or rsi < self.rsi_extreme
            trigger_ok = reco_candle or rsi < self.rsi_extreme
            status = "✓" if rsi_ok and trigger_ok and not blocked_by_regime else "❌"
            checks.append(f"rsi_reversal[{status}]:rsi={rsi:.1f}(need<{self.rsi_oversold:.0f}) recov={'Y' if reco_candle else 'N'} regime={regime}(allow={sorted(self.reversal_buy_regimes)})")
        if self.enable_breakout:
            status = "✓" if close > recent_high and volume_spike >= 1.8 and 55 <= rsi <= self.max_breakout_rsi and regime == "trend_up" else "❌"
            checks.append(f"breakout[{status}]:close={close:.4f} hi20={recent_high:.4f} vol={volume_spike:.2f}(≥1.8) rsi={rsi:.1f}(55-{self.max_breakout_rsi:.0f}) reg={regime}")
        if self.enable_ema_crossover:
            status = "✓" if prev_ema10 <= prev_sma50 and ema10 > sma50 and close > ema10 and 55 <= rsi <= self.max_breakout_rsi and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike else "❌"
            checks.append(f"ema_cross[{status}]:cross={'Y' if prev_ema10<=prev_sma50 and ema10>sma50 else 'N'} rsi={rsi:.1f}(55-{self.max_breakout_rsi:.0f}) reg={regime} vol={volume_spike:.2f}(≥{self.min_momentum_volume_spike:.1f})")
        if self.enable_rsi_momentum:
            status = "✓" if prev_rsi <= 50 < rsi and close > ema10 and close >= prev_close and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike else "❌"
            checks.append(f"rsi_mom[{status}]:cross50={'Y' if prev_rsi<=50<rsi else 'N'} reg={regime} vol={volume_spike:.2f}(≥{self.min_momentum_volume_spike:.1f})")
        if self.enable_trend_pullback:
            status = "✓" if regime == "trend_up" and prev_close <= prev_ema10 and close > ema10 and 45 <= rsi <= 65 and volume_spike >= self.min_momentum_volume_spike else "❌"
            checks.append(f"pullback[{status}]:ema_reclaim={'Y' if prev_close<=prev_ema10 and close>ema10 else 'N'} rsi={rsi:.1f}(45-65) reg={regime} vol={volume_spike:.2f}(≥{self.min_momentum_volume_spike:.1f})")
        if self.enable_liquidity_sweep:
            swept = low < swing_low and close > swing_low
            status = "✓" if swept and wick_ratio >= 0.35 and rsi <= 55 and volume_spike >= min_liq_vol else "❌"
            checks.append(f"liq_sweep[{status}]:swept={'Y' if swept else 'N'} wick={wick_ratio:.2f}(≥0.35) rsi={rsi:.1f}(≤55) vol={volume_spike:.2f}(≥{min_liq_vol:.1f})")
        if self.enable_range_bounce:
            in_range = (regime == "sideway" and range_width_atr >= self.range_min_width_atr
                        and 0.0 <= range_pos <= self.range_bounce_max_pos
                        and self.sideway_min_rsi <= rsi <= self.sideway_max_rsi
                        and close >= prev_close and volume_spike >= self.range_min_volume_spike)
            status = "✓" if in_range else "❌"
            checks.append(f"range_bounce[{status}]:pos={range_pos:.2f}(≤{self.range_bounce_max_pos:.2f}) w_atr={range_width_atr:.1f}(≥{self.range_min_width_atr:.1f}) rsi={rsi:.1f}({self.sideway_min_rsi:.0f}-{self.sideway_max_rsi:.0f}) recov={'Y' if close>=prev_close else 'N'} vol={volume_spike:.2f}(≥{self.range_min_volume_spike:.2f}) reg={regime}")
        if self.enable_bb_reversion:
            status = "✓" if (regime == "sideway" and close_std >= close * 0.001 and prev_close <= lower_band < close
                              and rsi <= self.sideway_max_rsi and close >= prev_close
                              and volume_spike >= self.range_min_volume_spike) else "❌"
            checks.append(f"bb_rev[{status}]:lower={lower_band:.4f} prev={prev_close:.4f} cur={close:.4f} std={close_std:.4f} rsi={rsi:.1f}(≤{self.sideway_max_rsi:.0f}) vol={volume_spike:.2f}(≥{self.range_min_volume_spike:.2f}) reg={regime}")
        if self.enable_orderflow:
            status = "✓" if delta_ratio >= 0.18 and close > ema10 and close >= prev_close and 45 <= rsi <= self.max_breakout_rsi and regime == "trend_up" and volume_spike >= self.min_momentum_volume_spike else "❌"
            checks.append(f"orderflow[{status}]:delta={delta_ratio:.2f}(≥0.18) rsi={rsi:.1f}(45-{self.max_breakout_rsi:.0f}) reg={regime} vol={volume_spike:.2f}(≥{self.min_momentum_volume_spike:.1f})")
        if self.enable_regime_flip:
            status = "✓" if prior_regime != "trend_up" and regime == "trend_up" and close > ema10 and rsi >= 50 and volume_spike >= min_rf_vol else "❌"
            checks.append(f"regime_flip[{status}]:{prior_regime}→{regime} rsi={rsi:.1f}(≥50) ema={'Y' if close>ema10 else 'N'} vol={volume_spike:.2f}(≥{min_rf_vol:.1f})")

        enabled_count = sum([self.enable_rsi_reversal, self.enable_breakout, self.enable_ema_crossover,
                             self.enable_rsi_momentum, self.enable_trend_pullback, self.enable_liquidity_sweep,
                             self.enable_range_bounce, self.enable_bb_reversion, self.enable_orderflow,
                             self.enable_regime_flip])
        wait_reason = (
            f"[{enabled_count} strats] RSI={rsi:.1f} reg={regime} vol={volume_spike:.2f} atr={atr:.4f}. "
            + " | ".join(checks)
        )

        # Ensemble-block info from pre-computed candidates (no re-scan needed).
        if candidates:
            buy_candidates = [c for c in candidates if c.action == "BUY"]
            if buy_candidates and self.enable_ensemble and len(buy_candidates) < self.ensemble_min_votes:
                names = ",".join(c.strategy for c in buy_candidates)
                wait_reason = (
                    f"ENSEMBLE: {len(buy_candidates)}/{enabled_count} BUY (need≥{self.ensemble_min_votes}) [{names}]. "
                    + " | ".join(checks)
                )

        return ScanSignal(
            symbol=symbol,
            timeframe=self.timeframe,
            strategy="none",
            action="WAIT",
            strength=0.0,
            entry=round(close, 8),
            stop_loss=round(close - atr, 8),
            take_profit=round(close + atr, 8),
            rsi=round(rsi, 4),
            atr=round(atr, 8),
            volume_spike=round(volume_spike, 4),
            market_regime=regime,
            reason=wait_reason,
            timestamp_utc=ts,
        )

    @staticmethod
    def _enrich(df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy().reset_index(drop=True)
        stock_df = work.rename(
            columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        stats = wrap(stock_df)
        for indicator in ("rsi", "atr", "close_10_ema", "close_50_sma"):
            stats[indicator]
        # ``wrap`` indexes rows by date, while ``work`` keeps a RangeIndex.
        # Assign raw values to avoid pandas aligning by incompatible labels and
        # turning the indicator columns into all-NaN.
        work["rsi"] = pd.to_numeric(stats["rsi"], errors="coerce").to_numpy()
        work["atr"] = pd.to_numeric(stats["atr"], errors="coerce").to_numpy()
        work["close_10_ema"] = pd.to_numeric(stats["close_10_ema"], errors="coerce").to_numpy()
        work["close_50_sma"] = pd.to_numeric(stats["close_50_sma"], errors="coerce").to_numpy()
        work["volume_spike"] = work["Volume"] / work["Volume"].rolling(20).mean()
        return work

    @staticmethod
    def _market_regime(row: pd.Series) -> str:
        close = float(row["Close"])
        ema10 = float(row["close_10_ema"])
        sma50 = float(row["close_50_sma"])
        atr = max(float(row["atr"]), close * 0.002)
        if close > sma50 + atr and ema10 > sma50:
            return "trend_up"
        if close < sma50 - atr and ema10 < sma50:
            return "trend_down"
        return "sideway"