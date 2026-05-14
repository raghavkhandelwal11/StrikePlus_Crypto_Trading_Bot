"""Low-risk: range swing on stable-correlated pairs. Use on low-vol assets only."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import atr, rsi
from app.engine.strategies.base import BaseStrategy


class StableSwingStrategy(BaseStrategy):
    name = "stable_swing"
    category = StrategyCategory.LOW
    required_timeframes = ["1h"]

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("1h")
        if df is None or len(df) < 60:
            return None
        a = atr(df, 14).iloc[-1]
        last = df["close"].iloc[-1]
        if pd.isna(a) or a / last > 0.01:        # require low-vol
            return None
        r = rsi(df["close"], 14).iloc[-1]
        if pd.isna(r):
            return None
        if r < 40:
            return Signal(
                side=Side.BUY, confidence=0.60, strategy=self.name,
                reason=f"low-vol oversold (RSI {r:.0f})",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd * 0.5,
            )
        if r > 60:
            return Signal(
                side=Side.SELL, confidence=0.60, strategy=self.name,
                reason=f"low-vol overbought (RSI {r:.0f})",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd * 0.5,
            )
        return None
