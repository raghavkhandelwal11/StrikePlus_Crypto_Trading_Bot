"""PancakeSwap V2 router interactions: quotes, liquidity, swap construction."""
from __future__ import annotations

from typing import List, Optional, Tuple

from loguru import logger
from web3 import Web3
from web3.exceptions import ContractLogicError

from app.core.config import get_settings
from app.engine.execution.abi import (
    ERC20_ABI,
    FACTORY_V2_ABI,
    PAIR_V2_ABI,
    ROUTER_V2_ABI,
)
from app.engine.execution.web3_client import Web3Client


class PancakeSwap:
    def __init__(self, w3c: Web3Client):
        self.s = get_settings()
        self.w3c = w3c
        self.w3 = w3c.w3
        self.router = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.s.pancakeswap_router),
            abi=ROUTER_V2_ABI,
        )
        self.factory = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.s.pancakeswap_factory),
            abi=FACTORY_V2_ABI,
        )

    # ---- Token helpers ----

    def erc20(self, address: str):
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=ERC20_ABI
        )

    def decimals(self, token: str) -> int:
        return int(self.erc20(token).functions.decimals().call())

    def balance_of(self, token: str, owner: str) -> int:
        return int(self.erc20(token).functions.balanceOf(Web3.to_checksum_address(owner)).call())

    # ---- Quotes ----

    def get_amounts_out(self, amount_in: int, path: List[str]) -> List[int]:
        cs_path = [Web3.to_checksum_address(a) for a in path]
        try:
            out = self.router.functions.getAmountsOut(amount_in, cs_path).call()
            return [int(x) for x in out]
        except ContractLogicError as e:
            logger.warning(f"getAmountsOut reverted (likely no path): {e}")
            return []

    def quote_price(
        self, token_in: str, token_out: str, amount_in_human: float
    ) -> Optional[float]:
        """Return units of token_out received per 1 unit of token_in (no slippage applied)."""
        try:
            d_in = self.decimals(token_in)
            d_out = self.decimals(token_out)
        except Exception as e:
            logger.warning(f"decimals fetch failed: {e}")
            return None
        amount_in = int(amount_in_human * 10**d_in)
        amounts = self.get_amounts_out(amount_in, [token_in, token_out])
        if not amounts or len(amounts) < 2:
            return None
        out_human = amounts[-1] / 10**d_out
        return out_human / amount_in_human if amount_in_human else None

    # ---- Liquidity ----

    def pool_reserves_usd(
        self, token_a: str, token_b: str, usd_price_of_b: float
    ) -> Optional[float]:
        """Estimate pool TVL in USD given the USD price of token_b (the quote token).

        Caller is expected to pass `usd_price_of_b` from a stable reference (e.g.
        a BNB/BUSD quote from the same router).
        """
        pair_addr = self.factory.functions.getPair(
            Web3.to_checksum_address(token_a), Web3.to_checksum_address(token_b)
        ).call()
        if int(pair_addr, 16) == 0:
            return None
        pair = self.w3.eth.contract(address=pair_addr, abi=PAIR_V2_ABI)
        r0, r1, _ = pair.functions.getReserves().call()
        t0 = pair.functions.token0().call()
        d_b = self.decimals(token_b)
        if t0.lower() == token_a.lower():
            reserve_b = r1 / 10**d_b
        else:
            reserve_b = r0 / 10**d_b
        return reserve_b * usd_price_of_b * 2.0     # rough TVL = 2 * reserveB in USD

    # ---- Slippage simulation ----

    def simulate_slippage(
        self, token_in: str, token_out: str, amount_in_human: float
    ) -> Optional[Tuple[float, float]]:
        """Compare price impact at the requested size vs. a reference 1-unit quote.

        Returns (executed_price, slippage_pct).
        """
        small = self.quote_price(token_in, token_out, amount_in_human=0.001)
        large = self.quote_price(token_in, token_out, amount_in_human=amount_in_human)
        if small is None or large is None or small == 0:
            return None
        slip_pct = (small - large) / small * 100.0
        return large, slip_pct

    # ---- Approval ----

    def ensure_approval(
        self, token: str, owner: str, spender: str, amount: int, gas_price_wei: int
    ) -> Optional[str]:
        """If allowance < amount, send an approve tx and return its hash; else None."""
        c = self.erc20(token)
        current = int(c.functions.allowance(
            Web3.to_checksum_address(owner), Web3.to_checksum_address(spender)
        ).call())
        if current >= amount:
            return None
        if not self.w3c.account:
            raise RuntimeError("no wallet account loaded")
        nonce = self.w3.eth.get_transaction_count(owner)
        tx = c.functions.approve(Web3.to_checksum_address(spender), 2**256 - 1).build_transaction({
            "from": Web3.to_checksum_address(owner),
            "nonce": nonce,
            "gas": 80_000,
            "gasPrice": gas_price_wei,
            "chainId": self.s.bsc_chain_id,
        })
        signed = self.w3c.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info(f"approve tx sent: {h.hex()}")
        return h.hex()

    # ---- Swap ----

    def build_swap_tx(
        self,
        amount_in: int,
        amount_out_min: int,
        path: List[str],
        recipient: str,
        deadline: int,
        gas_price_wei: int,
        nonce: int,
    ) -> dict:
        cs_path = [Web3.to_checksum_address(a) for a in path]
        tx = self.router.functions.swapExactTokensForTokens(
            amount_in, amount_out_min, cs_path,
            Web3.to_checksum_address(recipient), deadline,
        ).build_transaction({
            "from": Web3.to_checksum_address(recipient),
            "nonce": nonce,
            "gas": 250_000,
            "gasPrice": gas_price_wei,
            "chainId": self.s.bsc_chain_id,
        })
        return tx
