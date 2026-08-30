#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آزمون باگ شماره ۸ — بسته روزانه کهنه و حذف بی‌صدا در radar_levels.py

دو ادعا آزمون می‌شود، هر دو بدون شبکه:

    ۱ — قیمت باید از کندل زنده بیاید، ساختار از کندل‌های بسته.
        نسخه معیوب کندل باز را دور می‌ریخت و «قیمت» تا ۲۸ ساعت کهنه می‌شد
        (زی‌کش: ۶۵۳.۹۹ به‌جای ۸۰۲.۳۱).

    ۲ — نمادی که نسبت ندارد باید در گزارش جدا بیاید، نه حذف بی‌صدا.
        نسخه معیوب ETH و HYPE را که در کشف قیمت بودند اصلاً چاپ نمی‌کرد.
        قانون مادر داده: «داده ندارم» گزارش‌شدنی است، نه حذف‌شدنی.

اجرا:
    python tests/test_radar_levels.py
"""

import math
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import radar_levels as RL

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ─────────────── داده مصنوعی ───────────────

def synth_daily(n: int = 120, live_close: float = 150.0) -> pd.DataFrame:
    """n کندل بسته با نوسان ملایم حول ۱۰۰، به‌علاوه یک کندل باز با جهش شدید."""
    rng = np.random.default_rng(7)
    ts = pd.date_range("2026-01-01", periods=n + 1, freq="D", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    rows = {
        "ts": ts,
        "open": np.append(close - 0.2, close[-1]),
        "high": np.append(close + 1.0, live_close + 1.0),
        "low": np.append(close - 1.0, close[-1] - 1.0),
        "close": np.append(close, live_close),
        "vol": np.full(n + 1, 1000.0),
        "confirm": np.append(np.ones(n), 0.0),
    }
    return pd.DataFrame(rows)


def fake_okx_response(n_closed: int = 99):
    """پاسخ ساختگی اوکی‌اکس: جدید به قدیم، جدیدترین کندل باز است (تأیید صفر)."""
    base_ts = 1_700_000_000_000
    day = 86_400_000
    rows = []
    for i in range(n_closed + 1):
        ts = base_ts - i * day
        confirm = "0" if i == 0 else "1"
        px = f"{100 + i}"
        rows.append([str(ts), px, px, px, px, "10", "10", "1000", confirm])

    class R:
        def json(self):
            return {"code": "0", "data": rows}

    class Empty:
        def json(self):
            return {"code": "0", "data": []}

    calls = {"n": 0}

    def getter(url, params=None, timeout=20):
        calls["n"] += 1
        return R() if calls["n"] == 1 else Empty()

    return getter


# ─────────────── آزمون ۱ — کندل زنده دور ریخته نشود ───────────────

def test_okx_candles_keeps_live() -> None:
    with mock.patch.object(RL.requests, "get", new=fake_okx_response()):
        df = RL.okx_candles("TST-USDT", "1D", 100)
    check("واکشی: چارچوب داده برگشت", df is not None)
    if df is None:
        return
    check("واکشی: کندل باز حذف نشده", int((df["confirm"] == 0).sum()) == 1,
          f"تعداد کندل باز در خروجی: {int((df['confirm'] == 0).sum())}")
    check("واکشی: آخرین سطر همان کندل زنده است",
          float(df["close"].iloc[-1]) == 100.0)


# ─────────────── آزمون ۲ — قیمت زنده، ساختار بسته ───────────────

def test_assess_price_fresh_structure_closed() -> None:
    df = synth_daily(n=120, live_close=150.0)
    closed = df[df["confirm"] == 1].reset_index(drop=True)

    a = RL.assess("TST", df)

    check("ارزیابی: قیمت از کندل زنده", a.price == 150.0,
          f"قیمت گزارش‌شده: {a.price}")
    check("ارزیابی: شمار کندل فقط بسته‌ها", a.n_bars == len(closed),
          f"n_bars={a.n_bars}، بسته‌ها={len(closed)}")

    expected_atr = float(RL.atr_wilder(closed).iloc[-1])
    check("ارزیابی: دامنه روزانه بدون کندل باز", math.isclose(a.atr, expected_atr),
          f"atr={a.atr}، انتظار={expected_atr}")


# ─────────────── آزمون ۳ — گزارش هیچ نمادی را بی‌صدا حذف نکند ───────────────

def test_report_includes_all_symbols() -> None:
    full = RL.Assessment(symbol="GOOD", price=100.0, atr=2.0, trend="صعودی",
                         verdict="نزدیک سطح", dist_sup_atr=1.0, rr=2.5)
    full.support = RL.Level(price=98.0, touches=3, last_idx=50, kind="حمایت")
    full.resistance = RL.Level(price=105.0, touches=2, last_idx=40, kind="مقاومت")

    disco = RL.Assessment(symbol="DISCO", price=999.0, atr=5.0, trend="صعودی",
                          verdict="کشف قیمت — بالای همه سطوح")
    nodata = RL.Assessment(symbol="NODATA", verdict="بدون داده")

    txt = RL.report([full, disco, nodata], min_rr=2.0)

    check("گزارش: نماد با نسبت هست", "GOOD" in txt)
    check("گزارش: نماد در کشف قیمت حذف نشده", "DISCO" in txt)
    check("گزارش: نماد بدون داده حذف نشده", "NODATA" in txt)


if __name__ == "__main__":
    test_okx_candles_keeps_live()
    test_assess_price_fresh_structure_closed()
    test_report_includes_all_symbols()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} آزمون شکست: " + "، ".join(FAILS))
        sys.exit(1)
    print("✅ همه آزمون‌های radar_levels گذشتند.")
