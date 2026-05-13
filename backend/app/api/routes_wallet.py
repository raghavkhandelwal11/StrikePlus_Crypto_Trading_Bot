"""Wallet inspection routes."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import WalletResponse
from app.engine.orchestrator import orchestrator
from app.engine.wallet import Wallet

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletResponse)
async def get_wallet() -> WalletResponse:
    w = orchestrator.wallet or Wallet(paper_mode=True)
    s = w.state()
    return WalletResponse(**s.__dict__)
