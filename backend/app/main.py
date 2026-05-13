"""FastAPI entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import routes_backtest, routes_bot, routes_market, routes_positions, routes_wallet, ws
from app.core.config import get_settings
from app.core.logger import setup_logging
from app.engine.data.market_data import market_data

setup_logging()
settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Cleanup on shutdown
    await market_data.close()


app = FastAPI(
    title="Crypto Trading Bot",
    version="0.1.0",
    description="Decentralized BSC/PancakeSwap trading bot — paper + live modes.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # tighten in prod
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0", "mode": settings.trading_mode}


app.include_router(routes_bot.router)
app.include_router(routes_wallet.router)
app.include_router(routes_positions.router)
app.include_router(routes_market.router)
app.include_router(routes_backtest.router)
app.include_router(ws.router)
