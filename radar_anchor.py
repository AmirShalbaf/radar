#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_anchor.py — لنگر کندل وقت جهانی، تنها منبع
=================================================

یافته نشست ۳ (رویداد ۳۵): اوکی‌اکس با 1D و 1W پیش‌فرض بر پایه وقت هنگ‌کنگ
می‌بندد — روزانه 16:00 UTC، هفتگی یکشنبه 16:00 UTC — و گیت با 1d و 7d بر پایه
وقت جهانی. پس «بسته روزانه» در مخزن یک لحظه نبود و با افتادن به صرافی دوم
۸ ساعت جابه‌جا می‌شد.

تعریف قطعی، نشست ۳ب:
    روزانه    باز شدن ۰۰:۰۰ UTC
    هفتگی     باز شدن دوشنبه ۰۰:۰۰ UTC — هفته دوشنبه تا یکشنبه
    چهارساعته باز شدن روی مضرب ۴ ساعت از ۰۰:۰۰ UTC. ۸ ساعت مضرب ۴ است، پس
              مرز در هر دو لنگر یکی است و نام درخواستی عوض نشد.
    یک ساعته  باز شدن سر ساعت — نشست ۷، فقط radar_history.py
    ۱۵ دقیقه  باز شدن روی مضرب ۱۵ دقیقه — نشست ۷، فقط radar_history.py

سنجش زنده ایستگاه ۱ نشست ۳ب، ۲۶ سپتامبر ۲۰۲۶: 1Dutc و 1Wutc اوکی‌اکس روی
هر دو نقطه دسترسی candles و history-candles، گیت، بایننس و بای‌بیت همه با
همین تعریف. کوکوین روزانه ۰۰:۰۰ است ولی هفتگی‌اش پنجشنبه ۰۰:۰۰ — از جدول
حذف شد، چون کلاسی هم نداشت.

کندلی که لنگرش با این تعریف نمی‌خواند رد و اعلام می‌شود. هرگز بازگشت
بی‌صدا به لنگر هنگ‌کنگ؛ هیچ لنگر درستی در دسترس نبود یعنی «داده ندارم».

فقط کتابخانه استاندارد — هم‌الگوی radar_text.py — تا radar_levels.py،
radar_watch.py و radar_positions.py بی‌آنکه استقلالشان بشکند ایمپورتش کنند.
"""
from __future__ import annotations

import numbers
from datetime import datetime, timezone

UTC = timezone.utc

# نام درخواستی هر صرافی برای نام داخلی تایم‌فریم. فقط لنگر وقت جهانی.
# radar_fetch3.BAR همین شیء است؛ مسیرهای تک‌صرافی از همین ردیف‌ها می‌خوانند.
BAR = {
    "okx":     {"1D": "1Dutc", "4H": "4H",  "1W": "1Wutc"},
    "binance": {"1D": "1d",    "4H": "4h",  "1W": "1w"},
    "bybit":   {"1D": "D",     "4H": "240", "1W": "W"},
    "gate":    {"1D": "1d",    "4H": "4h",  "1W": "7d"},
}

# کندل آزاد radar_history.py — نشست ۷. جدول BAR بالا جدول موتور است و آزمون
# قفلش کرده؛ اینجا همان ردیف‌ها به‌علاوه ۱۵ دقیقه و یک ساعت. لنگر این دو در هر
# لنگر روزانه‌ای یکی است، پس نام درخواستی همان نام عادی صرافی است.
HISTORY_BAR = {
    "okx":  {**BAR["okx"],  "15m": "15m", "1H": "1H"},
    "gate": {**BAR["gate"], "15m": "15m", "1H": "1h"},
}

# طول هر تایم‌فریم به ثانیه
SECONDS = {"15m": 900, "1H": 3_600, "4H": 14_400, "1D": 86_400, "1W": 604_800}

# متن انتظار هر تایم‌فریم در پیام رد
EXPECT = {"1D": "۰۰:۰۰ UTC", "4H": "مضرب ۴ ساعت از ۰۰:۰۰ UTC", "1W": "دوشنبه ۰۰:۰۰ UTC",
          "15m": "مضرب ۱۵ دقیقه", "1H": "سر ساعت"}

# سطر لنگر در گزارش‌ها — یک متن، نه چند نسخه دستی
ANCHOR_LINE = ("لنگر کندل: روزانه ۰۰:۰۰ UTC، هفتگی دوشنبه ۰۰:۰۰ UTC — اوکی‌اکس 1Dutc و "
               "1Wutc، گیت 1d و 7d. کندل با لنگر دیگر رد می‌شود.")


def to_utc(t) -> datetime:
    """
    زمان باز شدن کندل به وقت جهانی. عدد یعنی میلی‌ثانیه یونیکس — قالب اوکی‌اکس.
    زمان بی‌منطقه خطاست: لنگرش را نمی‌شود دانست.
    """
    # numbers.Real عدد نامپای را هم می‌گیرد؛ int ساده np.int64 را نمی‌گیرد
    if isinstance(t, numbers.Real) and not isinstance(t, bool):
        return datetime.fromtimestamp(float(t) / 1000, UTC)
    if not isinstance(t, datetime):
        raise ValueError(f"زمان باز شدن کندل نامعتبر: {t!r}")
    if t.tzinfo is None:
        raise ValueError(f"زمان باز شدن کندل منطقه زمانی ندارد: {t!r}")
    return t.astimezone(UTC)


def anchor_ok(t, bar: str) -> bool:
    """آیا زمان باز شدن این کندل روی لنگر وقت جهانی تایم‌فریمش است؟"""
    if bar not in EXPECT:
        raise ValueError(f"تایم‌فریم ناشناخته برای لنگر: {bar!r}")
    u = to_utc(t)
    if bar == "15m":
        return u.minute % 15 == 0 and (u.second, u.microsecond) == (0, 0)
    if (u.minute, u.second, u.microsecond) != (0, 0, 0):
        return False
    if bar == "1H":
        return True
    if bar == "1D":
        return u.hour == 0
    if bar == "4H":
        return u.hour % 4 == 0
    return u.weekday() == 0 and u.hour == 0


def off_anchor(opens, bar: str) -> list[datetime]:
    """زمان‌های باز شدنی که لنگرشان نادرست است، به وقت جهانی."""
    return [to_utc(t) for t in opens if not anchor_ok(t, bar)]


def reject_message(where: str, bar: str, bad: list[datetime]) -> str:
    """پیام رد، یک قالب برای همه مسیرها."""
    more = f" — {len(bad)} کندل" if len(bad) > 1 else ""
    return (f"{where}: لنگر نادرست — باز شدن {bad[0].isoformat()} "
            f"{EXPECT[bar]} نیست{more}. کندل رد شد؛ لنگر هنگ‌کنگ جانشین نمی‌شود")


def check(opens, bar: str, where: str) -> str:
    """پیام رد، یا رشته خالی اگر لنگر همه کندل‌ها درست است."""
    bad = off_anchor(opens, bar)
    return reject_message(where, bar, bad) if bad else ""
