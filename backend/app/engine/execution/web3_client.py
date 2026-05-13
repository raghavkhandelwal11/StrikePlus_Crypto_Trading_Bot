"""Web3 client wrapper. Owns a single Web3 instance with fallback RPC.

The wallet private key is loaded *once* via security.load_private_key and
held in memory. We never log it. The eth-account `LocalAccount` derived
from it is used only to sign transactions — it has no withdraw permission
beyond that, since BSC is account-based and any tx must be signed by this key.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from app.core.config import Settings, get_settings
from app.core.security import load_private_key


class Web3Client:
    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or get_settings()
        self.w3 = self._connect()
        self.account = None
        self.address: Optional[str] = None
        self._init_account()

    def _connect(self) -> Web3:
        for url in (self.s.bsc_rpc_url, self.s.bsc_rpc_fallback):
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 15}))
                # BSC uses POA — extraData would otherwise overflow the standard middleware.
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                if w3.is_connected():
                    logger.info(f"web3 connected to {url}")
                    return w3
            except Exception as e:
                logger.warning(f"web3 connect failed for {url}: {e}")
        raise RuntimeError("Failed to connect to BSC RPC (primary and fallback both unreachable)")

    def _init_account(self) -> None:
        pk = load_private_key(self.s.wallet_encrypted_key, self.s.wallet_encryption_password)
        if pk is None:
            logger.warning("no wallet configured — execution engine will run in paper mode only")
            return
        self.account = self.w3.eth.account.from_key(pk)
        self.address = self.account.address
        if self.s.wallet_address and self.s.wallet_address.lower() != self.address.lower():
            raise RuntimeError(
                "WALLET_ADDRESS does not match the address derived from the encrypted key"
            )
        logger.info(f"wallet loaded: {self.address}")

    def gas_price_gwei(self) -> float:
        try:
            return float(self.w3.from_wei(self.w3.eth.gas_price, "gwei"))
        except Exception as e:
            logger.warning(f"gas_price fetch failed: {e}")
            return float("inf")

    def bnb_balance(self) -> float:
        if not self.address:
            return 0.0
        wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(wei, "ether"))


_singleton: Optional[Web3Client] = None


def get_web3_client() -> Web3Client:
    global _singleton
    if _singleton is None:
        _singleton = Web3Client()
    return _singleton
