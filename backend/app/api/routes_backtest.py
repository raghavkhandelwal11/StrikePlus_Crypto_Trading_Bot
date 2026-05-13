"""Backtest endpoint."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.api.schemas import BacktestRequest, BacktestResponse
from app.core.types import StrategyCategory
from app.engine.backtest import Backtester
from app.engine.data.market_data import market_data

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    candles = await market_data.fetch_ohlcv(req.symbol, req.interval, req.limit)
    if len(candles) < 100:
        raise HTTPException(400, f"insufficient candles: got {len(candles)}")
    bt = Backtester(
        starting_capital=req.starting_capital,
        fee_pct=req.fee_pct,
        slippage_pct=req.slippage_pct,
    )
    cat = StrategyCategory(req.category) if req.category else None
    result = bt.run(candles, symbol=req.symbol, category=cat)
    return BacktestResponse(
        metrics=asdict(result.metrics),
        final_equity=result.final_equity,
        trades=result.trades,
        equity_curve=result.equity_curve,
    )
