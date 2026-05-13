"""Technical indicators. Wraps the `ta` library and adds a few helpers."""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import VolumeWeightedAveragePrice


def ema(series: pd.Series, period: int) -> pd.Series:
    return EMAIndicator(close=series, window=period).ema_indicator()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    return RSIIndicator(close=series, window=period).rsi()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=period
    ).average_true_range()


def macd(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    m = MACD(close=series)
    return m.macd(), m.macd_signal(), m.macd_diff()


def bollinger(series: pd.Series, period: int = 20, k: float = 2.0):
    bb = BollingerBands(close=series, window=period, window_dev=k)
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()


def vwap(df: pd.DataFrame) -> pd.Series:
    return VolumeWeightedAveragePrice(
        high=df["high"], low=df["low"], close=df["close"], volume=df["volume"]
    ).volume_weighted_average_price()


def realized_volatility(series: pd.Series, period: int = 20) -> pd.Series:
    """Annualized stdev of log returns."""
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(period).std() * np.sqrt(period)


def detect_regime(df: pd.DataFrame) -> str:
    """Cheap regime classifier — returns 'trend_up', 'trend_down', 'range', or 'high_vol'.

    Logic:
      - High vol if ATR/price > 2%
      - Trend up if EMA50 > EMA200 and price above EMA50 by > 0.3%
      - Trend down if mirror condition
      - Else range
    """
    if len(df) < 200:
        return "range"
    close = df["close"]
    e50 = ema(close, 50).iloc[-1]
    e200 = ema(close, 200).iloc[-1]
    last = close.iloc[-1]
    a = atr(df, 14).iloc[-1]
    if pd.isna(a) or pd.isna(e50) or pd.isna(e200):
        return "range"
    if a / last > 0.02:
        return "high_vol"
    if e50 > e200 and last > e50 * 1.003:
        return "trend_up"
    if e50 < e200 and last < e50 * 0.997:
        return "trend_down"
    return "range"
