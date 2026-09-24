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

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

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

# ─────────── جدول رژیم (هم‌راستا با radar_size.py و risk-budget.md) ───────────
REGIMES = [
    (0.50,  "انبساطی", 8.0, 1.00, 5, 10),
    (0.00,  "سازنده",  6.0, 0.75, 4, 15),
    (-0.50, "محتاط",   4.0, 0.50, 3, 25),
    (-1.20, "انقباضی", 2.5, 0.30, 2, 40),
    (-99.0, "بحرانی",  1.5, 0.20, 1, 55),
]

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


def load_regime(path=REGIME_FILE, now: datetime | None = None
                ) -> tuple[float | None, str]:
    """
    امتیاز رژیم از regime.json، یا None با دلیل خوانا.

    خروجی دوم در حالت سالم منبع است، در حالت خراب دلیل. هیچ استثنایی
    بالا نمی‌رود: فایل خراب هم «رژیم کهنه» است، با دلیل صریح در گزارش.
    """
    now = now or datetime.now(UTC)
    name = os.path.basename(str(path))
    if not os.path.exists(path):
        return None, f"فایل {name} نیست"
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        return None, f"{name} خوانا نیست (`{type(exc).__name__}`)"
    if not isinstance(doc, dict):
        return None, f"{name} شیء JSON نیست"

    score = doc.get("score")
    if (isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score)):
        return None, f"میدان score در {name} نیست یا عدد معتبر نیست"

    raw_ts = doc.get("generated_at")
    if not isinstance(raw_ts, str):
        return None, f"میدان generated_at در {name} نیست"
    try:
        ts = datetime.fromisoformat(raw_ts)
    except ValueError:
        return None, f"generated_at در {name} قابل‌خواندن نیست"
    if ts.tzinfo is None:
        return None, f"generated_at در {name} منطقه زمانی ندارد"

    age = now - ts
    if age < -REGIME_CLOCK_SKEW:
        return None, f"generated_at در {name} در آینده است"
    if age > timedelta(days=REGIME_MAX_AGE_DAYS):
        return None, (f"{name} {age.total_seconds() / 86400:.1f} روز عمر دارد — "
                      f"بیش از {fa(REGIME_MAX_AGE_DAYS)} روز")
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return float(score), f"{name}، تولید {stamp}"


def regime_row(score: float) -> dict:
    for floor, name, cap, mult, maxpos, stable in REGIMES:
        if score >= floor:
            return {"name": name, "cap": cap, "mult": mult,
                    "maxpos": maxpos, "stable": stable}
    return {"name": "بحرانی", "cap": 1.5, "mult": 0.20, "maxpos": 1, "stable": 55}


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


def update_strikes(state: dict, sym: str, score: float) -> tuple[int, list]:
    """
    تاریخچه امتیاز را نگه می‌دارد و تعداد ضربه‌های متوالی را می‌شمارد.
    ضربه = امتیاز این بازبینی کمتر از بازبینی قبل.
    """
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


def build_report(book: dict, rows: list[dict], reg: dict | None,
                 candidates: list[dict], regime_note: str = "") -> str:
    """
    reg خالی یعنی رژیم کهنه یا غایب. آن‌وقت هر سطر وابسته به رژیم برچسب
    «رژیم کهنه» می‌گیرد و هیچ باند جانشینی جا زده نمی‌شود. regime_note
    در حالت سالم منبع رژیم است، در حالت کهنه دلیل آن.
    """
    o: list[str] = []
    W = o.append

    total = book.get("balance_total") or sum(p["size_usd"] for p in book["positions"])
    stable = book.get("stable_usd", 0.0)
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

    # ── ۱ حرارت واقعی سبد
    W("## ۱ — حرارت واقعی سبد")
    W("")
    W("قانون ۶.۰: پوزیشن اسپات **بدون سطح ابطال**، ریسکش ۱۰۰٪ اندازه آن پوزیشن است،")
    W("نه صفر. این همان محاسبه‌ای است که ۵.۴ نداشت.")
    W("")
    heat_usd = 0.0
    no_inval = []
    for r in rows:
        p = r["pos"]
        if p.get("invalidation"):
            d = abs(r["price"] - p["invalidation"]) / r["price"] if r["price"] else 1.0
            risk = p["size_usd"] * min(d, 1.0)
        else:
            risk = p["size_usd"]
            no_inval.append(p["symbol"])
        r["risk_usd"] = risk
        heat_usd += risk

    n_alt = sum(1 for r in rows if r["pos"]["symbol"].upper() not in ("BTC", "XAUT", "PAXG"))
    corr = {0: 1.0, 1: 1.00, 2: 1.20, 3: 1.40}.get(n_alt, 1.60)
    heat_pct = heat_usd / total * 100 if total else 0

    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| کل موجودی | {total:,.0f} دلار |")
    W(f"| ذخیره استیبل | {stable:,.0f} دلار ({stable_pct:.1f}٪) |")
    if reg is None:
        W(f"| رژیم | ⛔ {REGIME_STALE} |")
        W("| **هدف ذخیره استیبل رژیم** | رژیم کهنه |")
    else:
        W(f"| رژیم | {reg['name']} — سقف ریسک {reg['cap']}٪ |")
        W(f"| **هدف ذخیره استیبل رژیم** | **{reg['stable']}٪** |")
    W(f"| منبع رژیم | {regime_note or '—'} |")
    W(f"| ریسک اسمی باز | {heat_usd:,.0f} دلار ({heat_pct:.1f}٪) |")
    W(f"| ضریب همبستگی ({n_alt} آلت) | {corr:.2f} |")
    if reg is None:
        W(f"| **ریسک مؤثر** | **{heat_pct*corr:.1f}٪** — سقف: رژیم کهنه |")
    else:
        W(f"| **ریسک مؤثر** | **{heat_pct*corr:.1f}٪ از سقف {reg['cap']}٪** |")
    W(f"| پوزیشن بدون سطح ابطال | {len(no_inval)} از {len(rows)} |")
    W("")
    if reg is None:
        # حذف بی‌صدای این دو هشدار همان خطایی است که جلویش را می‌گیریم
        W("⚠️ **مقایسه ممکن نیست — رژیم کهنه است.** حرارت با سقف رژیم سنجیده "
          "نشد و کسری ذخیره استیبل حساب نشد.")
        W("")
    elif heat_pct * corr > reg["cap"]:
        W(f"⛔ **حرارت سبد {heat_pct*corr:.1f}٪ است، بیش از سقف رژیم {reg['cap']}٪.**")
        W("")
        W("**این عدد را درست بخوان.** سقف رژیم بر «ریسک جدید خالص» حاکم است.")
        W("پس معنی این هشدار سه چیز است، نه بیشتر:")
        W("")
        W("| هست | نیست |")
        W("|---|---|")
        W("| ورود جدید مجاز نیست | «همه را همین امروز بفروش» |")
        W("| کاهش، چرخش و ساخت ذخیره مجازند | چرخش هم ممنوع است |")
        W("| مسیر بازگشت به سقف، بخش ۴ و ۵ است | باید منتظر رژیم بهتر ماند |")
        W("")
        W("علت اصلی این عدد معمولاً پوزیشن اسپات بدون سطح ابطال است که با")
        W("ریسک ۱۰۰٪ شمرده می‌شود. با نوشتن ابطال برای هر پوزیشن، عدد واقعی‌تر می‌شود.")
        W("")
    if reg is not None and stable_pct < reg["stable"]:
        gap = (reg["stable"] - stable_pct) / 100 * total
        W(f"⚠️ ذخیره استیبل {stable_pct:.1f}٪ است، هدف رژیم {reg['stable']}٪.")
        W(f"**کسری: {gap:,.0f} دلار.** ترتیب فروش در بخش ۴.")
        W("")
    if no_inval:
        W(f"⚠️ این پوزیشن‌ها سطح ابطال ندارند: {'، '.join(no_inval)}")
        W("برای هرکدام یک سطح ساختاری روزانه یا هفتگی بنویس.")
        W("پوزیشنی که نتوانی برایش ابطال بنویسی، تز ندارد — و باید بسته شود.")
        W("")

    # ── ۲ جدول پوزیشن‌ها
    W("## ۲ — چهار آزمون هر پوزیشن")
    W("")
    W("| نماد | قیمت | امتیاز | ض | قدرت نسبی۳۰ | RSI | ابطال | حکم |")
    W("|---|---|---|---|---|---|---|---|")
    for r in rows:
        p = r["pos"]
        inv = p.get("invalidation")
        inv_txt = fmt(inv) if inv else "**ندارد**"
        broken = False
        if inv and r["price"]:
            broken = (r["price"] < inv) if p.get("side", "long") == "long" else (r["price"] > inv)
        if broken:
            verdict = "⛔ خروج ۱۰۰٪"
        elif r["strikes"] >= 4:
            verdict = "⛔ خروج کامل (۴ ضربه)"
        elif r["strikes"] == 3:
            verdict = "🔻 کاهش ۵۰٪ اجباری"
        elif r["strikes"] == 2:
            verdict = "⚠️ آماده‌سازی کاهش"
        elif r["swap_edge"] and r["swap_edge"] >= SWAP_MIN_EDGE:
            verdict = f"🔄 چرخش به {r['swap_to']}"
        elif r["score"] is None:
            verdict = "داده ناکافی"
        elif r["score"] < -0.5:
            verdict = "⚠️ ضعیف — نامزد فروش"
        else:
            verdict = "نگه‌دار"
        r["verdict"] = verdict
        W(f"| {p['symbol']} | {fmt(r['price'])} | "
          f"{r['score']:+.2f} | {r['strikes']} | "
          f"{(r['rs30']*100):+.1f}٪ | {fmt(r['rsi'],1)} | {inv_txt} | {verdict} |"
          if r["score"] is not None and r["rs30"] is not None else
          f"| {p['symbol']} | {fmt(r['price'])} | "
          f"{fmt(r['score'],2)} | {r['strikes']} | — | {fmt(r['rsi'],1)} | {inv_txt} | {verdict} |")
    W("")
    W("ستون «ض» = تعداد ضربه‌های متوالی (بازبینی با امتیاز کاهشی).")
    W("سه ضربه ← کاهش ۵۰٪ اجباری. چهار ضربه ← خروج کامل. بدون استثنا.")
    W("")

    # ── ۳ جانشینی
    W("## ۳ — آزمون جانشینی")
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
            worst = min((r for r in rows if r["score"] is not None),
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

    # ── ۴ ترتیب فروش
    W("## ۴ — ترتیب فروش هنگام ساخت ذخیره")
    W("")
    W("**هرگز بر اساس میزان ضرر مرتب نکن.** میزان ضرر واقعیتی درباره گذشته است")
    W("و هیچ اطلاعاتی درباره آینده ندارد. **هرگز برنده را اول نفروش** (اثر تمایل).")
    W("")

    def sell_key(r):
        p = r["pos"]
        return (
            0 if r["strikes"] >= 3 else 1,
            0 if not p.get("invalidation") else 1,
            r["score"] if r["score"] is not None else 0,
            r["rs30"] if r["rs30"] is not None else 0,
        )

    order = sorted(rows, key=sell_key)
    W("| اولویت | نماد | اندازه | دلیل |")
    W("|---|---|---|---|")
    for i, r in enumerate(order, 1):
        p = r["pos"]
        why = []
        if r["strikes"] >= 3:
            why.append(f"{r['strikes']} ضربه متوالی")
        if not p.get("invalidation"):
            why.append("بدون سطح ابطال")
        if r["score"] is not None and r["score"] < 0:
            why.append(f"امتیاز {r['score']:+.2f}")
        if r["rs30"] is not None and r["rs30"] < 0:
            why.append(f"قدرت نسبی {r['rs30']*100:+.1f}٪")
        W(f"| {i} | {p['symbol']} | {p['size_usd']:,.0f} دلار | "
          f"{'، '.join(why) if why else ('سطح ابطال دارد — ریسک محدود' if p.get('invalidation') else 'هیچ نشانه ضعفی ندارد')} |")
    W("")

    # ── ۵ فهرست اقدام امروز
    W("## ۵ — فهرست اقدام امروز")
    W("")
    actions: list[str] = []
    for r in rows:
        p = r["pos"]
        if r["verdict"].startswith("⛔"):
            actions.append(f"**{p['symbol']}** — خروج کامل. {r['verdict'][2:]}")
        elif r["verdict"].startswith("🔻"):
            actions.append(f"**{p['symbol']}** — کاهش حداقل ۵۰٪ "
                           f"(حدود {p['size_usd']/2:,.0f} دلار). سه ضربه متوالی")
        elif r["verdict"].startswith("🔄"):
            actions.append(f"**{p['symbol']}** — چرخش به {r['swap_to']}، "
                           f"مزیت {r['swap_edge']:+.2f}")
    if reg is not None and stable_pct < reg["stable"]:
        gap = (reg["stable"] - stable_pct) / 100 * total
        actions.append(f"**ذخیره استیبل** — فروش {gap:,.0f} دلار به ترتیب بخش ۴")
    for r in rows:
        if not r["pos"].get("invalidation"):
            actions.append(f"**{r['pos']['symbol']}** — نوشتن سطح ابطال ساختاری "
                           f"(روزانه یا هفتگی) و ثبت آن")

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
    W("**ثبت اجباری:** هر اقدام انجام‌شده در `radar_journal.py` و هر اقدام")
    W("**انجام‌نشده** در دفتر هزینه فرصت ثبت شود. بدون هر دو، نرخ اقدام")
    W("قابل محاسبه نیست و نمی‌فهمیم چارچوب سخت‌گیر است یا شل.")

    return "\n".join(o)


# ─────────────────────── اجرا ───────────────────────

SAMPLE = {
    "balance_total": 2500,
    "stable_usd": 0,
    "positions": [
        {"symbol": "SOL",  "size_usd": 210, "entry": 0, "invalidation": None,
         "side": "long", "spot": True},
        {"symbol": "HYPE", "size_usd": 180, "entry": 0, "invalidation": None,
         "side": "long", "spot": True},
        {"symbol": "ONDO", "size_usd": 120, "entry": 0, "invalidation": None,
         "side": "long", "spot": True},
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=f"بازبینی سبد و موتور خروج — رادار {fa(VERSION)}")
    ap.add_argument("--holdings", default="holdings.json")
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
            json.dump(SAMPLE, f, ensure_ascii=False, indent=2)
        print(f"فایل نمونه ساخته شد: {a.holdings}")
        print("آن را با موجودی واقعی پر کن، سپس دوباره اجرا کن.")
        return 0

    if not os.path.exists(a.holdings):
        print(f"فایل {a.holdings} پیدا نشد. برای ساخت نمونه: --init")
        return 1
    with open(a.holdings, encoding="utf-8") as f:
        book = json.load(f)

    if requests is None or pd is None:
        print("کتابخانه requests یا pandas نصب نیست: pip install requests pandas")
        return 1

    # کلید دستی، سپس فایل تازه، سپس «رژیم کهنه» — بدون مقدار جانشین
    if a.regime is not None:
        score, regime_note = a.regime, "دستی (کلید `--regime`)"
    else:
        score, regime_note = load_regime(a.regime_file)
    reg = regime_row(score) if score is not None else None
    if reg is None:
        print(f"⚠️ {REGIME_STALE}: {regime_note}")
    state = load_state()

    print("واکشی داده بیت‌کوین به‌عنوان مرجع قدرت نسبی...")
    btc = candles("BTC")

    rows = []
    for p in book["positions"]:
        print(f"  واکشی {p['symbol']}...")
        df = candles(p["symbol"])
        sc = score_position(df, btc)
        score = sc["score"] if sc else None
        strikes, _ = update_strikes(state, p["symbol"], score if score is not None else 0.0)
        rows.append({
            "pos": p,
            "price": sc["price"] if sc else None,
            "score": score,
            "rsi": sc["rsi"] if sc else None,
            "rs30": sc["rs30"] if sc else None,
            "coverage": sc["coverage"] if sc else 0,
            "strikes": strikes,
            "swap_edge": None,
            "swap_to": None,
        })

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

    save_state(state)
    txt = build_report(book, rows, reg, cands, regime_note)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\nذخیره شد در {a.out}")
    print("\n" + txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
