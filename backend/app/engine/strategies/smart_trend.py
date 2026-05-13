"""SmartTrend — the highest-quality long-only setup, ATR-aware.

Edge design (borrowed from professional trend followers):
  - Multi-timeframe ALIGNMENT: 4h trend up AND 1h pulling back AND 15m reversing
  - Volatility regime gate: ATR/price must be in a "tradeable" band (0.4%-3%)
  - Volume confirmation: above 20-bar average volume
  - RSI shows oversold-then-recovering on entry TF (catch the bounce, not the dump)
  - Only fires when ALL signals align — quality > quantity (1-3 per day)

The signal embeds proposed stop_loss & take_profit in metadata so the exit
manager can use ATR-based R-multiple stops instead of fixed %.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from app.core.types import Side, Signal, StrategyCategory
from app.engine.data.indicators import atr, ema, rsi, vwap
from app.engine.strategies.base import BaseStrategy


class SmartTrendStrategy(BaseStrategy):
    name = "smart_trend"
    category = StrategyCategory.MEDIUM
    required_timeframes = ["15m", "1h", "4h"]

    # ATR-based risk parameters (R = 1 unit of risk = atr_mult × ATR)
    atr_mult_stop: float = 1.5             # stop = entry - 1.5×ATR
    atr_mult_target: float = 3.0           # TP   = entry + 3×ATR (2R reward)

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        df15 = candles.get("15m")
        df1h = candles.get("1h")
        df4h = candles.get("4h") or df1h     # fallback if 4h not available

        if df15 is None or len(df15) < 100:
            return None
        if df1h is None or len(df1h) < 50:
            return None
        if df4h is None or len(df4h) < 30:
            return None

        close15 = df15["close"]
        last_price = float(close15.iloc[-1])
        a = atr(df15, 14).iloc[-1]
        if pd.isna(a) or a <= 0:
            return None

        atr_pct = a / last_price
        # Volatility regime gate — too quiet = no follow-through; too wild = whipsaws.
        if atr_pct < 0.004 or atr_pct > 0.030:
            return None

        # --- 4h: macro trend must be UP ---
        e4h_fast = ema(df4h["close"], 8).iloc[-1]
        e4h_slow = ema(df4h["close"], 21).iloc[-1]
        if pd.isna(e4h_fast) or pd.isna(e4h_slow) or e4h_fast <= e4h_slow:
            return None

        # --- 1h: short-term trend up AND not extended (price within 1.5 ATR of EMA21) ---
        e1h = ema(df1h["close"], 21).iloc[-1]
        if pd.isna(e1h):
            return None
        if df1h["close"].iloc[-1] <= e1h:
            return None
        a1h = atr(df1h, 14).iloc[-1]
        if pd.isna(a1h) or (df1h["close"].iloc[-1] - e1h) > 1.5 * a1h:
            return None      # too extended — let it pull back

        # --- 15m: oversold-then-recovering RSI (catch the bounce) ---
        r15 = rsi(close15, 14)
        recent_min = float(r15.iloc[-6:-1].min())
        r_now = float(r15.iloc[-1])
        if not (recent_min < 40 and r_now > 45):
            return None

        # --- 15m: VWAP & EMA50 — price reclaiming key levels ---
        v15 = vwap(df15).iloc[-1]
        e15_50 = ema(close15, 50).iloc[-1]
        if pd.isna(v15) or pd.isna(e15_50):
            return None
        if last_price < min(v15, e15_50) * 0.999:
            return None      # below both — not a clean reclaim

        # --- Volume confirmation ---
        vol_avg = df15["volume"].rolling(20).mean().iloc[-1]
        if pd.isna(vol_avg) or df15["volume"].iloc[-1] < vol_avg * 1.1:
            return None

        # All gates passed — build the signal with ATR-based stop/target.
        stop = last_price - self.atr_mult_stop * a
        target = last_price + self.atr_mult_target * a
        risk_per_unit = last_price - stop          # = atr_mult_stop * a
        rr = (target - last_price) / risk_per_unit   # should equal atr_mult_target/atr_mult_stop = 2.0

        # Confidence: blend the strength of each signal.
        confidence = 0.65
        if r_now > 55:
            confidence += 0.05
        if df15["volume"].iloc[-1] > vol_avg * 1.5:
            confidence += 0.05
        confidence = min(0.85, confidence)

        return Signal(
            side=Side.BUY,
            confidence=confidence,
            strategy=self.name,
            reason=f"4h↑ 1h↑ 15m RSI {recent_min:.0f}→{r_now:.0f}, vol×{df15['volume'].iloc[-1]/vol_avg:.1f}",
            token_in=token_in,
            token_out=token_out,
            suggested_amount_usd=capital_usd,
            metadata={
                "stop_loss": stop,
                "take_profit": target,
                "atr": a,
                "rr": rr,
                "entry_price": last_price,
            },
        )
