#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_budget.py — جدول بودجه رژیم، تنها منبع اصلی
=================================================

پیش از نشست ۲ رادار ۷ این جدول دو نسخه داشت — radar_book.py و
radar_size.py — و radar_regime.py سومی می‌شد. متنی که در چند جا نوشته
شود، دیر یا زود از هم جدا می‌افتد (رویداد ۲۲ در STATE.md). حالا سبد،
اندازه و رژیم هر سه از همین‌جا می‌خوانند.

فقط کتابخانه استاندارد — تا استقلال radar_book.py و radar_size.py
نشکند. آزمون tests/test_budget.py این را قفل می‌کند.

قاعده مرز: روی مرز دقیق، **باند پایین‌تر** — محافظه‌کارانه. امتیاز
دقیقاً ‎+0.50 «سازنده» است، نه «انبساطی». پیش از این `>=` بود.
"""
from __future__ import annotations

import math

# (کف انحصاری، نام، سقف ریسک باز٪، ضریب اندازه، حداکثر پوزیشن هم‌جهت، هدف ذخیره استیبل٪)
# کف انحصاری است: امتیاز باید **بزرگ‌تر** از کف باشد. ردیف آخر کف ندارد.
BANDS = (
    (0.50, "انبساطی", 8.0, 1.00, 5, 10),
    (0.00, "سازنده", 6.0, 0.75, 4, 15),
    (-0.50, "محتاط", 4.0, 0.50, 3, 25),
    (-1.20, "انقباضی", 2.5, 0.30, 2, 40),
    (None, "بحرانی", 1.5, 0.20, 1, 55),
)


def regime_band(score: float) -> dict:
    """
    ردیف بودجه برای امتیاز رژیم.

    امتیاز پوچ یا بی‌نهایت خطای صریح می‌دهد. پیش از این `--regime nan`
    از همه مقایسه‌ها رد می‌شد و بی‌صدا «بحرانی» می‌گرفت.
    """
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score)):
        raise ValueError(f"امتیاز رژیم عدد متناهی نیست: {score!r}")
    for floor, name, cap, mult, maxpos, stable in BANDS:
        if floor is None or score > floor:
            return {"name": name, "cap": cap, "mult": mult,
                    "maxpos": maxpos, "stable": stable}
    raise AssertionError("ردیف آخر جدول بودجه باید کف نداشته باشد")


# ترتیب باندها از محافظه‌کارترین به بازترین
BAND_ORDER = tuple(name for _, name, *_ in reversed(BANDS))


def band_by_name(name: str) -> dict:
    """ردیف بودجه از نام باند — عددها همیشه از همین جدول، نه از فایل."""
    for _, n, cap, mult, maxpos, stable in BANDS:
        if n == name:
            return {"name": n, "cap": cap, "mult": mult, "maxpos": maxpos, "stable": stable}
    raise ValueError(f"باند ناشناخته: {name!r}")


# ── هیسترزیس اندازه‌گیری دفتر معامله — تصمیم ک۳۲، ۲۵ سپتامبر ۲۰۲۶ ──
#
# پایین‌آمدن باند فوری؛ بالا رفتن فقط پس از سه روز متوالی در باند تازه.
# اجرا: بالا رفتن وقتی مجاز است که سه روز **تقویمی پیاپی** — امروز و دو روز
# قبل — همه بالای باند مؤثر فعلی باشند؛ آن‌وقت به کمترین باند آن سه روز
# می‌رود. روز جاافتاده یعنی «پیاپی نیست» — بالا رفتن ممنوع، محافظه‌کارانه.
# فقط برای اندازه‌گیری دفتر معامله؛ هدف ذخیره دفتر موقعیت باند خام روز است.
HYSTERESIS_UP_DAYS = 3


def trade_band(days: list) -> str:
    """
    باند مؤثر دفتر معامله از توالی (تاریخ، باند خام) به ترتیب زمان؛ آخری
    امروز است. روز نخست تاریخچه باند خام خودش را می‌گیرد.
    """
    if not days:
        raise ValueError("تاریخچه باند خالی است")
    rank = BAND_ORDER.index
    eff = days[0][1]
    rank(eff)                                         # نام ناشناخته: ValueError
    for k in range(1, len(days)):
        b = days[k][1]
        if rank(b) <= rank(eff):
            eff = b                                   # پایین‌آمدن یا ماندن: فوری
            continue
        win = days[k - HYSTERESIS_UP_DAYS + 1: k + 1] if k >= HYSTERESIS_UP_DAYS - 1 else []
        consecutive = (len(win) == HYSTERESIS_UP_DAYS and
                       all((win[i + 1][0] - win[i][0]).days == 1 for i in range(len(win) - 1)))
        if consecutive:
            low = min((w[1] for w in win), key=rank)
            if rank(low) > rank(eff):
                eff = low
    return eff
