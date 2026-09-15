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

# آستانه کهنگی سطوح پایش، به روز.
#
# چهارده روز انتخاب شد چون دو برابر افق معمول یک ستاپ نوسانی است.
# کمتر از این، هر بازبینی عقب‌افتاده هشدار می‌دهد و هشدار بی‌ارزش می‌شود.
# بیشتر از این، سطح ماه‌کهنه بی‌صدا می‌ماند — همان حالتی که این هشدار
# برای گرفتنش ساخته شد.
STALE_AFTER_DAYS = 14

SAMPLE = {
    "_راهنما": "هر مورد یک پوزیشن یا یک ستاپ در انتظار است",
    "_راهنمای_updated": "تاریخ آخرین بازبینی سطوح، به شکل YYYY-MM-DD. "
                        "پس از هر ویرایش سطوح به‌روزش کن، وگرنه هشدار "
                        "کهنگی فعال می‌شود",
    "updated": None,
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


# ─────────────────────── کهنگی سطوح ───────────────────────

def watch_age_days(path: str, now: datetime | None = None) -> float | None:
    """
    سن سطوح پایش به روز. مقدار None یعنی فایل نیست.

    ترتیب اولویت:
      ۱) میدان `updated` داخل خود فایل. تنها منبعی که در رانر گیت‌هاب هم
         معتبر است.
      ۲) مهر زمانی آخرین ویرایش فایل. برای اجرای محلی.

    **چرا میدان صریح مقدم است:** گیت مهر زمانی را ذخیره نمی‌کند. هر
    `actions/checkout` به همه فایل‌ها مهر لحظه چک‌اوت می‌زند، پس در رانر
    هر فایل همیشه «تازه» دیده می‌شود — و هشدار دقیقاً در جایی که هر چهار
    ساعت اجرا می‌شود بی‌اثر می‌ماند.
    """
    now = now or datetime.now(UTC)
    if not os.path.exists(path):
        return None

    stamp = None
    raw = load_json(path, {}).get("updated")
    if raw:
        try:
            d = datetime.fromisoformat(str(raw))
            stamp = d if d.tzinfo else d.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            stamp = None          # میدان خراب: به مهر زمانی برگرد

    if stamp is None:
        try:
            stamp = datetime.fromtimestamp(os.path.getmtime(path), UTC)
        except OSError:
            return None

    return (now - stamp).total_seconds() / 86_400


def stale_warning(path: str, now: datetime | None = None) -> str | None:
    """
    متن هشدار کهنگی، یا None اگر سطوح تازه باشند یا فایل نباشد.

    فایل غایب هشدار کهنگی نمی‌گیرد — مسئله دیگری است و `main` جداگانه
    گزارشش می‌کند. دو مسئله متفاوت نباید یک پیام بگیرند.
    """
    age = watch_age_days(path, now)
    if age is None or age < STALE_AFTER_DAYS:
        return None
    return (f"⚠️ سطوح پایش کهنه است — {age:.0f} روز از آخرین بازبینی "
            f"{os.path.basename(path)} گذشته (آستانه {STALE_AFTER_DAYS} روز).\n"
            f"پایشگر دارد سطوح قدیمی را می‌سنجد. ابطال و نردبان را بازبینی کن، "
            f"سپس میدان updated را به‌روز کن.")


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
        # فقط نوع استثنا — متن استثنای requests گاهی نشانی درخواست را
        # برمی‌گرداند و توکن بخشی از همان نشانی است.
        print(f"  ارسال تلگرام ناموفق: {type(e).__name__}")


def ping_telegram() -> bool:
    """
    یک پیام آزمایشی به تلگرام می‌فرستد و بلافاصله نتیجه را می‌دهد —
    بدون منتظر ماندن برای فعال‌شدن هیچ هشداری.

    توکن هرگز چاپ نمی‌شود: نه در پیام موفقیت، نه در پیام خطا، نه در خطای
    شبکه. حتی متن استثنای requests گاهی نشانی کامل درخواست را برمی‌گرداند
    و توکن بخشی از آن نشانی است، پس فقط نوع استثنا گزارش می‌شود.
    """
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    missing = [name for name, v in
               (("TELEGRAM_BOT_TOKEN", tok), ("TELEGRAM_CHAT_ID", chat))
               if not v]
    if missing:
        print(f"❌ متغیر محیطی غایب: {', '.join(missing)}")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data={"chat_id": chat,
                  "text": "🔔 آزمایش رادار — این یک پیام آزمایشی است."},
            timeout=15)
    except Exception as e:
        print(f"❌ خطای شبکه: {type(e).__name__}")
        return False

    try:
        j = r.json()
    except ValueError:
        j = {}

    if r.status_code == 200 and j.get("ok"):
        print("✅ پیام آزمایشی با موفقیت به تلگرام ارسال شد.")
        return True
    print(f"❌ ارسال ناموفق — کد {r.status_code}: {j.get('description', '؟')}")
    return False


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


def run_once(watch: dict, state: dict, quiet: bool = False,
             path: str = WATCH_FILE) -> int:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if not quiet:
        print(f"پایش — {ts}")

    # هشدار کهنگی پیش از هر سنجشی — اگر سطوح کهنه‌اند، بقیه خروجی هم
    # باید با همین چشم خوانده شود.
    warn = stale_warning(path)
    if warn:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"stale_{day}"
        if state.get(key):
            # پایش هر چهار ساعت یعنی شش اجرا در روز. همان هشدار شش بار
            # در تلگرام نویز است — در خروجی می‌ماند، در تلگرام روزی یک بار.
            if not quiet:
                print(warn)
        else:
            state[key] = True
            notify(warn, quiet=quiet)

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
    ap.add_argument("--ping", action="store_true",
                    help="پیام آزمایشی به تلگرام و خروج، بدون پایش")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.ping:
        return 0 if ping_telegram() else 1

    if a.init:
        sample = dict(SAMPLE)
        sample["updated"] = datetime.now(UTC).strftime("%Y-%m-%d")
        save_json(a.watch, sample)
        print(f"فایل نمونه ساخته شد: {a.watch}")
        print("سطوح واقعی خودت را جایگزین کن، سپس اجرا کن.")
        print(f"پس از هر ویرایش سطوح، میدان updated را هم به‌روز کن — "
              f"وگرنه بعد از {STALE_AFTER_DAYS} روز هشدار کهنگی می‌گیری.")
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
                run_once(watch, state, a.quiet, path=a.watch)
                time.sleep(a.loop)
        except KeyboardInterrupt:
            print("\nمتوقف شد.")
        return 0

    run_once(watch, state, a.quiet, path=a.watch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
