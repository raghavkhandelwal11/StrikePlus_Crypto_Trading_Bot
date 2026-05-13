"""CLI: train the Random Forest (and optionally LSTM) on Binance OHLCV.

Usage:
  python backend/scripts/train_ai.py --symbol BNBUSDT --interval 1h --limit 1000

The trained models go to backend/data/models/{rf.pkl, lstm.pt} and are
loaded automatically by the AI confirmation layer on next bot start.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.ai.random_forest import RandomForestTrend  # noqa: E402
from app.engine.data.market_data import candles_to_df, market_data  # noqa: E402


async def fetch(symbol: str, interval: str, limit: int):
    candles = await market_data.fetch_ohlcv(symbol, interval, limit=limit)
    await market_data.close()
    return candles_to_df(candles)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BNBUSDT")
    p.add_argument("--interval", default="1h")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--threshold", type=float, default=0.002)
    args = p.parse_args()

    df = asyncio.run(fetch(args.symbol, args.interval, args.limit))
    if df.empty or len(df) < 200:
        sys.exit(f"not enough candles: {len(df)}")

    rf = RandomForestTrend()
    stats = rf.train(df, horizon=args.horizon, threshold=args.threshold)
    print(f"RF trained: {stats}")
    print("(IMPORTANT) In-sample accuracy is NOT predictive performance.")
    print("Validate with a walk-forward test before relying on the model in production.")


if __name__ == "__main__":
    main()
