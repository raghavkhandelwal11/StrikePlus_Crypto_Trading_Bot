"""High-risk: short-window momentum scalp (1m + 5m confirm)."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import rsi
from app.engine.strategies.base import BaseStrategy


class MomentumScalpStrategy(BaseStrategy):
    name = "momentum_scalp"
    category = StrategyCategory.HIGH
    required_timeframes = ["1m", "5m"]

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df1 = candles.get("1m")
        df5 = candles.get("5m")
        if df1 is None or len(df1) < 30 or df5 is None or len(df5) < 30:
            return None

        ret_3 = df1["close"].iloc[-1] / df1["close"].iloc[-4] - 1
        r = rsi(df1["close"], 7).iloc[-1]
        r5 = rsi(df5["close"], 14).iloc[-1]

        # Momentum: 3-bar move on 1m, RSI not yet overbought, 5m RSI rising.
        # Loosened threshold 0.5% → 0.3% so it fires on normal pushes, not just
        # rare bursts. RSI window widened 55-75 → 52-78.
        if pd.isna(r) or pd.isna(r5):
            return None
        if ret_3 > 0.003 and 52 < r < 78 and r5 > 48:
            return Signal(
                side=Side.BUY,
                confidence=0.62,
                strategy=self.name,
                reason=f"3-bar ret {ret_3*100:.2f}%, rsi1m {r:.0f}",
                token_in=token_in,
                token_out=token_out,
                suggested_amount_usd=capital_usd * 0.6,    # smaller size for scalps
            )
        return None
