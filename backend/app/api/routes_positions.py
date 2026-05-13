"""Open position inspection routes."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from app.engine.data.market_data import market_data
from app.engine.orchestrator import orchestrator, _binance_symbol  # type: ignore

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def list_positions() -> Dict[str, Any]:
    """Return the current open positions with live mark prices when available."""
    out: List[dict] = []
    for p in orchestrator.positions.all_open():
        mark = p.avg_entry_price
        symbol = _binance_symbol(p.token)
        if symbol:
            try:
                candles = await market_data.fetch_ohlcv(symbol, "1m", limit=1)
                if candles:
                    mark = candles[-1].close
            except Exception:
                pass
        out.append(p.to_dict(mark_price=mark))
    return {"positions": out, "count": len(out)}
