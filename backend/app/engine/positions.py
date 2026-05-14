"""Position tracker — the single source of truth for what the bot currently holds.

The orchestrator used to fire BUY signals every tick because nothing told it
"you already own this token". This module fixes that: each token has one
Position with units, cost basis, and average entry price. Closing a position
emits realized PnL.

Both paper and live modes share this tracker; live mode reconciles against
on-chain balances on startup (TODO) but during a run the tracker is authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Position:
    token: str
    units: float = 0.0
    avg_entry_price: float = 0.0
    cost_basis_usd: float = 0.0
    opened_at: Optional[datetime] = None
    last_update: Optional[datetime] = None
    strategy: str = ""
    high_water_mark: float = 0.0           # tracks peak price since open, for trailing stop
    stop_loss: float = 0.0                 # ATR-based or %-based; 0 means use fallback %
    take_profit: float = 0.0               # target price
    initial_risk: float = 0.0              # (entry - stop) — the "R" for R-multiples
    window_id: Optional[str] = None        # which trading window owns this
    target_usd: float = 0.0                # full intended position size (Kelly-lite target)
    pyramid_step: int = 0                  # # of add-on legs done (0 = just opened)
    scale_outs_done: int = 0               # # of partial profit-takes done (max 1)
    entry_fees_paid_usd: float = 0.0       # cumulative buy-side fees (gas + LP)
                                            # — used to compute NET pnl on exit

    def is_open(self) -> bool:
        return self.units > 1e-9

    def mark_value_usd(self, price: float) -> float:
        return self.units * price

    def unrealized_pnl_usd(self, price: float) -> float:
        return self.units * price - self.cost_basis_usd

    def unrealized_pnl_pct(self, price: float) -> float:
        if self.cost_basis_usd <= 0:
            return 0.0
        return (price / self.avg_entry_price - 1.0) * 100.0 if self.avg_entry_price else 0.0

    def to_dict(self, mark_price: Optional[float] = None) -> dict:
        d = {
            "token": self.token,
            "units": self.units,
            "avg_entry_price": self.avg_entry_price,
            "cost_basis_usd": self.cost_basis_usd,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "strategy": self.strategy,
            "high_water_mark": self.high_water_mark,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "initial_risk": self.initial_risk,
            "window_id": self.window_id,
            "target_usd": self.target_usd,
            "pyramid_step": self.pyramid_step,
            "scale_outs_done": self.scale_outs_done,
            "entry_fees_paid_usd": self.entry_fees_paid_usd,
        }
        if mark_price is not None:
            d["mark_price"] = mark_price
            d["mark_value_usd"] = self.mark_value_usd(mark_price)
            d["unrealized_pnl_usd"] = self.unrealized_pnl_usd(mark_price)
            d["unrealized_pnl_pct"] = self.unrealized_pnl_pct(mark_price)
        return d


class PositionTracker:
    """Long-only position tracker keyed by (window_id|None, lowercased token)."""

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    @staticmethod
    def _key(token: str, window_id: Optional[str] = None) -> str:
        return f"{window_id or '_'}|{token.lower()}"

    # ---- queries ----

    def get(self, token: str, window_id: Optional[str] = None) -> Optional[Position]:
        p = self._positions.get(self._key(token, window_id))
        return p if p and p.is_open() else None

    def has_open(self, token: str, window_id: Optional[str] = None) -> bool:
        return self.get(token, window_id) is not None

    def all_open(self) -> List[Position]:
        return [p for p in self._positions.values() if p.is_open()]

    def open_tokens(self) -> List[str]:
        return [p.token for p in self.all_open()]

    def by_window(self, window_id: str) -> List[Position]:
        return [p for p in self._positions.values()
                if p.is_open() and p.window_id == window_id]

    # ---- mutations ----

    def apply_buy(
        self,
        token: str,
        units: float,
        fill_price: float,
        strategy: str,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        window_id: Optional[str] = None,
        target_usd: float = 0.0,
        is_pyramid: bool = False,
        fees_paid_usd: float = 0.0,
    ) -> Position:
        """Open or add to a long position. Updates avg entry as a weighted mean.

        On initial open, records ATR-based stop/target and target_usd (the full
        intended position size for pyramiding). On pyramid adds, keeps the
        original stop/target (don't re-arm based on new bar) and bumps the step.

        `fees_paid_usd` accumulates onto the position so that when we close
        (in part or in full), apply_sell can deduct a proportional share of
        the entry fees from the realized PnL — producing TRUE net profit.
        """
        key = self._key(token, window_id)
        p = self._positions.get(key) or Position(
            token=token, opened_at=datetime.utcnow(), window_id=window_id,
        )
        first_entry = not p.is_open()
        added_cost = units * fill_price
        new_units = p.units + units
        if new_units > 0:
            p.cost_basis_usd += added_cost
            p.avg_entry_price = p.cost_basis_usd / new_units
        p.units = new_units
        p.strategy = strategy
        p.last_update = datetime.utcnow()
        p.high_water_mark = max(p.high_water_mark, fill_price)
        p.entry_fees_paid_usd += max(0.0, fees_paid_usd)
        if first_entry:
            p.stop_loss = stop_loss
            p.take_profit = take_profit
            p.initial_risk = max(0.0, fill_price - stop_loss) if stop_loss > 0 else 0.0
            p.target_usd = target_usd or added_cost
            p.pyramid_step = 0
            p.scale_outs_done = 0
        elif is_pyramid:
            p.pyramid_step += 1
            # Keep original stop_loss / take_profit / initial_risk — the trade
            # plan was set at first entry; adds don't change the risk geometry.
        self._positions[key] = p
        return p

    def apply_sell(
        self,
        token: str,
        units: float,
        fill_price: float,
        window_id: Optional[str] = None,
        sell_fees_usd: float = 0.0,
    ) -> tuple[float, Optional[Position]]:
        """Close all or part of a position. Returns (NET_realized_pnl_usd, position_snapshot).

        NET PnL math:
            gross  = (fill_price - avg_entry) * units
            buy_fees_share   = entry_fees_paid_usd * (units / units_before)
            net    = gross - buy_fees_share - sell_fees_usd

        Cost basis AND entry-fee accumulator both reduce proportionally so
        partial closes preserve the per-unit entry economics.
        """
        key = self._key(token, window_id)
        p = self._positions.get(key)
        if p is None or not p.is_open():
            return 0.0, None
        units = min(units, p.units)
        portion = units / p.units if p.units > 0 else 1.0
        gross = (fill_price - p.avg_entry_price) * units
        buy_fees_share = p.entry_fees_paid_usd * portion
        net_realized = gross - buy_fees_share - max(0.0, sell_fees_usd)

        p.cost_basis_usd *= (1.0 - portion)
        p.entry_fees_paid_usd *= (1.0 - portion)
        p.units -= units
        p.last_update = datetime.utcnow()
        if p.units < 1e-9:
            # Flatten — clear all per-position state
            p.units = 0.0
            p.cost_basis_usd = 0.0
            p.avg_entry_price = 0.0
            p.opened_at = None
            p.high_water_mark = 0.0
            p.stop_loss = 0.0
            p.take_profit = 0.0
            p.initial_risk = 0.0
            p.target_usd = 0.0
            p.pyramid_step = 0
            p.scale_outs_done = 0
            p.entry_fees_paid_usd = 0.0
        return net_realized, p

    def update_mark(self, token: str, price: float) -> None:
        """Bump the high-water mark on EVERY position holding this token.

        We iterate because positions are keyed by (window_id, token) and the
        same token can live in multiple windows.
        """
        tl = token.lower()
        for p in self._positions.values():
            if p.is_open() and p.token.lower() == tl:
                p.high_water_mark = max(p.high_water_mark, price)
