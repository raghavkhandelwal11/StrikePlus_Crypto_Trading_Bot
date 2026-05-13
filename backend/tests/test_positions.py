"""Tests for PositionTracker — covers open, scale-in, partial close, full close."""
from __future__ import annotations

import pytest

from app.engine.positions import PositionTracker


def test_open_and_close():
    pt = PositionTracker()
    pt.apply_buy(token="0xABC", units=10, fill_price=100.0, strategy="ema_rsi")
    p = pt.get("0xabc")
    assert p is not None and p.units == 10
    assert p.avg_entry_price == 100.0
    assert p.cost_basis_usd == 1000.0

    realized, _ = pt.apply_sell(token="0xabc", units=10, fill_price=110.0)
    assert realized == pytest.approx(100.0)              # 10 * (110 - 100)
    assert pt.get("0xabc") is None                       # fully closed


def test_scale_in_updates_avg_entry():
    pt = PositionTracker()
    pt.apply_buy("0xABC", units=10, fill_price=100.0, strategy="x")
    pt.apply_buy("0xABC", units=10, fill_price=120.0, strategy="x")
    p = pt.get("0xABC")
    assert p.units == 20
    assert p.avg_entry_price == pytest.approx(110.0)
    assert p.cost_basis_usd == pytest.approx(2200.0)


def test_partial_close_preserves_basis():
    pt = PositionTracker()
    pt.apply_buy("0xABC", units=10, fill_price=100.0, strategy="x")
    realized, _ = pt.apply_sell("0xABC", units=4, fill_price=110.0)
    assert realized == pytest.approx(40.0)               # 4 * 10
    p = pt.get("0xABC")
    assert p.units == 6
    # Cost basis reduced proportionally; avg entry preserved.
    assert p.cost_basis_usd == pytest.approx(600.0)
    assert p.avg_entry_price == pytest.approx(100.0)


def test_unrealized_pnl():
    pt = PositionTracker()
    pt.apply_buy("0xABC", units=10, fill_price=100.0, strategy="x")
    p = pt.get("0xABC")
    assert p.unrealized_pnl_usd(110.0) == pytest.approx(100.0)
    assert p.unrealized_pnl_pct(110.0) == pytest.approx(10.0)


def test_high_water_mark_updates():
    pt = PositionTracker()
    pt.apply_buy("0xABC", units=1, fill_price=100.0, strategy="x")
    pt.update_mark("0xabc", 105.0)
    pt.update_mark("0xabc", 102.0)                      # should NOT lower the peak
    assert pt.get("0xabc").high_water_mark == 105.0


def test_sell_no_position_is_no_op():
    pt = PositionTracker()
    realized, p = pt.apply_sell("0xABC", units=5, fill_price=100.0)
    assert realized == 0.0
    assert p is None


def test_pyramid_add_preserves_stop_and_increments_step():
    """Pyramid add should NOT change the original stop_loss / take_profit
    (the risk plan was set at first entry). It should bump pyramid_step."""
    pt = PositionTracker()
    pt.apply_buy(
        token="0xABC", units=5, fill_price=100.0, strategy="smart_trend",
        stop_loss=95.0, take_profit=110.0, target_usd=1000.0,
    )
    p = pt.get("0xabc")
    assert p.pyramid_step == 0
    assert p.stop_loss == 95.0
    assert p.target_usd == 1000.0
    assert p.initial_risk == 5.0      # entry 100 - stop 95

    # Add at +0.5R = price 102.5
    pt.apply_buy(
        token="0xABC", units=5, fill_price=102.5, strategy="smart_trend",
        is_pyramid=True,
    )
    p = pt.get("0xabc")
    assert p.units == 10
    assert p.pyramid_step == 1
    assert p.stop_loss == 95.0          # unchanged
    assert p.take_profit == 110.0       # unchanged
    assert p.initial_risk == 5.0        # unchanged
    # Avg entry = (5×100 + 5×102.5) / 10 = 101.25
    assert p.avg_entry_price == pytest.approx(101.25)


def test_scale_out_preserves_avg_entry_and_basis_proportional():
    """A 50% scale-out should preserve avg_entry and halve the cost_basis."""
    pt = PositionTracker()
    pt.apply_buy(
        token="0xABC", units=10, fill_price=100.0, strategy="x",
        stop_loss=95.0, take_profit=110.0, target_usd=1000.0,
    )
    # Scale-out 50% at 110
    realized, p = pt.apply_sell("0xABC", units=5, fill_price=110.0)
    assert realized == pytest.approx(50.0)   # 5 × (110 - 100)
    p = pt.get("0xabc")
    assert p.units == 5
    assert p.avg_entry_price == pytest.approx(100.0)     # preserved
    assert p.cost_basis_usd == pytest.approx(500.0)       # halved
    # State still active — stop, target, target_usd intact
    assert p.stop_loss == 95.0
    assert p.take_profit == 110.0
    assert p.target_usd == 1000.0
    assert p.is_open()


def test_window_keyed_positions_are_isolated():
    """The same token in two different windows must NOT share a position."""
    pt = PositionTracker()
    pt.apply_buy("0xABC", units=10, fill_price=100.0, strategy="x",
                 window_id="win1", target_usd=500.0)
    pt.apply_buy("0xABC", units=20, fill_price=200.0, strategy="x",
                 window_id="win2", target_usd=2000.0)

    p1 = pt.get("0xABC", window_id="win1")
    p2 = pt.get("0xABC", window_id="win2")
    assert p1 is not None and p2 is not None
    assert p1.units == 10 and p1.avg_entry_price == 100.0
    assert p2.units == 20 and p2.avg_entry_price == 200.0

    # by_window returns only that window's positions
    assert len(pt.by_window("win1")) == 1
    assert len(pt.by_window("win2")) == 1
    # all_open sees both
    assert len(pt.all_open()) == 2
