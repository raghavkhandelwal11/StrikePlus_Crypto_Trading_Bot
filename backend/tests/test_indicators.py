"""Smoke tests for indicators and regime detection."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.engine.data.indicators import detect_regime, ema, rsi


def _df(prices):
    n = len(prices)
    return pd.DataFrame({
        "ts": np.arange(n) * 60_000,
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": np.ones(n),
    })


def test_ema_and_rsi_finite():
    prices = np.linspace(100, 110, 300) + np.random.default_rng(1).normal(0, 0.1, 300)
    df = _df(prices)
    assert np.isfinite(ema(df["close"], 20).iloc[-1])
    assert np.isfinite(rsi(df["close"], 14).iloc[-1])


def test_regime_trend_up():
    prices = np.linspace(100, 200, 300)
    df = _df(prices)
    assert detect_regime(df) in ("trend_up", "high_vol")
