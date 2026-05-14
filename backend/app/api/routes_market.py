"""Market data routes — OHLCV + 24h tickers + supported-pairs list."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.engine.data.market_data import market_data

router = APIRouter(prefix="/market", tags=["market"])


# Curated list of pairs supported on BSC via PancakeSwap V2 (paired against USDT).
# `token` is the BSC address used by the executor; `symbol` is the Binance OHLCV proxy.
#
# Curation criteria — every pair must:
#   1. Have a deployed BEP20 contract with real PancakeSwap V2 liquidity
#   2. Be among the top ~30 by market cap (no micro-caps; no honeypots)
#   3. Have a matching Binance USDT spot pair so OHLCV streams just work
#
# Volatility profile, low → high (rough 15m ATR%):
#   BUSD/USDT (peg flat) · BTC · ETH · BNB · XRP · ADA · MATIC · SOL · CAKE · DOGE
SUPPORTED_PAIRS: List[Dict[str, str]] = [
    # Majors (lowest vol, safest)
    {"symbol": "BNBUSDT",   "token": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "label": "BNB/USDT"},
    {"symbol": "ETHUSDT",   "token": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "label": "ETH/USDT (peg)"},
    {"symbol": "BTCUSDT",   "token": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "label": "BTC/USDT (peg)"},
    {"symbol": "BUSDUSDT",  "token": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "label": "BUSD/USDT"},
    # Large caps (moderate vol)
    {"symbol": "SOLUSDT",   "token": "0x570A5D26f7765Ecb712C0924E4De545B89fD43dF", "label": "SOL/USDT (peg)"},
    {"symbol": "XRPUSDT",   "token": "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE", "label": "XRP/USDT (peg)"},
    {"symbol": "ADAUSDT",   "token": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", "label": "ADA/USDT (peg)"},
    {"symbol": "MATICUSDT", "token": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD", "label": "MATIC/USDT (peg)"},
    # Higher vol / DEX-native
    {"symbol": "CAKEUSDT",  "token": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "label": "CAKE/USDT (native)"},
    {"symbol": "DOGEUSDT",  "token": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43", "label": "DOGE/USDT (peg)"},
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
