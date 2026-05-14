"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Trading mode
    trading_mode: Literal["paper", "live"] = "paper"

    # BSC mainnet
    bsc_rpc_url: str = "https://bsc-dataseed1.binance.org"
    bsc_rpc_fallback: str = "https://bsc-dataseed2.binance.org"
    bsc_chain_id: int = 56

    # BSC testnet
    bsc_testnet_rpc_url: str = "https://data-seed-prebsc-1-s1.binance.org:8545"
    bsc_testnet_chain_id: int = 97

    # Wallet
    wallet_encrypted_key: Optional[str] = None
    wallet_encryption_password: Optional[str] = None
    wallet_address: Optional[str] = None

    # PancakeSwap
    pancakeswap_router: str = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    pancakeswap_factory: str = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    wbnb_address: str = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    busd_address: str = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
    usdt_address: str = "0x55d398326f99059fF775485246999027B3197955"

    # Trading config
    default_quote_token: str = "WBNB"
    trade_token_list: str = ""
    blacklist_tokens: str = ""

    # Risk limits
    max_capital_per_trade_usd: float = 200.0
    min_capital_threshold_usd: float = 10.0
    # Bumped from 6 → 12: pyramid adds + scale-outs each count as a trade,
    # so 6/hr really meant only ~1.5 NEW positions/hour. 12/hr gives ~3
    # full position lifecycles per hour while still capping fee burn.
    max_trades_per_hour: int = 12
    max_slippage_pct: float = 1.0
    max_daily_loss_pct: float = 5.0
    circuit_breaker_losses: int = 3
    max_gas_price_gwei: float = 10.0
    min_liquidity_usd: float = 50_000.0

    # Fees
    fee_buffer_pct: float = 0.5
    pancake_lp_fee_pct: float = 0.25

    # Exit / position management (fallback fixed-% — only used when a strategy
    # doesn't supply an ATR-based stop_loss/take_profit)
    take_profit_pct: float = 2.0                # close longs at +2%
    stop_loss_pct: float = 1.5                  # close longs at -1.5%
    trailing_stop_pct: float = 1.0              # drawdown from peak to trigger
    max_holding_minutes: int = 240              # auto-close stale positions (0 = disabled)
    min_signal_confidence: float = 0.60         # don't act on weak signals (bumped from 0.55)
    min_seconds_between_trades: int = 180       # per-token cooldown (3 min — was 600/10 min, too patient)
    max_open_positions: int = 3                 # cap concurrent positions
    starting_paper_capital_usd: float = 1000.0  # paper-mode wallet float

    # Smart sizing — risk-per-trade as a % of equity (Kelly-lite)
    risk_per_trade_pct: float = 1.0             # 1% of equity at risk per trade
    max_concentration_pct: float = 30.0         # no single position > 30% of cash

    # Paper-mode slippage — major BSC pairs see <0.3% on $50 trades typically.
    # The old default of MAX_SLIPPAGE_PCT (1.0%) made backtests pessimistic.
    paper_mode_slippage_pct: float = 0.3

    # Multi-window
    max_concurrent_windows: int = 3

    # AI
    ai_enabled: bool = True
    ai_confidence_threshold: float = 0.6
    lstm_model_path: str = "backend/data/models/lstm.pkl"
    rf_model_path: str = "backend/data/models/rf.pkl"

    # Alerts
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None

    # Database
    database_url: str = "sqlite:///./backend/data/bot.db"

    # Frontend / API
    next_public_api_url: str = "http://localhost:8000"
    next_public_ws_url: str = "ws://localhost:8000/ws"
    rate_limit_per_minute: int = 60

    # ---- Derived helpers ----

    @property
    def trade_tokens(self) -> List[str]:
        return [t.strip() for t in self.trade_token_list.split(",") if t.strip()]

    @property
    def blacklist(self) -> List[str]:
        return [t.strip().lower() for t in self.blacklist_tokens.split(",") if t.strip()]

    @property
    def is_live(self) -> bool:
        return self.trading_mode == "live"

    @field_validator("wallet_address")
    @classmethod
    def _normalize_addr(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith("0x"):
            raise ValueError("wallet_address must be a 0x-prefixed hex address")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()
