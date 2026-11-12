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


def _week(k):
    return (pd.Timestamp("2025-01-06", tz="UTC") + pd.Timedelta(days=7 * k)).isoformat()


def test_metrics_expectancy_arithmetic():
    # ارشیا: ۵۰٪ برد با میانگین ۵R ← امید ۲R. هر معامله در هفته‌ای جدا، تا خوشه‌ها مستقل باشند
    trades = [_tr(5 if k % 2 == 0 else -1, _week(k)) for k in range(20)]
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


# ── بازبینی ۱۲ نوامبر — رویداد ۱۴۰: هر یافته یک آزمون با عدد دقیق ──────────────

def test_limit_entry_bar_target_not_credited():
    # سقف شمع ورود شاید پیش از پر شدن خرید محدود آمده باشد؛ هدف همان شمع شمرده نمی‌شود
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 96, 96.5), B(3, 96.5, 97, 93, 93.5)]
    for tgt in (103, 99):    # ۹۹ زیر باز شدن: نباید با باز شدن پیش از ورود بسته شود
        od = S.Order("long", "limit", price=97, stop=94, targets=[(tgt, 1.0)])
        t, = S.run(bars, once(od), **Z)
        assert t.reason == "stop" and t.exit == 94 and t.r == pytest.approx(-1.0)
        assert t.ambiguous is True


def test_gap_through_stop_beats_target_mode():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 90, 111, 88, 90)]
    od = S.Order("long", "market", stop=95, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), both_hit="target", **Z)
    assert t.reason == "stop" and t.exit == 90 and t.r == pytest.approx(-2.0)
    half = S.Order("long", "market", stop=95, targets=[(110, 0.5)])
    t2, = S.run(bars, once(half), both_hit="target", **Z)
    assert t2.r == pytest.approx(-2.0)


def test_gap_above_target_at_open_is_target_even_if_stop_touched_later():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 115, 116, 89, 95)]
    od = S.Order("long", "market", stop=90, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "target" and t.exit == 115 and t.r == pytest.approx(1.5)
    assert t.ambiguous is False


def test_market_order_through_stop_or_past_target_is_skipped():
    od = S.Order("long", "market", stop=90, targets=[(110, 1.0)])
    below = [B(1, 100, 100, 100, 100), B(2, 88, 89, 87, 88), B(3, 88, 89, 87, 88)]
    res = S.run(below, once(od), **Z)
    assert res == [] and [s["reason"] for s in res.skipped] == ["through_stop"]
    above = [B(1, 100, 100, 100, 100), B(2, 112, 113, 111, 112), B(3, 112, 113, 111, 112)]
    res2 = S.run(above, once(od), **Z)
    assert res2 == [] and [s["reason"] for s in res2.skipped] == ["past_target"]


def test_r_uses_planned_risk_so_a_gap_near_the_stop_cannot_explode():
    # اندازه پوزیشن در لحظه سفارش ثابت می‌شود: ریسک برنامه‌ریزی‌شده ۱۰۰ تا ۹۵
    bars = [B(1, 100, 100, 100, 100), B(2, 95.1, 105.5, 95.05, 105)]
    od = S.Order("long", "market", stop=95, targets=[(105, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.r == pytest.approx((105 - 95.1) / 5)          # ۱.۹۸، نه ۹۹


def test_stop_entry_bar_stop_is_pessimistic_flagged_and_never_at_prior_open():
    od = S.Order("long", "stop", price=105, stop=100, targets=[(115, 1.0)])
    for o, l in ((102, 99), (98, 97)):    # دومی: باز شدن زیر حد ضرر، پیش از ورود
        bars = [B(1, 100, 100, 100, 100), B(2, o, 106, l, 104)]
        t, = S.run(bars, once(od), **Z)
        assert t.entry == 105 and t.exit == 100 and t.r == pytest.approx(-1.0)
        assert t.ambiguous is True


def test_strategy_view_blocks_future_and_engine_is_linear():
    import time

    def probe(bars, i, p):
        assert len(bars) == i + 1 and bars[-1] is src[i] and bars[i] is src[i]
        assert len(bars[0:10 ** 6]) == i + 1 and bars[::-1][0] is src[i]
        if i == 2:
            bars[i + 1]                                     # آینده: باید IndexError بدهد
        return None
    src = [B(k % 28 + 1, 100, 101, 99, 100) for k in range(6)]
    with pytest.raises(IndexError):
        S.run(src, probe, **Z)
    big = [S.Bar(str(k), 100.0, 101.0, 99.0, 100.0) for k in range(100_000)]
    t0 = time.perf_counter()
    S.run(big, lambda b, i, p: None, **Z)
    assert time.perf_counter() - t0 < 5.0                  # کپی برش در هر شمع درجه دو بود


def test_cluster_bootstrap_correlated_duplicates_do_not_narrow_interval():
    base = [_tr(5 if k % 2 == 0 else -1, _week(k)) for k in range(20)]
    dup = [x for x in base for _ in range(5)]              # پنج نماد کاملاً هم‌بسته، همان روزها
    assert S.metrics(dup)["expectancy_ci90"] == pytest.approx(S.metrics(base)["expectancy_ci90"])
    assert S.metrics(base)["ci_clusters"] == 20


def _tx(r, ent, ex):
    return S.Trade("X", "long", "", ent, ent, 100, 95, ex, 100, "x", 1, r * 5, r)


def test_drawdown_and_streak_follow_exit_time():
    d = lambda k: f"2026-01-{k:02d}T00:00:00+00:00"
    trades = [_tx(3, d(1), d(10)), _tx(-2, d(2), d(3)), _tx(1, d(4), d(5)), _tx(-2, d(11), d(12))]
    m = S.metrics(trades)
    assert m["max_dd_r"] == pytest.approx(-2.0)            # به ترتیب ورود ۳- می‌شد


def test_equity_floors_at_zero_and_marks_ruin():
    m = S.metrics([_tr(-12, _week(0)), _tr(-12, _week(1))], risk_pct=10.0)
    assert m["max_dd_pct_at_risk"] == pytest.approx(-100.0) and m["ruined"] is True


@pytest.mark.parametrize("od", [
    S.Order("long", "market", stop=95, targets=[(110, 1.0)], time_stop=0),
    S.Order("long", "market", stop=95, targets=[(110, 0.8), (120, 0.8)]),
    S.Order("long", "market", stop=95, targets=[(98, 1.0)]),
    S.Order("long", "market", stop=101, targets=[(110, 1.0)]),
    S.Order("short", "limit", price=103, stop=106, targets=[(104, 1.0)]),
])
def test_bad_orders_rejected(od):
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100)]
    with pytest.raises(ValueError):
        S.run(bars, once(od), **Z)


def test_split_compares_real_times_not_strings():
    a = _tr(1, "2024-12-31T22:00:00-03:00")                # ۱ ژانویه ۰۱:۰۰ وقت جهانی ← بیرون‌نمونه
    b = _tr(-1, "2025-01-01T02:00:00+03:30")               # ۳۱ دسامبر ۲۲:۳۰ وقت جهانی ← درون‌نمونه
    s = S.split_metrics([a, b], "2025-01-01")
    assert s["in_sample"]["expectancy_r"] == -1 and s["out_of_sample"]["expectancy_r"] == 1


def test_bars_from_frame_sorts_and_refuses_unsafe_frames():
    ts = pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-02"], utc=True)
    base = {"ts": ts, "open": [3.0, 1.0, 2.0], "high": [3.5, 1.5, 2.5], "low": [2.5, 0.5, 1.5],
            "close": [3.2, 1.2, 2.2], "volume": [1.0, 1.0, 1.0]}
    bars = S.bars_from_frame(pd.DataFrame({**base, "confirm": [1, 1, float("nan")]}))
    assert [b.c for b in bars] == [1.2, 3.2]                # مرتب، و confirm نامعلوم یعنی باز
    with pytest.raises(ValueError):
        S.bars_from_frame(pd.DataFrame(base))               # بی confirm شمع باز جدا نمی‌شود
    with pytest.raises(ValueError):
        S.bars_from_frame(pd.DataFrame({**base, "ts": [1, 2, 3], "confirm": [1, 1, 1]}))


def test_fees_exact_values_exit_fee_on_exit_notional():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 104, 99.5, 103), B(3, 103, 111, 102, 110)]
    od = S.Order("long", "market", stop=95, targets=[(110, 1.0)])
    t, = S.run(bars, once(od), fee_bps=10, slip_bps=5)
    e, x = 100 * 1.0005, 110 * 0.9995
    pct = (x - e) / e - 0.001 - 0.001 * x / e
    assert t.pct == pytest.approx(100 * pct, abs=1e-4)
    assert t.r == pytest.approx(pct / (5 / e), abs=1e-4)


def test_short_with_costs_and_gap_through_stop():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 108, 109, 107, 108)]
    od = S.Order("short", "market", stop=105, targets=[(90, 1.0)])
    t, = S.run(bars, once(od), fee_bps=10, slip_bps=5)
    e, x = 100 * 0.9995, 108 * 1.0005                       # فروش ارزان‌تر، خرید گران‌تر
    pct = (e - x) / e - 0.001 - 0.001 * x / e
    assert t.reason == "stop" and t.exit == pytest.approx(x)
    assert t.r == pytest.approx(pct / (5 / e), abs=1e-4)    # شکاف: بیش از یک ریسک


def test_partial_target_then_stop():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 99, 104), B(3, 104, 104, 94, 95)]
    od = S.Order("long", "market", stop=95, targets=[(105, 0.5), (120, 0.5)])
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "stop" and t.pct == pytest.approx(0.0) and t.r == pytest.approx(0.0)


def test_expire_one_means_next_bar_only_and_reentry_after_close():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 100, 106, 99, 105)]
    od = S.Order("long", "stop", price=104, stop=99, targets=[(110, 1.0)], expire=1)
    assert S.run(bars, once(od), **Z) == []
    always = lambda b, i, p: S.Order("long", "market", stop=b[-1].c - 5, targets=[(b[-1].c + 1, 1.0)])
    seq = [B(k, 100, 101.5, 99, 100) for k in range(1, 6)]
    res = S.run(seq, always, **Z)
    assert [t.entry_t for t in res] == [b.t for b in seq[1:]]   # هر بسته‌شدن، ورود تازه در شمع بعد


def test_metrics_mixed_r_median_ambiguous_and_skipped():
    no_r = S.Trade("X", "long", "", _week(3), _week(3), 100, None, _week(3), 101, "x", 4, 1.0, None)
    ts = [_tr(2, _week(0)), _tr(-1, _week(1)), _tr(-1, _week(2)), no_r]
    ts[1].bars, ts[2].bars, ts[0].bars = 2, 3, 1
    ts[0].ambiguous = True
    m = S.metrics(ts, skipped=[{"reason": "through_stop"}, {"reason": "past_target"}, {"reason": "through_stop"}])
    assert m["r_n"] == 3 and m["expectancy_r"] == pytest.approx(0.0)
    assert m["median_bars"] == 2.5 and m["ambiguous_n"] == 1
    assert m["skipped"] == {"past_target": 1, "through_stop": 2}
    assert S.metrics([_tr(1, _week(0))])["profit_factor"] is None


def test_run_many_merges_skipped_and_cli_options(tmp_path, capsys):
    od = S.Order("long", "market", stop=90, targets=[(110, 1.0)])
    below = [B(1, 100, 100, 100, 100), B(2, 88, 89, 87, 88), B(3, 88, 89, 87, 88)]
    fine = [B(1, 100, 100, 100, 100), B(2, 100, 111, 99, 110), B(3, 110, 111, 109, 110)]
    res = S.run_many({"A": below, "B": fine}, once(od), **Z)
    assert len(res) == 1 and res[0].symbol == "B" and len(res.skipped) == 1
    closes = [100 - k for k in range(40)] + [61 + 2 * k for k in range(40)]
    df = pd.DataFrame([{"ts": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=k), "open": c,
                        "high": c + 1, "low": c - 1, "close": c, "volume": 1.0, "confirm": 1}
                       for k, c in enumerate(closes)])
    out = tmp_path / "s.json"
    rc = S.main(["run", "--strategy", "sma_cross", "--symbols", "btc,eth", "--from", "2026-01-01",
                 "--to", "2026-03-31", "--split", "2026-02-20", "--both-hit", "target", "--cluster", "day",
                 "--json", str(out)], history_fn=lambda *a: df)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0 and doc["meta"]["both_hit"] == "target" and doc["meta"]["cluster"] == "day"
    assert "split" in doc and "skipped" in doc and doc["version"] == S.VERSION
    assert "به فرض ترتیب درون شمع" in capsys.readouterr().out


def test_cluster_none_treats_each_trade_alone_even_if_same_object():
    one = _tr(5, _week(0))
    lose = _tr(-1, _week(0))
    m = S.metrics([one, lose] * 10, cluster="none")
    assert m["ci_clusters"] == 20                           # یک شیء تکراری هم جدا شمرده می‌شود
    assert S.metrics([one, lose] * 10)["expectancy_ci90"] is None   # همه در یک هفته: یک خوشه


def test_skip_decided_on_raw_open_not_slipped_price():
    # باز شدن 89.99 زیر حد ضرر ۹۰ است؛ لغزش خرید آن را به بالای ۹۰ می‌برد ولی نباید پنهانش کند
    od = S.Order("long", "market", stop=90, targets=[(110, 1.0)])
    bars = [B(1, 100, 100, 100, 100), B(2, 89.99, 91, 89, 90.5), B(3, 90.5, 91, 90, 90.5)]
    res = S.run(bars, once(od), fee_bps=10, slip_bps=5)
    assert res == [] and res.skipped[0]["reason"] == "through_stop"


# ── بازبینی دوم ۱۲ نوامبر — رویداد ۱۴۰ ─────────────────────────────────────────

@pytest.mark.parametrize("nxt,time_stop", [
    (B(3, 105, 106, 104, 105), None),          # باز شدن بالای هدف
    (B(3, 112, 113, 111, 112), None),          # شکاف بالای هدف
    (B(3, 101, 102, 93, 94), None),            # ریزش تا زیر حد ضرر
    (None, 1),                                  # خروج زمانی همان شمع ورود
])
def test_limit_entry_bar_close_beyond_target_proves_target(nxt, time_stop):
    # بسته شدن پس از پر شدن است: بسته ۱۰۵ بالای هدف ۱۰۳ یعنی هدف حتماً خورده شد
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 96, 105)] + ([nxt] if nxt else [])
    od = S.Order("long", "limit", price=97, stop=94, targets=[(103, 1.0)], time_stop=time_stop)
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "target" and t.exit == 103 and t.r == pytest.approx(2.0) and t.bars == 1


def test_short_limit_entry_bar_mirror():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 104, 94, 95), B(3, 95, 96, 94, 95)]
    od = S.Order("short", "limit", price=103, stop=106, targets=[(97, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.exit == 97 and t.r == pytest.approx(2.0)
    up = [B(1, 100, 100, 100, 100), B(2, 100, 104, 96, 99), B(3, 99, 107, 98, 106)]
    t2, = S.run(up, once(od), **Z)                          # کف ۹۶ شاید پیش از پر شدن بود
    assert t2.reason == "stop" and t2.r == pytest.approx(-1.0) and t2.ambiguous is True


def test_limit_entry_bar_close_beyond_target_and_stop_touched_is_ambiguous():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 93, 105)]
    od = S.Order("long", "limit", price=97, stop=94, targets=[(103, 1.0)])
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "stop" and t.ambiguous is True       # هر دو پس از پر شدن؛ ترتیب نامعلوم
    t2, = S.run(bars, once(od), both_hit="target", **Z)
    assert t2.reason == "target" and t2.r == pytest.approx(2.0)


def test_short_stop_entry_bar_and_gap_past_target():
    od = S.Order("short", "stop", price=95, stop=100, targets=[(85, 1.0)])
    bars = [B(1, 100, 100, 100, 100), B(2, 98, 101, 94, 96)]  # سقف ۱۰۱ شاید پیش از ورود
    t, = S.run(bars, once(od), **Z)
    assert t.entry == 95 and t.exit == 100 and t.r == pytest.approx(-1.0) and t.ambiguous is True
    gap = [B(1, 100, 100, 100, 100), B(2, 84, 85, 83, 84)]
    res = S.run(gap, once(od), **Z)
    assert res == [] and res.skipped[0]["reason"] == "past_target"


def test_stop_entry_bar_close_below_stop_is_certain_not_ambiguous():
    od = S.Order("long", "stop", price=105, stop=100, targets=[(115, 1.0)])
    bars = [B(1, 100, 100, 100, 100), B(2, 102, 106, 98, 99)]
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "stop" and t.ambiguous is False      # بسته زیر حد ضرر پس از ورود است


def test_stop_entry_bar_both_hit_target_mode():
    od = S.Order("long", "stop", price=105, stop=100, targets=[(110, 1.0)])
    bars = [B(1, 100, 100, 100, 100), B(2, 102, 111, 99, 108)]
    t, = S.run(bars, once(od), both_hit="target", **Z)
    assert t.reason == "target" and t.r == pytest.approx(1.0) and t.ambiguous is True


def test_partial_targets_with_gap_open_then_stop():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 108, 109, 94, 95)]
    od = S.Order("long", "market", stop=95, targets=[(105, 0.5), (107, 0.25), (120, 0.25)])
    t, = S.run(bars, once(od), **Z)
    # دو پله نزدیک در باز شدن ۱۰۸، یک‌چهارم مانده در حد ضرر ۹۵
    assert t.pct == pytest.approx(0.75 * 8 - 0.25 * 5) and t.r == pytest.approx((0.75 * 8 - 0.25 * 5) / 5)
    assert t.ambiguous is False


def test_limit_fill_at_better_gap_open_uses_planned_risk():
    od = S.Order("long", "limit", price=97, stop=94, targets=[(103, 1.0)])
    bars = [B(1, 100, 100, 100, 100), B(2, 96, 97, 95, 96.5), B(3, 96.5, 97, 93, 93.5)]
    t, = S.run(bars, once(od), **Z)
    assert t.entry == 96 and t.r == pytest.approx((94 - 96) / 3, abs=1e-4)   # اندازه از ۹۷ تا ۹۴


def test_time_stop_and_target_on_same_bar():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100), B(3, 100, 111, 99, 104)]
    od = S.Order("long", "market", stop=95, targets=[(110, 0.5)], time_stop=2)
    t, = S.run(bars, once(od), **Z)
    assert t.reason == "time" and t.pct == pytest.approx(0.5 * 10 + 0.5 * 4)


def test_list_targets_from_json_work():
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 106, 99, 104)]
    t, = S.run(bars, once(S.Order("long", "market", stop=95, targets=[[105, 1.0]])), **Z)
    assert t.reason == "target" and t.r == pytest.approx(1.0)


@pytest.mark.parametrize("od", [
    S.Order("long", "market", stop=float("nan"), targets=[(110, 1.0)]),
    S.Order("long", "market", stop=95, targets=[(float("nan"), 1.0)]),
    S.Order("long", "limit", price=float("inf"), stop=95, targets=[(110, 1.0)]),
])
def test_non_finite_orders_rejected(od):
    bars = [B(1, 100, 100, 100, 100), B(2, 100, 101, 99, 100)]
    with pytest.raises(ValueError):
        S.run(bars, once(od), **Z)


def test_bars_from_frame_rejects_non_finite_prices():
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01"], utc=True), "open": [float("nan")], "high": [1.0],
                       "low": [0.5], "close": [0.8], "volume": [1.0], "confirm": [1]})
    with pytest.raises(ValueError):
        S.bars_from_frame(df)


def test_small_sample_counts_clusters_too():
    ts = [_tr(5 if k % 2 == 0 else -1, _week(k % 10)) for k in range(50)]
    m = S.metrics(ts)
    assert m["ci_clusters"] == 10 and m["small_sample"] is True
