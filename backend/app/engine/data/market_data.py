"""Market data fetcher.

Sources (in priority order, all free):
  1. Binance public REST/WS for OHLCV (used as a faithful proxy for major pairs).
     This is fine for technical analysis even when executing on PancakeSwap, since
     prices on the major BSC pairs track CEX within slippage.
  2. PancakeSwap on-chain quote (router.getAmountsOut) for live execution price.

For obscure tokens not listed on Binance, plug in a DEX subgraph here.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
import pandas as pd
from loguru import logger

from app.core.types import Candle

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"

_TF_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d",
}


@dataclass(frozen=True)
class _CacheKey:
    symbol: str
    interval: str
    limit: int


class MarketData:
    """Async OHLCV fetcher with a small in-memory TTL cache.

    TTL was 20s originally — fine for strategy ticks but felt "dead" on the
    chart. Now 2s so the chart's fast-tick can pull fresh candles every poll
    without spamming Binance. Each cache hit still costs zero outbound calls.
    """

    def __init__(self, ttl_seconds: int = 2):
        self._ttl = ttl_seconds
        self._cache: Dict[_CacheKey, tuple[float, List[Candle]]] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 200,
    ) -> List[Candle]:
        """Fetch OHLCV from Binance. `symbol` is e.g. 'BNBUSDT'."""
        if interval not in _TF_MAP:
            raise ValueError(f"Unsupported interval: {interval}")
        key = _CacheKey(symbol.upper(), interval, limit)
        now = time.time()
        async with self._lock:
            cached = self._cache.get(key)
            if cached and (now - cached[0]) < self._ttl:
                return cached[1]

        client = await self._get_client()
        try:
            r = await client.get(
                BINANCE_KLINES,
                params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
            )
            r.raise_for_status()
            raw = r.json()
        except Exception as e:
            logger.error(f"market_data fetch failed for {symbol} {interval}: {e}")
            return []

        candles = [
            Candle(
                ts=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
        async with self._lock:
            self._cache[key] = (now, candles)
        return candles

    async def fetch_multi_tf(
        self, symbol: str, intervals: List[str], limit: int = 200
    ) -> Dict[str, List[Candle]]:
        """Fetch multiple timeframes in parallel — used for multi-TF confirmation."""
        results = await asyncio.gather(
            *(self.fetch_ohlcv(symbol, tf, limit) for tf in intervals),
            return_exceptions=True,
        )
        out: Dict[str, List[Candle]] = {}
        for tf, res in zip(intervals, results):
            if isinstance(res, Exception):
                logger.warning(f"failed to fetch {symbol} {tf}: {res}")
                out[tf] = []
            else:
                out[tf] = res
        return out

    async def fetch_24h_ticker(self, symbol: str) -> Optional[Dict[str, float]]:
        """Get 24h ticker stats (last price, % change, volume) from Binance."""
        client = await self._get_client()
        try:
            r = await client.get(BINANCE_TICKER_24H, params={"symbol": symbol.upper()})
            r.raise_for_status()
            d = r.json()
            return {
                "symbol": d["symbol"],
                "last_price": float(d["lastPrice"]),
                "price_change_pct": float(d["priceChangePercent"]),
                "high_24h": float(d["highPrice"]),
                "low_24h": float(d["lowPrice"]),
                "volume_24h": float(d["volume"]),
                "quote_volume_24h": float(d["quoteVolume"]),
            }
        except Exception as e:
            logger.warning(f"ticker fetch failed for {symbol}: {e}")
            return None

    async def fetch_24h_tickers(self, symbols: List[str]) -> List[Dict[str, float]]:
        """Fetch 24h stats for multiple symbols in parallel."""
        results = await asyncio.gather(
            *(self.fetch_24h_ticker(s) for s in symbols),
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, dict)]


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame([c.__dict__ for c in candles])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


# Singleton — share the connection pool across the app.
market_data = MarketData()
