#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_regime.py — امتیاز رژیم بازار، رادار ۷
============================================

کار باز ک۳ از ۲۲ اوت ۲۰۲۶. تا نشست ۲ گزارش سبد رژیم را از یک عدد ثابت
می‌گرفت (رویداد ۲۷ در STATE.md). این اسکریپت آن را از داده می‌سازد.

سه ستون، هر ورودی امتیازی میان ‎-2 و ‎+2:

    نقدینگی جهانی ۴۰٪   قیمت پول، شیب منحنی، روند نقدینگی خالص، دلار
    چرخه بیت‌کوین ۳۵٪   فاصله از میانگین پنجاه‌هفته، تسلط بدون استیبل،
                         اتر به بیت‌کوین
    اشتهای ریسک ۲۵٪     رشد عرضه استیبل، ترس و طمع، تسلط تتر

**نگاشت ورودی به امتیاز فرضیه است، نه اندازه‌گیری.** آستانه‌ها و سازوکار
هر ورودی در references/macro-liquidity.md نوشته شده‌اند.

قانون سوگیری صفر:
    خام   = Σ وزن×امتیاز ورودی‌های موجود ÷ Σ همه وزن‌ها
    نرمال = همان صورت ÷ Σ وزن ورودی‌های موجود
    نهایی = کمینه خام و نرمال — همیشه محافظه‌کارانه‌تر
چون خام = نرمال × پوشش، برای نرمال مثبت خام کوچک‌تر است و برای نرمال
منفی خود نرمال. پس کمینه همیشه باند پایین‌تر یا برابر را می‌دهد.

ورودی بدون منبع، یا کهنه‌تر از مهلت آهنگ انتشارش، غایب است — نه صفر.

خروجی:
    regime.json              قرارداد با radar_book.py: score و generated_at
    regime_history.json      تسلط‌ها برای روند ۳۰ روزه، و امتیازها برای
                             سنجش اعتبار بعدی خود رژیم
    reports/regime-DATE.md   برای خواندن انسان

    python radar_regime.py
    python radar_regime.py --stdout          # فقط چاپ، هیچ فایلی نمی‌نویسد
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from radar_budget import regime_band
# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

VERSION = "1.0"
UTC = timezone.utc
REFERENCE = "references/macro-liquidity.md"


class RegimeError(Exception):
    """خطای صریح ساخت رژیم — هرگز بی‌صدا بلعیده نمی‌شود."""


# ═══════════════════════ ستون‌ها، ورودی‌ها، وزن ═══════════════════════

COLUMNS = {
    "liquidity": ("نقدینگی جهانی", 0.40),
    "cycle": ("چرخه بیت‌کوین", 0.35),
    "appetite": ("اشتهای ریسک", 0.25),
}

# کلید ← (ستون، برچسب). وزن ستون میان ورودی‌هایش مساوی تقسیم می‌شود.
# «قیمت پول» ترکیب مسیر نرخ و بازده واقعی است: هر دو از سخت‌گیری فدرال
# می‌آیند و جدا شمردنشان یک خبر را دو بار حساب می‌کرد.
# تسلط بیت‌کوین با استیبل عمداً نیست: ترکیبی از تسلط بدون استیبل و سهم
# استیبل است و هم‌خطی سه‌تایی می‌ساخت.
INPUTS = {
    "money_price": ("liquidity", "قیمت پول"),
    "curve": ("liquidity", "شیب منحنی ۳۰ منهای ۲"),
    "net_liq": ("liquidity", "روند ۳۰ روزه نقدینگی خالص"),
    "dollar": ("liquidity", "روند ۳۰ روزه شاخص دلار"),
    "ma50w": ("cycle", "فاصله از میانگین ساده پنجاه‌هفته"),
    "dom_ex": ("cycle", "تغییر ۳۰ روزه تسلط بدون استیبل"),
    "ethbtc": ("cycle", "تغییر ۳۰ روزه اتر به بیت‌کوین"),
    "stable": ("appetite", "رشد ۳۰ روزه عرضه استیبل"),
    "fng": ("appetite", "ترس و طمع"),
    "usdt_dom": ("appetite", "تغییر ۳۰ روزه تسلط تتر"),
}


def weights() -> dict[str, float]:
    n = {c: sum(1 for col, _ in INPUTS.values() if col == c) for c in COLUMNS}
    return {k: COLUMNS[c][1] / n[c] for k, (c, _) in INPUTS.items()}


# ═══════════════════════ نگاشت — فرضیه، نه اندازه‌گیری ═══════════════════════

@dataclass(frozen=True)
class Mapping:
    """s = برش(جهت × (x − خنثی) ÷ k، کف، سقف). k مقداری است که یک واحد می‌سازد."""
    neutral: float
    k: float
    sign: int
    lo: float = -2.0
    hi: float = 2.0
    unit: str = ""
    why: str = ""

    def __call__(self, x: float) -> float:
        return max(self.lo, min(self.hi, self.sign * (x - self.neutral) / self.k))


MAPPINGS = {
    "rate_path": Mapping(0.0, 0.5, -1, unit="واحد درصد",
                         why="افزایش قیمت‌شده فراتر از محدوده هدف: تأمین مالی گران‌تر"),
    # k = 1.0، نه 0.5: با 0.5 هر بازده واقعی بالای ۲٪ در ‎-2 اشباع می‌شد و
    # ورودی کور بود — گشایش واقعی از 2.78 به 2.2 هیچ اثری نمی‌گذاشت
    "real_10y": Mapping(1.0, 1.0, -1, unit="٪",
                        why="هزینه فرصت نگه‌داشتن دارایی بی‌بازده"),
    "curve": Mapping(0.0, 0.5, +1, lo=-1.0, hi=0.0, unit="واحد درصد",
                     why="فقط وارونگی جریمه می‌شود؛ شیب مثبت نشانه روشنی ندارد"),
    "net_liq": Mapping(0.0, 1.0, +1, unit="٪",
                       why="دلار در دسترس بازار؛ انبساط باد موافق"),
    "dollar": Mapping(0.0, 1.0, -1, unit="٪",
                      why="دلار قوی یعنی نقدینگی دلاری جهانی تنگ‌تر"),
    "ma50w": Mapping(0.0, 10.0, +1, unit="٪",
                     why="بالای میانگین پنجاه‌هفته فاز صعودی چرخه"),
    "dom_ex": Mapping(0.0, 1.0, -1, unit="واحد درصد",
                      why="تمرکز سرمایه در بیت‌کوین؛ ریسک بیشتر برای سبد آلت‌محور"),
    "ethbtc": Mapping(0.0, 5.0, +1, unit="٪",
                      why="اشتهای ریسک از بیت‌کوین فراتر می‌رود"),
    "stable": Mapping(0.0, 1.0, +1, unit="٪",
                      why="استیبل تازه یعنی قدرت خرید تازه"),
    "fng": Mapping(50.0, 25.0, +1, lo=-1.0, hi=1.0,
                   why="اشتهای ریسک؛ دو سر طیف خلاف‌جهت‌اند، پس بریده در ±۱"),
    "usdt_dom": Mapping(0.0, 0.5, -1, unit="واحد درصد",
                        why="پول پارک‌شده در حاشیه امن"),
}


def score_input(key: str, x: float) -> float:
    return MAPPINGS[key](x)


def money_price(rate_s: float | None, real_s: float | None) -> float | None:
    """
    ترکیب مسیر نرخ و بازده واقعی. قانون سوگیری صفر در سطح خود ترکیب:
    کمینه «جمع موجود ÷ ۲» و «میانگین موجود». پس غیبت جزء جریمه‌کننده
    امتیاز را بالا نمی‌برد.
    """
    avail = [s for s in (rate_s, real_s) if s is not None]
    if not avail:
        return None
    return min(sum(avail) / 2, sum(avail) / len(avail))


# ═══════════════════════ تازگی بر اساس آهنگ انتشار ═══════════════════════

# مهلت هر منبع به روز. سری روزانه ۷ روز؛ سری با انتشار هفتگی ۱۴ روز —
# یعنی یک انتشار جاافتاده. با یک عدد برای همه، پوشش هر هفته فقط به خاطر
# تقویم انتشار بالا و پایین می‌رفت؛ آن نویز است، نه داده.
FRESH_DAYS = {
    "DGS2": 7, "DGS10": 7, "DGS30": 7, "T10YIE": 7,
    "DFEDTARU": 7, "DFEDTARL": 7, "RRPONTSYD": 7,
    "WALCL": 14, "WTREGEN": 14, "DTWEXBGS": 14,
    "CoinGecko": 7, "DefiLlama": 7, "Alternative.me": 7,
    "candle_1D": 7, "candle_1W": 14,
}
FUTURE_SKEW = timedelta(days=1)
LOW_COVERAGE = 0.50


def is_low_coverage(coverage: float) -> bool:
    """«زیر ۵۰٪» پوشش کم است؛ خود ۵۰٪ نه."""
    return coverage < LOW_COVERAGE


def _fresh(ts: datetime | None, limit: int, now: datetime) -> str:
    """رشته خالی یعنی تازه؛ در غیر این صورت دلیل غیبت."""
    if ts is None:
        return "عمر نامعلوم — مهر زمان ندارد"
    age = now - ts
    if age < -FUTURE_SKEW:
        return "مهر زمان در آینده است"
    if age > timedelta(days=limit):
        return f"کهنه: {age.total_seconds() / 86400:.1f} روز، مهلت {fa(limit)} روز"
    return ""


# ═══════════════════════ ورودی ═══════════════════════

@dataclass
class Input:
    key: str
    column: str
    label: str
    weight: float
    value: float | None = None
    score: float | None = None
    ts: datetime | None = None
    max_age_days: int | None = None
    reason: str = ""
    detail: str = ""
    obs: dict = field(default_factory=dict)   # مشاهده خام برای تاریخچه


def _blank(key: str) -> Input:
    col, label = INPUTS[key]
    return Input(key=key, column=col, label=label, weight=weights()[key])


def _fred_value(fred: dict, dkey: str, field_: str, now: datetime
                ) -> tuple[float | None, datetime | None, int | None, str]:
    """مقدار یک سنجه مشتق FRED با سنجش تازگی **هر سری منبع** جدا."""
    d = (fred.get("derived") or {}).get(dkey)
    if d is None:
        return None, None, None, f"سنجه {dkey} ساخته نشد — داده FRED نیامد"
    raw = fred.get("raw") or {}
    limits = []
    for sid in d.get("sources", []):
        r = raw.get(sid)
        if r is None:
            return None, d.get("ts"), None, f"سری {sid} نیامد"
        limit = FRESH_DAYS.get(sid, 7)
        limits.append(limit)
        why = _fresh(r.get("ts"), limit, now)
        if why:
            return None, r.get("ts"), limit, f"{sid} {why}"
    v = d.get(field_)
    if v is None or not math.isfinite(v):
        return None, d.get("ts"), min(limits or [7]), d.get("read") or "مقدار نامعتبر"
    return float(v), d.get("ts"), min(limits or [7]), ""


def _field_value(f, limit: int, now: datetime
                 ) -> tuple[float | None, datetime | None, str]:
    if f is None or f.value is None:
        return None, None, "منبع پاسخ نداد"
    why = _fresh(f.ts, limit, now)
    if why:
        return None, f.ts, why
    return float(f.value), f.ts, ""


def _history_change(history: dict, name: str, current: float, now: datetime
                    ) -> tuple[float | None, str]:
    """
    تغییر ۳۰ روزه از regime_history.json: نزدیک‌ترین روز به ۳۰ روز قبل،
    در بازه ۲۷ تا ۳۳ روز. کوین‌گکو رایگان تاریخچه تسلط نمی‌دهد.
    """
    today = now.date()
    best = None
    for day, rec in (history.get("days") or {}).items():
        # کلیدها در load_history اعتبارسنجی شده‌اند — خراب یعنی خطای صریح
        back = (today - datetime.strptime(day, "%Y-%m-%d").date()).days
        v = rec.get(name)
        if 27 <= back <= 33 and isinstance(v, (int, float)):
            if best is None or abs(back - 30) < abs(best[0] - 30):
                best = (back, float(v))
    if best is None:
        n = len(history.get("days") or {})
        return None, f"تاریخچه ۳۰ روزه کافی نیست ({n} روز ثبت شده)"
    return current - best[1], ""


def _closed(df):
    import radar_fetch3 as R
    return R._closed(df)


def _close_time(ts, bar: str) -> datetime:
    import radar_fetch3 as R
    return (ts + timedelta(seconds=R.BAR_SECONDS[bar])).to_pydatetime()


def measure(src: dict, history: dict, now: datetime) -> dict[str, Input]:
    """
    هر ورودی را از داده منابع می‌سازد. منبع‌ها از radar_fetch3.py می‌آیند
    (gather)؛ اینجا فقط اندازه، تازگی و امتیاز است — بدون شبکه.
    """
    fred, macro = src.get("fred") or {}, src.get("macro") or {}
    inp = {k: _blank(k) for k in INPUTS}

    # ── قیمت پول: مسیر نرخ و بازده واقعی
    mp = inp["money_price"]
    parts, notes = {}, []
    for dkey, name in (("rate_path", "مسیر نرخ"), ("real_10y", "بازده واقعی")):
        v, ts, limit, why = _fred_value(fred, dkey, "value", now)
        if why:
            notes.append(f"{name} غایب: {why}")
            parts[dkey] = None
        else:
            s = score_input(dkey, v)
            parts[dkey] = s
            notes.append(f"{name} {v:.3f} ← امتیاز {s:+.2f}")
            mp.ts = ts if mp.ts is None else min(mp.ts, ts)
            mp.max_age_days = limit
    mp.score = money_price(parts["rate_path"], parts["real_10y"])
    mp.detail = "؛ ".join(notes)
    mp.obs = {"components": parts}
    if mp.score is None:
        mp.reason = "هر دو جزء غایب — " + mp.detail

    # ── سنجه‌های تک‌مشتق FRED
    for key, dkey, fld in (("curve", "curve_30_2", "value"),
                           ("net_liq", "net_liq_trend", "pct"),
                           ("dollar", "dollar_30d", "value")):
        v, ts, limit, why = _fred_value(fred, dkey, fld, now)
        i = inp[key]
        i.value, i.ts, i.max_age_days, i.reason = v, ts, limit, why
        if not why:
            i.score = score_input(key, v)

    # ── چرخه: میانگین ساده پنجاه‌هفته — قیمت زنده، میانگین از هفته‌های بسته
    i = inp["ma50w"]
    i.max_age_days = FRESH_DAYS["candle_1W"]
    btc = src.get("btc") or {}
    wk, dl = btc.get("1W"), btc.get("1D")
    if wk is None or dl is None or len(wk) == 0 or len(dl) == 0:
        i.reason = "کندل هفتگی یا روزانه بیت‌کوین نیامد"
    else:
        import radar_fetch3 as R
        wc = _closed(wk)
        live = R.last_close(dl)
        if len(wc) < 50:
            i.reason = f"نابالغ: {len(wc)} هفته بسته، ۵۰ لازم"
        elif live is None:
            i.reason = "قیمت زنده بیت‌کوین پوچ است"
        else:
            sma = float(wc["close"].tail(50).mean())
            i.ts = min(_close_time(wc["ts"].iloc[-1], "1W"), now)
            why = _fresh(i.ts, i.max_age_days, now)
            if why:
                i.reason = why
            else:
                i.value = 100 * (live / sma - 1)
                i.score = score_input("ma50w", i.value)
                i.detail = f"قیمت {live:,.2f}، میانگین {sma:,.2f}"

    # ── چرخه: اتر به بیت‌کوین، تغییر ۳۰ روزه روی کندل روزانه بسته
    i = inp["ethbtc"]
    i.max_age_days = FRESH_DAYS["candle_1D"]
    pair = src.get("ethbtc")
    if pair is None or len(pair) == 0:
        i.reason = "جفت اتر به بیت‌کوین نیامد"
    else:
        pc = _closed(pair)
        t_now = pc["ts"].iloc[-1]
        then = pc.loc[pc["ts"] <= t_now - timedelta(days=30), "close"]
        i.ts = _close_time(t_now, "1D")
        why = _fresh(i.ts, i.max_age_days, now)
        if len(then) == 0:
            i.reason = "کمتر از ۳۰ روز داده جفت"
        elif why:
            i.reason = why
        else:
            c_now, c_then = float(pc["close"].iloc[-1]), float(then.iloc[-1])
            i.value = 100 * (c_now / c_then - 1)
            i.score = score_input("ethbtc", i.value)

    # ── تسلط‌ها: مقدار امروز از کوین‌گکو، روند ۳۰ روزه از تاریخچه
    for key, name in (("dom_ex", "btc_dom_ex_stable"),
                      ("usdt_dom", "usdt_dominance")):
        i = inp[key]
        i.max_age_days = FRESH_DAYS["CoinGecko"]
        cur, ts, why = _field_value(macro.get(name), i.max_age_days, now)
        i.ts = ts
        if why:
            i.reason = why
            continue
        i.obs[name] = cur
        chg, why = _history_change(history, name, cur, now)
        if why:
            i.reason = why
        else:
            i.value = chg
            i.score = score_input(key, chg)
            i.detail = f"امروز {cur:.3f}"
    # تسلط با استیبل امتیاز نمی‌گیرد، ولی برای تاریخچه ثبت می‌شود
    bd, _, why = _field_value(macro.get("btc_dominance"), FRESH_DAYS["CoinGecko"], now)
    if not why:
        inp["dom_ex"].obs["btc_dominance"] = bd

    # ── اشتها: رشد استیبل و ترس و طمع
    for key, name, limit in (("stable", "stable_change_30d", FRESH_DAYS["DefiLlama"]),
                             ("fng", "fear_greed", FRESH_DAYS["Alternative.me"])):
        i = inp[key]
        i.max_age_days = limit
        v, ts, why = _field_value(macro.get(name), limit, now)
        i.value, i.ts, i.reason = v, ts, why
        if not why:
            i.score = score_input(key, v)
    return inp


# ═══════════════════════ تجمیع ═══════════════════════

def aggregate(inp: dict[str, Input]) -> dict:
    """قانون سوگیری صفر: خام، نرمال، و کمینه آن دو به‌عنوان امتیاز نهایی."""
    total_w = sum(i.weight for i in inp.values())
    present = [i for i in inp.values() if i.score is not None]
    num = sum(i.weight * i.score for i in present)
    have_w = sum(i.weight for i in present)
    if have_w <= 0:
        raise RegimeError("هیچ ورودی معتبری نیامد — پوشش صفر")
    raw, norm = num / total_w, num / have_w
    score = min(raw, norm)
    coverage = have_w / total_w

    cols = {}
    for c, (label, w) in COLUMNS.items():
        mine = [i for i in inp.values() if i.column == c]
        ok = [i for i in mine if i.score is not None]
        cw = sum(i.weight for i in ok)
        cols[c] = {"label": label, "weight": w,
                   "score": (sum(i.weight * i.score for i in ok) / cw) if cw else None,
                   "coverage": cw / sum(i.weight for i in mine)}
    return {"raw": raw, "norm": norm, "score": score, "coverage": coverage,
            "low_coverage": is_low_coverage(coverage),
            "band": regime_band(score), "columns": cols,
            "missing": [{"key": i.key, "label": i.label, "reason": i.reason}
                        for i in inp.values() if i.score is None]}


# ═══════════════════════ خروجی ═══════════════════════

def _iso(ts: datetime | None) -> str | None:
    return ts.astimezone(UTC).isoformat() if ts else None


def build_doc(res: dict, inp: dict[str, Input], now: datetime) -> dict:
    """
    سند regime.json. قرارداد با radar_book.py دو میدان اجباری دارد —
    score (امتیاز نهایی محافظه‌کارانه) و generated_at (با منطقه زمانی) —
    و بقیه میدان‌ها اضافه‌اند. امتیاز با دقت کامل ذخیره می‌شود تا باند
    سبد روی مرز همان باند رژیم باشد.
    """
    return {
        "score": res["score"],
        "generated_at": _iso(now),
        "raw": res["raw"], "norm": res["norm"],
        "coverage": res["coverage"], "low_coverage": res["low_coverage"],
        "band": res["band"], "columns": res["columns"],
        "inputs": [{"key": i.key, "column": i.column, "label": i.label,
                    "weight": i.weight, "value": i.value, "score": i.score,
                    "ts": _iso(i.ts), "max_age_days": i.max_age_days,
                    "reason": i.reason, "detail": i.detail}
                   for i in inp.values()],
        "missing": res["missing"],
        "freshness_days": dict(FRESH_DAYS),
        "version": VERSION,
        "note": f"نگاشت‌ها فرضیه‌اند، نه اندازه‌گیری — {REFERENCE}",
    }


def load_history(path) -> dict:
    """تاریخچه غایب یعنی تهی. تاریخچه خراب خطای صریح است — بازنویسی نمی‌شود."""
    if not os.path.exists(path):
        return {"version": 1, "days": {}}
    try:
        with open(path, encoding="utf-8") as f:
            h = json.load(f)
    except (OSError, ValueError) as exc:
        raise RegimeError(f"تاریخچه {path} خوانا نیست: {type(exc).__name__}") from exc
    if not isinstance(h, dict) or not isinstance(h.get("days"), dict):
        raise RegimeError(f"تاریخچه {path} ساختار درست ندارد")
    for day, rec in h["days"].items():
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise RegimeError(f"تاریخچه {path}: کلید روز نامعتبر {day!r}") from exc
        if not isinstance(rec, dict):
            raise RegimeError(f"تاریخچه {path}: رکورد روز {day} شیء نیست")
    return h


def update_history(history: dict, res: dict, inp: dict[str, Input],
                   now: datetime) -> dict:
    """
    روز امروز را می‌افزاید یا بازنویسی می‌کند؛ روزهای دیگر دست نمی‌خورند.
    امتیازها هم ثبت می‌شوند تا بعداً خود رژیم با radar_validate سنجیده شود.
    """
    h = {"version": history.get("version", 1), "days": dict(history.get("days") or {})}
    rec = {"generated_at": _iso(now), "raw": res["raw"], "norm": res["norm"],
           "score": res["score"], "band": res["band"]["name"],
           "coverage": res["coverage"],
           "inputs": {k: i.score for k, i in inp.items()}}
    for i in inp.values():
        for name, v in i.obs.items():
            if name != "components":
                rec[name] = v
    h["days"][now.strftime("%Y-%m-%d")] = rec
    return h


def write_json(path, doc: dict) -> None:
    """نوشتن اتمی: فایل موقت در همان پوشه، سپس جایگزینی."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _num(v, d: int = 2) -> str:
    return "—" if v is None else f"{v:+.{d}f}"


def render_md(doc: dict) -> str:
    stamp = datetime.fromisoformat(doc["generated_at"]).strftime("%Y-%m-%d %H:%M UTC")
    b = doc["band"]
    L = [f"# رژیم بازار — رادار ۷، نسخه {fa(VERSION)}", "",
         f"تولید: **{stamp}**", "",
         "> **فرضیه، نه اندازه‌گیری.** نگاشت ورودی به امتیاز حدسی است با "
         f"دلیل سازوکاری و هنوز با داده سنجیده نشده. آستانه‌ها: `{REFERENCE}`.", ""]
    if doc["low_coverage"]:
        L += [f"> ⚠️ **پوشش کم:** فقط {100 * doc['coverage']:.0f}٪ وزن ورودی‌ها موجود است.", ""]
    L += ["| سنجه | مقدار |", "|---|---|",
          f"| امتیاز خام | {_num(doc['raw'], 3)} |",
          f"| امتیاز نرمال | {_num(doc['norm'], 3)} |",
          f"| **امتیاز نهایی** — کمینه دو | **{_num(doc['score'], 3)}** |",
          f"| **باند** | **{b['name']}** |",
          f"| سقف ریسک باز | {b['cap']}٪ |",
          f"| ضریب اندازه | {b['mult']:.2f} |",
          f"| حداکثر پوزیشن هم‌جهت | {b['maxpos']} |",
          f"| هدف ذخیره استیبل | {b['stable']}٪ |",
          f"| پوشش | {100 * doc['coverage']:.1f}٪ |", "",
          "## ستون‌ها", "", "| ستون | وزن | امتیاز | پوشش ستون |", "|---|---|---|---|"]
    for c in doc["columns"].values():
        L.append(f"| {c['label']} | {100 * c['weight']:.0f}٪ | {_num(c['score'])} | "
                 f"{100 * c['coverage']:.0f}٪ |")
    L += ["", "## ورودی‌ها", "",
          "| ستون | ورودی | مقدار | تاریخ مشاهده | مهلت (روز) | امتیاز | وزن |",
          "|---|---|---|---|---|---|---|"]
    for i in doc["inputs"]:
        col = doc["columns"][i["column"]]["label"]
        day = i["ts"][:10] if i["ts"] else "—"
        L.append(f"| {col} | {i['label']} | {_num(i['value'], 3)} | {day} | "
                 f"{i['max_age_days'] or '—'} | {_num(i['score'])} | "
                 f"{100 * i['weight']:.2f}٪ |")
    if doc["missing"]:
        L += ["", "## ورودی‌های غایب", "",
              "غایب یعنی از مخرج نرمال کم شد، نه صفر.", ""]
        L += [f"- **{m['label']}** — {m['reason']}" for m in doc["missing"]]
    details = [i for i in doc["inputs"] if i["detail"]]
    if details:
        L += ["", "## جزئیات", ""]
        L += [f"- **{i['label']}:** {i['detail']}" for i in details]
    L += ["", "---", "",
          "خام = Σ وزن×امتیاز موجود ÷ Σ همه وزن‌ها. نرمال = همان صورت ÷ Σ وزن موجود. "
          "نهایی = کمینه دو. روی مرز دقیق، باند پایین‌تر.", ""]
    return "\n".join(L)


# ═══════════════════════ واکشی — فقط از توابع radar_fetch3.py ═══════════════════════

def gather(order: list[str]) -> dict:
    """داده را از توابع موجود می‌گیرد، کپی نمی‌کند. هیچ عددی از جست‌وجوی وب."""
    import radar_fetch3 as R
    fred = R.fetch_fred(R.http_text)
    macro: dict = {}
    R.fetch_macro(macro)
    live, _dead = R.probe_venues(order)
    order = live or order
    btc, _, _ = R.candles_first_ok("BTC", order, R.DAILY_WANT, [])
    _, _, pair = R.candles_first_ok("ETH", order, R.DAILY_WANT, [])
    return {"fred": fred, "macro": macro, "btc": btc, "ethbtc": pair}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="امتیاز رژیم بازار — رادار ۷")
    ap.add_argument("--json", default="regime.json")
    ap.add_argument("--history", default="regime_history.json")
    ap.add_argument("--report", default=None,
                    help="پیش‌فرض reports/regime-YYYY-MM-DD.md")
    ap.add_argument("--venues", default="okx,gate")
    ap.add_argument("--stdout", action="store_true",
                    help="فقط چاپ گزارش — هیچ فایلی نوشته نمی‌شود")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    order = [v.strip().lower() for v in a.venues.split(",") if v.strip()]

    try:
        history = load_history(a.history)
        inp = measure(gather(order), history, now)
        res = aggregate(inp)
    except RegimeError as exc:
        print(f"⛔ ساخت رژیم خطا داد: {exc}", file=sys.stderr)
        return 2

    doc = build_doc(res, inp, now)
    md = render_md(doc)
    if a.stdout:
        print(md)
        return 0
    report = a.report or os.path.join("reports", f"regime-{now:%Y-%m-%d}.md")
    os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
    with open(report, "w", encoding="utf-8") as f:
        f.write(md)
    write_json(a.history, update_history(history, res, inp, now))
    write_json(a.json, doc)
    print(f"رژیم: {res['band']['name']} — نهایی {res['score']:+.3f}، "
          f"پوشش {100 * res['coverage']:.0f}٪ → {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
