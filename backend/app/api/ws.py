"""WebSocket endpoint. Streams bot events (status, trades, signals) to the dashboard."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.event_bus import bus
from app.core.state import bot_state

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await bus.subscribe()
    # Send a snapshot on connect so the UI populates immediately.
    try:
        await websocket.send_text(json.dumps({"type": "status", "data": bot_state.to_dict()}))
        while True:
            try:
                event: Any = await asyncio.wait_for(queue.get(), timeout=20.0)
                await websocket.send_text(json.dumps(event, default=str))
            except asyncio.TimeoutError:
                # Heartbeat to keep proxies happy.
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"ws error: {e}")
    finally:
        await bus.unsubscribe(queue)
