"""Telegram + Discord notifier. All channels are optional and fail open."""
from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger

from app.core.config import get_settings


class Notifier:
    def __init__(self) -> None:
        s = get_settings()
        self.tg_token = s.telegram_bot_token
        self.tg_chat = s.telegram_chat_id
        self.discord_url = s.discord_webhook_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=8.0)
        return self._client

    async def send(self, message: str, level: str = "info") -> None:
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "❗", "trade": "💱"}.get(level, "")
        text = f"{prefix} {message}" if prefix else message
        await self._tg(text)
        await self._discord(text)

    async def _tg(self, text: str) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        try:
            client = await self._get_client()
            await client.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                json={"chat_id": self.tg_chat, "text": text},
            )
        except Exception as e:
            logger.warning(f"telegram send failed: {e}")

    async def _discord(self, text: str) -> None:
        if not self.discord_url:
            return
        try:
            client = await self._get_client()
            await client.post(self.discord_url, json={"content": text})
        except Exception as e:
            logger.warning(f"discord send failed: {e}")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
