#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_pump.py — اسکنر پامپ، نشست ۹ رادار ۷
==========================================

چه می‌کند:
    ۱) جهان بازار: جفت‌های نقدی USDT اوکی‌اکس و گیت با حجم ۲۴ ساعته یک صرافی
       دست‌کم ۳ میلیون دلار. حجم دو صرافی جمع نمی‌شود.
    ۲) دروازه جریان: جهش حجم ۱ یا ۴ ساعته، رشد بهره باز به واحد کوین، یا دو برابر
       شدن نسبت حجم قرارداد دائمی به نقدی. یکی بس است.
    ۳) برای گذشته‌ها از دروازه: سطح ساختاری radar_levels، ستاپ‌های کتابخانه،
       وتوی آزادسازی radar_events و بودن در ال‌بانک.
    ۴) رتبه بی امتیاز: ماشه، سپس پیش‌شرط، سپس فقط جریان؛ داخل هر گروه فاصله از سطح.

    python radar_pump.py
    python radar_pump.py --out reports/PUMP.md --json pump.json --ledger pump_ledger.json

خروجی سه فایل با مسیر ثابت، نه پوشه — ک۱۴: گزارش، pump.json، و دفتر
pump_ledger.json. دفتر همه گذشته‌ها از دروازه را ثبت می‌کند، نه فقط فهرست نهایی —
تا آزمون نشست ۱۳ سوگیری انتخاب نداشته باشد.

⚠️ این فهرست مجوز ورود نیست. اسکنر معامله نمی‌کند و چیزی وارد دفتر موقعیت
   نمی‌شود. هر نامزد مال دفتر معامله است، زیر سقف ریسک رژیم. تا نشست ۱۳ همه
   «آزمون‌نشده»اند — تصمیم کاربر، ۶ اکتبر ۲۰۲۶.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import radar_fetch3 as R
import radar_levels as L
from radar_rotate import GOLD, LEV_RE, STABLES, rs_pair
# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
VERSION = "1.0"
HOUR_MS = 3_600_000

# ── آستانه‌ها — همه آزمون‌نشده، هر کدام ردیف دفتر فرض‌ها
MIN_VOL_USD = 3_000_000          # کف حجم ۲۴ ساعته یک صرافی — تصمیم کاربر، نشست ۹
Z_MIN = 2.0                      # جهش حجم، عدد استانداردشده
OI24_MIN = 0.15                  # رشد بهره باز ۲۴ ساعته به واحد کوین
RATIO_MULT = 2.0                 # نسبت قرارداد به نقدی در برابر شش روز پیش از آن
NEW_LISTING_DAYS = 30            # تازه‌فهرست: عمر قدیمی‌ترین فهرست
FRESH_VENUE_DAYS = 14            # فهرست‌شدن تازه در یک صرافی
LATE_ATR = 3.0                   # «دیر است» — همان مرز «کشیده» در radar_levels
CROWD_FUNDING_ABS = 0.001        # ازدحام لانگ یا شورت: قدر مطلق فاندینگ ۸ ساعته — تصمیم کاربر
LEV_FUNDING_8H = 0.0003          # پامپ اهرمی — همان مرز آزمون پامپ radar_rotate
LEV_OI24 = 0.15
LEV_PRICE_MAX = 0.02             # «قیمت رشد نکرده»: تغییر ۲۴ ساعته کمتر از این
ABNORMAL_K = 5.0                 # ر۵۶ — شمع ۴ ساعته غیرعادی
POST_PUMP_RS7 = 50.0             # پس از پامپ: قدرت نسبی ۷ روزه به بیت‌کوین، واحد درصد — تصمیم کاربر
OI_USD_MIN = 2_000_000           # نشانه بهره باز فقط با بهره باز دلاری دست‌کم این — تصمیم کاربر
SQ_DRIFT = 0.5                   # فشردگی افقی: تغییر خالص بسته پنجره کمتر از این کسر ارتفاع
SQ_LIVE_ATR = 0.5                # فشردگی: قیمت زنده درون محدوده یا تا این کسر دامنه واقعی بیرونش

# ── کارت معامله — کتابخانه ستاپ و radar_size
BASE_RISK_PCT = 2.0              # ریسک پایه — همان radar_size
MAX_TRADE_RISK_PCT = 2.0         # سقف ریسک هر معامله — همان radar_size
FEE_SIDE, SLIP = 0.001, 0.001    # کارمزد هر طرف و لغزش — همان پیش‌فرض radar_size
RT_COST = 2 * FEE_SIDE + SLIP    # هزینه رفت و برگشت، کسری از قیمت ورود
MIN_RR = 2.5                     # کف نسبت — اصل دو کتابخانه
STOP_BUF_ATR = 0.25              # فاصله استاپ از سطح — همان buffer_atr در radar_levels
ON_LEVEL_ATR = 0.5               # «ورود روی سطح ساختاری»: تا این کسر دامنه واقعی
QUALITY = (("الف", 2.0, 4.0), ("ب", 1.5, 3.0), ("ج", 1.0, MIN_RR))   # جدول ۸.۲ کتابخانه
PULSE_MAX, PULSE_TTL_DAYS = 5, 3  # نامزد نبض: سقف و انقضا؛ پیدا شدن دوباره تمدید — تصمیم کاربر
DAILY_TARGET = (3, 8)            # نامزد لانگ و شورت در روز — پیشنهاد بازبین، تصمیم کاربر

# ── پنجره‌ها
Z1H_BASE, Z1H_MIN, Z1H_RECENT = 168, 120, 6
Z4H_BASE, Z4H_MIN = 84, 60
RATIO_RECENT, RATIO_BASE = 24, 144
ABN_RECENT, ABN_BASE = 42, 84
SQ_WIN, SQ_PRIOR = 10, 20
BREAK_LOOK, BASE_MIN = 10, 15
CANDLES = 300
VETO_TOP = 15
LEDGER_POINTS = {"h24": 24, "d7": 24 * 7}
DUE_MARGIN = timedelta(minutes=5)
BAR_S = {"1h": 3600, "4h": 14_400}

UNTESTED = "آزمون‌نشده"
NOT_IN_LBANK = "در LBank نیست"
VENUE_FA = {"okx": "اوکی‌اکس", "gate": "گیت"}
STATE_FA = {"trigger": "ماشه", "pre": "پیش‌شرط"}
SETUP_FA = {"الف‌۱": "شکست و بازآزمایی", "الف‌۲": "پولبک در روند", "الف‌۳": "فشردگی",
            "ج‌۱": "شکست ناکام", "ج‌۲": "سقف پایین‌تر", "ر۵۸": "شکست کف پس از چند برخورد"}
GROUP = {"trigger": 1, "pre": 2}
GROUP_FLOW = 3
SECTIONS = ("long", "short", "afterpump", "late", "nolevel", "veto")

# پیچیده‌شده و سپرده‌ای — فهرست صریح، نه الگو: WIF و WLD و STX نماد واقعی‌اند
WRAPPED = {"WBTC", "WETH", "WBETH", "STETH", "WSTETH", "CBBTC", "CBETH", "RETH", "METH",
           "BETH", "WEETH", "EZETH", "RSETH", "SWETH", "OSETH", "PUFETH", "SOLVBTC",
           "XSOLVBTC", "LBTC", "TBTC", "STBTC", "JITOSOL", "MSOL", "BNSOL", "BBSOL", "JUPSOL",
           "STSOL", "WSOL", "WBNB", "WAVAX", "WMATIC", "WPOL", "WTRX", "WFTM", "WHBAR"}

OKX = "https://www.okx.com"
GATE = "https://api.gateio.ws/api/v4"
LBANK = "https://api.lbkex.com"
# فاصله کمینه میان دو درخواست هر مقصد، ثانیه — زیر سقف سرعت هر صرافی
PACE = {"okx": 0.12, "okx_rubik": 0.45, "gate": 0.06, "lbank": 0.1}
# دامنه ورودی اسکی است — [A-Z0-9]، نه \w که حرف فارسی را هم می‌گیرد
SYMBOL_RE = re.compile(r"[A-Z0-9]{1,20}")


# ═══════════════ شبکه ═══════════════

def host_key(url: str) -> str:
    for k, mark in (("okx", "okx.com"), ("gate", "gateio"), ("lbank", "lbkex"),
                    ("defillama", "llama"), ("coingecko", "coingecko")):
        if mark in url:
            return k
    return "other"


class Net:
    """
    درخواست شمرده و فاصله‌دار. get تزریقی است و هم‌شکل requests.Session().get —
    آزمون بی‌شبکه. خود شیء هم get است، پس به radar_events و radar_history داده
    می‌شود و درخواست آن‌ها هم شمرده می‌شود.
    """

    def __init__(self, get, sleep=time.sleep, clock=time.monotonic):
        self._get, self._sleep, self._clock = get, sleep, clock
        self.count: dict[str, int] = {}
        self.errors: list[str] = []
        self._last: dict[str, float] = {}

    def __call__(self, url, params=None, **kw):
        k = host_key(url)
        gap = PACE.get("okx_rubik" if "/rubik/" in url else k, 0.0)
        wait = self._last.get(k, -1e9) + gap - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last[k] = self._clock()
        self.count[k] = self.count.get(k, 0) + 1
        kw.setdefault("timeout", 20)
        return self._get(url, params=params, **kw)

    def json(self, url, params=None, tries: int = 2):
        """پاسخ JSON یا None. خطا ثبت می‌شود، نه بلعیده."""
        why = ""
        for i in range(tries):
            try:
                r = self(url, params)
                st = getattr(r, "status_code", 200)
                if st == 200:
                    return r.json()
                why = f"کد {st}"
                if st not in (429, 500, 502, 503, 504):
                    break
            except Exception as exc:
                why = f"{type(exc).__name__}: {str(exc)[:120]}"
            if i + 1 < tries:
                self._sleep(1.0 * (i + 1))
        self.errors.append(f"{host_key(url)} {url.split('?')[0].rsplit('/', 1)[-1]}: {why}")
        return None

    def http(self, url, params=None, label="", **kw):
        """هم‌شکل R.http_get، برای کلاس‌های صرافی radar_fetch3."""
        return self.json(url, params)


def okx_data(js):
    if isinstance(js, dict) and str(js.get("code")) == "0" and isinstance(js.get("data"), list):
        return js["data"]
    return None


def as_list(js):
    return js if isinstance(js, list) else None


def _f(x) -> float | None:
    """عدد متناهی یا None. پوچ از `is None` رد می‌شود و سنجه را «موجود» جا می‌زند."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ═══════════════ جهان بازار ═══════════════

def exclude_reason(base: str) -> str | None:
    if not SYMBOL_RE.fullmatch(base or ""):
        return "نماد غیر اسکی"
    if base in STABLES:
        return "استیبل"
    if LEV_RE.search(base):
        return "اهرمی"
    if base in WRAPPED:
        return "پیچیده‌شده"
    if base in GOLD:
        return "طلا"
    return None


def _interval_h(iv: float | None) -> float:
    return iv if iv is not None and 0.5 <= iv <= 24 else 8.0


def okx_funding_8h(row: dict) -> float | None:
    """نرخ هر بازه به ۸ ساعت. بازه = فاصله دو تسویه پیاپی."""
    r = _f(row.get("fundingRate"))
    a, b = _f(row.get("fundingTime")), _f(row.get("nextFundingTime"))
    iv = _interval_h((b - a) / HOUR_MS if a and b and b > a else None)
    return None if r is None else r * 8 / iv


def gate_funding_8h(c: dict) -> float | None:
    r = _f(c.get("funding_rate"))
    iv = _interval_h((_f(c.get("funding_interval")) or 28_800) / 3600)
    return None if r is None else r * 8 / iv


def pair_age(ages: dict[str, float]) -> tuple[float | None, list[str]]:
    """عمر بازار = قدیمی‌ترین فهرست. فهرست‌شدن تازه در هر صرافی برچسب جدا دارد."""
    if not ages:
        return None, ["عمر نامعلوم"]
    age = max(ages.values())
    labels = ["تازه‌فهرست"] if age < NEW_LISTING_DAYS else []
    labels += [f"فهرست تازه در {VENUE_FA[v]}" for v, a in sorted(ages.items())
               if a < FRESH_VENUE_DAYS]
    return age, labels


def build_universe(m: dict, min_vol: float, now: datetime) -> tuple[dict, float | None, list[str]]:
    """
    جهان بازار از پاسخ‌های یک‌باره. کف روی حجم یک صرافی است، نه جمع دو صرافی؛
    صرافی داده اوکی‌اکس است اگر خودش از کف گذشت، وگرنه گیت.
    """
    warns: list[str] = []
    okx, gate = {}, {}
    for t in m.get("okx_spot") or []:
        i = t.get("instId", "")
        last, o24 = _f(t.get("last")), _f(t.get("open24h"))
        if i.endswith("-USDT") and last and last > 0:
            okx[i[:-5]] = {"price": last, "vol": _f(t.get("volCcy24h")) or 0.0,
                           "chg24": last / o24 - 1 if o24 else None}
    pairs = m.get("gate_pairs")
    info = {p.get("base"): p for p in pairs or [] if p.get("quote") == "USDT"}
    if pairs is None:
        warns.append("فهرست جفت‌های گیت نیامد — وضعیت معامله و عمر جفت گیت نامعلوم")
    for t in m.get("gate_spot") or []:
        p = t.get("currency_pair", "")
        last = _f(t.get("last"))
        if not p.endswith("_USDT") or not last or last <= 0:
            continue
        b = p[:-5]
        if pairs is not None and (info.get(b) or {}).get("trade_status") != "tradable":
            continue
        chg = _f(t.get("change_percentage"))
        gate[b] = {"price": last, "vol": _f(t.get("quote_volume")) or 0.0,
                   "chg24": chg / 100 if chg is not None else None}
    if not okx:
        warns.append("تیکر نقدی اوکی‌اکس نیامد — جهان بازار فقط از گیت")
    if not gate:
        warns.append("تیکر نقدی گیت نیامد — جهان بازار فقط از اوکی‌اکس")

    btc = (okx.get("BTC") or gate.get("BTC") or {}).get("price")
    listed = {i["instId"][:-5]: _f(i.get("listTime")) for i in m.get("okx_inst") or []
              if i.get("instId", "").endswith("-USDT")}
    okx_perp = {r["instId"][:-10]: okx_funding_8h(r) for r in m.get("okx_funding") or []
                if r.get("instId", "").endswith("-USDT-SWAP")}
    gate_perp = {c["name"][:-5]: c for c in m.get("gate_contracts") or []
                 if c.get("name", "").endswith("_USDT") and not c.get("in_delisting")}

    uni: dict[str, dict] = {}
    for b in sorted(set(okx) | set(gate)):
        if b == "BTC" or exclude_reason(b):
            continue
        vo, vg = okx.get(b, {}).get("vol", 0.0), gate.get(b, {}).get("vol", 0.0)
        if max(vo, vg) < min_vol:
            continue
        venue = "okx" if vo >= min_vol else "gate"
        src = okx[b] if venue == "okx" else gate[b]
        ages = {}
        lt = listed.get(b)
        if lt and lt > 0:
            ages["okx"] = (now.timestamp() * 1000 - lt) / (24 * HOUR_MS)
        bs = _f((info.get(b) or {}).get("buy_start"))
        if b in gate and bs and bs > 0:
            ages["gate"] = (now.timestamp() - bs) / 86_400
        age, labels = pair_age(ages)
        if (info.get(b) or {}).get("st_tag"):
            labels.append("برچسب ریسک گیت")
        # مشتقات از همان صرافی اگر قرارداد دارد؛ وگرنه از دیگری. سری کندل هرگز ترکیب
        # نمی‌شود: نسبت قرارداد به نقدی فقط وقتی هر دو پا در یک صرافی‌اند.
        has = {"okx": b in okx_perp, "gate": b in gate_perp}
        other = "gate" if venue == "okx" else "okx"
        deriv = venue if has[venue] else (other if has[other] else None)
        fund = (okx_perp.get(b) if deriv == "okx"
                else gate_funding_8h(gate_perp[b]) if deriv == "gate" else None)
        uni[b] = {"symbol": b, "venue": venue, "price": src["price"], "chg24": src["chg24"],
                  "vol24": src["vol"], "vol_okx": vo, "vol_gate": vg, "deriv_venue": deriv,
                  "perp_same_venue": has[venue], "funding_8h": fund,
                  "quanto": _f(gate_perp[b].get("quanto_multiplier")) if b in gate_perp else None,
                  "age_days": age, "ages": ages, "labels": labels}
    return uni, btc, warns


def lbank_pairs(js) -> set[str] | None:
    """جفت‌های نقدی USDT ال‌بانک. پاسخ خالی هم «نامعلوم» است، نه «هیچ جفتی»."""
    if not isinstance(js, dict) or not isinstance(js.get("data"), list):
        return None
    out = {p.split("_")[0].upper() for p in js["data"] if isinstance(p, str) and p.endswith("_usdt")}
    return out or None


def lbank_label(sym: str, pairs: set[str] | None) -> str:
    if pairs is None:
        return "نامعلوم"
    return "هست" if sym in pairs else NOT_IN_LBANK


# ═══════════════ کندل ═══════════════

COLS = ["ts", "open", "high", "low", "close", "qv", "confirm"]


def _frame(rows: list) -> pd.DataFrame | None:
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=COLS)
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    for c in COLS[1:6]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["confirm"] = df["confirm"].astype(int)
    return df.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)


def okx_frame(rows) -> pd.DataFrame | None:
    """[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm] — حجم دلاری خانه هشتم، قرارداد هم."""
    return _frame([[int(x[0]), x[1], x[2], x[3], x[4], x[7], 1 if str(x[8]) == "1" else 0]
                   for x in rows or [] if len(x) >= 9])


def _closed_by_time(t_s: int, bar_s: int, now: datetime) -> int:
    return 1 if t_s + bar_s <= now.timestamp() else 0


def gate_spot_frame(rows, bar_s: int, now: datetime) -> pd.DataFrame | None:
    """[t(s), quoteVol, close, high, low, open, baseVol, closed]"""
    out = []
    for x in rows or []:
        if len(x) < 6:
            continue
        t = int(float(x[0]))
        conf = ((1 if str(x[7]).lower() == "true" else 0) if len(x) > 7
                else _closed_by_time(t, bar_s, now))
        out.append([t * 1000, x[5], x[3], x[4], x[2], x[1], conf])
    return _frame(out)


def gate_fut_frame(rows, bar_s: int, now: datetime) -> pd.DataFrame | None:
    """{t, o, h, l, c, v, sum} — sum حجم دلاری است. پرچم بسته ندارد؛ از زمان."""
    return _frame([[int(x["t"]) * 1000, x.get("o"), x.get("h"), x.get("l"), x.get("c"),
                    x.get("sum"), _closed_by_time(int(x["t"]), bar_s, now)]
                   for x in rows or [] if isinstance(x, dict) and "t" in x])


def closed(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """کندل باز همیشه حذف — سنجه فقط روی کندل بسته."""
    if df is None:
        return None
    return df[df["confirm"] == 1].reset_index(drop=True)


# ═══════════════ سنجه‌ها ═══════════════

def vol_z(qv, base_n: int, min_n: int) -> tuple[float | None, str | None]:
    """
    z آخرین کندل بسته در برابر base_n کندل پیش از آن، روی ln(1+v) — حجم دم‌کلفت است.
    کمبود پایه «داده کم» است و انحراف صفر یا پوچ «داده ندارم» — هیچ‌کدام صفر نیست.
    """
    x = np.log1p(np.asarray(list(qv), dtype=float))
    if len(x) < min_n + 1:
        return None, "داده کم"
    t, base = x[-1], x[-(base_n + 1):-1]
    if not (np.isfinite(t) and np.all(np.isfinite(base))):
        return None, "داده ندارم"
    sd = float(base.std(ddof=1))
    if not sd > 0:
        return None, "داده ندارم"
    return float((t - base.mean()) / sd), None


def z_recent_max(qv, base_n: int, min_n: int, recent: int
                 ) -> tuple[float | None, int | None, str | None]:
    """بیشینه z در چند کندل بسته آخر — اجرا روزی یک بار است و جهش ساعت قبل گم نشود."""
    qv = list(qv)
    best, ago, why = None, None, None
    for k in range(recent):
        if len(qv) - k < min_n + 1:
            break
        z, w = vol_z(qv[:len(qv) - k], base_n, min_n)
        if z is None:
            why = why or w
        elif best is None or z > best:
            best, ago = z, k
    if best is None:
        return None, None, why or "داده کم"
    return best, ago, None


def z_by_ts(df: pd.DataFrame | None, base_n: int, min_n: int, recent: int) -> dict:
    """z هر یک از چند کندل بسته آخر، با کلید مهر زمان همان کندل."""
    if df is None or len(df) == 0:
        return {}
    qv, ts, out = list(df["qv"]), list(df["ts"]), {}
    for k in range(recent):
        n = len(qv) - k
        if n < min_n + 1:
            break
        z, _ = vol_z(qv[:n], base_n, min_n)
        if z is not None:
            out[ts[n - 1]] = z
    return out


def rel_z(sym: pd.DataFrame | None, btc: pd.DataFrame | None, base_n: int, min_n: int,
          recent: int) -> dict:
    """
    جهش حجم نسبت به بازار: z نماد منهای z بیت‌کوین در همان ساعت و همان صرافی.
    وقتی کل بازار تکان می‌خورد همه از دروازه مطلق می‌گذشتند — LTC و FIL، ۱۰ اکتبر.

    دروازه هر دو را می‌خواهد، در یک ساعت: z مطلق و z نسبی هر دو دست‌کم آستانه؛ یعنی
    gate = z − max(0, z بیت‌کوین). بیت‌کوین کم‌حجم دروازه را شل نمی‌کند — شنبه ۱۰ اکتبر،
    z بیت‌کوین ‎-1.29، تفریق ساده دروازه را از ۱۰ به ۳۴ برد. ف۳۹.
    z مطلق برای جدول می‌ماند. بیت‌کوین غایب یعنی نسبی نامعلوم، نه صفر.
    """
    z, ago, why = z_recent_max([] if sym is None else sym["qv"], base_n, min_n, recent)
    out = {"z": z, "ago": ago, "rel": None, "btc_z": None, "gate": None, "why": why}
    if z is None:
        return out
    zs, zb = z_by_ts(sym, base_n, min_n, recent), z_by_ts(btc, base_n, min_n, recent)
    common = [t for t in zs if t in zb]
    if not common:
        return dict(out, why="بیت‌کوین داده ندارد")
    rel, bz = max((zs[t] - zb[t], zb[t]) for t in common)
    gate = max(zs[t] - max(0.0, zb[t]) for t in common)
    return dict(out, rel=rel, btc_z=bz, gate=gate)


def ratio_shift(spot: pd.DataFrame | None, perp: pd.DataFrame | None) -> dict:
    """
    r = حجم دلاری قرارداد ۲۴ ساعت بسته / حجم نقدی همان ساعت‌ها؛ r7 همان روی ۱۴۴
    ساعت پیش از آن؛ shift = ln(r / r7). هر دو پا از یک صرافی، هم‌تراز روی مهر زمان.
    """
    out = {"r24": None, "r7": None, "shift": None, "why": None}
    if perp is None or len(perp) == 0:
        return dict(out, why="قرارداد ندارد")
    if spot is None or len(spot) == 0:
        return dict(out, why="داده ندارم")
    j = spot[["ts", "qv"]].merge(perp[["ts", "qv"]], on="ts", suffixes=("_s", "_p"))
    need = RATIO_RECENT + RATIO_BASE
    if len(j) < need:
        return dict(out, why="داده کم")
    j = j.iloc[-need:]
    s24, p24 = float(j["qv_s"].iloc[-RATIO_RECENT:].sum()), float(j["qv_p"].iloc[-RATIO_RECENT:].sum())
    s7, p7 = float(j["qv_s"].iloc[:-RATIO_RECENT].sum()), float(j["qv_p"].iloc[:-RATIO_RECENT].sum())
    if not all(math.isfinite(v) and v > 0 for v in (s24, p24, s7, p7)):
        return dict(out, why="داده ندارم")
    r, r7 = p24 / s24, p7 / s7
    return dict(out, r24=r, r7=r7, shift=math.log(r / r7))


def oi_change(points: list[tuple[int, float | None]], now: datetime) -> dict:
    """
    بهره باز به واحد کوین، تا بالا رفتن قیمت آن را باد نکند. points: (مهر ms، کوین).
    نقطه ساعت جاری هنوز بسته نشده و حذف می‌شود — همان قاعده کندل باز.
    """
    cut = now.timestamp() * 1000
    s = {int(t): v for t, v in points
         if t + HOUR_MS <= cut and v is not None and math.isfinite(v) and v > 0}
    out = {"oi": None, "d4": None, "d24": None, "why": None}
    if not s:
        return dict(out, why="داده ندارم")
    t = max(s)
    a4, a24 = s.get(t - 4 * HOUR_MS), s.get(t - 24 * HOUR_MS)
    out["oi"] = s[t]
    if a4 is not None:
        out["d4"] = s[t] / a4 - 1
    if a24 is None:
        out["why"] = "داده کم"
    else:
        out["d24"] = s[t] / a24 - 1
    return out


def abnormal_4h(df: pd.DataFrame | None) -> dict:
    """ر۵۶ — بیشینه دامنه ۴ ساعته در ۷ روز بسته، تقسیم بر میانه ۱۴ روز پیش از آن."""
    out = {"ratio": None, "flag": None, "why": None}
    if df is None or len(df) < ABN_RECENT + ABN_BASE:
        return dict(out, why="داده کم")
    rng = ((df["high"] - df["low"]) / df["open"]).to_numpy(dtype=float)[-(ABN_RECENT + ABN_BASE):]
    base, top = float(np.median(rng[:ABN_BASE])), float(np.nanmax(rng[ABN_BASE:]))
    if not (math.isfinite(base) and base > 0 and math.isfinite(top)):
        return dict(out, why="داده ندارم")
    ratio = top / base
    return dict(out, ratio=ratio, flag=bool(ratio >= ABNORMAL_K))


def price_chg24(df: pd.DataFrame | None) -> float | None:
    if df is None or len(df) < 25:
        return None
    a, b = _f(df["close"].iloc[-25]), _f(df["close"].iloc[-1])
    return b / a - 1 if a and b is not None else None


def _ge(x, t: float) -> bool:
    return x is not None and math.isfinite(x) and x >= t - 1e-12


def flow_signs(m: dict) -> list[str]:
    """دروازه جریان — دودویی، نه امتیاز. سنجه غایب نشانه نیست، صفر هم نیست."""
    s = []
    if _ge(m.get("z1h_gate"), Z_MIN):
        s.append("حجم ساعتی")
    if _ge(m.get("z4h_gate"), Z_MIN):
        s.append("حجم چهارساعته")
    # رشد از پایه ناچیز معنا ندارد — کف دلاری، ف۴۰
    if _ge(m.get("d24"), OI24_MIN) and _ge(m.get("oi_usd"), OI_USD_MIN):
        s.append("بهره باز")
    if _ge(m.get("shift"), math.log(RATIO_MULT)):
        s.append("نسبت قرارداد")
    return s


def leveraged_pump(funding_8h, d24, chg24) -> bool:
    """فاندینگ بالا و بهره باز رو به رشد، ولی قیمت رشد نکرده — الگوی پامپ اهرمی نبض."""
    if None in (funding_8h, d24, chg24):
        return False
    return funding_8h >= LEV_FUNDING_8H and d24 >= LEV_OI24 and chg24 < LEV_PRICE_MAX


def crowd_label(funding_8h) -> str | None:
    """تأمین مالی افراطی در هر دو جهت: قدر مطلق نرخ ۸ ساعته بالاتر از آستانه."""
    f = _f(funding_8h)
    if f is None or abs(f) <= CROWD_FUNDING_ABS:
        return None
    return "ازدحام لانگ" if f > 0 else "ازدحام شورت"


def post_pump(m: dict | None) -> bool:
    """
    پس از پامپ: شمع غیرعادی ر۵۶، یا قدرت نسبی ۷ روزه بالاتر از آستانه. سطحی که بعد از
    پامپ ساخته شده فاصله را کم نشان می‌دهد — KAIA و MAGIC، اجرای ۱۰ اکتبر.
    """
    m = m or {}
    rs7 = _f(m.get("rs7"))
    return bool(m.get("abn_flag")) or (rs7 is not None and rs7 > POST_PUMP_RS7)


def flow_labels(row: dict) -> list[str]:
    """برچسب‌های جریان. ر۵۴ برچسب نمی‌گیرد — روی حجم یک صرافی همه را می‌گرفت."""
    m, out = row.get("metrics") or {}, []
    if m.get("abn_flag"):
        out.append("شمع غیرعادی")
    crowd = crowd_label(row.get("funding_8h"))
    if crowd:
        out.append(crowd)
    if leveraged_pump(row.get("funding_8h"), m.get("d24"), m.get("chg24_closed")):
        out.append("پامپ اهرمی")
    return out


def r54(vol_usd, btc_px) -> float | None:
    """ر۵۴ — حجم ۲۴ ساعته به بیت‌کوین از تیکر همان صرافی. فقط ستون."""
    return vol_usd / btc_px if btc_px and vol_usd is not None else None


# ═══════════════ ستاپ‌ها — روی کندل روزانه بسته ═══════════════

def _setup(name: str, side: str, state: str, level: float, **geo) -> dict:
    """هندسه ستاپ برای کارت معامله در geo — عدد ساده، نه numpy."""
    return {"name": name, "side": side, "state": state, "level": float(level),
            **{k: _f(v) if not isinstance(v, bool) else v for k, v in geo.items()}}


def _compressed(df: pd.DataFrame, atr: pd.Series, end: int) -> tuple[float, float] | None:
    """پنجره [end-۱۰، end): دامنه واقعی نزولی، و دامنه پنجره کمتر از نصف ۲۰ کندل پیش از آن."""
    if end < SQ_WIN + SQ_PRIOR or end > len(df):
        return None
    w, p = df.iloc[end - SQ_WIN:end], df.iloc[end - SQ_WIN - SQ_PRIOR:end - SQ_WIN]
    hi, lo = float(w["high"].max()), float(w["low"].min())
    if not atr.iloc[end - 1] < atr.iloc[end - SQ_WIN]:
        return None
    if not hi - lo < 0.5 * (float(p["high"].max()) - float(p["low"].min())):
        return None
    # افقی: روند با دامنه کم‌شونده فشردگی نیست — LTC، ۱۰ اکتبر. ف۴۵
    if not abs(float(w["close"].iloc[-1]) - float(w["close"].iloc[0])) < SQ_DRIFT * (hi - lo):
        return None
    return hi, lo


def squeeze(df: pd.DataFrame) -> dict | None:
    """الف‌۳ — فشردگی. ماشه: بسته بیرون از محدوده با دامنه بیش از دامنه واقعی."""
    if df is None or len(df) < SQ_WIN + SQ_PRIOR + 1:
        return None
    atr, n = L.atr_wilder(df), len(df)
    box = _compressed(df, atr, n - 1)
    if box:
        hi, lo = box
        x, pc = df.iloc[-1], float(df["close"].iloc[-2])
        tr = max(x["high"] - x["low"], abs(x["high"] - pc), abs(x["low"] - pc))
        if tr > atr.iloc[-2]:
            # تأیید اختیاری: حجم انبساط بالای میانگین ۲۰ کندل پیش از آن
            exp_vol = bool(x["vol"] > df["vol"].iloc[-21:-1].mean()) if "vol" in df else False
            geo = dict(hi=hi, lo=lo, atr=atr.iloc[-2], exp_vol=exp_vol)
            if x["close"] > hi:
                return _setup("الف‌۳", "long", "trigger", hi, **geo)
            if x["close"] < lo:
                return _setup("الف‌۳", "short", "trigger", lo, **geo)
    box = _compressed(df, atr, n)
    if not box:
        return None
    return _setup("الف‌۳", "long", "pre", box[0], hi=box[0], lo=box[1], atr=atr.iloc[-1],
                  exp_vol=False)


def _hist_levels(df: pd.DataFrame) -> list:
    """سطح‌های شناخته‌شده پیش از پنجره اخیر — تعریف radar_levels.structural_levels."""
    hist = df.iloc[:len(df) - BREAK_LOOK].reset_index(drop=True)
    a = _f(L.atr_wilder(hist).iloc[-1]) if len(hist) else None
    if not a or a <= 0:
        return []
    res, sup = L.structural_levels(hist, a)
    return res + sup


def breakout(df: pd.DataFrame) -> dict | None:
    """
    الف‌۱ و ج‌۱. سطح دست‌کم دو برخورد پیش از پنجره ۱۰ کندل اخیر؛ نخستین بسته بالای
    آن در پنجره، شکست است.
      • بسته آخر دوباره زیر سطح ← ج‌۱، شکست ناکام. قاتل: شاخص قدرت نسبی زیر ۳۰.
      • وگرنه الف‌۱ — پیش‌شرط: ۱۵ بسته زیر سطح پیش از شکست. قاتل: حجم شکست نه
        بالای میانگین ۲۰. ماشه: کندل آخر تا نیم دامنه واقعی به سطح برگشت و صعودی
        بالای آن بست.
    """
    if df is None or len(df) < 60:
        return None
    n, c = len(df), df["close"].to_numpy(dtype=float)
    atr = L.atr_wilder(df)
    rsi = _f(R.rsi_wilder(df["close"], 14).iloc[-1])
    last = df.iloc[-1]
    found, killed = [], None
    for lv in _hist_levels(df):
        lvl = lv.price
        b = next((i for i in range(n - BREAK_LOOK, n) if c[i] > lvl >= c[i - 1]), None)
        if b is None:
            continue
        if c[-1] < lvl:
            if rsi is None or rsi >= 30:
                found.append(_setup("ج‌۱", "short", "trigger", lvl,
                                    fail_high=df["high"].iloc[b:].max(),
                                    range_low=df["low"].iloc[max(0, b - BASE_MIN):b].min(),
                                    atr=atr.iloc[-1]))
            continue
        if b < BASE_MIN or not np.all(c[b - BASE_MIN:b] <= lvl):
            continue
        vm = _f(df["vol"].iloc[max(0, b - 20):b].mean())
        if not (vm and vm > 0 and float(df["vol"].iloc[b]) > vm):
            killed = "شکست بی‌حجم"
            continue
        # دامنه واقعی پیش از شکست — شمع شکست بزرگ آن را باد می‌کند و «بازگشت به سطح» را شل
        a = float(atr.iloc[b - 1])
        retest = (b < n - 1 and last["low"] <= lvl + 0.5 * a and last["close"] > lvl
                  and last["close"] > last["open"])
        found.append(_setup("الف‌۱", "long", "trigger" if retest else "pre", lvl,
                            range_low=df["low"].iloc[b - BASE_MIN:b].min(),
                            retest_low=last["low"] if retest else None, atr=a))
    if found:
        return min(found, key=lambda s: (GROUP[s["state"]], abs(c[-1] - s["level"])))
    return {"killed": killed} if killed else None


def pullback(df: pd.DataFrame) -> dict | None:
    """
    الف‌۲ — فقط پیش‌شرط: دو سقف و دو کف بالاتر، قیمت زیر سقف آخر. «کندل واکنش» تعریف
    عددی ندارد، پس ماشه چشمی است. قاتل: اصلاح بیش از دو سوم موج، یا شاخص قدرت نسبی زیر ۵۰.
    """
    if df is None or len(df) < 30:
        return None
    highs, lows = L.find_pivots(df, 3, 3)
    if len(highs) < 2 or len(lows) < 2:
        return None
    (_, h1), (ih2, h2) = highs[-2:]
    (_, l1), (_, l2) = lows[-2:]
    if not (h2 > h1 and l2 > l1):
        return None
    px, rsi = float(df["close"].iloc[-1]), _f(R.rsi_wilder(df["close"], 14).iloc[-1])
    if not px < h2 or rsi is None or rsi < 50:
        return None
    leg = [v for i, v in lows if i < ih2]
    if not leg or h2 - px > 2 / 3 * (h2 - leg[-1]):
        return None
    return _setup("الف‌۲", "long", "pre", l2)


def lower_high(df: pd.DataFrame) -> dict | None:
    """ج‌۲ — پیش‌شرط: کف پایین‌تر. ماشه: سقف پایین‌تر پس از آن و کندل آخر نزولی زیرش."""
    if df is None or len(df) < 20:
        return None
    highs, lows = L.find_pivots(df, 3, 3)
    if len(highs) < 2 or len(lows) < 2:
        return None
    (_, h1), (ih2, h2) = highs[-2:]
    (_, l1), (il2, l2) = lows[-2:]
    if not l2 < l1:
        return None
    x = df.iloc[-1]
    geo = dict(h1=h1, h2=h2, l2=l2, atr=L.atr_wilder(df).iloc[-1])
    if ih2 > il2 and h2 < h1 and x["close"] < x["open"] and x["close"] < h2:
        return _setup("ج‌۲", "short", "trigger", h2, **geo)
    return _setup("ج‌۲", "short", "pre", h2, **geo)


def floor_break(df: pd.DataFrame) -> dict | None:
    """
    ر۵۸ — کف با دست‌کم سه برخورد، و نخستین بسته زیرش در پنجره اخیر. نه پس از صعود:
    بسته پیش از شکست از بسته ۲۰ کندل پیش‌تر بالاتر نباشد.
    """
    if df is None or len(df) < 60:
        return None
    n, c = len(df), df["close"].to_numpy(dtype=float)
    for lv in sorted(_hist_levels(df), key=lambda v: -v.price):
        if lv.touches < 3:
            continue
        b = next((i for i in range(n - BREAK_LOOK, n) if c[i] < lv.price <= c[i - 1]), None)
        if b is None or c[-1] >= lv.price or b < 21 or c[b - 1] > c[b - 21]:
            continue
        return _setup("ر۵۸", "short", "trigger", lv.price)
    return None


def live_check(setups: list[dict], price: float | None) -> tuple[list[dict], list[str]]:
    """
    ستاپ روی کندل بسته دیروز ساخته شده؛ قیمت زنده امروز ممکن است باطلش کرده باشد.
    شورت: قیمت زنده باید زیر سطح باشد. لانگ: بالای سطح — جز فشردگی پیش از شکست،
    که قیمت هنوز درون محدوده است.
    """
    if price is None:
        return list(setups), []
    keep, labels = [], []
    for s in setups:
        if s["side"] == "short":
            bad = price >= s["level"]
        elif s["name"] == "الف‌۳" and s["state"] == "pre":
            # فشردگی واقعی: قیمت زنده درون محدوده یا در حال شکستنش — ف۴۵
            hi, lo, a = s.get("hi"), s.get("lo"), s.get("atr")
            bad = (None not in (hi, lo, a)
                   and not lo - SQ_LIVE_ATR * a <= price <= hi + SQ_LIVE_ATR * a)
        else:
            bad = price <= s["level"]
        if bad:
            labels.append(f"{'شورت' if s['side'] == 'short' else 'لانگ'} {s['name']} باطل شد")
        else:
            keep.append(s)
    return keep, labels


def detect_setups(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    out, labels = [], []
    for fn in (breakout, squeeze, pullback, lower_high, floor_break):
        try:
            s = fn(df)
        except Exception as exc:
            labels.append(f"خطای ستاپ {fn.__name__}: {type(exc).__name__}")
            continue
        if not s:
            continue
        if "killed" in s:
            labels.append(s["killed"])
        else:
            out.append(s)
    return out, labels


# ═══════════════ رتبه، وتو ═══════════════

def _num(x, spec: str) -> str | None:
    v = _f(x)
    return None if v is None else format(v, spec)


def why_line(e: dict) -> str:
    """یک جمله ساده «چرا». عدد بازار لاتین، نثر فارسی."""
    m, parts = e.get("metrics") or {}, []
    s = e.get("setup")
    if s:
        parts.append(f"{SETUP_FA[s['name']]} ({s['name']}) — {STATE_FA[s['state']]}")
    for sign in e.get("signs") or []:
        if sign in ("حجم ساعتی", "حجم چهارساعته"):
            z = _num(m.get("z1h_gate" if sign == "حجم ساعتی" else "z4h_gate"), ".1f")
            parts.append(f"{sign} {z} انحراف معیار بالای عادی و بیش از بیت‌کوین" if z
                         else f"{sign} بالای عادی و بیش از بیت‌کوین")
        elif sign == "بهره باز":
            d = _num(100 * m["d24"], "+.0f") if _f(m.get("d24")) is not None else None
            parts.append(f"بهره باز {d}٪ در ۲۴ ساعت" if d else "بهره باز رو به رشد")
        elif sign == "نسبت قرارداد":
            r = _num(math.exp(m["shift"]), ".1f") if _f(m.get("shift")) is not None else None
            parts.append(f"حجم قرارداد به نقدی {r} برابر شش روز پیش" if r
                         else "حجم قرارداد به نقدی بالا رفته")
    return "؛ ".join(parts) or "بی نشانه"


def _entry(row: dict, side: str, setup: dict | None, group: int, dist) -> dict:
    e = {k: row.get(k) for k in ("symbol", "venue", "price", "signs", "metrics", "lbank",
                                  "funding_8h", "levels", "atr_d")}
    e["labels"] = list(row.get("labels") or [])
    rs7 = _f((row.get("metrics") or {}).get("rs7"))
    if side == "long" and rs7 is not None and rs7 < 0:
        e["labels"].append("ضعیف‌تر از بیت‌کوین")        # ر۵۵
    # فشردگی: فاصله تا ماشه ورود، یعنی لبه محدوده؛ بقیه فاصله تا سطح
    if setup and setup["name"] == "الف‌۳" and setup.get("atr") and _f(row.get("price")):
        dist = abs(setup["level"] - row["price"]) / setup["atr"]
    d = _f(dist)
    e.update(side=side, setup=setup, group=group, dist_atr=d, status=UNTESTED, veto=None)
    if side == "long" and post_pump(row.get("metrics")):
        e["section"] = "afterpump"          # گروهش در دفتر نامزد می‌ماند
    else:
        e["section"] = "nolevel" if d is None else "late" if d > LATE_ATR else side
    e["why"] = why_line(e)
    return e


def place(row: dict) -> list[dict]:
    """
    جایگاه هر نماد گذشته از دروازه: شورت اگر ستاپ شورت دارد؛ لانگ اگر ستاپ لانگ دارد
    یا هیچ ستاپی ندارد («فقط جریان»). فاصله لانگ تا سطح زیر، شورت تا سطح بالا.
    """
    best = {}
    for s in row.get("setups") or []:
        if s["side"] not in best or GROUP[s["state"]] < GROUP[best[s["side"]]["state"]]:
            best[s["side"]] = s
    out = []
    if "short" in best:
        sh = best["short"]
        out.append(_entry(row, "short", sh, GROUP[sh["state"]], row.get("d_res")))
    if "long" in best or "short" not in best:
        lo = best.get("long")
        out.append(_entry(row, "long", lo, GROUP[lo["state"]] if lo else GROUP_FLOW,
                          row.get("d_sup")))
    return out


def rank(rows: list[dict]) -> dict[str, list[dict]]:
    """رتبه بی امتیاز: گروه (ماشه، پیش‌شرط، فقط جریان)، سپس فاصله از سطح."""
    sec: dict[str, list[dict]] = {k: [] for k in SECTIONS}
    for r in rows:
        for e in place(r):
            sec[e["section"]].append(e)
    for k in ("long", "short", "afterpump"):
        sec[k].sort(key=lambda e: (e["group"], math.inf if e["dist_atr"] is None else e["dist_atr"],
                                   e["symbol"]))
    sec["late"].sort(key=lambda e: (e["dist_atr"], e["symbol"]))
    sec["nolevel"].sort(key=lambda e: (e["group"], e["symbol"]))
    return sec


def apply_veto(sec: dict, veto_fn, get, now: datetime) -> list[str]:
    """
    وتوی آزادسازی radar_events برای نامزدهای بالای فهرست — ف۳۱. «وتو» به بخش جدا
    می‌رود؛ «نامعلوم» سر جایش می‌ماند با بررسی دستی پیش از ورود — رد خودکار نیست.
    """
    syms = list(dict.fromkeys([e["symbol"] for e in sec["long"][:VETO_TOP]]
                              + [e["symbol"] for e in sec["short"][:VETO_TOP]]))
    if not syms:
        return []
    try:
        verdicts, notes, _ = veto_fn(syms, get, now)
    except Exception as exc:
        verdicts = {s: {"status": "unknown", "why": "وتو اجرا نشد"} for s in syms}
        notes = [f"⛔ وتوی آزادسازی اجرا نشد — {type(exc).__name__}. حکم همه «نامعلوم»."]
    for k in ("long", "short"):
        keep = []
        for e in sec[k]:
            v = verdicts.get(e["symbol"])
            if v is not None:
                e["veto"] = {"status": v.get("status", "unknown"), "why": v.get("why", "")}
            if e["veto"] and e["veto"]["status"] == "veto":
                e["section"] = "veto"
                sec["veto"].append(e)
            else:
                keep.append(e)
        sec[k] = keep
    return list(notes or [])


# ═══════════════ واکشی هر نماد ═══════════════

def fetch_market(net: Net) -> dict:
    """یک بار برای کل بازار: سه درخواست اوکی‌اکس، سه گیت، یکی ال‌بانک."""
    return {
        "okx_spot": okx_data(net.json(OKX + "/api/v5/market/tickers", {"instType": "SPOT"})),
        "okx_inst": okx_data(net.json(OKX + "/api/v5/public/instruments", {"instType": "SPOT"})),
        "okx_funding": okx_data(net.json(OKX + "/api/v5/public/funding-rate", {"instId": "ANY"})),
        "gate_spot": as_list(net.json(GATE + "/spot/tickers")),
        "gate_pairs": as_list(net.json(GATE + "/spot/currency_pairs")),
        "gate_contracts": as_list(net.json(GATE + "/futures/usdt/contracts")),
        "lbank": lbank_pairs(net.json(LBANK + "/v2/currencyPairs.do")),
    }


def okx_candles(net: Net, inst: str, bar: str) -> pd.DataFrame | None:
    return okx_frame(okx_data(net.json(OKX + "/api/v5/market/candles",
                                       {"instId": inst, "bar": bar, "limit": CANDLES})))


def gate_candles(net: Net, pair: str, iv: str, now: datetime) -> pd.DataFrame | None:
    return gate_spot_frame(as_list(net.json(GATE + "/spot/candlesticks",
                                            {"currency_pair": pair, "interval": iv,
                                             "limit": CANDLES})), BAR_S[iv], now)


def gate_perp_candles(net: Net, contract: str, now: datetime) -> pd.DataFrame | None:
    return gate_fut_frame(as_list(net.json(GATE + "/futures/usdt/candlesticks",
                                           {"contract": contract, "interval": "1h",
                                            "limit": CANDLES})), 3600, now)


def oi_points(net: Net, base: str, venue: str, quanto: float | None) -> list:
    """اوکی‌اکس: [ts, oi, oiCcy, oiUsd] — خانه سوم کوین. گیت: قرارداد × ضریب."""
    if venue == "okx":
        d = okx_data(net.json(OKX + "/api/v5/rubik/stat/contracts/open-interest-history",
                              {"instId": f"{base}-USDT-SWAP", "period": "1H", "limit": 48}))
        return [(int(x[0]), _f(x[2])) for x in d or [] if len(x) > 2]
    d = as_list(net.json(GATE + "/futures/usdt/contract_stats",
                         {"contract": f"{base}_USDT", "interval": "1h", "limit": 48}))
    q = quanto or 1.0
    return [(int(x["time"]) * 1000, (_f(x.get("open_interest")) or 0.0) * q)
            for x in d or [] if isinstance(x, dict) and "time" in x]


def flow_metrics(net: Net, u: dict, now: datetime, btc: dict | None = None) -> dict:
    """
    سنجه‌های جریان یک نماد — حداکثر چهار درخواست، همه روی کندل بسته. btc: کندل بسته
    ۱ و ۴ ساعته بیت‌کوین همان صرافی، برای جهش نسبی.
    """
    b, v = u["symbol"], u["venue"]
    if v == "okx":
        h1, h4 = okx_candles(net, f"{b}-USDT", "1H"), okx_candles(net, f"{b}-USDT", "4H")
    else:
        h1, h4 = gate_candles(net, f"{b}_USDT", "1h", now), gate_candles(net, f"{b}_USDT", "4h", now)
    h1, h4 = closed(h1), closed(h4)
    m: dict = {}
    btc = btc or {}
    r1 = rel_z(h1, btc.get("1h"), Z1H_BASE, Z1H_MIN, Z1H_RECENT)
    r4 = rel_z(h4, btc.get("4h"), Z4H_BASE, Z4H_MIN, 1)
    m["z1h"], m["z1h_ago"], m["z1h_rel"], m["z1h_btc"], m["z1h_gate"], m["z1h_why"] = (
        r1["z"], r1["ago"], r1["rel"], r1["btc_z"], r1["gate"], r1["why"])
    m["z4h"], m["z4h_rel"], m["z4h_btc"], m["z4h_gate"], m["z4h_why"] = (
        r4["z"], r4["rel"], r4["btc_z"], r4["gate"], r4["why"])
    m["chg24_closed"] = price_chg24(h1)
    ab = abnormal_4h(h4)
    m["abn_ratio"], m["abn_flag"] = ab["ratio"], ab["flag"]
    if u["perp_same_venue"]:
        perp = closed(okx_candles(net, f"{b}-USDT-SWAP", "1H") if v == "okx"
                      else gate_perp_candles(net, f"{b}_USDT", now))
        rs = ratio_shift(h1, perp)
    else:
        rs = {"r24": None, "r7": None, "shift": None, "why": "قرارداد ندارد"}
    m["ratio24"], m["ratio7"], m["shift"], m["shift_why"] = rs["r24"], rs["r7"], rs["shift"], rs["why"]
    oc = (oi_change(oi_points(net, b, u["deriv_venue"], u.get("quanto")), now)
          if u["deriv_venue"] else {"oi": None, "d4": None, "d24": None, "why": "قرارداد ندارد"})
    m["oi"], m["d4"], m["d24"], m["oi_why"] = oc["oi"], oc["d4"], oc["d24"], oc["why"]
    m["oi_usd"] = oc["oi"] * u["price"] if oc["oi"] and u.get("price") else None
    m["funding_8h"] = u["funding_8h"]
    return m


def daily_candles(net: Net, base: str, venue: str) -> pd.DataFrame | None:
    """کندل روزانه از کلاس صرافی radar_fetch3 — همان لنگر و صفحه‌بندی؛ شبکه از Net."""
    return R.VENUES[venue].candles(base, "1D", R.DAILY_WANT, net.http)


def structure(net: Net, row: dict, btc: pd.DataFrame | None) -> dict:
    """سطح، فاصله، ستاپ و قدرت نسبی — فقط برای گذشته‌ها از دروازه."""
    out = {"d_sup": None, "d_res": None, "support": None, "resistance": None,
           "level_verdict": None, "setups": [], "labels": [], "rs7": None, "rs30": None,
           "levels": [], "atr_d": None}
    d = daily_candles(net, row["symbol"], row["venue"])
    if d is None or len(d) == 0:
        out["labels"].append("کندل روزانه نیامد")
        return out
    a = L.assess(row["symbol"], d)
    out["level_verdict"] = a.verdict
    atr = _f(a.atr)
    if a.support is not None and atr:
        out["support"], out["d_sup"] = a.support.price, _f(a.dist_sup_atr)
    if a.resistance is not None and atr and a.price is not None:
        out["resistance"], out["d_res"] = a.resistance.price, (a.resistance.price - a.price) / atr
    dc = d[d["confirm"] == 1].reset_index(drop=True) if "confirm" in d.columns else d
    out["atr_d"] = atr
    if atr:
        res, sup = L.structural_levels(dc, atr)
        out["levels"] = sorted(lv.price for lv in res + sup)
    setups, labels = detect_setups(dc)
    out["setups"], void = live_check(setups, _f(row.get("price")))
    out["labels"] = labels + void
    if btc is not None:
        out["rs7"], out["rs30"] = rs_pair(dc, btc, 7), rs_pair(dc, btc, 30)
    return out


# ═══════════════ کارت معامله — جدول همان ستاپ در کتابخانه ═══════════════

CARD_KEYS = ("ok", "why", "tag", "entry", "stop", "target", "target_25r", "rr", "rr_gross", "grade",
             "risk_pct")
STEP_R = 2.5                     # پله کنار هدف ساختاری: ورود + ۲.۵ × فاصله ورود تا استاپ


def _p(x) -> str:
    """قیمت در متن کارت — عدد بازار، رقم لاتین."""
    v = _f(x)
    return "—" if v is None else f"{v:.6g}"


def card_geometry(s: dict, price: float | None, levels: list, atr) -> dict | str:
    """ورود، استاپ، هدف، ماشه و ابطال از جدول همان ستاپ — یا دلیل نبود کارت."""
    name, side, st = s["name"], s["side"], s["state"]
    a = _f(s.get("atr")) or _f(atr)
    if name == "الف‌۳":
        hi, lo = _f(s.get("hi")), _f(s.get("lo"))
        if hi is None or lo is None or hi <= lo:
            return "کارت ندارد — محدوده فشردگی نامعلوم"
        h = hi - lo
        if side == "long":
            nxt = min((v for v in levels if v > hi), default=None)
            return {"entry": hi, "stop": lo,
                    "target": hi + 2 * h if nxt is None else max(hi + 2 * h, nxt),
                    "trigger": f"بسته روزانه بالای سقف محدوده {_p(hi)}",
                    "invalid": f"بسته روزانه دوباره داخل محدوده، زیر {_p(hi)}"}
        nxt = max((v for v in levels if v < lo), default=None)
        return {"entry": lo, "stop": hi,
                "target": lo - 2 * h if nxt is None else min(lo - 2 * h, nxt),
                "trigger": f"بسته روزانه زیر کف محدوده {_p(lo)}",
                "invalid": f"بسته روزانه دوباره داخل محدوده، بالای {_p(lo)}"}
    if name == "الف‌۱":
        lvl, rl = s["level"], _f(s.get("range_low"))
        if rl is None or a is None:
            return "کارت ندارد — رنج شکسته‌شده نامعلوم"
        if st == "trigger" and _f(s.get("retest_low")) is not None and price is not None:
            entry, stop = price, s["retest_low"] - STOP_BUF_ATR * a
            trig = f"بازآزمایی {_p(lvl)} انجام شد — ورود در قیمت زنده"
        else:
            entry, stop = lvl, lvl - STOP_BUF_ATR * a
            trig = f"بازگشت به {_p(lvl)} و کندل واکنش صعودی روی آن"
        return {"entry": entry, "stop": stop, "target": lvl + (lvl - rl), "trigger": trig,
                "invalid": f"بسته روزانه دوباره زیر {_p(lvl)} — داخل رنج قبلی"}
    if name == "ج‌۱":
        fh, rl = _f(s.get("fail_high")), _f(s.get("range_low"))
        if None in (fh, rl, a, price):
            return "کارت ندارد — هندسه شکست ناکام نامعلوم"
        return {"entry": price, "stop": fh + STOP_BUF_ATR * a, "target": rl,
                "trigger": f"بسته روزانه دوباره زیر {_p(s['level'])} رخ داد — ورود در قیمت زنده",
                "invalid": f"بازپس‌گیری {_p(s['level'])} با بسته روزانه"}
    if name == "ج‌۲" and st == "trigger":
        h1, h2, l2 = _f(s.get("h1")), _f(s.get("h2")), _f(s.get("l2"))
        if None in (h1, h2, l2, a, price):
            return "کارت ندارد — هندسه سقف پایین‌تر نامعلوم"
        return {"entry": price, "stop": h2 + STOP_BUF_ATR * a, "target": l2,
                "trigger": f"سقف پایین‌تر {_p(h2)} و کندل نزولی رخ داد — ورود در قیمت زنده",
                "invalid": f"بازپس‌گیری سقف قبلی {_p(h1)}"}
    if name == "ر۵۸":
        return "کارت ندارد — ر۵۸ روش است، ستاپ کتابخانه نیست"
    return "کارت ندارد — ماشه عددی ندارد، چشمی"


def confirmations(s: dict, e: dict) -> dict[str, bool]:
    """تأییدهای اختیاری جدول همان ستاپ. آنچه سنجیده نمی‌شود «نه» است — محافظه‌کارانه."""
    m = e.get("metrics") or {}
    rs7, d24, f = _f(m.get("rs7")), _f(m.get("d24")), _f(e.get("funding_8h"))
    return {
        "الف‌۱": {"حجم شکست بالای میانگین": True,       # بی آن، شکست بی‌حجم و ستاپ کشته
                  "قدرت نسبی مثبت به بیت‌کوین": rs7 is not None and rs7 > 0,
                  "سطح هم‌زمان مرز ناحیه ارزش": False},  # سنجیده نمی‌شود
        "الف‌۳": {"بهره باز رو به رشد": d24 is not None and d24 > 0,
                  "حجم انبساط بالای میانگین": bool(s.get("exp_vol"))},
        "ج‌۱": {"فاندینگ به‌شدت مثبت": f is not None and f > CROWD_FUNDING_ABS,
                "بهره باز بالا": d24 is not None and d24 >= OI24_MIN},
        "ج‌۲": {"ضعف نسبی به بیت‌کوین": rs7 is not None and rs7 < 0,
                "حجم بالاتر در موج نزولی": False},     # سنجیده نمی‌شود
    }.get(s["name"], {})


def quality(rr: float, conf: dict, on_level: bool) -> tuple[str | None, float]:
    """جدول ۸.۲ کتابخانه — بی امتیاز: نسبت، تأییدها و ورود روی سطح."""
    n, k = len(conf), sum(conf.values())
    for grade, mult, floor in QUALITY:
        if rr < floor:
            continue
        if grade == "الف" and not (n and k == n and on_level):
            continue
        if grade == "ب" and k < 1:
            continue
        return grade, mult
    return None, 0.0


def size_card(entry: float, risk: float, cost: float, qmult: float, budget: dict | None) -> dict:
    """
    ریسک٪ = ۲ × ضریب رژیم × ضریب کیفیت؛ سقف هر معامله ۲٪ مثل radar_size؛ سقف باقی‌مانده
    بودجه دفتر معامله. سرمایه به روش radar_book. هر کارت جدا — با هم بیش از باقی‌مانده‌اند.
    """
    out = {"risk_pct": None, "risk_usd": None, "qty": None, "notional": None, "size_why": None}
    band = (budget or {}).get("band")
    if band is None:
        return dict(out, size_why="اندازه ندارد — رژیم کهنه یا خوانده نشد")
    pct = min(BASE_RISK_PCT * band["mult"] * qmult, MAX_TRADE_RISK_PCT)
    free = _f(budget.get("free_pct"))
    if free is not None:
        pct = min(pct, max(free, 0.0))
    out["risk_pct"] = pct
    total = _f(budget.get("total"))
    if not total:
        return dict(out, size_why="سرمایه نامعلوم — فقط درصد ریسک")
    usd = pct / 100 * total
    qty = usd / (risk + cost)
    return dict(out, risk_usd=usd, qty=qty, notional=qty * entry)


def make_card(e: dict, budget: dict | None) -> dict:
    """کارت معامله یک نامزد لانگ یا شورت. کف نسبت با کارمزد ۲.۵ — اصل دو کتابخانه."""
    side, s = e.get("side"), e.get("setup")
    c = {k: None for k in CARD_KEYS + ("trigger", "invalid", "confirms", "on_level", "qmult",
                                        "risk_usd", "qty", "notional", "size_why")}
    c.update(ok=False, tag="فیوچرز" if side == "short" else "نقدی")
    if not s:
        return dict(c, why="کارت ندارد — ستاپ نام‌دار نیست")
    price = _f(e.get("price"))
    g = card_geometry(s, price, e.get("levels") or [], e.get("atr_d"))
    if isinstance(g, str):
        return dict(c, why=g)
    c.update(g)
    sgn = 1 if side == "long" else -1
    risk, reward = sgn * (g["entry"] - g["stop"]), sgn * (g["target"] - g["entry"])
    if not (risk > 0 and reward > 0):
        return dict(c, why="کارت ندارد — هندسه وارونه")
    # هدف ساختاری گاهی خیلی دور است — OP، ۱۰ اکتبر، +۸۱٪. پله ۲.۵R کنارش
    c["target_25r"] = g["entry"] + sgn * STEP_R * risk
    cost = g["entry"] * RT_COST
    c.update(rr_gross=reward / risk, rr=(reward - cost) / (risk + cost))
    a = _f(e.get("atr_d")) or _f(s.get("atr"))
    on_level = bool(a) and any(abs(v - g["entry"]) <= ON_LEVEL_ATR * a for v in e.get("levels") or [])
    conf = confirmations(s, e)
    grade, qmult = quality(c["rr"], conf, on_level)
    c.update(confirms=conf, on_level=on_level, grade=grade, qmult=qmult)
    if side == "long" and e.get("lbank") != "هست":
        return dict(c, why="کارت ندارد — در LBank نیست" if e.get("lbank") == NOT_IN_LBANK
                    else "کارت ندارد — بودن در LBank نامعلوم")
    if grade is None:
        return dict(c, why="کارت ندارد — نسبت کافی نیست")
    c["ok"] = True
    c.update(size_card(g["entry"], risk, cost, qmult, budget))
    return c


def ticker_prices(m: dict) -> dict[str, float]:
    """قیمت زنده هر نماد از تیکرهای یک‌باره: اوکی‌اکس اول، گیت پشتیبان."""
    out: dict[str, float] = {}
    for t in m.get("gate_spot") or []:
        p, v = t.get("currency_pair", ""), _f(t.get("last"))
        if p.endswith("_USDT") and v:
            out[p[:-5]] = v
    for t in m.get("okx_spot") or []:
        i, v = t.get("instId", ""), _f(t.get("last"))
        if i.endswith("-USDT") and v:
            out[i[:-5]] = v
    return out


def budget_from(h: dict, prices: dict, band: dict) -> dict:
    """سرمایه و حرارت دفتر معامله با همان توابع radar_book — radar_positions.value و trade_heat."""
    import radar_positions as PS
    val = PS.value(h, prices)
    total = val["total"]
    heat = PS.trade_heat(h, band, total)
    free = heat["cap_usd"] - heat["effective"]
    return {"band": band, "total": total, "free_pct": 100 * free / total if total > 0 else None,
            "heat": heat["effective"], "cap_usd": heat["cap_usd"],
            "missing": val["missing"], "note": ""}


def load_budget(holdings: str, regime_file: str, prices: dict) -> dict:
    """باند دفتر معامله با هیسترزیس، مثل radar_size؛ سرمایه از holdings.json. خطا یعنی بی‌اندازه."""
    out = {"band": None, "total": None, "free_pct": None, "note": ""}
    try:
        import radar_book as B
        from radar_budget import regime_band
        info = B.load_regime(regime_file)
        raw = regime_band(info.score) if info.score is not None else None
        band, bnote = B.effective_trade_band(raw, info)
    except Exception as exc:
        return dict(out, note=f"رژیم خوانده نشد — {type(exc).__name__}")
    if band is None:
        return dict(out, note=f"رژیم کهنه — {bnote}")
    try:
        import radar_positions as PS
        h, _ = PS.load(holdings)
        b = budget_from(h, prices, band)
    except Exception as exc:
        return dict(out, band=band, note=f"باند {band['name']}؛ سرمایه خوانده نشد — "
                                         f"{type(exc).__name__}")
    miss = f"؛ ⚠️ بی‌قیمت: {'، '.join(b['missing'])}" if b["missing"] else ""
    return dict(b, note=f"باند {band['name']} — {bnote}{miss}")


# ═══════════════ دفتر نامزد — برای نشست ۱۳ ═══════════════

def load_ledger(path: str) -> dict:
    p = Path(path)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": 1, "_قاعده": "همه گذشته‌ها از دروازه جریان، روزی یک بار برای هر نماد. "
            "قیمت ۲۴ ساعت و ۷ روز بسته کندل ۱ ساعته است. داده آزمون نشست ۱۳ — "
            "بی سوگیری انتخاب.", "entries": []}


def ledger_add(led: dict, rows: list[dict], sec: dict, now: datetime) -> int:
    day, have = now.strftime("%Y-%m-%d"), {e["id"] for e in led["entries"]}
    places: dict[str, list] = {}
    for k in SECTIONS:
        for e in sec[k]:
            places.setdefault(e["symbol"], []).append(
                {"side": e["side"], "section": k, "group": e["group"], "setup": e["setup"],
                 "dist_atr": e["dist_atr"], "veto": e["veto"],
                 "card": ({k2: e["card"].get(k2) for k2 in CARD_KEYS} if e.get("card")
                          else None)})
    n = 0
    for r in rows:
        eid = f"{day}:{r['symbol']}"
        if eid in have:
            continue
        led["entries"].append({
            "id": eid, "at": iso(now), "symbol": r["symbol"], "venue": r["venue"],
            "price": r["price"], "signs": r["signs"], "placements": places.get(r["symbol"], []),
            "metrics": r["metrics"], "labels": r["labels"], "lbank": r.get("lbank"),
            "status": UNTESTED, "prices": {k: None for k in LEDGER_POINTS}})
        n += 1
    return n


def ledger_fill(led: dict, now: datetime, history) -> list[str]:
    """قیمت‌های سررسیده — همان تعریف دفتر رویداد radar_events. شکست با دلیل می‌ماند."""
    notes = []
    for e in led["entries"]:
        at = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
        for name, hrs in LEDGER_POINTS.items():
            cur = e["prices"].get(name)
            if cur is not None and "close" in cur:
                continue
            close_at = (at + timedelta(hours=hrs)).replace(minute=0, second=0, microsecond=0)
            if now < close_at + DUE_MARGIN:
                continue
            open_ = close_at - timedelta(hours=1)
            try:
                s = history(e["symbol"], "1h", open_, open_)
                row = s.df[(s.df["ts"] == open_) & (s.df["confirm"] == 1)]
                if row.empty:
                    raise LookupError(f"کندل بسته {iso(open_)} نیامد")
                e["prices"][name] = {"close": float(row["close"].iloc[-1]),
                                     "candle_open": iso(open_), "venue": s.venue}
            except Exception as exc:
                why = f"{type(exc).__name__}: {str(exc)[:160]}"
                e["prices"][name] = {"error": why, "tried_at": iso(now)}
                notes.append(f"⚠️ دفتر نامزد: {e['symbol']} {name} برای {e['id']} — {why}")
    return notes


# ═══════════════ خروجی ═══════════════

def _clean(o):
    """JSON سالم: عدد نامتناهی None می‌شود، نوع numpy عدد ساده."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _f(o)
    return o


def _cell(x, spec: str, pct: bool = False) -> str:
    v = _f(x)
    if v is None:
        return "—"
    return format(100 * v, spec) + "٪" if pct else format(v, spec)


def _veto_txt(v) -> str:
    if not v:
        return "—"
    return {"veto": "⛔ وتو", "pass": "عبور", "unknown": "نامعلوم — بررسی دستی"}.get(
        v.get("status"), "نامعلوم — بررسی دستی")


def _setup_txt(s) -> str:
    return f"{s['name']} {STATE_FA[s['state']]}" if s else "فقط جریان"


def _card_txt(c: dict | None) -> str:
    if not c:
        return "—"
    if c["ok"]:
        risk = f"، ریسک {c['risk_pct']:.2f}٪" if c.get("risk_pct") is not None else ""
        return f"رده {c['grade']}{risk}"
    return (c["why"] or "").replace("کارت ندارد — ", "ندارد: ")


def _table(es: list[dict], side_word: str) -> list[str]:
    where = f"فاصله تا سطح {side_word}" if side_word else "فاصله تا سطح"
    o = [f"| # | نماد | ستاپ | {where} (برابر دامنه واقعی) | چرا "
         "| فاندینگ ۸ ساعته | وتو | ال‌بانک | کارت | برچسب |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(es, 1):
        labels = "، ".join([UNTESTED] + list(e.get("labels") or []))
        o.append(f"| {i} | **{e['symbol']}** | {_setup_txt(e['setup'])} | {_cell(e['dist_atr'], '.2f')} "
                 f"| {e['why']} | {_cell(e.get('funding_8h'), '+.4f', True)} | {_veto_txt(e['veto'])} "
                 f"| {e.get('lbank') or '—'} | {_card_txt(e.get('card'))} | {labels} |")
    return o


def _cards_section(res: dict) -> list[str]:
    sec, b = res["sections"], res.get("budget") or {}
    o = [f"## ۳ — کارت‌های معامله — {UNTESTED}", "",
         "> طبق جدول همان ستاپ در کتابخانه. نسبت با کارمزد و لغزش رفت و برگشت "
         f"{fa(f'{100 * RT_COST:g}')}٪؛ کف {fa(f'{MIN_RR:g}')} — اصل دو. ریسک٪ = "
         f"{fa(f'{BASE_RISK_PCT:g}')} × ضریب رژیم × ضریب کیفیت جدول ۸.۲، سقف هر معامله "
         f"{fa(f'{MAX_TRADE_RISK_PCT:g}')}٪ مثل radar_size، و سقف باقی‌مانده بودجه دفتر معامله. "
         "هر کارت جدا حساب شده؛ با هم از باقی‌مانده بیشترند. لانگ نقدی فقط اگر در ال‌بانک هست.",
         ""]
    total, free = _f(b.get("total")), _f(b.get("free_pct"))
    o += [f"بودجه: {b.get('note') or 'خوانده نشد'} | سرمایه "
          f"{'—' if total is None else format(total, ',.0f') + ' دلار'} | باقی‌مانده بودجه دفتر "
          f"معامله {'—' if free is None else format(free, '.2f') + '٪'}", ""]
    ok = [e for e in sec["long"] + sec["short"] if (e.get("card") or {}).get("ok")]
    if not ok:
        return o + ["**امروز کارتی نیست.** دلیل هر نامزد در ستون «کارت» بخش ۱ و ۲.", ""]
    o += ["| نماد | سمت | ستاپ | ماشه ورود | ابطال | ورود | استاپ | پله دو و نیم برابر ریسک (2.5R) "
          "| هدف ساختاری | نسبت با کارمزد تا هدف ساختاری | رده | ریسک٪ | ریسک دلاری | مقدار | نوع |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in ok:
        c = e["card"]
        o.append(f"| **{e['symbol']}** | {'لانگ' if e['side'] == 'long' else 'شورت'} "
                 f"| {_setup_txt(e['setup'])} | {c['trigger']} | {c['invalid']} | {_p(c['entry'])} "
                 f"| {_p(c['stop'])} | {_p(c['target_25r'])} | {_p(c['target'])} | {c['rr']:.2f} "
                 f"| {c['grade']} "
                 f"| {_cell(c.get('risk_pct'), '.2f')} | {_cell(c.get('risk_usd'), ',.0f')} "
                 f"| {_cell(c.get('qty'), '.6g')} | {c['tag']} |")
    return o + [""]


def render_md(res: dict) -> str:
    sec, L_ = res["sections"], []
    A = L_.append
    A(f"# اسکنر پامپ رادار {R.FRAMEWORK} — نسخه {VERSION}")
    A("")
    A(f"تولید: **{res['generated']}** | صرافی داده: اوکی‌اکس و گیت | ال‌بانک: فهرست جفت نقدی")
    A("")
    A("> **این فهرست مجوز ورود نیست.** اسکنر معامله نمی‌کند و چیزی وارد دفتر موقعیت "
      "نمی‌شود. هر نامزد مال دفتر معامله است، زیر سقف ریسک رژیم.")
    A(">")
    A(f"> **همه نامزدها {UNTESTED}‌اند تا نشست ۱۳.** رتبه بی امتیاز است: ماشه ستاپ، سپس "
      "پیش‌شرط، سپس فقط جریان؛ داخل هر گروه فاصله از سطح.")
    A("")
    n_cards = sum(1 for e in sec["long"] + sec["short"] if (e.get("card") or {}).get("ok"))
    lo_t, hi_t = DAILY_TARGET
    A(f"**امروز {n_cards} کارت، {len(sec['long']) + len(sec['short'])} نامزد.** هدف روزانه "
      f"{fa(lo_t)} تا {fa(hi_t)} نامزد لانگ و شورت — پیشنهاد بازبین، تصمیم کاربر.")
    A("")
    for w in res["warnings"]:
        A(f"> ⚠️ {w}")
        A("")
    A("| جهان بازار | از دروازه جریان گذشت | لانگ | شورت | پس از پامپ | دیر است | بی‌سطح | وتو |")
    A("|---|---|---|---|---|---|---|---|")
    A(f"| {res['universe_n']} | {res['gate_n']} | " + " | ".join(
        str(len(sec[k])) for k in SECTIONS) + " |")
    A("")
    floor_m = fa(f"{res['min_vol'] / 1e6:g}")
    A(f"کف جهان بازار: حجم ۲۴ ساعته یک صرافی دست‌کم {floor_m} میلیون دلار. "
      "حجم دو صرافی جمع نمی‌شود.")
    A("")
    A("## ۱ — لانگ")
    A("")
    L_ += _table(sec["long"], "زیر") if sec["long"] else ["**هیچ نامزدی.**"]
    A("")
    A(f"## ۲ — شورت — {UNTESTED}")
    A("")
    A("> سقف ریسک رژیم همان است. ستاپ‌های ج‌۱، ج‌۲، ر۵۸ و شکست فشردگی رو به پایین.")
    A("")
    L_ += _table(sec["short"], "بالا") if sec["short"] else ["**هیچ نامزدی.**"]
    A("")
    L_ += _cards_section(res)
    A("## ۴ — پس از پامپ — دنبالش نکن")
    A("")
    A(f"> شمع غیرعادی ر۵۶، یا قدرت نسبی ۷ روزه به بیت‌کوین بالاتر از "
      f"{fa(f'{POST_PUMP_RS7:g}')}٪. سطحی که بعد از پامپ ساخته شده فاصله را کم نشان "
      "می‌دهد. در دفتر نامزد با گروه خودش ثبت می‌شود.")
    A("")
    L_ += _table(sec["afterpump"], "زیر") if sec["afterpump"] else ["**هیچ‌کدام.**"]
    A("")
    A(f"## ۵ — دیر است — بیش از {fa(f'{LATE_ATR:g}')} برابر دامنه واقعی از سطح")
    A("")
    A("> جای حد ضرر نزدیک ندارد — قاعده سخت ۵ و ر۵۷. منتظر اصلاح و برگشت.")
    A("")
    L_ += _table(sec["late"], "") if sec["late"] else ["**هیچ‌کدام.**"]
    A("")
    A("## ۶ — بی‌سطح یا داده کم")
    A("")
    L_ += _table(sec["nolevel"], "") if sec["nolevel"] else ["**هیچ‌کدام.**"]
    A("")
    A("## ۷ — وتوی آزادسازی")
    A("")
    if sec["veto"]:
        A("| نماد | سمت | دلیل |")
        A("|---|---|---|")
        for e in sec["veto"]:
            A(f"| **{e['symbol']}** | {'لانگ' if e['side'] == 'long' else 'شورت'} | {e['veto']['why']} |")
    else:
        A("**هیچ‌کدام.**")
    A("")
    for n_ in res["veto_notes"]:
        A(f"> {n_}")
        A("")
    A("## ۸ — سنجه‌های همه گذشته‌ها از دروازه")
    A("")
    A("| نماد | صرافی | جهش حجم ۱ ساعته، مطلق / نسبی | جهش حجم ۴ ساعته، مطلق / نسبی "
      "| بهره باز ۲۴ ساعته | نسبت قرارداد "
      "به نقدی | فاندینگ ۸ ساعته | حجم به بیت‌کوین | قدرت نسبی ۷ روزه | قدرت نسبی ۳۰ روزه "
      "| شمع ۴ ساعته | عمر روز |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in res["rows"]:
        m = r["metrics"]
        ratio = _cell(math.exp(m["shift"]), ".2f") if _f(m.get("shift")) is not None else (
            m.get("shift_why") or "—")
        A(f"| **{r['symbol']}** | {VENUE_FA[r['venue']]} "
          f"| {_cell(m.get('z1h'), '+.1f')} / {_cell(m.get('z1h_rel'), '+.1f')} "
          f"| {_cell(m.get('z4h'), '+.1f')} / {_cell(m.get('z4h_rel'), '+.1f')} "
          f"| {_cell(m.get('d24'), '+.1f', True)} | {ratio} "
          f"| {_cell(m.get('funding_8h'), '+.4f', True)} | {_cell(m.get('vol_btc'), '.0f')} "
          f"| {_cell(m.get('rs7'), '+.1f')} | {_cell(m.get('rs30'), '+.1f')} "
          f"| {_cell(m.get('abn_ratio'), '.1f')} | {_cell(r.get('age_days'), '.0f')} |")
    A("")
    A("## چطور بخوانی")
    A("")
    A("| ستون یا برچسب | معنا |")
    A("|---|---|")
    A(f"| جهش حجم | حجم دلاری کندل بسته در برابر میانگین خود نماد، به انحراف معیار. "
      f"نسبی یعنی منهای همان عدد بیت‌کوین در همان ساعت و همان صرافی. دروازه: مطلق و نسبی "
      f"هر دو دست‌کم {fa(f'{Z_MIN:g}')} |")
    A(f"| بهره باز | تغییر ۲۴ ساعته به واحد کوین. دروازه: دست‌کم {fa(f'{100 * OI24_MIN:g}')}٪، "
      f"با بهره باز دلاری دست‌کم {fa(f'{OI_USD_MIN / 1e6:g}')} میلیون |")
    A("| ضعیف‌تر از بیت‌کوین | ر۵۵ — لانگ با قدرت نسبی ۷ روزه منفی |")
    A("| کارت | رده جدول ۸.۲ و ریسک٪، یا دلیل نبود کارت |")
    A(f"| نسبت قرارداد به نقدی | این ۲۴ ساعت در برابر شش روز پیش از آن، یک صرافی. دروازه: "
      f"{fa(f'{RATIO_MULT:g}')} برابر |")
    A("| ماشه / پیش‌شرط / فقط جریان | گروه رتبه. داخل گروه، نزدیک‌تر به سطح بالاتر |")
    A(f"| ازدحام لانگ / شورت | قدر مطلق فاندینگ ۸ ساعته بالاتر از "
      f"{fa(f'{100 * CROWD_FUNDING_ABS:g}')}٪؛ مثبت لانگ، منفی شورت |")
    A("| پامپ اهرمی | فاندینگ بالا و بهره باز رو به رشد، ولی قیمت رشد نکرده — الگوی هشدار نبض |")
    A(f"| شمع غیرعادی | ر۵۶ — دامنه یک شمع ۴ ساعته دست‌کم {fa(f'{ABNORMAL_K:g}')} برابر میانه |")
    A("| حجم به بیت‌کوین | ر۵۴ — حجم ۲۴ ساعته یک صرافی تقسیم بر قیمت بیت‌کوین. فقط ستون، "
      "بی کف و بی برچسب |")
    A("| در LBank نیست | جفت نقدی USDT در ال‌بانک نیست. «نامعلوم» یعنی فهرست ال‌بانک نیامد |")
    A("")
    A("## درخواست‌ها")
    A("")
    A("| مقصد | درخواست |")
    A("|---|---|")
    for k, v in sorted(res["requests"].items()):
        A(f"| {k} | {v} |")
    A(f"| زمان اجرا | {res['elapsed_s']:.0f} ثانیه |")
    A("")
    return "\n".join(L_)


# ═══════════════ نبض و تلگرام ═══════════════

def pulse_picks(sec: dict) -> list[dict]:
    """نامزدهای امروز برای نبض: کارت‌دار اول، سپس لانگ و شورت به ترتیب رتبه."""
    both = list(sec.get("long") or []) + list(sec.get("short") or [])
    return ([e for e in both if (e.get("card") or {}).get("ok")]
            + [e for e in both if not (e.get("card") or {}).get("ok")])


def pulse_merge(prev: list[dict], picks: list[dict], now: datetime) -> list[dict]:
    """
    بخش pulse در pump.json — جدا از دفتر موقعیت؛ watch.json هرگز نوشته نمی‌شود.
    سقف ۵ و انقضای ۳ روز. نامزد امروز اول است و پیدا شدن دوباره انقضا را تمدید می‌کند؛
    سپس مانده‌های تاریخ‌نگذشته، تازه‌دیده‌تر اول.
    """
    exp = iso(now + timedelta(days=PULSE_TTL_DAYS))
    live = {}
    for it in prev or []:
        try:
            if datetime.fromisoformat(it["expires"].replace("Z", "+00:00")) > now:
                live[it["symbol"]] = it
        except (KeyError, TypeError, ValueError):
            continue
    out: list[dict] = []
    for e in picks:
        if len(out) >= PULSE_MAX:
            break
        if any(o["symbol"] == e["symbol"] for o in out):
            continue
        out.append({"symbol": e["symbol"], "side": e["side"],
                    "setup": (e.get("setup") or {}).get("name"),
                    "added": (live.get(e["symbol"]) or {}).get("added", iso(now)),
                    "last_seen": iso(now), "expires": exp})
    for it in sorted(live.values(), key=lambda x: x.get("last_seen", ""), reverse=True):
        if len(out) >= PULSE_MAX:
            break
        if all(o["symbol"] != it["symbol"] for o in out):
            out.append(it)
    return out


def telegram_line(sec: dict) -> str:
    """یک خط ساده برای پیام روزانه: تعداد کارت و نامشان، و تعداد هر بخش."""
    cards = [e["symbol"] for e in list(sec.get("long") or []) + list(sec.get("short") or [])
             if (e.get("card") or {}).get("ok")]
    names = f": {'، '.join(cards)}" if cards else ""
    parts = [f"{w} {len(sec.get(k) or [])}" for k, w in
             (("long", "لانگ"), ("short", "شورت"), ("afterpump", "پس از پامپ"), ("late", "دیر است"),
              ("nolevel", "بی‌سطح"), ("veto", "وتو"))]
    return f"اسکنر پامپ، {UNTESTED}: {len(cards)} کارت{names}؛ " + "، ".join(parts)


def _write(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


# ═══════════════ اجرا ═══════════════

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def scan(net: Net, now: datetime, min_vol: float, veto_fn, limit: int = 0,
         budget_fn=None) -> dict | None:
    m = fetch_market(net)
    if not m["okx_spot"] and not m["gate_spot"]:
        return None
    uni, btc_px, warns = build_universe(m, min_vol, now)
    if m["lbank"] is None:
        warns.append("فهرست ال‌بانک نیامد — ستون ال‌بانک «نامعلوم»، نه «نیست»")
    if btc_px is None:
        warns.append("قیمت بیت‌کوین نیامد — حجم به بیت‌کوین خالی")
    syms = sorted(uni, key=lambda s: -uni[s]["vol24"])
    syms = syms[:limit] if limit else syms
    _log(f"[۱] جهان بازار: {len(uni)} نماد — سنجه جریان برای {len(syms)}")
    btc_frames: dict[str, dict] = {}

    def btc_for(v: str) -> dict:
        """کندل بسته بیت‌کوین همان صرافی، یک بار — مبنای جهش حجم نسبی."""
        if v not in btc_frames:
            if v == "okx":
                f1, f4 = okx_candles(net, "BTC-USDT", "1H"), okx_candles(net, "BTC-USDT", "4H")
            else:
                f1, f4 = (gate_candles(net, "BTC_USDT", "1h", now),
                          gate_candles(net, "BTC_USDT", "4h", now))
            btc_frames[v] = {"1h": closed(f1), "4h": closed(f4)}
            if f1 is None or f4 is None:
                warns.append(f"کندل بیت‌کوین {VENUE_FA[v]} نیامد — جهش حجم نسبی نامعلوم")
        return btc_frames[v]

    rows = []
    for i, s in enumerate(syms, 1):
        if i % 10 == 0:
            _log(f"     {i}/{len(syms)} ...")
        u = uni[s]
        try:
            met = flow_metrics(net, u, now, btc_for(u["venue"]))
        except Exception as exc:
            warns.append(f"{s}: سنجه جریان خطا داد — {type(exc).__name__}")
            continue
        met["vol_btc"] = r54(u["vol24"], btc_px)
        signs = flow_signs(met)
        if signs:
            rows.append(dict(u, metrics=met, signs=signs, labels=list(u["labels"]),
                             lbank=lbank_label(s, m["lbank"])))
    _log(f"[۲] از دروازه جریان گذشت: {len(rows)} — سطح و ستاپ روزانه")
    btc = None
    n_fail = len(R.FAILURES)
    if rows:
        bd = daily_candles(net, "BTC", "okx")
        btc = None if bd is None else bd[bd["confirm"] == 1].reset_index(drop=True)
    for r in rows:
        try:
            st = structure(net, r, btc)
        except Exception as exc:
            st = {"d_sup": None, "d_res": None, "setups": [], "rs7": None, "rs30": None,
                  "labels": [f"سطح و ستاپ خطا داد — {type(exc).__name__}"]}
        r.update(d_sup=st["d_sup"], d_res=st["d_res"], setups=st["setups"],
                 support=st.get("support"), resistance=st.get("resistance"),
                 level_verdict=st.get("level_verdict"), levels=st.get("levels") or [],
                 atr_d=st.get("atr_d"))
        r["metrics"].update(rs7=st["rs7"], rs30=st["rs30"])
        r["labels"] += st["labels"] + flow_labels(r)
    warns += [f"radar_fetch3: {x}" for x in R.FAILURES[n_fail:][:10]]
    sec = rank(rows)
    _log("[۳] وتوی آزادسازی ...")
    vnotes = apply_veto(sec, veto_fn, net, now)
    budget = budget_fn(ticker_prices(m)) if budget_fn else None
    for k in ("long", "short"):
        for e in sec[k]:
            e["card"] = make_card(e, budget)
    prices = {s: {"price": u["price"], "venue": u["venue"]} for s, u in sorted(uni.items())}
    return {"uni": uni, "rows": rows, "sections": sec, "warnings": warns, "veto_notes": vnotes,
            "budget": budget, "prices": prices}


def main(argv=None, get=None, now: datetime | None = None, veto=None, history=None,
         sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(description="اسکنر پامپ — نشست ۹ رادار ۷")
    ap.add_argument("--min-vol", type=float, default=MIN_VOL_USD, dest="min_vol",
                    help="کف حجم ۲۴ ساعته یک صرافی، دلار")
    ap.add_argument("--out", default="reports/PUMP.md", help="گزارش مارک‌داون — فایل، نه پوشه")
    ap.add_argument("--json", default="pump.json", help="خروجی ماشین‌خوان — فایل")
    ap.add_argument("--ledger", default="pump_ledger.json", help="دفتر نامزد نشست ۱۳ — فایل")
    ap.add_argument("--no-ledger", action="store_true", dest="no_ledger")
    ap.add_argument("--holdings", default="holdings.json", help="سرمایه — فقط خواندن")
    ap.add_argument("--regime-file", default="regime.json", dest="regime_file",
                    help="باند رژیم — فقط خواندن")
    ap.add_argument("--limit", type=int, default=0, help="فقط برای اشکال‌زدایی: سقف نماد")
    ap.add_argument("--line", help="یک خط ساده برای پیام تلگرام — فایل")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)

    # ک۱۴: مسیر خروجی فایل است. پوشه هم‌نام یعنی خطای صریح، نه فایل داخل پوشه.
    for p in (a.out, a.json, a.line, None if a.no_ledger else a.ledger):
        if p and Path(p).is_dir():
            _log(f"⛔ مسیر خروجی پوشه است، نه فایل: {p}")
            return 2

    now = (now or datetime.now(UTC)).astimezone(UTC)
    if get is None:
        import requests
        sess = requests.Session()
        sess.headers["User-Agent"] = f"radar-pump/{VERSION}"
        get = sess.get
    net = Net(get, sleep=sleep)
    if veto is None:
        import radar_events as E
        veto = E.unlock_verdicts
    if history is None:
        import radar_history as H
        history = lambda s, tf, x, y: H.history(s, tf, x, y, get=net)   # noqa: E731

    t0 = time.monotonic()
    res = scan(net, now, a.min_vol, veto, a.limit,
               budget_fn=lambda px: load_budget(a.holdings, a.regime_file, px))
    if res is None:
        _log("⛔ تیکر نقدی هیچ صرافی نیامد — " + "؛ ".join(net.errors[:4]))
        return 3
    res.update(generated=now.strftime("%Y-%m-%d %H:%M UTC"), min_vol=a.min_vol,
               universe_n=len(res["uni"]), gate_n=len(res["rows"]))
    res["warnings"] += [f"درخواست ناموفق: {e}" for e in net.errors[:10]]

    led_notes: list[str] = []
    if not a.no_ledger:
        led = load_ledger(a.ledger)
        led_notes = ledger_fill(led, now, history)
        ledger_add(led, res["rows"], res["sections"], now)
        # عکس کنترل: قیمت همه نمادهای جهان بازار، تا نشست ۱۳ نامزد را با غیرنامزد بسنجد
        led.setdefault("controls", []).append({"at": iso(now), "prices": res["prices"]})
        led["updated"] = iso(now)
        _write(a.ledger, json.dumps(_clean(led), ensure_ascii=False, indent=1))
    res["warnings"] += led_notes[:10]
    res["requests"] = dict(net.count)
    res["elapsed_s"] = time.monotonic() - t0

    sec = res["sections"]
    out = {"version": VERSION, "framework": R.FRAMEWORK, "generated": iso(now),
           "status": UNTESTED,
           "note": "مجوز ورود نیست. هر نامزد مال دفتر معامله است، زیر سقف ریسک رژیم.",
           "thresholds": {"min_vol_usd": a.min_vol, "z_min": Z_MIN, "oi24_min": OI24_MIN,
                          "ratio_mult": RATIO_MULT, "late_atr": LATE_ATR,
                          "new_listing_days": NEW_LISTING_DAYS,
                          "fresh_venue_days": FRESH_VENUE_DAYS,
                          "crowd_funding_abs": CROWD_FUNDING_ABS,
                          "lev_funding_8h": LEV_FUNDING_8H, "abnormal_k": ABNORMAL_K,
                          "post_pump_rs7": POST_PUMP_RS7, "oi_usd_min": OI_USD_MIN,
                          "min_rr": MIN_RR, "rt_cost": RT_COST},
           "budget": {k: (res["budget"] or {}).get(k) for k in ("total", "free_pct", "note")},
           "cards_n": sum(1 for e in sec["long"] + sec["short"] if (e.get("card") or {}).get("ok")),
           "universe_n": res["universe_n"], "gate_n": res["gate_n"],
           "candidates": [e["symbol"] for e in sec["long"] + sec["short"]],
           "sections": sec, "requests": res["requests"],
           "elapsed_s": round(res["elapsed_s"], 1), "warnings": res["warnings"]}
    prev_pulse = []
    if Path(a.json).is_file():
        try:
            prev_pulse = (json.loads(Path(a.json).read_text(encoding="utf-8")).get("pulse")
                          or {}).get("items") or []
        except ValueError:
            res["warnings"].append("pump.json پیشین خوانا نبود — بخش pulse از نو")
    out["pulse"] = {"max": PULSE_MAX, "ttl_days": PULSE_TTL_DAYS,
                    "items": pulse_merge(prev_pulse, pulse_picks(sec), now)}
    _write(a.json, json.dumps(_clean(out), ensure_ascii=False, indent=1))
    if a.line:
        _write(a.line, telegram_line(sec) + "\n")
    md = render_md(res)
    if a.stdout:
        print(md)
    _write(a.out, md)
    _log(f"✅ {a.out} و {a.json} — {res['elapsed_s']:.0f} ثانیه، درخواست: {res['requests']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
