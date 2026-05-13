"""Medium-risk: EMA crossover + RSI confirmation."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import ema, rsi
from app.engine.strategies.base import BaseStrategy


class EmaRsiStrategy(BaseStrategy):
    name = "ema_rsi"
    category = StrategyCategory.MEDIUM
    required_timeframes = ["15m", "1h"]

    def __init__(self, fast: int = 12, slow: int = 26, rsi_period: int = 14):
        self.fast = fast
        self.slow = slow
        self.rsi_period = rsi_period

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df = candles.get("15m")
        df_htf = candles.get("1h")
        if df is None or len(df) < self.slow + 5:
            return None

        e_fast = ema(df["close"], self.fast)
        e_slow = ema(df["close"], self.slow)
        r = rsi(df["close"], self.rsi_period)
        if pd.isna(e_fast.iloc[-1]) or pd.isna(e_slow.iloc[-1]) or pd.isna(r.iloc[-1]):
            return None

        # Bullish cross: fast crossed above slow on the last bar; RSI in 50-70 range.
        crossed_up = e_fast.iloc[-2] <= e_slow.iloc[-2] and e_fast.iloc[-1] > e_slow.iloc[-1]
        crossed_dn = e_fast.iloc[-2] >= e_slow.iloc[-2] and e_fast.iloc[-1] < e_slow.iloc[-1]

        # Multi-TF: don't fight the 1h trend.
        htf_up = True
        if df_htf is not None and len(df_htf) > 50:
            htf_up = df_htf["close"].iloc[-1] > ema(df_htf["close"], 50).iloc[-1]

        if crossed_up and 50 < r.iloc[-1] < 70 and htf_up:
            return Signal(
                side=Side.BUY, confidence=0.65, strategy=self.name,
                reason=f"EMA{self.fast}>{self.slow} cross, RSI {r.iloc[-1]:.0f}",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd,
            )
        if crossed_dn and 30 < r.iloc[-1] < 50 and not htf_up:
            return Signal(
                side=Side.SELL, confidence=0.6, strategy=self.name,
                reason=f"EMA{self.fast}<{self.slow} cross, RSI {r.iloc[-1]:.0f}",
                token_in=token_in, token_out=token_out,
                suggested_amount_usd=capital_usd,
            )
        return None
