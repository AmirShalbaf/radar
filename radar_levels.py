#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_levels.py — نسخه ۱.۰
اسکنر موقعیت نسبت به سطح ساختاری

═══════════════════════════════════════════════════════════════════

مسئله‌ای که حل می‌کند:

    نسبت ریسک به پاداش با تنگ‌کردن استاپ ساخته نمی‌شود.
    با **نزدیک‌بودن ورود به سطح ابطال** ساخته می‌شود.

    مثال واقعی ZEC، ۹ اوت ۲۰۲۶:
        ورود ۵۱۵.۷۹، ابطال ۴۸۰.۴۳ → فاصله ۳۵.۳۶ → نسبت ۱.۷۳
        ورود ۴۸۵.۰۰، ابطال ۴۸۰.۴۳ → فاصله  ۴.۵۷ → نسبت ۱۹.۷

    همان معامله، همان ابطال، همان هدف. تنها تفاوت: کجا وارد شدی.

پس این اسکریپت دنبال «کوین خوب» نمی‌گردد.
دنبال **کوینی که همین حالا روی سطح ایستاده** می‌گردد.

═══════════════════════════════════════════════════════════════════

روش یافتن سطح — قاعده عزیزپور، کدنویسی‌شده:

    ۱ — فقط از تایم روزانه و بالاتر. زیر روزانه سطح نیست، ماشه است.
    ۲ — هر سطح حداقل **دو نقطه برخورد** لازم دارد. یک نقطه خط نیست.
    ۳ — داده سمت راست وزن بیشتری دارد. تازه‌تر است.

اجرا:
    python radar_levels.py --preset all
    python radar_levels.py --watchlist BTC,ETH,ZEC --min-rr 2
    python radar_levels.py --preset all --out levels.md
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass, field

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

import numpy as np
import pandas as pd
import requests

VERSION = "1.1"

PRESETS = {
    "main":  ["BTC", "ETH", "SOL"],
    "watch": ["BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "LINK", "AAVE", "SUI"],
    "all":   ["BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "HBAR", "XLM",
              "RNDR", "AAVE", "DOGE", "LINK", "SUI", "ZEC", "BNB", "XRP"],
}


# ═══════════════════════ واکشی ═══════════════════════

def okx_candles(inst: str, bar: str = "1D", want: int = 600) -> pd.DataFrame | None:
    """کندل از OKX با صفحه‌بندی. ترتیب صعودی، فقط کندل‌های بسته‌شده."""
    rows, cursor, guard = [], None, 0
    while len(rows) < want and guard < 20:
        guard += 1
        params = {"instId": inst, "bar": bar, "limit": "100"}
        path = "/api/v5/market/candles"
        if cursor:
            params["after"] = cursor
            path = "/api/v5/market/history-candles"
        try:
            r = requests.get(f"https://www.okx.com{path}", params=params, timeout=20)
            js = r.json()
            batch = js.get("data") or []
        except Exception:
            break
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0]
        time.sleep(0.15)

    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close",
                                     "vol", "volCcy", "volCcyQuote", "confirm"])
    for c in ["open", "high", "low", "close", "vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["confirm"] = pd.to_numeric(df["confirm"], errors="coerce")
    df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms", utc=True)
    df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    return df[df["confirm"] == 1].reset_index(drop=True)


# ═══════════════════════ اندیکاتور ═══════════════════════

def atr_wilder(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


# ═══════════════════════ یافتن سطح ═══════════════════════

def find_pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[list, list]:
    """
    نقاط چرخش. یک سقف وقتی سقف است که در پنجره چپ و راست بالاترین باشد.

    نکته: کندل‌های انتهای سری هنوز پنجره راست کامل ندارند و نمی‌توانند
    تأیید شوند. این عمدی است — سقف تأییدنشده، سقف نیست.
    """
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    n = len(df)
    for i in range(left, n - right):
        w = h[i - left: i + right + 1]
        if h[i] == w.max() and (w == h[i]).sum() == 1:
            highs.append((i, float(h[i])))
        w = l[i - left: i + right + 1]
        if l[i] == w.min() and (w == l[i]).sum() == 1:
            lows.append((i, float(l[i])))
    return highs, lows


@dataclass
class Level:
    price: float
    touches: int
    last_idx: int
    kind: str                       # "حمایت" یا "مقاومت"
    members: list = field(default_factory=list)
    flipped: bool = False           # تازه از مقاومت به حمایت برگشته

    @property
    def tag(self) -> str:
        return f"{self.touches}{'⚡' if self.flipped else ''}"


def cluster_levels(pivots: list, tol: float, n_bars: int,
                   min_touches: int = 2) -> list[Level]:
    """
    نقاط چرخش نزدیک به هم را به یک سطح تبدیل می‌کند.

    قاعده عزیزپور: «یک خط دو نقطه لازم دارد. یک نقطه خط نیست.»
    پس min_touches پیش‌فرض ۲ است و پایین‌تر نمی‌رود.

    tol معمولاً کسری از ATR است — دو برخورد در فاصله کمتر از نصف ATR
    عملاً یک سطح‌اند.
    """
    if not pivots:
        return []
    pts = sorted(pivots, key=lambda x: x[1])
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if abs(p[1] - cur[-1][1]) <= tol:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)

    out = []
    for c in clusters:
        if len(c) < min_touches:
            continue
        # وزن‌دهی به داده تازه‌تر — قاعده «سمت راست مهم‌تر است»
        w = np.array([0.5 + 0.5 * (i / max(n_bars - 1, 1)) for i, _ in c])
        price = float(np.average([v for _, v in c], weights=w))
        out.append(Level(price=price, touches=len(c),
                         last_idx=max(i for i, _ in c), kind="", members=c))
    return out


# ═══════════════════════ ارزیابی ═══════════════════════

@dataclass
class Assessment:
    symbol: str
    price: float = math.nan
    atr: float = math.nan
    trend: str = "؟"
    support: Level | None = None
    resistance: Level | None = None
    dist_sup_atr: float = math.nan
    rr: float = math.nan
    swing_low_4h: float = math.nan      # کف نوسان چهارساعته
    rr_tactical: float = math.nan       # نسبت با استاپ چهارساعته
    verdict: str = ""
    note: str = ""
    n_bars: int = 0


def assess(sym: str, df: pd.DataFrame, buffer_atr: float = 0.25,
           tol_atr: float = 1.0, df_4h: pd.DataFrame | None = None) -> Assessment:
    a = Assessment(symbol=sym, n_bars=len(df))
    if df is None or len(df) < 60:
        a.verdict = "داده کم"
        return a

    df = df.copy()
    df["atr"] = atr_wilder(df)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)

    price = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    a.price, a.atr = price, atr

    # جهت روند — قاعده ر۱: خلاف روند وارد نشو
    #
    # درس رخداد ۹ اوت ۲۰۲۶ (بی‌ان‌بی):
    #   نسخه اول وقتی میانگین ۲۰۰ نابالغ بود، آن را **کلاً دور می‌انداخت**
    #   و فقط قیمت را با میانگین ۵۰ می‌سنجید. برای بی‌ان‌بی این یعنی
    #   برچسب «صعودی» در حالی که میانگین ۲۰۰ روی ۶۴۶ بود و قیمت ۶۰۵ —
    #   یعنی ساختار روزانه نزولی بود.
    #
    # قاعده درست: عدد نابالغ **سوگیری** دارد، ولی **بی‌اطلاع** نیست.
    #   نادیده‌گرفتنش بدتر از استفاده با هشدار است.
    e50 = float(df["ema50"].iloc[-1])
    e200 = float(df["ema200"].iloc[-1])
    mature200 = len(df) >= 3 * 200

    if math.isfinite(e200):
        if price > e50 > e200:
            a.trend = "صعودی"
        elif price < e50 < e200:
            a.trend = "نزولی"
        elif price < e200 and price > e50:
            a.trend = "بی‌ساختار ↓"      # زیر بلندمدت، بالای میان‌مدت
        elif price > e200 and price < e50:
            a.trend = "بی‌ساختار ↑"
        else:
            a.trend = "بی‌ساختار"
        if not mature200:
            a.trend += "*"
            a.note = f"میانگین ۲۰۰ نابالغ ({len(df)} کندل، {3*200} لازم) — با تریدینگ‌ویو تأیید کن"
    else:
        a.trend = "؟"
        a.note = "میانگین ۲۰۰ محاسبه نشد"

    highs, lows = find_pivots(df)
    # درس آزمون ۹ اوت ۲۰۲۶:
    #   با tol = نصف دامنه، دو قله واقعی به فاصله ۲.۷۹ خوشه نشدند چون
    #   آستانه ۲.۲۱ بود. نتیجه: هیچ مقاومتی پیدا نشد و نسبت nan شد.
    #   در بازار واقعی، دو برخورد به یک سطح که ماه‌ها فاصله دارند،
    #   طبیعتاً حدود یک دامنه از هم فرق می‌کنند، نه نصف دامنه.
    #   رسم دستی هم همین‌قدر روادار است — چشم «تقریباً همان‌جا» را می‌بیند.
    tol = tol_atr * atr
    res_all = cluster_levels(highs, tol, len(df))
    sup_all = cluster_levels(lows, tol, len(df))
    for L in res_all:
        L.kind = "مقاومت"
    for L in sup_all:
        L.kind = "حمایت"

    # سطحی که از مقاومت به حمایت برگشته، هنوز به‌عنوان حمایت آزمون نشده.
    # درس رخداد سولانا ۹ اوت: اسکنر «حمایت با ۵ برخورد» گفت، ولی هر پنج
    # برخورد **به‌عنوان مقاومت** بود. قیمت تازه از رویش رد شده بود.
    for L in res_all:
        if L.price < price:
            L.flipped = True

    below = [L for L in (sup_all + res_all) if L.price < price]
    above = [L for L in (sup_all + res_all) if L.price > price]

    a.support = max(below, key=lambda L: L.price) if below else None
    a.resistance = min(above, key=lambda L: L.price) if above else None

    # تفکیک دو حالت متفاوت که نسخه اول هر دو را «سطح کافی نیست» می‌خواند:
    #   بدون حمایت  → واقعاً نمی‌دانیم کجا ابطال بگذاریم. بی‌فایده.
    #   بدون مقاومت → قیمت بالای همه سطوح است. کشف قیمت. **اطلاعات است، نه نبود اطلاعات.**
    if not a.support:
        a.verdict = "بدون حمایت شناسایی‌شده"
        return a
    if not a.resistance:
        a.dist_sup_atr = (price - a.support.price) / atr if atr else math.nan
        a.verdict = "کشف قیمت — بالای همه سطوح"
        a.note = (a.note + " | " if a.note else "") + "مقاومتی بالای قیمت نیست، هدف باید دستی تعیین شود"
        return a

    # استاپ کمی زیر سطح — نه دقیقاً رویش
    stop = a.support.price - buffer_atr * atr
    risk = price - stop
    reward = a.resistance.price - price
    a.dist_sup_atr = (price - a.support.price) / atr if atr else math.nan
    a.rr = reward / risk if risk > 0 else math.nan

    # ── نسبت تاکتیکی: استاپ از ساختار چهارساعته، نه روزانه ──
    #
    # درس رخداد زی‌کش: تز معامله شکست چهارساعته بود، ولی اسکنر استاپ را
    # از حمایت روزانه (۴۹۱) گرفت. ریسک ۳۹ به‌جای ۷ → نسبت ۰.۴۰ به‌جای ۲.۶۵.
    # استاپ باید به همان ساختاری بچسبد که **تز** را تعریف می‌کند.
    if df_4h is not None and len(df_4h) > 30:
        _, lows4 = find_pivots(df_4h, 2, 2)
        recent = [v for i, v in lows4 if i >= len(df_4h) - 30 and v < price]
        if recent:
            a.swing_low_4h = max(recent)
            risk_t = price - a.swing_low_4h * 0.998
            if risk_t > 0:
                a.rr_tactical = reward / risk_t

    if a.dist_sup_atr <= 0.5:
        a.verdict = "روی سطح"
    elif a.dist_sup_atr <= 1.5:
        a.verdict = "نزدیک سطح"
    elif a.dist_sup_atr <= 3.0:
        a.verdict = "میانه"
    else:
        a.verdict = "کشیده"
    return a


# ═══════════════════════ خروجی ═══════════════════════

def fmt(x, d=4):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:,.{d}f}".rstrip("0").rstrip(".") if d else f"{x:,.0f}"


def report(rows: list[Assessment], min_rr: float) -> str:
    ok = [a for a in rows if math.isfinite(a.rr)]
    ok.sort(key=lambda a: (-a.rr))

    L = [
        f"# اسکنر سطوح رادار — نسخه {VERSION}",
        "",
        "> **اصل:** نسبت ریسک به پاداش با تنگ‌کردن استاپ ساخته نمی‌شود،",
        "> با نزدیک‌بودن ورود به سطح ابطال ساخته می‌شود.",
        "",
        "| نماد | قیمت | روند | وضعیت | فاصله | حمایت | مقاومت | نسبت | نسبت ۴س |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for a in ok:
        sup = f"{fmt(a.support.price)} ({a.support.tag})" if a.support else "—"
        res = f"{fmt(a.resistance.price)} ({a.resistance.tag})" if a.resistance else "—"
        rrt = f"**{fmt(a.rr_tactical, 2)}**" if math.isfinite(a.rr_tactical) else "—"
        L.append(
            f"| {a.symbol} | {fmt(a.price)} | {a.trend} | {a.verdict} | "
            f"{fmt(a.dist_sup_atr, 2)}× | {sup} | {res} | {fmt(a.rr, 2)} | {rrt} |"
        )

    # فقط «صعودی» خالص — «بی‌ساختار» و «صعودی*» با ستاره هم رد می‌شوند
    def _best(a):
        return max([x for x in (a.rr, a.rr_tactical) if math.isfinite(x)], default=0.0)
    cand = [a for a in ok
            if _best(a) >= min_rr
            and a.verdict in ("روی سطح", "نزدیک سطح")
            and a.trend == "صعودی"]
    L += ["", "---", "", f"## نامزدها — نسبت ≥ {min_rr}، نزدیک سطح، روند صعودی", ""]
    if cand:
        for a in cand:
            stop = a.support.price - 0.25 * a.atr
            L += [
                f"### {a.symbol}",
                "",
                f"| مورد | مقدار |",
                f"|---|---|",
                f"| قیمت | {fmt(a.price)} |",
                f"| حمایت ({a.support.touches} برخورد) | {fmt(a.support.price)} |",
                f"| استاپ پیشنهادی | {fmt(stop)} |",
                f"| فاصله استاپ | {fmt(100*(a.price-stop)/a.price, 2)}٪ |",
                f"| مقاومت ({a.resistance.touches} برخورد) | {fmt(a.resistance.price)} |",
                f"| نسبت با استاپ روزانه | **{fmt(a.rr, 2)}** |",
                f"| کف نوسان چهارساعته | {fmt(a.swing_low_4h)} |",
                f"| نسبت با استاپ چهارساعته | **{fmt(a.rr_tactical, 2)}** |",
                f"| دامنه روزانه | {fmt(100*a.atr/a.price, 2)}٪ |",
                "",
            ]
            if a.note:
                L += [f"> ⚠️ {a.note}", ""]
    else:
        L += ["هیچ نامزدی با این شرایط پیدا نشد.", "",
              "**این خودش یک داده است.** وقتی هیچ کوینی روی سطح نیست،",
              "پاسخ سؤال «آیا امروز نیاز به ورود هست؟» خیر است."]

    L += [
        "", "---", "",
        "## محدودیت‌ها — بخوان پیش از استفاده",
        "",
        "| مورد | توضیح |",
        "|---|---|",
        "| نرخ برد | **محاسبه نمی‌شود.** از یک عکس لحظه‌ای قابل تخمین نیست |",
        "| تعداد برخورد | شمارش تاریخی است، نه تضمین واکنش آینده |",
        "| سطوح | فقط از تایم روزانه. زیر روزانه ماشه است نه سطح |",
        "| مقاومت نزدیک | نسبت بالا با مقاومت خیلی نزدیک، توهم است |",
        "| برچسب `*` روی روند | میانگین ۲۰۰ هنوز بالغ نشده — با تریدینگ‌ویو تأیید کن |",
        "| علامت ⚡ کنار سطح | تازه از مقاومت به حمایت برگشته، هنوز آزمون نشده |",
        "| نسبت ۴س | استاپ از کف نوسان چهارساعته — برای تز شکست کوتاه‌مدت |",
        "| **مهم** | اسکنر فقط ساختار قیمت را می‌بیند. موضع‌گیری، جریان و بهره باز را نمی‌بیند |",
        "",
        "> این خروجی **نامزد** می‌دهد، نه **حکم**. هر نامزد باید با",
        "> `radar_fetch3.py` عمیق بررسی شود و از دروازه پذیرش رادار بگذرد.",
        "",
    ]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="اسکنر موقعیت نسبت به سطح ساختاری")
    ap.add_argument("--watchlist", help="جدا با کاما")
    ap.add_argument("--preset", choices=list(PRESETS), default="all")
    ap.add_argument("--min-rr", type=float, default=2.0, dest="min_rr")
    ap.add_argument("--bars", type=int, default=700)
    ap.add_argument("--tol", type=float, default=1.0, dest="tol_atr",
                    help="رواداری خوشه‌بندی سطح، بر حسب دامنه روزانه")
    ap.add_argument("--out")
    args = ap.parse_args()

    syms = ([s.strip().upper() for s in args.watchlist.split(",")]
            if args.watchlist else PRESETS[args.preset])

    print(f"اسکنر سطوح v{VERSION} — {len(syms)} نماد\n", file=sys.stderr)
    rows = []
    for s in syms:
        print(f"  {s} ...", end="", flush=True, file=sys.stderr)
        df = okx_candles(f"{s}-USDT", "1D", args.bars)
        df4 = okx_candles(f"{s}-USDT", "4H", 200) if df is not None else None
        a = (assess(s, df, tol_atr=args.tol_atr, df_4h=df4) if df is not None
             else Assessment(symbol=s, verdict="بدون داده"))
        rows.append(a)
        print(f" {a.verdict}  نسبت={fmt(a.rr,2)}", file=sys.stderr)

    txt = report(rows, args.min_rr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\n✅ {args.out}", file=sys.stderr)
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
