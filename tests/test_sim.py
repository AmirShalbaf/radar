# -*- coding: utf-8 -*-
"""آزمون هسته شبیه‌ساز — ک۱۳۳. بی‌شبکه، با شمع ساختگی و عددهای دستی."""
from __future__ import annotations

import json

import pandas as pd
import pytest

import radar_sim as S


def B(t, o, h, l, c):
    return S.Bar(f"2026-01-{t:02d}T00:00:00+00:00", o, h, l, c)


def once(order, at=0):
    """استراتژی‌ای که فقط در بسته شدن شمع at یک سفارش می‌دهد."""
    def f(bars, i, p):
        return order if i == at else None
    return f


Z = dict(fee_bps=0.0, slip_bps=0.0)


def test_market_entry_next_open_and_target():
    bars = [B(1, 100, 101, 99, 100), B(2, 100, 104, 99.5, 103), B(3, 103, 111, 102, 110)]
    od = S.Order("long", "market", stop=95, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.entry == 100 and t.entry_t == bars[1].t      # باز شدن شمع بعد از سیگنال
    assert t.exit == 110 and t.reason == "target"
    assert t.r == pytest.approx(2.0)                       # ۱۰ سود روی ۵ ریسک
    assert t.pct == pytest.approx(10.0)


def test_no_lookahead_strategy_sees_only_past():
    seen = []

    def spy(bars, i, p):
        seen.append((i, len(bars), bars[-1].c))
        return None
    bars = [B(k, 100 + k, 101 + k, 99 + k, 100 + k) for k in range(1, 6)]
    S.run(bars, spy, **Z)
    assert all(n == i + 1 for i, n, _ in seen)
    assert all(c == bars[i].c for i, _, c in seen)
    assert seen[-1][0] == len(bars) - 2                   # آخرین شمع سیگنال نمی‌دهد


def test_stop_and_target_same_bar_is_stop_by_default():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 112, 94, 100)]
    od = S.Order("long", "market", stop=95, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "stop" and t.r == pytest.approx(-1.0)
    t2, = S.run(bars, once(od), both_hit="target", **Z)
    assert t2.reason == "target" and t2.r == pytest.approx(2.0)


def test_gap_through_stop_exits_at_open_worse_than_stop():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 90, 92, 88, 91)]
    od = S.Order("long", "market", stop=95, targets=[(120, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.exit == 90 and t.reason == "stop"
    assert t.r == pytest.approx(-2.0)                      # شکاف، ضرر دو برابر ریسک


def test_stop_entry_triggers_on_touch_and_on_gap_at_open():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 103, 99, 102), B(3, 102, 120, 101, 119)]
    od = S.Order("long", "stop", price=102.5, stop=99, targets=[(115, 1.0)], expire=2)
    t, = S.run(bars, once(od), **Z)
    assert t.entry == 102.5 and t.entry_t == bars[1].t
    gap = [B(1, 100, 100, 100, 100), B(2, 105, 106, 104, 105), B(3, 105, 120, 104, 119)]
    t2, = S.run(gap, once(od), **Z)
    assert t2.entry == 105                                 # شکاف از ماشه: باز شدن شمع


def test_stop_order_expires_unfilled():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 100, 101, 99, 100), B(4, 100, 130, 99, 120)]
    od = S.Order("long", "stop", price=110, stop=99, targets=[(125, 1.0)], expire=2)
    assert S.run(bars, once(od), **Z) == []


def test_limit_entry():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 100, 96, 97), B(3, 97, 106, 97, 105)]
    od = S.Order("long", "limit", price=97, stop=94, targets=[(103, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.entry == 97 and t.exit == 103 and t.r == pytest.approx(2.0)


def test_partial_targets_and_time_stop():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 99, 105), B(3, 105, 107, 104, 106), B(4, 106, 107, 104, 104)]
    od = S.Order("long", "market", stop=95, targets=[(105, 0.5), (120, 0.5)], time_stop=3)
    t, = S.run(bars, once(od), **Z)
    # نیمی در 105 (+5٪)، نیمی با خروج زمانی در بسته شمع سوم پس از ورود، 104 (+4٪)
    assert t.reason == "time" and t.bars == 3
    assert t.pct == pytest.approx(4.5)
    assert t.r == pytest.approx(0.9)


def test_short_side():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 95, 96), B(3, 96, 97, 89, 90)]
    od = S.Order("short", "market", stop=105, targets=[(90, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.exit == 90 and t.r == pytest.approx(2.0)


def test_fees_and_slippage_reduce_result():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 104, 99.5, 103), B(3, 103, 111, 102, 110)]
    od = S.Order("long", "market", stop=95, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), fee_bps=10, slip_bps=5)
    assert t.entry == pytest.approx(100.05)                # خرید گران‌تر
    assert t.exit == pytest.approx(109.945)                # فروش ارزان‌تر
    assert t.pct < 10 - 0.2 and t.r < 2.0


def test_no_stop_trade_has_pct_but_no_r():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 80, 85), B(3, 85, 112, 84, 111)]
    od = S.Order("long", "market", stop=None, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.r is None and t.pct == pytest.approx(10.0)
    assert t.mae_pct == pytest.approx(-20.0)               # بی حد ضرر، بیست درصد زیر آب رفت
    m = S.metrics([t])
    assert "expectancy_r" not in m and m["win_rate"] == 100.0


def test_open_position_closed_at_end():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 102, 99, 101), B(3, 101, 103, 100, 102)]
    od = S.Order("long", "market", stop=90, targets=[(150, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "end" and t.exit == 102


def test_wrong_side_stop_rejected():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100)]
    with pytest.raises(ValueError):
        S.run(bars, once(S.Order("long", "stop", price=101, stop=102)), **Z)


def _tr(r, t="2026-01-05T00:00:00+00:00"):
    return S.Trade("X", "long", "", t, t, 100, 95, t, 100, "x", 1, r * 5, r)


def test_metrics_expectancy_arithmetic():
    # ارشیا: ۵۰٪ برد با میانگین ۵R ← امید ۲R
    trades = [_tr(5), _tr(-1)] * 10
    m = S.metrics(trades, risk_pct=1.0)
    assert m["n"] == 20 and m["win_rate"] == 50.0
    assert m["expectancy_r"] == pytest.approx(2.0)
    assert m["avg_win_r"] == 5 and m["avg_loss_r"] == -1
    assert m["profit_factor"] == pytest.approx(5.0)
    lo, hi = m["expectancy_ci90"]
    assert lo <= 2.0 <= hi
    # بیست درصد برد هنوز مثبت: 0.2 × 5 − 0.8 × 1 = 0.2
    m2 = S.metrics([_tr(5)] * 2 + [_tr(-1)] * 8)
    assert m2["expectancy_r"] == pytest.approx(0.2)


def test_metrics_drawdown_and_streak():
    rs = [1, -1, -1, -1, 2, -1]
    m = S.metrics([_tr(r) for r in rs], risk_pct=2.0)
    assert m["max_dd_r"] == pytest.approx(-3.0)
    assert m["longest_loss_streak"] == 3
    assert m["max_dd_pct_at_risk"] == pytest.approx(round(100 * (0.98 ** 3 - 1), 2))


def test_split_in_out_of_sample():
    a = _tr(1, "2024-06-01T00:00:00+00:00")
    b = _tr(-1, "2025-06-01T00:00:00+00:00")
    s = S.split_metrics([a, b], "2025-01-01")
    assert s["in_sample"]["n"] == 1 and s["out_of_sample"]["n"] == 1
    assert s["in_sample"]["expectancy_r"] == 1 and s["out_of_sample"]["expectancy_r"] == -1


def test_bars_from_frame_skips_open_candle():
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                       "open": [1.0, 2.0], "high": [1.5, 2.5], "low": [0.5, 1.5], "close": [1.2, 2.2],
                       "volume": [10.0, 20.0], "confirm": [1, 0]})
    bars = S.bars_from_frame(df)
    assert len(bars) == 1 and bars[0].c == 1.2 and bars[0].t.startswith("2026-01-01")


def test_sma_cross_end_to_end_and_cli(tmp_path, capsys):
    # روند پایین، سپس بالا: یک تقاطع، یک معامله
    closes = [100 - k for k in range(40)] + [61 + 2 * k for k in range(40)]
    rows = []
    for k, c in enumerate(closes):
        rows.append({"ts": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=k),
                     "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0, "confirm": 1})
    df = pd.DataFrame(rows)
    out = tmp_path / "sim.json"
    rc = S.main(["run", "--strategy", "sma_cross", "--symbols", "btc", "--tf", "1d", "--from", "2026-01-01",
                 "--to", "2026-03-31", "--json", str(out), "--params", '{"rr": 2, "hold": 100}'],
                history_fn=lambda *a: df)
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["metrics"]["n"] >= 1 and doc["trades"][0]["symbol"] == "BTC"
    assert "شبیه‌ساز — sma_cross" in capsys.readouterr().out
