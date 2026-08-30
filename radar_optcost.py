#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_optcost.py — دفتر هزینه فرصت و خودسنجی چارچوب، رادار ۶.۱
================================================================

چرا این فایل مهم‌ترین ابزار کالیبراسیون ۶.۰ است
------------------------------------------------
تا ۵.۴ فقط **خطای نوع اول** شمرده می‌شد: ورودهای بدی که انجام شدند.
**خطای نوع دوم** — ورودهای خوبی که رد شدند — هیچ‌جا ثبت نمی‌شد.

چارچوبی که فقط یک نوع خطا را می‌بیند، به‌طور سیستماتیک به همان سمتی
می‌رود که خطایش دیده نمی‌شود. رادار ۵.۴ به سمت خاموشی رفت
(نرخ عبور محاسبه‌شده: حدود ۱.۵٪) و هیچ‌کس اندازه‌اش نگرفت.

این اسکریپت رادار را **قابل ابطال** می‌کند.

قید روش‌شناختی حیاتی
--------------------
R ازدست‌رفته با فرض **اجرای کامل معامله فرضی** حساب می‌شود، نه با فرض
«تا سقف نگه می‌داشتم». اگر قیمت اول به استاپ فرضی رسید و بعد پرواز کرد،
R ازدست‌رفته **منفی یک** است، نه مثبت. بدون این قید، دفتر هزینه فرصت
به ماشین حسرت تبدیل می‌شود و تصمیم را به سمت بی‌احتیاطی می‌برد.

دستورها
-------
    python radar_optcost.py add --symbol ZEC --price 515.79 \
        --blocker "رده کیفیت F" --grade F --score 0.55 \
        --entry 515.79 --stop 478 --target 575 --regime -1.25

    python radar_optcost.py session --action        # ثبت جلسه با اقدام
    python radar_optcost.py session --no-action     # ثبت جلسه بدون اقدام
    python radar_optcost.py followup                # پرکردن قیمت ۱۴ و ۳۰ روزه
    python radar_optcost.py report                  # گزارش خودسنجی
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    requests = None

VERSION = "6.1"
UTC = timezone.utc
FILE = "radar_optcost.json"
OKX = "https://www.okx.com"

# باندهای سالم — از references/calibration.md بخش ۶
ACTION_RATE_LOW = 20.0
ACTION_RATE_HEALTHY = (30.0, 60.0)
ACTION_RATE_HIGH = 70.0
OPP_COST_ALARM = 0.50      # R
BLOCKER_CONC_ALARM = 40.0  # درصد
MIN_N_RECORDS = 15
MIN_N_SESSIONS = 20


def load() -> dict:
    if os.path.exists(FILE):
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"rejects": [], "sessions": []}


def save(d: dict) -> None:
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def candles_since(symbol: str, days: int) -> list[dict] | None:
    """کندل روزانه برای بازخوانی مسیر قیمت پس از رد."""
    if requests is None:
        return None
    try:
        r = requests.get(f"{OKX}/api/v5/market/candles",
                         params={"instId": f"{symbol.upper()}-USDT",
                                 "bar": "1D", "limit": str(min(days + 5, 300))},
                         timeout=20)
        j = r.json()
        if j.get("code") != "0":
            return None
        out = []
        for row in j["data"]:
            out.append({"ts": int(row[0]), "h": float(row[2]),
                        "l": float(row[3]), "c": float(row[4])})
        return sorted(out, key=lambda x: x["ts"])
    except Exception:
        return None


def path_r(rec: dict, bars: list[dict]) -> tuple[float | None, str]:
    """
    R ازدست‌رفته با شبیه‌سازی مسیر واقعی قیمت.

    قانون: اگر استاپ فرضی **پیش از** هدف فرضی خورده باشد، نتیجه منفی یک است
    و رد **درست** بوده. این قید، دفتر را از تبدیل‌شدن به ماشه حسرت نجات می‌دهد.
    """
    e, s, t = rec.get("entry"), rec.get("stop"), rec.get("target")
    if not (e and s and t) or not bars:
        return None, "داده ناقص"
    risk = abs(e - s)
    if risk <= 0:
        return None, "ریسک صفر"
    long = t > e
    start_ms = int(datetime.strptime(rec["date"], "%Y-%m-%d")
                   .replace(tzinfo=UTC).timestamp() * 1000)
    seq = [b for b in bars if b["ts"] >= start_ms]
    if not seq:
        return None, "کندلی پس از تاریخ رد نیست"

    filled = False
    best = 0.0
    for b in seq:
        # آیا ورود فرضی پر می‌شد؟ (سفارش محدود روی سطح)
        if not filled:
            if (long and b["l"] <= e) or (not long and b["h"] >= e):
                filled = True
            else:
                continue
        if long:
            if b["l"] <= s:
                return -1.0, "استاپ فرضی پیش از هدف خورد — رد درست بود"
            if b["h"] >= t:
                return round(abs(t - e) / risk, 3), "هدف فرضی خورد — رد گران بود"
            best = max(best, (b["h"] - e) / risk)
        else:
            if b["h"] >= s:
                return -1.0, "استاپ فرضی پیش از هدف خورد — رد درست بود"
            if b["l"] <= t:
                return round(abs(e - t) / risk, 3), "هدف فرضی خورد — رد گران بود"
            best = max(best, (e - b["l"]) / risk)
    if not filled:
        return 0.0, "ورود فرضی هرگز پر نشد — رد بی‌هزینه بود"
    return round(best, 3), "هنوز باز — بهترین حرکت تا امروز"


# ─────────────────────── دستورها ───────────────────────

def cmd_add(a) -> None:
    d = load()
    rid = max([r["id"] for r in d["rejects"]], default=0) + 1
    rec = {
        "id": rid, "date": now(), "symbol": a.symbol.upper(),
        "price": a.price, "blocker": a.blocker, "grade": a.grade,
        "score": a.score, "regime": a.regime, "side": a.side,
        "entry": a.entry, "stop": a.stop, "target": a.target,
        "note": a.note,
        "p14": None, "p30": None, "r_lost": None, "r_note": None,
    }
    d["rejects"].append(rec)
    d["sessions"].append({"date": now(), "action": False,
                          "kind": "رد", "symbol": a.symbol.upper()})
    save(d)
    print(f"✅ رد ثبت شد — شناسه {rid}")
    print(f"   {rec['symbol']} در {a.price} | شرط مسدودکننده: {a.blocker}")
    print("   در ۱۴ و ۳۰ روز آینده `followup` را اجرا کن.")


def cmd_session(a) -> None:
    d = load()
    d["sessions"].append({"date": now(), "action": bool(a.action),
                          "kind": a.kind or ("اقدام" if a.action else "بدون اقدام"),
                          "symbol": (a.symbol or "").upper()})
    save(d)
    tot = len(d["sessions"])
    act = sum(1 for s in d["sessions"] if s["action"])
    print(f"✅ جلسه ثبت شد. نرخ اقدام تا امروز: {act}/{tot} = {act/tot*100:.1f}٪")


def cmd_followup(a) -> None:
    d = load()
    updated = 0
    for r in d["rejects"]:
        age = (datetime.now(UTC) - datetime.strptime(r["date"], "%Y-%m-%d")
               .replace(tzinfo=UTC)).days
        if r["r_lost"] is not None and age > 35:
            continue
        bars = candles_since(r["symbol"], max(age + 2, 5))
        if not bars:
            print(f"  {r['symbol']}: داده در دسترس نیست")
            continue
        start = datetime.strptime(r["date"], "%Y-%m-%d").replace(tzinfo=UTC)
        for k, dd in (("p14", 14), ("p30", 30)):
            if r[k] is None and age >= dd:
                tgt = int((start + timedelta(days=dd)).timestamp() * 1000)
                near = min(bars, key=lambda b: abs(b["ts"] - tgt))
                r[k] = near["c"]
        rl, note = path_r(r, bars)
        r["r_lost"], r["r_note"] = rl, note
        updated += 1
        print(f"  {r['symbol']}: R ازدست‌رفته {rl} — {note}")
    save(d)
    print(f"\n{updated} رکورد به‌روز شد.")


def cmd_report(a) -> None:
    d = load()
    rej, ses = d["rejects"], d["sessions"]
    o: list[str] = []
    W = o.append

    W("=" * 66)
    W(f"گزارش خودسنجی چارچوب — رادار {VERSION}")
    W(f"تاریخ: {now()}")
    W("=" * 66)
    W("")
    W("این گزارش **درباره بازار نیست. درباره خود رادار است.**")
    W("")

    # ── ۱ نرخ اقدام
    tot = len(ses)
    act = sum(1 for s in ses if s["action"])
    rate = act / tot * 100 if tot else 0
    W("## ۱ — نرخ اقدام")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| کل جلسات ثبت‌شده | {tot} |")
    W(f"| جلسات با اقدام اجرایی | {act} |")
    W(f"| **نرخ اقدام** | **{rate:.1f}٪** |")
    W(f"| باند سالم | {ACTION_RATE_HEALTHY[0]:.0f} تا {ACTION_RATE_HEALTHY[1]:.0f}٪ |")
    W("")
    if tot < MIN_N_SESSIONS:
        W(f"⚠️ نمونه کوچک است ({tot} از {MIN_N_SESSIONS}). "
          "هر قضاوتی اینجا یک برداشت است، نه یک اندازه‌گیری.")
    elif rate < ACTION_RATE_LOW:
        W("⛔ **نرخ اقدام زیر ۲۰٪.** تشخیص: چارچوب بیش‌ازحد سخت‌گیر است.")
        W("اقدام روی چارچوب: آستانه رده‌های کیفیت را یک پله شل کن.")
    elif rate > ACTION_RATE_HIGH:
        W("⚠️ نرخ اقدام بالای ۷۰٪. تشخیص: چارچوب بیش‌ازحد فعال است.")
        W("اقدام روی چارچوب: ضریب رژیم را یک پله پایین بیاور.")
    else:
        W("✅ نرخ اقدام در باند سالم.")
    W("")

    # ── ۲ هزینه فرصت
    scored = [r for r in rej if r["r_lost"] is not None]
    W("## ۲ — هزینه فرصت ردها")
    W("")
    if not scored:
        W("هنوز رکورد امتیازخورده‌ای نیست. `followup` را اجرا کن.")
    else:
        avg = sum(r["r_lost"] for r in scored) / len(scored)
        good = sum(1 for r in scored if r["r_lost"] <= 0)
        W("| مورد | مقدار |")
        W("|---|---|")
        W(f"| رکوردهای ارزیابی‌شده | {len(scored)} |")
        W(f"| **هزینه فرصت متوسط** | **{avg:+.3f}R** |")
        W(f"| ردهای درست (R ≤ ۰) | {good} از {len(scored)} = {good/len(scored)*100:.0f}٪ |")
        W(f"| آستانه هشدار | +{OPP_COST_ALARM}R |")
        W("")
        if len(scored) < MIN_N_RECORDS:
            W(f"⚠️ نمونه کوچک ({len(scored)} از {MIN_N_RECORDS}).")
        elif avg > OPP_COST_ALARM:
            W("⛔ **ردها گران‌اند.** تشخیص: شرط پرتکرارِ مسدودکننده کالیبره نیست.")
            W("اقدام: آن شرط را شل کن یا به ضریب اندازه تبدیلش کن.")
        else:
            W("✅ هزینه فرصت در محدوده قابل‌قبول. ردها به‌طور متوسط محافظت کرده‌اند.")
        W("")
        W("| # | نماد | تاریخ | شرط مسدودکننده | R ازدست‌رفته | خوانش |")
        W("|---|---|---|---|---|---|")
        for r in sorted(scored, key=lambda x: -(x["r_lost"] or 0))[:15]:
            W(f"| {r['id']} | {r['symbol']} | {r['date']} | {r['blocker']} | "
              f"{r['r_lost']:+.2f} | {r['r_note']} |")
    W("")

    # ── ۳ توزیع شرط مسدودکننده
    W("## ۳ — توزیع شرط مسدودکننده")
    W("")
    if not rej:
        W("رکوردی نیست.")
    else:
        cnt: dict[str, int] = {}
        for r in rej:
            cnt[r["blocker"]] = cnt.get(r["blocker"], 0) + 1
        W("| شرط | تعداد | سهم | R متوسط |")
        W("|---|---|---|---|")
        flagged = []
        for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
            share = v / len(rej) * 100
            sub = [r["r_lost"] for r in rej
                   if r["blocker"] == k and r["r_lost"] is not None]
            avg_r = sum(sub) / len(sub) if sub else None
            W(f"| {k} | {v} | {share:.0f}٪ | "
              f"{f'{avg_r:+.2f}' if avg_r is not None else '—'} |")
            if share > BLOCKER_CONC_ALARM:
                flagged.append((k, share, avg_r))
        W("")
        for k, share, avg_r in flagged:
            W(f"⛔ **شرط «{k}» تنهایی {share:.0f}٪ ردها را ساخته** "
              f"(آستانه {BLOCKER_CONC_ALARM:.0f}٪).")
            # سه حالت جدا: تهی یعنی «داده ندارم»، نه منفی — قانون مادر داده
            if avg_r is None:
                W("   ولی R ازدست‌رفته‌اش هنوز محاسبه نشده — درباره گرانی یا")
                W("   محافظتش نمی‌شود قضاوت کرد. `followup` را اجرا کن.")
            elif avg_r > 0:
                W(f"   و R متوسطش {avg_r:+.2f} است — یعنی این شرط گران است.")
                W("   اقدام: شل کن یا به ضریب اندازه تبدیلش کن.")
            else:
                W("   ولی R متوسطش صفر یا منفی است — یعنی محافظت کرده. فعلاً نگهش دار.")
    W("")

    W("## ۴ — یادآوری")
    W("")
    W("سه فرضیه رقیب برای «رادار درست عمل نمی‌کند»:")
    W("")
    W("| فرضیه | نشانه |")
    W("|---|---|")
    W("| چارچوب شل است | نرخ برد پایین‌تر از احتمال اعلام‌شده |")
    W("| **چارچوب سخت‌گیر است** | **نرخ اقدام پایین + هزینه فرصت مثبت** |")
    W("| رژیم خصمانه است | ضرر متمرکز در لانگ آلت؛ شورت و نقد خوب بوده |")
    W("| نمونه کوچک است | زیر آستانه‌های بالا |")
    W("")
    W("سطر دوم تا ۵.۴ اصلاً قابل تشخیص نبود.")

    txt = "\n".join(o)
    if getattr(a, "out", None):
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"ذخیره شد در {a.out}")
    print(txt)


def main() -> int:
    ap = argparse.ArgumentParser(description=f"دفتر هزینه فرصت — رادار {VERSION}")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("add", help="ثبت یک حکم رد یا صبر")
    p.add_argument("--symbol", required=True)
    p.add_argument("--price", type=float, required=True, help="قیمت در لحظه رد")
    p.add_argument("--blocker", required=True, help="کدام وتو یا کدام ضریب صفر کرد")
    p.add_argument("--grade", default="", help="رده کیفیت ستاپ")
    p.add_argument("--score", type=float, default=None)
    p.add_argument("--regime", type=float, default=None)
    p.add_argument("--side", choices=["long", "short"], default="long")
    p.add_argument("--entry", type=float, default=None, help="ورود فرضی")
    p.add_argument("--stop", type=float, default=None, help="استاپ فرضی")
    p.add_argument("--target", type=float, default=None, help="هدف فرضی")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sp.add_parser("session", help="ثبت یک جلسه تحلیل برای محاسبه نرخ اقدام")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--action", action="store_true", help="جلسه به اقدام اجرایی ختم شد")
    g.add_argument("--no-action", dest="action", action="store_false")
    p.add_argument("--kind", default=None, help="نوع اقدام: ورود / کاهش / چرخش / سفارش در انتظار")
    p.add_argument("--symbol", default=None)
    p.set_defaults(func=cmd_session)

    p = sp.add_parser("followup", help="پرکردن قیمت ۱۴ و ۳۰ روزه و محاسبه R ازدست‌رفته")
    p.set_defaults(func=cmd_followup)

    p = sp.add_parser("report", help="گزارش خودسنجی چارچوب")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_report)

    a = ap.parse_args()
    a.func(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
