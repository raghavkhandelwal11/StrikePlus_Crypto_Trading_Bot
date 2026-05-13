"""In-memory bot state, accessible across modules and shared with WebSocket broadcasts."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional

from app.core.types import BotConfig, BotStatus, TradeResult


@dataclass
class TradeHistoryEntry:
    ts: str
    side: str
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    price: float
    pnl_usd: float
    strategy: str
    tx_hash: Optional[str]
    status: str
    notional_usd: float = 0.0           # USD value at execution
    gas_cost_usd: float = 0.0
    lp_fee_usd: float = 0.0
    reason: str = ""                    # entry/exit reason (e.g. take_profit)


@dataclass
class BotState:
    status: BotStatus = BotStatus.IDLE
    started_at: Optional[datetime] = None
    duration_seconds: int = 0
    config: Optional[BotConfig] = None
    active_strategy: str = "none"
    consecutive_losses: int = 0
    daily_pnl_usd: float = 0.0
    realized_pnl_usd: float = 0.0
    trades_this_hour: Deque[datetime] = field(default_factory=deque)
    trade_history: List[TradeHistoryEntry] = field(default_factory=list)
    last_error: Optional[str] = None
    kill_switch: bool = False

    def reset_daily(self) -> None:
        self.daily_pnl_usd = 0.0
        self.consecutive_losses = 0

    def record_trade(self, result: TradeResult, notional_usd: float = 0.0, reason: str = "") -> None:
        entry = TradeHistoryEntry(
            ts=result.ts.isoformat(),
            side=(result.side.value if result.side else "unknown"),
            token_in=result.token_in or "",
            token_out=result.token_out or "",
            amount_in=result.amount_in or 0.0,
            amount_out=result.amount_out or 0.0,
            price=result.price or 0.0,
            pnl_usd=result.pnl_usd or 0.0,
            strategy=result.strategy or "unknown",
            tx_hash=result.tx_hash,
            status=result.status.value,
            notional_usd=notional_usd,
            gas_cost_usd=result.gas_cost_usd or 0.0,
            lp_fee_usd=result.lp_fee_usd or 0.0,
            reason=reason,
        )
        self.trade_history.append(entry)
        if result.pnl_usd is not None:
            self.realized_pnl_usd += result.pnl_usd
            self.daily_pnl_usd += result.pnl_usd
            if result.pnl_usd < 0:
                self.consecutive_losses += 1
            elif result.pnl_usd > 0:
                self.consecutive_losses = 0
        self.trades_this_hour.append(result.ts)
        # purge older than an hour
        cutoff = datetime.utcnow() - timedelta(hours=1)
        while self.trades_this_hour and self.trades_this_hour[0] < cutoff:
            self.trades_this_hour.popleft()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "duration_seconds": self.duration_seconds,
            "active_strategy": self.active_strategy,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl_usd": round(self.daily_pnl_usd, 4),
            "realized_pnl_usd": round(self.realized_pnl_usd, 4),
            "trades_last_hour": len(self.trades_this_hour),
            "trade_count": len(self.trade_history),
            "last_error": self.last_error,
            "kill_switch": self.kill_switch,
            "config": (asdict(self.config) if self.config else None),
        }


# Process-wide singleton. Mutated by the orchestrator and read by API/WS handlers.
bot_state = BotState()
state_lock = asyncio.Lock()
