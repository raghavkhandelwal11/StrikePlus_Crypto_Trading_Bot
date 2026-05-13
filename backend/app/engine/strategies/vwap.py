"""Medium-risk: VWAP pullback. Buy when price reverts to VWAP in an uptrend."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import ema, vwap
from app.engine.strategies.base import BaseStrategy


class VwapStrategy(BaseStrategy):
    name = "vwap"
    category = StrategyCategory.MEDIUM
    required_timeframes = ["15m", "1h"]

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("15m")
        if df is None or len(df) < 60:
            return None
        v = vwap(df).iloc[-1]
        last = df["close"].iloc[-1]
        e50 = ema(df["close"], 50).iloc[-1]
        if pd.isna(v) or pd.isna(e50):
            return None
        # Price within 0.3% of VWAP, but trend (EMA50) is up — buy the dip to VWAP.
        if last > e50 and abs(last - v) / v < 0.003 and last >= v * 0.998:
            return Signal(
                side=Side.BUY, confidence=0.6, strategy=self.name,
                reason=f"price near VWAP {v:.4f} in uptrend",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd,
            )
        return None
