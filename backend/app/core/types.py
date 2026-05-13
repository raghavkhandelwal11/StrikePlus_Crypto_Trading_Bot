"""Shared types and enums used across the trading engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REJECTED = "rejected"
    PARTIAL = "partial"


class StrategyCategory(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MarketRegime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOL = "high_vol"


class BotStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class Candle:
    """OHLCV candle."""
    ts: int            # ms epoch
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    side: Side
    confidence: float                       # 0..1
    strategy: str
    reason: str
    token_in: str
    token_out: str
    suggested_amount_usd: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeIntent:
    """A signal that has passed the risk gate; ready to send to execution."""
    side: Side
    token_in: str
    token_out: str
    amount_in_wei: int
    min_amount_out_wei: int
    slippage_pct: float
    expected_price: float
    strategy: str
    gas_price_gwei: float
    deadline_seconds: int = 60


@dataclass
class TradeResult:
    """The result of a trade attempt."""
    status: OrderStatus
    tx_hash: Optional[str] = None
    side: Optional[Side] = None
    token_in: Optional[str] = None
    token_out: Optional[str] = None
    amount_in: Optional[float] = None
    amount_out: Optional[float] = None
    price: Optional[float] = None
    gas_cost_usd: Optional[float] = None
    lp_fee_usd: Optional[float] = None
    slippage_pct: Optional[float] = None
    pnl_usd: Optional[float] = None
    strategy: Optional[str] = None
    error: Optional[str] = None
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WalletState:
    address: str
    bnb_balance: float
    token_balances: Dict[str, float]      # token_address -> balance
    deployed_capital_usd: float
    available_capital_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float


@dataclass
class BotConfig:
    """Configuration for a bot run."""
    duration_seconds: int
    strategy_category: StrategyCategory = StrategyCategory.MEDIUM
    auto_switch: bool = True
    tokens: List[str] = field(default_factory=list)
    quote_token: str = "WBNB"
    paper_mode: bool = True
