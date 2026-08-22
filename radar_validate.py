#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_validate.py — سنجش اعتبار موتور امتیازدهی، رادار ۶.۱
============================================================

چرا این فایل تعیین‌کننده است
----------------------------
ممیزی مخزن نشان داد: **صفر فایل آزمون، صفر بک‌تست، صفر اعتبارسنجی.**

یعنی هیچ‌کس هرگز نسنجیده بود که امتیاز رادار اصلاً بازده آینده را
پیش‌بینی می‌کند یا نه. همه نسخه‌ها — از ۳ تا ۶ — بر پایه استدلال
ساخته شده‌اند، نه بر پایه اندازه‌گیری.

استدلال خوب لازم است، ولی کافی نیست. این اسکریپت پرسش اصلی را می‌پرسد:

    آیا کوین با امتیاز بالاتر، بازده ۳۰ روزه بهتری داشته؟

اگر پاسخ منفی باشد، موتور امتیازدهی برتری ندارد و باید بازنویسی شود —
هر چقدر هم استدلالش زیبا باشد.

قیدهای روش‌شناختی که رعایت می‌شوند
-----------------------------------
  • بدون نگاه به آینده: امتیاز روز t فقط از داده تا روز t ساخته می‌شود
  • کارمزد و لغزش کسر می‌شود
  • بازده در برابر بیت‌کوین هم گزارش می‌شود (بازده مطلق در بازار خرسی گمراه‌کننده است)
  • نرخ پایه گزارش می‌شود، نه فقط نمونه‌های موافق
  • تعداد نمونه هر سطل نشان داده می‌شود — سطل با نمونه کم قضاوت نمی‌شود

نمونه اجرا
----------
    python radar_validate.py --symbols BTC,ETH,SOL,LINK,AAVE,SUI,ONDO,TAO \
        --horizon 30 --out validate.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

try:
    import requests
    import pandas as pd
    import numpy as np
except ImportError:
    print("نیاز: pip install requests pandas numpy")
    sys.exit(1)

VERSION = "6.1"
UTC = timezone.utc
OKX = "https://www.okx.com"

FEE_ROUNDTRIP = 0.20   # درصد — ورود و خروج
SLIPPAGE = 0.10        # درصد
MIN_BUCKET_N = 20      # کمتر از این، سطل قضاوت نمی‌شود


def candles(symbol: str, want: int = 900) -> pd.DataFrame | None:
    rows, after = [], None
    try:
        while len(rows) < want:
            p = {"instId": f"{symbol.upper()}-USDT", "bar": "1D", "limit": "100"}
            if after:
                p["after"] = after
            j = requests.get(f"{OKX}/api/v5/market/candles",
                             params=p, timeout=20).json()
            if j.get("code") != "0" or not j.get("data"):
                break
            rows.extend(j["data"])
            after = j["data"][-1][0]
            if len(j["data"]) < 100:
                break
    except Exception:
        return None
    if len(rows) < 250:
        return None
    df = pd.DataFrame([{"ts": int(r[0]), "o": float(r[1]), "h": float(r[2]),
                        "l": float(r[3]), "c": float(r[4]), "v": float(r[5])}
                       for r in rows])
    return df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi_wilder(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, 1e-12))


def score_series(df: pd.DataFrame, btc: pd.DataFrame,
                 rs_days: int = 30) -> pd.Series:
    """
    همان موتور امتیازدهی radar_book.py، ولی به‌صورت سری زمانی.

    قید ضدنگاه‌به‌آینده: هر عدد فقط از داده تا همان کندل ساخته می‌شود.
    میانگین‌های نمایی و شاخص قدرت نسبی ذاتاً گذشته‌نگرند، پس امن‌اند.
    """
    c = df["c"]
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    r = rsi_wilder(c)

    # ── بُعد ۱: ساختار
    s = pd.Series(0.0, index=df.index)
    s += np.where(c > e20, 0.5, -0.5)
    s += np.where(c > e50, 0.5, -0.5)
    s += np.where(e20 > e50, 0.5, -0.5)
    s += np.where(c > e200, 0.5, -0.5)
    struct = s.clip(-2, 2)

    # ── بُعد ۲: مومنتوم — فقط یک ابزار از خانواده (محافظ هم‌خطی)
    mom = pd.Series(np.select(
        [r >= 60, r >= 50, r >= 40, r >= 30],
        [1.0, 0.5, -0.5, -1.0], default=-1.5), index=df.index)

    # ── بُعد ۳: قدرت نسبی به بیت‌کوین
    m = df[["ts", "c"]].merge(btc[["ts", "c"]], on="ts",
                              how="left", suffixes=("", "_b"))
    m["c_b"] = m["c_b"].ffill()
    ret_a = m["c"] / m["c"].shift(rs_days) - 1
    ret_b = m["c_b"] / m["c_b"].shift(rs_days) - 1
    rs = (ret_a - ret_b).values
    rel = pd.Series(np.select(
        [rs > 0.10, rs > 0.02, rs > -0.02, rs > -0.10],
        [2.0, 1.0, 0.0, -1.0], default=-2.0), index=df.index)
    rel[pd.isna(rs)] = np.nan

    w = {"struct": 0.45, "mom": 0.20, "rel": 0.35}
    num = struct * w["struct"] + mom * w["mom"] + rel.fillna(0) * w["rel"]
    den = w["struct"] + w["mom"] + np.where(rel.isna(), 0, w["rel"])
    out = num / den
    out[:200] = np.nan          # قانون بلوغ میانگین ۲۰۰
    return out


def bucket(x: float) -> str:
    if pd.isna(x):
        return "بدون داده"
    if x >= 1.2:
        return "بسیار قوی (۱.۲+)"
    if x >= 0.8:
        return "قوی (۰.۸ تا ۱.۲)"
    if x >= 0.4:
        return "متوسط (۰.۴ تا ۰.۸)"
    if x >= 0.0:
        return "ضعیف (۰ تا ۰.۴)"
    if x >= -0.8:
        return "منفی (−۰.۸ تا ۰)"
    return "بسیار منفی (زیر −۰.۸)"


ORDER = ["بسیار قوی (۱.۲+)", "قوی (۰.۸ تا ۱.۲)", "متوسط (۰.۴ تا ۰.۸)",
         "ضعیف (۰ تا ۰.۴)", "منفی (−۰.۸ تا ۰)", "بسیار منفی (زیر −۰.۸)"]


def main() -> int:
    ap = argparse.ArgumentParser(description=f"سنجش اعتبار موتور امتیازدهی — رادار {VERSION}")
    ap.add_argument("--symbols", default="BTC,ETH,SOL,LINK,AAVE,SUI,ONDO,TAO,XRP,BNB")
    ap.add_argument("--horizon", type=int, default=30, help="افق بازده به روز")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    print("واکشی بیت‌کوین به‌عنوان مرجع...")
    btc = candles("BTC")
    if btc is None:
        print("داده بیت‌کوین در دسترس نیست. شبکه یا صرافی را بررسی کن.")
        return 1

    frames = []
    for s in syms:
        print(f"  {s} ...")
        df = candles(s)
        if df is None or len(df) < 300:
            print(f"    داده ناکافی — رد شد")
            continue
        sc = score_series(df, btc)
        h = a.horizon
        fwd = df["c"].shift(-h) / df["c"] - 1
        bfwd = btc.set_index("ts")["c"].reindex(df["ts"]).ffill().values
        bfwd = pd.Series(bfwd, index=df.index)
        bret = bfwd.shift(-h) / bfwd - 1
        frames.append(pd.DataFrame({
            "symbol": s, "score": sc,
            "fwd": fwd - (FEE_ROUNDTRIP + SLIPPAGE) / 100,
            "rel": (fwd - bret),
        }))

    if not frames:
        print("هیچ نمادی داده کافی نداشت.")
        return 1

    d = pd.concat(frames).dropna(subset=["score", "fwd"])
    d["bucket"] = d["score"].apply(bucket)

    o: list[str] = []
    W = o.append
    W(f"# سنجش اعتبار موتور امتیازدهی — رادار {VERSION}")
    W("")
    W(f"تاریخ اجرا: {datetime.now(UTC).strftime('%Y-%m-%d')}")
    W(f"نمادها: {'، '.join(syms)}")
    W(f"افق بازده: {a.horizon} روز | کارمزد و لغزش کسرشده: "
      f"{FEE_ROUNDTRIP + SLIPPAGE:.2f}٪")
    W(f"کل مشاهدات: {len(d):,}")
    W("")
    W("## پرسش")
    W("")
    W("آیا کوین با امتیاز بالاتر، بازده آینده بهتری داشته؟")
    W("اگر پاسخ منفی باشد، موتور امتیازدهی برتری ندارد — هر چقدر هم استدلالش خوب باشد.")
    W("")

    W("## نتیجه به تفکیک سطل امتیاز")
    W("")
    W("| سطل | نمونه | بازده متوسط | میانه | نرخ مثبت | بازده نسبت به بیت‌کوین |")
    W("|---|---|---|---|---|---|")
    rows = []
    for b in ORDER:
        g = d[d["bucket"] == b]
        if len(g) == 0:
            continue
        mean = g["fwd"].mean() * 100
        med = g["fwd"].median() * 100
        pos = (g["fwd"] > 0).mean() * 100
        rel = g["rel"].mean() * 100
        flag = "" if len(g) >= MIN_BUCKET_N else " ⚠️"
        W(f"| {b}{flag} | {len(g):,} | {mean:+.2f}٪ | {med:+.2f}٪ | "
          f"{pos:.0f}٪ | {rel:+.2f}٪ |")
        rows.append((b, len(g), mean, rel))
    W("")
    W(f"⚠️ = نمونه کمتر از {MIN_BUCKET_N}؛ قضاوت‌پذیر نیست.")
    W("")

    # ── نرخ پایه
    base = d["fwd"].mean() * 100
    base_rel = d["rel"].mean() * 100
    W("## نرخ پایه")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| بازده متوسط همه مشاهدات | {base:+.2f}٪ |")
    W(f"| بازده متوسط نسبت به بیت‌کوین | {base_rel:+.2f}٪ |")
    W("")
    W("**هر سطلی که از این عدد بهتر نباشد، ارزش افزوده‌ای نساخته.**")
    W("")

    # ── همبستگی رتبه‌ای
    valid = d.dropna(subset=["score", "fwd"])
    ic = valid["score"].corr(valid["fwd"], method="spearman")
    ic_rel = valid["score"].corr(valid["rel"], method="spearman")
    W("## ضریب اطلاعات (همبستگی رتبه‌ای امتیاز و بازده)")
    W("")
    W("| سنجه | مقدار | خوانش |")
    W("|---|---|---|")

    def read(v):
        if pd.isna(v):
            return "قابل محاسبه نیست"
        if v > 0.05:
            return "برتری معنادار"
        if v > 0.02:
            return "برتری ضعیف ولی واقعی"
        if v > -0.02:
            return "**بدون برتری — امتیاز پیش‌بینی نمی‌کند**"
        return "**برتری معکوس — امتیاز برعکس کار می‌کند**"

    W(f"| بازده مطلق | {ic:+.4f} | {read(ic)} |")
    W(f"| بازده نسبت به بیت‌کوین | {ic_rel:+.4f} | {read(ic_rel)} |")
    W("")
    W("در مدیریت دارایی، ضریب اطلاعات بالای ۰.۰۵ روی نمونه بزرگ، عدد محترمی است.")
    W("زیر ۰.۰۲ یعنی امتیاز عملاً تصادفی است.")
    W("")

    # ── حکم
    W("## حکم")
    W("")
    top = [r for r in rows if r[0].startswith("بسیار قوی") or r[0].startswith("قوی")]
    bot = [r for r in rows if r[0].startswith("بسیار منفی") or r[0].startswith("منفی")]
    t_mean = sum(r[2] * r[1] for r in top) / sum(r[1] for r in top) if top else None
    b_mean = sum(r[2] * r[1] for r in bot) / sum(r[1] for r in bot) if bot else None

    if t_mean is not None and b_mean is not None:
        spread = t_mean - b_mean
        W(f"| مورد | مقدار |")
        W(f"|---|---|")
        W(f"| بازده متوسط سطل‌های قوی | {t_mean:+.2f}٪ |")
        W(f"| بازده متوسط سطل‌های منفی | {b_mean:+.2f}٪ |")
        W(f"| **فاصله (اسپرد)** | **{spread:+.2f}٪** |")
        W("")
        if spread > 3 and (ic or 0) > 0.03:
            W("✅ **موتور امتیازدهی برتری نشان می‌دهد.** امتیاز بالا با بازده بهتر همراه بوده.")
            W("این اجازه می‌دهد به آستانه‌های رده کیفیت اعتماد شود.")
        elif spread > 0:
            W("⚠️ **برتری ضعیف.** جهت درست است ولی فاصله کوچک است.")
            W("آستانه‌های رده کیفیت باید محافظه‌کارانه بمانند تا نمونه بزرگ‌تر شود.")
        else:
            W("⛔ **برتری‌ای دیده نمی‌شود.** امتیاز، بازده آینده را پیش‌بینی نکرده.")
            W("")
            W("این یعنی موتور امتیازدهی باید بازنویسی شود، نه اینکه آستانه‌ها")
            W("تنظیم شوند. تنظیم آستانه روی موتوری که سیگنال ندارد، بی‌فایده است.")
    W("")

    W("## محدودیت‌های صادقانه این آزمون")
    W("")
    W("| محدودیت | اثر |")
    W("|---|---|")
    W("| فقط داده اوکی‌اکس | عمر نمادهای تازه کوتاه است |")
    W("| مشاهدات هم‌پوشان روزانه | نمونه مؤثر کمتر از عدد نشان‌داده‌شده است |")
    W("| همه نمادها همبسته‌اند | یک رژیم بازار، نه چند رژیم مستقل |")
    W("| بدون بلوک جریان و ماکرو | فقط بُعد فنی سنجیده شد، نه کل رادار |")
    W("| بدون مدیریت پوزیشن | بازده خام، نه بازده با استاپ و نردبان خروج |")
    W("")
    W("**نتیجه این آزمون، کف اعتبار است نه سقف آن.** اگر اینجا برتری نباشد،")
    W("بعید است با افزودن لایه‌های دیگر پیدا شود.")

    txt = "\n".join(o)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\nذخیره شد در {a.out}")
    print("\n" + txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
