"""Structured logging setup. Uses loguru with JSON sinks for trade/error logs."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from app.core.config import get_settings

_LOG_DIR = Path("backend/data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_initialized = False


def setup_logging() -> None:
    """Configure loguru sinks. Idempotent."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()

    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        _LOG_DIR / "app.log",
        level=settings.log_level,
        rotation="20 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
    )
    logger.add(
        _LOG_DIR / "errors.log",
        level="ERROR",
        rotation="20 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )
    _initialized = True


def log_trade(record: Dict[str, Any]) -> None:
    """Append a structured trade record to the trade log (JSON lines)."""
    trade_log = _LOG_DIR / "trades.jsonl"
    with trade_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


# Always configure on import so submodules get a working logger.
setup_logging()
