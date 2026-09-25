#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_book.py — موتور بازبینی سبد و خروج، رادار ۶.۱
====================================================

چرا این فایل نوشته شد
---------------------
رادار تا ۵.۴ یک چارچوب **ورود** بود. ولی ضرر سبد از ورود نیامد؛
از **نگه‌داشتن** آمد. سه نشانه ثبت شده بود و هیچ‌کدام به اقدام تبدیل نشد:

    • ONDO چهار امتیاز اسکن نزولی متوالی گرفت — هیچ قانونی برای واکنش نبود
    • ZEC از رتبه ۱ به خارج از رتبه‌بندی افتاد — هیچ اقدامی
    • هشت پوزیشن اسپات بدون هیچ سطح ابطالی — در حرارت سبد صفر شمرده می‌شدند

این اسکریپت آن فاصله را می‌بندد.

چهار آزمون هفتگی هر پوزیشن
--------------------------
    ۱) زنده‌بودن تز        — ابطال ساختاری نقض شده؟
    ۲) پوسیدگی نسبی        — قدرت نسبی ۳۰ روزه به بیت‌کوین + روند امتیاز
    ۳) جانشینی             — نامزد بهتری با مزیت بالای ۰.۵ هست؟
    ۴) هزینه نگهداری       — فاندینگ و هزینه فرصت

قانون سه‌ضربه
-------------
سه بازبینی متوالی با امتیاز کاهشی ← کاهش اجباری حداقل ۵۰٪.
چهارمی ← خروج کامل. بدون استثنا، بدون توجه به میزان ضرر.

نمونه اجرا
----------
    python radar_book.py --holdings holdings.json --regime -1.25
    python radar_book.py --holdings holdings.json --regime -1.25 --candidates BTC,XAUT,HYPE
    python radar_book.py --init            # ساخت فایل نمونه holdings.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa
# دو دفتر و دفتر کل — کتابخانه استاندارد، استقلال این فایل نمی‌شکند
import radar_positions as P

try:
    import requests
except ImportError:
    requests = None

try:
    import pandas as pd
except ImportError:
    pd = None

VERSION = "6.1"
UTC = timezone.utc
STATE_FILE = "book_state.json"
OKX = "https://www.okx.com"

# ─────────── جدول رژیم — تنها منبع اصلی radar_budget.py، کپی محلی نگیر ───────────
# پیش از نشست ۲ این جدول اینجا و در radar_size.py جدا نوشته شده بود.
# روی مرز دقیق باند پایین‌تر انتخاب می‌شود؛ پیش از این `>=` بود.
from radar_budget import regime_band as regime_row

# قاعده بلوغ ۳n: میانگین نمایی ۲۰۰ دست‌کم ۶۰۰ کندل **بسته** لازم دارد،
# و صرافی کندل باز را هم می‌فرستد که جدا می‌شود — پس یکی بیشتر.
# کپی محلی از radar_fetch3.py، چون ایمپورت آن استقلال این فایل و
# ایمپورت اختیاری pandas را می‌شکند. آزمون tests/test_ema200_maturity.py
# برابری دو نسخه را قفل می‌کند.
EMA200_MATURE_BARS = 3 * 200
DAILY_WANT = EMA200_MATURE_BARS + 1

SWAP_COST_SCORE = 0.15    # هزینه تعویض بر حسب واحد امتیاز
SWAP_MIN_EDGE = 0.50      # آستانه اجرای جانشینی
SWAP_WATCH_EDGE = 0.30    # آستانه نامزدی
MAX_SWAPS_WEEK = 2
MIN_HOLD_DAYS = 10


# ─────────── منبع رژیم — رفع موقت تا نشست ۲ (radar_regime.py) ───────────
#
# پیش از این گردش‌کار روزانه هر روز `-1.0` تزریق می‌کرد و پیش‌فرض این فایل
# 0.0 بود. حالا رژیم از regime.json می‌آید، یا از کلید دستی --regime.
# اگر هیچ‌کدام معتبر نبود، گزارش «رژیم کهنه» می‌گوید — هیچ مقدار جانشینی
# جا زده نمی‌شود.
#
# قرارداد regime.json — خواننده فقط دو میدان لازم دارد و بقیه را نادیده
# می‌گیرد، تا نشست ۲ میدان اضافه کند بی‌آنکه چیزی بشکند:
#   score         امتیاز **نهایی تصمیم**: باند محافظه‌کارانه‌تر میان امتیاز
#                 خام و نرمال‌شده (قاعده ۲، قانون سوگیری صفر). نه خام، نه نرمال.
#   generated_at  زمان ISO با منطقه زمانی. بدون منطقه زمانی نامعتبر است،
#                 چون عمرش را نمی‌شود دانست. عمر از همین میدان حساب می‌شود،
#                 نه از زمان تغییر فایل — دریافت مخزن در گیت آن را تازه می‌کند.
REGIME_FILE = "regime.json"
REGIME_MAX_AGE_DAYS = 7
# کجی ساعت مجاز میان دستگاه سازنده و خواننده
REGIME_CLOCK_SKEW = timedelta(minutes=10)
REGIME_STALE = "رژیم کهنه — بازمحاسبه لازم است"


class RegimeInfo(NamedTuple):
    """
    خروجی load_regime. NamedTuple، نه تاپل ساده: مصرف‌کننده با نام میدان
    می‌خواند، پس افزودن میدان بعدی او را نمی‌شکند.

    score     امتیاز رژیم، یا None یعنی «رژیم کهنه»
    source    در حالت سالم منبع رژیم، در حالت کهنه دلیل آن
    warnings  هشدارهایی که باید کنار رژیم دیده شوند: پوشش کم، خطای ساخت
    """
    score: float | None
    source: str
    warnings: list


def _stamp(raw) -> str:
    """زمان ISO با منطقه زمانی به قالب گزارش؛ در غیر این صورت «زمان نامعلوم»."""
    if isinstance(raw, str):
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            return "زمان نامعلوم"
        if ts.tzinfo is not None:
            return ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return "زمان نامعلوم"


def _regime_warnings(doc: dict) -> list[str]:
    """
    هشدار میدان‌های اضافه‌ای که خواننده می‌فهمد. میدان شناخته‌شده با شکل
    نادرست هشدار «نامعتبر» می‌گیرد — نادیده‌گرفتنش بی‌صدا بود.
    """
    w = []
    lc = doc.get("low_coverage")
    if lc is not None:
        if not isinstance(lc, bool):
            w.append("⚠️ میدان low_coverage در regime.json نامعتبر است")
        elif lc:
            cov = doc.get("coverage")
            if (isinstance(cov, (int, float)) and not isinstance(cov, bool)
                    and math.isfinite(cov) and 0 <= cov <= 1):
                w.append(f"⚠️ پوشش کم ({100 * cov:.0f}٪) — امتیاز رژیم از بخش "
                         "کوچکی از وزن ورودی‌ها ساخته شده")
            else:
                w.append("⚠️ پوشش کم — درصد پوشش نامعلوم")
    lbe = doc.get("last_build_error")
    if lbe is not None:
        if not isinstance(lbe, dict) or not isinstance(lbe.get("error"), str):
            w.append("⚠️ میدان last_build_error در regime.json نامعتبر است")
        else:
            w.append(f"⚠️ آخرین ساخت رژیم خطا داد ({_stamp(lbe.get('at'))}): "
                     f"{lbe['error']} — رژیم این گزارش از ساخت موفق قبلی است")
    return w


def load_regime(path=REGIME_FILE, now: datetime | None = None) -> RegimeInfo:
    """
    امتیاز رژیم از regime.json، یا None با دلیل خوانا.

    هیچ استثنایی بالا نمی‌رود: فایل خراب هم «رژیم کهنه» است، با دلیل صریح
    در گزارش. سند خطا — میدان error در بالاترین سطح — همیشه کهنه است،
    حتی اگر امتیاز هم داشته باشد: محافظه‌کارانه‌تر.
    """
    now = now or datetime.now(UTC)
    name = os.path.basename(str(path))
    if not os.path.exists(path):
        return RegimeInfo(None, f"فایل {name} نیست", [])
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        return RegimeInfo(None, f"{name} خوانا نیست (`{type(exc).__name__}`)", [])
    if not isinstance(doc, dict):
        return RegimeInfo(None, f"{name} شیء JSON نیست", [])

    warns = _regime_warnings(doc)
    if "error" in doc:
        return RegimeInfo(None, f"ساخت رژیم خطا داد ({_stamp(doc.get('generated_at'))}): "
                                f"{doc['error']}", warns)

    score = doc.get("score")
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score)):
        return RegimeInfo(None, f"میدان score در {name} نیست یا عدد معتبر نیست", warns)

    raw_ts = doc.get("generated_at")
    if not isinstance(raw_ts, str):
        return RegimeInfo(None, f"میدان generated_at در {name} نیست", warns)
    try:
        ts = datetime.fromisoformat(raw_ts)
    except ValueError:
        return RegimeInfo(None, f"generated_at در {name} قابل‌خواندن نیست", warns)
    if ts.tzinfo is None:
        return RegimeInfo(None, f"generated_at در {name} منطقه زمانی ندارد", warns)

    age = now - ts
    if age < -REGIME_CLOCK_SKEW:
        return RegimeInfo(None, f"generated_at در {name} در آینده است", warns)
    if age > timedelta(days=REGIME_MAX_AGE_DAYS):
        return RegimeInfo(None, f"{name} {age.total_seconds() / 86400:.1f} روز عمر دارد — "
                                f"بیش از {fa(REGIME_MAX_AGE_DAYS)} روز", warns)
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return RegimeInfo(float(score), f"{name}، تولید {stamp}", warns)


# ─────────────────────── واکشی داده ───────────────────────

def _mark_confirm(df):
    """
    ستون confirm صادق: ۱ برای کندل بسته، ۰ برای کندل باز. سطر باز حذف
    نمی‌شود — قیمت زنده از همان می‌آید.

    اولویت با پرچم صرافی (اوکی‌اکس، ستون conf). اگر نبود، از زمان:
    کندلی بسته است که زمان باز شدنش به‌علاوه یک روز گذشته باشد — همان
    قاعده _df در radar_fetch3.py. پرچم پوچ یعنی باز؛ محافظه‌کارانه‌تر.
    """
    if "conf" in df.columns:
        df["confirm"] = (pd.to_numeric(df["conf"], errors="coerce")
                         .fillna(0).astype(int))
    else:
        now = pd.Timestamp.now(tz="UTC")
        df["confirm"] = ((df["ts"] + pd.Timedelta(days=1)) <= now).astype(int)
    return df


def okx_candles(symbol: str, bar: str = "1D", want: int = DAILY_WANT):
    """کندل روزانه از اوکی‌اکس. صرافی‌های دیگر از کولب مسدودند."""
    if requests is None or pd is None:
        return None
    inst = f"{symbol.upper()}-USDT"
    rows, after = [], None
    try:
        while len(rows) < want:
            p = {"instId": inst, "bar": bar, "limit": "100"}
            if after:
                p["after"] = after
            r = requests.get(f"{OKX}/api/v5/market/candles",
                             params=p, timeout=20)
            j = r.json()
            if j.get("code") != "0" or not j.get("data"):
                break
            batch = j["data"]
            rows.extend(batch)
            after = batch[-1][0]
            if len(batch) < 100:
                break
    except Exception:
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v",
                                     "vc", "vq", "conf"][:len(rows[0])])
    for col in ("o", "h", "l", "c", "v"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return _mark_confirm(df)



def gate_candles(symbol: str, want: int = DAILY_WANT):
    """
    کندل روزانه از گیت — منبع دوم.

    دلیل وجود: برخی نمادها در اوکی‌اکس نیستند. نمونه واقعی: TAO.
    بدون این تابع، آن نمادها «داده ندارم» می‌گیرند و ریسکشان
    ۱۰۰٪ شمرده می‌شود — حتی اگر سطح ابطال داشته باشند.

    ترتیب ستون‌های گیت متفاوت است:
        [زمان، حجم به ارز مظنه، بسته، بالا، پایین، باز، حجم پایه، ...]
    """
    if requests is None or pd is None:
        return None
    try:
        r = requests.get("https://api.gateio.ws/api/v4/spot/candlesticks",
                         params={"currency_pair": f"{symbol.upper()}_USDT",
                                 "interval": "1d",
                                 "limit": str(min(want, 1000))}, timeout=20)
        if r.status_code != 200:
            return None
        rows = r.json()
    except Exception:
        return None
    if not rows or len(rows) < 60:
        return None
    out = []
    for x in rows:
        try:
            out.append({"ts": int(float(x[0])) * 1000,
                        "c": float(x[2]), "h": float(x[3]),
                        "l": float(x[4]), "o": float(x[5]),
                        "v": float(x[6]) if len(x) > 6 else 0.0})
        except (ValueError, IndexError):
            continue
    if len(out) < 60:
        return None
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return _mark_confirm(df.sort_values("ts").reset_index(drop=True))


def candles(symbol: str, bar: str = "1D", want: int = DAILY_WANT):
    """اوکی‌اکس اول، گیت به‌عنوان جایگزین."""
    df = okx_candles(symbol, bar, want)
    if df is not None and len(df) >= 60:
        return df
    return gate_candles(symbol, want)


def _last_close(df) -> float | None:
    """
    آخرین قیمت بسته‌شدن از قاب کامل (ستون c) — یا None اگر تهی یا پوچ باشد.

    نسخه محلی `radar_fetch3.last_close` با نام ستون این فایل. ایمپورت
    نمی‌شود تا استقلال فایل نشکند. **هر تغییر اینجا باید در نسخه اصلی هم
    بیاید** — آزمون `test_book_guard_matches_canonical` این دو را قفل می‌کند.

    نگهبان `is None` کافی نیست: `float(nan)` مقدار `nan` می‌دهد نه `None`.
    اینجا پوچ بدتر از اسکن بود: هر مقایسه با nan نادرست است، پس ساختار
    «زیر همه میانگین‌ها» و قدرت نسبی کمینه می‌گرفت — امتیاز نزولی ساختگی
    که ضربه می‌سازد. مقدار بی‌نهایت هم پوچ حساب می‌شود.
    """
    if df is None or len(df) == 0 or "c" not in df.columns:
        return None
    try:
        v = float(df["c"].iloc[-1])
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi_wilder(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-12)
    return 100 - 100 / (1 + rs)


def score_position(df, btc, days_rs: int = 30) -> dict | None:
    """
    امتیاز ساده و شفاف بر پایه چهار بُعد مستقل (محافظ هم‌خطی بند ۵.۱):
        ساختار، مومنتوم، قدرت نسبی، موقعیت نسبت به میانگین بلند
    خروجی روی مقیاس منفی۲ تا مثبت۲.
    """
    if df is None or len(df) < 60:
        return None
    # قیمت از کندل زنده، ساختار از کندل بسته — قاعده radar_levels.py.
    # پیش از این همه اندیکاتورها کندل باز را می‌دیدند و شمارش بلوغ
    # کندل باز را هم حساب می‌کرد.
    closed = df[df["confirm"] == 1].reset_index(drop=True) \
        if "confirm" in df.columns else df
    if len(closed) < 60:
        return None
    c_full = df["c"]      # فقط قیمت زنده و قدرت نسبی — مورد اخیر مال نشست ۱۲
    c = closed["c"]
    # نگهبان پوچ: قیمت پوچ یعنی «داده ناکافی» در گزارش، نه امتیاز ساختگی
    px = _last_close(df)
    if px is None:
        return None
    e20, e50 = float(ema(c, 20).iloc[-1]), float(ema(c, 50).iloc[-1])
    mature = len(closed) >= EMA200_MATURE_BARS    # قانون بلوغ ۳n برای EMA200
    e200 = float(ema(c, 200).iloc[-1]) if len(closed) >= 200 else None
    r = float(rsi_wilder(c).iloc[-1])

    parts, notes = {}, []

    # ۱ — ساختار (بر پایه موقعیت نسبت به میانگین‌ها، نه اندیکاتور دوم)
    s = 0.0
    if px > e20:
        s += 0.5
    else:
        s -= 0.5
    if px > e50:
        s += 0.5
    else:
        s -= 0.5
    if e20 > e50:
        s += 0.5
    else:
        s -= 0.5
    if e200 is not None:
        if px > e200:
            s += 0.5
        else:
            s -= 0.5
        if not mature:
            # آستانه از همان ثابتی که منطق بالا می‌خواند — درس رویداد ۲۲
            notes.append(f"EMA200 نابالغ — کمتر از {fa(EMA200_MATURE_BARS)} کندل، قانون ۳n")
    parts["ساختار"] = max(-2, min(2, s))

    # ۲ — مومنتوم (فقط یک ابزار از خانواده شاخص قدرت نسبی)
    if r >= 60:
        m = 1.0
    elif r >= 50:
        m = 0.5
    elif r >= 40:
        m = -0.5
    elif r >= 30:
        m = -1.0
    else:
        m = -1.5
    parts["مومنتوم"] = m

    # ۳ — قدرت نسبی به بیت‌کوین
    rs = None
    if btc is not None and len(btc) > days_rs and len(df) > days_rs:
        a0, a1 = float(c_full.iloc[-days_rs - 1]), px
        b0, b1 = float(btc["c"].iloc[-days_rs - 1]), float(btc["c"].iloc[-1])
        if a0 > 0 and b0 > 0:
            rs = (a1 / a0 - 1) - (b1 / b0 - 1)
    if rs is None:
        parts["قدرت نسبی"] = None
        notes.append("قدرت نسبی: داده ندارم — از مخرج کم شد")
    else:
        if rs > 0.10:
            parts["قدرت نسبی"] = 2.0
        elif rs > 0.02:
            parts["قدرت نسبی"] = 1.0
        elif rs > -0.02:
            parts["قدرت نسبی"] = 0.0
        elif rs > -0.10:
            parts["قدرت نسبی"] = -1.0
        else:
            parts["قدرت نسبی"] = -2.0

    # ── جمع‌بندی با قانون سوگیری صفر: نبود داده از مخرج کم می‌شود
    w = {"ساختار": 0.45, "مومنتوم": 0.20, "قدرت نسبی": 0.35}
    num = sum(w[k] * v for k, v in parts.items() if v is not None)
    den = sum(w[k] for k, v in parts.items() if v is not None)
    score = num / den if den else 0.0

    return {"price": px, "score": round(score, 3), "rsi": round(r, 1),
            "rs30": round(rs, 4) if rs is not None else None,
            "e20": e20, "e50": e50, "e200": e200,
            "coverage": round(den * 100, 0), "parts": parts,
            "notes": notes, "mature": mature, "bars": len(closed)}


# ─────────────────────── وضعیت ماندگار ───────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"reviews": {}, "swaps": []}


def save_state(d: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# مبنای امتیاز سبد. هر تغییری در ورودی امتیاز — کندل، اندیکاتور، وزن —
# باید این شناسه را عوض کند. امتیاز دو مبنا مقایسه‌پذیر نیست و قانون
# سه‌ضربه هر امتیاز را با قبلی می‌سنجد، پس نخستین دور پس از تغییر فقط
# خط پایه ثبت می‌کند. نسخه ۱: کندل بسته و ۶۰۱ کندل — نشست ۱ رادار ۷.
SCORE_BASIS = "closed-candle-v1"


def begin_round(state: dict) -> bool:
    """
    آغاز هر دور بازبینی. اگر مبنای ذخیره‌شده با SCORE_BASIS فرق داشت:
    تاریخچه قبلی زیر archive بایگانی می‌شود، reviews خالی می‌شود تا
    امتیاز امروز خط پایه تازه باشد، و مبنا به‌روز می‌شود.

    خالی‌کردن لازم است، نه فقط افزودن: اگر تاریخچه مبنای قدیم کنار تازه
    بماند، زنجیره کاهش فردا از مرز دو مبنا رد می‌شود و ضربه ساختگی
    برمی‌گردد. خروجی True یعنی این دور خط پایه است و ضربه‌ای شمرده نمی‌شود.
    """
    old = state.get("score_basis")
    if old == SCORE_BASIS:
        return False
    if state.get("reviews"):
        state.setdefault("archive", []).append({
            "basis": old,
            "until": datetime.now(UTC).strftime("%Y-%m-%d"),
            "reviews": state["reviews"],
        })
    state["reviews"] = {}
    state["score_basis"] = SCORE_BASIS
    return True


def update_strikes(state: dict, sym: str, score: float | None) -> tuple[int, list]:
    """
    تاریخچه امتیاز را نگه می‌دارد و تعداد ضربه‌های متوالی را می‌شمارد.
    ضربه = امتیاز این بازبینی کمتر از بازبینی قبل.

    امتیاز خالی یعنی «داده ندارم» در این دور: تاریخچه دست نمی‌خورد — نه
    ورودی تازه، نه بازنویسی ورودی امروز. شمارش از همان تاریخچه دست‌نخورده
    می‌آید، پس ضربه تازه‌ای اضافه نمی‌شود و ضربه‌های قبلی هم صفر نمی‌شوند.
    پیش از این main به‌جای خالی صفر می‌فرستاد و صفر ضربه ساختگی می‌ساخت —
    نقض قانون سوگیری صفر. بازطراحی کامل منطق ضربه مال نشست ۱۲ است.
    """
    if score is None:
        hist = state["reviews"].get(sym, [])
    else:
        hist = state["reviews"].setdefault(sym, [])
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if hist and hist[-1]["date"] == today:
            hist[-1]["score"] = score
        else:
            hist.append({"date": today, "score": score})
        hist[:] = hist[-12:]

    strikes = 0
    for i in range(len(hist) - 1, 0, -1):
        if hist[i]["score"] < hist[i - 1]["score"]:
            strikes += 1
        else:
            break
    return strikes, hist


# ─────────────────────── گزارش ───────────────────────

def fmt(x, d=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.{d}f}".rstrip("0").rstrip(".")
    return str(x)


def _pnl(r: dict) -> str:
    """سود و زیان فقط وقتی قیمت خرید همه لات‌ها معلوم است — عدد ساخته نمی‌شود."""
    if r.get("avg_entry") and r.get("price"):
        return f"{100 * (r['price'] / r['avg_entry'] - 1):+.1f}٪"
    return "—"


def _verdict(r: dict) -> str:
    p, wk = r["pos"], r.get("weekly")
    inv = p.get("invalidation")
    if r.get("dust"):
        return "ناچیز"
    if inv is not None and wk is not None and wk["close"] < inv:
        return "⛔ خروج ۱۰۰٪ — بسته هفتگی زیر ابطال"
    if r["strikes"] >= 4:
        v = "⛔ خروج کامل (۴ ضربه)"
    elif r["strikes"] == 3:
        v = "🔻 کاهش ۵۰٪ اجباری"
    elif r["strikes"] == 2:
        v = "⚠️ آماده‌سازی کاهش"
    elif r["swap_edge"] and r["swap_edge"] >= SWAP_MIN_EDGE:
        v = f"🔄 چرخش به {r['swap_to']}"
    elif r["score"] is None:
        v = "داده ناکافی"
    elif r["score"] < -0.5:
        v = "⚠️ ضعیف — نامزد فروش"
    else:
        v = "نگه‌دار"
    if inv is not None and wk is None:
        v += " — ⚠️ بسته هفتگی: داده ندارم"
    return v


def build_report(h: dict, rows: list[dict], reg: dict | None,
                 candidates: list[dict], regime_note: str = "",
                 baseline: bool = False,
                 regime_warnings: list[str] | None = None,
                 val: dict | None = None, heat: dict | None = None,
                 reentry: list[dict] | None = None) -> str:
    """
    گزارش دو دفتر — تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶.

    دفتر موقعیت با سقف رژیم مقایسه نمی‌شود: سقف برای معامله کوتاه با حد
    ضرر طراحی شده و اعمال لفظی‌اش روی سبد بلندمدت یعنی فروش حدود ۹۰٪.
    ریسک تا ابطالش فقط گزارش می‌شود و هدف ذخیره رژیم روی کل سرمایه است.
    سقف رژیم فقط روی دفتر معامله.

    reg خالی یعنی رژیم کهنه یا غایب: هر سطر وابسته به رژیم برچسب «رژیم کهنه»
    می‌گیرد و هیچ باند جانشینی جا زده نمی‌شود. baseline یعنی این دور پس از
    تغییر مبنای امتیاز فقط خط پایه ثبت کرد. regime_warnings کنار رژیم دیده
    می‌شوند: بالای گزارش و در سطر «هشدار رژیم».
    """
    regime_warnings = regime_warnings or []
    val = val or {"total": 0.0, "stable_usd": 0.0, "incomplete": False, "missing": []}
    reentry = reentry or []
    o: list[str] = []
    W = o.append

    total, stable = val["total"], val["stable_usd"]
    stable_pct = stable / total * 100 if total else 0

    W("=" * 66)
    W(f"بازبینی سبد و موتور خروج — رادار {fa(VERSION)}")
    W(f"تاریخ: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    W("=" * 66)
    W("")
    if reg is None:
        W(f"⛔ **{REGIME_STALE}.** {regime_note}.")
        W("هر سطر وابسته به رژیم در این گزارش عدد ندارد. مقدار پیش‌فرض جا زده نشده است.")
        W("")
    for w in regime_warnings:
        W(w)
    if regime_warnings:
        W("")
    if baseline:
        W(f"ℹ️ **این دور خط پایه تازه است.** مبنای امتیاز عوض شده (`{SCORE_BASIS}`) "
          "و امتیاز امروز با دورهای پیشین مقایسه‌پذیر نیست. پس هیچ ضربه‌ای شمرده "
          "نشد. تاریخچه پیشین در `book_state.json` زیر `archive` بایگانی شد.")
        W("")

    live = [r for r in rows if not r.get("dust")]
    no_inval = [r["pos"]["symbol"] for r in live if r["pos"].get("invalidation") is None]
    pos_risk = 0.0
    for r in live:
        inv, v = r["pos"].get("invalidation"), r.get("value")
        if v is None:
            continue
        # قانون ۶.۰: پوزیشن بی‌ابطال، ریسکش ۱۰۰٪ ارزش آن است، نه صفر
        pos_risk += v if inv is None else r["qty"] * max(r["price"] - inv, 0.0)

    # ── ۱ سرمایه و ذخیره
    W("## ۱ — سرمایه و ذخیره")
    W("")
    W("دو دفتر: سقف ریسک رژیم فقط روی دفتر معامله است. دفتر موقعیت با آن مقایسه")
    W("نمی‌شود؛ هدف ذخیره رژیم روی کل سرمایه است.")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    cap_txt = f"{total:,.0f} دلار — ارزش زنده"
    if val["incomplete"]:
        cap_txt += f" — ⚠️ ناقص، بی‌قیمت: {'، '.join(val['missing'])}"
    W(f"| کل سرمایه | {cap_txt} |")
    W(f"| مقدارها از | {_stamp(h.get('updated'))} — {h.get('source', '—')} |")
    W(f"| ذخیره استیبل | {stable:,.0f} دلار ({stable_pct:.1f}٪) |")
    if reg is None:
        W(f"| رژیم | ⛔ {REGIME_STALE} |")
        W("| **هدف ذخیره استیبل رژیم** | رژیم کهنه |")
    else:
        W(f"| رژیم | {reg['name']} — سقف ریسک {reg['cap']}٪ |")
        W(f"| **هدف ذخیره استیبل رژیم** | **{reg['stable']}٪** |")
    W(f"| منبع رژیم | {regime_note or '—'} |")
    if regime_warnings:
        # خط عمودی داخل خانه جدول، جدول را می‌شکند
        cell = "؛ ".join(w.replace("|", "\\|") for w in regime_warnings)
        W(f"| هشدار رژیم | {cell} |")
    W(f"| ریسک دفتر موقعیت تا ابطال | {pos_risk:,.0f} دلار — فقط گزارش؛ با سقف رژیم "
      "مقایسه نمی‌شود. پوزیشن بی‌ابطال با ۱۰۰٪ ارزش |")
    W(f"| پوزیشن بدون سطح ابطال | {len(no_inval)} از {len(live)} — ناچیز شمرده نمی‌شود |")
    if heat is None:
        W("| **ریسک مؤثر دفتر معامله** | — سقف: رژیم کهنه |")
    else:
        W(f"| **ریسک مؤثر دفتر معامله** | **{heat['effective']:,.0f} دلار از سقف "
          f"{heat['cap_usd']:,.0f} دلار** ({reg['cap']}٪ کل سرمایه) |")
    W("")
    if reg is None:
        # حذف بی‌صدای این دو هشدار همان خطایی است که جلویش را می‌گیریم
        W("⚠️ **مقایسه ممکن نیست — رژیم کهنه است.** سقف دفتر معامله و کسری ذخیره "
          "استیبل حساب نشد.")
        W("")
    else:
        gap = reg["stable"] / 100 * total - stable
        if gap > 0:
            W(f"⚠️ ذخیره استیبل {stable_pct:.1f}٪ است، هدف رژیم {reg['stable']}٪ کل سرمایه.")
            W(f"**کسری: {gap:,.0f} دلار.** ترتیب فروش در بخش ۵.")
            W("")
    if no_inval:
        W(f"⚠️ این پوزیشن‌ها سطح ابطال ندارند: {'، '.join(no_inval)}")
        W("برای هرکدام یک سطح ساختاری هفتگی یا روزانه با دست‌کم دو برخورد بنویس.")
        W("")

    # ── ۲ دفتر موقعیت
    W("## ۲ — دفتر موقعیت")
    W("")
    W("ابطال با **بسته هفتگی به وقت جهانی**: هفته دوشنبه تا یکشنبه، بسته در")
    W("دوشنبه ۰۰:۰۰ UTC — اوکی‌اکس 1Wutc، گیت 7d. لنگر در دسترس نبود یعنی «داده ندارم».")
    W("سود و زیان فقط وقتی قیمت خرید همه لات‌ها معلوم است.")
    W("")
    W("| نماد | مقدار | قیمت | ارزش | سود/زیان٪ | امتیاز | ض | قدرت نسبی۳۰ | RSI | "
      "ابطال | بسته هفتگی | حکم |")
    W("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        p = r["pos"]
        r["verdict"] = _verdict(r)
        inv, wk = p.get("invalidation"), r.get("weekly")
        rs = f"{r['rs30'] * 100:+.1f}٪" if r["rs30"] is not None else "—"
        W(f"| {p['symbol']} | {fmt(r['qty'], 6)} | {fmt(r['price'])} | "
          f"{fmt(r.get('value'), 2)} | {_pnl(r)} | {fmt(r['score'], 2)} | {r['strikes']} | "
          f"{rs} | {fmt(r['rsi'], 1)} | "
          f"{fmt(inv) if inv is not None else '**ندارد**'} | "
          f"{fmt(wk['close']) if wk else '—'} | {r['verdict']} |")
    W("")
    W("ستون «ض» = تعداد ضربه‌های متوالی (بازبینی با امتیاز کاهشی).")
    W("سه ضربه ← کاهش ۵۰٪ اجباری. چهار ضربه ← خروج کامل. بدون استثنا.")
    W("")
    if reentry:
        W("### ورود دوباره — خارج‌شده با ابطال")
        W("")
        W("اگر بسته هفتگی دوباره بالای همان سطح رفت، ورود دوباره تا همان مقدار قبلی مجاز است.")
        W("")
        W("| نماد | سطح | سهمیه | مصرف‌شده | بسته هفتگی | حکم |")
        W("|---|---|---|---|---|---|")
        for e in reentry:
            st, wk = e["state"], e.get("weekly")
            left = st["max_qty"] - st["used"]
            if wk is None:
                v = "داده ندارم — بسته هفتگی"
            elif wk["close"] > st["level"]:
                v = f"✅ ورود دوباره مجاز — تا {fmt(left, 6)}"
            else:
                v = "هنوز زیر سطح"
            W(f"| {e['symbol']} | {fmt(st['level'])} | {fmt(st['max_qty'], 6)} | "
              f"{fmt(st['used'], 6)} | {fmt(wk['close']) if wk else '—'} | {v} |")
        W("")

    # ── ۳ دفتر معامله
    W("## ۳ — دفتر معامله")
    W("")
    trades = [p for p in h["positions"] if p["book"] == "trade" and p["status"] == "open"]
    if not trades:
        W("دفتر معامله خالی است. هر معامله تازه اینجا ثبت می‌شود — واقعی یا فرضی، با "
          "شناسه تصمیم و نام ستاپ در دفترچه.")
    else:
        W("| نماد | جهت | نوع | مقدار | ورود | حد ضرر | ریسک دلاری |")
        W("|---|---|---|---|---|---|---|")
        for p in trades:
            s = 1 if p.get("side", "long") == "long" else -1
            risk = sum(l["qty"] * s * (l["entry"] - p["stop"]) for l in p["lots"])
            entry = p["lots"][0]["entry"] if len(p["lots"]) == 1 else None
            qty = sum(l["qty"] for l in p["lots"])
            W(f"| {p['symbol']} | {p.get('side', 'long')} | "
              f"{'فرضی' if p.get('paper') else 'واقعی'} | {fmt(qty, 6)} | "
              f"{fmt(entry)} | {fmt(p['stop'])} | {risk:,.2f} |")
        W("")
        if heat is None:
            W("⚠️ سقف دفتر معامله معلوم نیست — رژیم کهنه است.")
        else:
            W("| مورد | مقدار |")
            W("|---|---|")
            W(f"| ریسک واقعی | {heat['risk_real']:,.2f} دلار |")
            W(f"| ضریب همبستگی | {heat['corr']:.2f} — از سه لانگ آلت هم‌زمان به بالا، "
              "بند ۸.۳ اسکیل |")
            W(f"| ریسک مؤثر | {heat['effective']:,.2f} دلار |")
            W(f"| سقف | {heat['cap_usd']:,.2f} دلار — {reg['cap']}٪ کل سرمایه |")
            W(f"| پوزیشن هم‌جهت | لانگ {heat['long_count']} از {heat['maxpos']}، "
              f"شورت {heat['short_count']} از {heat['maxpos']} |")
            W(f"| ریسک فرضی — جدا، نه در سرمایه و نه در حرارت | {heat['risk_paper']:,.2f} دلار |")
            W("")
            if heat["over_cap"] or heat["over_maxpos"]:
                why = []
                if heat["over_cap"]:
                    why.append("ریسک مؤثر بالای سقف")
                if heat["over_maxpos"]:
                    why.append("بیش از حداکثر پوزیشن هم‌جهت")
                W(f"⛔ **ورود تازه در دفتر معامله مجاز نیست** — {'، '.join(why)}.")
    W("")

    # ── ۴ جانشینی
    W("## ۴ — آزمون جانشینی")
    W("")
    if not candidates:
        W("نامزدی داده نشد. برای فعال‌کردن: `--candidates BTC,XAUT,HYPE`")
        W("یا خروجی `radar_rotate.py --deep` را به‌عنوان منبع نامزد استفاده کن.")
    else:
        W("**اصل:** چرخش، ریسک جدید خالص اضافه نمی‌کند — پس تابع دروازه رژیم نیست.")
        W("این تنها اقدامی است که در رژیم بحرانی هم بدون سقف مجاز است.")
        W("")
        W("| نامزد | امتیاز | بهترین جفت | امتیاز موجود | مزیت | حکم |")
        W("|---|---|---|---|---|---|")
        for c in candidates:
            if c["score"] is None:
                continue
            worst = min((r for r in live if r["score"] is not None),
                        key=lambda r: r["score"], default=None)
            if worst is None:
                continue
            edge = c["score"] - worst["score"] - SWAP_COST_SCORE
            if edge >= SWAP_MIN_EDGE:
                v = "✅ اجرا"
            elif edge >= SWAP_WATCH_EDGE:
                v = "نامزد — تأیید هفته بعد"
            else:
                v = "نگه‌دار"
            W(f"| {c['symbol']} | {c['score']:+.2f} | {worst['pos']['symbol']} | "
              f"{worst['score']:+.2f} | {edge:+.2f} | {v} |")
        W("")
        W(f"مزیت = امتیاز نامزد − امتیاز موجود − {fa(SWAP_COST_SCORE)} "
          f"(هزینه تعویض).")
        W(f"آستانه اجرا: {fa(SWAP_MIN_EDGE)}. "
          f"حداکثر {fa(MAX_SWAPS_WEEK)} تعویض در هفته.")
        W(f"حداقل دوره نگهداری پیش از تعویض: {fa(MIN_HOLD_DAYS)} روز.")
        W("نامزد باید آزمون پامپ کاذب را رد کند: `radar_rotate.py --deep`")
    W("")

    # ── ۵ ترتیب فروش
    W("## ۵ — ترتیب فروش هنگام ساخت ذخیره")
    W("")
    W("**هرگز بر اساس میزان ضرر مرتب نکن.** میزان ضرر واقعیتی درباره گذشته است")
    W("و هیچ اطلاعاتی درباره آینده ندارد. **هرگز برنده را اول نفروش** (اثر تمایل).")
    W("پوزیشن ناچیز در این فهرست نیست.")
    W("")

    def sell_key(r):
        p = r["pos"]
        return (
            0 if r["strikes"] >= 3 else 1,
            0 if p.get("invalidation") is None else 1,
            r["score"] if r["score"] is not None else 0,
            r["rs30"] if r["rs30"] is not None else 0,
        )

    order = sorted(live, key=sell_key)
    W("| اولویت | نماد | ارزش | دلیل |")
    W("|---|---|---|---|")
    for i, r in enumerate(order, 1):
        p = r["pos"]
        why = []
        if r["strikes"] >= 3:
            why.append(f"{r['strikes']} ضربه متوالی")
        if p.get("invalidation") is None:
            why.append("بدون سطح ابطال")
        if r["score"] is not None and r["score"] < 0:
            why.append(f"امتیاز {r['score']:+.2f}")
        if r["rs30"] is not None and r["rs30"] < 0:
            why.append(f"قدرت نسبی {r['rs30']*100:+.1f}٪")
        if not why:
            why.append("سطح ابطال دارد — ریسک محدود" if p.get("invalidation") is not None
                       else "هیچ نشانه ضعفی ندارد")
        W(f"| {i} | {p['symbol']} | {fmt(r.get('value'), 0)} دلار | {'، '.join(why)} |")
    W("")

    # ── ۶ فهرست اقدام امروز
    W("## ۶ — فهرست اقدام امروز")
    W("")
    actions: list[str] = []
    for r in live:
        p = r["pos"]
        if r["verdict"].startswith("⛔"):
            actions.append(f"**{p['symbol']}** — خروج کامل. {r['verdict'][2:]}. ثبت با "
                           "`radar_positions.py exit`")
        elif r["verdict"].startswith("🔻"):
            half = (r["value"] or 0) / 2
            actions.append(f"**{p['symbol']}** — کاهش حداقل ۵۰٪ "
                           f"(حدود {half:,.0f} دلار). سه ضربه متوالی")
        elif r["verdict"].startswith("🔄"):
            actions.append(f"**{p['symbol']}** — چرخش به {r['swap_to']}، "
                           f"مزیت {r['swap_edge']:+.2f}")
    for e in reentry:
        wk = e.get("weekly")
        if wk is not None and wk["close"] > e["state"]["level"]:
            actions.append(f"**{e['symbol']}** — ورود دوباره مجاز است؛ ثبت با "
                           "`radar_positions.py reenter`")
    if reg is not None:
        gap = reg["stable"] / 100 * total - stable
        if gap > 0:
            actions.append(f"**ذخیره استیبل** — فروش {gap:,.0f} دلار به ترتیب بخش ۵، "
                           "ثبت با `radar_positions.py trim --reason reserve`")
    if heat is not None and (heat["over_cap"] or heat["over_maxpos"]):
        actions.append("**دفتر معامله** — ورود تازه مجاز نیست تا ریسک زیر سقف برگردد")
    for s in no_inval:
        actions.append(f"**{s}** — نوشتن سطح ابطال ساختاری (هفتگی یا روزانه) و ثبت آن")

    if actions:
        for i, a in enumerate(actions, 1):
            W(f"{i}. {a}")
    else:
        W("هیچ اقدام اجباری‌ای فعال نشد. **ولی خروجی خالی مجاز نیست.**")
        W("چهار اقدام همیشه‌مجاز (کتابچه رژیم):")
        W("")
        W("- گذاشتن سفارش در انتظار روی سطح ساختاری، بالای نقطه ابطال")
        W("- گذاشتن هشدار قیمتی با عدد دقیق")
        W("- کاهش پله‌ای ضعیف‌ترین پوزیشن")
        if reg is None:
            W("- افزایش ذخیره استیبل — هدف رژیم پس از بازمحاسبه معلوم می‌شود")
        else:
            W(f"- افزایش ذخیره استیبل به سمت هدف رژیم ({reg['stable']}٪)")
    W("")
    W("---")
    W("")
    W("**ثبت اجباری:** هر تغییر مقدار فقط با `radar_positions.py` و یک ردیف دفتر کل.")
    W("هر اقدام انجام‌شده در `radar_journal.py` و هر اقدام **انجام‌نشده** در دفتر هزینه")
    W("فرصت ثبت شود. بدون هر دو، نرخ اقدام قابل محاسبه نیست.")

    return "\n".join(o)


# ─────────────────────── اجرا ───────────────────────

def sample_holdings() -> dict:
    """نمونه قالب ۲ — بر پایه مقدار. با موجودی واقعی جایگزین کن."""
    now = datetime.now(UTC)
    return {"version": 2, "updated": now.isoformat(),
            "source": "نمونه — با موجودی واقعی جایگزین کن",
            "frozen": {"date": now.strftime("%Y-%m-%d"), "members": {"SOL": 1.0}},
            "cash": [{"asset": "USDT", "qty": 0.0, "account": "صرافی"}],
            "positions": [{"symbol": "SOL", "book": "position", "status": "open",
                           "lots": [{"qty": 1.0, "account": "صرافی", "entry": None}],
                           "invalidation": None}],
            "ledger": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=f"بازبینی سبد و موتور خروج — رادار {fa(VERSION)}")
    ap.add_argument("--holdings", default="holdings.json")
    ap.add_argument("--journal", default=None, help="پیش‌فرض radar_journal.json")
    # پیش‌فرض خالی است، نه عدد: پیش از این 0.0 بود و اجرای بی‌کلید بی‌صدا
    # «سازنده» می‌گرفت
    ap.add_argument("--regime", type=float, default=None,
                    help="امتیاز رژیم دستی — بر regime.json مقدم است")
    ap.add_argument("--regime-file", default=REGIME_FILE,
                    help="فایل رژیم؛ اگر نبود یا کهنه بود، گزارش «رژیم کهنه» می‌گوید")
    ap.add_argument("--candidates", default="", help="نمادهای نامزد جانشینی، جدا با کاما")
    ap.add_argument("--init", action="store_true", help="ساخت فایل نمونه holdings.json")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.init:
        with open(a.holdings, "w", encoding="utf-8") as f:
            json.dump(sample_holdings(), f, ensure_ascii=False, indent=2)
        print(f"فایل نمونه ساخته شد: {a.holdings}")
        print("آن را با موجودی واقعی پر کن، سپس دوباره اجرا کن.")
        return 0

    # قالب ۲ و ناوردای دفتر کل — هر نقض خطای صریح، نه خواندن غلط
    try:
        h, _journal = P.load(a.holdings, a.journal)
    except P.PositionsError as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 2

    if requests is None or pd is None:
        print("کتابخانه requests یا pandas نصب نیست: pip install requests pandas")
        return 1

    # کلید دستی، سپس فایل تازه، سپس «رژیم کهنه» — بدون مقدار جانشین
    if a.regime is not None:
        info = RegimeInfo(a.regime, "دستی (کلید `--regime`)", [])
    else:
        info = load_regime(a.regime_file)
    reg = regime_row(info.score) if info.score is not None else None
    if reg is None:
        print(f"⚠️ {REGIME_STALE}: {info.source}")
    for w in info.warnings:
        print(w)
    state = load_state()
    # مبنای امتیاز عوض شده باشد، این دور فقط خط پایه است — بدون ضربه
    baseline = begin_round(state)
    if baseline:
        print(f"ℹ️ مبنای امتیاز عوض شده ({SCORE_BASIS}) — این دور فقط خط پایه ثبت می‌شود")

    print("واکشی داده بیت‌کوین به‌عنوان مرجع قدرت نسبی...")
    btc = candles("BTC")

    prices: dict = {}
    frames: dict = {}
    for p in h["positions"]:
        if p["status"] != "open" or p["symbol"] in frames:
            continue
        print(f"  واکشی {p['symbol']}...")
        df = candles(p["symbol"])
        frames[p["symbol"]] = df
        prices[p["symbol"]] = _last_close(df) if df is not None else None
    val = P.value(h, prices)
    vrow = {r["symbol"]: r for r in val["rows"] if r["book"] == "position"}

    rows = []
    for p in h["positions"]:
        if p["book"] != "position" or p["status"] != "open":
            continue
        sym = p["symbol"]
        sc = score_position(frames.get(sym), btc)
        score = sc["score"] if sc else None
        # امتیاز خالی همان خالی می‌رود، نه صفر — صفر ضربه ساختگی می‌ساخت
        strikes, _ = update_strikes(state, sym, score)
        # بسته هفتگی به لنگر وقت جهانی — فقط از radar_positions، یک منبع
        wk, why = (P.weekly_close(sym) if p.get("invalidation") is not None
                   else (None, []))
        v = vrow.get(sym, {})
        rows.append({
            "pos": p, "qty": P.position_qty(p),
            "price": prices.get(sym), "value": v.get("value"),
            "dust": v.get("dust", False), "avg_entry": v.get("avg_entry"),
            "score": score,
            "rsi": sc["rsi"] if sc else None,
            "rs30": sc["rs30"] if sc else None,
            "strikes": strikes, "weekly": wk, "weekly_why": why,
            "swap_edge": None, "swap_to": None,
        })

    reentry = []
    for p in h["positions"]:
        if p["book"] == "position" and p["status"] == "exited":
            st = P.reentry_state(h, p["symbol"])
            if st is None:
                continue
            wk, why = P.weekly_close(p["symbol"])
            reentry.append({"symbol": p["symbol"], "state": st, "weekly": wk, "why": why})

    cands = []
    for s in [x.strip().upper() for x in a.candidates.split(",") if x.strip()]:
        print(f"  واکشی نامزد {s}...")
        sc = score_position(candles(s), btc)
        cands.append({"symbol": s, "score": sc["score"] if sc else None})

    # بهترین جفت جانشینی برای هر پوزیشن
    if cands:
        best = max((c for c in cands if c["score"] is not None),
                   key=lambda c: c["score"], default=None)
        if best:
            for r in rows:
                if r["score"] is None:
                    continue
                edge = best["score"] - r["score"] - SWAP_COST_SCORE
                r["swap_edge"] = round(edge, 3)
                r["swap_to"] = best["symbol"]

    heat = P.trade_heat(h, reg, val["total"]) if reg is not None else None
    save_state(state)
    txt = build_report(h, rows, reg, cands, info.source, baseline,
                       info.warnings, val=val, heat=heat, reentry=reentry)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\nذخیره شد در {a.out}")
    print("\n" + txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
