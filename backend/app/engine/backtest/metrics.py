"""Backtest performance metrics: Sharpe, max drawdown, win rate, etc."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class BacktestMetrics:
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    num_trades: int
    profit_factor: float


def compute_metrics(equity_curve: List[float], trade_pnls: List[float]) -> BacktestMetrics:
    """Compute standard metrics from an equity curve and per-trade PnLs (in % or USD).

    Treats trade_pnls as $ amounts; equity_curve as $ amounts indexed by step.
    """
    if not equity_curve or len(equity_curve) < 2:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, len(trade_pnls), 0)

    eq = np.array(equity_curve, dtype=float)
    rets = np.diff(eq) / eq[:-1]
    rets = rets[np.isfinite(rets)]

    total_return_pct = (eq[-1] / eq[0] - 1) * 100.0

    # Sharpe — assume per-bar returns, annualize with sqrt(N) given an arbitrary period.
    # For a calendar-aware Sharpe, scale by sqrt(bars_per_year).
    sharpe = 0.0
    if rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * np.sqrt(252))

    # Max drawdown
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd_pct = float(dd.min() * 100.0) if dd.size else 0.0

    if trade_pnls:
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        win_rate = len(wins) / len(trade_pnls) * 100.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    else:
        win_rate = avg_win = avg_loss = profit_factor = 0.0

    return BacktestMetrics(
        total_return_pct=total_return_pct,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd_pct,
        win_rate_pct=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        num_trades=len(trade_pnls),
        profit_factor=profit_factor,
    )
