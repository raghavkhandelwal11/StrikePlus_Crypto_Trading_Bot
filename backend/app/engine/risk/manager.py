"""Risk manager.

Enforces every limit listed in the spec:
  - max capital per trade
  - min capital threshold
  - max trades per hour
  - max slippage
  - fee cap (skip if fees > expected profit)
  - daily loss limit
  - circuit breaker (consecutive losses)
  - kill switch (manual + auto)
  - gas spike protection
  - liquidity validation
  - token blacklist
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.core.config import Settings, get_settings
from app.core.state import bot_state
from app.core.types import Signal


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    sized_amount_usd: float = 0.0
    slippage_pct: float = 0.0


class RiskManager:
    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or get_settings()

    # ---- public API ----

    def check_signal(
        self,
        signal: Signal,
        wallet_capital_usd: float,
        gas_price_gwei: float,
        pool_liquidity_usd: float,
        expected_profit_usd: float,
        expected_fee_usd: float,
    ) -> RiskDecision:
        """Validate a signal against every limit. Returns decision + sized amount."""
        # 1. Kill switch
        if bot_state.kill_switch:
            return RiskDecision(False, "kill_switch_active")

        # 2. Token blacklist
        if signal.token_in.lower() in self.s.blacklist or signal.token_out.lower() in self.s.blacklist:
            return RiskDecision(False, "token_blacklisted")

        # 3. Min capital threshold
        if wallet_capital_usd < self.s.min_capital_threshold_usd:
            return RiskDecision(False, "below_min_capital_threshold")

        # 4. Daily loss limit
        if bot_state.daily_pnl_usd <= -abs(self.s.max_daily_loss_pct / 100.0 * wallet_capital_usd):
            bot_state.kill_switch = True
            return RiskDecision(False, "daily_loss_limit_hit (kill_switch engaged)")

        # 5. Circuit breaker on consecutive losses
        if bot_state.consecutive_losses >= self.s.circuit_breaker_losses:
            return RiskDecision(False, f"circuit_breaker (losses={bot_state.consecutive_losses})")

        # 6. Trades per hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = sum(1 for ts in bot_state.trades_this_hour if ts >= cutoff)
        if recent >= self.s.max_trades_per_hour:
            return RiskDecision(False, f"max_trades_per_hour ({recent}>={self.s.max_trades_per_hour})")

        # 7. Gas spike
        if gas_price_gwei > self.s.max_gas_price_gwei:
            return RiskDecision(False, f"gas_spike ({gas_price_gwei:.2f} > {self.s.max_gas_price_gwei})")

        # 8. Liquidity check
        if pool_liquidity_usd < self.s.min_liquidity_usd:
            return RiskDecision(False, f"insufficient_liquidity (${pool_liquidity_usd:,.0f})")

        # 9. Fee cap — skip if hard costs eat expected profit.
        # Require: expected_profit > expected_fee × (1 + fee_buffer_pct).
        # This means fees must be exceeded by at least fee_buffer_pct% of margin.
        required_profit = expected_fee_usd * (1.0 + self.s.fee_buffer_pct / 100.0)
        if expected_profit_usd <= required_profit:
            return RiskDecision(
                False,
                f"fees_exceed_profit (fee=${expected_fee_usd:.3f} profit=${expected_profit_usd:.3f})",
            )

        # 10. Sizing — cap to per-trade limit and confidence-scale
        sized = min(signal.suggested_amount_usd, self.s.max_capital_per_trade_usd)
        sized = sized * max(0.3, min(1.0, signal.confidence))   # taper by confidence
        if sized < self.s.min_capital_threshold_usd:
            return RiskDecision(False, "sized_below_min_threshold")

        # 11. Slippage — cap by config
        slippage = min(self.s.max_slippage_pct, max(0.1, self.s.max_slippage_pct))

        return RiskDecision(True, "ok", sized_amount_usd=sized, slippage_pct=slippage)

    def trip_kill_switch(self, reason: str) -> None:
        bot_state.kill_switch = True
        bot_state.last_error = f"kill_switch: {reason}"
        logger.error(f"KILL SWITCH ENGAGED: {reason}")

    def release_kill_switch(self) -> None:
        bot_state.kill_switch = False
        logger.warning("kill switch released")
