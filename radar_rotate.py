#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_rotate.py — شکارچی چرخش: قدرت نسبی پایدار + تجمیع
=========================================================

هدف: پیدا کردن کوین‌هایی که **هم‌زمان** دو شرط را دارند:
   ۱) نسبت به بیت‌کوین صعودی‌اند — در هر دو پنجره ۳۰ و ۷ روزه
   ۲) در حال تجمیع‌اند — قیمت بالای مرکز حجمی، نه در حال سقوط آزاد

این همان الگوی چرخش «ضعیف به قوی» در بازار خرسی است.

    python radar_rotate.py --venues okx,gate --min-vol 3000000
    python radar_rotate.py --top 60 --exclude BTC,ETH

⚠️ خروجی این اسکریپت **مجوز ورود نیست**. فهرست نامزد است. هر نامزد باید
   با radar_fetch3.py تحلیل عمیق شود و از دروازه رژیم عبور کند.
"""
from __future__ import annotations
import argparse, math, os, sys, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import radar_fetch3 as R

UTC = timezone.utc

# توکن‌هایی که ذاتاً از تحلیل قدرت نسبی خارج‌اند
import re
# توکن‌های اهرمی و معکوس — قدرت نسبی روی آنها بی‌معناست چون ذاتاً مشتق‌اند
# پسوند UP/DOWN فقط وقتی اهرمی است که پیش از آن دست‌کم سه حرف باشد،
# وگرنه نمادهای واقعی مثل JUP قربانی می‌شوند.
LEV_RE = re.compile(r"(\d[LS]$)|((?<=[A-Z]{3})UP$)|((?<=[A-Z]{2})DOWN$)"
                    r"|(BULL$)|(BEAR$)|(HEDGE$)|(HALF$)")
STABLES = {"USDT","USDC","DAI","TUSD","FDUSD","USDE","PYUSD","BUSD","USDD",
           "EURT","EURS","USDP","GUSD","LUSD","FRAX","SUSD","USDS"}


def universe_okx(min_vol: float) -> list[dict]:
    """
    مرحله ۱ — یک درخواست، همه جفت‌های نقدی. غربال ارزان پیش از کندل.
    بدون این مرحله باید برای هر کوین کندل گرفت که ساعت‌ها طول می‌کشد.
    """
    d = R.okx_get("/api/v5/market/tickers", {"instType": "SPOT"}, label="فهرست بازار")
    if not d:
        return []
    out = []
    for t in d:
        inst = t.get("instId", "")
        if not inst.endswith("-USDT"):
            continue
        base = inst[:-5]
        if base in STABLES or LEV_RE.search(base):
            continue
        try:
            last = float(t["last"]); o24 = float(t["open24h"])
            vol = float(t.get("volCcy24h") or 0)     # حجم به واحد ارز مظنه
        except (KeyError, ValueError, TypeError):
            continue
        if last <= 0 or o24 <= 0 or vol < min_vol:
            continue
        out.append({"symbol": base, "price": last,
                    "chg24": 100 * (last / o24 - 1), "vol24": vol})
    return out


def rs_pair(df: pd.DataFrame, btc: pd.DataFrame, days: int) -> float | None:
    """قدرت نسبی با هم‌ترازی تاریخی — نه شماره ردیف."""
    if df is None or btc is None or len(df) < days + 2:
        return None
    now = df["ts"].iloc[-1]
    back = now - pd.Timedelta(days=days)
    def at(d, t):
        m = d["ts"] <= t
        return float(d.loc[m, "close"].iloc[-1]) if m.any() else None
    c1, c0 = at(df, now), at(df, back)
    b1, b0 = at(btc, now), at(btc, back)
    if None in (c1, c0, b1, b0) or c0 <= 0 or b0 <= 0:
        return None
    return 100 * (c1 / c0 - 1) - 100 * (b1 / b0 - 1)


def analyze(sym: str, order: list[str], btc: pd.DataFrame) -> dict | None:
    got, vn, _ = R.candles_first_ok(sym, order, 200, [])
    if "1D" not in got:
        return None
    d = got["1D"]
    d = d[d["confirm"] == 1] if "confirm" in d.columns else d
    if len(d) < 60:
        return None
    r = d.iloc[-1]
    px = float(r["close"])
    row = {"symbol": sym, "price": px, "venue": vn, "bars": len(d)}

    row["rs30"] = rs_pair(d, btc, 30)
    row["rs7"] = rs_pair(d, btc, 7)
    row["rs3"] = rs_pair(d, btc, 3)
    for lbl, col in [("e50", "ema50"), ("e200", "ema200")]:
        v = float(r[col])
        row[lbl] = 100 * (px - v) / v if math.isfinite(v) and v > 0 else None
    row["rsi"] = float(r["rsi14"]) if math.isfinite(r["rsi14"]) else None
    row["atr_pct"] = 100*float(r["atr14"])/px if math.isfinite(r["atr14"]) else None
    vm = float(r["vol_ma20"])
    row["vol_x"] = float(r["vol"])/vm if math.isfinite(vm) and vm > 0 else None

    # تجمیع: موقعیت نسبت به ناحیه ارزش
    try:
        a = (R.three_anchors(d, None, got.get("4H")) or {}).get("A")
        if a:
            row["poc"], row["val"], row["vah"] = a["poc"], a["val"], a["vah"]
            row["vs_poc"] = 100*(px - a["poc"])/a["poc"] if a["poc"] else None
            row["zone"] = ("بالا" if px > a["vah"] else
                           "زیر" if px < a["val"] else "داخل")
            row["vp_days"] = a.get("span_days")
    except Exception:
        pass
    return row


def score(row: dict) -> tuple[float | None, int, list[str]]:
    """
    امتیاز چرخش ۰ تا ۲. قانون سخت: قدرت نسبی باید در **هر دو** پنجره مثبت باشد،
    وگرنه امتیاز سقف می‌خورد. دلیل: قدرت ۳۰ روزه بدون تأیید ۷ روزه یعنی
    حرکت تمام شده؛ قدرت ۷ روزه بدون ۳۰ روزه یعنی هنوز اثبات نشده.
    """
    parts, flags = [], []
    r30, r7, r3 = row.get("rs30"), row.get("rs7"), row.get("rs3")

    if r30 is not None and r7 is not None:
        if r30 > 0 and r7 > 0:
            s = min(2.0, 1.0 + (min(r30, 30)/30) + (min(r7, 15)/15) * 0.5)
            flags.append("✅قدرت‌پایدار")
        elif r7 > 0:
            s = 0.7; flags.append("شتاب‌تازه")
        elif r30 > 0:
            s = 0.4; flags.append("⚠️فرسایش")
        else:
            s = 0.0
        parts.append((s, 0.40))
    if r3 is not None and r7 is not None and r3 > 0 and r7 > 0:
        flags.append("سه‌روزه‌هم‌مثبت")

    z, vs_poc = row.get("zone"), row.get("vs_poc")
    if z:
        if z == "بالا":
            s = 2.0; flags.append("بالای‌ناحیه‌ارزش")
        elif z == "داخل":
            s = 1.4 if (vs_poc or 0) > 0 else 1.0
        else:
            s = 0.3
        parts.append((s, 0.25))

    e50, e200 = row.get("e50"), row.get("e200")
    if e50 is not None and e200 is not None:
        s = 0.0
        if e200 > 0: s += 1.0
        if e50 > 0:  s += 0.7
        if e200 > 0 and e50 > 0 and e50 < e200: s += 0.3   # چیدمان سالم
        parts.append((min(2.0, s), 0.20))
        if e200 > 0: flags.append("بالای‌EMA200")

    rsi = row.get("rsi")
    if rsi is not None:
        if rsi > 78:   s = 0.3; flags.append("⚠️داغ")
        elif rsi > 68: s = 1.0
        elif rsi >= 50: s = 2.0
        elif rsi >= 42: s = 1.2
        else:          s = 0.4
        parts.append((s, 0.15))

    vx = row.get("vol_x")
    if vx is not None and vx > 2.5:
        flags.append("حجم‌انفجاری")
    if row.get("atr_pct") and row["atr_pct"] > 15:
        flags.append("⚠️نوسان‌مفرط")

    if not parts:
        return None, 0, flags
    w = sum(x[1] for x in parts)
    return round(sum(v*x for v, x in parts)/w, 3), len(parts), flags


def pump_check(sym: str, order: list[str], px: float) -> str:
    """
    آزمون پامپ مصنوعی — بند حالت ۴ رادار.
    جهش بهره باز + فاندینگ به‌شدت مثبت = حرکت با اهرم، نه با پول تازه.
    """
    f, oi, _, _ = R.gather_venues(sym, order, px)
    agg = R.agg_funding(f)
    chg = [o["chg24"] for o in oi.values() if o.get("chg24") is not None]
    if not agg and not chg:
        return "بدون داده مشتقات"
    fnd = agg.get("mean", 0) * 100 if agg else None
    oic = float(np.mean(chg)) if chg else None
    if fnd is not None and oic is not None:
        if oic > 15 and fnd > 0.03:
            return f"⛔ **پامپ اهرمی** — بهره باز {oic:+.0f}٪ با فاندینگ {fnd:+.4f}٪"
        if oic > 15 and fnd <= 0:
            return f"فشار شورت — بهره باز {oic:+.0f}٪، فاندینگ {fnd:+.4f}٪"
        return f"سالم — بهره باز {oic:+.1f}٪، فاندینگ {fnd:+.4f}٪"
    return f"ناقص — فاندینگ {fnd:+.4f}٪" if fnd is not None else f"ناقص — بهره باز {oic:+.1f}٪"


def build_report(rows: list[dict], uni_n: int, pool_n: int,
                 order: list[str], min_vol: float, deep: dict) -> str:
    L: list[str] = []; A = L.append
    now = datetime.now(UTC)
    A(f"# شکارچی چرخش رادار {R.FRAMEWORK}")
    A("")
    A(f"تولید: **{now.strftime('%Y-%m-%d %H:%M UTC')}** | نسخه {R.VERSION} | "
      f"صرافی: {', '.join(order)}")
    A("")
    A(f"جهان بازار: **{uni_n}** جفت نقدی با حجم بالای {min_vol:,.0f} دلار "
      f"← **{pool_n}** نامزد وارد تحلیل کندل شد")
    A("")
    A("> **این فهرست مجوز ورود نیست.** نامزدها باید با `radar_fetch3.py` "
      "تحلیل عمیق شوند و از دروازه رژیم عبور کنند.")
    A("")

    ok = [r for r in rows if r.get("score") is not None]
    ok.sort(key=lambda r: r["score"], reverse=True)

    dual = [r for r in ok if (r.get("rs30") or -1) > 0 and (r.get("rs7") or -1) > 0]
    A("## ۱ — قدرت نسبی پایدار (هر دو پنجره مثبت)")
    A("")
    if dual:
        A("| # | نماد | قیمت | امتیاز | ق.ن ۳۰ر | ق.ن ۷ر | ق.ن ۳ر | vs EMA200 | vs EMA50 | RSI | ناحیه | vs POC | نشانه‌ها |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(dual[:20], 1):
            g = lambda k, f="{:+.1f}%": (f.format(r[k]) if r.get(k) is not None else "—")
            A(f"| {i} | **{r['symbol']}** | {R.fmt_num(r['price'])} | **{r['score']:.2f}** "
              f"| {g('rs30')} | {g('rs7')} | {g('rs3')} | {g('e200')} | {g('e50')} "
              f"| {g('rsi','{:.0f}')} | {r.get('zone','—')} | {g('vs_poc')} "
              f"| {'، '.join(r.get('flags', [])) or '—'} |")
        A("")
    else:
        A("**هیچ کوینی هر دو شرط را ندارد.**")
        A("")
        A("> این خودش یک یافته است، نه نبود داده: در این لحظه هیچ کوینی "
          "قدرت نسبی پایدار ندارد. چرخش، ستاپ ندارد.")
        A("")

    accel = [r for r in ok if (r.get("rs30") or 0) <= 0 and (r.get("rs7") or -1) > 0]
    A("## ۲ — شتاب تازه (۷ روزه مثبت، ۳۰ روزه هنوز منفی)")
    A("")
    A("> ریسک بالاتر: چرخش هنوز تأیید نشده. ولی نقطه ورود بهتری می‌دهد "
      "اگر چرخش واقعی باشد.")
    A("")
    if accel:
        A("| # | نماد | قیمت | امتیاز | ق.ن ۳۰ر | ق.ن ۷ر | ق.ن ۳ر | vs EMA200 | RSI | ناحیه | نشانه‌ها |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(accel[:15], 1):
            g = lambda k, f="{:+.1f}%": (f.format(r[k]) if r.get(k) is not None else "—")
            A(f"| {i} | **{r['symbol']}** | {R.fmt_num(r['price'])} | {r['score']:.2f} "
              f"| {g('rs30')} | {g('rs7')} | {g('rs3')} | {g('e200')} "
              f"| {g('rsi','{:.0f}')} | {r.get('zone','—')} | {'، '.join(r.get('flags', [])) or '—'} |")
        A("")
    else:
        A("**هیچ‌کدام.**"); A("")

    if deep:
        A("---"); A(""); A("## ۳ — آزمون پامپ مصنوعی (نامزدهای برتر)"); A("")
        A("| نماد | حکم |"); A("|---|---|")
        for s, v in deep.items():
            A(f"| **{s}** | {v} |")
        A("")
        A("> جهش بهره باز همراه با فاندینگ به‌شدت مثبت یعنی حرکت با **اهرم** "
          "ساخته شده، نه با پول تازه. چنین حرکتی معمولاً سریع برمی‌گردد.")
        A("")

    A("---"); A(""); A("## چطور بخوانی"); A("")
    A("| ستون | معنا |")
    A("|---|---|")
    A("| ق.ن ۳۰ر / ۷ر / ۳ر | قدرت نسبی به بیت‌کوین در سه پنجره. هر سه مثبت = قوی‌ترین حالت |")
    A("| ✅قدرت‌پایدار | هم ۳۰ روزه هم ۷ روزه مثبت — شرط اصلی چرخش |")
    A("| شتاب‌تازه | فقط ۷ روزه مثبت — تأیید نشده |")
    A("| ⚠️فرسایش | فقط ۳۰ روزه مثبت — حرکت احتمالاً تمام شده |")
    A("| ناحیه | موقعیت نسبت به ناحیه ارزش. بالا = خریدار کنترل دارد |")
    A("| ⚠️داغ | RSI بالای ۷۸ — ورود دیرهنگام |")
    A("| ⚠️نوسان‌مفرط | ATR روزانه بالای ۱۵٪ — حجم پوزیشن باید بسیار کوچک شود |")
    A("")
    A("**گام بعد برای هر نامزد:**")
    A("")
    A("```")
    A("python radar_fetch3.py SYMBOL --balance 800 --venues " + ",".join(order))
    A("```")
    A("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="شکارچی چرخش — قدرت نسبی پایدار")
    ap.add_argument("--venues", default="okx,gate")
    ap.add_argument("--min-vol", type=float, default=3_000_000,
                    help="حداقل حجم دلاری ۲۴ ساعته")
    ap.add_argument("--top", type=int, default=45,
                    help="چند نماد وارد مرحله کندل شود")
    ap.add_argument("--deep", type=int, default=5,
                    help="برای چند نامزد برتر آزمون پامپ اجرا شود")
    ap.add_argument("--exclude", default="", help="نمادهای حذفی، جدا با کاما")
    ap.add_argument("--out", default="out")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()

    order = [v.strip().lower() for v in a.venues.split(",") if v.strip().lower() in R.VENUES]
    if not order:
        print("صرافی معتبری انتخاب نشد.", file=sys.stderr); return 2
    excl = {s.strip().upper() for s in a.exclude.split(",") if s.strip()}

    t0 = time.time()
    print("[۰] آزمایش دسترسی ...", file=sys.stderr)
    live, dead = R.probe_venues(order)
    for vn, why in dead:
        print(f"     ✗ {vn}: {why}", file=sys.stderr)
    if live:
        order = live
        print(f"     ✓ {', '.join(live)}", file=sys.stderr)

    print("[۱] غربال ارزان — یک درخواست برای کل بازار ...", file=sys.stderr)
    uni = universe_okx(a.min_vol)
    if not uni:
        print("جهان بازار خالی برگشت.", file=sys.stderr); return 3
    uni = [u for u in uni if u["symbol"] not in excl]
    print(f"     {len(uni)} جفت با حجم کافی", file=sys.stderr)

    # مرجع بیت‌کوین
    print("[۲] مرجع بیت‌کوین ...", file=sys.stderr)
    bg, _, _ = R.candles_first_ok("BTC", order, 200, [])
    if "1D" not in bg:
        print("کندل بیت‌کوین نیامد — قدرت نسبی ممکن نیست.", file=sys.stderr); return 4
    btc = bg["1D"]
    btc = (btc[btc["confirm"] == 1] if "confirm" in btc.columns else btc).reset_index(drop=True)
    b_now, b_open = float(btc["close"].iloc[-1]), float(btc["close"].iloc[-2])
    btc_chg = 100 * (b_now / b_open - 1)

    # پیش‌رتبه‌بندی ارزان: تغییر ۲۴ ساعته نسبت به بیت‌کوین
    for u in uni:
        u["rel24"] = u["chg24"] - btc_chg
    pool = sorted(uni, key=lambda u: -u["rel24"])[:a.top]
    print(f"[۳] تحلیل کندل {len(pool)} نامزد ...", file=sys.stderr)

    rows = []
    for i, u in enumerate(pool, 1):
        if i % 10 == 0:
            print(f"     {i}/{len(pool)} ...", file=sys.stderr)
        try:
            r = analyze(u["symbol"], order, btc)
        except Exception as exc:
            R.FAILURES.append(f"{u['symbol']}: {type(exc).__name__}")
            r = None
        if r:
            r["vol24"] = u["vol24"]
            r["score"], r["cov"], r["flags"] = score(r)
            rows.append(r)
        time.sleep(0.25)

    ok = sorted([r for r in rows if r.get("score") is not None],
                key=lambda r: -r["score"])
    deep = {}
    if a.deep > 0 and ok:
        print(f"[۴] آزمون پامپ برای {min(a.deep, len(ok))} نامزد برتر ...", file=sys.stderr)
        for r in ok[:a.deep]:
            try:
                deep[r["symbol"]] = pump_check(r["symbol"], order, r["price"])
            except Exception:
                deep[r["symbol"]] = "خطا"
            time.sleep(0.3)

    rep = build_report(rows, len(uni), len(pool), order, a.min_vol, deep)
    if a.stdout:
        print(rep)
    else:
        os.makedirs(a.out, exist_ok=True)
        fn = os.path.join(a.out, f"ROTATE_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.md")
        open(fn, "w", encoding="utf-8").write(rep)
        print(f"\n✅ {fn}  ({time.time()-t0:.0f} ثانیه)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
