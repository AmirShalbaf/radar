#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_book.py — موتور بازبینی سبد و خروج، رادار ۶.۰
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
import os
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None

try:
    import pandas as pd
except ImportError:
    pd = None

VERSION = "6.0"
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

SWAP_COST_SCORE = 0.15    # هزینه تعویض بر حسب واحد امتیاز
SWAP_MIN_EDGE = 0.50      # آستانه اجرای جانشینی
SWAP_WATCH_EDGE = 0.30    # آستانه نامزدی
MAX_SWAPS_WEEK = 2
MIN_HOLD_DAYS = 10


def regime_row(score: float) -> dict:
    for floor, name, cap, mult, maxpos, stable in REGIMES:
        if score >= floor:
            return {"name": name, "cap": cap, "mult": mult,
                    "maxpos": maxpos, "stable": stable}
    return {"name": "بحرانی", "cap": 1.5, "mult": 0.20, "maxpos": 1, "stable": 55}


# ─────────────────────── واکشی داده ───────────────────────

def okx_candles(symbol: str, bar: str = "1D", want: int = 260):
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
    return df


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
    c = df["c"]
    px = float(c.iloc[-1])
    e20, e50 = float(ema(c, 20).iloc[-1]), float(ema(c, 50).iloc[-1])
    mature = len(df) >= 600          # قانون بلوغ ۳n برای EMA200
    e200 = float(ema(c, 200).iloc[-1]) if len(df) >= 200 else None
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
            notes.append("EMA200 نابالغ — کمتر از ۶۰۰ کندل، قانون ۳n")
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
        a0, a1 = float(c.iloc[-days_rs - 1]), px
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
            "notes": notes, "mature": mature, "bars": len(df)}


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


def build_report(book: dict, rows: list[dict], reg: dict,
                 candidates: list[dict]) -> str:
    o: list[str] = []
    W = o.append

    total = book.get("balance_total") or sum(p["size_usd"] for p in book["positions"])
    stable = book.get("stable_usd", 0.0)
    stable_pct = stable / total * 100 if total else 0

    W("=" * 66)
    W(f"بازبینی سبد و موتور خروج — رادار {VERSION}")
    W(f"تاریخ: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    W("=" * 66)
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
    W(f"| رژیم | {reg['name']} — سقف ریسک {reg['cap']}٪ |")
    W(f"| **هدف ذخیره استیبل رژیم** | **{reg['stable']}٪** |")
    W(f"| ریسک اسمی باز | {heat_usd:,.0f} دلار ({heat_pct:.1f}٪) |")
    W(f"| ضریب همبستگی ({n_alt} آلت) | {corr:.2f} |")
    W(f"| **ریسک مؤثر** | **{heat_pct*corr:.1f}٪ از سقف {reg['cap']}٪** |")
    W(f"| پوزیشن بدون سطح ابطال | {len(no_inval)} از {len(rows)} |")
    W("")
    if heat_pct * corr > reg["cap"]:
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
    if stable_pct < reg["stable"]:
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
        W(f"مزیت = امتیاز نامزد − امتیاز موجود − {SWAP_COST_SCORE} (هزینه تعویض).")
        W(f"آستانه اجرا: {SWAP_MIN_EDGE}. حداکثر {MAX_SWAPS_WEEK} تعویض در هفته.")
        W(f"حداقل دوره نگهداری پیش از تعویض: {MIN_HOLD_DAYS} روز.")
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
          f"{'، '.join(why) if why else 'قوی‌ترین — آخر بفروش'} |")
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
    if stable_pct < reg["stable"]:
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
    ap = argparse.ArgumentParser(description=f"بازبینی سبد و موتور خروج — رادار {VERSION}")
    ap.add_argument("--holdings", default="holdings.json")
    ap.add_argument("--regime", type=float, required=False, default=0.0,
                    help="امتیاز رژیم از تحلیل ماکرو")
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

    reg = regime_row(a.regime)
    state = load_state()

    print("واکشی داده بیت‌کوین به‌عنوان مرجع قدرت نسبی...")
    btc = okx_candles("BTC")

    rows = []
    for p in book["positions"]:
        print(f"  واکشی {p['symbol']}...")
        df = okx_candles(p["symbol"])
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
        sc = score_position(okx_candles(s), btc)
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
    txt = build_report(book, rows, reg, cands)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\nذخیره شد در {a.out}")
    print("\n" + txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
