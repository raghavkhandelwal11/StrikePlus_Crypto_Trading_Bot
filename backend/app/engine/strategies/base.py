"""Base strategy interface. All strategies emit zero or one Signal per evaluation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import pandas as pd

from app.core.types import Signal, StrategyCategory


class BaseStrategy(ABC):
    name: str = "base"
    category: StrategyCategory = StrategyCategory.MEDIUM

    # Timeframes the strategy needs (highest priority first).
    required_timeframes: List[str] = ["5m"]

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        token_in: str,
        token_out: str,
        candles: Dict[str, pd.DataFrame],
        capital_usd: float,
    ) -> Optional[Signal]:
        """Return a Signal or None.

        `candles` maps timeframe label -> dataframe with columns
        [ts, open, high, low, close, volume].
        """
        raise NotImplementedError
