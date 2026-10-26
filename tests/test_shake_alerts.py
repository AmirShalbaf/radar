"""
هشدار تکان — بند ۲ متن ۱۸، ۲۶ اکتبر ۲۰۲۶. در مسیر نبض، از همان منبع داده نبض.

برای BTC و هر موقعیت باز دفتر موقعیت:
  - حرکت ۵٪ یا بیشتر در ۴ ساعت، یا ۸٪ یا بیشتر در ۲۴ ساعت، با شمع بسته ساعتی
  - قیمت تا ۲٪ بالای سطح ابطال، یا عبور درون‌روزی به زیر آن — «حکم فقط با بسته هفتگی است»
  - تغییر باند خام رژیم نسبت به گزارش قبلی
هر رویداد برای هر نماد در هر روز وقت جهانی یک بار؛ کلید فقط پس از ارسال موفق؛ سقف ۳
پیام در هر اجرا. ساعت پیام به وقت تهران.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W
import radar_telegram as TG

UTC = timezone.utc
NOW = datetime(2026, 10, 26, 8, 41, tzinfo=UTC)          # دوشنبه


def _bars(closes, end=NOW, low=None):
    """شمع‌های بسته ساعتی تا آخرین ساعت کامل پیش از end. closes به ترتیب زمان."""
    last_open = end.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    out = []
    for i, c in enumerate(closes):
        op = last_open - timedelta(hours=len(closes) - 1 - i)
        lo = low.get(i, c * 0.999) if low else c * 0.999
        out.append({"open": op, "close": float(c), "low": float(lo), "high": float(c) * 1.001})
    return out


def _flat(px, n=30):
    return [px] * n


def _h(qty=5.0, sym="SOL", inv=96.7108):
    return {"version": 2, "frozen": {"date": "2026-09-25", "members": {sym: qty, "TAO": 0.000092},
                                     "cash": []},
            "cash": [],
            "positions": [{"symbol": sym, "book": "position", "status": "open",
                           "invalidation": inv, "invalidation_since": "2026-09-25T21:34:47+00:00",
                           "lots": [{"qty": qty, "account": "LBank", "entry": None}]},
                          {"symbol": "TAO", "book": "position", "status": "open",
                           "invalidation": None,
                           "lots": [{"qty": 0.000092, "account": "LBank", "entry": None}]}],
            "ledger": []}


def _watch(sym="SOL", inv=96.7108, plan=None):
    w = {"positions": [{"symbol": sym, "invalidation": inv,
                        "invalidation_since": "2026-09-25T21:34:47+00:00"}]}
    if plan:
        w["reserve_plan"] = plan
    return w


def _feed(data):
    def hourly(sym):
        if sym not in data:
            return None, ["آزمون: داده نیست"]
        return data[sym], []
    return hourly


def _run(data, state, watch=None, h=None, regime=None, history=None, now=NOW):
    # انحراف معیار غایب: کف ثابت — آستانه نسبی ک۱۰۵ در آزمون‌های جدا، پایین همین پرونده
    return W.shake_alerts(watch or _watch(), h or _h(), state, now, hourly=_feed(data),
                          regime=regime, history=history,
                          sigma=lambda sym, hrs: (None, ["آزمون"]))


# ── حرکت ──

def test_four_hour_move_fires_and_tiny_one_does_not() -> None:
    up = _flat(100.0, 26) + [101, 102, 104, 105.0]       # 4 ساعت: 100 ← 105، +5.0٪
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}, {})
    assert len(msgs) == 1 and "SOL" in msgs[0] and "+5.0٪" in msgs[0]
    assert "۴ ساعت" in msgs[0]
    small = _flat(100.0, 26) + [101, 102, 103, 104.9]
    assert _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(small)}, {}) == []


def test_down_move_and_24h_move() -> None:
    down = [100.0] * 6 + [98.0] * 20 + [97, 96, 95, 94.5]   # 4 ساعت 98 ← 94.5 = −3.6٪
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(down)}, {}, watch=_watch(inv=50.0),
                h=_h(inv=50.0))
    assert msgs == []
    down24 = [100.0] * 6 + list(range(99, 91, -1)) + [92.0] * 16   # 24 ساعت: 100 ← 92 = −8٪
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(down24)}, {},
                watch=_watch(inv=50.0), h=_h(inv=50.0))
    assert len(msgs) == 1 and "۲۴ ساعت" in msgs[0] and "-8.0٪" in msgs[0]


def test_btc_included_without_level() -> None:
    btc = _flat(80000.0, 26) + [81000, 82000, 83000, 84500.0]    # +5.6٪
    msgs = _run({"BTC": _bars(btc), "SOL": _bars(_flat(110.0))}, {})
    assert len(msgs) == 1 and msgs[0].startswith("📈 تکان BTC")
    assert "سطح ابطال" not in msgs[0]


def test_dust_position_skipped() -> None:
    tao = _flat(250.0, 26) + [260, 270, 280, 300.0]
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(_flat(110.0)), "TAO": _bars(tao)}, {})
    assert msgs == []


# ── سطح ابطال ──

def test_near_level_message_says_weekly_close_only() -> None:
    sol = _flat(99.0, 29) + [97.9]                     # 1.23٪ بالای 96.7108
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(sol)}, {})
    assert len(msgs) == 1
    m = msgs[0]
    assert "نزدیک سطح ابطال" in m and "97.9" in m and "96.7108" in m and "1.2٪" in m
    assert "حکم فقط با بسته هفتگی است" in m
    # آخرین شمع بسته 07:00 تا 08:00 وقت جهانی — 11:30 تهران
    assert "2026-10-26 11:30 تهران" in m
    # بسته هفتگی بعد: دوشنبه 2026-11-02 00:00 وقت جهانی — 03:30 تهران
    assert "2026-11-02 03:30 تهران" in m


def test_far_from_level_is_quiet() -> None:
    sol = _flat(99.0, 30)                              # 2.37٪ بالای سطح
    assert _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(sol)}, {}) == []


def test_intraday_cross_below_level() -> None:
    sol = _flat(99.0, 30)
    bars = _bars(sol, low={27: 96.2})
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": bars}, {})
    assert len(msgs) == 1
    assert "زیر سطح ابطال" in msgs[0] and "96.2" in msgs[0]
    assert "حکم فقط با بسته هفتگی است" in msgs[0]


def test_cross_keyed_by_candle_day_not_repeated_next_day() -> None:
    state: dict = {}
    late = datetime(2026, 10, 25, 22, 41, tzinfo=UTC)
    bars = _bars(_flat(99.0), end=late, low={28: 96.0})       # شمع 20:00 روز ۲۵
    msgs = _run({"BTC": _bars(_flat(80000.0), end=late), "SOL": bars}, state, now=late)
    assert len(msgs) == 1
    W.commit_sent(msgs, state)
    # روز بعد همان شمع هنوز در پنجره ۲۴ ساعت است — پیام دوباره نه
    nxt = datetime(2026, 10, 26, 0, 41, tzinfo=UTC)
    rows = [b for b in bars] + _bars(_flat(99.0, 2), end=nxt)
    msgs = _run({"BTC": _bars(_flat(80000.0), end=nxt), "SOL": rows}, state, now=nxt)
    assert msgs == []


# ── باند خام رژیم ──

def _regime(band="انقباضی", at="2026-10-20T12:01:31+00:00", score=-0.5647):
    return {"generated_at": at, "score": score, "band": {"name": band, "stable": 40},
            "trade_band": {"name": band}}


def _hist(**days):
    return {"days": {d: {"band": b} for d, b in days.items()}}


def test_raw_band_change_fires_once() -> None:
    state: dict = {}
    hist = _hist(**{"2026-10-19": "محتاط", "2026-10-20": "انقباضی"})
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(_flat(110.0))}
    now = datetime(2026, 10, 20, 13, 41, tzinfo=UTC)
    data = {k: _bars(_flat(v[0]["close"]), end=now) for k, v in data.items()}
    msgs = _run(data, state, regime=_regime(), history=hist, now=now)
    assert len(msgs) == 1
    m = msgs[0]
    assert "از محتاط به انقباضی" in m and "۲۵٪" in m and "۴۰٪" in m
    W.commit_sent(msgs, state)
    assert _run(data, state, regime=_regime(), history=hist, now=now) == []


def test_no_band_change_no_message() -> None:
    hist = _hist(**{"2026-10-24": "انقباضی", "2026-10-25": "انقباضی"})
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(_flat(110.0))}, {},
                regime=_regime(at="2026-10-25T11:56:12+00:00"), history=hist)
    assert msgs == []


# ── قاعده‌های ارسال ──

def test_once_per_day_and_again_next_day() -> None:
    state: dict = {}
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    msgs = _run(data, state, watch=_watch(inv=50.0), h=_h(inv=50.0))
    assert len(msgs) == 1
    W.commit_sent(msgs, state)
    assert _run(data, state, watch=_watch(inv=50.0), h=_h(inv=50.0)) == []
    tomorrow = NOW + timedelta(days=1)
    data2 = {"BTC": _bars(_flat(80000.0), end=tomorrow), "SOL": _bars(up, end=tomorrow)}
    assert len(_run(data2, state, watch=_watch(inv=50.0), h=_h(inv=50.0), now=tomorrow)) == 1


def test_cap_three_per_run_rest_next_run() -> None:
    state: dict = {}
    syms = ["SOL", "ETH", "AAVE", "LINK", "SUI"]
    h = {"positions": [{"symbol": s, "book": "position", "status": "open", "invalidation": 1.0,
                        "invalidation_since": "2026-09-25T21:34:47+00:00",
                        "lots": [{"qty": 100.0, "account": "LBank", "entry": None}]}
                       for s in syms], "ledger": []}
    watch = {"positions": [{"symbol": s, "invalidation": 1.0,
                            "invalidation_since": "2026-09-25T21:34:47+00:00"} for s in syms]}
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]
    data = {"BTC": _bars(_flat(80000.0)), **{s: _bars(up) for s in syms}}
    first = _run(data, state, watch=watch, h=h)
    assert len(first) == W.SHAKE_MAX_MSGS == 3
    W.commit_sent(first, state)
    second = _run(data, state, watch=watch, h=h)
    assert len(second) == 2
    assert {m.split()[2] for m in first} | {m.split()[2] for m in second} == set(syms)


def test_open_order_changes_action() -> None:
    plan = {"created": "2026-10-24T03:46:49+00:00", "deadline": "2026-11-26T00:00:00+00:00",
            "steps": [{"symbol": "SOL", "qty": 0.5, "price": 120.0}]}
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}, {},
                watch=_watch(inv=50.0, plan=plan), h=_h(inv=50.0))
    assert "سفارش‌های باز SOL را ببین" in msgs[0]
    msgs = _run({"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}, {},
                watch=_watch(inv=50.0), h=_h(inv=50.0))
    assert "اقدامی تا بسته هفتگی لازم نیست" in msgs[0]


def test_no_data_is_printed_not_sent(capsys) -> None:
    msgs = _run({"BTC": _bars(_flat(80000.0))}, {})
    assert msgs == []
    assert "SOL" in capsys.readouterr().out


def test_run_once_commits_shake_key_only_after_receipt(tmp_path, monkeypatch) -> None:
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(W, "_shake_feed", lambda: _feed(data))
    monkeypatch.setattr(W, "_sigma_feed", lambda: (lambda sym, hrs: (None, ["آزمون"])))
    monkeypatch.setattr(W, "ticker", lambda s: None)
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None: (None, ["آزمون"]))
    sent = []
    monkeypatch.setattr(TG, "send", lambda text: (sent.append(text), TG.Sent(False, "کد 500"))[1])
    state: dict = {"weekly_digest_2026-10-26T00:00:00+00:00": {"sent": "x"}}
    W.run_once(_watch(inv=50.0), state, quiet=True, path=str(tmp_path / "w.json"), h=_h(inv=50.0),
               now=NOW, regime_path=None, shake=True)
    assert any("📈 تکان SOL" in s for s in sent)
    assert not any(k.startswith("shake_") for k in state)
    monkeypatch.setattr(TG, "send", lambda text: (sent.append(text), TG.Sent(True, "کد 200"))[1])
    W.run_once(_watch(inv=50.0), state, quiet=True, path=str(tmp_path / "w.json"), h=_h(inv=50.0),
               now=NOW, regime_path=None, shake=True)
    assert any(k.startswith("shake_move4_SOL_") for k in state)


def test_tehran_offset_single_source() -> None:
    import radar_anchor as A
    import radar_video as V
    assert V.TEHRAN is A.TEHRAN
    assert A.TEHRAN.utcoffset(None) == timedelta(hours=3, minutes=30)


# ── ک۱۰۵، متن ۱۹: آستانه نسبی به نوسان ──

def _sig(**sd):
    """انحراف معیار ساختگی: نماد ← {ساعت: درصد}؛ غایب یعنی داده ندارم."""
    def sigma(sym, hrs):
        v = (sd.get(sym) or {}).get(hrs)
        return (v, []) if v is not None else (None, ["آزمون: داده نیست"])
    return sigma


def test_move_sigma_definition() -> None:
    closes = [100.0, 101.0, 100.0, 102.0, 101.0]
    rets = [100 * (closes[i] / closes[i - 1] - 1) for i in range(1, 5)]   # بازده ۱ ساعته، درصد
    mu = sum(rets) / 4
    sd = (sum((x - mu) ** 2 for x in rets) / 3) ** 0.5
    assert W.move_sigma(closes, 1) == pytest.approx(sd)
    assert W.move_sigma([100.0, 101.0], 1) is None


def test_relative_threshold_suppresses_noisy_move() -> None:
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]               # +6٪ در ۴ ساعت
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    msgs = W.shake_alerts(_watch(inv=50.0), _h(inv=50.0), {}, NOW, hourly=_feed(data),
                          sigma=_sig(SOL={4: 2.0, 24: 3.0}))     # آستانه max(5، 8) = 8٪
    assert msgs == []


def test_relative_threshold_keeps_big_move_and_says_rule() -> None:
    up = _flat(100.0, 26) + [102, 104, 106, 109.0]               # +9٪
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    msgs = W.shake_alerts(_watch(inv=50.0), _h(inv=50.0), {}, NOW, hourly=_feed(data),
                          sigma=_sig(SOL={4: 2.0, 24: 4.0}))   # ۲۴ ساعت: آستانه 12٪
    assert len(msgs) == 1
    assert "آستانه 8.0٪" in msgs[0] and "۴ برابر انحراف معیار" in msgs[0] and "2.00٪" in msgs[0]


def test_low_volatility_keeps_fixed_floor() -> None:
    up = _flat(100.0, 26) + [101, 102, 104, 105.5]               # +5.5٪، σ کوچک
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    msgs = W.shake_alerts(_watch(inv=50.0), _h(inv=50.0), {}, NOW, hourly=_feed(data),
                          sigma=_sig(SOL={4: 0.5, 24: 1.0}))
    assert len(msgs) == 1 and "آستانه 5.0٪" in msgs[0]


def test_sigma_missing_falls_back_to_fixed() -> None:
    up = _flat(100.0, 26) + [101, 102, 104, 106.0]
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(up)}
    msgs = W.shake_alerts(_watch(inv=50.0), _h(inv=50.0), {}, NOW, hourly=_feed(data),
                          sigma=_sig())
    assert len(msgs) == 1 and "انحراف معیار: داده ندارم" in msgs[0]


def test_sigma_fetched_only_past_fixed_threshold() -> None:
    asked = []

    def sigma(sym, hrs):
        asked.append((sym, hrs))
        return None, []
    data = {"BTC": _bars(_flat(80000.0)), "SOL": _bars(_flat(110.0))}
    W.shake_alerts(_watch(), _h(), {}, NOW, hourly=_feed(data), sigma=sigma)
    assert asked == []


# ── بند ۸ متن ۱۹: هفته نقض — اقدام فقط ارجاع به پیام ابطال ──

def test_breached_week_action_points_to_invalidation_message() -> None:
    sol = _flat(99.0, 30)
    bars = _bars(sol, low={27: 96.2})                            # عبور درون‌روزی
    weekly = lambda s: ({"close": 95.5, "closed_at": "2026-10-26T00:00:00+00:00",
                         "venue": "okx"}, [])
    msgs = W.shake_alerts(_watch(), _h(), {}, NOW, hourly=_feed({"BTC": _bars(_flat(80000.0)),
                                                                  "SOL": bars}),
                          sigma=lambda s, h: (None, []), weekly=weekly)
    assert len(msgs) == 1
    assert "پیام ابطال هفتگی SOL را ببین" in msgs[0] and "95.5" in msgs[0]
    assert "اقدامی تا بسته هفتگی لازم نیست" not in msgs[0]


def test_week_above_level_keeps_wait_action() -> None:
    sol = _flat(99.0, 30)
    bars = _bars(sol, low={27: 96.2})
    weekly = lambda s: ({"close": 101.4, "closed_at": "2026-10-26T00:00:00+00:00",
                         "venue": "okx"}, [])
    msgs = W.shake_alerts(_watch(), _h(), {}, NOW, hourly=_feed({"BTC": _bars(_flat(80000.0)),
                                                                  "SOL": bars}),
                          sigma=lambda s, h: (None, []), weekly=weekly)
    assert "اقدامی تا بسته هفتگی لازم نیست" in msgs[0]


def test_run_once_passes_weekly_cache_to_shake(tmp_path, monkeypatch) -> None:
    bars = _bars(_flat(99.0, 30), low={27: 96.2})
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(W, "_shake_feed", lambda: _feed({"BTC": _bars(_flat(80000.0)),
                                                          "SOL": bars}))
    monkeypatch.setattr(W, "_sigma_feed", lambda: (lambda s, h: (None, [])))
    monkeypatch.setattr(W, "ticker", lambda s: None)
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None: (
        {"close": 95.5, "closed_at": "2026-10-26T00:00:00+00:00", "venue": "okx"}, []))
    sent = []
    monkeypatch.setattr(TG, "send", lambda text: (sent.append(text), TG.Sent(True, "کد 200"))[1])
    W.run_once(_watch(), {"weekly_digest_2026-10-26T00:00:00+00:00": {"sent": "x"}}, quiet=True,
               path=str(tmp_path / "w.json"), h=_h(), now=NOW, regime_path=None, shake=True)
    cross = [s for s in sent if "زیر سطح ابطال درون‌روز" in s]
    assert cross and "پیام ابطال هفتگی SOL را ببین" in cross[0]
