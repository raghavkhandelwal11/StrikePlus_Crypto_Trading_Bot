"""Multi-window orchestrator.

Each TradingWindow runs its own per-tick loop:
  1. Fetch multi-TF candles
  2. EXIT phase  — check stop/target/trailing for THIS window's positions
  3. ENTRY phase — only if no open position on this token in THIS window AND
                   cooldown passed AND below caps AND signal passes confidence floor
                   AND risk gate AND smart sizing (vol-targeted)
  4. Broadcast   — status + per-window summaries + positions over WebSocket

Global controls:
  - start_window(config) → spawns a new window
  - stop_window(id, close_positions=True)
  - kill_window(id) → closes that window's positions and stops it
  - terminate_all() → stops EVERY window and closes EVERY position
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from app.core.config import get_settings
from app.core.event_bus import bus
from app.core.state import bot_state, state_lock
from app.core.types import (
    BotConfig,
    BotStatus,
    OrderStatus,
    Side,
    Signal,
    StrategyCategory,
    TradeIntent,
)
from app.engine.ai import AIConfirmation
from app.engine.alerts import Notifier
from app.engine.data.market_data import candles_to_df, market_data
from app.engine.execution import ExecutionEngine
from app.engine.exit_manager import ExitManager
from app.engine.fees import FeeCalculator
from app.engine.performance import strategy_perf
from app.engine.positions import Position, PositionTracker
from app.engine.risk import RiskManager
from app.engine.strategies import StrategyManager
from app.engine.wallet import Wallet
from app.engine.window import TradingWindow, window_manager


# Map BSC token addresses (lowercased) → Binance OHLCV symbol pairs.
_SYMBOL_MAP = {
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": "BNBUSDT",     # WBNB
    "0xe9e7cea3dedca5984780bafc599bd69add087d56": "BUSDUSDT",    # BUSD
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": "ETHUSDT",     # ETH-peg
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": "BTCUSDT",     # BTCB
    "0xcc42724c6683b7e57334c4e856f4c9965ed682bd": "MATICUSDT",   # MATIC-peg
}


def _binance_symbol(token: str) -> Optional[str]:
    return _SYMBOL_MAP.get(token.lower())


# ---------------------------------------------------------------------------
# Opportunity-quality thresholds per risk category.
#
#   min_agree       : how many strategies must fire BUY simultaneously
#   min_conf        : minimum average confidence across agreeing signals
#   persistence     : how many consecutive ticks the setup must hold before entry
#   warmup_seconds  : "cold start" period after window creation during which
#                     the bot REFUSES to trade — gives the user visible patience
#
# Low risk demands more agreement, more confidence, and a longer warmup. High
# risk takes single-signal entries almost immediately.
# ---------------------------------------------------------------------------
_QUALITY: Dict[StrategyCategory, Dict[str, Any]] = {
    StrategyCategory.LOW:    {"min_agree": 2, "min_conf": 0.70, "persistence": 3, "warmup_seconds": 90},
    StrategyCategory.MEDIUM: {"min_agree": 2, "min_conf": 0.65, "persistence": 2, "warmup_seconds": 45},
    StrategyCategory.HIGH:   {"min_agree": 1, "min_conf": 0.60, "persistence": 1, "warmup_seconds": 15},
}


class Orchestrator:
    """Process-wide singleton coordinating windows + shared singletons."""

    def __init__(self) -> None:
        self.s = get_settings()
        self.strategy = StrategyManager()
        self.risk = RiskManager()
        self.ai = AIConfirmation()
        self.fees = FeeCalculator()
        self.exits = ExitManager()
        self.positions = PositionTracker()       # shared across windows, keyed by (wid, token)
        self.notifier = Notifier()
        self.executor: Optional[ExecutionEngine] = None
        self.wallet: Optional[Wallet] = None
        self._initialized = False

    # ---- lazy init of executor/wallet on first start ----

    def _ensure_initialized(self, paper_mode: bool) -> None:
        if self._initialized:
            return
        self.executor = ExecutionEngine(paper_mode=paper_mode)
        self.wallet = Wallet(
            paper_mode=paper_mode,
            starting_capital_usd=self.s.starting_paper_capital_usd,
            positions=self.positions,
            w3c=self.executor.w3c if self.executor else None,
            dex=self.executor.dex if self.executor else None,
        )
        self._initialized = True

    # ---- window lifecycle ----

    async def start_window(self, config: BotConfig, max_deploy_usd: float) -> str:
        self._ensure_initialized(config.paper_mode)
        w = window_manager.create(
            tokens=config.tokens,
            duration_seconds=config.duration_seconds,
            strategy_category=config.strategy_category,
            auto_switch=config.auto_switch,
            paper_mode=config.paper_mode,
            max_deploy_usd=max_deploy_usd,
        )
        # mirror status on legacy bot_state for backward-compat UI
        async with state_lock:
            bot_state.status = BotStatus.RUNNING
            bot_state.started_at = datetime.utcnow()
            bot_state.duration_seconds = config.duration_seconds
            bot_state.config = config
            bot_state.last_error = None

        w.task = asyncio.create_task(self._run_window(w))
        await self.notifier.send(
            f"Window {w.id} started — duration={config.duration_seconds}s "
            f"deploy<=${max_deploy_usd:.0f} mode={'paper' if config.paper_mode else 'LIVE'}",
            level="info",
        )
        await self._broadcast()
        return w.id

    async def stop_window(self, window_id: str, close_positions: bool = True, reason: str = "user") -> None:
        w = window_manager.get(window_id)
        if w is None:
            return
        if close_positions:
            await self._close_window_positions(w, reason=reason)
        w.stop_event.set()
        if w.task:
            try:
                await asyncio.wait_for(w.task, timeout=10)
            except asyncio.TimeoutError:
                w.task.cancel()
        if w.status == "running":
            w.status = "stopped"
        await self._broadcast()

    async def kill_window(self, window_id: str) -> None:
        w = window_manager.get(window_id)
        if w is None:
            return
        w.kill_switch = True
        logger.warning(f"window {window_id} KILL — closing positions")
        await self._close_window_positions(w, reason=f"kill_window:{window_id}")
        w.status = "killed"
        w.stop_event.set()
        await self._broadcast()

    async def extend_window(self, window_id: str, additional_seconds: int) -> Optional[TradingWindow]:
        w = window_manager.get(window_id)
        if w is None or w.status != "running":
            return None
        w.extend(additional_seconds)
        logger.info(f"window {window_id} extended by {additional_seconds}s")
        await self._broadcast()
        return w

    async def terminate_all(self) -> None:
        """Stops every window AND closes every position. The 'big red button'."""
        logger.warning("TERMINATE ALL invoked")
        # Snapshot first — windows mutate as we iterate.
        for w in list(window_manager.all()):
            if w.status == "running":
                await self.stop_window(w.id, close_positions=True, reason="terminate_all")
        # Belt-and-suspenders: also close any orphaned positions.
        orphans = [p for p in self.positions.all_open()]
        for p in orphans:
            await self._close_position(p, price=p.avg_entry_price, reason="terminate_all_orphan")
        async with state_lock:
            bot_state.status = BotStatus.STOPPED
        await self._broadcast()

    # ---- per-window loop ----

    async def _run_window(self, w: TradingWindow) -> None:
        try:
            while datetime.utcnow() < w.deadline_at and not w.stop_event.is_set():
                if w.kill_switch:
                    break
                try:
                    await self._tick_window(w)
                except Exception as e:
                    logger.exception(f"window {w.id} tick error: {e}")
                try:
                    await asyncio.wait_for(w.stop_event.wait(), timeout=5)
                    break
                except asyncio.TimeoutError:
                    pass

            if not w.stop_event.is_set() and not w.kill_switch:
                # Natural end — close out for clean PnL
                logger.info(f"window {w.id} deadline reached — closing positions")
                await self._close_window_positions(w, reason="duration_ended")
                w.status = "completed"
        except Exception as e:
            logger.exception(f"window {w.id} crashed: {e}")
            w.status = "error"
        finally:
            if w.status == "running":
                w.status = "stopped"
            await self._broadcast()

    async def _tick_window(self, w: TradingWindow) -> None:
        if self.executor is None or self.wallet is None:
            return
        if not w.tokens:
            return

        for token_addr in w.tokens:
            symbol = _binance_symbol(token_addr)
            if symbol is None:
                continue

            candles_by_tf = await self._fetch_candles(symbol)
            primary = candles_by_tf.get("15m")
            if primary is None or primary.empty or len(primary) < 50:
                continue

            current_price = float(primary["close"].iloc[-1])
            self.positions.update_mark(token_addr, current_price)

            position = self.positions.get(token_addr, window_id=w.id)

            # ============================================================
            # CASE A: position already open in this window
            #   1. Hard exit (stop/target/trailing/time/reverse) → close
            #   2. Scale-out at +2R → sell half, ratchet stop on remainder
            #   3. Pyramid add at +0.5R → buy another 50% of target
            # ============================================================
            if position is not None:
                position.high_water_mark = max(position.high_water_mark, current_price)

                reverse = self._has_reverse_signal(symbol, token_addr, candles_by_tf, position)
                decision = self.exits.check(position, current_price, reverse_signal=reverse)
                if decision.new_stop_loss is not None and decision.new_stop_loss > position.stop_loss:
                    logger.info(f"window {w.id} ratchet stop {position.stop_loss:.4f} -> {decision.new_stop_loss:.4f}")
                    position.stop_loss = decision.new_stop_loss
                if decision.should_exit:
                    await self._close_position(position, current_price, reason=decision.reason, window=w)
                    continue

                # R-multiple of unrealized PnL (only meaningful when ATR stop set)
                unreal_r = (
                    (current_price - position.avg_entry_price) / position.initial_risk
                    if position.initial_risk > 0 else 0.0
                )

                # 2. Scale-out 50% at +2R (lock half the profit, free-ride the rest).
                if position.scale_outs_done == 0 and unreal_r >= 2.0:
                    await self._scale_out(position, current_price, fraction=0.5, window=w)
                    continue

                # 3. Pyramid add: at +0.5R AND target not yet filled.
                #    With initial=50% of target, one add of 50% brings us to 100%.
                if (
                    position.pyramid_step == 0
                    and unreal_r >= 0.5
                    and position.target_usd > 0
                    and position.cost_basis_usd < position.target_usd * 0.95
                ):
                    await self._pyramid_add(
                        w=w, position=position, token_addr=token_addr,
                        symbol=symbol, current_price=current_price,
                        candles_by_tf=candles_by_tf,
                    )
                continue

            # ============================================================
            # CASE B: no position — multi-stage opportunity analysis
            #
            #   1. WARMUP — first N seconds, refuse to trade (visible patience)
            #   2. ANALYZE — run ALL eligible strategies, count agreement
            #   3. SCORE — require multi-strategy agreement + min confidence
            #   4. PERSIST — require setup to hold for N consecutive ticks
            #   5. AI CONFIRM — open-source models cast a veto vote
            #   6. RISK + ENTER
            #
            # At every stage we set window.phase + reasoning so the UI can show
            # what the bot is thinking instead of looking blind.
            # ============================================================
            if not self._can_enter(w, token_addr):
                # Could be cooldown, daily-trade cap, etc. _can_enter is silent.
                continue

            quality = _QUALITY[w.strategy_category]
            elapsed = (datetime.utcnow() - w.started_at).total_seconds()

            # 1. WARMUP gate
            if elapsed < quality["warmup_seconds"]:
                remaining = int(quality["warmup_seconds"] - elapsed)
                w.set_phase("warmup",
                    f"Observing market for {remaining}s before first trade "
                    f"({w.strategy_category.value} risk: {quality['warmup_seconds']}s warmup)")
                continue

            wallet_state = self.wallet.state()
            cap = min(w.max_deploy_usd - w.deployed_usd, wallet_state.available_capital_usd)
            if cap < self.s.min_capital_threshold_usd:
                w.set_phase("waiting",
                    f"Insufficient capital (${cap:.2f} < ${self.s.min_capital_threshold_usd})")
                continue

            # 2. ANALYZE: run ALL eligible strategies in this regime
            fired = self.strategy.evaluate_all(
                symbol=symbol,
                token_in=self.s.usdt_address, token_out=token_addr,
                candles_by_tf=candles_by_tf,
                capital_usd=cap,
                category=w.strategy_category if not w.auto_switch else None,
            )
            buy_sigs = [(s, n, r) for s, n, r in fired if s.side == Side.BUY]

            # 3. SCORE: agreement + confidence threshold
            min_agree = int(quality["min_agree"])
            min_conf = float(quality["min_conf"])
            if len(buy_sigs) < min_agree:
                w.set_phase("analyzing",
                    f"Watching {symbol} — only {len(buy_sigs)}/{min_agree} strategies "
                    f"signal BUY ({w.strategy_category.value} risk requires {min_agree})")
                w.pending_signals.pop(token_addr.lower(), None)
                continue

            avg_conf = sum(s.confidence for s, _, _ in buy_sigs) / len(buy_sigs)
            if avg_conf < min_conf:
                names = ", ".join(n for _, n, _ in buy_sigs[:3])
                w.set_phase("analyzing",
                    f"{len(buy_sigs)} strategies firing ({names}) but "
                    f"avg confidence {avg_conf:.2f} < {min_conf:.2f} required")
                w.pending_signals.pop(token_addr.lower(), None)
                continue

            # Pick the highest-confidence signal as the canonical one
            signal, strat_name, regime = buy_sigs[0]

            # 4. PERSISTENCE: setup must hold for N consecutive ticks
            persistence_required = int(quality["persistence"])
            ok, count = self._signal_persisted(w, token_addr, signal, required=persistence_required)
            if not ok:
                names = ", ".join(n for _, n, _ in buy_sigs[:3])
                w.set_phase("pending",
                    f"Setup detected ({names}, conf {avg_conf:.2f}) — "
                    f"confirming {count}/{persistence_required} ticks…")
                continue

            # 5. AI veto
            approved_ai, conf, ai_reason = self.ai.confirm(signal, primary)
            if not approved_ai:
                w.set_phase("analyzing", f"AI rejected setup: {ai_reason}")
                w.pending_signals.pop(token_addr.lower(), None)
                continue
            signal.confidence = conf

            # 6. ENTER
            bot_state.active_strategy = signal.strategy
            w.set_phase("entering",
                f"Setup confirmed: {len(buy_sigs)} strategies agree "
                f"(avg conf {avg_conf:.2f}) — opening 50% position")

            await self._try_enter(
                w=w, signal=signal, regime=regime, token_addr=token_addr,
                current_price=current_price, available_cap=cap,
                candles_by_tf=candles_by_tf,
            )
            w.pending_signals.pop(token_addr.lower(), None)

        # Final phase update: if any open positions, report "holding"
        open_count = len(self.positions.by_window(w.id))
        if open_count > 0 and not w.phase.startswith(("entering", "warmup", "killed")):
            w.set_phase("holding",
                f"Managing {open_count} open position{'s' if open_count > 1 else ''}")

        await self._broadcast()

    # ---- signal persistence ----

    def _signal_persisted(
        self, w: TradingWindow, token: str, signal: Signal, required: int,
    ) -> tuple[bool, int]:
        """Require the same signal to fire on N consecutive ticks before acting.

        Returns (ok, current_count). Resets to 1 if the firing strategy changes.
        """
        key = token.lower()
        state = w.pending_signals.get(key)
        if state is None or state.get("strategy") != signal.strategy:
            w.pending_signals[key] = {
                "strategy": signal.strategy,
                "first_seen": time.time(),
                "count": 1,
            }
            return (1 >= required, 1)
        new_count = int(state.get("count", 0)) + 1
        state["count"] = new_count
        return (new_count >= required, new_count)

    # ---- pre-entry gating ----

    def _can_enter(self, w: TradingWindow, token_addr: str) -> bool:
        if self.positions.has_open(token_addr, window_id=w.id):
            return False
        if len(self.positions.by_window(w.id)) >= self.s.max_open_positions:
            return False
        last = w.last_fill_ts.get(token_addr.lower(), 0.0)
        if time.time() - last < self.s.min_seconds_between_trades:
            return False
        if w.deployed_usd >= w.max_deploy_usd:
            return False
        # Trade-rate cap is global, not per-window (anti-DOS)
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = sum(1 for ts in bot_state.trades_this_hour if ts >= cutoff)
        if recent >= self.s.max_trades_per_hour:
            return False
        return True

    def _has_reverse_signal(
        self, symbol: str, token_addr: str,
        candles_by_tf: Dict[str, pd.DataFrame], position: Position,
    ) -> bool:
        try:
            sig_pair = self.strategy.evaluate(
                symbol=symbol,
                token_in=token_addr, token_out=self.s.usdt_address,
                candles_by_tf=candles_by_tf,
                capital_usd=position.cost_basis_usd,
                category=None,
            )
            if sig_pair is None:
                return False
            sig, _ = sig_pair
            return sig.side == Side.SELL and sig.confidence >= self.s.min_signal_confidence
        except Exception:
            return False

    # ---- entry execution (with vol-targeted sizing) ----

    async def _try_enter(
        self, *, w: TradingWindow, signal: Signal, regime: str, token_addr: str,
        current_price: float, available_cap: float,
        candles_by_tf: Dict[str, pd.DataFrame],
    ) -> None:
        """Initial entry — opens at 50% of the Kelly-lite target.

        The remaining 50% is added later by `_pyramid_add` once the trade is
        confirmed working (price up +0.5R). This averages cost when wrong and
        compounds size when right.
        """
        if self.executor is None or self.wallet is None:
            return

        # ATR-based stop if the signal supplied one; else fall back to %-based
        meta = signal.metadata or {}
        stop_loss = float(meta.get("stop_loss", 0.0))
        take_profit = float(meta.get("take_profit", 0.0))
        atr_val = float(meta.get("atr", 0.0))

        # --- Vol-targeted sizing (Kelly-lite) — the FULL intended position ---
        equity = self.wallet.state().available_capital_usd + sum(
            p.mark_value_usd(current_price) for p in self.positions.by_window(w.id)
        )
        full_target_usd = self._size_position(
            signal=signal,
            equity_usd=equity,
            available_cap=available_cap,
            entry_price=current_price,
            stop_loss=stop_loss,
        )
        if full_target_usd < self.s.min_capital_threshold_usd:
            return

        # --- Initial entry = 50% of target. Pyramid add will bring it to 100%. ---
        size_usd = full_target_usd * 0.5
        # ...but never below the fee floor (otherwise the initial leg has bad EV).
        if size_usd < self.s.min_capital_threshold_usd:
            size_usd = min(full_target_usd, available_cap)

        # Gas / fee estimate — calibrated for real BSC swap costs:
        # PancakeSwap V2 swap uses ~150k gas, BSC base fee is typically 3 gwei.
        # That's ~$0.27 at BNB=$600 — closer to the on-chain truth than 200k×5gwei.
        gas_gwei = 3.0 if w.paper_mode else (
            self.executor.w3c.gas_price_gwei() if self.executor.w3c else 3.0
        )
        bnb_usd = 600.0
        if not w.paper_mode and self.executor.dex:
            bnb_usd = self.executor.dex.quote_price(
                self.s.wbnb_address, self.s.usdt_address, 0.01
            ) or 600.0

        costs = self.fees.estimate(
            trade_size_usd=size_usd, gas_units=150_000,
            gas_price_gwei=gas_gwei, bnb_usd=bnb_usd,
            slippage_pct=self.s.paper_mode_slippage_pct if w.paper_mode else self.s.max_slippage_pct,
        )
        hard_fee = costs.gas_usd + costs.lp_fee_usd

        # Expected profit estimate — what we make if the TP is hit.
        # The 0.8 discount accounts for entry/exit slippage and the chance we
        # close at a ratcheted-stop ABOVE entry (rather than the full TP).
        if take_profit > 0 and current_price > 0:
            expected_profit = size_usd * ((take_profit - current_price) / current_price) * 0.85
        else:
            expected_profit = size_usd * (self.s.take_profit_pct / 100.0) * 0.8

        liquidity = float("inf")
        if not w.paper_mode and self.executor.dex:
            liquidity = self.executor.dex.pool_reserves_usd(
                token_addr, self.s.usdt_address, 1.0
            ) or 0.0

        decision = self.risk.check_signal(
            signal=signal,
            wallet_capital_usd=equity,
            gas_price_gwei=gas_gwei,
            pool_liquidity_usd=liquidity,
            expected_profit_usd=expected_profit,
            expected_fee_usd=hard_fee,
        )
        if not decision.approved:
            self.fees.record_skip()
            await bus.publish({"type": "signal_rejected", "data": {
                "window_id": w.id, "strategy": signal.strategy, "reason": decision.reason,
            }})
            return

        amount_in_usd = min(size_usd, decision.sized_amount_usd)
        amount_in_wei = int(amount_in_usd * 10**18)
        token_units_expected = amount_in_usd / current_price if current_price > 0 else 0.0
        min_out = token_units_expected * (1.0 - decision.slippage_pct / 100.0)

        intent = TradeIntent(
            side=Side.BUY,
            token_in=self.s.usdt_address,
            token_out=token_addr,
            amount_in_wei=amount_in_wei,
            min_amount_out_wei=int(min_out * 10**18),
            slippage_pct=(self.s.paper_mode_slippage_pct if w.paper_mode else decision.slippage_pct),
            expected_price=current_price,
            strategy=signal.strategy,
            gas_price_gwei=gas_gwei,
        )
        result = await self.executor.execute(intent)

        if result.status == OrderStatus.CONFIRMED and result.amount_out:
            self.positions.apply_buy(
                token=token_addr,
                units=result.amount_out,
                fill_price=result.price or current_price,
                strategy=signal.strategy,
                stop_loss=stop_loss,
                take_profit=take_profit,
                window_id=w.id,
                target_usd=full_target_usd,         # full intended size for pyramid
            )
            if w.paper_mode:
                self.wallet.paper_apply_buy(amount_in_usd)
            w.last_fill_ts[token_addr.lower()] = time.time()
            w.deployed_usd += amount_in_usd
            w.trade_count += 1

        bot_state.record_trade(result, notional_usd=amount_in_usd, reason=signal.reason)
        self.fees.record(costs, signal.strategy)

        await self.notifier.send(
            f"[{w.id}] {signal.strategy} BUY ${amount_in_usd:.2f} @ ${current_price:.4f}"
            + (f" SL=${stop_loss:.4f} TP=${take_profit:.4f}" if stop_loss > 0 else ""),
            level="trade",
        )
        await bus.publish({"type": "trade", "data": {
            "window_id": w.id,
            "result": _ser(result),
            "signal": {"strategy": signal.strategy, "reason": signal.reason, "regime": regime},
            "fees": asdict(costs),
            "notional_usd": amount_in_usd,
            "stop_loss": stop_loss, "take_profit": take_profit,
        }})

    def _size_position(
        self, *, signal: Signal, equity_usd: float, available_cap: float,
        entry_price: float, stop_loss: float,
    ) -> float:
        """Vol-targeted sizing: risk a fixed % of equity per trade.

        size_usd = (equity × risk_pct) / (stop_distance / entry_price)
        Clipped to max_per_trade, max_concentration, and available cash.

        Floor: enforce a minimum size that dilutes fixed gas + LP fee to under
        a fraction of the expected TP move. Otherwise tiny trades just feed
        the fee meter without any realistic chance of net profit.
        """
        # Base risk-adjusted size
        if stop_loss > 0 and entry_price > stop_loss:
            stop_dist_pct = (entry_price - stop_loss) / entry_price
            risk_usd = equity_usd * (self.s.risk_per_trade_pct / 100.0)
            base = risk_usd / stop_dist_pct
        else:
            base = signal.suggested_amount_usd

        # Floor: ensure 2 × hard_fee < expected TP move.
        # With gas ≈ $0.27 and 0.25% LP fee, a $100 trade gives ~$0.52 fee.
        # A 2% TP on that = $2 → ~26% drag. A $50 trade is ~50% drag → marginal.
        # So set the floor at $100 by default for major BSC pairs.
        fee_floor = 100.0

        # Cap by config + confidence taper
        conf_factor = max(0.5, min(1.0, signal.confidence))
        size = min(
            max(base * conf_factor, fee_floor),
            self.s.max_capital_per_trade_usd,
            equity_usd * (self.s.max_concentration_pct / 100.0),
            available_cap,
        )
        return max(0.0, size)

    # ---- closing positions ----

    async def _close_position(
        self, position: Position, price: float, reason: str,
        window: Optional[TradingWindow] = None,
    ) -> None:
        if self.executor is None or self.wallet is None:
            return
        units = position.units
        if units <= 0:
            return

        slip = self.s.paper_mode_slippage_pct if (window and window.paper_mode) else self.s.max_slippage_pct
        intent = TradeIntent(
            side=Side.SELL,
            token_in=position.token,
            token_out=self.s.usdt_address,
            amount_in_wei=int(units * 10**18),
            min_amount_out_wei=int(units * price * (1.0 - slip / 100.0) * 10**18),
            slippage_pct=slip,
            expected_price=price,
            strategy=position.strategy or "exit",
            gas_price_gwei=5.0,
        )
        result = await self.executor.execute(intent)
        proceeds = result.amount_out or 0.0

        # Snapshot cost basis BEFORE apply_sell zeros it out on a full close.
        cost_basis_to_release = position.cost_basis_usd

        realized, _ = self.positions.apply_sell(
            position.token, units, result.price or price,
            window_id=position.window_id,
        )
        result.pnl_usd = realized

        if window:
            window.realized_pnl_usd += realized
            window.deployed_usd = max(0.0, window.deployed_usd - cost_basis_to_release)
            window.trade_count += 1

        if self.wallet.paper_mode and proceeds > 0:
            self.wallet.paper_apply_sell(proceeds)
        self.wallet.update_pnl(realized_delta=realized)

        # ONLINE LEARNING — strategies that lose get auto-disabled
        strategy_perf.record_close(position.strategy or "unknown", realized)

        bot_state.record_trade(result, notional_usd=proceeds, reason=reason)
        if window:
            window.last_fill_ts[position.token.lower()] = time.time()

        await self.notifier.send(
            f"CLOSE {position.strategy} @ ${price:.4f} pnl=${realized:+.2f} ({reason})",
            level="trade",
        )
        await bus.publish({"type": "trade", "data": {
            "window_id": window.id if window else None,
            "result": _ser(result),
            "signal": {"strategy": position.strategy, "reason": reason, "regime": "exit"},
            "fees": {
                "gas_usd": result.gas_cost_usd or 0.0,
                "lp_fee_usd": result.lp_fee_usd or 0.0,
                "slippage_usd": 0.0,
                "total_usd": (result.gas_cost_usd or 0.0) + (result.lp_fee_usd or 0.0),
            },
            "notional_usd": proceeds,
            "exit_reason": reason,
        }})

    async def _pyramid_add(
        self, *, w: TradingWindow, position: Position, token_addr: str,
        symbol: str, current_price: float, candles_by_tf: Dict[str, pd.DataFrame],
    ) -> None:
        """Build up a winning position: add the remaining ~50% of target_usd
        once the trade has moved +0.5R in our favor.

        Re-evaluates the strategy to make sure the setup is still valid; if the
        strategy isn't firing anymore we don't add.
        """
        if self.executor is None or self.wallet is None:
            return

        # Verify strategy still supports the trade
        sig_pair = self.strategy.evaluate(
            symbol=symbol,
            token_in=self.s.usdt_address, token_out=token_addr,
            candles_by_tf=candles_by_tf,
            capital_usd=position.target_usd,
            category=w.strategy_category if not w.auto_switch else None,
        )
        if sig_pair is None:
            return
        signal, _ = sig_pair
        if signal.side != Side.BUY or signal.confidence < self.s.min_signal_confidence:
            return

        # Size the add — gap between current cost basis and target.
        add_usd = position.target_usd - position.cost_basis_usd
        remaining_cap = w.max_deploy_usd - w.deployed_usd
        wallet_cash = self.wallet.state().available_capital_usd
        add_usd = min(add_usd, remaining_cap, wallet_cash)
        if add_usd < self.s.min_capital_threshold_usd:
            return

        slip = self.s.paper_mode_slippage_pct if w.paper_mode else self.s.max_slippage_pct
        amount_in_wei = int(add_usd * 10**18)
        units_expected = add_usd / current_price if current_price > 0 else 0.0

        intent = TradeIntent(
            side=Side.BUY,
            token_in=self.s.usdt_address,
            token_out=token_addr,
            amount_in_wei=amount_in_wei,
            min_amount_out_wei=int(units_expected * (1.0 - slip / 100.0) * 10**18),
            slippage_pct=slip,
            expected_price=current_price,
            strategy=signal.strategy,
            gas_price_gwei=3.0,
        )
        result = await self.executor.execute(intent)

        if result.status != OrderStatus.CONFIRMED or not result.amount_out:
            logger.warning(f"window {w.id} pyramid add failed: {result.error}")
            return

        self.positions.apply_buy(
            token=token_addr, units=result.amount_out,
            fill_price=result.price or current_price,
            strategy=signal.strategy,
            window_id=w.id,
            is_pyramid=True,
        )
        if w.paper_mode:
            self.wallet.paper_apply_buy(add_usd)
        w.deployed_usd += add_usd
        w.trade_count += 1

        reason = f"pyramid_add_{position.pyramid_step}"
        bot_state.record_trade(result, notional_usd=add_usd, reason=reason)
        await self.notifier.send(
            f"[{w.id}] ADD #{position.pyramid_step} ${add_usd:.2f} @ ${current_price:.4f}",
            level="trade",
        )
        await bus.publish({"type": "trade", "data": {
            "window_id": w.id,
            "result": _ser(result),
            "signal": {"strategy": signal.strategy, "reason": reason, "regime": "pyramid"},
            "fees": {"gas_usd": 0.0, "lp_fee_usd": result.lp_fee_usd or 0.0,
                     "slippage_usd": 0.0, "total_usd": result.lp_fee_usd or 0.0},
            "notional_usd": add_usd,
        }})

    async def _scale_out(
        self, position: Position, current_price: float,
        fraction: float, window: TradingWindow,
    ) -> None:
        """Take partial profits — sell `fraction` of the position, ratchet stop
        to entry+0.5R on the remainder so the rest of the trade is risk-free.
        """
        if self.executor is None or self.wallet is None:
            return
        units_to_sell = max(0.0, position.units * fraction)
        if units_to_sell <= 0:
            return

        slip = self.s.paper_mode_slippage_pct if window.paper_mode else self.s.max_slippage_pct
        cost_basis_to_release = position.cost_basis_usd * fraction

        intent = TradeIntent(
            side=Side.SELL,
            token_in=position.token,
            token_out=self.s.usdt_address,
            amount_in_wei=int(units_to_sell * 10**18),
            min_amount_out_wei=int(units_to_sell * current_price * (1.0 - slip / 100.0) * 10**18),
            slippage_pct=slip,
            expected_price=current_price,
            strategy=position.strategy or "scale_out",
            gas_price_gwei=3.0,
        )
        result = await self.executor.execute(intent)
        proceeds = result.amount_out or 0.0

        realized, _ = self.positions.apply_sell(
            position.token, units_to_sell, result.price or current_price,
            window_id=position.window_id,
        )
        result.pnl_usd = realized
        position.scale_outs_done += 1

        # Lock 0.5R profit on the remainder: ratchet stop to entry + 0.5R.
        if position.initial_risk > 0:
            new_stop = position.avg_entry_price + 0.5 * position.initial_risk
            if new_stop > position.stop_loss:
                position.stop_loss = new_stop

        window.realized_pnl_usd += realized
        window.deployed_usd = max(0.0, window.deployed_usd - cost_basis_to_release)
        window.trade_count += 1
        if window.paper_mode and proceeds > 0:
            self.wallet.paper_apply_sell(proceeds)
        self.wallet.update_pnl(realized_delta=realized)

        strategy_perf.record_close(position.strategy or "unknown", realized)

        reason = f"scale_out_{int(fraction*100)}pct"
        bot_state.record_trade(result, notional_usd=proceeds, reason=reason)
        await self.notifier.send(
            f"[{window.id}] SCALE-OUT {int(fraction*100)}% @ ${current_price:.4f} "
            f"pnl=${realized:+.2f} stop->${position.stop_loss:.4f}",
            level="trade",
        )
        await bus.publish({"type": "trade", "data": {
            "window_id": window.id,
            "result": _ser(result),
            "signal": {"strategy": position.strategy, "reason": reason, "regime": "scale_out"},
            "fees": {"gas_usd": result.gas_cost_usd or 0.0,
                     "lp_fee_usd": result.lp_fee_usd or 0.0,
                     "slippage_usd": 0.0,
                     "total_usd": (result.gas_cost_usd or 0.0) + (result.lp_fee_usd or 0.0)},
            "notional_usd": proceeds,
            "exit_reason": reason,
        }})

    async def close_position_manual(self, window_id: str, token: str) -> bool:
        """User-triggered close of one specific position in one specific window.

        Returns True if a position was closed, False if not found.
        """
        w = window_manager.get(window_id)
        if w is None:
            return False
        position = self.positions.get(token, window_id=window_id)
        if position is None:
            return False
        symbol = _binance_symbol(position.token)
        price = position.avg_entry_price
        if symbol:
            try:
                candles = await market_data.fetch_ohlcv(symbol, "1m", limit=1)
                if candles:
                    price = candles[-1].close
            except Exception:
                pass
        await self._close_position(position, price, reason="manual_exit", window=w)
        return True

    async def _close_window_positions(self, w: TradingWindow, reason: str) -> None:
        for p in list(self.positions.by_window(w.id)):
            symbol = _binance_symbol(p.token)
            price = p.avg_entry_price
            if symbol:
                try:
                    candles = await market_data.fetch_ohlcv(symbol, "1m", limit=1)
                    if candles:
                        price = candles[-1].close
                except Exception:
                    pass
            await self._close_position(p, price, reason=reason, window=w)

    # ---- broadcasting ----

    async def _broadcast(self) -> None:
        if self.wallet is None:
            await bus.publish({"type": "status", "data": bot_state.to_dict()})
            return
        marks: Dict[str, float] = {}
        for p in self.positions.all_open():
            symbol = _binance_symbol(p.token)
            if not symbol:
                continue
            try:
                c = await market_data.fetch_ohlcv(symbol, "1m", limit=1)
                if c:
                    marks[p.token.lower()] = c[-1].close
            except Exception:
                pass
        wallet_state = self.wallet.state(marks=marks)
        positions_payload = [
            p.to_dict(mark_price=marks.get(p.token.lower(), p.avg_entry_price))
            for p in self.positions.all_open()
        ]
        windows_payload = [
            asdict(w.summary(open_positions=len(self.positions.by_window(w.id))))
            for w in window_manager.all()
        ]
        await bus.publish({"type": "status", "data": bot_state.to_dict()})
        await bus.publish({"type": "wallet", "data": _ser(wallet_state)})
        await bus.publish({"type": "positions", "data": positions_payload})
        await bus.publish({"type": "windows", "data": windows_payload})

    async def _fetch_candles(self, symbol: str) -> Dict[str, pd.DataFrame]:
        tfs = ["1m", "5m", "15m", "1h", "4h"]
        raw = await market_data.fetch_multi_tf(symbol, tfs, limit=200)
        return {tf: candles_to_df(c) for tf, c in raw.items()}

    # ---- legacy compat helpers (used by old kill endpoint) ----

    @property
    def is_running(self) -> bool:
        return any(w.status == "running" for w in window_manager.all())


def _ser(obj) -> dict:
    if hasattr(obj, "__dict__"):
        out = {}
        for k, v in obj.__dict__.items():
            if hasattr(v, "value"):       # enum
                out[k] = v.value
            else:
                out[k] = v
        return out
    return dict(obj)


# Process-wide singleton
orchestrator = Orchestrator()
