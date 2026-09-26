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

این قانون برای موردهای items است — ستاپ‌های دفتر معامله.

دفتر موقعیت — نشست ۳ رادار ۷
----------------------------
بخش‌های positions، market و reserve_plan در watch.json نسخه ۲:
    ابطال        بسته هفتگی وقت جهانی، یک بار برای هر هفته بسته‌شده.
                 سهم خروج exit_fraction، پیش‌فرض ۱.۰.
    سطح هشدار    فقط پیام، خروج نمی‌سازد.
    ورود دوباره  بسته هفتگی بالای سطح، از سهمیه دفتر کل holdings.json.
    هشدار بازار  بسته هفتگی BTC زیر میانگین ساده ۵۰ هفته — فقط اطلاع.
    نقشه ذخیره   پله رسیده، و مهلت برای پله‌های پرنشده.
سطح ابطال فقط در بازبینی هفتگی عوض می‌شود؛ این پایشگر watch.json را
بازنویسی نمی‌کند. حد ضرر دفتر معامله باید سفارش روی خود صرافی باشد —
پیام تلگرام حد ضرر نیست.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

import radar_positions as P
# لنگر کندل وقت جهانی — کتابخانه استاندارد، نشست ۳ب
import radar_anchor as A

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

# خطای شبکه و پاسخ نامعتبر — صریح، نه `except Exception: pass`. پیش از نشست ۳ب
# هر دو تابع پایین هر خطا را می‌بلعیدند و علت در گزارش پایش نمی‌آمد. None
# همچنان یعنی «داده ندارم»، ولی علتش در stderr و از آنجا در reports/WATCH.md است.
_BAD_REPLY = (ValueError, KeyError, IndexError, TypeError)


def _say(symbol: str, what: str, why: str) -> None:
    print(f"⚠️ {symbol.upper()}: {what} — {why}", file=sys.stderr)


def ticker(symbol: str) -> float | None:
    """قیمت لحظه‌ای. برای پله ورود، هدف و هشدار قیمتی."""
    try:
        r = requests.get(f"{OKX}/api/v5/market/ticker",
                         params={"instId": f"{symbol.upper()}-USDT"}, timeout=15)
        j = r.json()
        if j.get("code") == "0" and j.get("data"):
            return float(j["data"][0]["last"])
        _say(symbol, "قیمت لحظه‌ای", f"کد {j.get('code')} {j.get('msg') or ''}")
    except (requests.RequestException, *_BAD_REPLY) as exc:
        _say(symbol, "قیمت لحظه‌ای", f"{type(exc).__name__}: {exc}")
    return None


def last_closed_daily(symbol: str) -> tuple[float, str] | None:
    """
    بسته آخرین کندل روزانه **کامل‌شده**.

    اوکی‌اکس کندل جاری ناتمام را هم برمی‌گرداند. آن را کنار می‌گذاریم،
    چون قانون رادار می‌گوید سایه شکست نیست — فقط بسته معتبر است.

    لنگر وقت جهانی، 1Dutc — نشست ۳ب. کندل با لنگر دیگر رد و اعلام می‌شود.
    """
    what = f"بسته روزانه {A.BAR['okx']['1D']}"
    try:
        r = requests.get(f"{OKX}/api/v5/market/candles",
                         params={"instId": f"{symbol.upper()}-USDT",
                                 "bar": A.BAR["okx"]["1D"], "limit": "3"}, timeout=15)
        j = r.json()
        if j.get("code") != "0" or len(j.get("data") or []) < 2:
            _say(symbol, what, f"کد {j.get('code')} {j.get('msg') or ''}، "
                               f"{len(j.get('data') or [])} کندل")
            return None
        rows = sorted(j["data"], key=lambda x: int(x[0]))
        why = A.check([int(x[0]) for x in rows], "1D",
                      f"{symbol.upper()}: اوکی‌اکس {A.BAR['okx']['1D']}")
        if why:
            print(f"⚠️ {why}", file=sys.stderr)
            return None
        now_ms = int(time.time() * 1000)
        for row in reversed(rows):
            start = int(row[0])
            if now_ms - start >= 86_400_000:      # کندل تمام شده
                day = datetime.fromtimestamp(start / 1000, UTC).strftime("%Y-%m-%d")
                return float(row[4]), day
        _say(symbol, what, "کندل تمام‌شده‌ای در پاسخ نبود")
    except (requests.RequestException, *_BAD_REPLY) as exc:
        _say(symbol, what, f"{type(exc).__name__}: {exc}")
    return None


# ─────────────────────── وضعیت ───────────────────────

class WatchError(Exception):
    """فایل پایش یا وضعیت خوانا نیست — هرگز بی‌صدا به فهرست خالی تبدیل نمی‌شود."""


def load_json(path: str, default: dict) -> dict:
    """
    فایل غایب همان پیش‌فرض است. فایل خراب خطای صریح: پیش از نشست ۳ اینجا
    except Exception: pass بود و watch.json خراب یعنی پایش خاموش.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise WatchError(f"{os.path.basename(path)} خوانا نیست ({type(exc).__name__}: {exc})") from exc
    if not isinstance(data, dict):
        raise WatchError(f"{os.path.basename(path)} خوانا نیست — شیء JSON نیست")
    return data


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
    try:
        raw = load_json(path, {}).get("updated")
    except WatchError:
        # فایل خراب: خطای بلندش را main پیش از پایش می‌دهد؛ اینجا فقط سن
        # لازم است، پس به مهر زمانی برمی‌گردد — همان رفتار پیشین
        raw = None
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
    return (f"⚠️ سطوح پایش کهنه است — {fa(f'{age:.0f}')} روز از آخرین بازبینی "
            f"{os.path.basename(path)} گذشته (آستانه {fa(STALE_AFTER_DAYS)} روز).\n"
            f"پایشگر دارد سطوح قدیمی را می‌سنجد. ابطال و نردبان را بازبینی کن، "
            f"سپس میدان updated را به‌روز کن.")


def _file_age(path: str, now: datetime) -> tuple[str, float | None, str | None]:
    """
    (مهر خوانا، سن به روز، علت خطا) فقط از میدان updated داخلی. بازگشت به
    زمان تغییر فایل نیست: در رانر گیت‌هاب checkout همه را تازه می‌کند.
    """
    if not os.path.exists(path):
        return "—", None, "فایل نیست"
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f).get("updated")
    except (OSError, ValueError, AttributeError) as exc:
        return "—", None, f"فایل خوانا نیست (`{type(exc).__name__}`)"
    try:
        d = datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        d = None
    if d is None:
        return "—", None, "میدان updated نیست یا نامعتبر — کهنه فرض شد"
    d = d if d.tzinfo else d.replace(tzinfo=UTC)          # قالب تاریخ خالی: ۰۰:۰۰ وقت جهانی
    age = (now - d).total_seconds() / 86_400
    if age < -1 / 144:                                    # ده دقیقه کجی ساعت
        return d.strftime("%Y-%m-%d %H:%M UTC"), None, "updated در آینده است — کهنه فرض شد"
    return d.strftime("%Y-%m-%d %H:%M UTC"), age, None


def staleness_report(holdings_path: str, watch_path: str,
                     now: datetime | None = None) -> tuple[str, bool]:
    """
    بخش «تازگی داده‌های دستی» برای LATEST.md و پیام تلگرام روزانه.
    holdings.json بیش از ۷ روز، watch.json بیش از ۱۴ روز. خروجی دوم: کهنه هست؟
    """
    from radar_positions import HOLDINGS_STALE_DAYS
    now = now or datetime.now(UTC)
    rows, stale = [], False
    for path, limit in ((holdings_path, HOLDINGS_STALE_DAYS), (watch_path, STALE_AFTER_DAYS)):
        stamp, age, err = _file_age(path, now)
        if err:
            stale, verdict = True, f"⚠️ {err}"
        elif age > limit:
            stale, verdict = True, "⚠️ کهنه — بازبینی و به‌روزرسانی updated لازم است"
        else:
            verdict = "✅ تازه"
        rows.append(f"| {os.path.basename(path)} | {stamp} | "
                    f"{'—' if age is None else f'{age:.1f}'} | {fa(limit)} | {verdict} |")
    lines = ["## تازگی داده‌های دستی", "",
             "| فایل | به‌روزرسانی | سن، روز | آستانه، روز | وضعیت |",
             "|---|---|---|---|---|", *rows, ""]
    if stale:
        lines += ["⚠️ **داده دستی کهنه است.** گزارش سبد و پایشگر روی آن ساخته می‌شوند.", ""]
    return "\n".join(lines), stale


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
        nk = "noclose_" + datetime.now(UTC).strftime("%Y-%m-%d")
        if cl is None and not st.get(nk):
            # پیش از نشست ۳ب ابطال این مورد بی‌صدا سنجیده نمی‌شد. روزی یک پیام
            st[nk] = True
            fired.append(f"⚠️ {sym} — بسته روزانه در دسترس نیست؛ ابطال {inv:,.4f} "
                         "سنجیده نشد — علت در گزارش پایش")
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


# ─────────────────────── دفتر موقعیت — نشست ۳ رادار ۷ ───────────────────────
#
# ابطال دفتر موقعیت با بسته هفتگی وقت جهانی سنجیده می‌شود — تصمیم «دو دفتر»،
# ۲۵ سپتامبر ۲۰۲۶. قانون بسته روزانه بالا فقط برای موردهای items است. سطح
# فقط در بازبینی هفتگی عوض می‌شود؛ پایشگر watch.json را بازنویسی نمی‌کند.
# هر هفته بسته‌شده یک بار سنجیده می‌شود: نخستین اجرای پس از دوشنبه ۰۰:۰۰.
# اندازه‌گیری ۳۰ روز نبض: آن اجرا حدود ۰۴:۳۰ تا ۰۵:۳۰ وقت جهانی می‌رسد.

# گزینه الف آزمون تکان‌خوردن. تصمیم کاربر، ۲۶ سپتامبر ۲۰۲۶: سهم خروج پارامتر
# است تا تصمیم نهایی فقط یک عدد در watch.json باشد
DEFAULT_EXIT_FRACTION = 1.0
# سطح هشدار پس از بازگشت ۱٪ بالای خودش دوباره مسلح می‌شود — نوسان روی خط
# پیام تکراری نسازد
WARN_REARM = 1.01
# پله ذخیره با پوشش ۹۹٪ مقدارش پرشده حساب می‌شود — گرد کردن صرافی
STEP_TOL = 0.01


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _n(x: float) -> str:
    """عدد بازار در پیام: رقم لاتین، بدون صفر و گرد کردن گمراه‌کننده."""
    return f"{x:.10g}"


def _aware(raw, what: str) -> datetime:
    try:
        d = datetime.fromisoformat(str(raw))
    except ValueError as exc:
        raise WatchError(f"{what} قابل‌خواندن نیست: {raw!r}") from exc
    if d.tzinfo is None:
        raise WatchError(f"{what} منطقه زمانی ندارد: {raw!r}")
    return d


FULL = "مهر کامل با منطقه زمانی لازم است"


def exit_fraction(w: dict) -> float:
    return float(w.get("exit_fraction", DEFAULT_EXIT_FRACTION))


def validate_watch(w: dict) -> None:
    """
    شکل بخش‌های دفتر موقعیت در watch.json. فایل نیمه‌درست یعنی پایش خاموش —
    خطای صریح. نسخه ۲: updated و مهر هر سطح، مهر کامل با منطقه زمانی؛ فقط
    تاریخ خطاست. updated فقط برای هشدار کهنگی است، نه برای داوری.
    """
    if w.get("version") == 2:
        _aware(w.get("updated"), f"updated — {FULL}")
    if "exit_fraction" in w:
        f = w["exit_fraction"]
        if not _num(f) or not 0 < f <= 1:
            raise WatchError(f"exit_fraction باید عددی بزرگ‌تر از 0 و حداکثر 1 باشد: {f!r}")
    for i, p in enumerate(w.get("positions") or [], 1):
        where = f"positions ردیف {i}"
        if not isinstance(p, dict) or not isinstance(p.get("symbol"), str):
            raise WatchError(f"{where}: نماد نیست")
        if not _num(p.get("invalidation")) or p["invalidation"] <= 0:
            raise WatchError(f"{where} ({p['symbol']}): سطح ابطال عدد مثبت نیست")
        _aware(p.get("invalidation_since"), f"{where} ({p['symbol']}): invalidation_since — {FULL}")
        ws = p.get("warnings", [])
        if not isinstance(ws, list) or not all(_num(x) and x > 0 for x in ws):
            raise WatchError(f"{where} ({p['symbol']}): سطوح هشدار نامعتبر")
    for i, m in enumerate(w.get("market") or [], 1):
        if not isinstance(m, dict) or not isinstance(m.get("symbol"), str):
            raise WatchError(f"market ردیف {i}: نماد نیست")
        if "weekly_close_below" in m:
            # بند ۴ ایستگاه آخر نشست ۳: عدد ثابت از بسته هفته بعد کهنه می‌شد
            raise WatchError(f"market ردیف {i}: عدد ثابت weekly_close_below مجاز نیست — "
                             "میانگین از regime.json میدان btc_sma50w خوانده می‌شود")
    rp = w.get("reserve_plan")
    if rp is not None:
        _aware(rp.get("created"), "reserve_plan.created")
        _aware(rp.get("deadline"), "reserve_plan.deadline")
        for i, s in enumerate(rp.get("steps") or [], 1):
            price = s.get("price")
            if (not isinstance(s.get("symbol"), str) or not _num(s.get("qty")) or s["qty"] <= 0
                    or not (price is None or (_num(price) and price > 0))):
                raise WatchError(f"reserve_plan پله {i}: نماد، مقدار یا قیمت نامعتبر")
            ex = s.get("executed")
            if ex is not None:
                if not isinstance(ex, dict) or not isinstance(ex.get("order_id"), str) \
                        or not ex["order_id"]:
                    raise WatchError(f"reserve_plan پله {i}: executed باید زمان و order_id داشته باشد")
                _aware(ex.get("at"), f"reserve_plan پله {i}: executed.at — {FULL}")


def unfilled_steps(rp: dict, h: dict) -> list[dict]:
    """
    پله‌های پرنشده نقشه ذخیره. پرشده یعنی پوشش‌داده با کاهش reserve دفتر کل
    پس از ساخت نقشه. پله‌های هر نماد به ترتیب نقشه پر می‌شوند.
    """
    return [{"symbol": s["symbol"], "qty": s["qty"], "price": s.get("price")}
            for s, filled in zip(rp.get("steps") or [], step_filled(rp, h)) if not filled]


def step_filled(rp: dict, h: dict) -> list[bool]:
    """
    پرشدن هر پله، به ترتیب نقشه، فقط از کاهش reserve دفتر کل پس از ساخت نقشه.
    علامت executed در watch.json اینجا نقشی ندارد — منبع حقیقت دفتر کل است.
    """
    created = _aware(rp["created"], "reserve_plan.created")
    done: dict[str, float] = {}
    for r in h.get("ledger", []):
        if r.get("action") == "trim" and r.get("reason") == "reserve":
            if _aware(r.get("at"), "زمان ردیف دفتر کل") >= created:
                done[r["symbol"]] = done.get(r["symbol"], 0.0) - float(r["delta"])
    out, cum = [], {}
    for s in rp.get("steps") or []:
        sym = s["symbol"]
        cum[sym] = cum.get(sym, 0.0) + s["qty"]
        out.append(cum[sym] - STEP_TOL * s["qty"] <= done.get(sym, 0.0))
    return out


def _once(state: dict, key: str, msgs: list, text: str) -> None:
    if not state.get(key):
        state[key] = True
        msgs.append(text)


def _week_of(now: datetime) -> str:
    """دوشنبه ۰۰:۰۰ وقت جهانی هفته جاری — کلید «یک بار در هفته»."""
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


def regime_sma(regime: dict | None, now: datetime) -> tuple[dict | None, str | None]:
    """
    میانگین ساده ۵۰ هفته بیت‌کوین از regime.json — میدان btc_sma50w. خروجی
    دوم هشدار صریح است: فایل غایب، کهنه یا بی‌میدان. آستانه کهنگی همان
    آستانه سبد است، از radar_book.
    """
    if not isinstance(regime, dict):
        return None, "regime.json نیست یا خوانا نیست"
    try:
        gen = _aware(regime.get("generated_at"), "regime.json generated_at")
    except WatchError as exc:
        return None, str(exc)
    from radar_book import REGIME_MAX_AGE_DAYS      # تنها منبع آستانه کهنگی رژیم
    age = (now - gen).total_seconds() / 86_400
    if age > REGIME_MAX_AGE_DAYS:
        return None, (f"regime.json کهنه است — {age:.1f} روز، آستانه "
                      f"{fa(REGIME_MAX_AGE_DAYS)} روز")
    s = regime.get("btc_sma50w")
    if not isinstance(s, dict):
        return None, "میدان btc_sma50w در regime.json نیست"
    if not _num(s.get("value")):
        return None, f"btc_sma50w در regime.json مقدار ندارد — {s.get('reason') or 'بی‌دلیل'}"
    try:
        _aware(s.get("week_closed_at"), "btc_sma50w.week_closed_at")
    except WatchError as exc:
        return None, str(exc)
    return s, None


def check_positions(watch: dict, h: dict, state: dict, now: datetime,
                    weekly=None, price=None, regime: dict | None = None) -> list[str]:
    """
    ابطال هفتگی، سطح هشدار، ورود دوباره، هشدار بازار و نقشه ذخیره. فقط state
    عوض می‌شود؛ watch و h دست‌نخورده می‌مانند. weekly و price تزریق‌پذیرند.
    regime سند regime.json است — منبع میانگین هشدار بازار.
    """
    weekly = weekly or (lambda s: P.weekly_close(s, now=now))
    price = price or ticker
    msgs: list[str] = []
    day, week = now.strftime("%Y-%m-%d"), _week_of(now)
    f = exit_fraction(watch)
    pos = {p["symbol"]: p for p in h.get("positions", []) if p.get("book") == "position"}
    if watch.get("positions"):
        bad = P.level_mismatches(h, watch)
        if bad:
            _once(state, f"mismatch_{day}_{'|'.join(bad)}", msgs,
                  "⛔ ناهمخوانی سطح ابطال میان watch.json و holdings.json:\n"
                  + "\n".join(f"- {b}" for b in bad)
                  + "\nتا یکی شوند، پایشگر با محافظه‌کارانه‌تر می‌سنجد: سطح بالاتر و مهر زودتر.")
        av = P.anchor_violations(watch)
        if av:
            # هشدار صریح، نه خطا: پایش با سطح فعلی ادامه دارد تا بازبینی
            _once(state, f"anchor_{day}_{'|'.join(av)}", msgs,
                  "⚠️ قاعده لنگر سطح ابطال — سطح باید دست‌کم ۱ دامنه واقعی هفتگی زیر "
                  "min(قیمت، آخرین بسته هفتگی) باشد:\n" + "\n".join(f"- {a}" for a in av)
                  + "\nپایش با سطح فعلی ادامه دارد تا بازبینی.")
    wk_cache: dict = {}
    px_cache: dict = {}

    def wk(sym):
        if sym not in wk_cache:
            wk_cache[sym] = weekly(sym)
        return wk_cache[sym]

    def px(sym):
        if sym not in px_cache:
            px_cache[sym] = price(sym)
            if px_cache[sym] is None:
                _once(state, f"noprice_{sym}_{day}", msgs,
                      f"⚠️ قیمت {sym} در دسترس نیست — سطح هشدار و پله ذخیره {sym} "
                      "این اجرا سنجیده نشد.")
        return px_cache[sym]

    # ── ۱ ابطال هفتگی و سطح هشدار
    for item in watch.get("positions") or []:
        sym, lvl = item["symbol"].upper(), float(item["invalidation"])
        tag = f" ({item['label']})" if item.get("label") else ""
        p = pos.get(sym)
        if p is None:
            continue                            # در پیام ناهمخوانی بالا آمده
        since = _aware(item["invalidation_since"], f"{sym}: invalidation_since")
        # ناهمخوانی: محافظه‌کارانه‌تر — سطح بالاتر زودتر خارج می‌کند، مهر زودتر
        # بسته بیشتری را داوری می‌کند
        hinv = p.get("invalidation")
        if _num(hinv):
            lvl = max(lvl, float(hinv))
        try:
            hs = P.level_since(p)
        except P.PositionsError:
            hs = None
        if hs is not None:
            since = min(since, hs)
        if p.get("status") != "open" or P.position_qty(p) <= 0:
            continue

        w, why = wk(sym)
        if w is None:
            _once(state, f"nodata_{sym}_{week}", msgs,
                  f"⚠️ داده ندارم — بسته هفتگی {sym} به لنگر وقت جهانی در دسترس نیست "
                  f"({'؛ '.join(why) or 'بی‌دلیل'}). ابطال{tag} سنجیده نشد؛ اجرای بعد "
                  "دوباره تلاش می‌کند.")
        elif (not state.get(f"wk_{sym}_{w['closed_at']}")
              and P.judged(w["closed_at"], since)):
            state[f"wk_{sym}_{w['closed_at']}"] = True
            close, qty = w["close"], P.position_qty(p)
            bkey = f"breach_{sym}"
            prev = state.get(bkey)
            head = (f"⛔ ابطال هفتگی {sym}{tag} — بسته هفته تا {w['closed_at'][:10]}: "
                    f"{_n(close)}، زیر سطح {_n(lvl)}.")
            if close < lvl and (f >= 1.0 or prev):
                state.pop(bkey, None)
                second = "دومین بسته پیاپی زیر سطح. " if prev else ""
                msgs.append(f"{head}\n{second}خروج کامل باقی‌مانده: {_n(qty)} {sym}.\n"
                            f"ثبت: radar_positions.py exit --symbol {sym} "
                            f"--price <قیمت اجرا> --level {_n(lvl)}")
            elif close < lvl:
                sell = qty * f
                state[bkey] = w["closed_at"]
                msgs.append(f"{head}\nفروش سهم {_n(f)}: {_n(sell)} {sym}. باقی فقط اگر "
                            "بسته هفتگی بعد هم زیر سطح بود.\n"
                            f"ثبت: radar_positions.py trim --reason invalidation "
                            f"--level {_n(lvl)} --symbol {sym} --qty {_n(sell)} "
                            "--price <قیمت اجرا>")
            elif prev:
                state.pop(bkey, None)
                msgs.append(f"✅ {sym}{tag} — بسته هفتگی {_n(close)} بالای سطح {_n(lvl)}. "
                            f"باقی‌مانده {_n(qty)} نگه داشته می‌شود. سهم فروخته‌شده: "
                            "ورود دوباره مجاز — radar_positions.py reenter")

        for wl in item.get("warnings") or []:
            v = px(sym)
            if v is None:
                break
            key = f"warn_{sym}_{_n(wl)}"
            if v < wl and not state.get(key):
                state[key] = True
                msgs.append(f"⚠️ سطح هشدار {sym} شکسته شد — قیمت {_n(v)} زیر {_n(wl)}.\n"
                            "فقط پیام؛ خروجی نمی‌سازد. ابطال همچنان بسته هفتگی زیر "
                            f"{_n(lvl)} است.")
            elif v > wl * WARN_REARM:
                state.pop(key, None)

    # ── ۲ ورود دوباره: سهمیه از دفتر کل، بسته هفتگی بالای سطح
    for sym in pos:
        st = P.reentry_state(h, sym)
        if st is None or st["used"] >= st["max_qty"] - P.TOL:
            continue
        w, why = wk(sym)
        if w is None:
            _once(state, f"nodata_re_{sym}_{week}", msgs,
                  f"⚠️ داده ندارم — بسته هفتگی {sym}؛ مجوز ورود دوباره سنجیده نشد.")
            continue
        key = f"re_{sym}_{w['closed_at']}"
        if state.get(key):
            continue
        state[key] = True
        if w["close"] > st["level"]:
            msgs.append(f"🔁 ورود دوباره مجاز {sym} — بسته هفتگی {_n(w['close'])} بالای "
                        f"سطح {_n(st['level'])}.\nسهمیه باقی: "
                        f"{_n(st['max_qty'] - st['used'])} {sym}. ثبت: radar_positions.py "
                        f"reenter --symbol {sym} --qty <مقدار> --price <قیمت> --account <حساب>")

    # ── ۳ هشدار بازار: فقط اطلاع. میانگین از regime.json، فقط بسته همان هفته
    for m in watch.get("market") or []:
        sym = m["symbol"].upper()
        sma, warn = regime_sma(regime, now)
        if warn:
            _once(state, f"mkt_warn_{sym}_{day}", msgs,
                  f"⚠️ {warn} — هشدار بازار {sym} سنجیده نشد.")
            continue
        w, why = wk(sym)
        if w is None:
            _once(state, f"nodata_mkt_{sym}_{week}", msgs,
                  f"⚠️ داده ندارم — بسته هفتگی {sym}؛ هشدار بازار سنجیده نشد.")
            continue
        closed = _aware(w["closed_at"], "زمان بسته هفتگی")
        sma_week = _aware(sma["week_closed_at"], "btc_sma50w.week_closed_at")
        if closed != sma_week:
            # گذراست: رژیم روزانه پس از بسته دوشنبه ساخته می‌شود. کهنگی واقعی
            # را هشدار بالا می‌گیرد
            print(f"  هشدار بازار {sym}: بسته هفته تا {w['closed_at'][:10]}، میانگین "
                  f"رژیم تا {sma['week_closed_at'][:10]} — در انتظار هفته یکسان")
            continue
        key = f"mkt_{sym}_{w['closed_at']}"
        if state.get(key):
            continue
        state[key] = True
        if w["close"] < sma["value"]:
            msgs.append(f"📉 هشدار بازار — بسته هفتگی {sym} {_n(w['close'])} زیر "
                        f"{m.get('label') or 'میانگین'} {_n(round(sma['value'], 2))} — "
                        f"هفته بسته در {w['closed_at'][:10]}، منبع regime.json.\n"
                        "فقط اطلاع؛ خروج نمی‌سازد.")

    # ── ۴ نقشه ذخیره
    rp = watch.get("reserve_plan")
    if rp:
        left = unfilled_steps(rp, h)
        deadline = _aware(rp["deadline"], "reserve_plan.deadline")
        acct = rp.get("account") or "حساب نقشه"

        def label(s):
            return "پله بازار" if s["price"] is None else f"پله {_n(s['price'])}"

        # علامت اجراشده‌ای که دفتر کل پوشش نمی‌دهد: پله پر حساب نمی‌شود، بلند است
        stray = [s for s, filled in zip(rp.get("steps") or [], step_filled(rp, h))
                 if s.get("executed") and not filled]
        if stray:
            rows = "\n".join(f"- {s['symbol']} {_n(s['qty'])} — {label(s)}، سفارش "
                             f"{s['executed']['order_id']}" for s in stray)
            _once(state, f"reserve_stray_{day}", msgs,
                  "⚠️ پله‌هایی در watch.json علامت اجراشده دارند ولی دفتر کل پوششان "
                  f"نمی‌دهد — پر حساب نشدند:\n{rows}\n"
                  "ثبت با radar_positions.py trim --reason reserve --at <زمان رسید>")

        if now >= deadline:
            if left:
                rows = "\n".join(f"- {s['symbol']} {_n(s['qty'])} — {label(s)}" for s in left)
                _once(state, f"reserve_deadline_{rp['deadline']}", msgs,
                      f"⏰ مهلت نقشه ذخیره گذشت ({deadline.astimezone(UTC):%Y-%m-%d %H:%M} "
                      f"UTC). پله‌های پرنشده — فروش در قیمت بازار از {acct}:\n{rows}\n"
                      "ثبت هر کدام: radar_positions.py trim --reason reserve")
        else:
            market = [s for s in left if s["price"] is None]
            if market:
                rows = "، ".join(f"{s['symbol']} {_n(s['qty'])}" for s in market)
                _once(state, f"reserve_market_{day}", msgs,
                      f"🧾 پله بازار نقشه ذخیره هنوز در دفتر کل ثبت نشده: {rows}. اجرا از "
                      f"{acct} و ثبت با radar_positions.py trim --reason reserve.")
            for s in left:
                if s["price"] is None:
                    continue
                v = px(s["symbol"])
                key = f"reserve_{s['symbol']}_{_n(s['price'])}"
                if v is not None and v >= s["price"] and not state.get(key):
                    state[key] = True
                    msgs.append(f"🎯 پله ذخیره {s['symbol']} {_n(s['price'])} رسید — قیمت "
                                f"{_n(v)}.\nفروش {_n(s['qty'])} {s['symbol']} از {acct}. "
                                "اگر سفارش پر شد، ثبت: radar_positions.py trim --reason "
                                f"reserve --symbol {s['symbol']} --qty {_n(s['qty'])} "
                                "--price <قیمت اجرا>")
    return msgs


def _read_regime(path: str | None) -> dict | None:
    """regime.json هر اجرا تازه خوانده می‌شود؛ غایب یا خراب یعنی None و هشدار صریح بعدی."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"  ⚠️ {os.path.basename(path)} خوانا نیست ({type(exc).__name__})")
        return None
    return doc if isinstance(doc, dict) else None


def run_once(watch: dict, state: dict, quiet: bool = False,
             path: str = WATCH_FILE, h: dict | None = None,
             now: datetime | None = None, regime_path: str | None = "regime.json") -> int:
    """
    h خالی یعنی holdings.json بار نشد — main پیش‌تر بلند گزارشش کرده. آن‌وقت
    فقط هشدار بازار سنجیده می‌شود، که به دفتر موقعیت وابسته نیست.
    """
    now = now or datetime.now(UTC)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
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
    scope = watch if h is not None else {"market": watch.get("market"),
                                         "updated": watch.get("updated")}
    regime = _read_regime(regime_path) if watch.get("market") else None
    for msg in check_positions(scope, h or {"positions": [], "ledger": []}, state, now,
                               regime=regime):
        notify(msg, quiet=False)
        n += 1
    if n == 0 and not quiet:
        print("  هیچ ماشه‌ای فعال نشد.")
    save_json(STATE_FILE, state)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=f"پایشگر زنده سطوح — رادار {fa(VERSION)}")
    ap.add_argument("--watch", default=WATCH_FILE)
    ap.add_argument("--once", action="store_true", help="یک اجرا و خروج")
    ap.add_argument("--loop", type=int, default=0, help="حلقه با فاصله ثانیه")
    ap.add_argument("--init", action="store_true", help="ساخت فایل نمونه watch.json")
    ap.add_argument("--ping", action="store_true",
                    help="پیام آزمایشی به تلگرام و خروج، بدون پایش")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--staleness", action="store_true",
                    help="بخش تازگی holdings.json و watch.json برای گزارش روزانه و خروج")
    ap.add_argument("--holdings", default="holdings.json")
    ap.add_argument("--regime-file", default="regime.json", dest="regime_file",
                    help="منبع میانگین ساده ۵۰ هفته بیت‌کوین برای هشدار بازار")
    a = ap.parse_args(argv)

    if a.staleness:
        print(staleness_report(a.holdings, a.watch)[0])
        return 0

    if a.ping:
        return 0 if ping_telegram() else 1

    if a.init:
        sample = dict(SAMPLE)
        sample["updated"] = datetime.now(UTC).strftime("%Y-%m-%d")
        save_json(a.watch, sample)
        print(f"فایل نمونه ساخته شد: {a.watch}")
        print("سطوح واقعی خودت را جایگزین کن، سپس اجرا کن.")
        print(f"پس از هر ویرایش سطوح، میدان updated را هم به‌روز کن — "
              f"وگرنه بعد از {fa(STALE_AFTER_DAYS)} روز هشدار کهنگی می‌گیری.")
        print("\nبرای هشدار تلگرام، این دو متغیر را تنظیم کن:")
        print("  TELEGRAM_BOT_TOKEN")
        print("  TELEGRAM_CHAT_ID")
        return 0

    if not os.path.exists(a.watch):
        print(f"فایل {a.watch} پیدا نشد. برای ساخت نمونه: --init")
        return 1

    try:
        watch = load_json(a.watch, {"items": []})
        validate_watch(watch)
    except WatchError as exc:
        notify(f"⛔ {exc} — پایش انجام نشد. هیچ ابطال و هشداری سنجیده نشد.")
        return 2
    rc = 0
    h = None
    if watch.get("positions") or watch.get("reserve_plan"):
        try:
            h, _ = P.load(a.holdings)
        except P.PositionsError as exc:
            notify(f"⛔ holdings.json نامعتبر — ابطال دفتر موقعیت و نقشه ذخیره سنجیده "
                   f"نشد: {exc}")
            rc = 2
        else:
            # پیامش را check_positions می‌دهد؛ اینجا فقط کد خروج بلند می‌شود
            if P.level_mismatches(h, watch):
                rc = 2
    try:
        state = load_json(STATE_FILE, {})
    except WatchError as exc:
        # هشدار تکراری بهتر از هشدار گم‌شده است: با وضعیت خالی ادامه، ولی بلند
        notify(f"⚠️ {exc} — وضعیت از صفر ساخته شد؛ هشدارهای تکراری ممکن است.")
        state, rc = {}, 3

    if a.loop:
        print(f"حلقه پایش هر {a.loop} ثانیه. برای توقف: Ctrl+C")
        try:
            while True:
                run_once(watch, state, a.quiet, path=a.watch, h=h,
                         regime_path=a.regime_file)
                time.sleep(a.loop)
        except KeyboardInterrupt:
            print("\nمتوقف شد.")
        return rc

    run_once(watch, state, a.quiet, path=a.watch, h=h, regime_path=a.regime_file)
    return rc


def run_cli(argv: list[str] | None = None) -> int:
    """
    نقطه ورود. افتادن پیش‌بینی‌نشده پیام تلگرام می‌دهد و همان خطا دوباره
    بالا می‌رود — پیش از این گام نبض با `|| true` آن را می‌بلعید.
    """
    try:
        return main(argv)
    except Exception as exc:
        notify(f"⛔ پایشگر رادار افتاد — {type(exc).__name__}: {str(exc)[:300]}\n"
               "این اجرا هیچ ابطال و هشداری را نسنجید.")
        raise


if __name__ == "__main__":
    sys.exit(run_cli())
