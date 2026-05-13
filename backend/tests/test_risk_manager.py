"""Unit tests for the risk manager — guards against regressions on safety logic."""
from __future__ import annotations

from app.core.config import Settings
from app.core.state import bot_state
from app.core.types import Side, Signal
from app.engine.risk.manager import RiskManager


def _signal(amount: float = 50.0, conf: float = 0.7) -> Signal:
    return Signal(
        side=Side.BUY, confidence=conf, strategy="test", reason="r",
        token_in="0xa", token_out="0xb", suggested_amount_usd=amount,
    )


def _settings(**overrides) -> Settings:
    s = Settings(_env_file=None)   # ignore .env
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def setup_function(_):
    bot_state.kill_switch = False
    bot_state.daily_pnl_usd = 0.0
    bot_state.consecutive_losses = 0
    bot_state.trades_this_hour.clear()


def test_kill_switch_blocks():
    bot_state.kill_switch = True
    rm = RiskManager(_settings())
    d = rm.check_signal(_signal(), 1000, 1, 1_000_000, 1.0, 0.1)
    assert not d.approved and "kill_switch" in d.reason


def test_blacklist():
    rm = RiskManager(_settings(blacklist_tokens="0xb"))
    d = rm.check_signal(_signal(), 1000, 1, 1_000_000, 1.0, 0.1)
    assert not d.approved and "blacklist" in d.reason


def test_min_capital():
    rm = RiskManager(_settings(min_capital_threshold_usd=100))
    d = rm.check_signal(_signal(), 50, 1, 1_000_000, 1.0, 0.1)
    assert not d.approved and "below_min_capital" in d.reason


def test_gas_spike():
    rm = RiskManager(_settings(max_gas_price_gwei=5))
    d = rm.check_signal(_signal(), 1000, 100, 1_000_000, 1.0, 0.1)
    assert not d.approved and "gas_spike" in d.reason


def test_liquidity():
    rm = RiskManager(_settings(min_liquidity_usd=100_000))
    d = rm.check_signal(_signal(), 1000, 1, 50, 1.0, 0.1)
    assert not d.approved and "liquidity" in d.reason


def test_fee_cap():
    rm = RiskManager(_settings())
    # fee greater than profit → reject
    d = rm.check_signal(_signal(), 1000, 1, 1_000_000, expected_profit_usd=0.1, expected_fee_usd=1.0)
    assert not d.approved and "fees" in d.reason


def test_approve_sizes_correctly():
    rm = RiskManager(_settings(max_capital_per_trade_usd=20, min_capital_threshold_usd=5))
    d = rm.check_signal(_signal(amount=50, conf=1.0), 1000, 1, 1_000_000, 1.0, 0.05)
    assert d.approved
    assert d.sized_amount_usd <= 20.0
