"""Per-trade cost calculator. Tracks gas + LP fee + slippage + cumulative totals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from app.core.config import get_settings


@dataclass
class CostBreakdown:
    gas_usd: float
    lp_fee_usd: float
    slippage_usd: float
    total_usd: float


@dataclass
class FeeStats:
    cumulative_gas_usd: float = 0.0
    cumulative_lp_fee_usd: float = 0.0
    cumulative_slippage_usd: float = 0.0
    trade_count: int = 0
    skipped_for_fees: int = 0
    by_strategy: Dict[str, float] = field(default_factory=dict)


class FeeCalculator:
    def __init__(self) -> None:
        self.s = get_settings()
        self.stats = FeeStats()

    def estimate(
        self,
        trade_size_usd: float,
        gas_units: int,
        gas_price_gwei: float,
        bnb_usd: float,
        slippage_pct: float,
    ) -> CostBreakdown:
        gas_bnb = gas_units * gas_price_gwei * 1e-9
        gas_usd = gas_bnb * bnb_usd
        lp_fee_usd = trade_size_usd * (self.s.pancake_lp_fee_pct / 100.0)
        slippage_usd = trade_size_usd * (slippage_pct / 100.0)
        total = gas_usd + lp_fee_usd + slippage_usd
        return CostBreakdown(gas_usd, lp_fee_usd, slippage_usd, total)

    def is_profitable(self, expected_profit_usd: float, costs: CostBreakdown) -> bool:
        buffer = self.s.fee_buffer_pct / 100.0
        return expected_profit_usd >= costs.total_usd * (1 + buffer)

    def record(self, costs: CostBreakdown, strategy: str) -> None:
        self.stats.cumulative_gas_usd += costs.gas_usd
        self.stats.cumulative_lp_fee_usd += costs.lp_fee_usd
        self.stats.cumulative_slippage_usd += costs.slippage_usd
        self.stats.trade_count += 1
        self.stats.by_strategy[strategy] = self.stats.by_strategy.get(strategy, 0.0) + costs.total_usd

    def record_skip(self) -> None:
        self.stats.skipped_for_fees += 1
