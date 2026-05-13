"""Low-risk: cross-DEX arbitrage scaffold.

This is a placeholder that documents the interface. A real implementation
should compare quotes from PancakeSwap V2 and another BSC DEX (Biswap,
Apeswap, PancakeV3) for the same pair, account for both swap fees and
gas on a routed atomic transaction, and only fire when the spread net of
costs is positive. Atomic execution typically requires a flash-loan
contract — out of scope for this initial drop, but the integration point is here.
"""
from __future__ import annotations

from typing import Optional

from app.core.types import Signal, StrategyCategory
from app.engine.strategies.base import BaseStrategy


class ArbitrageStrategy(BaseStrategy):
    name = "arbitrage"
    category = StrategyCategory.LOW
    required_timeframes = ["5m"]

    def evaluate(self, symbol, token_in, token_out, candles, capital_usd) -> Optional[Signal]:
        # Implement: fetch quote from PancakeSwap router AND a second DEX router,
        # compute net spread = (price_b / price_a) - 1 - fees_a - fees_b - gas_pct,
        # require > min_spread (e.g. 0.3%), then return a Signal that the
        # execution engine routes through both pools in a single tx.
        return None
