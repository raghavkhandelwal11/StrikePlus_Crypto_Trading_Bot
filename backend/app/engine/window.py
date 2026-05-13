"""TradingWindow + WindowManager — supports multiple independent trading runs.

Each window is an isolated async task with:
  - its own duration, deadline, and (extensible) end time
  - its own capital cap (max_deploy_usd)
  - its own token list, strategy category, auto-switch
  - its own positions (tagged with window_id in the shared PositionTracker)
  - its own deployed_capital, realized_pnl, trade history
  - its own kill switch

A global PositionTracker holds all positions across windows (keyed by
window_id|token). Closing a window flushes only its own positions.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import get_settings
from app.core.types import StrategyCategory


@dataclass
class WindowSummary:
    id: str
    status: str                            # running | stopped | killed | completed
    started_at: str
    deadline_at: str
    duration_seconds: int
    tokens: List[str]
    strategy_category: str
    auto_switch: bool
    paper_mode: bool
    max_deploy_usd: float
    deployed_usd: float
    realized_pnl_usd: float
    trade_count: int
    open_positions: int
    kill_switch: bool
    extended_by_seconds: int = 0
    phase: str = "starting"                # warmup | analyzing | pending | holding | cooldown | …
    reasoning: str = "initializing"        # human-readable explanation of current decision


@dataclass
class TradingWindow:
    id: str
    paper_mode: bool
    tokens: List[str]
    strategy_category: StrategyCategory
    auto_switch: bool
    max_deploy_usd: float
    duration_seconds: int
    started_at: datetime
    deadline_at: datetime
    extended_by_seconds: int = 0
    status: str = "running"
    kill_switch: bool = False
    deployed_usd: float = 0.0
    realized_pnl_usd: float = 0.0
    trade_count: int = 0
    # cross-tick state
    last_fill_ts: Dict[str, float] = field(default_factory=dict)
    # signal-persistence buffer: tracks the last seen signal per token so the
    # orchestrator can require a signal to fire on 2+ consecutive ticks before
    # committing capital. Each entry: { strategy: str, count: int, first_seen: float }.
    pending_signals: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # last analysis phase + human-readable reasoning, shown in the UI so the
    # user can see what the bot is "thinking" (warmup, analyzing, etc.).
    phase: str = "starting"
    reasoning: str = "initializing"
    task: Optional[asyncio.Task] = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    trade_history: List[dict] = field(default_factory=list)

    def summary(self, open_positions: int = 0) -> WindowSummary:
        return WindowSummary(
            id=self.id,
            status=self.status,
            started_at=self.started_at.isoformat(),
            deadline_at=self.deadline_at.isoformat(),
            duration_seconds=self.duration_seconds,
            tokens=self.tokens,
            strategy_category=self.strategy_category.value,
            auto_switch=self.auto_switch,
            paper_mode=self.paper_mode,
            max_deploy_usd=self.max_deploy_usd,
            deployed_usd=round(self.deployed_usd, 4),
            realized_pnl_usd=round(self.realized_pnl_usd, 4),
            trade_count=self.trade_count,
            open_positions=open_positions,
            kill_switch=self.kill_switch,
            extended_by_seconds=self.extended_by_seconds,
            phase=self.phase,
            reasoning=self.reasoning,
        )

    def set_phase(self, phase: str, reasoning: str) -> None:
        self.phase = phase
        self.reasoning = reasoning

    def extend(self, seconds: int) -> None:
        self.deadline_at += timedelta(seconds=seconds)
        self.duration_seconds += seconds
        self.extended_by_seconds += seconds


class WindowManager:
    """Singleton — owns the lifecycle of every TradingWindow."""

    def __init__(self) -> None:
        self.s = get_settings()
        self.windows: Dict[str, TradingWindow] = {}

    # ---- queries ----

    def get(self, window_id: str) -> Optional[TradingWindow]:
        return self.windows.get(window_id)

    def all(self) -> List[TradingWindow]:
        return list(self.windows.values())

    def running(self) -> List[TradingWindow]:
        return [w for w in self.windows.values() if w.status == "running"]

    # ---- lifecycle ----

    def create(
        self,
        *, tokens: List[str], duration_seconds: int,
        strategy_category: StrategyCategory, auto_switch: bool,
        paper_mode: bool, max_deploy_usd: float,
    ) -> TradingWindow:
        if len(self.running()) >= self.s.max_concurrent_windows:
            raise RuntimeError(
                f"max {self.s.max_concurrent_windows} concurrent windows already running"
            )
        now = datetime.utcnow()
        w = TradingWindow(
            id=uuid.uuid4().hex[:8],
            paper_mode=paper_mode,
            tokens=tokens,
            strategy_category=strategy_category,
            auto_switch=auto_switch,
            max_deploy_usd=max_deploy_usd,
            duration_seconds=duration_seconds,
            started_at=now,
            deadline_at=now + timedelta(seconds=duration_seconds),
        )
        self.windows[w.id] = w
        logger.info(f"window created {w.id} duration={duration_seconds}s deploy<={max_deploy_usd}")
        return w

    def remove(self, window_id: str) -> None:
        self.windows.pop(window_id, None)


window_manager = WindowManager()
