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

def score_symbol(base: str, order: list[str], btc_close: pd.Series | None
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
    # ۶ — قدرت نسبی به بیت‌کوین، ۳۰ روزه
    if btc_close is not None and len(d) > 31 and len(btc_close) > 31:
        try:
            c30 = 100 * (price / float(d["close"].iloc[-31]) - 1)
            b30 = 100 * (float(btc_close.iloc[-1]) / float(btc_close.iloc[-31]) - 1)
            row["rs_btc_30d"] = c30 - b30
            row["chg_30d"] = c30
        except Exception:
            pass

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

    row["deriv_venues"] = ",".join(sorted(set(fund) | set(oi) | set(pos))) or "—"
    row["score"], row["covered"] = composite(row)
    return row


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
    if row.get("oi_chg24") is not None and row.get("funding_8h") is not None \
       and row["oi_chg24"] > 8 and row["funding_8h"] <= 0:
        f.append("فشارشورت")
    return "، ".join(f) if f else "—"


# ═══════════════════ گزارش ═══════════════════

def build_scan_report(rows: list[dict], macro: dict, fred: dict,
                      order: list[str], top: int) -> str:
    L: list[str] = []; A = L.append
    now = datetime.now(UTC)
    A(f"# اسکن رادار ۵.۲ — {len(rows)} کوین")
    A("")
    A(f"تولید: **{now.strftime('%Y-%m-%d %H:%M UTC')}** | صرافی‌ها: {', '.join(order)}")
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
    A("| # | نماد | قیمت | امتیاز | vs EMA200 | vs EMA50 | RSI | قدرت نسبی ۳۰ روزه | ATR٪ | فاندینگ ۸ ساعته | بهره باز ۲۴ ساعته | پوشش |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ok, 1):
        def pc(k, d=1):
            v = r.get(k)
            return f"{v:+.{d}f}%" if v is not None else "—"
        def nm(k, d=1):
            v = r.get(k)
            return f"{v:.{d}f}" if v is not None else "—"
        A(f"| {i} | **{r['symbol']}** | {R.fmt_num(r['price'])} | **{r['score']:+.2f}** "
          f"| {pc('vs_ema200')} | {pc('vs_ema50')} | {nm('rsi')} | {pc('rs_btc_30d')} "
          f"| {nm('atr_pct',2)} | {pc('funding_8h',4)} | {pc('oi_chg24')} | {r['covered']}/۵ |")
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

    A("---"); A(""); A(f"## ۲ — نامزدهای تحلیل عمیق (بالاترین {top})"); A("")
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
        if r.get("atr_pct"):
            A(f"- نوسان روزانه {r['atr_pct']:.2f}٪ ← استاپ ۱.۵ برابری یعنی "
              f"{r['atr_pct']*1.5:.2f}٪، سقف اهرم حدود {math.floor(100/(r['atr_pct']*1.5*1.5))}x")
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
    A("| پوشش | چند سنجه از ۵ داده داشت. زیر ۴ یعنی امتیاز کم‌اعتبار |")
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

    # مرجع بیت‌کوین برای قدرت نسبی
    print("[۲] مرجع بیت‌کوین ...", file=sys.stderr)
    btc_got, _, _ = R.candles_first_ok("BTC", order, 300, [])
    btc_close = None
    if "1D" in btc_got:
        bd = btc_got["1D"]
        bd = bd[bd["confirm"] == 1] if "confirm" in bd.columns else bd
        btc_close = bd["close"].reset_index(drop=True)

    rows = []
    for i, s in enumerate(syms, 1):
        print(f"[۳] {i}/{len(syms)} — {s} ...", file=sys.stderr)
        try:
            r = score_symbol(s, order, btc_close)
        except Exception as exc:
            R.FAILURES.append(f"{s}: {type(exc).__name__} {str(exc)[:70]}")
            r = None
        rows.append(r or {"symbol": s, "score": None, "covered": 0, "price": None})
        time.sleep(0.4)   # احترام به سقف نرخ صرافی‌ها

    rep = build_scan_report(rows, macro, fred, order, a.top)

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
