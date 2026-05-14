"""High-risk: Donchian breakout with volume + ATR filter."""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import atr
from app.engine.strategies.base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    name = "breakout"
    category = StrategyCategory.HIGH
    required_timeframes = ["5m", "1h"]

    def __init__(self, lookback: int = 20, vol_mult: float = 1.3):
        # vol_mult 1.5× was rare on BSC pairs; 1.3× still requires real
        # participation but fires often enough to be useful.
        self.lookback = lookback
        self.vol_mult = vol_mult

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("5m")
        df_htf = candles.get("1h")
        if df is None or len(df) < self.lookback + 5 or df_htf is None or len(df_htf) < 50:
            return None

        recent = df.iloc[-self.lookback - 1 : -1]
        last = df.iloc[-1]
        upper = recent["high"].max()
        lower = recent["low"].min()
        avg_vol = recent["volume"].mean()
        a = atr(df, 14).iloc[-1]
        if pd.isna(a):
            return None

        # Multi-TF confirmation: require 1h trend agrees with breakout direction.
        htf_close = df_htf["close"]
        htf_trend_up = htf_close.iloc[-1] > htf_close.iloc[-20]

        # Long breakout
        if (
            last["close"] > upper
            and last["volume"] > self.vol_mult * avg_vol
            and a / last["close"] < 0.04          # not a vol spike
            and htf_trend_up
        ):
            return Signal(
                side=Side.BUY,
                confidence=0.7,
                strategy=self.name,
                reason=f"close>{upper:.4f} on {last['volume']/avg_vol:.1f}x vol",
                token_in=token_in,
                token_out=token_out,
                suggested_amount_usd=capital_usd,
                metadata={"upper": upper, "lower": lower, "atr": a},
            )
        return None
