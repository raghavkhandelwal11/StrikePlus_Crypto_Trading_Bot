"""Pydantic schemas for the REST/WebSocket API."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DurationKey = Literal["15m", "30m", "1h", "3h", "6h", "12h", "1d", "1w"]

DURATION_SECONDS = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h":  60 * 60,
    "3h":  3 * 60 * 60,
    "6h":  6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d":  24 * 60 * 60,
    "1w":  7 * 24 * 60 * 60,
}


class StartBotRequest(BaseModel):
    duration: DurationKey
    strategy_category: Literal["low", "medium", "high"] = "medium"
    auto_switch: bool = True
    tokens: List[str] = Field(default_factory=list)
    paper_mode: bool = True


class StopBotRequest(BaseModel):
    reason: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    started_at: Optional[str]
    duration_seconds: int
    active_strategy: str
    consecutive_losses: int
    daily_pnl_usd: float
    realized_pnl_usd: float
    trades_last_hour: int
    trade_count: int
    last_error: Optional[str]
    kill_switch: bool
    config: Optional[dict] = None


class WalletResponse(BaseModel):
    address: str
    bnb_balance: float
    token_balances: dict
    deployed_capital_usd: float
    available_capital_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float


class BacktestRequest(BaseModel):
    symbol: str = "BNBUSDT"
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "15m"
    limit: int = Field(500, ge=100, le=1000)
    starting_capital: float = 1000.0
    fee_pct: float = 0.25
    slippage_pct: float = 0.3
    category: Optional[Literal["low", "medium", "high"]] = None


class BacktestResponse(BaseModel):
    metrics: dict
    final_equity: float
    trades: list
    equity_curve: list
