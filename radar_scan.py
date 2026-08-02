#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_scan.py — اسکنر چندکوینی رادار ۵.۲
=========================================

فلسفه: اول **غربال**، بعد **عمق**.
یک بار دروازه رژیم و ماکرو گرفته می‌شود (نه به ازای هر کوین)، سپس هر کوین
فقط با داده چارت و مشتقات خودش امتیاز می‌گیرد و رتبه‌بندی می‌شود.

    python radar_scan.py --watchlist BTC,ETH,SOL,ONDO,TAO,HYPE
    python radar_scan.py --preset main --venues binance,okx
    python radar_scan.py --preset all --top 5

خروجی: جدول مقایسه‌ای + فهرست کوین‌هایی که ارزش تحلیل عمیق دارند.
سپس برای هر کدام:  python radar_fetch3.py SYMBOL --balance 800
"""
from __future__ import annotations
import argparse, math, os, sys, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd

import radar_fetch3 as R

UTC = timezone.utc

PRESETS = {
    "main":  ["BTC", "ETH", "SOL"],
    "watch": ["BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "LINK", "AAVE", "SUI"],
    "all":   ["BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "HBAR", "XLM",
              "RNDR", "AAVE", "DOGE", "LINK", "SUI"],
}


# ═══════════════════ امتیازدهی غربال ═══════════════════

def _close_at(df: pd.DataFrame, ts) -> float | None:
    """آخرین قیمت بسته‌شدن در تاریخ ts یا قبل از آن. هم‌ترازی تاریخی، نه موقعیتی."""
    if df is None or len(df) == 0:
        return None
    m = df["ts"] <= ts
    if not m.any():
        return None
    return float(df.loc[m, "close"].iloc[-1])


def score_symbol(base: str, order: list[str], btc_ref: pd.DataFrame | None
                 ) -> dict | None:
    base = R.SYMBOL_ALIAS.get(base.upper(), base.upper())
    """
    شش سنجه غربال. هر کدام که داده نداشته باشد None می‌ماند — هرگز صفر فرضی.
    امتیاز نهایی فقط روی سنجه‌های موجود نرمال می‌شود (قانون سوگیری صفر).
    """
    got, vn, _ = R.candles_first_ok(base, order, 300, [])
    if "1D" not in got:
        return None
    d = got["1D"]
    d = d[d["confirm"] == 1] if "confirm" in d.columns else d
    if len(d) < 60:
        return None
    r = d.iloc[-1]
    price = float(r["close"])

    row: dict = {"symbol": base, "venue": vn, "price": price,
                 "date": str(r["ts"].date())}

    # ۱ — فاصله از EMA200: ساختار بلندمدت
    if math.isfinite(r["ema200"]) and r["ema200"] > 0:
        row["vs_ema200"] = 100 * (price - r["ema200"]) / r["ema200"]
    # ۲ — فاصله از EMA50: ساختار میان‌مدت
    if math.isfinite(r["ema50"]) and r["ema50"] > 0:
        row["vs_ema50"] = 100 * (price - r["ema50"]) / r["ema50"]
    # ۳ — RSI
    if math.isfinite(r["rsi14"]):
        row["rsi"] = float(r["rsi14"])
    # ۴ — نوسان روزانه
    if math.isfinite(r["atr14"]) and price > 0:
        row["atr_pct"] = 100 * float(r["atr14"]) / price
    # ۵ — تورم حجم اخیر
    if math.isfinite(r["vol_ma20"]) and r["vol_ma20"] > 0:
        row["vol_x"] = float(r["vol"]) / float(r["vol_ma20"])
    # ۶ — قدرت نسبی به بیت‌کوین: دو پنجره، ۳۰ روزه و ۷ روزه
    #     پنجره بلند جهت را می‌گوید، پنجره کوتاه می‌گوید جهت هنوز زنده است یا نه.
    if btc_ref is not None and len(btc_ref):
        # هم‌ترازی بر اساس **تاریخ**، نه شماره ردیف. اگر تعداد کندل کوین و
        # بیت‌کوین فرق کند، مقایسه موقعیتی دو تاریخ متفاوت را کنار هم می‌گذارد.
        now_ts = r["ts"]
        b_now = _close_at(btc_ref, now_ts)
        for days, tag in [(30, "30d"), (7, "7d")]:
            back = now_ts - pd.Timedelta(days=days)
            c_then = _close_at(d, back)
            b_then = _close_at(btc_ref, back)
            if None in (c_then, b_then, b_now) or c_then <= 0 or b_then <= 0:
                continue
            cw = 100 * (price / c_then - 1)
            bw = 100 * (b_now / b_then - 1)
            row[f"rs_btc_{tag}"] = cw - bw
            row[f"chg_{tag}"] = cw
            row[f"rs_{tag}_from"] = str(pd.Timestamp(back).date())
    # پرچم فرسایش: قدرت بلندمدت مثبت ولی کوتاه‌مدت منفی
    r30, r7 = row.get("rs_btc_30d"), row.get("rs_btc_7d")
    if r30 is not None and r7 is not None:
        row["rs_decay"] = (r30 > 0 and r7 < 0)
        row["rs_accel"] = (r30 < 0 and r7 > 0)

    # ── مشتقات
    fund, oi, pos, _ = R.gather_venues(base, order, price)
    agg = R.agg_funding(fund)
    if agg:
        row["funding_8h"] = agg["mean"] * 100
        row["funding_split"] = agg.get("disagree", False)
    ch = [o["chg24"] for o in oi.values() if o.get("chg24") is not None]
    if ch:
        row["oi_chg24"] = float(np.mean(ch))
    usd = [o["usd"] for o in oi.values() if o.get("usd")]
    if usd:
        row["oi_usd"] = float(np.sum(usd))
    ga = [p.get("global_account") for p in pos.values() if p.get("global_account")]
    tp = [p.get("top_position") for p in pos.values() if p.get("top_position")]
    if ga:
        row["ls_crowd"] = float(np.mean(ga))
    if tp:
        row["ls_whale"] = float(np.mean(tp))
    if ga and tp and np.mean(tp) > 0:
        row["crowd_vs_whale"] = float(np.mean(ga) / np.mean(tp))

    # ── پروفایل حجم بازه ثابت، نسخه سبک برای غربال.
    #    فقط لنگر الف (کف تا سقف موج جاری) + موقعیت قیمت نسبت به ناحیه ارزش.
    #    نسخه کامل سه‌لنگری در radar_fetch3.py می‌ماند.
    try:
        anch = R.three_anchors(got["1D"], None, got.get("4H"))
        a = anch.get("A") or anch.get("B")
        if a:
            row["poc"] = a["poc"]
            row["val"], row["vah"] = a["val"], a["vah"]
            row["vp_from"], row["vp_to"] = a["from"], a["to"]
            row["vs_poc"] = 100 * (price - a["poc"]) / a["poc"] if a["poc"] else None
            if price > a["vah"]:
                row["vp_zone"] = "بالای ناحیه ارزش"
            elif price < a["val"]:
                row["vp_zone"] = "زیر ناحیه ارزش"
            else:
                row["vp_zone"] = "داخل ناحیه ارزش"
            # فاصله تا مرزها — همان اعدادی که استاپ و هدف از آن ساخته می‌شود
            row["to_val"] = 100 * (price - a["val"]) / price if price else None
            row["to_vah"] = 100 * (a["vah"] - price) / price if price else None
    except Exception as exc:
        R.FAILURES.append(f"{base} پروفایل حجم: {type(exc).__name__}")

    row["deriv_venues"] = ",".join(sorted(set(fund) | set(oi) | set(pos))) or "—"
    row["score"], row["covered"] = composite(row)
    row["short_score"], row["short_covered"] = short_composite(row)
    return row


def short_composite(row: dict) -> tuple[float | None, int]:
    """
    امتیاز شورت — **معکوس امتیاز لانگ نیست.**

    منطق: بهترین شورت کوینی است که تازه دارد می‌شکند و هنوز لانگ‌های
    اهرمی داخلش نشسته‌اند. بدترین شورت کوینی است که از قبل له شده —
    آنجا سوختی برای ریزش نمانده و جهش‌های شدید کمین کرده‌اند.

    خروجی ۰ تا ۲. هرچه بالاتر، شورت جذاب‌تر.
    """
    parts: list[tuple[float, float]] = []

    # ۱ — ضعف تازه، نه ضعف کهنه (وزن ۳۰٪)
    v200, v50 = row.get("vs_ema200"), row.get("vs_ema50")
    if v50 is not None:
        if v50 >= 0:
            s = 0.0                       # هنوز بالای میانگین، شکستی رخ نداده
        elif v50 > -12:
            s = min(2.0, abs(v50) / 6.0)  # ناحیه شکست تازه
        else:
            s = max(0.3, 2.0 - (abs(v50) - 12) / 10)   # خیلی دور، کشیده شده
        if v200 is not None and v200 < -30:
            s *= 0.5                      # از قبل له شده، سوخت کم
        parts.append((max(0.0, min(2.0, s)), 0.30))

    # ۲ — RSI در ناحیه شکار، نه در اشباع فروش (وزن ۲۰٪)
    rsi = row.get("rsi")
    if rsi is not None:
        if rsi < 30:
            s = 0.0                       # اشباع فروش، ریسک جهش
        elif rsi < 38:
            s = 0.6
        elif rsi <= 58:
            s = 2.0                       # ناحیه ایده‌آل ورود شورت
        elif rsi <= 70:
            s = 1.4
        else:
            s = 0.8                       # هنوز داغ، شکستی تأیید نشده
        parts.append((s, 0.20))

    # ۳ — لانگ‌های اهرمی به‌عنوان سوخت (وزن ۲۵٪)
    fnd, oic = row.get("funding_8h"), row.get("oi_chg24")
    if fnd is not None:
        s = 0.0
        if fnd > 0.03:   s = 2.0          # ازدحام شدید لانگ
        elif fnd > 0.01: s = 1.4
        elif fnd > 0:    s = 0.8
        else:            s = 0.2          # فاندینگ منفی، شورت‌ها از قبل ازدحام دارند
        if oic is not None and oic > 5 and fnd > 0:
            s = min(2.0, s + 0.5)         # بهره باز در حال رشد با فاندینگ مثبت
        parts.append((s, 0.25))

    # ۴ — ضعف نسبی، ولی نه فروپاشی کامل (وزن ۱۵٪)
    r30, r7 = row.get("rs_btc_30d"), row.get("rs_btc_7d")
    if r30 is not None:
        if r30 > 5:      s = 0.2          # قوی‌تر از بیت‌کوین، شورت خلاف جریان
        elif r30 > -5:   s = 1.0
        elif r30 > -20:  s = 1.8          # ضعف روشن
        else:            s = 0.9          # از قبل خیلی عقب افتاده
        if r7 is not None and r7 < 0 and r30 > 0:
            s = 1.6                       # فرسایش تازه — بهترین لحظه شورت
        parts.append((s, 0.15))

    # ۵ — جمعیت لانگ در برابر نهنگ شورت (وزن ۱۰٪)
    cw = row.get("crowd_vs_whale")
    if cw is not None:
        parts.append((max(0.0, min(2.0, (cw - 1.0) / 1.2)), 0.10))

    if not parts:
        return None, 0
    wsum = sum(w for _, w in parts)
    return round(sum(v * w for v, w in parts) / wsum, 3), len(parts)


def composite(row: dict) -> tuple[float | None, int]:
    """
    امتیاز مرکب −۲ تا +۲. فقط سنجه‌های موجود شمرده و نرمال می‌شوند.
    وزن‌ها: ساختار ۴۰٪، قدرت نسبی ۳۰٪، مومنتوم ۱۵٪، جریان ۱۵٪.
    """
    parts: list[tuple[float, float]] = []   # (امتیاز، وزن)

    v200 = row.get("vs_ema200")
    if v200 is not None:
        s = max(-2.0, min(2.0, v200 / 15.0))
        parts.append((s, 0.25))
    v50 = row.get("vs_ema50")
    if v50 is not None:
        parts.append((max(-2.0, min(2.0, v50 / 10.0)), 0.15))

    rs = row.get("rs_btc_30d")
    if rs is not None:
        parts.append((max(-2.0, min(2.0, rs / 15.0)), 0.30))

    rsi = row.get("rsi")
    if rsi is not None:
        # ۵۰ خنثی؛ بالای ۷۵ دیگر امتیاز اضافه نمی‌گیرد (خطر ورود دیرهنگام)
        s = (rsi - 50) / 15.0
        if rsi > 75:
            s = min(s, 0.5)
        parts.append((max(-2.0, min(2.0, s)), 0.15))

    fnd, oic = row.get("funding_8h"), row.get("oi_chg24")
    if fnd is not None or oic is not None:
        fs = 0.0
        if fnd is not None:
            # فاندینگ داغ = ازدحام لانگ = منفی
            fs += -1.0 if fnd > 0.02 else (0.5 if fnd < 0 else 0.0)
        if oic is not None and fnd is not None:
            if oic > 5 and fnd > 0.01:
                fs += -0.5          # بهره باز بالا + فاندینگ مثبت = رشد اهرمی
            elif oic > 5 and fnd <= 0:
                fs += 0.8           # بهره باز بالا + فاندینگ منفی = شورت‌ها در فشار
        parts.append((max(-2.0, min(2.0, fs)), 0.15))

    if not parts:
        return None, 0
    wsum = sum(w for _, w in parts)
    return round(sum(s * w for s, w in parts) / wsum, 3), len(parts)


def flags(row: dict) -> str:
    """هشدارهای کوتاه و قابل خواندن در جدول."""
    f = []
    if row.get("rsi") is not None and row["rsi"] > 75:
        f.append("داغ")
    if row.get("funding_8h") is not None and row["funding_8h"] > 0.03:
        f.append("فاندینگ‌داغ")
    if row.get("funding_split"):
        f.append("فاندینگ‌ناهم‌علامت")
    if row.get("crowd_vs_whale") is not None and row["crowd_vs_whale"] > 1.5:
        f.append("جمعیت‌مقابل‌نهنگ")
    if row.get("vol_x") is not None and row["vol_x"] > 2:
        f.append("حجم‌انفجاری")
    if row.get("rs_decay"):
        f.append("⚠️فرسایش‌قدرت")
    if row.get("rs_accel"):
        f.append("شتاب‌گیری")
    if row.get("oi_chg24") is not None and row.get("funding_8h") is not None \
       and row["oi_chg24"] > 8 and row["funding_8h"] <= 0:
        f.append("فشارشورت")
    return "، ".join(f) if f else "—"


# ═══════════════════ گزارش ═══════════════════

def build_scan_report(rows: list[dict], macro: dict, fred: dict,
                      order: list[str], top: int, dead: list = None) -> str:
    L: list[str] = []; A = L.append
    now = datetime.now(UTC)
    A(f"# اسکن رادار ۵.۲ — {len(rows)} کوین")
    A("")
    A(f"تولید: **{now.strftime('%Y-%m-%d %H:%M UTC')}** | صرافی‌های فعال: {', '.join(order)}")
    A("")
    if dead:
        A("**در دسترس نبودند:** " + "، ".join(f"{v} ({w})" for v, w in dead))
        A("")
    A("> این یک **غربال** است، نه تحلیل. هیچ ورودی از روی این جدول باز نمی‌شود. "
      "خروجی‌اش فقط فهرست نامزدهای تحلیل عمیق است.")
    A("")

    # ── رژیم، یک بار برای همه
    A("## ۰ — رژیم بازار و ماکرو (مشترک بین همه کوین‌ها)")
    A("")
    A("| سنجه | مقدار |"); A("|---|---|")
    for lab, k, f in [("تسلط بیت‌کوین", "btc_dominance", "{:.2f}%"),
                      ("تسلط بدون استیبل‌کوین", "btc_dom_ex_stable", "{:.2f}%"),
                      ("ترس و طمع", "fear_greed", "{}"),
                      ("تغییر ۳۰ روزه استیبل‌کوین", "stable_change_30d", "{:+.2f}%")]:
        A(f"| {lab} | {macro.get(k, R.Field()).render(f)} |")
    for k, d in (fred.get("derived") or {}).items():
        val = R.fmt_num(d["value"], 3) if d.get("value") is not None else "—"
        A(f"| {d['label']} | {val} — {d['read']} |")
    A("")

    if R.FAILURES:
        from collections import Counter
        def key(f):
            src = f.split(":")[0].strip()
            rest = f.split(":", 1)[1] if ":" in f else ""
            why = rest.strip()[:60]
            return (src, why)
        cnt = Counter(key(f) for f in R.FAILURES)
        A("### منابعی که پاسخ ندادند"); A("")
        A("| منبع | علت | تعداد |"); A("|---|---|---|")
        for (src, why), v in cnt.most_common(15):
            A(f"| {src} | {why or '—'} | {v} |")
        A(""); A("> اینها «داده ندارم» هستند و از پوشش کم می‌شوند."); A("")

    ok = [r for r in rows if r.get("score") is not None]
    ok.sort(key=lambda r: r["score"], reverse=True)

    A("---"); A(""); A("## ۱ — رتبه‌بندی")
    A("")
    A("| # | نماد | قیمت | لانگ | **شورت** | vs EMA200 | vs EMA50 | RSI | ق.ن ۳۰ر | **ق.ن ۷ر** | ATR٪ | فاندینگ | ب.باز ۲۴س |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ok, 1):
        def pc(k, d=1):
            v = r.get(k)
            return f"{v:+.{d}f}%" if v is not None else "—"
        def nm(k, d=1):
            v = r.get(k)
            return f"{v:.{d}f}" if v is not None else "—"
        ss = r.get("short_score")
        ss_txt = f"**{ss:.2f}**" if ss is not None else "—"
        A(f"| {i} | **{r['symbol']}** | {R.fmt_num(r['price'])} | {r['score']:+.2f} | {ss_txt} "
          f"| {pc('vs_ema200')} | {pc('vs_ema50')} | {nm('rsi')} | {pc('rs_btc_30d')} "
          f"| {pc('rs_btc_7d')} | {nm('atr_pct',2)} | {pc('funding_8h',4)} | {pc('oi_chg24')} |")
    A("")

    bad = [r for r in rows if r.get("score") is None]
    if bad:
        A(f"**بدون داده کافی:** {', '.join(r['symbol'] for r in bad)}")
        A("")

    A("### هشدارها"); A("")
    A("| نماد | هشدار | جمعیت / نهنگ |"); A("|---|---|---|")
    for r in ok:
        cw = f"{r['ls_crowd']:.2f} / {r['ls_whale']:.2f}" if r.get("ls_whale") else "—"
        A(f"| {r['symbol']} | {flags(r)} | {cw} |")
    A("")

    vp = [r for r in ok if r.get("poc")]
    if vp:
        A("---"); A(""); A("## ۲ — پروفایل حجم بازه ثابت (لنگر موج جاری)"); A("")
        A("> نسخه سبک: فقط لنگر الف. سه‌لنگر کامل و آزمون هم‌گرایی در تحلیل عمیق.")
        A("")
        A("| نماد | بازه | نقطه کنترل | مرز پایین | مرز بالا | موقعیت | نسبت به POC | تا مرز پایین |")
        A("|---|---|---|---|---|---|---|---|")
        for r in vp:
            A(f"| **{r['symbol']}** | {r.get('vp_from','—')} تا {r.get('vp_to','—')} "
              f"| **{R.fmt_num(r['poc'])}** | {R.fmt_num(r.get('val'))} "
              f"| {R.fmt_num(r.get('vah'))} | {r.get('vp_zone','—')} "
              f"| {f"{r['vs_poc']:+.1f}%" if r.get('vs_poc') is not None else '—'} "
              f"| {f"{r['to_val']:+.1f}%" if r.get('to_val') is not None else '—'} |")
        A("")
        below = [r["symbol"] for r in vp if r.get("vp_zone") == "زیر ناحیه ارزش"]
        above = [r["symbol"] for r in vp if r.get("vp_zone") == "بالای ناحیه ارزش"]
        if below:
            A(f"**زیر ناحیه ارزش ({len(below)}):** {'، '.join(below)} — فروشنده کنترل دارد")
        if above:
            A(f"**بالای ناحیه ارزش ({len(above)}):** {'، '.join(above)} — خریدار کنترل دارد")
        A("")

    sh = [r for r in ok if r.get("short_score") is not None]
    sh.sort(key=lambda r: r["short_score"], reverse=True)
    if sh:
        A("---"); A(""); A("## ۳ — رتبه‌بندی سمت شورت"); A("")
        A("> این جدول **معکوس جدول بالا نیست.** کوینی که از قبل له شده، شورت بدی است — "
          "سوخت ریزش تمام شده و مستعد جهش است. بهترین شورت، ضعف **تازه** با "
          "لانگ اهرمی هنوز نشسته است.")
        A("")
        A("| # | نماد | امتیاز شورت | ضعف تازه | RSI | فاندینگ | جمعیت/نهنگ | وضعیت |")
        A("|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(sh[:8], 1):
            v50 = r.get("vs_ema50"); rsi = r.get("rsi")
            if rsi is not None and rsi < 30:
                st = "اشباع فروش — پرهیز"
            elif v50 is not None and v50 >= 0:
                st = "هنوز نشکسته"
            elif r.get("vs_ema200") is not None and r["vs_ema200"] < -30:
                st = "از قبل له شده"
            elif r.get("rs_decay"):
                st = "**فرسایش تازه — بهترین لحظه**"
            else:
                st = "ضعف در جریان"
            A(f"| {i} | **{r['symbol']}** | **{r['short_score']:.2f}** "
              f"| {f'{v50:+.1f}%' if v50 is not None else '—'} "
              f"| {f'{rsi:.1f}' if rsi is not None else '—'} "
              f"| {f'{r[chr(34)]}' if False else (f'{r["funding_8h"]:+.4f}%' if r.get('funding_8h') is not None else '—')} "
              f"| {f'{r["crowd_vs_whale"]:.2f}x' if r.get('crowd_vs_whale') else '—'} | {st} |")
        A("")

    A("---"); A(""); A(f"## ۴ — نامزدهای تحلیل عمیق سمت لانگ (بالاترین {top})"); A("")
    for r in ok[:top]:
        A(f"### {r['symbol']}  —  امتیاز {r['score']:+.2f}")
        A("")
        A(f"- ساختار: قیمت {R.fmt_num(r.get('vs_ema200'),1)}٪ نسبت به EMA200، "
          f"{R.fmt_num(r.get('vs_ema50'),1)}٪ نسبت به EMA50")
        if r.get("rs_btc_30d") is not None:
            if r["symbol"] == "BTC":
                A("- قدرت نسبی: بیت‌کوین خودش معیار است")
            else:
                A(f"- قدرت نسبی ۳۰ روزه در برابر بیت‌کوین: {r['rs_btc_30d']:+.1f}٪ "
                  f"({'بهتر از بیت‌کوین' if r['rs_btc_30d']>0 else 'ضعیف‌تر از بیت‌کوین'})")
                if r.get("rs_btc_7d") is not None:
                    A(f"- قدرت نسبی **۷ روزه**: {r['rs_btc_7d']:+.1f}٪")
                    if r.get("rs_decay"):
                        A("- ⚠️ **فرسایش قدرت**: پنجره ۳۰ روزه مثبت ولی ۷ روزه منفی. "
                          "امتیاز بالا از گذشته می‌آید، نه از حالا.")
                    elif r.get("rs_accel"):
                        A("- 🔼 **شتاب‌گیری**: پنجره ۳۰ روزه منفی ولی ۷ روزه مثبت — چرخش تازه.")
        if r.get("atr_pct"):
            A(f"- نوسان روزانه {r['atr_pct']:.2f}٪ ← استاپ ۱.۵ برابری یعنی "
              f"{r['atr_pct']*1.5:.2f}٪، سقف اهرم حدود {math.floor(100/(r['atr_pct']*1.5*1.5))}x")
        if r.get("poc"):
            A(f"- پروفایل حجم: نقطه کنترل {R.fmt_num(r['poc'])}، "
              f"ناحیه ارزش {R.fmt_num(r.get('val'))} تا {R.fmt_num(r.get('vah'))} "
              f"← قیمت **{r.get('vp_zone','—')}**")
        A(f"- هشدار: {flags(r)}")
        A("")
        A(f"```\npython radar_fetch3.py {r['symbol']} --balance 800 --venues {','.join(order)}\n```")
        A("")

    A("---"); A("")
    A("## چطور بخوانی")
    A("")
    A("| ستون | معنا |")
    A("|---|---|")
    A("| امتیاز | مرکب −۲ تا +۲. ساختار ۴۰٪، قدرت نسبی ۳۰٪، مومنتوم ۱۵٪، جریان ۱۵٪ |")
    A("| قدرت نسبی | بازده ۳۰ روزه کوین منهای بازده ۳۰ روزه بیت‌کوین. مثبت یعنی مستقل قوی است |")
    A("| فاندینگ داغ | بالای ۰.۰۳٪ یعنی ازدحام لانگ ← ریسک شست‌وشو |")
    A("| فشار شورت | بهره باز بالا + فاندینگ منفی ← سوخت صعود |")
    A("| جمعیت مقابل نهنگ | بالای ۱.۵ یعنی خرده‌فروش لانگ‌تر از پول هوشمند است |")
    A("| **ق.ن ۷ر** | قدرت نسبی ۷ روزه. اگر ۳۰ روزه مثبت و ۷ روزه منفی بود = فرسایش |")
    A("| **امتیاز شورت** | ۰ تا ۲، مستقل از امتیاز لانگ. ضعف تازه + لانگ اهرمی نشسته |")
    A("| اشباع فروش — پرهیز | RSI زیر ۳۰. سوخت ریزش تمام شده، ریسک جهش |")
    A("| نقطه کنترل (POC) | قیمتی که بیشترین حجم آنجا معامله شده — قوی‌ترین سطح |")
    A("| ناحیه ارزش | بازه‌ای که ۷۰٪ حجم در آن رخ داده. زیرش = کنترل فروشنده |")
    A("")
    A("> **امتیاز بالا مجوز ورود نیست.** فقط می‌گوید کدام کوین ارزش تحلیل کامل رادار را دارد.")
    A("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="اسکنر چندکوینی رادار ۵.۲")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--watchlist", help="فهرست جدا شده با کاما، مثل BTC,ETH,SOL")
    g.add_argument("--preset", choices=list(PRESETS), help="فهرست آماده")
    ap.add_argument("--venues", default="binance,okx,bybit,gate")
    ap.add_argument("--top", type=int, default=3, help="چند نامزد برتر معرفی شود")
    ap.add_argument("--out", default="out")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()

    syms = ([s.strip().upper() for s in a.watchlist.split(",") if s.strip()]
            if a.watchlist else PRESETS[a.preset])
    order = [v.strip().lower() for v in a.venues.split(",") if v.strip().lower() in R.VENUES]
    if not order:
        print("صرافی معتبری انتخاب نشد.", file=sys.stderr); return 2

    t0 = time.time()

    # رژیم و ماکرو فقط یک بار — نه به ازای هر کوین
    print("[۱] رژیم و ماکرو ...", file=sys.stderr)
    macro: dict = {}
    R.fetch_macro(macro)
    fred = R.fetch_fred(R.http_text)

    print("[۰] آزمایش دسترسی صرافی‌ها ...", file=sys.stderr)
    live, dead = R.probe_venues(order)
    for vn, why in dead:
        print(f"     ✗ {vn}: {why}", file=sys.stderr)
    if live:
        print(f"     ✓ در دسترس: {', '.join(live)}", file=sys.stderr)
        order = live
    else:
        print("     ⚠️ هیچ صرافی پاسخ نداد", file=sys.stderr)
    dead_note = dead

    # مرجع بیت‌کوین برای قدرت نسبی
    print("[۲] مرجع بیت‌کوین ...", file=sys.stderr)
    btc_got, _, _ = R.candles_first_ok("BTC", order, 300, [])
    btc_ref = None
    if "1D" in btc_got:
        bd = btc_got["1D"]
        btc_ref = (bd[bd["confirm"] == 1] if "confirm" in bd.columns else bd
                   ).reset_index(drop=True)

    rows = []
    for i, s in enumerate(syms, 1):
        print(f"[۳] {i}/{len(syms)} — {s} ...", file=sys.stderr)
        try:
            r = score_symbol(s, order, btc_ref)
        except Exception as exc:
            R.FAILURES.append(f"{s}: {type(exc).__name__} {str(exc)[:70]}")
            r = None
        rows.append(r or {"symbol": s, "score": None, "covered": 0, "price": None})
        time.sleep(0.4)   # احترام به سقف نرخ صرافی‌ها

    rep = build_scan_report(rows, macro, fred, order, a.top, dead_note)

    if a.stdout:
        print(rep)
    else:
        os.makedirs(a.out, exist_ok=True)
        fn = os.path.join(a.out, f"SCAN_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.md")
        open(fn, "w", encoding="utf-8").write(rep)
        print(f"\n✅ {fn}  ({time.time()-t0:.0f} ثانیه)", file=sys.stderr)
    if R.FAILURES:
        print(f"   ⚠️ {len(R.FAILURES)} منبع پاسخ نداد", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
