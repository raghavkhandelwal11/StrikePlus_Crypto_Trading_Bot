# Crypto Trading Bot — BSC / PancakeSwap

A modular, decentralized crypto trading bot operating on **Binance Smart Chain** via **PancakeSwap V2**, with a Python (FastAPI) backend, a React/Next.js dashboard, an open-source AI confirmation layer, real-time WebSocket updates, and full risk controls. Ships with paper-trading mode by default.

> ⚠️ **Read this first.** This software trades real money on a public blockchain. The code is structured for safety and extensibility but you, the operator, are responsible for auditing it before depositing live funds. Start in `paper` mode, then on **BSC testnet**, then with a small live float you can afford to lose. Never share or commit your private key.

---

## Flow Diagram

```
[User UI]
   ↓
[Select Strategy + Duration]
   ↓
[Risk Manager Validation]
   ↓
[Market Data Fetcher]
   ↓
[AI + Strategy Engine]
   ↓
[Decision Engine]
   ↓
[Execution Engine]
   ↓
[PancakeSwap Smart Contract]
   ↓
[Trade Executed]
   ↓
[Update Wallet + PnL + Logs]
   ↓
[Loop until duration ends or stop triggered]
```

## Architecture

```
Frontend (React / Next.js)
        ↓ REST + WebSocket
Backend API (FastAPI)
        ↓
Trading Engine (Python)
   ├── Strategy Manager       (high / medium / low risk + auto-switch by regime)
   ├── Risk Manager           (limits, kill switch, circuit breaker, blacklist)
   ├── AI Confirmation        (Random Forest + LSTM as gate)
   ├── Execution Engine       (web3.py, PancakeSwap V2, retry, MEV buffer)
   ├── Fee Calculator         (gas + LP + slippage; skip if unprofitable)
   ├── Data Layer             (OHLCV + indicators + multi-TF)
   ├── Wallet                 (live balances, paper sim, PnL)
   ├── Backtest Engine        (Sharpe, max DD, win rate)
   ├── Alerts                 (Telegram + Discord, optional)
   └── Logging                (rotated app log + JSONL trade log)
        ↓
Blockchain (BSC / PancakeSwap)
```

## Project layout

```
crypto_trading_bot/
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI routers + WebSocket
│   │   ├── core/                   # config, types, logger, security, state, event bus
│   │   └── engine/
│   │       ├── strategies/         # 8 strategies + manager
│   │       ├── risk/               # risk manager
│   │       ├── execution/          # web3 + PancakeSwap + executor
│   │       ├── ai/                 # RF + LSTM + confirmation
│   │       ├── data/               # market data + indicators
│   │       ├── wallet/             # live + paper wallet
│   │       ├── backtest/           # backtester + metrics
│   │       ├── fees/               # cost calculator
│   │       └── alerts/             # Telegram/Discord
│   ├── scripts/                    # encrypt_key, train_ai
│   ├── tests/                      # pytest unit tests
│   ├── data/                       # logs, model artifacts (mounted in Docker)
│   └── requirements.txt
├── frontend/
│   ├── app/                        # Next.js app router
│   ├── components/                 # Chart, Controls, Status, Logs, Trades
│   ├── lib/                        # api client + WebSocket hook
│   └── package.json
├── docker/                         # Dockerfiles
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone & configure

```bash
git clone <repo-url> crypto_trading_bot
cd crypto_trading_bot
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Edit `.env` — at minimum set `TRADING_MODE=paper` to start safely.

### 2. Encrypt your wallet private key (only required for live mode)

```bash
cd backend
python scripts/encrypt_key.py
```

The script prompts for the key + a password, never echoes them, and prints a `WALLET_ENCRYPTED_KEY` value to paste into `.env`.

The plaintext key is decrypted in memory only when the bot starts. The key file lives encrypted at rest.

### 3. Run with Docker (recommended)

```bash
docker compose up --build
```

- Backend: <http://localhost:8000> (Swagger docs at `/docs`)
- Frontend: <http://localhost:3000>

### 4. Run locally (no Docker)

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### 5. (Optional) Train the AI confirmation models

```bash
cd backend
python scripts/train_ai.py --symbol BNBUSDT --interval 1h --limit 1000
```

This trains a Random Forest classifier and saves it to `backend/data/models/rf.pkl`. The bot loads it automatically on next start.

> The LSTM stub requires PyTorch (`pip install torch`). Without it, the LSTM no-ops; the bot still runs with the Random Forest alone, or with no AI gate at all (`AI_ENABLED=false`).

---

## Environment variables

See [.env.example](./.env.example) for the full list. The high-impact ones:

| Var | Default | Purpose |
| --- | --- | --- |
| `TRADING_MODE` | `paper` | `paper` (simulated) or `live` (real on-chain). Default-safe. |
| `BSC_RPC_URL` | binance public | RPC endpoint. Use a paid provider for mainnet stability. |
| `WALLET_ENCRYPTED_KEY` | _empty_ | Output of `scripts/encrypt_key.py`. |
| `WALLET_ENCRYPTION_PASSWORD` | _empty_ | The password chosen during encryption. |
| `MAX_CAPITAL_PER_TRADE_USD` | `50` | Per-trade cap. |
| `MAX_DAILY_LOSS_PCT` | `5.0` | Auto kill-switch threshold. |
| `CIRCUIT_BREAKER_LOSSES` | `3` | Halt after N consecutive losses. |
| `MAX_GAS_PRICE_GWEI` | `10` | Skip trades during gas spikes. |
| `MIN_LIQUIDITY_USD` | `50000` | Pool TVL gate. |
| `MAX_SLIPPAGE_PCT` | `1.0` | Slippage cap; doubles as MEV buffer. |
| `AI_ENABLED` | `true` | Toggle AI confirmation gate. |
| `BLACKLIST_TOKENS` | _empty_ | Comma-separated BEP20 addresses to never trade. |

---

## Strategies

The bot runs a **strategy manager** that picks among 8 strategies based on the detected market regime (`trend_up`, `trend_down`, `range`, `high_vol`) and a user-selected risk category. You can also lock to a single category by toggling off auto-switch in the UI.

| Risk | Strategy | When it fires |
| --- | --- | --- |
| **High** | `breakout` | Donchian channel breakout with ≥1.5× volume + 1h-trend agreement. |
| **High** | `momentum_scalp` | Strong 3-bar 1m move with non-overbought RSI and 5m trend agreement. |
| **Medium** | `ema_rsi` | EMA12/EMA26 cross + RSI 50–70 + 1h trend filter. |
| **Medium** | `vwap` | Pullback to VWAP within an EMA50 uptrend. |
| **Medium** | `mean_reversion` | Bollinger band touch + RSI oversold/overbought. |
| **Low** | `grid` | Even-spaced grid below recent mid-price. |
| **Low** | `stable_swing` | Low-vol RSI swing on stable-correlated pairs. |
| **Low** | `arbitrage` | Cross-DEX spread (scaffold; flash-loan execution to be wired in). |

**Multi-timeframe confirmation:** every strategy that is trend-sensitive checks the next-higher timeframe before firing.

**Volatility filtering:** the regime detector classifies any series with ATR/price > 2% as `high_vol` and routes only the high-risk strategies there.

---

## Risk controls (all enforced in `engine/risk/manager.py`)

- ✅ Max capital per trade
- ✅ Min capital threshold
- ✅ Max trades per hour (rolling window)
- ✅ Max slippage (cap on `amountOutMin` calculation)
- ✅ Fee cap — trade rejected if `gas + LP + slippage ≥ expected_profit − buffer`
- ✅ Max daily loss (auto-engages kill switch)
- ✅ Circuit breaker after N consecutive losses
- ✅ Manual + auto kill switch (UI button + auto on daily loss)
- ✅ Gas spike guard (`MAX_GAS_PRICE_GWEI`)
- ✅ Liquidity validation (pool TVL via factory `getPair` + reserves)
- ✅ Token blacklist (env-configurable)

---

## Execution engine

- Uses the **PancakeSwap V2 router** via `web3.py`, `swapExactTokensForTokens`.
- **Pre-trade simulation** of slippage by comparing `getAmountsOut` at requested size vs. a 0.001-unit reference.
- **Retry with exponential backoff** for transient RPC errors (`tenacity`).
- **MEV buffer** baked into `amountOutMin` via `MAX_SLIPPAGE_PCT`.
- **Tx receipt timeout** so the bot doesn't hang on a stalled mempool.
- **Auto-approval** of router for ERC20 tokens (idempotent — checks allowance first).
- **Partial-execution handling** through the executor's `OrderStatus.PARTIAL` path; extend with reserves-based fill modeling in the live executor for richer cases.

---

## AI confirmation

Two open-source models confirm a strategy signal before it reaches the risk gate:

- **Random Forest (sklearn)** — classifies the next-N-bar direction as `up / flat / down`. Always available.
- **LSTM (PyTorch)** — same prediction, sequence-aware. Optional (`pip install torch`).

**Decision rule:**
- ≥1 model agrees with the signal direction at confidence ≥ `AI_CONFIDENCE_THRESHOLD` → **boost** confidence by +0.15 and approve.
- All available models disagree at high confidence → **reject**.
- Otherwise → **pass through** (AI never blocks unprompted).

**Important:** The shipped models start untrained. Run `scripts/train_ai.py` on your target asset/timeframe. In-sample accuracy is **not** predictive performance — validate with walk-forward backtests in the dashboard.

---

## Backtesting & paper trading

- **Paper mode** is the default `TRADING_MODE`. Simulated balances start at $1,000; trades fill against the live router quote with configured slippage.
- **Backtester** at `POST /backtest` replays Binance historical OHLCV through the same strategy manager. Returns:
  - Sharpe ratio
  - Max drawdown
  - Win rate
  - Profit factor
  - Avg win / avg loss
  - Equity curve + trade log

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe |
| `GET` | `/bot/status` | Current bot state |
| `POST` | `/bot/start` | Start a run |
| `POST` | `/bot/stop` | Graceful stop |
| `POST` | `/bot/kill` | Engage kill switch |
| `POST` | `/bot/release-kill` | Release kill switch |
| `GET` | `/bot/strategies` | List strategies |
| `GET` | `/bot/trades` | Recent trade history |
| `GET` | `/wallet` | Wallet state (balances + PnL) |
| `GET` | `/market/ohlcv` | OHLCV proxy |
| `POST` | `/backtest` | Run a backtest |
| `WS`  | `/ws` | Live event stream (status / trades / signals) |

Auto-generated docs at <http://localhost:8000/docs>.

---

## Security

- Private keys are encrypted with **Fernet (AES-128-CBC + HMAC)** + a PBKDF2-derived key. Decrypted only in memory at startup.
- Plaintext keys are never logged.
- The wallet address derived from the key is checked against the configured `WALLET_ADDRESS` to prevent silent mistakes.
- API rate-limited via `slowapi` (`RATE_LIMIT_PER_MINUTE`).
- `.env` is in `.gitignore`. Re-check before any `git push`.
- The bot only ever calls **swap functions** on PancakeSwap; it has no logic to send raw BNB/tokens to arbitrary recipients.

---

## Deployment

- Configurable RPC endpoint + fallback (`BSC_RPC_URL`, `BSC_RPC_FALLBACK`).
- Stateless backend except for `backend/data/` (mount as a volume).
- Single-process `uvicorn`. Behind a real reverse proxy (Caddy / nginx), turn off the wildcard CORS in `app/main.py`.
- For multi-chain: the `ExecutionEngine` and `PancakeSwap` modules already isolate chain-specific code — add an EVM router class for Ethereum/Polygon next to `pancakeswap.py` and gate by chain id.

---

## Tests

```bash
cd backend
pytest
```

Includes unit tests for the risk manager (each limit) and indicator pipeline.

---

## Honest scope notes

The system is structured for production but a few items are intentionally minimal so you can shape them to your stack:

- **AI models ship untrained.** Train them on your data before relying on the gate.
- **Symbol map.** OHLCV is fetched from Binance for major pairs. For obscure tokens, plug in a DEX subgraph (Bitquery / The Graph) inside `engine/data/market_data.py`.
- **Arbitrage strategy** is a documented scaffold — atomic cross-DEX execution typically needs a flash-loan contract, which is out of scope for this drop.
- **Database.** Logs use a JSONL trade log + rotated app log. A SQLite/Postgres trade history is wired via `DATABASE_URL` but not used by the orchestrator yet.
- **Live mode requires testing.** The `live` path is implemented, but you should run extensively on **BSC testnet** (chain id 97) before flipping the switch.

---

## License

MIT — use at your own risk. Trading bots can lose money. Read the code.
# StrikePlus_Crypto_Trading_Bot
