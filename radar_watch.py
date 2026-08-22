#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_watch.py — پایشگر زنده سطوح و هشدار، رادار ۶.۱
======================================================

مسئله‌ای که حل می‌کند
---------------------
تا ۶.۰ همه اسکریپت‌ها **عکس لحظه‌ای** می‌گرفتند: اجرا می‌کردی، عدد می‌دیدی،
تمام. هیچ چیزی بین دو اجرا اتفاق نمی‌افتاد.

ولی سه رویداد مهم‌ترین رویدادهای رادارند و هیچ‌کدام منتظر اجرای دستی نمی‌مانند:

    ۱) نقض ابطال ساختاری با بسته روزانه   ← تنها ماشه بدون استثنا در کل رادار
    ۲) پرشدن پله نردبان ورود              ← سفارش در انتظار فعال شد
    ۳) رسیدن به هدف                        ← نردبان خروج فعال می‌شود

این اسکریپت آن سه را زنده پایش می‌کند.

دو حالت اجرا
------------
    یک‌بار (برای گردش‌کار گیت‌هاب، هر ۱۵ دقیقه):
        python radar_watch.py --once

    حلقه محلی (روی کامپیوتر خودت):
        python radar_watch.py --loop 300

قانون بسته روزانه
-----------------
ابطال **فقط** با بسته‌شدن کندل روزانه سنجیده می‌شود، نه با سایه.
این اسکریپت آن قانون را رعایت می‌کند: برای ابطال، کندل روزانه بسته‌شده
را می‌خواند، نه قیمت لحظه‌ای. برای پله ورود و هدف، قیمت لحظه‌ای مبناست
چون آن‌ها سفارش‌اند، نه حکم ساختاری.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("نیاز به requests: pip install requests")
    sys.exit(1)

VERSION = "6.1"
UTC = timezone.utc
OKX = "https://www.okx.com"
WATCH_FILE = "watch.json"
STATE_FILE = "watch_state.json"

SAMPLE = {
    "_راهنما": "هر مورد یک پوزیشن یا یک ستاپ در انتظار است",
    "items": [
        {
            "symbol": "ZEC",
            "side": "long",
            "invalidation": 480.43,
            "ladder": [515.0, 500.0, 487.0],
            "targets": [575.0, 620.0],
            "note": "پوزیشن اسپات باز — رکورد کالیبراسیون ۱"
        },
        {
            "symbol": "BTC",
            "side": "long",
            "invalidation": None,
            "ladder": [],
            "targets": [],
            "alerts": [70000.0, 60000.0],
            "note": "فقط هشدار قیمتی"
        }
    ]
}


# ─────────────────────── داده ───────────────────────

def ticker(symbol: str) -> float | None:
    """قیمت لحظه‌ای. برای پله ورود، هدف و هشدار قیمتی."""
    try:
        r = requests.get(f"{OKX}/api/v5/market/ticker",
                         params={"instId": f"{symbol.upper()}-USDT"}, timeout=15)
        j = r.json()
        if j.get("code") == "0" and j.get("data"):
            return float(j["data"][0]["last"])
    except Exception:
        pass
    return None


def last_closed_daily(symbol: str) -> tuple[float, str] | None:
    """
    بسته آخرین کندل روزانه **کامل‌شده**.

    اوکی‌اکس کندل جاری ناتمام را هم برمی‌گرداند. آن را کنار می‌گذاریم،
    چون قانون رادار می‌گوید سایه شکست نیست — فقط بسته معتبر است.
    """
    try:
        r = requests.get(f"{OKX}/api/v5/market/candles",
                         params={"instId": f"{symbol.upper()}-USDT",
                                 "bar": "1D", "limit": "3"}, timeout=15)
        j = r.json()
        if j.get("code") != "0" or len(j.get("data", [])) < 2:
            return None
        rows = sorted(j["data"], key=lambda x: int(x[0]))
        now_ms = int(time.time() * 1000)
        for row in reversed(rows):
            start = int(row[0])
            if now_ms - start >= 86_400_000:      # کندل تمام شده
                day = datetime.fromtimestamp(start / 1000, UTC).strftime("%Y-%m-%d")
                return float(row[4]), day
    except Exception:
        pass
    return None


# ─────────────────────── وضعیت ───────────────────────

def load_json(path: str, default: dict) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def notify(msg: str, quiet: bool = False) -> None:
    """چاپ + ارسال تلگرام در صورت وجود کلید."""
    if not quiet:
        print(msg)
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": msg}, timeout=15)
    except Exception as e:
        print(f"  ارسال تلگرام ناموفق: {e}")


# ─────────────────────── پایش ───────────────────────

def check_item(it: dict, state: dict) -> list[str]:
    """یک مورد را می‌سنجد و فهرست هشدارهای تازه را برمی‌گرداند."""
    sym = it["symbol"].upper()
    side = it.get("side", "long")
    fired: list[str] = []
    st = state.setdefault(sym, {})

    px = ticker(sym)
    if px is None:
        return [f"⚠️ {sym} — قیمت در دسترس نیست"]

    # ── ۱ ابطال ساختاری: فقط با بسته روزانه
    inv = it.get("invalidation")
    if inv:
        cl = last_closed_daily(sym)
        if cl:
            close, day = cl
            broken = (close < inv) if side == "long" else (close > inv)
            key = f"inv_{day}"
            if broken and not st.get(key):
                st[key] = True
                fired.append(
                    f"⛔ {sym} — نقض ابطال ساختاری\n"
                    f"بسته روزانه {day}: {close:,.4f}\n"
                    f"سطح ابطال: {inv:,.4f}\n"
                    f"حکم رادار: خروج ۱۰۰٪ فوری، بدون بحث.\n"
                    f"این تنها ماشه‌ای است که هیچ استثنایی ندارد."
                )
            elif not broken:
                fired_note = st.get("inv_near")
                dist = abs(close - inv) / close * 100
                if dist < 3 and not fired_note:
                    st["inv_near"] = True
                    fired.append(f"⚠️ {sym} — فاصله تا ابطال {dist:.1f}٪ "
                                 f"(بسته {close:,.4f} / ابطال {inv:,.4f})")
                elif dist >= 5:
                    st.pop("inv_near", None)

    # ── ۲ پله‌های نردبان ورود
    for i, lv in enumerate(it.get("ladder") or [], 1):
        key = f"ladder_{i}"
        if st.get(key):
            continue
        hit = (px <= lv) if side == "long" else (px >= lv)
        if hit:
            st[key] = True
            if inv:
                bad = (px < inv) if side == "long" else (px > inv)
                if bad:
                    fired.append(f"🚫 {sym} — پله {i} در {lv:,.4f} لمس شد ولی "
                                 f"قیمت زیر سطح ابطال است. سفارش لغو شود.")
                    continue
            fired.append(
                f"🎯 {sym} — پله {i} نردبان ورود پر شد\n"
                f"سطح {lv:,.4f} | قیمت {px:,.4f}\n"
                f"پله‌های بعد را نگه دار. ثبت در ژورنال یادت نرود."
            )

    # ── ۳ اهداف
    for i, tg in enumerate(it.get("targets") or [], 1):
        key = f"target_{i}"
        if st.get(key):
            continue
        hit = (px >= tg) if side == "long" else (px <= tg)
        if hit:
            st[key] = True
            action = ("خروج ۴۰٪ و انتقال استاپ به سربه‌سر"
                      if i == 1 else "خروج ۳۵٪")
            fired.append(f"✅ {sym} — هدف {i} خورد در {tg:,.4f}\n"
                         f"نردبان خروج: {action}")

    # ── ۴ هشدارهای قیمتی ساده
    for lv in it.get("alerts") or []:
        key = f"alert_{lv}"
        if st.get(key):
            continue
        prev = st.get("last_px")
        if prev is not None and ((prev < lv <= px) or (prev > lv >= px)):
            st[key] = True
            fired.append(f"🔔 {sym} — عبور از {lv:,.4f} | قیمت {px:,.4f}")

    st["last_px"] = px
    return fired


def run_once(watch: dict, state: dict, quiet: bool = False) -> int:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if not quiet:
        print(f"پایش — {ts}")
    n = 0
    for it in watch.get("items", []):
        for msg in check_item(it, state):
            notify(msg, quiet=False)
            n += 1
    if n == 0 and not quiet:
        print("  هیچ ماشه‌ای فعال نشد.")
    save_json(STATE_FILE, state)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=f"پایشگر زنده سطوح — رادار {VERSION}")
    ap.add_argument("--watch", default=WATCH_FILE)
    ap.add_argument("--once", action="store_true", help="یک اجرا و خروج")
    ap.add_argument("--loop", type=int, default=0, help="حلقه با فاصله ثانیه")
    ap.add_argument("--init", action="store_true", help="ساخت فایل نمونه watch.json")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.init:
        save_json(a.watch, SAMPLE)
        print(f"فایل نمونه ساخته شد: {a.watch}")
        print("سطوح واقعی خودت را جایگزین کن، سپس اجرا کن.")
        print("\nبرای هشدار تلگرام، این دو متغیر را تنظیم کن:")
        print("  TELEGRAM_BOT_TOKEN")
        print("  TELEGRAM_CHAT_ID")
        return 0

    if not os.path.exists(a.watch):
        print(f"فایل {a.watch} پیدا نشد. برای ساخت نمونه: --init")
        return 1

    watch = load_json(a.watch, {"items": []})
    state = load_json(STATE_FILE, {})

    if a.loop:
        print(f"حلقه پایش هر {a.loop} ثانیه. برای توقف: Ctrl+C")
        try:
            while True:
                run_once(watch, state, a.quiet)
                time.sleep(a.loop)
        except KeyboardInterrupt:
            print("\nمتوقف شد.")
        return 0

    run_once(watch, state, a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
