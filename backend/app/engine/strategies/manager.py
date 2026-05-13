"""Strategy manager: selects which strategy to run given market regime + risk category."""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from app.core.types import Signal, StrategyCategory
from app.engine.data.indicators import detect_regime
from app.engine.performance import strategy_perf
from app.engine.strategies.arbitrage import ArbitrageStrategy
from app.engine.strategies.base import BaseStrategy
from app.engine.strategies.breakout import BreakoutStrategy
from app.engine.strategies.ema_rsi import EmaRsiStrategy
from app.engine.strategies.grid import GridStrategy
from app.engine.strategies.mean_reversion import MeanReversionStrategy
from app.engine.strategies.momentum_scalp import MomentumScalpStrategy
from app.engine.strategies.smart_trend import SmartTrendStrategy
from app.engine.strategies.stable_swing import StableSwingStrategy
from app.engine.strategies.vwap import VwapStrategy

# Regime -> ordered list of preferred strategy names.
# `smart_trend` is preferred whenever we're in any trend regime.
_REGIME_PREFERENCE: Dict[str, List[str]] = {
    "trend_up":   ["smart_trend", "breakout", "ema_rsi", "vwap"],
    "trend_down": ["smart_trend", "ema_rsi", "vwap"],
    "range":      ["mean_reversion", "vwap", "grid", "stable_swing"],
    "high_vol":   ["smart_trend", "momentum_scalp"],
}


class StrategyManager:
    def __init__(self) -> None:
        self._all: Dict[str, BaseStrategy] = {
            s.name: s for s in [
                SmartTrendStrategy(),          # premier strategy
                BreakoutStrategy(),
                MomentumScalpStrategy(),
                EmaRsiStrategy(),
                VwapStrategy(),
                MeanReversionStrategy(),
                GridStrategy(),
                StableSwingStrategy(),
                ArbitrageStrategy(),
            ]
        }

    def list_strategies(self) -> List[Dict[str, str]]:
        return [
            {"name": s.name, "category": s.category.value}
            for s in self._all.values()
        ]

    def _eligible(self, category: StrategyCategory) -> List[BaseStrategy]:
        return [s for s in self._all.values() if s.category == category]

    def pick_for_regime(
        self, regime: str, category: Optional[StrategyCategory]
    ) -> List[BaseStrategy]:
        """Return strategies in priority order for the regime.

        If `category` is provided, only return strategies of that category
        (intersected with regime preference, fallback to all of category).
        """
        names = _REGIME_PREFERENCE.get(regime, [])
        ordered = [self._all[n] for n in names if n in self._all]
        if category is not None:
            ordered = [s for s in ordered if s.category == category]
            if not ordered:
                ordered = self._eligible(category)
        return ordered

    def evaluate(
        self,
        symbol: str,
        token_in: str,
        token_out: str,
        candles_by_tf: Dict[str, pd.DataFrame],
        capital_usd: float,
        category: Optional[StrategyCategory] = None,
    ) -> Optional[tuple[Signal, str]]:
        """Run preferred strategies; return the FIRST that fires (legacy behavior).

        Prefer `evaluate_all` for multi-strategy agreement scoring.
        """
        fired = self.evaluate_all(symbol, token_in, token_out, candles_by_tf, capital_usd, category)
        if not fired:
            return None
        sig, _, regime = fired[0]
        return sig, regime

    def evaluate_all(
        self,
        symbol: str,
        token_in: str,
        token_out: str,
        candles_by_tf: Dict[str, pd.DataFrame],
        capital_usd: float,
        category: Optional[StrategyCategory] = None,
    ) -> List[tuple[Signal, str, str]]:
        """Run every eligible strategy and return ALL that fire.

        Returns a list of `(signal, strategy_name, regime)` tuples, sorted by
        confidence descending. Used by the orchestrator's opportunity scorer
        to require multi-strategy agreement before committing capital.
        """
        primary: Optional[pd.DataFrame] = None
        for tf in ("15m", "5m", "1h"):
            df = candles_by_tf.get(tf)
            if df is not None and not df.empty:
                primary = df
                break
        if primary is None or len(primary) < 50:
            return []
        regime = detect_regime(primary)
        candidates = self.pick_for_regime(regime, category)
        out: List[tuple[Signal, str, str]] = []
        for strat in candidates:
            if strategy_perf.is_disabled(strat.name):
                continue
            try:
                sig = strat.evaluate(symbol, token_in, token_out, candles_by_tf, capital_usd)
            except Exception as e:
                logger.warning(f"strategy {strat.name} raised: {e}")
                continue
            if sig is None:
                continue
            mult = strategy_perf.confidence_multiplier(strat.name)
            sig.confidence = min(1.0, sig.confidence * mult)
            out.append((sig, strat.name, regime))
        out.sort(key=lambda x: x[0].confidence, reverse=True)
        return out
