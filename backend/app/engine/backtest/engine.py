"""Vectorized-walk backtester. Replays historical candles and lets the strategy
manager fire signals; tracks equity, slippage, and fees.

Limitations:
  - Single-symbol. Extend `run_multi` for portfolio backtests.
  - Fills at next-bar open with configured slippage; no order book modeling.
  - No partial fills. A real DEX backtest would need liquidity at each candle.

For a faster vectorized backtest of single strategies, swap out the per-bar
loop for numpy ops. The current implementation trades speed for fidelity to
the live execution path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from app.core.types import Side, StrategyCategory
from app.engine.backtest.metrics import BacktestMetrics, compute_metrics
from app.engine.data.market_data import candles_to_df
from app.engine.strategies.manager import StrategyManager


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: List[float]
    trades: List[dict]
    final_equity: float


class Backtester:
    def __init__(
        self,
        starting_capital: float = 1000.0,
        fee_pct: float = 0.25,
        slippage_pct: float = 0.3,
    ):
        self.starting_capital = starting_capital
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.manager = StrategyManager()

    def run(
        self,
        candles: List,
        symbol: str = "BACKTEST",
        category: Optional[StrategyCategory] = None,
        warmup: int = 200,
    ) -> BacktestResult:
        df = candles_to_df(candles)
        if len(df) <= warmup + 5:
            return BacktestResult(compute_metrics([], []), [], [], self.starting_capital)

        cash = self.starting_capital
        position_units = 0.0
        avg_entry = 0.0

        equity_curve: List[float] = []
        trades: List[dict] = []
        trade_pnls: List[float] = []

        # Walk forward bar by bar, building rolling windows for the strategy manager.
        for i in range(warmup, len(df) - 1):
            window = df.iloc[: i + 1]
            # Provide multi-TF candles by resampling — backtests use a single 15m series.
            candles_by_tf = {"15m": window, "5m": window, "1m": window, "1h": window}
            sig_pair = self.manager.evaluate(
                symbol=symbol,
                token_in="USDT",
                token_out=symbol,
                candles_by_tf=candles_by_tf,
                capital_usd=cash,
                category=category,
            )
            next_open = df.iloc[i + 1]["open"]

            if sig_pair is not None:
                signal, regime = sig_pair
                size_usd = min(signal.suggested_amount_usd, cash * 0.5)
                if signal.side == Side.BUY and cash > 10 and position_units == 0:
                    fill_price = next_open * (1 + self.slippage_pct / 100.0)
                    fee = size_usd * self.fee_pct / 100.0
                    units = (size_usd - fee) / fill_price
                    cash -= size_usd
                    position_units = units
                    avg_entry = fill_price
                    trades.append({
                        "ts": int(df.iloc[i + 1]["ts"]),
                        "side": "buy",
                        "price": fill_price,
                        "size_usd": size_usd,
                        "strategy": signal.strategy,
                        "regime": regime,
                    })
                elif signal.side == Side.SELL and position_units > 0:
                    fill_price = next_open * (1 - self.slippage_pct / 100.0)
                    proceeds = position_units * fill_price
                    fee = proceeds * self.fee_pct / 100.0
                    pnl = proceeds - fee - position_units * avg_entry
                    cash += proceeds - fee
                    trade_pnls.append(pnl)
                    trades.append({
                        "ts": int(df.iloc[i + 1]["ts"]),
                        "side": "sell",
                        "price": fill_price,
                        "pnl_usd": pnl,
                        "strategy": signal.strategy,
                        "regime": regime,
                    })
                    position_units = 0.0
                    avg_entry = 0.0

            mark = df.iloc[i + 1]["close"]
            equity = cash + position_units * mark
            equity_curve.append(equity)

        # Close any open position at the last close
        if position_units > 0:
            last = df.iloc[-1]["close"]
            proceeds = position_units * last * (1 - self.slippage_pct / 100.0)
            fee = proceeds * self.fee_pct / 100.0
            pnl = proceeds - fee - position_units * avg_entry
            cash += proceeds - fee
            trade_pnls.append(pnl)
            position_units = 0.0
            equity_curve.append(cash)

        metrics = compute_metrics(equity_curve, trade_pnls)
        logger.info(f"backtest done: ret={metrics.total_return_pct:.2f}% sharpe={metrics.sharpe_ratio:.2f}")
        return BacktestResult(metrics, equity_curve, trades, cash + position_units * df.iloc[-1]["close"])
