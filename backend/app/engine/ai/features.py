"""Feature engineering for AI models. Pure pandas — used by both training and inference."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.data.indicators import atr, ema, rsi


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of model-ready features. Drops rows with NaNs."""
    out = pd.DataFrame(index=df.index)
    close = df["close"]
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_15"] = close.pct_change(15)
    out["rsi_14"] = rsi(close, 14) / 100.0
    out["ema_fast_slow"] = ema(close, 12) / ema(close, 26) - 1.0
    a = atr(df, 14)
    out["atr_norm"] = a / close
    out["vol_change"] = df["volume"].pct_change(5)
    out["range_pct"] = (df["high"] - df["low"]) / close
    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    return out


def make_labels(df: pd.DataFrame, horizon: int = 5, threshold: float = 0.002) -> pd.Series:
    """Multi-class label: 1 = up, -1 = down, 0 = flat over `horizon` bars."""
    fwd = df["close"].shift(-horizon) / df["close"] - 1.0
    y = pd.Series(0, index=df.index)
    y[fwd > threshold] = 1
    y[fwd < -threshold] = -1
    return y
