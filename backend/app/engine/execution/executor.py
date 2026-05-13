"""Execution engine. Orchestrates: pre-trade checks → swap build → submit → confirm.

Modes:
  - paper: no on-chain calls; just simulate using the router quote
  - live: real swap

Safety features built in:
  - Slippage simulation before sending
  - Retry with exponential backoff on transient RPC errors
  - Tx receipt timeout
  - MEV-resistant min-out (slippage buffer)
  - Per-tx nonce management with fallback fetch
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from web3 import Web3

from app.core.config import get_settings
from app.core.logger import log_trade
from app.core.types import OrderStatus, Side, TradeIntent, TradeResult
from app.engine.execution.pancakeswap import PancakeSwap
from app.engine.execution.web3_client import Web3Client, get_web3_client


class TransientRPCError(Exception):
    """Wrapper to mark RPC errors as retryable."""


class ExecutionEngine:
    def __init__(self, paper_mode: bool = True):
        self.s = get_settings()
        self.paper_mode = paper_mode
        self.w3c: Optional[Web3Client] = None
        self.dex: Optional[PancakeSwap] = None
        if not paper_mode:
            self.w3c = get_web3_client()
            self.dex = PancakeSwap(self.w3c)

    # ---- Paper trading: simulate fill against the live quote ----

    async def execute_paper(self, intent: TradeIntent) -> TradeResult:
        """Simulate a fill using the intent's expected price + half-slippage.

        For a BUY (USDT -> token):
            amount_in  is in USDT (the quote)
            fill_price is token-USDT price, slightly worse than mid by half-slippage
            amount_out is token units = amount_in / fill_price

        For a SELL (token -> USDT):
            amount_in  is in token units
            fill_price is token-USDT price, slightly worse than mid by half-slippage
            amount_out is USDT = amount_in * fill_price
        """
        await asyncio.sleep(0)   # yield
        mid = intent.expected_price or 1.0
        half_slip = intent.slippage_pct / 100.0 / 2.0
        amount_in_human = intent.amount_in_wei / 1e18

        if intent.side == Side.BUY:
            fill_price = mid * (1.0 + half_slip)            # we pay slightly more
            amount_out = amount_in_human / fill_price if fill_price > 0 else 0.0
            notional_usd = amount_in_human
        else:  # SELL
            fill_price = mid * (1.0 - half_slip)            # we receive slightly less
            amount_out = amount_in_human * fill_price
            notional_usd = amount_out

        result = TradeResult(
            status=OrderStatus.CONFIRMED,
            tx_hash="paper-" + str(int(time.time() * 1000)),
            side=intent.side,
            token_in=intent.token_in,
            token_out=intent.token_out,
            amount_in=amount_in_human,
            amount_out=amount_out,
            price=fill_price,
            gas_cost_usd=0.0,                               # paper mode = no gas
            lp_fee_usd=notional_usd * self.s.pancake_lp_fee_pct / 100.0,
            slippage_pct=intent.slippage_pct,
            strategy=intent.strategy,
        )
        log_trade({"mode": "paper", **result.__dict__})
        return result

    # ---- Live trading ----

    async def execute_live(self, intent: TradeIntent) -> TradeResult:
        if self.dex is None or self.w3c is None or self.w3c.account is None:
            return TradeResult(status=OrderStatus.REJECTED, error="no_wallet_or_dex")

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._do_live_trade, intent)
        except Exception as e:
            logger.exception(f"live execution failed: {e}")
            return TradeResult(status=OrderStatus.FAILED, error=str(e), strategy=intent.strategy)

    @retry(
        retry=retry_if_exception_type(TransientRPCError),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _do_live_trade(self, intent: TradeIntent) -> TradeResult:
        assert self.dex is not None and self.w3c is not None and self.w3c.account is not None
        owner = self.w3c.address
        gas_price_wei = self.dex.w3.to_wei(intent.gas_price_gwei, "gwei")

        # 1. Approve router if needed (skip for native BNB; we use WBNB-as-token here for simplicity)
        try:
            self.dex.ensure_approval(
                token=intent.token_in,
                owner=owner,
                spender=self.s.pancakeswap_router,
                amount=intent.amount_in_wei,
                gas_price_wei=gas_price_wei,
            )
        except Exception as e:
            raise TransientRPCError(f"approve failed: {e}") from e

        # 2. Build swap tx
        deadline = int(time.time()) + intent.deadline_seconds
        nonce = self.dex.w3.eth.get_transaction_count(Web3.to_checksum_address(owner))
        tx = self.dex.build_swap_tx(
            amount_in=intent.amount_in_wei,
            amount_out_min=intent.min_amount_out_wei,
            path=[intent.token_in, intent.token_out],
            recipient=owner,
            deadline=deadline,
            gas_price_wei=gas_price_wei,
            nonce=nonce,
        )

        # 3. Sign + send
        signed = self.w3c.account.sign_transaction(tx)
        try:
            tx_hash = self.dex.w3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception as e:
            raise TransientRPCError(f"send_raw_transaction failed: {e}") from e

        # 4. Wait for receipt with timeout
        try:
            receipt = self.dex.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except Exception as e:
            return TradeResult(
                status=OrderStatus.FAILED,
                tx_hash=tx_hash.hex(),
                error=f"timeout_or_rpc_error: {e}",
                strategy=intent.strategy,
            )

        if receipt.status != 1:
            return TradeResult(
                status=OrderStatus.FAILED,
                tx_hash=tx_hash.hex(),
                error="tx_reverted",
                strategy=intent.strategy,
            )

        gas_used = receipt.gasUsed
        gas_cost_bnb = float(self.dex.w3.from_wei(gas_used * gas_price_wei, "ether"))
        d_in = self.dex.decimals(intent.token_in)

        result = TradeResult(
            status=OrderStatus.CONFIRMED,
            tx_hash=tx_hash.hex(),
            side=intent.side,
            token_in=intent.token_in,
            token_out=intent.token_out,
            amount_in=intent.amount_in_wei / 10**d_in,
            amount_out=None,            # parse Transfer logs in a richer impl
            price=intent.expected_price,
            gas_cost_usd=gas_cost_bnb * self._bnb_usd_estimate(),
            slippage_pct=intent.slippage_pct,
            strategy=intent.strategy,
        )
        log_trade({"mode": "live", **result.__dict__})
        return result

    def _bnb_usd_estimate(self) -> float:
        """Best-effort BNB price for converting gas cost to USD. Quote BNB->USDT on the same router."""
        if self.dex is None:
            return 0.0
        try:
            p = self.dex.quote_price(self.s.wbnb_address, self.s.usdt_address, 0.01)
            return p or 0.0
        except Exception:
            return 0.0

    # ---- Public entry point ----

    async def execute(self, intent: TradeIntent) -> TradeResult:
        if self.paper_mode:
            return await self.execute_paper(intent)
        return await self.execute_live(intent)
