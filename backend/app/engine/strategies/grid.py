"""Low-risk: simple grid. Buys at evenly spaced levels below the recent mid,
sells at corresponding levels above. The orchestrator stores the grid state
externally; each evaluate() returns a single Signal for the next-most-relevant level.
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

    def __init__(self, levels: int = 5, spacing_pct: float = 0.5):
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
                return Signal(
                    side=Side.BUY, confidence=0.5, strategy=self.name,
                    reason=f"grid buy at level {i} ({level:.4f})",
                    token_in=token_in, token_out=token_out,
                    suggested_amount_usd=capital_usd / self.levels,
                )
        # Reset memory if price recovers above mid
        if last >= mid:
            self._last_buy_level[symbol] = float("inf")
        return None
