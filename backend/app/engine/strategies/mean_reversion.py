"""Medium-risk: Bollinger band mean reversion."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import bollinger, rsi
from app.engine.strategies.base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    name = "mean_reversion"
    category = StrategyCategory.MEDIUM
    required_timeframes = ["15m"]

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("15m")
        if df is None or len(df) < 30:
            return None
        upper, mid, lower = bollinger(df["close"], 20, 2.0)
        r = rsi(df["close"], 14).iloc[-1]
        last = df["close"].iloc[-1]
        if pd.isna(lower.iloc[-1]) or pd.isna(r):
            return None
        # Touched lower band, RSI oversold but turning up.
        # Loosened RSI <35 → <40 to catch more bounces. Confidence 0.62 —
        # two confirmations (BB + RSI) is a real edge, not 50/50.
        if last <= lower.iloc[-1] * 1.001 and r < 40:
            return Signal(
                side=Side.BUY, confidence=0.62, strategy=self.name,
                reason=f"BB lower touch, RSI {r:.0f}",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd * 0.8,
            )
        if last >= upper.iloc[-1] * 0.999 and r > 65:
            return Signal(
                side=Side.SELL, confidence=0.62, strategy=self.name,
                reason=f"BB upper touch, RSI {r:.0f}",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd * 0.8,
            )
        return None
