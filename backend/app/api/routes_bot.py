"""Bot + window control routes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.schemas import (
    DURATION_SECONDS,
    DurationKey,
    StatusResponse,
    StopBotRequest,
)
from app.core.config import get_settings
from app.core.state import bot_state
from app.core.types import BotConfig, StrategyCategory
from app.engine.orchestrator import orchestrator
from app.engine.performance import strategy_perf
from app.engine.window import window_manager

router = APIRouter(prefix="/bot", tags=["bot"])


class StartWindowRequest(BaseModel):
    duration: DurationKey
    strategy_category: str = "medium"
    auto_switch: bool = True
    tokens: List[str] = Field(default_factory=list)
    paper_mode: bool = True
    max_deploy_usd: float = Field(500.0, gt=0)


class ExtendWindowRequest(BaseModel):
    additional_seconds: int = Field(..., gt=0, le=7 * 24 * 3600)


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(**bot_state.to_dict())


@router.get("/windows")
async def list_windows() -> Dict[str, Any]:
    items = []
    for w in window_manager.all():
        open_count = len(orchestrator.positions.by_window(w.id))
        items.append(w.summary(open_positions=open_count).__dict__)
    return {"windows": items, "count": len(items)}


@router.post("/windows")
async def create_window(req: StartWindowRequest) -> Dict[str, Any]:
    s = get_settings()
    tokens = req.tokens or s.trade_tokens
    if not tokens:
        raise HTTPException(400, "no tokens configured (request body or TRADE_TOKEN_LIST env)")
    if not req.paper_mode and not s.is_live:
        raise HTTPException(400, "TRADING_MODE=paper in env; set to 'live' to enable real trading")
    try:
        cat = StrategyCategory(req.strategy_category)
    except ValueError:
        raise HTTPException(400, f"invalid strategy_category: {req.strategy_category}")
    config = BotConfig(
        duration_seconds=DURATION_SECONDS[req.duration],
        strategy_category=cat,
        auto_switch=req.auto_switch,
        tokens=tokens,
        paper_mode=req.paper_mode,
    )
    try:
        window_id = await orchestrator.start_window(config, max_deploy_usd=req.max_deploy_usd)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"window_id": window_id, "status": "running"}


@router.post("/windows/{window_id}/stop")
async def stop_window(window_id: str) -> Dict[str, Any]:
    if window_manager.get(window_id) is None:
        raise HTTPException(404, "window not found")
    await orchestrator.stop_window(window_id, close_positions=True, reason="user_stop")
    return {"window_id": window_id, "status": "stopped"}


@router.post("/windows/{window_id}/kill")
async def kill_window(window_id: str) -> Dict[str, Any]:
    if window_manager.get(window_id) is None:
        raise HTTPException(404, "window not found")
    await orchestrator.kill_window(window_id)
    return {"window_id": window_id, "status": "killed"}


@router.post("/windows/{window_id}/extend")
async def extend_window(window_id: str, req: ExtendWindowRequest) -> Dict[str, Any]:
    w = await orchestrator.extend_window(window_id, req.additional_seconds)
    if w is None:
        raise HTTPException(404, "window not found or not running")
    return {"window_id": window_id, "new_deadline": w.deadline_at.isoformat()}


@router.post("/windows/{window_id}/positions/{token}/close")
async def close_window_position(window_id: str, token: str) -> Dict[str, Any]:
    """Manually close a single open position in a specific window.

    `token` is the BSC token address held by the position. The bot computes
    realized PnL using the latest mark price, applies it to the window, and
    feeds the outcome into the strategy performance tracker (online learning).
    """
    ok = await orchestrator.close_position_manual(window_id, token)
    if not ok:
        raise HTTPException(404, "position not found for that window+token")
    return {"window_id": window_id, "token": token, "status": "closed"}


@router.post("/terminate-all")
async def terminate_all() -> Dict[str, Any]:
    """Stop EVERY window and close EVERY position. The 'big red button'."""
    await orchestrator.terminate_all()
    return {"status": "terminated_all"}


# ---- Legacy single-bot routes (kept for back-compat) ----

@router.post("/start", response_model=Dict[str, Any])
async def start_legacy(req: StartWindowRequest) -> Dict[str, Any]:
    return await create_window(req)


@router.post("/stop")
async def stop_legacy(req: StopBotRequest) -> Dict[str, Any]:
    await orchestrator.terminate_all()
    return {"status": "stopped_all"}


@router.post("/kill")
async def kill_legacy() -> Dict[str, Any]:
    await orchestrator.terminate_all()
    return {"status": "killed_all"}


@router.post("/release-kill")
async def release_kill() -> Dict[str, Any]:
    orchestrator.risk.release_kill_switch()
    return {"status": "kill_released"}


@router.get("/strategies")
async def strategies() -> Dict[str, Any]:
    return {
        "strategies": orchestrator.strategy.list_strategies(),
        "performance": strategy_perf.snapshot(),
    }


@router.get("/performance")
async def performance() -> Dict[str, Any]:
    return {"strategies": strategy_perf.snapshot()}


@router.post("/performance/reset")
async def reset_performance() -> Dict[str, Any]:
    strategy_perf.reset()
    return {"status": "reset"}


@router.get("/trades")
async def trades(limit: int = 100) -> Dict[str, Any]:
    items = bot_state.trade_history[-limit:]
    return {"count": len(bot_state.trade_history), "items": [t.__dict__ for t in items]}
