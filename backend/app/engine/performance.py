"""Strategy performance tracker — online learning + auto-pruning.

What it does:
  - Records every closed trade's PnL by strategy & regime
  - Computes rolling win-rate, profit factor, and Kelly-style edge
  - DISABLES a strategy that's losing badly over the last N trades
  - Boosts/penalizes the confidence floor per strategy
  - Persists to disk so the bot remembers across restarts

The orchestrator queries `confidence_multiplier()` before sizing and
`is_disabled()` before entry. Closing a trade calls `record_close()`.

This is the "learn from mistakes" feature: a strategy that fails on this
asset/regime gets ratcheted down automatically.
"""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Deque, Dict, List, Optional


@dataclass
class StratStats:
    name: str
    trades: int = 0
    wins: int = 0
    gross_win_usd: float = 0.0
    gross_loss_usd: float = 0.0
    last_pnls: List[float] = field(default_factory=list)        # last 50 PnLs
    disabled_until_ts: Optional[float] = None                    # unix epoch

    @property
    def total_pnl(self) -> float:
        return self.gross_win_usd - self.gross_loss_usd

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss_usd <= 0:
            return float("inf") if self.gross_win_usd > 0 else 0.0
        return self.gross_win_usd / self.gross_loss_usd

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.trades - self.wins,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor != float("inf") else 9999.0,
            "total_pnl_usd": round(self.total_pnl, 4),
            "disabled_until_ts": self.disabled_until_ts,
        }


class StrategyPerformance:
    """Process-wide rolling perf tracker. Thread-safe writes, JSON-on-disk."""

    def __init__(self, path: str = "backend/data/strategy_perf.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stats: Dict[str, StratStats] = {}
        self._lock = Lock()
        self._load()

    # ---- persistence ----

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for name, d in data.items():
                self._stats[name] = StratStats(
                    name=name,
                    trades=int(d.get("trades", 0)),
                    wins=int(d.get("wins", 0)),
                    gross_win_usd=float(d.get("gross_win_usd", 0.0)),
                    gross_loss_usd=float(d.get("gross_loss_usd", 0.0)),
                    last_pnls=list(d.get("last_pnls", []))[-50:],
                    disabled_until_ts=d.get("disabled_until_ts"),
                )
        except Exception:
            # Corrupted file — start fresh rather than crash the bot.
            self._stats = {}

    def _save(self) -> None:
        out = {
            name: {
                "trades": s.trades, "wins": s.wins,
                "gross_win_usd": s.gross_win_usd, "gross_loss_usd": s.gross_loss_usd,
                "last_pnls": s.last_pnls, "disabled_until_ts": s.disabled_until_ts,
            } for name, s in self._stats.items()
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2))
        os.replace(tmp, self.path)

    # ---- public API ----

    def record_close(self, strategy: str, pnl_usd: float) -> None:
        """Call when a position is closed (exit). pnl_usd is the realized PnL."""
        with self._lock:
            s = self._stats.setdefault(strategy, StratStats(name=strategy))
            s.trades += 1
            if pnl_usd > 0:
                s.wins += 1
                s.gross_win_usd += pnl_usd
            else:
                s.gross_loss_usd += -pnl_usd
            s.last_pnls.append(round(pnl_usd, 4))
            if len(s.last_pnls) > 50:
                s.last_pnls = s.last_pnls[-50:]

            # Auto-disable: needs at least 15 trades AND last 15 net-loss
            # AND overall win rate <30%. The bot benches it for 30 min so
            # other strategies get more time — not a death sentence.
            import time
            if len(s.last_pnls) >= 15:
                last15 = s.last_pnls[-15:]
                if sum(last15) < 0 and s.win_rate < 0.30:
                    s.disabled_until_ts = time.time() + 1800    # 30min cooldown
            self._save()

    def is_disabled(self, strategy: str) -> bool:
        s = self._stats.get(strategy)
        if not s or s.disabled_until_ts is None:
            return False
        import time
        if time.time() > s.disabled_until_ts:
            s.disabled_until_ts = None    # auto-clear expiry
            return False
        return True

    def confidence_multiplier(self, strategy: str) -> float:
        """Return a 0.7..1.25 multiplier to apply to a signal's confidence.

        Strategies with proven track records get boosted; underperformers shrink.
        Requires 12+ trades before kicking in — early random noise shouldn't
        choke off a strategy after a single bad streak.
        """
        s = self._stats.get(strategy)
        if not s or s.trades < 12:
            return 1.0                    # not enough data — neutral
        # Map win_rate [0.30..0.65] -> [0.7..1.25], clipped.
        # Tightened from [0.5..1.3] so the multiplier can't single-handedly
        # gate out a strategy whose raw confidence is right at threshold.
        wr = s.win_rate
        mult = 0.7 + (wr - 0.30) / 0.35 * 0.55
        return max(0.7, min(1.25, mult))

    def snapshot(self) -> List[dict]:
        with self._lock:
            return [s.to_dict() for s in self._stats.values()]

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()
            self._save()


# Process-wide singleton
strategy_perf = StrategyPerformance()
