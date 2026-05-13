"""Market data routes — OHLCV + 24h tickers + supported-pairs list."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.engine.data.market_data import market_data

router = APIRouter(prefix="/market", tags=["market"])


# Curated list of pairs supported on BSC via PancakeSwap V2 (paired against USDT).
# `token` is the BSC address used by the executor; `symbol` is the Binance OHLCV proxy.
SUPPORTED_PAIRS: List[Dict[str, str]] = [
    {"symbol": "BNBUSDT",   "token": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "label": "BNB/USDT"},
    {"symbol": "ETHUSDT",   "token": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "label": "ETH/USDT (peg)"},
    {"symbol": "BTCUSDT",   "token": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "label": "BTC/USDT (peg)"},
    {"symbol": "BUSDUSDT",  "token": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "label": "BUSD/USDT"},
    {"symbol": "MATICUSDT", "token": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD", "label": "MATIC/USDT (peg)"},
]

# Headline pairs shown in the top ticker bar.
HEADLINE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


@router.get("/ohlcv")
async def ohlcv(
    symbol: str = Query("BNBUSDT"),
    interval: str = Query("15m"),
    # Allow limit=1 so the chart can request just the latest candle for fast ticks.
    limit: int = Query(200, ge=1, le=1000),
) -> List[dict]:
    try:
        candles = await market_data.fetch_ohlcv(symbol, interval, limit)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return [c.__dict__ for c in candles]


@router.get("/pairs")
async def list_pairs() -> Dict[str, Any]:
    """Supported pairs + their 24h ticker — used to populate UI selectors."""
    symbols = [p["symbol"] for p in SUPPORTED_PAIRS]
    tickers = await market_data.fetch_24h_tickers(symbols)
    by_symbol = {t["symbol"]: t for t in tickers}
    enriched = []
    for p in SUPPORTED_PAIRS:
        t = by_symbol.get(p["symbol"], {})
        enriched.append({**p, **t})
    return {"pairs": enriched, "count": len(enriched)}


@router.get("/headline")
async def headline_tickers() -> Dict[str, Any]:
    """Headline pairs (BTC/ETH/BNB) for the top dashboard ticker."""
    tickers = await market_data.fetch_24h_tickers(HEADLINE_SYMBOLS)
    return {"tickers": tickers}
