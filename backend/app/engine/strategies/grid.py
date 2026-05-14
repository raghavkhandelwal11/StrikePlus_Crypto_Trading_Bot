"""Low-risk: simple grid. Buys at evenly spaced levels below the recent mid,
sells at corresponding levels above. The orchestrator stores the grid state
externally; each evaluate() returns a single Signal for the next-most-relevant level.

Economics tuning note (fee gate kept rejecting grid fills):
  - Default spacing was 0.5% — but PancakeSwap LP fees alone are 0.25% × 2 = 0.5%
    round-trip, before gas. Grid had zero edge by design. Widened to 1.2% so
    each round trip targets a ~1.2% gross gain, comfortably above the
    ~0.6% all-in fee drag on $100 trades.
  - Now also emits `take_profit` in metadata so the orchestrator's fee gate
    scores against grid's REAL target (the mid), not the global 2% fallback.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.strategies.base import BaseStrategy


class GridStrategy(BaseStrategy):
    name = "grid"
    category = StrategyCategory.LOW
    required_timeframes = ["15m"]

    def __init__(self, levels: int = 5, spacing_pct: float = 1.2):
        self.levels = levels
        self.spacing_pct = spacing_pct
        # Per-symbol last-fill memory so we don't double-fire the same level.
        self._last_buy_level: Dict[str, float] = {}

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("15m")
        if df is None or len(df) < 50:
            return None
        mid = df["close"].rolling(50).mean().iloc[-1]
        last = df["close"].iloc[-1]
        if pd.isna(mid):
            return None

        spacing = mid * (self.spacing_pct / 100.0)
        # Find the deepest grid level the price has crossed below.
        for i in range(1, self.levels + 1):
            level = mid - i * spacing
            if last <= level and self._last_buy_level.get(symbol, float("inf")) > level:
                self._last_buy_level[symbol] = level
                # The grid's take-profit is the mid — that's how grid trading
                # captures range. Stop_loss is one level further down (where
                # the grid would re-arm for a deeper average-in, but we treat
                # it as a hard stop on each leg).
                target_price = float(mid)
                stop_price = float(mid - (i + 1) * spacing)
                return Signal(
                    side=Side.BUY, confidence=0.55, strategy=self.name,
                    reason=f"grid buy lvl {i} @ {level:.4f} (TP {target_price:.4f})",
                    token_in=token_in, token_out=token_out,
                    suggested_amount_usd=capital_usd / self.levels,
                    metadata={
                        "stop_loss":    stop_price,
                        "take_profit":  target_price,
                        "entry_price":  float(last),
                        "grid_level":   i,
                    },
                )
        # Reset memory if price recovers above mid
        if last >= mid:
            self._last_buy_level[symbol] = float("inf")
        return None
