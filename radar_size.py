#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_size.py — موتور اندازه مدرج رادار ۶.۰
============================================

مسئله‌ای که حل می‌کند
---------------------
رادار ۵.۴ فقط دو خروجی داشت: ورود با ریسک ۲٪، یا هیچ.
این یک تابع پله‌ای روی متغیری پیوسته بود. نتیجه: نرخ عبور حدود ۱.۵٪.

۶.۰ اندازه را تابع پیوسته چهار ضریب می‌کند:

    ریسک٪ = ۲.۰ × ضریب رژیم × ضریب کیفیت × ضریب پوشش × ضریب جریان

هیچ ضریبی صفر نمی‌شود مگر رده کیفیت F یا فعال‌شدن یکی از چهار وتوی واقعی.

چهار وتوی واقعی (تنها موارد توقف کامل)
--------------------------------------
  ۱) نقطه ابطال تعریف‌نشده، یا قیمت لیکوئید نزدیک‌تر از ابطال
  ۲) امید ریاضی منفی
  ۳) نقدشوندگی ناکافی یا آزادسازی توکن بزرگ  (پرچم دستی)
  ۴) بودجه ریسک رژیم کاملاً مصرف شده

نمونه اجرا
----------
    python radar_size.py --balance 2500 --regime -1.25 --score 1.35 \
        --rr 4.66 --coverage 78 --flow 3 --entry 497.15 --stop 478.0 \
        --invalidation 480.43 --target 575 --win-prob 0.45 \
        --side long --open-risk 0.9 --structural
"""

from __future__ import annotations

import argparse
import sys

VERSION = "6.0"

# ─────────────────────── جدول‌های مرجع ───────────────────────

# (کف امتیاز رژیم، نام، سقف ریسک باز٪، ضریب اندازه، حداکثر پوزیشن هم‌جهت، هدف ذخیره٪)
REGIMES = [
    (0.50,  "انبساطی", 8.0, 1.00, 5, 10),
    (0.00,  "سازنده",  6.0, 0.75, 4, 15),
    (-0.50, "محتاط",   4.0, 0.50, 3, 25),
    (-1.20, "انقباضی", 2.5, 0.30, 2, 40),
    (-99.0, "بحرانی",  1.5, 0.20, 1, 55),
]

BASE_RISK = 2.0          # ریسک پایه درصد حساب
SWAP_COST_SCORE = 0.15   # هزینه تعویض بر حسب واحد امتیاز
MIN_TICKET_RATIO = 0.15  # سقف نسبت کارمزد به ریسک دلاری


def regime_row(score: float):
    """ردیف رژیم را از امتیاز برمی‌گرداند."""
    for floor, name, cap, mult, maxpos, stable in REGIMES:
        if score >= floor:
            return {"name": name, "cap": cap, "mult": mult,
                    "maxpos": maxpos, "stable": stable}
    return {"name": "بحرانی", "cap": 1.5, "mult": 0.20, "maxpos": 1, "stable": 55}


def quality_grade(score: float, rr: float, side: str,
                  structural: bool, regime_name: str,
                  structureless: bool = False,
                  anchors_scattered: bool = False) -> tuple[str, float, list[str]]:
    """
    رده کیفیت ستاپ را برمی‌گرداند: (رده، ضریب، فهرست دلایل تعدیل)

    برای شورت، امتیاز از موتور شورت مستقل می‌آید (مقیاس ۰ تا ۲)،
    نه از معکوس‌کردن امتیاز لانگ. آستانه‌ها متفاوت‌اند.
    """
    notes: list[str] = []

    if side == "long":
        if score >= 1.20 and rr >= 4 and structural:
            base = "A"
        elif score >= 0.80 and rr >= 3:
            base = "B"
        elif score >= 0.40 and rr >= 2:
            base = "C"
        elif score >= 0.00 and rr >= 1.5:
            base = "D"
        else:
            base = "F"
    else:  # short — مقیاس ۰ تا ۲ از موتور شورت مستقل
        if score >= 1.50 and rr >= 4:
            base = "A"
        elif score >= 1.20 and rr >= 3:
            base = "B"
        elif score >= 0.90 and rr >= 2:
            base = "C"
        elif score >= 0.60 and rr >= 1.5:
            base = "D"
        else:
            base = "F"

    order = ["F", "D", "C", "B", "A"]
    idx = order.index(base)

    # ── تعدیل‌های پایین‌برنده
    if side == "long" and regime_name in ("انقباضی", "بحرانی"):
        idx = max(0, idx - 1)
        notes.append("لانگ آلت در رژیم منفی — یک رده پایین (معامله خلاف‌روند)")

    if structureless and idx > order.index("C"):
        idx = order.index("C")
        notes.append("ساختار بی‌ساختار — سقف رده C (جهت نامعلوم، ولی سطح معلوم)")

    if anchors_scattered:
        idx = max(0, idx - 1)
        notes.append("نقاط کنترل سه لنگر پراکنده — یک رده پایین")

    # ── تعدیل بالابرنده: هم‌گرایی کامل روی سطح ساختاری
    if structural and not anchors_scattered and not structureless and rr >= 5:
        if idx < order.index("A"):
            idx += 1
            notes.append("ورود روی سطح ساختاری + لنگرهای هم‌گرا + نسبت بالای ۵ — یک رده بالا")

    grade = order[idx]
    mult = {"A": 2.00, "B": 1.50, "C": 1.00, "D": 0.50, "F": 0.0}[grade]
    return grade, mult, notes


def coverage_mult(cov: float) -> tuple[float, str]:
    if cov >= 80:
        return 1.00, "پوشش کامل"
    if cov >= 65:
        return 0.85, "پوشش خوب"
    if cov >= 50:
        return 0.70, "پوشش متوسط"
    if cov >= 35:
        return 0.50, "پوشش ضعیف — ورود کاوشی"
    return 0.30, "نابینایی نسبی — اندازه نمادین"


def flow_mult(n: int) -> tuple[float, str]:
    if n >= 3:
        return 1.00, "بلوک جریان کافی"
    if n == 2:
        return 0.85, "بلوک جریان ناقص"
    if n == 1:
        return 0.70, "بلوک جریان بسیار ناقص"
    return 0.50, "کور نسبت به جریان"


def expectancy(win_prob: float, rr: float) -> float:
    """امید ریاضی به واحد R."""
    return win_prob * rr - (1 - win_prob) * 1.0


def entry_ladder(near: float, poc: float, far: float,
                 regime_name: str) -> list[tuple[float, float]]:
    """
    نردبان ورود سه‌پله‌ای.
    در رژیم منفی، وزن به پله‌های دورتر منتقل می‌شود چون احتمال
    رسیدن قیمت به سطح دور بالاتر است.
    """
    if regime_name in ("انقباضی", "بحرانی"):
        w = (0.10, 0.30, 0.60)
    else:
        w = (0.20, 0.35, 0.45)
    return list(zip((near, poc, far), w))


def weighted_entry(ladder: list[tuple[float, float]]) -> float:
    return sum(p * w for p, w in ladder) / sum(w for _, w in ladder)


def fmt(x, d=4):
    if x is None:
        return "—"
    return f"{x:,.{d}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


# ─────────────────────── محاسبه اصلی ───────────────────────

def compute(a) -> str:
    out: list[str] = []
    W = out.append

    reg = regime_row(a.regime)

    # ورود مؤثر: اگر نردبان داده شده، میانگین وزنی؛ وگرنه ورود تک‌نقطه‌ای
    ladder = None
    if a.ladder_near and a.ladder_poc and a.ladder_far:
        ladder = entry_ladder(a.ladder_near, a.ladder_poc, a.ladder_far, reg["name"])
        eff_entry = weighted_entry(ladder)
    else:
        eff_entry = a.entry

    # نسبت: اگر هدف داده شده از ورود مؤثر بازمحاسبه کن
    rr = a.rr
    if a.target and a.stop:
        risk_d = abs(eff_entry - a.stop)
        rew_d = abs(a.target - eff_entry)
        if risk_d > 0:
            rr = rew_d / risk_d

    grade, qmult, qnotes = quality_grade(
        a.score, rr, a.side, a.structural, reg["name"],
        structureless=a.structureless, anchors_scattered=a.scattered)

    cmult, cnote = coverage_mult(a.coverage)
    fmult, fnote = flow_mult(a.flow)

    # ── چهار وتوی واقعی
    vetoes: list[str] = []

    if a.invalidation is None:
        vetoes.append("وتو ۱ — نقطه ابطال ساختاری تعریف نشده")
    elif a.liq is not None:
        if a.side == "long" and a.liq >= a.invalidation:
            vetoes.append(f"وتو ۱ — قیمت لیکوئید {fmt(a.liq)} بالاتر از ابطال {fmt(a.invalidation)}؛ اهرم زیاد است")
        if a.side == "short" and a.liq <= a.invalidation:
            vetoes.append(f"وتو ۱ — قیمت لیکوئید {fmt(a.liq)} پایین‌تر از ابطال {fmt(a.invalidation)}؛ اهرم زیاد است")

    ev = expectancy(a.win_prob, rr) if a.win_prob is not None else None
    if ev is not None and ev <= 0:
        vetoes.append(f"وتو ۲ — امید ریاضی منفی ({ev:+.2f}R). در هیچ اندازه‌ای سودده نیست")

    if a.illiquid:
        vetoes.append("وتو ۳ — نقدشوندگی ناکافی یا آزادسازی توکن بزرگ در افق معامله")

    free = reg["cap"] - a.open_risk
    if free <= 0:
        vetoes.append(f"وتو ۴ — بودجه رژیم مصرف شده (سقف {reg['cap']}٪، باز {a.open_risk}٪)")

    # ── ریسک نهایی
    raw = BASE_RISK * reg["mult"] * qmult * cmult * fmult
    capped = min(raw, 2.0)
    if grade == "D":
        capped = min(capped, 1.0)
    final = min(capped, max(free, 0.0))

    # ── گزارش
    W("=" * 66)
    W(f"موتور اندازه مدرج — رادار {VERSION}")
    W("=" * 66)
    W("")
    W("## ۱ — رژیم و بودجه")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| امتیاز رژیم | {a.regime:+.2f} |")
    W(f"| نام رژیم | {reg['name']} |")
    W(f"| سقف ریسک باز کل | {reg['cap']}٪ |")
    W(f"| ریسک باز فعلی | {a.open_risk}٪ |")
    W(f"| **ظرفیت آزاد** | **{max(free,0):.2f}٪** |")
    W(f"| ضریب اندازه رژیم | {reg['mult']:.2f} |")
    W(f"| حداکثر پوزیشن هم‌جهت | {reg['maxpos']} |")
    W(f"| هدف ذخیره استیبل | {reg['stable']}٪ |")
    W("")

    W("## ۲ — کیفیت ستاپ و ضرایب")
    W("")
    W("| ضریب | مقدار | توضیح |")
    W("|---|---|---|")
    W(f"| رژیم | {reg['mult']:.2f} | {reg['name']} |")
    W(f"| کیفیت | {qmult:.2f} | رده {grade} — امتیاز {a.score:+.2f}، نسبت {rr:.2f} |")
    W(f"| پوشش داده | {cmult:.2f} | {cnote} ({a.coverage:.0f}٪) |")
    W(f"| بلوک جریان | {fmult:.2f} | {fnote} ({a.flow} از ۴) |")
    W(f"| **حاصل‌ضرب** | **{reg['mult']*qmult*cmult*fmult:.3f}** | |")
    W("")
    for n in qnotes:
        W(f"- تعدیل رده: {n}")
    if qnotes:
        W("")

    W("## ۳ — وتوهای واقعی")
    W("")
    if vetoes:
        for v in vetoes:
            W(f"- ⛔ {v}")
        W("")
        W("**حکم: توقف کامل.** وتو با کوچک‌کردن اندازه حل نمی‌شود.")
        W("")
        W("گزینه‌های جایگزین (بند ۸.۴ اسکیل):")
        W("- سفارش در انتظار روی سطح دورتر تا رده کیفیت بالا برود")
        W("- چرخش خنثی‌ریسک به‌جای ورود جدید — ریسک اضافه نمی‌کند")
        W("- هشدار قیمتی روی ماشه عینی + بازبینی سبد")
        W("")
        return "\n".join(out)
    W("- ✅ هیچ وتویی فعال نیست")
    W("")

    if grade == "F":
        W("## ۴ — حکم: رده F")
        W("")
        W("**دلیل دقیق:**")
        base_grade = quality_grade(a.score, rr, a.side, a.structural,
                                   "محتاط", False, False)[0]
        if base_grade != "F":
            W(f"- ستاپ خام رده **{base_grade}** بود، ولی تعدیل‌ها آن را به F رساندند:")
            for n in qnotes:
                W(f"  - {n}")
        else:
            thr = {"long": [("D", 0.00, 1.5), ("C", 0.40, 2.0)],
                   "short": [("D", 0.60, 1.5), ("C", 0.90, 2.0)]}[a.side]
            g, smin, rmin = thr[0]
            if a.score < smin:
                W(f"- امتیاز {a.score:+.2f} زیر آستانه رده D ({smin:+.2f}) است")
            if rr < rmin:
                W(f"- نسبت {rr:.2f} زیر آستانه رده D ({rmin}) است")
        W("")

        # قیمت ورود لازم برای رسیدن به هر رده — بخش عملی
        if a.target and a.stop:
            W("**این «هرگز» نیست، «در این قیمت نه». قیمت ورود لازم برای هر رده:**")
            W("")
            W("| رده | نسبت لازم | قیمت ورود لازم | فاصله از قیمت فعلی |")
            W("|---|---|---|---|")
            for g, need in (("D", 1.5), ("C", 2.0), ("B", 3.0), ("A", 4.0)):
                # حل معادله: |target - E| / |E - stop| = need
                if a.side == "long":
                    E = (a.target + need * a.stop) / (1 + need)
                else:
                    E = (a.target + need * a.stop) / (1 + need)
                d = (E - a.entry) / a.entry * 100
                W(f"| {g} | {need} | {fmt(E)} | {d:+.2f}٪ |")
            W("")
            W("این جدول همان اصل فاصله ورود تا ابطال است: نسبت با جای ورود ساخته می‌شود، نه با تنگ‌کردن استاپ.")
            W("")
        W("**اقدام امروز:** سفارش در انتظار روی قیمت رده C یا B بگذار، به‌علاوه هشدار قیمتی.")
        W("سفارش در انتظار زیر سطح ابطال ممنوع است.")
        return "\n".join(out)

    # ── اندازه پوزیشن
    risk_usd = a.balance * final / 100.0
    stop_pct = abs(eff_entry - a.stop) / eff_entry * 100.0 if a.stop else None
    size_usd = risk_usd / (stop_pct / 100.0) if stop_pct else None
    lev = size_usd / a.margin if (size_usd and a.margin) else None

    W("## ۴ — اندازه نهایی")
    W("")
    W("```")
    W(f"ریسک٪ = {BASE_RISK} × {reg['mult']:.2f} × {qmult:.2f} × {cmult:.2f} × {fmult:.2f} = {raw:.3f}٪")
    if capped < raw:
        W(f"پس از سقف رده: {capped:.3f}٪")
    if final < capped:
        W(f"پس از سقف ظرفیت آزاد: {final:.3f}٪")
    W("```")
    W("")
    W("| مورد | مقدار |")
    W("|---|---|")
    W(f"| رده کیفیت | **{grade}** |")
    W(f"| ریسک نهایی | **{final:.3f}٪ حساب** |")
    W(f"| ریسک دلاری | {risk_usd:,.2f} دلار |")
    W(f"| ورود مؤثر | {fmt(eff_entry)} |")
    W(f"| حد ضرر | {fmt(a.stop)} |")
    W(f"| فاصله استاپ | {stop_pct:.2f}٪ |" if stop_pct else "| فاصله استاپ | — |")
    W(f"| **اندازه پوزیشن** | **{size_usd:,.2f} دلار** |" if size_usd else "| اندازه پوزیشن | — |")
    if lev:
        W(f"| اهرم لازم (مارجین {a.margin:,.0f}) | {lev:.2f}× |")
    if a.invalidation is not None:
        d_inv = abs(eff_entry - a.invalidation)
        W(f"| فاصله ورود مؤثر تا ابطال | {fmt(d_inv)} |")
        if a.target:
            d_tgt = abs(a.target - eff_entry)
            W(f"| نسبت فاصله ابطال به هدف | {d_inv/d_tgt:.3f} "
              f"({'✅ زیر یک‌سوم' if d_inv/d_tgt < 0.3333 else '⚠️ بالای یک‌سوم'}) |")
    W(f"| نسبت ریسک به ریوارد | {rr:.2f} |")
    if ev is not None:
        W(f"| امید ریاضی | {ev:+.3f}R (احتمال برد {a.win_prob:.0%}) |")
    W(f"| حرارت سبد پس از ورود | {a.open_risk + final:.2f}٪ از {reg['cap']}٪ |")
    W("")

    # ── آزمون کمینه بلیت
    if size_usd:
        rt_cost = size_usd * (a.fee * 2 + a.slip) / 100.0
        ratio = rt_cost / risk_usd if risk_usd > 0 else 99
        ok = ratio <= MIN_TICKET_RATIO
        W("## ۵ — آزمون کمینه بلیت")
        W("")
        W("| مورد | مقدار |")
        W("|---|---|")
        W(f"| هزینه رفت‌وبرگشت | {rt_cost:,.3f} دلار |")
        W(f"| نسبت به ریسک دلاری | {ratio:.1%} |")
        W(f"| حکم | {'✅ به‌صرفه' if ok else '⚠️ به‌صرفه نیست'} |")
        W("")
        if not ok:
            W("**اندازه بیش‌ازحد کوچک شد. سه گزینه — نه «بدون ورود»:**")
            W("")
            W("- **الف)** سفارش در انتظار روی سطح دورتر بگذار تا نسبت و رده بالا برود")
            W("- **ب)** همان سرمایه را از راه **چرخش سبد** به کار بگیر — ریسک جدید اضافه نمی‌کند و تابع رژیم نیست")
            W("- **ج)** صبر تا رژیم یک پله بهبود یابد؛ ماشه عینی و قیمتی بنویس")
            W("")

    # ── نردبان ورود
    W("## ۶ — نردبان ورود")
    W("")
    if ladder:
        W("| پله | قیمت | سهم | حجم دلاری |")
        W("|---|---|---|---|")
        for i, (px, w) in enumerate(ladder, 1):
            W(f"| {i} | {fmt(px)} | {w:.0%} | {size_usd*w:,.2f} |" if size_usd
              else f"| {i} | {fmt(px)} | {w:.0%} | — |")
        W("")
        W(f"**ورود مؤثر (میانگین وزنی): {fmt(eff_entry)}**")
        W("")
        if a.invalidation is not None:
            single_rr = (abs(a.target - a.entry) / abs(a.entry - a.stop)) if (a.target and a.stop) else None
            if single_rr:
                W("| حالت | ورود | نسبت |")
                W("|---|---|---|")
                W(f"| ورود تک‌نقطه‌ای | {fmt(a.entry)} | {single_rr:.2f} |")
                W(f"| **ورود پلکانی** | **{fmt(eff_entry)}** | **{rr:.2f}** |")
                W("")
        W("**قانون ابطال پله‌ها:** اگر قیمت پیش از پرشدن پله‌های پایین‌تر، ابطال ساختاری را")
        W("با بسته روزانه نقض کرد، همه سفارش‌های باقی‌مانده لغو می‌شوند.")
    else:
        W("نردبان داده نشده. برای فعال‌کردن، سه سطح را بده:")
        W("`--ladder-near <مرز نزدیک ناحیه ارزش> --ladder-poc <نقطه کنترل> --ladder-far <مرز دور>`")
        W("")
        W("ورود پلکانی معمولاً نسبت را بدون هیچ پیش‌بینی‌ای بالا می‌برد،")
        W("چون میانگین وزنی ورود به‌طور طبیعی نزدیک سطح ابطال می‌نشیند.")
    W("")

    W("## ۷ — یادآوری")
    W("")
    W("- این خروجی **اندازه** را می‌دهد، نه **تز**. تز از تحلیل رادار می‌آید.")
    W("- هر تصمیم — چه ورود، چه رد — باید در دفترچه یا دفتر هزینه فرصت ثبت شود.")
    W("- بدون ثبت، کالیبراسیون ناممکن است و چارچوب قابل اصلاح نیست.")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=f"موتور اندازه مدرج رادار {VERSION}")
    ap.add_argument("--balance", type=float, required=True, help="کل موجودی دلاری")
    ap.add_argument("--regime", type=float, required=True, help="امتیاز رژیم، منفی۲ تا مثبت۲")
    ap.add_argument("--score", type=float, required=True,
                    help="امتیاز نهایی کوین. لانگ: منفی۲..مثبت۲ | شورت: ۰..۲ از موتور شورت مستقل")
    ap.add_argument("--rr", type=float, default=0.0, help="نسبت ریسک به ریوارد؛ اگر target داده شود بازمحاسبه می‌شود")
    ap.add_argument("--coverage", type=float, default=100.0, help="پوشش داده درصد")
    ap.add_argument("--flow", type=int, default=4, help="تعداد اعداد موجود بلوک جریان، ۰ تا ۴")
    ap.add_argument("--entry", type=float, required=True, help="قیمت ورود تک‌نقطه‌ای")
    ap.add_argument("--stop", type=float, required=True, help="حد ضرر")
    ap.add_argument("--target", type=float, default=None, help="هدف اول")
    ap.add_argument("--invalidation", type=float, default=None, help="سطح ابطال ساختاری")
    ap.add_argument("--liq", type=float, default=None, help="قیمت لیکوئید تقریبی")
    ap.add_argument("--win-prob", type=float, default=None, help="احتمال برد، ۰ تا ۱")
    ap.add_argument("--side", choices=["long", "short"], default="long")
    ap.add_argument("--open-risk", type=float, default=0.0, help="ریسک باز فعلی درصد حساب")
    ap.add_argument("--margin", type=float, default=None, help="مارجین تخصیصی برای محاسبه اهرم")
    ap.add_argument("--structural", action="store_true", help="ورود روی سطح ساختاری روزانه یا بالاتر")
    ap.add_argument("--structureless", action="store_true", help="ساختار بی‌ساختار است")
    ap.add_argument("--scattered", action="store_true", help="نقاط کنترل سه لنگر پراکنده‌اند")
    ap.add_argument("--illiquid", action="store_true", help="نقدشوندگی ناکافی یا آزادسازی توکن بزرگ")
    ap.add_argument("--ladder-near", type=float, default=None)
    ap.add_argument("--ladder-poc", type=float, default=None)
    ap.add_argument("--ladder-far", type=float, default=None)
    ap.add_argument("--fee", type=float, default=0.10, help="کارمزد هر طرف درصد")
    ap.add_argument("--slip", type=float, default=0.10, help="لغزش درصد")
    ap.add_argument("--out", default=None, help="ذخیره خروجی در فایل")
    a = ap.parse_args()

    txt = compute(a)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"ذخیره شد در {a.out}")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
