"""Wallet view: native BNB + cash balance + delegated position tracking.

In **paper** mode, the wallet keeps:
  - a USDT cash balance (USD)
  - realized PnL accumulator
  Position units live in the `PositionTracker`.

In **live** mode, balances are read from the chain via Web3Client; the
position tracker is the source of truth for cost basis & PnL (which the
chain doesn't record).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger

from app.core.config import get_settings
from app.core.types import WalletState
from app.engine.execution.pancakeswap import PancakeSwap
from app.engine.execution.web3_client import Web3Client
from app.engine.positions import PositionTracker


class Wallet:
    def __init__(
        self,
        paper_mode: bool = True,
        starting_capital_usd: float = 1000.0,
        positions: Optional[PositionTracker] = None,
        w3c: Optional[Web3Client] = None,
        dex: Optional[PancakeSwap] = None,
    ):
        self.s = get_settings()
        self.paper_mode = paper_mode
        self.starting_capital_usd = starting_capital_usd
        self.positions = positions or PositionTracker()
        self.realized_pnl_usd = 0.0
        self.w3c = w3c
        self.dex = dex

        # Paper-mode cash (USDT). Positions live in the PositionTracker.
        self._paper_cash_usdt: float = starting_capital_usd

    # ---- paper accounting ----

    def paper_cash(self) -> float:
        return self._paper_cash_usdt

    def paper_apply_buy(self, notional_usd: float) -> None:
        """Subtract spent cash from paper wallet."""
        self._paper_cash_usdt = max(0.0, self._paper_cash_usdt - notional_usd)

    def paper_apply_sell(self, notional_usd: float) -> None:
        """Add proceeds to paper wallet."""
        self._paper_cash_usdt += notional_usd

    def update_pnl(self, realized_delta: float = 0.0) -> None:
        self.realized_pnl_usd += realized_delta

    # ---- state snapshots ----

    def _mark_prices(self, default: float = 0.0) -> Dict[str, float]:
        """Best-effort mid-price for each held token. Live mode hits the router."""
        marks: Dict[str, float] = {}
        if not self.dex:
            return marks
        for p in self.positions.all_open():
            try:
                px = self.dex.quote_price(p.token, self.s.usdt_address, 0.01)
                if px:
                    marks[p.token.lower()] = px
            except Exception:
                pass
        return marks

    def _paper_state(self, marks: Optional[Dict[str, float]] = None) -> WalletState:
        marks = marks or {}
        token_balances: Dict[str, float] = {}
        deployed = 0.0
        unreal = 0.0
        for p in self.positions.all_open():
            token_balances[p.token] = p.units
            mark = marks.get(p.token.lower(), p.avg_entry_price)   # fall back to entry
            deployed += p.mark_value_usd(mark)
            unreal += p.unrealized_pnl_usd(mark)
        return WalletState(
            address="paper-wallet",
            bnb_balance=0.0,
            token_balances=token_balances,
            deployed_capital_usd=deployed,
            available_capital_usd=self._paper_cash_usdt,
            realized_pnl_usd=self.realized_pnl_usd,
            unrealized_pnl_usd=unreal,
        )

    def _live_state(self) -> WalletState:
        if self.w3c is None or self.w3c.address is None or self.dex is None:
            return WalletState(
                address="", bnb_balance=0.0, token_balances={},
                deployed_capital_usd=0.0, available_capital_usd=0.0,
                realized_pnl_usd=self.realized_pnl_usd, unrealized_pnl_usd=0.0,
            )
        bnb = self.w3c.bnb_balance()
        balances: Dict[str, float] = {}
        watch: List[str] = list(set(self.s.trade_tokens + [self.s.usdt_address, self.s.busd_address]))
        bnb_usd = self._bnb_usd()
        available = bnb * bnb_usd
        deployed = 0.0
        unreal = 0.0
        marks = self._mark_prices()

        for token in watch:
            try:
                d = self.dex.decimals(token)
                bal = self.dex.balance_of(token, self.w3c.address) / 10**d
                balances[token] = bal
                if token.lower() in (self.s.usdt_address.lower(), self.s.busd_address.lower()):
                    available += bal
            except Exception as e:
                logger.warning(f"wallet read failed for {token}: {e}")

        # Use position tracker for deployed value & unrealized PnL — the chain
        # doesn't tell us cost basis.
        for p in self.positions.all_open():
            mark = marks.get(p.token.lower(), p.avg_entry_price)
            deployed += p.mark_value_usd(mark)
            unreal += p.unrealized_pnl_usd(mark)

        return WalletState(
            address=self.w3c.address,
            bnb_balance=bnb,
            token_balances=balances,
            deployed_capital_usd=deployed,
            available_capital_usd=available,
            realized_pnl_usd=self.realized_pnl_usd,
            unrealized_pnl_usd=unreal,
        )

    def _bnb_usd(self) -> float:
        if self.dex is None:
            return 0.0
        try:
            return self.dex.quote_price(self.s.wbnb_address, self.s.usdt_address, 0.01) or 0.0
        except Exception:
            return 0.0

    def state(self, marks: Optional[Dict[str, float]] = None) -> WalletState:
        return self._paper_state(marks) if self.paper_mode else self._live_state()
