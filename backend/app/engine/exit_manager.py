"""Smart exit decision engine — R-multiple aware.

If a position has an explicit `stop_loss` (set by a smart strategy from ATR):
  - Use that price as the hard stop.
  - Take profit at `take_profit`.
  - After +1R unrealized → ratchet stop to ENTRY (break-even = "free trade").
  - After +1.5R unrealized → ratchet stop to entry + 0.5R (locked in 0.5R profit).
  - Trailing stop kicks in at +2R (one ATR from peak).

If a position has NO explicit stop (legacy strategies):
  - Fall back to fixed % TP/SL from config.

Plus: time-based exit and reverse-signal exit (same as before).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import get_settings
from app.engine.positions import Position


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str = ""
    fraction: float = 1.0
    # Optional: update the position's stop loss in-place (for trailing).
    new_stop_loss: Optional[float] = None


class ExitManager:
    def __init__(self) -> None:
        self.s = get_settings()

    def check(
        self,
        position: Position,
        current_price: float,
        reverse_signal: bool = False,
    ) -> ExitDecision:
        # --- R-multiple system (preferred when position has explicit stop) ---
        if position.stop_loss > 0 and position.initial_risk > 0:
            return self._check_r_multiple(position, current_price, reverse_signal)
        # --- Fallback: fixed-% system for legacy strategies ---
        return self._check_fixed_pct(position, current_price, reverse_signal)

    # ---- R-multiple ----

    def _check_r_multiple(
        self, p: Position, price: float, reverse: bool,
    ) -> ExitDecision:
        # 1. Hard stop (initial or ratcheted)
        if price <= p.stop_loss:
            r_pnl = (price - p.avg_entry_price) / p.initial_risk
            return ExitDecision(True, f"stop_hit @ ${p.stop_loss:.4f} ({r_pnl:+.2f}R)")

        # 2. Take profit
        if p.take_profit > 0 and price >= p.take_profit:
            return ExitDecision(True, f"target_hit @ ${p.take_profit:.4f} (+2R)")

        # 3. Ratchet logic — update the stop, don't exit.
        unreal_r = (price - p.avg_entry_price) / p.initial_risk
        new_stop = p.stop_loss

        if unreal_r >= 2.0:
            # Trailing: 1 ATR (= 1R risk distance) below the HWM
            trailed = p.high_water_mark - p.initial_risk
            new_stop = max(new_stop, trailed)
        elif unreal_r >= 1.5:
            # Lock 0.5R: stop at entry + 0.5R
            new_stop = max(new_stop, p.avg_entry_price + 0.5 * p.initial_risk)
        elif unreal_r >= 1.0:
            # Free trade: stop at entry
            new_stop = max(new_stop, p.avg_entry_price)

        if new_stop > p.stop_loss:
            return ExitDecision(
                False, reason=f"ratchet_stop -> ${new_stop:.4f}",
                new_stop_loss=new_stop,
            )

        # 4. Time exit
        if p.opened_at and self.s.max_holding_minutes > 0:
            age = datetime.utcnow() - p.opened_at
            if age >= timedelta(minutes=self.s.max_holding_minutes):
                return ExitDecision(
                    True, f"time_exit ({age.total_seconds()/60:.0f}m, {unreal_r:+.2f}R)"
                )

        # 5. Reverse signal exit (only if at least break-even — avoid panic-selling lows)
        if reverse and unreal_r >= 0:
            return ExitDecision(True, f"reverse_signal ({unreal_r:+.2f}R)")

        return ExitDecision(False)

    # ---- Fixed % (legacy) ----

    def _check_fixed_pct(
        self, p: Position, price: float, reverse: bool,
    ) -> ExitDecision:
        pnl_pct = p.unrealized_pnl_pct(price)
        if pnl_pct <= -self.s.stop_loss_pct:
            return ExitDecision(True, f"stop_loss ({pnl_pct:.2f}%)")
        if pnl_pct >= self.s.take_profit_pct:
            return ExitDecision(True, f"take_profit (+{pnl_pct:.2f}%)")
        if (
            self.s.trailing_stop_pct > 0
            and p.high_water_mark > p.avg_entry_price * 1.005
        ):
            dd = (p.high_water_mark - price) / p.high_water_mark * 100.0
            if dd >= self.s.trailing_stop_pct:
                return ExitDecision(True, f"trailing_stop (dd {dd:.2f}%)")
        if p.opened_at and self.s.max_holding_minutes > 0:
            age = datetime.utcnow() - p.opened_at
            if age >= timedelta(minutes=self.s.max_holding_minutes):
                return ExitDecision(True, f"time_exit ({age.total_seconds()/60:.0f}m, {pnl_pct:+.2f}%)")
        if reverse:
            return ExitDecision(True, f"reverse_signal ({pnl_pct:+.2f}%)")
        return ExitDecision(False)
