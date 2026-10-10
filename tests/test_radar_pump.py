# -*- coding: utf-8 -*-
"""
آزمون اسکنر پامپ — نشست ۹، ایستگاه ۲الف. بی‌شبکه، با داده مصنوعی.

قاعده‌ها: کندل باز حذف؛ صرافی‌ها ترکیب نمی‌شوند؛ جزء غایب صفر نیست؛ رتبه بی امتیاز؛
«نامعلوم» وتو نیست؛ خروجی فایل است نه پوشه — ک۱۴؛ همه نامزدها «آزمون‌نشده»؛
اسکنر چیزی در دفتر موقعیت نمی‌نویسد.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import radar_fetch3 as R
import radar_pump as P

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 7, 30, tzinfo=UTC)          # شنبه
HOUR_MS = 3_600_000


# ═══════════════ سازنده‌های داده مصنوعی ═══════════════

def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def okx_rows(qv: list[float], bar_h: int = 1, close: float = 1.0, open_last: bool = True,
             end: datetime = NOW) -> list[list[str]]:
    """کندل اوکی‌اکس، تازه‌ترین اول. آخرین ردیف کندل باز است (confirm=0)."""
    step = bar_h * HOUR_MS
    last_open = _ms(end.replace(minute=0, second=0, microsecond=0)) // step * step
    n = len(qv) + (1 if open_last else 0)
    out = []
    for k in range(n):
        ts = last_open - (n - 1 - k) * step
        is_open = open_last and k == n - 1
        v = 9e12 if is_open else qv[k]            # کندل باز عمداً غول‌آسا — نباید دیده شود
        c = close
        out.append([str(ts), str(c), str(c * 1.01), str(c * 0.99), str(c), "1", "1", str(v),
                    "0" if is_open else "1"])
    return list(reversed(out))


def closed_frame(qv, close=1.0):
    return P.closed(P.okx_frame(okx_rows(list(qv), close=close)))


def daily(spec: list[tuple[float, float, float, float, float]], open_candle: bool = False) -> pd.DataFrame:
    """قاب روزانه از (open, high, low, close, vol)."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [{"ts": t0 + timedelta(days=i), "open": o, "high": h, "low": l, "close": c, "vol": v,
             "confirm": 1} for i, (o, h, l, c, v) in enumerate(spec)]
    if open_candle:
        o, h, l, c, v = spec[-1]
        rows.append({"ts": t0 + timedelta(days=len(spec)), "open": c, "high": c, "low": c,
                     "close": c, "vol": v, "confirm": 0})
    return pd.DataFrame(rows)


def base_osc(n: int, lo_close: float = 94.0, hi_close: float = 96.0, vol: float = 1000.0):
    """نوسان دوحالته بی نقطه چرخش — بیشینه و کمینه هر پنجره یکتا نیست."""
    out = []
    for i in range(n):
        c = lo_close if i % 2 == 0 else hi_close
        out.append((c, c + 1, c - 1, c, vol))
    return out


def breakout_spec(last: tuple, vol_mult: float = 5.0):
    """
    سطح ۱۰۰ با دو برخورد (اندیس ۲۰ و ۴۰)، رنج زیرش، شکست در اندیس ۶۵،
    و کندل آخر به انتخاب آزمون. ۶۰ تا ۶۹ پنجره اخیر است.
    """
    spec = base_osc(65)
    spec[20] = (96, 100.0, 95, 96, 1000)
    spec[40] = (96, 100.3, 95, 96, 1000)
    spec.append((96, 104, 95.5, 103, 1000 * vol_mult))      # 65: شکست
    spec.append((103, 105, 102, 104, 1000))                 # 66
    spec.append((104, 105, 102.5, 104.5, 1000))             # 67
    spec.append((104.5, 105, 102, 103, 1000))               # 68
    spec.append(last)                                       # 69
    return spec


def zigzag(points: list[tuple[int, float]]):
    """قیمت میانی تکه‌خطی؛ همه کندل‌ها نزولی، دامنه یک واحد."""
    xs, ys = zip(*points)
    out = []
    for i in range(xs[-1] + 1):
        m = float(np.interp(i, xs, ys))
        out.append((m + 0.2, m + 0.5, m - 0.5, m - 0.2, 1000.0))
    return out


def squeeze_spec(extra: tuple | None = None):
    spec = []
    for i in range(40):
        m = 90.0 if i % 2 == 0 else 110.0
        spec.append((m, m + 2, m - 2, m, 1000.0))
    for _ in range(10):
        spec.append((100.0, 100.5, 99.5, 100.0, 1000.0))
    if extra:
        spec.append(extra)
    return spec


class _Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeGet:
    """مسیر ← پاسخ. نخستین الگوی منطبق برنده است. هر درخواست ثبت می‌شود."""

    def __init__(self, routes: list[tuple[str, object]]):
        self.routes, self.calls = routes, []

    def __call__(self, url, params=None, **kw):
        key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        self.calls.append(key)
        for pat, payload in self.routes:
            if pat in key:
                if callable(payload):
                    payload = payload(params or {})
                return _Resp(payload)
        return _Resp({"code": "51001", "msg": "not found", "data": []}, 200)


# ═══════════════ جهان بازار ═══════════════

def test_exclusions_keep_real_tokens():
    assert P.exclude_reason("USDC") == "استیبل"
    assert P.exclude_reason("ETH3L") == "اهرمی"
    assert P.exclude_reason("WBTC") == "پیچیده‌شده"
    assert P.exclude_reason("STETH") == "پیچیده‌شده"
    assert P.exclude_reason("XAUT") == "طلا"
    for real in ("JUP", "WIF", "WLD", "STX", "SOL"):
        assert P.exclude_reason(real) is None, real
    assert P.exclude_reason("ریال") == "نماد غیر اسکی"


def _market(now=NOW):
    old = _ms(now - timedelta(days=400))
    return {
        "okx_spot": [
            {"instId": "BTC-USDT", "last": "80000", "open24h": "79000", "volCcy24h": "9e8"},
            {"instId": "AAA-USDT", "last": "102.2", "open24h": "100", "volCcy24h": "4000000"},
            {"instId": "SUM-USDT", "last": "1", "open24h": "1", "volCcy24h": "2000000"},
            {"instId": "USDC-USDT", "last": "1", "open24h": "1", "volCcy24h": "9e8"},
            {"instId": "NEW-USDT", "last": "5", "open24h": "4", "volCcy24h": "8000000"},
        ],
        "okx_inst": [
            {"instId": "AAA-USDT", "listTime": str(old), "state": "live"},
            {"instId": "SUM-USDT", "listTime": str(old), "state": "live"},
            {"instId": "NEW-USDT", "listTime": str(_ms(now - timedelta(days=10))), "state": "live"},
        ],
        "okx_funding": [
            {"instId": "AAA-USDT-SWAP", "fundingRate": "0.0001",
             "fundingTime": str(_ms(now)), "nextFundingTime": str(_ms(now) + 4 * HOUR_MS)},
        ],
        "gate_spot": [
            {"currency_pair": "SUM_USDT", "last": "1", "quote_volume": "2000000", "change_percentage": "0"},
            {"currency_pair": "BBB_USDT", "last": "3", "quote_volume": "5000000", "change_percentage": "2"},
            {"currency_pair": "HALT_USDT", "last": "3", "quote_volume": "9000000", "change_percentage": "2"},
        ],
        "gate_pairs": [
            {"id": "SUM_USDT", "base": "SUM", "quote": "USDT", "trade_status": "tradable", "buy_start": 0},
            {"id": "BBB_USDT", "base": "BBB", "quote": "USDT", "trade_status": "tradable",
             "buy_start": int((now - timedelta(days=5)).timestamp()), "st_tag": True},
            {"id": "HALT_USDT", "base": "HALT", "quote": "USDT", "trade_status": "untradable", "buy_start": 0},
        ],
        "gate_contracts": [
            {"name": "BBB_USDT", "funding_rate": "0.0002", "funding_interval": 3600,
             "quanto_multiplier": "10", "in_delisting": False},
        ],
    }


def test_universe_floor_is_per_venue_not_summed():
    uni, btc, warns = P.build_universe(_market(), 3_000_000, NOW)
    assert btc == 80000.0
    assert set(uni) == {"AAA", "NEW", "BBB"}          # SUM: دو تا ۲ میلیون جمع نمی‌شود
    assert uni["AAA"]["venue"] == "okx" and uni["BBB"]["venue"] == "gate"
    assert "BTC" not in uni and "USDC" not in uni and "HALT" not in uni


def test_funding_normalized_to_8h_and_labels():
    uni, _, _ = P.build_universe(_market(), 3_000_000, NOW)
    assert uni["AAA"]["funding_8h"] == pytest.approx(0.0002)      # بازه ۴ ساعته × ۲
    assert uni["BBB"]["funding_8h"] == pytest.approx(0.0016)      # بازه ۱ ساعته × ۸
    assert uni["BBB"]["deriv_venue"] == "gate" and uni["NEW"]["deriv_venue"] is None
    assert "برچسب ریسک گیت" in uni["BBB"]["labels"]


def test_pair_age_labels():
    uni, _, _ = P.build_universe(_market(), 3_000_000, NOW)
    assert "تازه‌فهرست" in uni["NEW"]["labels"]
    assert "فهرست تازه در اوکی‌اکس" in uni["NEW"]["labels"]
    assert "تازه‌فهرست" not in uni["AAA"]["labels"]
    assert "فهرست تازه در گیت" in uni["BBB"]["labels"]
    age, labels = P.pair_age({"okx": 400.0, "gate": 5.0})
    assert age == 400.0 and labels == ["فهرست تازه در گیت"]          # عمر بازار = قدیمی‌ترین
    assert P.pair_age({}) == (None, ["عمر نامعلوم"])


# ═══════════════ سنجه‌ها ═══════════════

def test_open_candle_dropped_okx_and_gate():
    f = P.okx_frame(okx_rows([100.0] * 5))
    assert len(f) == 6 and len(P.closed(f)) == 5 and P.closed(f)["qv"].max() == 100.0
    g = [[str(int(NOW.timestamp()) - 3600 * (3 - k)), "50", "1", "1", "1", "1", "5",
          "true" if k < 3 else "false"] for k in range(4)]
    gf = P.gate_spot_frame(g, 3600, NOW)
    assert len(P.closed(gf)) == 3 and P.closed(gf)["qv"].max() == 50.0
    fut = [{"t": int(NOW.timestamp()) - 3600 * (3 - k), "o": "1", "h": "1", "l": "1", "c": "1",
            "sum": "7"} for k in range(4)]
    assert len(P.closed(P.gate_fut_frame(fut, 3600, NOW))) == 3     # آخری هنوز باز است


def test_vol_z_window_and_formula():
    base = [100.0, 300.0] * 84                       # ۱۶۸ کندل پایه
    qv = [1e9] + base + [1000.0]                     # غول بیرون از پنجره پایه
    z, why = P.vol_z(qv, 168, 120)
    x = np.log1p(np.array(base))
    want = (math.log1p(1000.0) - x.mean()) / x.std(ddof=1)
    assert why is None and z == pytest.approx(want)


def test_vol_z_missing_is_not_zero():
    assert P.vol_z([100.0] * 50, 168, 120) == (None, "داده کم")
    assert P.vol_z([100.0] * 200, 168, 120) == (None, "داده ندارم")      # انحراف صفر
    assert P.vol_z([100.0, 200.0] * 100 + [float("nan")], 168, 120) == (None, "داده ندارم")


def test_recent_max_finds_spike_hours_ago():
    qv = [100.0, 200.0] * 90 + [5000.0, 100.0, 200.0]
    z, ago, why = P.z_recent_max(qv, 168, 120, 6)
    assert why is None and ago == 2 and z > 5


def test_ratio_shift_same_venue():
    spot = closed_frame([1000.0] * 200)
    perp = closed_frame([1000.0] * 176 + [2000.0] * 24)
    r = P.ratio_shift(spot, perp)
    assert r["why"] is None and r["shift"] == pytest.approx(math.log(2))
    assert P.ratio_shift(spot, None)["why"] == "قرارداد ندارد"
    assert P.ratio_shift(spot, closed_frame([1000.0] * 50))["why"] == "داده کم"


def test_oi_change_coin_units_and_open_point_dropped():
    top = NOW.replace(minute=0, second=0, microsecond=0)
    pts = [(_ms(top - timedelta(hours=h)), 120.0 if h == 1 else 100.0) for h in range(1, 30)]
    pts.append((_ms(top), 999.0))                    # ساعت جاری — باز، حذف
    r = P.oi_change(pts, NOW)
    assert r["why"] is None
    assert r["d24"] == pytest.approx(0.20) and r["d4"] == pytest.approx(0.20)
    assert P.oi_change(pts[:5], NOW)["why"] == "داده کم"


def test_abnormal_4h_candle():
    rows = [[0, 100.0, 105.0, 100.0, 104.0] for _ in range(126)]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    assert P.abnormal_4h(df)["flag"] is False
    df.loc[120, "high"] = 135.0                       # دامنه ۳۵٪ در برابر ۵٪ — ر۵۶
    out = P.abnormal_4h(df)
    assert out["flag"] is True and out["ratio"] == pytest.approx(7.0)
    assert P.abnormal_4h(df.iloc[:50])["why"] == "داده کم"


def test_flow_gate_inclusive_and_missing_not_zero():
    assert P.flow_signs({"z1h_rel": 2.0}) == ["حجم ساعتی"]
    assert P.flow_signs({"z1h": 5.0, "z1h_rel": 1.9}) == []          # دروازه روی z نسبی است
    assert P.flow_signs({"z4h_rel": 1.99, "d24": 0.15, "oi_usd": 2e6}) == ["بهره باز"]
    assert P.flow_signs({"shift": math.log(2)}) == ["نسبت قرارداد"]
    assert P.flow_signs({"z1h_rel": None, "z4h_rel": None, "d24": None, "shift": None}) == []


def test_oi_sign_needs_two_million_dollar_base():
    assert P.flow_signs({"d24": 0.50, "oi_usd": 1.9e6}) == []
    assert P.flow_signs({"d24": 0.50}) == []                          # کف نامعلوم، نشانه نه
    assert P.flow_signs({"d24": 0.15, "oi_usd": 2.0e6}) == ["بهره باز"]


def test_volume_spike_is_relative_to_btc_same_hours():
    spike = closed_frame([100.0, 200.0] * 90 + [8000.0])
    calm = closed_frame([100.0, 200.0] * 90 + [150.0])
    whole = P.rel_z(spike, spike, 168, 120, 6)                        # کل بازار تکان خورد
    assert whole["z"] > 5 and abs(whole["rel"]) < 1e-9
    alone = P.rel_z(spike, calm, 168, 120, 6)
    assert alone["rel"] > 2 and alone["rel"] == pytest.approx(alone["z"] - alone["btc_z"])
    none = P.rel_z(spike, None, 168, 120, 6)
    assert none["z"] > 5 and none["rel"] is None and none["why"] == "بیت‌کوین داده ندارد"


def test_leveraged_pump_pattern():
    # الگوی پامپ اهرمی نبض: فاندینگ بالا، بهره باز رو به رشد، قیمت رشد نکرده
    assert P.leveraged_pump(0.0003, 0.15, 0.0) is True
    assert P.leveraged_pump(0.0003, 0.15, 0.05) is False          # قیمت رشد کرده
    assert P.leveraged_pump(0.0001, 0.30, 0.0) is False
    assert P.leveraged_pump(None, 0.30, 0.0) is False


def test_extreme_funding_both_directions():
    assert P.crowd_label(0.0011) == "ازدحام لانگ"
    assert P.crowd_label(-0.0011) == "ازدحام شورت"
    assert P.crowd_label(0.001) is None and P.crowd_label(-0.001) is None   # «بالاتر از»
    assert P.crowd_label(None) is None


def test_flow_labels_never_mark_r54():
    row = {"funding_8h": -0.0149, "metrics": {"abn_flag": True, "d24": 6.8, "chg24_closed": 0.3,
                                              "vol_btc": 135.0}}
    assert P.flow_labels(row) == ["شمع غیرعادی", "ازدحام شورت"]
    assert all("ر۵۴" not in x for x in P.flow_labels(row))


def test_r54_is_a_column_only():
    assert P.r54(16_000_000, 80_000) == 200.0
    assert P.r54(1e6, None) is None and P.r54(None, 80_000) is None


# ═══════════════ ستاپ‌ها ═══════════════

def test_squeeze_pre_and_trigger_both_ways():
    pre = P.squeeze(daily(squeeze_spec()))
    assert pre["name"] == "الف‌۳" and pre["state"] == "pre"
    up = P.squeeze(daily(squeeze_spec((100.0, 115.0, 99.8, 114.0, 3000.0))))
    assert up["state"] == "trigger" and up["side"] == "long"
    dn = P.squeeze(daily(squeeze_spec((100.0, 100.2, 85.0, 86.0, 3000.0))))
    assert dn["state"] == "trigger" and dn["side"] == "short"
    assert P.squeeze(daily(base_osc(80, 90, 110))) is None
    assert pre["hi"] == 100.5 and pre["lo"] == 99.5 and pre["atr"] > 0


def test_squeeze_must_be_horizontal_not_a_falling_drift():
    # LTC، ۱۰ اکتبر: دامنه کم‌شونده در روند نزولی — فشردگی نیست
    spec = []
    for i in range(40):
        m = 70.0 if i % 2 == 0 else 90.0
        spec.append((m, m + 2, m - 2, m, 1000.0))
    for m in np.linspace(72.0, 64.0, 10):
        spec.append((m + 0.3, m + 0.5, m - 0.5, m - 0.3, 1000.0))
    assert P.squeeze(daily(spec)) is None
    spec.append((63.5, 64.0, 55.0, 56.0, 3000.0))
    assert P.squeeze(daily(spec)) is None                             # ماشه هم نه


def test_breakout_retest_trigger_pre_and_volume_killer():
    trig = P.breakout(daily(breakout_spec((101.2, 102.5, 100.8, 102.2, 1000))))
    assert trig["name"] == "الف‌۱" and trig["state"] == "trigger"
    assert trig["level"] == pytest.approx(100.15, abs=0.2)
    pre = P.breakout(daily(breakout_spec((103.5, 105, 103, 104.5, 1000))))
    assert pre["name"] == "الف‌۱" and pre["state"] == "pre"
    weak = P.breakout(daily(breakout_spec((101.2, 102.5, 100.8, 102.2, 1000), vol_mult=1.0)))
    assert weak == {"killed": "شکست بی‌حجم"}


def test_retest_measured_with_pre_breakout_volatility():
    # شکست با شمع غول‌آسا دامنه واقعی را باد می‌کند؛ کف ۱۰۳ «بازگشت به سطح ۱۰۰» نیست
    spec = base_osc(65)
    spec[20] = (96, 100.0, 95, 96, 1000)
    spec[40] = (96, 100.3, 95, 96, 1000)
    spec += [(96, 140, 95.5, 135, 5000), (135, 140, 120, 125, 1000), (125, 130, 110, 115, 1000),
             (115, 118, 105, 110, 1000), (104, 106, 103.0, 105.5, 1000)]
    assert P.breakout(daily(spec))["state"] == "pre"


def test_live_price_voids_stale_setup():
    sh = {"name": "ج‌۱", "side": "short", "state": "trigger", "level": 100.0}
    lo = {"name": "الف‌۱", "side": "long", "state": "trigger", "level": 100.0}
    box = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 100.0}
    box = dict(box, hi=100.0, lo=96.0, atr=2.0)
    keep, labels = P.live_check([sh, lo, box], 101.0)
    assert keep == [lo, box] and labels == ["شورت ج‌۱ باطل شد"]
    keep, labels = P.live_check([sh, lo, box], 99.0)
    assert keep == [sh, box] and labels == ["لانگ الف‌۱ باطل شد"]
    assert P.live_check([sh], None) == ([sh], [])


def test_squeeze_live_price_inside_or_breaking():
    box = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 100.0, "hi": 100.0,
           "lo": 96.0, "atr": 2.0}
    assert P.live_check([box], 98.0)[0] == [box]                      # درون محدوده
    assert P.live_check([box], 100.9)[0] == [box]                     # در حال شکستن
    keep, labels = P.live_check([box], 93.0)                          # بیرون، پایین
    assert keep == [] and labels == ["لانگ الف‌۳ باطل شد"]


def test_failed_breakout_is_short():
    out = P.breakout(daily(breakout_spec((99.5, 100, 97.5, 98, 1000))))
    assert out["name"] == "ج‌۱" and out["side"] == "short" and out["state"] == "trigger"


def test_pullback_precondition_only():
    df = daily(zigzag([(0, 100), (10, 95), (20, 106), (30, 101), (40, 112), (49, 110)]))
    out = P.pullback(df)
    assert out["name"] == "الف‌۲" and out["state"] == "pre" and out["side"] == "long"
    deep = daily(zigzag([(0, 100), (10, 95), (20, 106), (30, 101), (40, 112), (49, 102)]))
    assert P.pullback(deep) is None                  # اصلاح بیش از دو سوم موج — قاتل


def test_lower_high_after_lower_low():
    df = daily(zigzag([(0, 105), (10, 100), (20, 112), (30, 95), (40, 106), (49, 99)]))
    out = P.lower_high(df)
    assert out["name"] == "ج‌۲" and out["side"] == "short" and out["state"] == "trigger"
    up = daily(zigzag([(0, 95), (10, 100), (20, 106), (30, 102), (40, 112), (49, 105)]))
    assert P.lower_high(up) is None


def test_floor_break_r58_needs_three_touches_and_no_rise():
    spec = base_osc(70, 104, 106)
    for i in (15, 30, 45):
        spec[i] = (104, 105, 100.0, 104, 1000)
    spec += [(104, 104.5, 101, 101.5, 1000), (101.5, 102, 97, 97.5, 1000)]
    out = P.floor_break(daily(spec))
    assert out["name"] == "ر۵۸" and out["side"] == "short"
    risen = spec[:50] + [(m, m + 0.5, m - 0.5, m, 1000) for m in np.linspace(106, 130, 20)]
    risen.append((130, 130, 97, 97.5, 1000))
    assert P.floor_break(daily(risen)) is None                       # شکست پس از صعود — نه


# ═══════════════ رتبه، وتو، ال‌بانک ═══════════════

def _row(sym, setups=(), d_sup=1.0, d_res=1.0, signs=("حجم ساعتی",)):
    return {"symbol": sym, "venue": "okx", "price": 1.0, "setups": list(setups),
            "d_sup": d_sup, "d_res": d_res, "signs": list(signs), "metrics": {}, "labels": []}


def test_rank_groups_then_distance_without_score():
    rows = [
        _row("FLOW", d_sup=0.2),
        _row("PRE", [{"name": "الف‌۳", "side": "long", "state": "pre", "level": 1}], d_sup=1.2),
        _row("TRIG", [{"name": "الف‌۱", "side": "long", "state": "trigger", "level": 1}], d_sup=1.4),
        _row("TRIG2", [{"name": "الف‌۳", "side": "long", "state": "trigger", "level": 1}], d_sup=0.3),
        _row("LATE", [{"name": "الف‌۱", "side": "long", "state": "trigger", "level": 1}], d_sup=3.5),
        _row("NOLVL", d_sup=None),
        _row("SHRT", [{"name": "ج‌۱", "side": "short", "state": "trigger", "level": 1}], d_res=0.5),
    ]
    sec = P.rank(rows)
    assert [e["symbol"] for e in sec["long"]] == ["TRIG2", "TRIG", "PRE", "FLOW"]
    assert [e["symbol"] for e in sec["short"]] == ["SHRT"]
    assert [e["symbol"] for e in sec["late"]] == ["LATE"]
    assert [e["symbol"] for e in sec["nolevel"]] == ["NOLVL"]
    flat = json.dumps(sec, ensure_ascii=False)
    assert "score" not in flat and "امتیاز" not in flat


def test_after_pump_leaves_long_groups():
    trig = [{"name": "الف‌۱", "side": "long", "state": "trigger", "level": 1}]
    short = [{"name": "ج‌۱", "side": "short", "state": "trigger", "level": 1}]
    rows = [
        dict(_row("ABN", trig, d_sup=0.1), metrics={"abn_flag": True, "rs7": 10.0}),
        dict(_row("RS", trig, d_sup=0.2), metrics={"abn_flag": False, "rs7": 50.1}),
        dict(_row("EDGE", trig, d_sup=0.3), metrics={"abn_flag": False, "rs7": 50.0}),
        dict(_row("FLOWP", d_sup=None), metrics={"abn_flag": None, "rs7": 120.0}),
        dict(_row("SH", short, d_res=0.4), metrics={"abn_flag": True, "rs7": 90.0}),
    ]
    sec = P.rank(rows)
    assert [e["symbol"] for e in sec["long"]] == ["EDGE"]             # +۵۰ خودش «بالاتر» نیست
    assert [e["symbol"] for e in sec["afterpump"]] == ["ABN", "RS", "FLOWP"]
    assert [e["symbol"] for e in sec["short"]] == ["SH"]              # شورت دست نمی‌خورد
    assert sec["nolevel"] == []
    # دفتر نامزد: گروه خودش می‌ماند، بخش «پس از پامپ»
    led = {"entries": []}
    P.ledger_add(led, rows, sec, NOW)
    abn = next(e for e in led["entries"] if e["symbol"] == "ABN")
    assert abn["placements"] == [{"side": "long", "section": "afterpump", "group": 1,
                                  "setup": trig[0], "dist_atr": 0.1, "veto": None, "card": None}]


def test_weaker_than_btc_label_only_on_longs():
    long_ = dict(_row("LTC", d_sup=1.0), metrics={"rs7": -7.0})
    short_ = dict(_row("SH", [{"name": "ج‌۱", "side": "short", "state": "trigger", "level": 1}],
                       d_res=0.5), metrics={"rs7": -7.0})
    sec = P.rank([long_, short_])
    assert "ضعیف‌تر از بیت‌کوین" in sec["long"][0]["labels"]
    assert "ضعیف‌تر از بیت‌کوین" not in sec["short"][0]["labels"]
    assert "ضعیف‌تر از بیت‌کوین" not in long_["labels"]               # ردیف دست نمی‌خورد


def test_squeeze_ranked_by_distance_to_entry_trigger():
    def sq(sym, d_sup, hi):
        s = {"name": "الف‌۳", "side": "long", "state": "pre", "level": hi, "hi": hi, "lo": 90.0,
             "atr": 2.0}
        return dict(_row(sym, [s], d_sup=d_sup), price=100.0)
    far, near = sq("FAR", 0.1, 104.0), sq("NEAR", 1.0, 100.4)        # ۲.۰ و ۰.۲ دامنه واقعی
    sec = P.rank([far, near])
    assert [e["symbol"] for e in sec["long"]] == ["NEAR", "FAR"]
    assert sec["long"][0]["dist_atr"] == pytest.approx(0.2)


def test_incomplete_data_never_ranks_better():
    full = _row("FULL", [{"name": "الف‌۳", "side": "long", "state": "trigger", "level": 1}], d_sup=2.9)
    gap = _row("GAP", [{"name": "الف‌۳", "side": "long", "state": "trigger", "level": 1}], d_sup=None)
    sec = P.rank([gap, full])
    assert [e["symbol"] for e in sec["long"]] == ["FULL"]
    assert [e["symbol"] for e in sec["nolevel"]] == ["GAP"]


def test_veto_unknown_stays_veto_moves():
    sec = P.rank([_row("A", d_sup=0.1), _row("B", d_sup=0.2), _row("C", d_sup=0.3)])

    def fake(syms, get, now):
        v = {"A": {"status": "veto", "why": "پله 3.1٪"}, "B": {"status": "unknown", "why": "پوشش کوتاه"},
             "C": {"status": "pass", "why": "بی پله"}}
        return {s: v[s] for s in syms}, [], []
    notes = P.apply_veto(sec, fake, None, NOW)
    assert [e["symbol"] for e in sec["long"]] == ["B", "C"]
    assert [e["symbol"] for e in sec["veto"]] == ["A"]
    assert sec["long"][0]["veto"]["status"] == "unknown"
    assert notes == []


def test_lbank_labels():
    assert P.lbank_label("AAA", {"AAA"}) == "هست"
    assert P.lbank_label("ZZZ", {"AAA"}) == "در LBank نیست"
    assert P.lbank_label("AAA", None) == "نامعلوم"
    assert P.lbank_pairs({"result": "true", "data": ["aaa_usdt", "bbb_btc"]}) == {"AAA"}
    assert P.lbank_pairs(None) is None


# ═══════════════ اجرای کامل بی‌شبکه ═══════════════

def _routes():
    m = _market()
    spike = [100.0, 200.0] * 90 + [8000.0]
    flat = [100.0, 200.0] * 100
    gate_1h = [[str(int(NOW.timestamp()) // 3600 * 3600 - 3600 * (len(flat) - k)), str(v), "3", "3", "3",
                "3", "1", "true"] for k, v in enumerate(flat)]
    top = NOW.replace(minute=0, second=0, microsecond=0)
    rubik = [[str(_ms(top - timedelta(hours=h))), "0", str(100.0 if h > 1 else 100.0), "0"]
             for h in range(0, 48)]
    stats = [{"time": int((top - timedelta(hours=h)).timestamp()), "open_interest": 10}
             for h in range(47, -1, -1)]
    fut = [{"t": int(NOW.timestamp()) // 3600 * 3600 - 3600 * (200 - k), "o": "3", "h": "3", "l": "3",
            "c": "3", "sum": "150"} for k in range(200)]
    ok = lambda d: {"code": "0", "data": d}                           # noqa: E731
    return [
        ("okx.com/api/v5/market/tickers?instType=SPOT", ok(m["okx_spot"])),
        ("okx.com/api/v5/public/instruments", ok(m["okx_inst"])),
        ("okx.com/api/v5/public/funding-rate", ok(m["okx_funding"])),
        ("open-interest-history", ok(rubik)),
        ("instId=AAA-USDT-SWAP", ok(okx_rows(flat))),
        ("bar=4H&instId=AAA-USDT", ok(okx_rows([100.0, 200.0] * 50, bar_h=4))),
        ("bar=1H&instId=AAA-USDT", ok(okx_rows(spike, close=2.0))),
        ("bar=1H&instId=BTC-USDT", ok(okx_rows(flat, close=80000.0))),
        ("bar=4H&instId=BTC-USDT", ok(okx_rows([100.0, 200.0] * 50, bar_h=4))),
        ("bar=4H&instId=NEW-USDT", ok(okx_rows([100.0, 200.0] * 50, bar_h=4))),
        ("bar=1H&instId=NEW-USDT", ok(okx_rows(flat, close=5.0))),
        ("gateio.ws/api/v4/spot/tickers", m["gate_spot"]),
        ("gateio.ws/api/v4/spot/currency_pairs", m["gate_pairs"]),
        ("gateio.ws/api/v4/futures/usdt/contracts", m["gate_contracts"]),
        ("futures/usdt/candlesticks", fut),
        ("contract_stats", stats),
        ("spot/candlesticks", gate_1h),
        ("lbkex.com/v2/currencyPairs.do", {"result": "true", "data": ["aaa_usdt"]}),
    ]


class _Hist:
    def __init__(self):
        self.calls = []

    def __call__(self, sym, tf, a, b):
        self.calls.append((sym, tf, a))

        class S:
            venue = "okx"
            df = pd.DataFrame({"ts": [pd.Timestamp(a)], "close": [2.5], "confirm": [1]})
        return S()


def _run(tmp_path, monkeypatch, extra=(), now=NOW, hist=None):
    bo = breakout_spec((101.2, 102.5, 100.8, 102.2, 1000))          # الف‌۱ با بازآزمایی
    monkeypatch.setattr(P, "daily_candles", lambda net, base, venue: daily(bo, open_candle=True))
    get = FakeGet(_routes())

    def veto(syms, g, n):
        return {s: {"status": "unknown", "why": "پوشش کوتاه"} for s in syms}, [], []
    argv = ["--out", str(tmp_path / "PUMP.md"), "--json", str(tmp_path / "pump.json"),
            "--ledger", str(tmp_path / "pump_ledger.json"), *extra]
    rc = P.main(argv, get=get, now=now, veto=veto, history=hist or _Hist(), sleep=lambda s: None)
    return rc, get


def test_main_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc, get = _run(tmp_path, monkeypatch)
    assert rc == 0
    js = json.loads((tmp_path / "pump.json").read_text(encoding="utf-8"))
    assert js["universe_n"] == 3 and js["gate_n"] == 1                # فقط AAA جهش دارد
    cands = js["sections"]["long"]
    assert [c["symbol"] for c in cands] == ["AAA"]
    c = cands[0]
    assert c["status"] == "آزمون‌نشده" and c["lbank"] == "هست"
    assert c["setup"]["name"] == "الف‌۱" and c["why"]
    assert c["veto"]["status"] == "unknown"
    assert js["requests"]["okx"] > 0 and js["requests"]["gate"] > 0 and js["requests"]["lbank"] == 1
    md = (tmp_path / "PUMP.md").read_text(encoding="utf-8")
    assert md.startswith(f"# اسکنر پامپ رادار {R.FRAMEWORK}")
    assert "مجوز ورود نیست" in md and "آزمون‌نشده" in md and "| AAA |" not in md
    assert "زیر کف ر۵۴" not in md and "پس از پامپ — دنبالش نکن" in md
    assert "امروز 0 کارت، 1 نامزد" in md and "۳ تا ۸ نامزد" in md
    assert c["card"]["ok"] is False and c["card"]["why"] == "کارت ندارد — نسبت کافی نیست"
    assert "**AAA**" in md
    # اسکنر معامله نمی‌کند — هیچ فایل دفتر موقعیتی ساخته نمی‌شود
    for f in ("holdings.json", "watch.json", "radar_journal.json", "radar_optcost.json"):
        assert not (tmp_path / f).exists()


def test_ledger_records_every_gate_passer_once_per_day_and_fills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run(tmp_path, monkeypatch)
    _run(tmp_path, monkeypatch, now=NOW + timedelta(hours=2))          # همان روز — تکرار نه
    led = json.loads((tmp_path / "pump_ledger.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in led["entries"]] == ["2026-10-10:AAA"]
    e = led["entries"][0]
    assert e["price"] == 102.2 and e["placements"][0]["setup"]["name"] == "الف‌۱"
    assert "z1h" in e["metrics"] and e["prices"] == {"h24": None, "d7": None}
    card = e["placements"][0]["card"]
    assert set(card) >= {"entry", "stop", "target", "rr", "ok"}
    ctl = led["controls"]
    assert len(ctl) == 2 and set(ctl[0]["prices"]) == {"AAA", "NEW", "BBB"}
    assert ctl[0]["prices"]["BBB"] == {"price": 3.0, "venue": "gate"}
    h = _Hist()
    _run(tmp_path, monkeypatch, now=NOW + timedelta(days=1, hours=1), hist=h)
    led = json.loads((tmp_path / "pump_ledger.json").read_text(encoding="utf-8"))
    first = led["entries"][0]
    assert first["prices"]["h24"]["close"] == 2.5 and first["prices"]["d7"] is None
    assert [x[0] for x in h.calls] == ["AAA"]


def test_out_must_be_a_file_not_a_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "PUMP.md").mkdir()
    rc, _ = _run(tmp_path, monkeypatch)
    assert rc == 2


def test_market_failure_exits_3(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    get = FakeGet([])
    rc = P.main(["--out", str(tmp_path / "x.md"), "--json", str(tmp_path / "x.json"), "--no-ledger"],
                get=get, now=NOW, sleep=lambda s: None)
    assert rc == 3 and not (tmp_path / "x.json").exists()


# ═══════════════ کارت معامله ═══════════════

BUDGET = {"band": {"name": "محتاط", "cap": 4.0, "mult": 0.5}, "total": 10_000.0, "free_pct": 4.0,
          "note": "آزمون"}


def _cand(setup, price, side="long", lbank="هست", levels=(), metrics=None, funding=None):
    return {"symbol": "X", "side": side, "setup": setup, "price": price, "lbank": lbank,
            "levels": list(levels), "metrics": metrics or {}, "funding_8h": funding,
            "atr_d": setup.get("atr") if setup else None}


def test_card_squeeze_double_height_is_exactly_two_and_rejected():
    s = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 110.0, "hi": 110.0, "lo": 100.0,
         "atr": 4.0}
    c = P.make_card(_cand(s, 105.0, levels=[130.0]), BUDGET)
    assert c["entry"] == 110.0 and c["stop"] == 100.0 and c["target"] == 130.0
    assert c["rr_gross"] == pytest.approx(2.0) and c["rr"] < 2.0
    assert c["ok"] is False and c["why"] == "کارت ندارد — نسبت کافی نیست"


def test_card_squeeze_next_level_target_grade_b_and_size():
    s = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 110.0, "hi": 110.0, "lo": 100.0,
         "atr": 4.0}
    c = P.make_card(_cand(s, 105.0, levels=[150.0], metrics={"d24": 0.2}), BUDGET)
    cost = 110.0 * P.RT_COST
    assert c["target"] == 150.0
    assert c["rr"] == pytest.approx((40.0 - cost) / (10.0 + cost))
    assert c["ok"] is True and c["grade"] == "ب" and c["qmult"] == 1.5
    assert c["risk_pct"] == pytest.approx(2.0 * 0.5 * 1.5)            # ۲٪ × رژیم × کیفیت
    assert c["risk_usd"] == pytest.approx(150.0)
    assert c["qty"] == pytest.approx(150.0 / (10.0 + cost))
    assert c["invalid"] and c["trigger"]


def test_card_size_capped_by_free_budget_and_stale_regime():
    s = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 110.0, "hi": 110.0, "lo": 100.0,
         "atr": 4.0}
    tight = dict(BUDGET, free_pct=0.5)
    assert P.make_card(_cand(s, 105.0, levels=[150.0], metrics={"d24": 0.2}), tight)["risk_pct"] == 0.5
    stale = P.make_card(_cand(s, 105.0, levels=[150.0], metrics={"d24": 0.2}), None)
    assert stale["ok"] is True and stale["risk_pct"] is None and "رژیم" in stale["size_why"]


def test_long_card_needs_lbank_short_card_is_futures():
    s = {"name": "الف‌۳", "side": "long", "state": "pre", "level": 110.0, "hi": 110.0, "lo": 100.0,
         "atr": 4.0}
    c = P.make_card(_cand(s, 105.0, lbank="در LBank نیست", levels=[150.0]), BUDGET)
    assert c["ok"] is False and c["why"] == "کارت ندارد — در LBank نیست"
    sh = {"name": "ج‌۱", "side": "short", "state": "trigger", "level": 100.0, "fail_high": 106.0,
          "range_low": 70.0, "atr": 2.0}
    c = P.make_card(_cand(sh, 98.0, side="short", lbank="در LBank نیست",
                          metrics={"d24": 0.2}, funding=0.002), BUDGET)
    assert c["ok"] is True and c["tag"] == "فیوچرز"
    assert c["entry"] == 98.0 and c["stop"] == pytest.approx(106.5) and c["target"] == 70.0
    assert c["grade"] == "ب"


def test_no_card_without_numeric_trigger():
    for s in ({"name": "الف‌۲", "side": "long", "state": "pre", "level": 95.0, "atr": 2.0},
              {"name": "ر۵۸", "side": "short", "state": "trigger", "level": 95.0, "atr": 2.0}):
        c = P.make_card(_cand(s, 100.0, side=s["side"]), BUDGET)
        assert c["ok"] is False and c["why"].startswith("کارت ندارد")
    assert P.make_card(_cand(None, 100.0), BUDGET)["why"] == "کارت ندارد — ستاپ نام‌دار نیست"


def test_budget_from_holdings_same_method_as_book():
    h = {"positions": [], "cash": [{"asset": "USDT", "qty": 1000}]}
    band = {"name": "محتاط", "cap": 4.0, "mult": 0.5, "maxpos": 3, "stable": 25}
    b = P.budget_from(h, {}, band)
    assert b["total"] == 1000.0 and b["free_pct"] == pytest.approx(4.0) and b["band"] == band
