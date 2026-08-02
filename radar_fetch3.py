#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_fetch3.py — واکشی چند-صرافی + ماکرو رسمی، برای رادار ۵.۲
=========================================================

هدف: تولید یک گزارش مارک‌داون که مستقیم در گفت‌وگو با کلاود چسبانده می‌شود.

اصل حاکم بر کل این فایل (قانون مادر رادار):
    هرگز عدد نساز. اگر منبعی جواب نداد، بنویس «داده ندارم».
    هیچ مقدار پیش‌فرض، تخمینی یا جایگزینی جای داده واقعی نمی‌نشیند.

استفاده:
    python radar_fetch3.py ONDO --balance 800
    python radar_fetch3.py ONDO --venues okx,binance,bybit,gate --balance 800
    python radar_fetch2.py BTC  --balance 800 --profile position
    python radar_fetch2.py SOL  --macro-event 2026-07-29   # لنگر ج پروفایل حجم

نصب:
    pip install requests pandas numpy

منابع (همه رایگان و بدون کلید مگر خلافش ذکر شود):
    OKX            کندل، نرخ تأمین مالی، بهره باز، نسبت لانگ/شورت، حجم تیکر
    CoinGecko      تسلط بیت‌کوین، ارزش کل بازار، عرضه، ارزش رقیق‌شده
    Alternative.me شاخص ترس و طمع
    DefiLlama      عرضه استیبل‌کوین، ارزش کل قفل‌شده، تقویم آزادسازی توکن
    Coinglass      اختیاری، فقط با کلید در متغیر محیطی COINGLASS_API_KEY
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests

UTC = timezone.utc
VERSION = "3.2"

# ═══════════════════════════════════════════════════════════════════
#  لایه ۰ — زیرساخت شبکه
# ═══════════════════════════════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "radar-fetch/3.2", "Accept": "application/json"})

# ── کلید کوین‌گکو (اختیاری). بدون کلید حدود ۵ تا ۱۵ درخواست در دقیقه،
#    با کلید رایگان Demo حدود ۳۰. برای اسکن ۱۳ کوین تفاوت محسوس است.
CG_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
CG_PRO = os.environ.get("COINGECKO_PRO", "").strip().lower() in ("1", "true", "yes")
CG_BASE = ("https://pro-api.coingecko.com/api/v3" if (CG_KEY and CG_PRO)
           else "https://api.coingecko.com/api/v3")
if CG_KEY:
    SESSION.headers.update(
        {"x-cg-pro-api-key" if CG_PRO else "x-cg-demo-api-key": CG_KEY})

# هر منبعی که شکست بخورد اینجا ثبت می‌شود و در گزارش نهایی می‌آید.
FAILURES: list[str] = []


def http_get(url: str, params: dict | None = None, timeout: int = 20,
             retries: int = 3, label: str = "") -> Any | None:
    """
    درخواست GET با تلاش مجدد. در صورت شکست None برمی‌گرداند — هرگز داده جعلی.
    """
    tag = label or url
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 451:
                FAILURES.append(f"{tag}: کد ۴۵۱ — دسترسی از این موقعیت جغرافیایی مسدود است")
                return None
            if r.status_code == 429:
                time.sleep(2 * attempt)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt == retries:
                FAILURES.append(f"{tag}: {type(exc).__name__} — {str(exc)[:120]}")
                return None
            time.sleep(1.2 * attempt)
    return None


def http_text(url: str, params: dict | None = None, timeout: int = 25,
              retries: int = 2, label: str = "") -> str | None:
    """دریافت متن خام — برای CSV فدرال‌رزرو که کلید لازم ندارد."""
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            if attempt == retries:
                FAILURES.append(f"{label or url}: {type(exc).__name__}")
                return None
            time.sleep(1.0 * attempt)
    return None


def okx_get(path: str, params: dict | None = None, label: str = "") -> list | None:
    """پوشش اختصاصی OKX — ساختار پاسخ آن همیشه {code, msg, data} است."""
    js = http_get(f"https://www.okx.com{path}", params, label=label or path)
    if not js:
        return None
    if str(js.get("code")) != "0":
        FAILURES.append(f"{label or path}: OKX code={js.get('code')} msg={js.get('msg')}")
        return None
    return js.get("data") or []


# ═══════════════════════════════════════════════════════════════════
#  لایه ۱ — ساختار نتیجه
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Field:
    """هر عدد در گزارش با مهر زمانی و منبع می‌آید. قانون تازگی داده."""
    value: Any = None
    source: str = ""
    ts: datetime | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None

    def age_hours(self) -> float | None:
        if self.ts is None:
            return None
        return (datetime.now(UTC) - self.ts).total_seconds() / 3600

    def render(self, fmt: str = "{}") -> str:
        if not self.ok:
            return "**داده ندارم**"
        try:
            body = fmt.format(self.value)
        except Exception:
            body = str(self.value)
        age = self.age_hours()
        if age is not None and age > 0.05:
            body += f"  _(عمر داده: {age:.1f} ساعت)_"
        return body


@dataclass
class Bundle:
    symbol: str = ""
    balance: float = 0.0
    profile: str = "trade"
    generated: datetime = field(default_factory=lambda: datetime.now(UTC))
    candles: dict[str, pd.DataFrame] = field(default_factory=dict)
    pair_btc: pd.DataFrame | None = None
    flow: dict[str, Field] = field(default_factory=dict)
    macro: dict[str, Field] = field(default_factory=dict)
    fundamental: dict[str, Field] = field(default_factory=dict)
    derivatives: dict[str, Field] = field(default_factory=dict)
    vprofile: dict[str, dict] = field(default_factory=dict)
    tests: list[tuple[str, bool, str]] = field(default_factory=list)
    venue_order: list = field(default_factory=list)
    candle_venue: str | None = None
    v_funding: dict = field(default_factory=dict)
    v_oi: dict = field(default_factory=dict)
    v_pos: dict = field(default_factory=dict)
    f_agg: dict = field(default_factory=dict)
    fred: dict = field(default_factory=dict)
    venue_dead: list = field(default_factory=list)
    fib: dict | None = None


# ═══════════════════════════════════════════════════════════════════
#  لایه ۲ — OKX: کندل با صفحه‌بندی
# ═══════════════════════════════════════════════════════════════════

BAR_MAP = {"1D": "1D", "4H": "4H", "1W": "1W"}


def okx_candles(inst_id: str, bar: str, want: int = 1000) -> pd.DataFrame | None:
    """
    کندل‌های OKX.

    راستی‌آزمایی ۲ (ترتیب کندل): OKX همیشه از جدید به قدیم می‌دهد.
    اینجا صریحاً بر اساس مهر زمانی صعودی مرتب می‌شود و در تست‌ها بررسی می‌گردد.
    ستون confirm==1 یعنی کندل بسته شده. کندل باز آخر جدا نگه داشته می‌شود.
    """
    rows: list[list] = []
    cursor: str | None = None
    guard = 0

    while len(rows) < want and guard < 20:
        guard += 1
        params = {"instId": inst_id, "bar": bar, "limit": "100"}
        if cursor:
            params["after"] = cursor          # after در OKX یعنی «قدیمی‌تر از این»
            path = "/api/v5/market/history-candles"
        else:
            path = "/api/v5/market/candles"
        batch = okx_get(path, params, label=f"کندل {inst_id} {bar}")
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0]
        time.sleep(0.15)

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"
    ])
    for c in ["open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["confirm"] = pd.to_numeric(df["confirm"], errors="coerce")
    df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms", utc=True)

    # ─── ترتیب صعودی + حذف تکراری. این خط قلب راستی‌آزمایی ۲ است.
    df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════════
#  لایه ۳ — اندیکاتورها (محاسبه محلی، نه خواندن از چارت)
# ═══════════════════════════════════════════════════════════════════

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI استاندارد وایلدر — هموارسازی RMA، نه SMA."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / n, adjust=False).mean()
    al = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0)


def atr_wilder(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR استاندارد وایلدر با هموارسازی RMA — همان تنظیمی که در چارت خواستیم."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def macd(close: pd.Series, fast=12, slow=26, sig=9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    signal = ema(line, sig)
    return pd.DataFrame({"macd": line, "signal": signal, "hist": line - signal})


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi14"] = rsi_wilder(df["close"], 14)
    df["atr14"] = atr_wilder(df, 14)
    m = macd(df["close"])
    df["macd"], df["macd_sig"], df["macd_hist"] = m["macd"], m["signal"], m["hist"]
    df["vol_ma20"] = df["vol"].rolling(20).mean()
    return df


# ═══════════════════════════════════════════════════════════════════
#  لایه ۴ — پروفایل حجم بازه ثابت + سه لنگر (بند ۵.۱ رادار)
# ═══════════════════════════════════════════════════════════════════

def pivots(df: pd.DataFrame, left: int = 5, right: int = 5) -> tuple[list[int], list[int]]:
    """تشخیص سقف و کف ساختاری با روش فراکتال ساده."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    for i in range(left, len(df) - right):
        if h[i] == max(h[i - left:i + right + 1]):
            highs.append(i)
        if l[i] == min(l[i - left:i + right + 1]):
            lows.append(i)
    return highs, lows


def volume_profile(df: pd.DataFrame, i0: int, i1: int, bins: int = 60) -> dict | None:
    """
    پروفایل حجم بازه ثابت (Fixed Range).
    حجم هر کندل به‌طور یکنواخت روی دامنه کف تا سقف همان کندل پخش می‌شود.
    خروجی: نقطه کنترل و مرزهای ناحیه ارزش ۷۰ درصدی.
    """
    seg = df.iloc[i0:i1 + 1]
    if len(seg) < 5:
        return None
    lo, hi = float(seg["low"].min()), float(seg["high"].max())
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return None

    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    hist = np.zeros(bins)

    for _, row in seg.iterrows():
        cl, ch, v = float(row["low"]), float(row["high"]), float(row["vol"])
        if not math.isfinite(v) or v <= 0:
            continue
        if ch <= cl:
            hist[min(np.searchsorted(edges, cl) - 1, bins - 1)] += v
            continue
        lo_b = max(np.searchsorted(edges, cl, side="right") - 1, 0)
        hi_b = min(np.searchsorted(edges, ch, side="left"), bins - 1)
        n = hi_b - lo_b + 1
        if n <= 0:
            continue
        hist[lo_b:hi_b + 1] += v / n

    total = hist.sum()
    if total <= 0:
        return None

    poc_i = int(hist.argmax())
    # گسترش دوطرفه از نقطه کنترل تا رسیدن به ۷۰٪ حجم — روش استاندارد ناحیه ارزش
    lo_i = hi_i = poc_i
    acc = hist[poc_i]
    while acc < 0.70 * total and (lo_i > 0 or hi_i < bins - 1):
        down = hist[lo_i - 1] if lo_i > 0 else -1.0
        up = hist[hi_i + 1] if hi_i < bins - 1 else -1.0
        if up >= down:
            hi_i += 1
            acc += max(up, 0)
        else:
            lo_i -= 1
            acc += max(down, 0)

    return {
        "from": str(seg["ts"].iloc[0].date()),
        "to": str(seg["ts"].iloc[-1].date()),
        "candles": len(seg),
        "poc": round(float(centers[poc_i]), 8),
        "val": round(float(edges[lo_i]), 8),
        "vah": round(float(edges[hi_i + 1]), 8),
        "range_low": round(lo, 8),
        "range_high": round(hi, 8),
    }


def vp_by_time(df_fine: pd.DataFrame, t0, t1, bins: int = 60) -> dict | None:
    """پروفایل حجم روی بازه زمانی — با کندل ریزتر دقت بیشتری می‌دهد."""
    m = (df_fine["ts"] >= t0) & (df_fine["ts"] <= t1)
    idx = df_fine.index[m]
    if len(idx) < 5:
        return None
    return volume_profile(df_fine, int(idx[0]), int(idx[-1]), bins)


def three_anchors(df: pd.DataFrame, macro_event: str | None,
                  df_fine: pd.DataFrame | None = None) -> dict[str, dict]:
    """
    سه لنگر اجباری رادار ۵.۲:
      الف — از آخرین کف ساختاری تا آخرین سقف ساختاری موج جاری
      ب  — کل محدوده تراکم قبلی، از شکست تا شکست
      ج  — از آخرین رویداد ماکرو تاریخ‌دار تا اکنون
    """
    out: dict[str, dict] = {}
    ph, pl = pivots(df, 5, 5)
    n = len(df)

    # ── لنگر الف — موج جاری
    # سه قید هم‌زمان:
    #   ۱) سقف مرجع باید **جدیدترین** سقف ساختاری باشد؛ لنگر «موج جاری» است.
    #   ۲) پنجره باید دست‌کم MIN_BARS کندل باشد؛ پروفایل حجم روی ۳ کندل
    #      عدد می‌دهد ولی نمونه آماری ندارد.
    #   ۳) پنجره نباید از MAX_BARS کهنه‌تر شود؛ لنگری که شش ماه پیش شروع
    #      می‌شود دیگر «موج جاری» نیست.
    # روش: سقف جدید را نگه دار، از میان **کف‌ها** عقب برو تا طول کافی شود.
    MIN_BARS, MAX_BARS = 20, 120
    if ph or pl:
        # اگر هیچ سقف ساختاری نباشد (روند بی‌وقفه یا داده کم)، آخرین کندل
        # مرجع می‌شود. بدون این، لنگر اصلاً ساخته نمی‌شد و پروفایل حجم
        # بی‌صدا غایب می‌ماند — بدترین حالت، چون کاربر متوجه نمی‌شود.
        last_high = ph[-1] if ph else n - 1
        lows_before = [i for i in pl if i < last_high]
        start = None
        for lo in reversed(lows_before):        # از نزدیک‌ترین کف به عقب
            span = last_high - lo + 1
            if span >= MIN_BARS:
                start = lo if span <= MAX_BARS else max(0, last_high - MAX_BARS + 1)
                break
        if start is None:                       # هیچ کفی به حد نصاب نرسید
            start = max(0, last_high - MIN_BARS + 1)
        if last_high - start + 1 >= 5:
            t0, t1 = df["ts"].iloc[start], df["ts"].iloc[last_high]
            span_d = int(last_high - start + 1)
            # اگر بازه از دامنه داده ریزدانه بیرون بزند، ریزدانه بی‌صدا
            # پنجره را می‌بُرد. در آن حالت روزانه مرجع می‌شود.
            vp = None
            if df_fine is not None and len(df_fine) and df_fine["ts"].iloc[0] <= t0:
                vp = vp_by_time(df_fine, t0, t1)
                if vp:
                    vp["grain"] = "چهارساعته"
            if vp is None:
                vp = volume_profile(df, start, last_high)
                if vp:
                    vp["grain"] = "روزانه"
            if vp:
                vp["label"] = "الف — کف ساختاری تا سقف ساختاری موج جاری"
                vp["span_days"] = span_d
                out["A"] = vp

    # ── لنگر ب: محدوده تراکم قبلی. کم‌نوسان‌ترین پنجره ۶۰ کندلی پیش از موج جاری.
    win = 60
    start_search = max(0, n - 400)
    end_search = out.get("A", {}).get("_i0", None)
    # لنگر ب باید **قبل از** موج جاری باشد؛ نقطه شروع لنگر الف مرز آن است.
    a_start_ts = out.get("A", {}).get("from")
    if a_start_ts:
        idx_ = df.index[df["ts"] <= pd.Timestamp(a_start_ts, tz="UTC")]
        hard_end = int(idx_[-1]) if len(idx_) else n - win - 1
    else:
        hard_end = n - win - 1
    best_i, best_score = None, None
    for i in range(start_search, max(start_search + 1, hard_end - win)):
        seg = df.iloc[i:i + win]
        rng = float(seg["high"].max() - seg["low"].min())
        mid = float(seg["close"].median())
        if mid <= 0 or not math.isfinite(rng):
            continue
        score = rng / mid                       # دامنه نسبی، هرچه کمتر یعنی متراکم‌تر
        if best_score is None or score < best_score:
            best_score, best_i = score, i
    if best_i is not None:
        t0, t1 = df["ts"].iloc[best_i], df["ts"].iloc[best_i + win - 1]
        vp = (vp_by_time(df_fine, t0, t1) if df_fine is not None else None) \
             or volume_profile(df, best_i, best_i + win - 1)
        if vp:
            vp["label"] = "ب — محدوده تراکم قبلی (خودکار: متراکم‌ترین پنجره ۶۰ کندلی)"
            vp["grain"] = "چهارساعته" if df_fine is not None else "روزانه"
            out["B"] = vp

    # ── لنگر ج
    if macro_event:
        try:
            ev = pd.Timestamp(macro_event, tz="UTC")
            idx = df.index[df["ts"] >= ev]
            if len(idx) >= 5:
                vp = (vp_by_time(df_fine, ev, df["ts"].iloc[-1]) if df_fine is not None
                      else None) or volume_profile(df, int(idx[0]), n - 1)
                if vp:
                    vp["label"] = f"ج — از رویداد ماکرو {macro_event} تا اکنون"
                    vp["grain"] = "چهارساعته" if df_fine is not None else "روزانه"
                    out["C"] = vp
        except Exception as exc:
            FAILURES.append(f"لنگر ج: تاریخ نامعتبر {macro_event} — {exc}")
    return out


FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]


def fibonacci(df: pd.DataFrame, lookback: int = 180) -> dict | None:
    """
    اصلاح فیبوناچی روی آخرین نوسان ساختاری معتبر.

    ⚠️ طبق فهرست رد‌شده‌های رادار، فیبوناچی **هرگز منبع اصلی سطح نیست**.
    مبنای نظری ندارد و کارکردش فقط هماهنگی جمعی معامله‌گران است.
    خروجی این تابع تنها به‌عنوان **لایه دوم تأیید** مصرف می‌شود:
    اگر سطح فیبوناچی با نقطه کنترل پروفایل حجم یکی شد، اعتبار سطح بالا می‌رود.
    در تضاد، **پروفایل حجم برنده است** چون از داده معامله واقعی می‌آید.
    """
    if df is None or len(df) < 40:
        return None
    seg = df.iloc[-min(lookback, len(df)):].reset_index(drop=True)
    hi_i = int(seg["high"].idxmax())
    lo_i = int(seg["low"].idxmin())
    hi, lo = float(seg["high"].iloc[hi_i]), float(seg["low"].iloc[lo_i])
    if hi <= lo:
        return None
    rng = hi - lo
    down = hi_i < lo_i          # سقف قبل از کف ← نوسان نزولی
    lvls = {}
    for f in FIB_LEVELS:
        # در نوسان نزولی، اصلاح از کف به بالا؛ در صعودی، از سقف به پایین
        lvls[f] = round(lo + rng * f if down else hi - rng * f, 8)
    price = float(df["close"].iloc[-1])
    nearest = min(lvls.items(), key=lambda kv: abs(kv[1] - price))
    return {
        "direction": "نزولی" if down else "صعودی",
        "swing_high": round(hi, 8), "swing_low": round(lo, 8),
        "high_date": str(seg["ts"].iloc[hi_i].date()),
        "low_date": str(seg["ts"].iloc[lo_i].date()),
        "levels": lvls,
        "nearest": {"ratio": nearest[0], "price": nearest[1],
                    "distance_pct": round(100 * (price - nearest[1]) / nearest[1], 2)},
    }


def fib_vp_confluence(fib: dict | None, anchors: dict, atr: float | None) -> str:
    """
    آزمون هم‌نشینی: آیا سطح فیبوناچی با نقطه کنترل پروفایل حجم یکی می‌شود؟
    آستانه: نصف ATR روزانه — همان معیار آزمون هم‌گرایی لنگرها.
    """
    if not fib or not anchors or not atr:
        return "قابل ارزیابی نیست"
    pocs = [(k, a["poc"]) for k, a in anchors.items() if a.get("poc")]
    if not pocs:
        return "نقطه کنترلی برای مقایسه نیست"
    hits = []
    for ratio, lvl in fib["levels"].items():
        for k, poc in pocs:
            if abs(lvl - poc) < atr / 2:
                hits.append(f"فیبو {ratio} ({lvl:.6f}) با نقطه کنترل لنگر {k} ({poc:.6f})")
    if hits:
        return "**هم‌نشینی دارد** — " + "؛ ".join(hits[:3])
    return "هم‌نشینی ندارد — پروفایل حجم مرجع می‌ماند، فیبوناچی امتیاز نمی‌گیرد"


def convergence(anchors: dict[str, dict], atr_daily: float | None) -> tuple[str, str]:
    """آزمون هم‌گرایی: نقاط کنترل هر سه لنگر باید در فاصله کمتر از نصف ATR روزانه باشند."""
    pocs = [a["poc"] for a in anchors.values() if a.get("poc")]
    if len(pocs) < 2 or not atr_daily:
        return ("نامشخص", "لنگر کافی یا ATR در دسترس نیست")
    spread = max(pocs) - min(pocs)
    limit = atr_daily / 2
    if spread < limit:
        return ("هم‌گرا", f"پراکندگی {spread:.6f} < نصف ATR {limit:.6f} ← سطح معتبر")
    return ("پراکنده", f"پراکندگی {spread:.6f} ≥ نصف ATR {limit:.6f} ← حکم صبر یا بدون ورود")




# ══════════ آداپتورهای چند-صرافی و ماکرو رسمی ══════════


# ═══════════════════ آداپتورهای صرافی ═══════════════════
# هر آداپتور برمی‌گرداند: dict یا None. هرگز عدد جعلی.

class Venue:
    name = "base"
    def spot(self, base: str) -> str: ...
    def perp(self, base: str) -> str: ...
    def candles(self, base, bar, want, http): return None
    def funding(self, base, http): return None
    def oi(self, base, price, http): return None
    def positioning(self, base, http): return None


BAR = {  # نگاشت تایم‌فریم برای هر صرافی
    "okx":     {"1D": "1D",  "4H": "4H",  "1W": "1W"},
    "binance": {"1D": "1d",  "4H": "4h",  "1W": "1w"},
    "bybit":   {"1D": "D",   "4H": "240", "1W": "W"},
    "gate":    {"1D": "1d",  "4H": "4h",  "1W": "7d"},
    "kucoin":  {"1D": "1day","4H": "4hour","1W": "1week"},
}


def _df(rows, cols, ms=True) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=cols)
    for c in df.columns:
        if c != "ts":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms" if ms else "s", utc=True)
    df["confirm"] = 1
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


class OKX(Venue):
    name = "okx"
    B = "https://www.okx.com"
    def spot(self, b): return f"{b}-USDT"
    def perp(self, b): return f"{b}-USDT-SWAP"

    def _g(self, http, path, params, label):
        js = http(f"{self.B}{path}", params, label=f"[okx] {label}")
        if not js or str(js.get("code")) != "0":
            return None
        return js.get("data") or []

    def candles(self, base, bar, want, http):
        rows, cur, guard = [], None, 0
        while len(rows) < want and guard < 15:
            guard += 1
            p = {"instId": self.spot(base), "bar": BAR["okx"][bar], "limit": "100"}
            path = "/api/v5/market/candles"
            if cur:
                p["after"] = cur; path = "/api/v5/market/history-candles"
            d = self._g(http, path, p, f"کندل {bar}")
            if not d: break
            rows += d; cur = d[-1][0]; time.sleep(.12)
        if not rows: return None
        df = _df([r[:6] for r in rows], ["ts","open","high","low","close","vol"])
        return df

    def funding(self, base, http):
        d = self._g(http, "/api/v5/public/funding-rate", {"instId": self.perp(base)}, "فاندینگ")
        if not d: return None
        x = d[0]
        try:
            r  = float(x["fundingRate"]); t0 = int(x["fundingTime"]); t1 = int(x["nextFundingTime"])
        except Exception: return None
        iv = (t1 - t0) / 3_600_000
        if not (0.5 <= iv <= 24): return None
        return {"rate": r, "interval_h": iv, "rate_8h": r * (8 / iv),
                "ts": datetime.fromtimestamp(t0/1000, UTC)}

    def oi(self, base, price, http):
        inst = self._g(http, "/api/v5/public/instruments",
                       {"instType":"SWAP","instId":self.perp(base)}, "مشخصات")
        ctv = float(inst[0]["ctVal"]) if inst else None
        d = self._g(http, "/api/v5/public/open-interest",
                    {"instType":"SWAP","instId":self.perp(base)}, "بهره باز")
        if not d: return None
        x = d[0]
        oi_c = float(x.get("oi", "nan")); oi_b = float(x.get("oiCcy") or "nan")
        p1 = oi_c*ctv if (ctv and math.isfinite(oi_c)) else float("nan")
        chosen = oi_b if math.isfinite(oi_b) else p1
        if not math.isfinite(chosen): return None
        agree = math.isfinite(p1) and math.isfinite(oi_b) and oi_b>0 and abs(p1-oi_b)/oi_b < .02
        h = self._g(http, "/api/v5/rubik/stat/contracts/open-interest-volume",
                    {"ccy": base, "period":"1H"}, "تاریخچه بهره باز")
        chg = None
        if h and len(h) >= 25:
            rs = sorted(h, key=lambda r:int(r[0]))
            a, b_ = float(rs[-25][1]), float(rs[-1][1])
            if a>0: chg = 100*(b_-a)/a
        return {"base": chosen, "usd": chosen*price if price else None,
                "chg24": chg, "cross_check": agree, "ts": datetime.now(UTC)}

    def positioning(self, base, http):
        d = self._g(http, "/api/v5/rubik/stat/contracts/long-short-account-ratio",
                    {"ccy": base, "period":"1H"}, "لانگ/شورت")
        if not d: return None
        rs = sorted(d, key=lambda r:int(r[0]))
        return {"global_account": float(rs[-1][1]), "ts": datetime.now(UTC)}


class Binance(Venue):
    name = "binance"
    # api.binance.com از آمریکا مسدود است (کد ۴۵۱). دامنه data-api فقط
    # داده عمومی بازار می‌دهد و معمولاً مسدود نیست. برای کندل امتحان می‌شود.
    S, F = "https://api.binance.com", "https://fapi.binance.com"
    S_ALT = "https://data-api.binance.vision"
    def spot(self, b): return f"{b}USDT"
    perp = spot

    def candles(self, base, bar, want, http):
        rows, end = [], None
        for _ in range(10):
            p = {"symbol": self.spot(base), "interval": BAR["binance"][bar],
                 "limit": min(1000, want)}
            if end: p["endTime"] = end
            d = http(f"{self.S}/api/v3/klines", p, label="[binance] کندل")
            if not d:
                d = http(f"{self.S_ALT}/api/v3/klines", p,
                         label="[binance] کندل (دامنه جایگزین)")
            if not d: break
            rows = d + rows
            end = int(d[0][0]) - 1
            if len(rows) >= want or len(d) < p["limit"]: break
            time.sleep(.15)
        if not rows: return None
        return _df([[r[0],r[1],r[2],r[3],r[4],r[5]] for r in rows],
                   ["ts","open","high","low","close","vol"])

    def funding(self, base, http):
        d = http(f"{self.F}/fapi/v1/premiumIndex", {"symbol": self.perp(base)},
                 label="[binance] فاندینگ")
        if not d or "lastFundingRate" not in d: return None
        info = http(f"{self.F}/fapi/v1/fundingInfo", label="[binance] بازه فاندینگ")
        iv = 8.0
        if isinstance(info, list):
            for i in info:
                if i.get("symbol") == self.perp(base):
                    iv = float(i.get("fundingIntervalHours", 8)); break
        r = float(d["lastFundingRate"])
        return {"rate": r, "interval_h": iv, "rate_8h": r*(8/iv), "ts": datetime.now(UTC)}

    def oi(self, base, price, http):
        d = http(f"{self.F}/fapi/v1/openInterest", {"symbol": self.perp(base)},
                 label="[binance] بهره باز")
        if not d or "openInterest" not in d: return None
        b_ = float(d["openInterest"])
        h = http(f"{self.F}/futures/data/openInterestHist",
                 {"symbol": self.perp(base), "period": "1h", "limit": 30},
                 label="[binance] تاریخچه بهره باز")
        chg = None
        if isinstance(h, list) and len(h) >= 25:
            a, c = float(h[-25]["sumOpenInterest"]), float(h[-1]["sumOpenInterest"])
            if a>0: chg = 100*(c-a)/a
        return {"base": b_, "usd": b_*price if price else None, "chg24": chg,
                "cross_check": None, "ts": datetime.now(UTC)}

    def positioning(self, base, http):
        """تنها صرافی که تفکیک نهنگ و خرده‌فروش را رایگان می‌دهد."""
        out, sym = {}, self.perp(base)
        for key, ep in [("global_account","globalLongShortAccountRatio"),
                        ("top_account","topLongShortAccountRatio"),
                        ("top_position","topLongShortPositionRatio")]:
            d = http(f"{self.F}/futures/data/{ep}",
                     {"symbol": sym, "period":"1h", "limit":30}, label=f"[binance] {key}")
            if isinstance(d, list) and d:
                out[key] = float(d[-1]["longShortRatio"])
                if len(d) >= 25: out[key+"_24h"] = float(d[-25]["longShortRatio"])
        d = http(f"{self.F}/futures/data/takerlongshortRatio",
                 {"symbol": sym, "period":"1h", "limit":30}, label="[binance] تیکر")
        if isinstance(d, list) and d:
            out["taker_buy_sell"] = float(d[-1]["buySellRatio"])
        return out or None


class Bybit(Venue):
    name = "bybit"
    B = "https://api.bybit.com"
    def spot(self, b): return f"{b}USDT"
    perp = spot

    def _g(self, http, path, p, label):
        js = http(f"{self.B}{path}", p, label=f"[bybit] {label}")
        if not js or js.get("retCode") != 0: return None
        return js.get("result") or {}

    def candles(self, base, bar, want, http):
        r = self._g(http, "/v5/market/kline",
                    {"category":"spot","symbol":self.spot(base),
                     "interval":BAR["bybit"][bar],"limit":1000}, f"کندل {bar}")
        if not r or not r.get("list"): return None
        return _df([x[:6] for x in r["list"]], ["ts","open","high","low","close","vol"])

    def funding(self, base, http):
        r = self._g(http, "/v5/market/tickers",
                    {"category":"linear","symbol":self.perp(base)}, "تیکر")
        if not r or not r.get("list"): return None
        x = r["list"][0]
        try: rate = float(x["fundingRate"])
        except Exception: return None
        inst = self._g(http, "/v5/market/instruments-info",
                       {"category":"linear","symbol":self.perp(base)}, "مشخصات")
        iv = 8.0
        if inst and inst.get("list"):
            iv = float(inst["list"][0].get("fundingInterval", 480)) / 60
        return {"rate": rate, "interval_h": iv, "rate_8h": rate*(8/iv),
                "ts": datetime.now(UTC), "oi_hint": x.get("openInterest")}

    def oi(self, base, price, http):
        r = self._g(http, "/v5/market/open-interest",
                    {"category":"linear","symbol":self.perp(base),
                     "intervalTime":"1h","limit":50}, "بهره باز")
        if not r or not r.get("list"): return None
        rs = sorted(r["list"], key=lambda z:int(z["timestamp"]))
        cur = float(rs[-1]["openInterest"]); chg = None
        if len(rs) >= 25:
            a = float(rs[-25]["openInterest"])
            if a>0: chg = 100*(cur-a)/a
        return {"base": cur, "usd": cur*price if price else None, "chg24": chg,
                "cross_check": None, "ts": datetime.now(UTC)}

    def positioning(self, base, http):
        r = self._g(http, "/v5/market/account-ratio",
                    {"category":"linear","symbol":self.perp(base),
                     "period":"1h","limit":50}, "لانگ/شورت")
        if not r or not r.get("list"): return None
        x = sorted(r["list"], key=lambda z:int(z["timestamp"]))[-1]
        try:
            b_, s_ = float(x["buyRatio"]), float(x["sellRatio"])
            return {"global_account": b_/s_ if s_ else None, "ts": datetime.now(UTC)}
        except Exception: return None


class Gate(Venue):
    name = "gate"
    B = "https://api.gateio.ws/api/v4"
    def spot(self, b): return f"{b}_USDT"
    perp = spot

    def candles(self, base, bar, want, http):
        d = http(f"{self.B}/spot/candlesticks",
                 {"currency_pair": self.spot(base), "interval": BAR["gate"][bar],
                  "limit": min(1000, want)}, label=f"[gate] کندل {bar}")
        if not isinstance(d, list) or not d: return None
        # قالب گیت: [ts(s), quoteVol, close, high, low, open, baseVol, ...]
        rows = [[x[0], x[5], x[3], x[4], x[2], x[6] if len(x) > 6 else x[1]] for x in d]
        return _df(rows, ["ts","open","high","low","close","vol"], ms=False)

    def funding(self, base, http):
        d = http(f"{self.B}/futures/usdt/contracts/{self.perp(base)}",
                 label="[gate] قرارداد")
        if not isinstance(d, dict) or "funding_rate" not in d: return None
        try:
            r = float(d["funding_rate"]); iv = float(d.get("funding_interval", 28800))/3600
        except Exception: return None
        if not (0.5 <= iv <= 24): iv = 8.0
        return {"rate": r, "interval_h": iv, "rate_8h": r*(8/iv), "ts": datetime.now(UTC)}

    def _stats(self, base, http):
        return http(f"{self.B}/futures/usdt/contract_stats",
                    {"contract": self.perp(base), "interval": "1h", "limit": 30},
                    label="[gate] آمار قرارداد")

    def oi(self, base, price, http):
        d = self._stats(base, http)
        if not isinstance(d, list) or not d: return None
        rs = sorted(d, key=lambda z: z["time"])
        cur = float(rs[-1].get("open_interest") or 0)
        if cur <= 0: return None
        chg = None
        if len(rs) >= 25:
            a = float(rs[-25].get("open_interest") or 0)
            if a>0: chg = 100*(cur-a)/a
        return {"base": cur, "usd": cur*price if price else None, "chg24": chg,
                "cross_check": None, "ts": datetime.now(UTC)}

    def positioning(self, base, http):
        d = self._stats(base, http)
        if not isinstance(d, list) or not d: return None
        x = sorted(d, key=lambda z: z["time"])[-1]
        out = {}
        if x.get("lsr_account"):     out["global_account"] = float(x["lsr_account"])
        if x.get("top_lsr_account"): out["top_account"]    = float(x["top_lsr_account"])
        if x.get("top_lsr_size"):    out["top_position"]   = float(x["top_lsr_size"])
        if x.get("lsr_taker"):       out["taker_buy_sell"] = float(x["lsr_taker"])
        return out or None


VENUES = {"okx": OKX(), "binance": Binance(), "bybit": Bybit(), "gate": Gate()}
DEFAULT_ORDER = ["okx", "binance", "bybit", "gate"]


# ═══════════════════ ماکرو رسمی از فدرال‌رزرو سنت‌لوئیس ═══════════════════
# مسیر CSV بدون کلید کار می‌کند. کلید فقط پایداری را بهتر می‌کند.

FRED_SERIES = {
    "DGS2":       ("بازده ۲ ساله", "%"),
    "DGS10":      ("بازده ۱۰ ساله", "%"),
    "DGS30":      ("بازده ۳۰ ساله", "%"),
    "T10YIE":     ("نرخ سربه‌سر تورم ۱۰ ساله", "%"),
    "DFEDTARU":   ("سقف نرخ بهره فدرال", "%"),
    "DTWEXBGS":   ("شاخص دلار، سبد وسیع", "شاخص"),
    "WALCL":      ("دارایی کل فدرال‌رزرو", "میلیون دلار"),
    "RRPONTSYD":  ("ریپوی معکوس شبانه", "میلیارد دلار"),
    "WTREGEN":    ("حساب خزانه‌داری", "میلیارد دلار"),
    "M2SL":       ("عرضه پول M2", "میلیارد دلار"),
    "CPIAUCSL":   ("شاخص قیمت مصرف‌کننده", "شاخص"),
    "ICSA":       ("مدعیان اولیه بیکاری", "نفر"),
    "UNRATE":     ("نرخ بیکاری", "%"),
    "CIVPART":    ("نرخ مشارکت", "%"),
    "PAYEMS":     ("اشتغال غیرکشاورزی", "هزار نفر"),
}


def fred_series(sid: str, http_text) -> tuple[float, datetime, float | None] | None:
    """
    آخرین مقدار + تاریخ + مقدار ۳۰ روز قبل.
    مسیر fredgraph.csv کلید نمی‌خواهد — همیشه در دسترس.
    """
    txt = http_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                    label=f"[FRED] {sid}")
    if not txt:
        return None
    rows = []
    for line in txt.strip().split("\n")[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        v = parts[-1].strip()
        if v in ("", ".", "NA"):
            continue
        try:
            rows.append((parts[0].strip(), float(v)))
        except ValueError:
            continue
    if not rows:
        return None
    d, val = rows[-1]
    ts = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC)
    # ۳۰ روز تقویمی، نه ۳۰ ردیف. سری‌ها بسامد متفاوت دارند
    # (روزانه، هفتگی، ماهانه) و ۳۰ ردیف برای سری ماهانه یعنی ۳۰ ماه.
    target = ts - timedelta(days=30)
    prev = None
    for dd, vv in reversed(rows[:-1]):
        if datetime.strptime(dd, "%Y-%m-%d").replace(tzinfo=UTC) <= target:
            prev = vv
            break
    return val, ts, prev


def fetch_fred(http_text) -> dict:
    """
    ستون نقدینگی جهانی رادار — همان بخشی که تا امروز خالی می‌ماند.
    خروجی خام + سنجه‌های مشتق وصله ۵.۳ (فاصله سیاست از خنثی، شیب منحنی).
    """
    raw: dict[str, dict] = {}
    for sid in FRED_SERIES:
        r = fred_series(sid, http_text)
        if r:
            raw[sid] = {"value": r[0], "ts": r[1], "prev30": r[2],
                        "label": FRED_SERIES[sid][0], "unit": FRED_SERIES[sid][1]}
        time.sleep(.1)

    d: dict[str, Any] = {"raw": raw, "derived": {}}
    g = lambda k: raw[k]["value"] if k in raw else None

    y2, y10, y30 = g("DGS2"), g("DGS10"), g("DGS30")
    ffr, be10 = g("DFEDTARU"), g("T10YIE")

    def sane(v, lo, hi):
        return v if (v is not None and lo <= v <= hi) else None

    if y2 is not None and ffr is not None:
        d["derived"]["neutral_gap"] = {
            "value": sane(y2 - ffr, -5, 5),
            "label": "فاصله سیاست از خنثی (بازده ۲ ساله منهای سقف نرخ بهره)",
            "read": "مثبت یعنی سیاست دیگر انقباضی نیست" if y2 > ffr else "منفی یعنی واقعاً انقباضی"}
    if y30 is not None and y2 is not None:
        d["derived"]["curve_30_2"] = {
            "value": sane(y30 - y2, -5, 5), "label": "شیب منحنی ۳۰ منهای ۲",
            "read": "شیب مثبت" if y30 > y2 else "منحنی معکوس"}
    if y10 is not None and be10 is not None:
        d["derived"]["real_10y"] = {
            "value": sane(y10 - be10, -5, 8),
            "label": "بازده واقعی ۱۰ ساله (از نرخ سربه‌سر تورم، نه CPI)",
            "read": "مثبت — رقیب جدی دارایی بدون بازده" if y10 > be10 else "منفی"}

    # نقدینگی خالص — تله واحد: WALCL میلیون است، دو تای دیگر میلیارد
    w, rr, tga = g("WALCL"), g("RRPONTSYD"), g("WTREGEN")
    if None not in (w, rr, tga):
        # واحدها: WALCL و WTREGEN به میلیون دلار، RRPONTSYD به میلیارد دلار
        nl = w/1000.0 - rr - tga/1000.0
        plausible = 2000 < nl < 12000     # بازه تاریخی نقدینگی خالص، میلیارد دلار
        d["derived"]["net_liquidity"] = {
            "value": nl if plausible else None,
            "label": "نقدینگی خالص فدرال‌رزرو (میلیارد دلار)",
            "read": ("دارایی ÷۱۰۰۰ منهای ریپوی معکوس منهای خزانه‌داری ÷۱۰۰۰"
                     if plausible else
                     f"⚠️ عدد خام {nl:,.0f} خارج از بازه منطقی — احتمال تغییر واحد در منبع. رد شد")}
        pw  = raw.get("WALCL", {}).get("prev30")
        prr = raw.get("RRPONTSYD", {}).get("prev30")
        ptg = raw.get("WTREGEN", {}).get("prev30")
        if plausible and None not in (pw, prr, ptg):
            # هر سه جزء باید از ۳۰ روز قبل باشند، وگرنه فقط تغییر یک جزء را می‌سنجیم
            prev_nl = pw/1000.0 - prr - ptg/1000.0
            delta = nl - prev_nl
            pct = 100 * delta / prev_nl if prev_nl else 0.0
            if abs(pct) < 1.0:
                rd = f"{pct:+.2f}٪ — تقریباً ثابت، نه باد موافق نه مخالف"
            elif pct > 0:
                rd = f"{pct:+.2f}٪ — تزریق، باد موافق"
            else:
                rd = f"{pct:+.2f}٪ — انقباض، باد مخالف"
            d["derived"]["net_liq_trend"] = {
                "value": delta,
                "label": "تغییر ۳۰ روزه نقدینگی خالص (میلیارد دلار)",
                "read": rd}

    # ترکیب اشتغال — قانون ۶ وصله ۵.۳
    u, cp = raw.get("UNRATE"), raw.get("CIVPART")
    if u and cp and u.get("prev30") and cp.get("prev30"):
        du, dcp = u["value"]-u["prev30"], cp["value"]-cp["prev30"]
        if du < 0 and dcp < 0:
            verdict = "بیکاری پایین آمده ولی مشارکت هم پایین آمده ← ضعف، نه قدرت"
        elif du < 0:
            verdict = "بیکاری پایین، مشارکت پایدار ← قدرت واقعی"
        else:
            verdict = "بیکاری در حال افزایش"
        d["derived"]["labor_composition"] = {
            "value": None, "label": "آزمون ترکیب اشتغال", "read": verdict}
    return d


# ══════════ منابع غیرصرافی ══════════

def fetch_macro(out: dict[str, Field]) -> None:
    """ستون‌های رژیم: تسلط بیت‌کوین، ارزش کل بازار، ترس و طمع، عرضه استیبل‌کوین."""
    g = http_get(f"{CG_BASE}/global", label="کوین‌گکو سراسری")
    if g and "data" in g:
        d = g["data"]
        ts = datetime.fromtimestamp(d.get("updated_at", time.time()), UTC)
        mc = d.get("market_cap_percentage", {})
        if "btc" in mc:
            out["btc_dominance"] = Field(mc["btc"], "CoinGecko", ts)
        if "eth" in mc:
            out["eth_dominance"] = Field(mc["eth"], "CoinGecko", ts)
        tot = d.get("total_market_cap", {}).get("usd")
        if tot:
            out["total_mcap"] = Field(tot, "CoinGecko", ts)
        chg = d.get("market_cap_change_percentage_24h_usd")
        if chg is not None:
            out["mcap_change_24h"] = Field(chg, "CoinGecko", ts)

    f = http_get("https://api.alternative.me/fng/",
                 {"limit": "31", "format": "json"}, label="ترس و طمع")
    if f and f.get("data"):
        rows = f["data"]
        ts = datetime.fromtimestamp(int(rows[0]["timestamp"]), UTC)
        out["fear_greed"] = Field(int(rows[0]["value"]), "Alternative.me", ts,
                                  rows[0].get("value_classification", ""))
        if len(rows) >= 8:
            out["fear_greed_7d_ago"] = Field(int(rows[7]["value"]), "Alternative.me")
        if len(rows) >= 31:
            out["fear_greed_30d_avg"] = Field(
                float(np.mean([int(r["value"]) for r in rows[:30]])), "Alternative.me")

    # عرضه استیبل‌کوین — سنجه چهارم بلوک جریان
    s = http_get("https://stablecoins.llama.fi/stablecoincharts/all",
                 label="عرضه استیبل‌کوین")
    if isinstance(s, list) and len(s) > 31:
        def total(rec):
            v = rec.get("totalCirculatingUSD", {})
            return sum(x for x in v.values() if isinstance(x, (int, float))) if isinstance(v, dict) else None
        try:
            now_v, d7, d30 = total(s[-1]), total(s[-8]), total(s[-31])
            ts = datetime.fromtimestamp(int(s[-1]["date"]), UTC)
            if now_v:
                out["stable_supply"] = Field(now_v, "DefiLlama", ts)
                if d7:
                    out["stable_change_7d"] = Field(100 * (now_v - d7) / d7, "DefiLlama", ts)
                if d30:
                    out["stable_change_30d"] = Field(100 * (now_v - d30) / d30, "DefiLlama", ts,
                                                     "سوخت واقعی سمت خرید")
        except (KeyError, TypeError, ZeroDivisionError) as exc:
            FAILURES.append(f"عرضه استیبل‌کوین: {exc}")

    # ── تسلط تتر به‌تنهایی. با «تسلط کل استیبل‌کوین‌ها» فرق دارد:
    #    دلار غیرمتمرکز و توکن‌های بازده‌دار رفتار متفاوتی از پول داغ تتر دارند.
    t = http_get(f"{CG_BASE}/coins/markets",
                 {"vs_currency": "usd", "ids": "tether,usd-coin", "per_page": "5"},
                 label="ارزش بازار استیبل‌کوین‌ها")
    tether_mc = usdc_mc = None
    if isinstance(t, list):
        for row in t:
            if row.get("id") == "tether":
                tether_mc = row.get("market_cap")
            elif row.get("id") == "usd-coin":
                usdc_mc = row.get("market_cap")
    tm = out.get("total_mcap")
    if tether_mc and tm and tm.ok and tm.value:
        out["usdt_mcap"] = Field(tether_mc, "CoinGecko", datetime.now(UTC))
        out["usdt_dominance"] = Field(
            100.0 * tether_mc / tm.value, "محاسبه‌شده", datetime.now(UTC),
            "تسلط تتر — بالا رفتنش یعنی پول به حاشیه امن رفته")
    if usdc_mc and tm and tm.ok and tm.value:
        out["usdc_dominance"] = Field(100.0 * usdc_mc / tm.value,
                                      "محاسبه‌شده", datetime.now(UTC))

    # ── TOTAL2 و TOTAL3: ارزش بازار بدون بیت‌کوین، و بدون بیت‌کوین و اتریوم
    bd_, ed_ = out.get("btc_dominance"), out.get("eth_dominance")
    if tm and tm.ok and bd_ and bd_.ok:
        btc_mc_ = tm.value * bd_.value / 100.0
        out["total2"] = Field(tm.value - btc_mc_, "محاسبه‌شده", datetime.now(UTC),
                              "ارزش بازار آلت‌کوین‌ها، بدون بیت‌کوین")
        if ed_ and ed_.ok:
            eth_mc_ = tm.value * ed_.value / 100.0
            out["total3"] = Field(tm.value - btc_mc_ - eth_mc_, "محاسبه‌شده",
                                  datetime.now(UTC), "بدون بیت‌کوین و اتریوم")
            if out.get("stable_supply") and out["stable_supply"].ok:
                # TOTAL3 منهای استیبل‌کوین = پول ریسک‌پذیر واقعی در آلت‌ها
                out["total3_ex_stable"] = Field(
                    tm.value - btc_mc_ - eth_mc_ - out["stable_supply"].value,
                    "محاسبه‌شده", datetime.now(UTC),
                    "پول واقعاً ریسک‌پذیر در آلت‌کوین‌ها")

    # تسلط بدون استیبل‌کوین — از ترکیب دو منبع بالا محاسبه می‌شود
    bd, tm, ss = out.get("btc_dominance"), out.get("total_mcap"), out.get("stable_supply")
    if bd and tm and ss and bd.ok and tm.ok and ss.ok:
        denom = tm.value - ss.value
        if denom > 0:
            btc_mcap = tm.value * bd.value / 100.0
            out["btc_dom_ex_stable"] = Field(
                100.0 * btc_mcap / denom, "محاسبه‌شده از CoinGecko و DefiLlama",
                datetime.now(UTC),
                "تسلط بیت‌کوین با حذف استیبل‌کوین از مخرج — ورودی ستون چرخه بیت‌کوین")
            out["stable_dominance"] = Field(
                100.0 * ss.value / tm.value, "محاسبه‌شده", datetime.now(UTC),
                "سهم استیبل‌کوین از کل بازار — سنجه پول کنارگذاشته")


CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "ONDO": "ondo-finance",
    "TAO": "bittensor", "HYPE": "hyperliquid", "HBAR": "hedera-hashgraph",
    "XLM": "stellar", "AAVE": "aave", "DOGE": "dogecoin", "LINK": "chainlink",
    "SUI": "sui", "RNDR": "render-token", "RENDER": "render-token",
}


def fetch_fundamental(base: str, out: dict[str, Field]) -> None:
    """عرضه در گردش، ارزش رقیق‌شده، فاصله از سقف تاریخی، ارزش کل قفل‌شده."""
    cid = CG_IDS.get(base.upper())
    if not cid:
        lst = http_get(f"{CG_BASE}/coins/list", label="فهرست کوین‌گکو")
        if isinstance(lst, list):
            for c in lst:
                if c.get("symbol", "").upper() == base.upper():
                    cid = c["id"]
                    break
    if not cid:
        FAILURES.append(f"شناسه کوین‌گکو برای {base} پیدا نشد")
        return

    c = http_get(f"{CG_BASE}/coins/{cid}",
                 {"localization": "false", "tickers": "false", "market_data": "true",
                  "community_data": "false", "developer_data": "false"},
                 label="کوین‌گکو جزئیات")
    if not c:
        return
    md = c.get("market_data", {}) or {}
    ts = datetime.now(UTC)

    def g(key, sub="usd"):
        v = md.get(key)
        return v.get(sub) if isinstance(v, dict) else v

    for name, key in [("mcap", "market_cap"), ("fdv", "fully_diluted_valuation"),
                      ("vol24", "total_volume"), ("ath", "ath"), ("atl", "atl")]:
        v = g(key)
        if v:
            out[name] = Field(v, "CoinGecko", ts)
    for name, key in [("circ_supply", "circulating_supply"),
                      ("total_supply", "total_supply"), ("max_supply", "max_supply")]:
        v = md.get(key)
        if v:
            out[name] = Field(v, "CoinGecko", ts)
    v = g("ath_change_percentage")
    if v is not None:
        out["from_ath_pct"] = Field(v, "CoinGecko", ts)

    if out.get("circ_supply") and out.get("total_supply"):
        out["float_pct"] = Field(
            100 * out["circ_supply"].value / out["total_supply"].value,
            "محاسبه‌شده", ts, "درصد عرضه آزادشده — هرچه کمتر، فشار رقیق‌شدگی آینده بیشتر")

    # ارزش کل قفل‌شده از دیفای‌لاما
    slug = {"ONDO": "ondo-finance", "AAVE": "aave", "LINK": "chainlink"}.get(base.upper())
    if slug:
        p = http_get(f"https://api.llama.fi/protocol/{slug}", label="ارزش کل قفل‌شده")
        if p and isinstance(p.get("tvl"), list) and p["tvl"]:
            last = p["tvl"][-1]
            out["tvl"] = Field(last.get("totalLiquidityUSD"), "DefiLlama",
                               datetime.fromtimestamp(last.get("date", 0), UTC))


def fetch_unlocks(base: str, out: dict[str, Field]) -> None:
    """تقویم آزادسازی توکن — شرط سخت شماره ۶ رادار."""
    em = http_get("https://api.llama.fi/emissions", label="فهرست آزادسازی")
    if not isinstance(em, list):
        return
    target = None
    for p in em:
        names = {str(p.get("name", "")).lower(), str(p.get("token", "")).lower(),
                 str(p.get("gecko_id", "")).lower()}
        if base.lower() in names or CG_IDS.get(base.upper(), "") in names:
            target = p
            break
    if not target:
        FAILURES.append(f"تقویم آزادسازی {base} در دیفای‌لاما پیدا نشد — دستی بررسی شود")
        return

    ts = datetime.now(UTC)
    for key, label in [("nextEvent", "رویداد بعدی"), ("upcomingEvent", "رویداد پیش‌رو")]:
        ev = target.get(key)
        if ev:
            out["next_unlock"] = Field(ev, "DefiLlama", ts, label)
            break
    if target.get("mcap") and target.get("maxSupply"):
        out["unlock_meta"] = Field(
            {k: target.get(k) for k in ("name", "token", "mcap", "maxSupply")},
            "DefiLlama", ts)


def fetch_coinglass(base: str, out: dict[str, Field]) -> None:
    """اختیاری — فقط اگر کلید در متغیر محیطی باشد."""
    key = os.environ.get("COINGLASS_API_KEY")
    if not key:
        out["coinglass"] = Field(None, "", None,
                                 "کلید تنظیم نشده — نقشه گرمایی لیکوئیدیشن دستی بماند")
        return
    js = http_get("https://open-api-v4.coinglass.com/api/futures/liquidation/aggregated-history",
                  {"symbol": base, "interval": "1h"},
                  label="کوین‌گلس لیکوئیدیشن")
    if js and js.get("data"):
        out["liq_24h"] = Field(js["data"][-24:], "Coinglass", datetime.now(UTC))



# ══════════ کمکی‌های گزارش ══════════

def fmt_num(v, d=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, (int, float)):
        a = abs(v)
        if a >= 1e9:
            return f"{v/1e9:,.2f}B"
        if a >= 1e6:
            return f"{v/1e6:,.2f}M"
        if a >= 1000:
            return f"{v:,.2f}"
        return f"{v:,.{d}f}"
    return str(v)


def snapshot(df: pd.DataFrame, name: str) -> str:
    """آخرین کندل بسته‌شده. کندل باز عمداً استفاده نمی‌شود."""
    closed = df[df["confirm"] == 1] if "confirm" in df.columns else df
    if len(closed) == 0:
        return f"### {name}\n\n**داده ندارم**\n"
    r = closed.iloc[-1]
    price = float(r["close"])
    atr = float(r["atr14"]) if math.isfinite(r["atr14"]) else None
    lines = [
        f"### {name}",
        "",
        f"آخرین کندل بسته‌شده: **{r['ts'].date()}**  |  تعداد کندل: {len(df)}",
        "",
        "| سنجه | مقدار | نسبت به قیمت |",
        "|---|---|---|",
        f"| بسته‌شدن | {fmt_num(price)} | — |",
        f"| بالاترین | {fmt_num(r['high'])} | — |",
        f"| پایین‌ترین | {fmt_num(r['low'])} | — |",
    ]
    for lbl, col in [("EMA ۲۰", "ema20"), ("EMA ۵۰", "ema50"), ("EMA ۲۰۰", "ema200")]:
        v = float(r[col]) if math.isfinite(r[col]) else None
        rel = f"{100*(price-v)/v:+.2f}%" if v else "—"
        lines.append(f"| {lbl} | {fmt_num(v)} | {rel} |")
    vr = r["vol_ma20"]
    vol_rel = f"{r['vol']/vr:.2f}x میانگین ۲۰" if (math.isfinite(vr) and vr > 0) else "—"
    lines += [
        f"| RSI ۱۴ | {fmt_num(r['rsi14'], 2)} | {'بالای ۵۰' if r['rsi14']>50 else 'زیر ۵۰'} |",
        f"| ATR ۱۴ | {fmt_num(atr)} | {f'{100*atr/price:.2f}%' if atr else '—'} |",
        f"| MACD هیستوگرام | {fmt_num(r['macd_hist'], 6)} | {'مثبت' if r['macd_hist']>0 else 'منفی'} |",
        f"| حجم | {fmt_num(r['vol'], 0)} | {vol_rel} |",
        "",
    ]
    order = []
    for lbl, col in [("قیمت", None), ("۲۰", "ema20"), ("۵۰", "ema50"), ("۲۰۰", "ema200")]:
        order.append((lbl, price if col is None else float(r[col])))
    order = [o for o in order if math.isfinite(o[1])]
    order.sort(key=lambda x: -x[1])
    lines.append("چیدمان از بالا به پایین: **" + " > ".join(o[0] for o in order) + "**")
    lines.append("")
    return "\n".join(lines)



def check_candle_order(df: pd.DataFrame, name: str, tests: list) -> None:
    """
    راستی‌آزمایی ۲ — ترتیب کندل‌ها.
    OKX از جدید به قدیم می‌دهد. اگر مرتب‌سازی درست انجام شده باشد،
    آخرین مهر زمانی باید تازه باشد و کل ستون صعودی.
    """
    if df is None or len(df) < 2:
        tests.append((f"راستی‌آزمایی ۲ — ترتیب {name}", False, "کندل کافی نیست"))
        return
    ascending = bool(df["ts"].is_monotonic_increasing)
    newest = df["ts"].iloc[-1]
    age_days = (datetime.now(UTC) - newest.to_pydatetime()).total_seconds() / 86400
    ok = ascending and age_days < 8
    tests.append((
        f"راستی‌آزمایی ۲ — ترتیب {name}",
        ok,
        f"صعودی={ascending} | آخرین کندل={newest.date()} | عمر={age_days:.2f} روز"
    ))



# ═══════════════════════════════════════════════════════════════════
#  ارکستراسیون چند-صرافی
# ═══════════════════════════════════════════════════════════════════

SYMBOL_ALIAS = {"RNDR": "RENDER"}   # نمادهای تغییرنام‌داده


def probe_venues(order: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """
    قبل از شروع، هر صرافی را با یک درخواست سبک آزمایش می‌کند.
    صرافی مسدود از فهرست خارج می‌شود تا وقت و سقف نرخ هدر نرود.
    """
    live, dead = [], []
    for vn in order:
        v = VENUES.get(vn)
        if v is None:
            continue

        def _why(from_idx: int, default: str = "پاسخ نداد") -> str:
            for f in FAILURES[from_idx:]:
                if "۴۵۱" in f or "451" in f:
                    return "مسدودیت جغرافیایی (کد ۴۵۱)"
                if "403" in f:
                    return "دسترسی ممنوع (کد ۴۰۳)"
                if "429" in f:
                    return "سقف نرخ (کد ۴۲۹)"
            return default

        # آزمون ۱ — بازار نقدی (کندل)
        i0 = len(FAILURES)
        try:
            df = v.candles("BTC", "1D", 5, http_get)
        except Exception:
            df = None
        spot_ok = df is not None and len(df) >= 3
        spot_why = "" if spot_ok else _why(i0)

        # آزمون ۲ — بازار مشتقات (فاندینگ). دامنه‌اش با نقدی فرق دارد
        # و ممکن است یکی باز و دیگری بسته باشد.
        i1 = len(FAILURES)
        try:
            fd = v.funding("BTC", http_get)
        except Exception:
            fd = None
        deriv_ok = bool(fd)
        deriv_why = "" if deriv_ok else _why(i1)

        if spot_ok and deriv_ok:
            live.append(vn)
        elif spot_ok:
            live.append(vn)
            VENUE_NO_DERIV.add(vn)
            dead.append((vn, f"فقط کندل — مشتقات: {deriv_why}"))
        elif deriv_ok:
            live.append(vn)
            dead.append((vn, f"فقط مشتقات — کندل: {spot_why}"))
        else:
            dead.append((vn, spot_why))
    return live, dead


VENUE_NO_DERIV: set = set()   # صرافی‌هایی که مشتقاتشان در آزمون رد شد


def gather_venues(base: str, order: list[str], price_hint: float | None
                  ) -> tuple[dict, dict, dict, dict]:
    """
    از همه صرافی‌های در دسترس داده می‌گیرد و **جمع می‌کند**، نه اینکه اولی را بردارد و برود.
    هر صرافی که خطا داد فقط از فهرست کنار می‌رود و بقیه ادامه می‌دهند.
    """
    funding, oi, pos, cndl = {}, {}, {}, {}
    for vn in order:
        v = VENUES.get(vn)
        if v is None or vn in VENUE_NO_DERIV:
            continue
        try:
            f = v.funding(base, http_get)
            if f: funding[vn] = f
            o = v.oi(base, price_hint, http_get)
            if o: oi[vn] = o
            p = v.positioning(base, http_get)
            if p: pos[vn] = p
        except Exception as exc:
            FAILURES.append(f"[{vn}] استثنای غیرمنتظره: {type(exc).__name__} {str(exc)[:80]}")
    return funding, oi, pos, cndl


def candles_first_ok(base: str, order: list[str], want: int, tests: list
                     ) -> tuple[dict, str | None, pd.DataFrame | None]:
    """
    کندل را از اولین صرافی سالم می‌گیرد. مخلوط‌کردن کندل چند صرافی ممنوع است —
    سطوح قیمتی باید از یک بازار بیایند وگرنه استاپ و ورود ناهم‌خوان می‌شوند.
    """
    for vn in order:
        v = VENUES.get(vn)
        if v is None:
            continue
        got, ok = {}, True
        for bar, n in [("1D", want), ("4H", 500), ("1W", 200)]:
            df = None
            try:
                df = v.candles(base, bar, n, http_get)
            except Exception as exc:
                FAILURES.append(f"[{vn}] کندل {bar}: {type(exc).__name__}")
            if df is None or len(df) < 60:
                if bar == "1D":
                    ok = False
                    break
                continue
            got[bar] = enrich(df)
        if ok and "1D" in got:
            check_candle_order(got["1D"], f"کندل روزانه ({vn})", tests)
            pair = None
            try:
                pdf = v.candles(f"{base}", "1D", 400, http_get) if False else None
            except Exception:
                pdf = None
            # جفت نسبت به بیت‌کوین فقط در OKX و بایننس نماد مستقیم دارد
            if vn in ("okx", "binance"):
                sym_save = v.spot
                try:
                    v.spot = (lambda b, _v=vn: f"{base}-BTC" if _v == "okx" else f"{base}BTC")
                    pdf = v.candles(base, "1D", 400, http_get)
                finally:
                    v.spot = sym_save
                if pdf is not None and len(pdf) > 60:
                    pair = enrich(pdf)
            return got, vn, pair
    return {}, None, None


def agg_funding(funding: dict) -> dict:
    """میانگین و پراکندگی نرخ تأمین مالی نرمال‌شده در همه صرافی‌های در دسترس."""
    vals = [f["rate_8h"] for f in funding.values() if f.get("rate_8h") is not None]
    if not vals:
        return {}
    return {"mean": float(np.mean(vals)), "min": float(np.min(vals)),
            "max": float(np.max(vals)), "n": len(vals),
            "disagree": bool(np.min(vals) < 0 < np.max(vals))}


def run3(symbol, balance, profile, macro_event, deep, order):
    base = SYMBOL_ALIAS.get(symbol.upper(), symbol.upper())
    b = Bundle(symbol=base, balance=balance, profile=profile)
    b.venue_order = order

    print(f"[۰/۵] آزمایش دسترسی صرافی‌ها ...", file=sys.stderr)
    live, dead = probe_venues(order)
    b.venue_dead = dead
    for vn, why in dead:
        print(f"      ✗ {vn}: {why}", file=sys.stderr)
    if live:
        print(f"      ✓ در دسترس: {', '.join(live)}", file=sys.stderr)
        order = live
        b.venue_order = live
    else:
        print("      ⚠️ هیچ صرافی در دسترس نیست — با ترتیب اصلی ادامه می‌دهم",
              file=sys.stderr)

    print(f"[۱/۵] کندل — تلاش به ترتیب {', '.join(order)} ...", file=sys.stderr)
    got, vn, pair = candles_first_ok(base, order, 1000 if deep else 400, b.tests)
    b.candles, b.candle_venue, b.pair_btc = got, vn, pair

    price = None
    if "1D" in b.candles:
        cl = b.candles["1D"]
        cl = cl[cl["confirm"] == 1] if "confirm" in cl.columns else cl
        if len(cl):
            price = float(cl.iloc[-1]["close"])

    print("[۲/۵] مشتقات از همه صرافی‌ها ...", file=sys.stderr)
    b.v_funding, b.v_oi, b.v_pos, _ = gather_venues(base, order, price)
    b.f_agg = agg_funding(b.v_funding)
    for vn2, f in b.v_funding.items():
        ok = 0.5 <= f["interval_h"] <= 24
        b.tests.append((f"راستی‌آزمایی ۳ — بازه فاندینگ ({vn2})", ok,
                        f"{f['interval_h']:.2f} ساعت، محاسبه‌شده از پاسخ صرافی"))
    for vn2, o in b.v_oi.items():
        if o.get("cross_check") is not None:
            b.tests.append((f"راستی‌آزمایی ۱ — واحد بهره باز ({vn2})", bool(o["cross_check"]),
                            "دو مسیر مستقل منطبق" if o["cross_check"] else "دو مسیر ناهم‌خوان"))
        if o.get("usd"):
            b.tests.append((f"آزمون بزرگی بهره باز ({vn2})", o["usd"] > 1_000_000,
                            f"{o['usd']:,.0f} دلار"))

    print("[۳/۵] ماکرو رسمی فدرال‌رزرو ...", file=sys.stderr)
    b.fred = fetch_fred(http_text)

    print("[۴/۵] بازار، بنیادی، آزادسازی ...", file=sys.stderr)
    fetch_macro(b.macro)
    fetch_fundamental(base, b.fundamental)
    fetch_unlocks(base, b.fundamental)

    print("[۵/۵] پروفایل حجم و فیبوناچی ...", file=sys.stderr)
    if "1D" in b.candles:
        b.vprofile = three_anchors(b.candles["1D"], macro_event, b.candles.get("4H"))
        b.fib = fibonacci(b.candles["1D"])
    return b


# ═══════════════════════════════════════════════════════════════════
#  گزارش نسخه ۳
# ═══════════════════════════════════════════════════════════════════

def report3(b: Bundle) -> str:
    L: list[str] = []; A = L.append
    A(f"# بسته داده رادار ۵.۲ — {b.symbol}")
    A("")
    A(f"تولید: **{b.generated.strftime('%Y-%m-%d %H:%M UTC')}** | نسخه {VERSION} | "
      f"پروفایل: **{'معامله' if b.profile=='trade' else 'موقعیت'}** | "
      f"منبع کندل: **{b.candle_venue or 'هیچ‌کدام'}**")
    A("")
    A(f"وضعیت کلیدها: کوین‌گکو {'✅ فعال' if CG_KEY else '⬜ بدون کلید'} | "
      f"کوین‌گلس {'✅ فعال' if os.environ.get('COINGLASS_API_KEY') else '⬜ بدون کلید'}")
    A("")
    A("> برچسب معرفتی همه اعداد: **مشاهده‌شده (Observed)** از نقاط عمومی صرافی، "
      "فدرال‌رزرو سنت‌لوئیس، کوین‌گکو و دیفای‌لاما.")
    A("")

    if b.venue_dead:
        A("**صرافی‌های در دسترس نبودند:** " +
          "، ".join(f"{v} ({w})" for v, w in b.venue_dead))
        A("")
    A("## ۰ — تست‌های سلامت")
    A(""); A("| تست | نتیجه | جزئیات |"); A("|---|---|---|")
    for n, ok, d in b.tests:
        A(f"| {n} | {'✅' if ok else '❌'} | {d} |")
    A("")
    if FAILURES:
        A("**منابعی که پاسخ ندادند:**"); A("")
        for f in FAILURES[:25]:
            A(f"- {f}")
        A(""); A("> اینها «داده ندارم» هستند و از پوشش داده کم می‌شوند."); A("")

    A("---"); A(""); A("## ۱ — چارت و اندیکاتور"); A("")
    for lab, k in [("روزانه","1D"),("چهارساعته","4H"),("هفتگی","1W")]:
        if k in b.candles:
            A(snapshot(b.candles[k], f"{b.symbol}/USDT — {lab} ({b.candle_venue})"))
    if b.pair_btc is not None and len(b.pair_btc):
        A(snapshot(b.pair_btc, f"{b.symbol}/BTC — روزانه (قدرت نسبی)"))

    A("---"); A(""); A("## ۲ — پروفایل حجم، سه لنگر"); A("")
    if b.vprofile:
        A("| لنگر | بازه | ریزدانگی | نقطه کنترل | مرز پایین | مرز بالا |")
        A("|---|---|---|---|---|---|")
        for k in ["A","B","C"]:
            v = b.vprofile.get(k)
            if v:
                A(f"| {v['label']} | {v['from']} تا {v['to']} | {v.get('grain','روزانه')} | "
                  f"**{fmt_num(v['poc'])}** | {fmt_num(v['val'])} | {fmt_num(v['vah'])} |")
        A("")
        atr_d = None
        if "1D" in b.candles:
            c = b.candles["1D"]; c = c[c["confirm"]==1]
            if len(c): atr_d = float(c.iloc[-1]["atr14"])
        vd, why = convergence(b.vprofile, atr_d)
        A(f"**آزمون هم‌گرایی: {vd}** — {why}"); A("")
    else:
        A("**داده ندارم**"); A("")

    # ── فیبوناچی: فقط لایه تأیید
    A("### فیبوناچی — لایه دوم تأیید، نه منبع سطح")
    A("")
    if b.fib:
        f = b.fib
        A(f"نوسان مرجع: **{f['direction']}** | سقف {fmt_num(f['swing_high'])} "
          f"({f['high_date']}) تا کف {fmt_num(f['swing_low'])} ({f['low_date']})")
        A("")
        A("| نسبت | سطح |"); A("|---|---|")
        for r_, v_ in f["levels"].items():
            mark = " ← نزدیک‌ترین" if r_ == f["nearest"]["ratio"] else ""
            A(f"| {r_} | {fmt_num(v_)}{mark} |")
        A("")
        atr_d2 = None
        if "1D" in b.candles:
            c2 = b.candles["1D"]; c2 = c2[c2["confirm"] == 1]
            if len(c2): atr_d2 = float(c2.iloc[-1]["atr14"])
        A(f"**آزمون هم‌نشینی با پروفایل حجم:** {fib_vp_confluence(b.fib, b.vprofile, atr_d2)}")
        A("")
        A("> فیبوناچی مبنای نظری ندارد و در فهرست رد‌شده‌های رادار است. "
          "فقط وقتی امتیاز می‌گیرد که با نقطه کنترل پروفایل حجم یکی شود. "
          "در تضاد، **پروفایل حجم برنده است**.")
        A("")
    else:
        A("**داده ندارم**"); A("")

    # ── مقایسه صرافی‌ها: جایگزین جدول کوین‌گلس
    A("---"); A(""); A("## ۳ — مشتقات، تفکیک‌شده به صرافی"); A("")
    if b.v_funding or b.v_oi:
        A("| صرافی | نرخ فاندینگ خام | بازه | **نرمال‌شده ۸ ساعت** | بهره باز (دلار) | تغییر ۲۴ ساعته |")
        A("|---|---|---|---|---|---|")
        for vn in b.venue_order:
            f, o = b.v_funding.get(vn), b.v_oi.get(vn)
            if not f and not o: continue
            fr_raw = f"{f['rate']*100:+.5f}%" if f else "—"
            fr_iv  = f"{f['interval_h']:.0f}h" if f else "—"
            fr_8h  = f"**{f['rate_8h']*100:+.5f}%**" if f else "—"
            oi_usd = fmt_num(o["usd"]) if (o and o.get("usd")) else "—"
            oi_chg = f"{o['chg24']:+.2f}%" if (o and o.get("chg24") is not None) else "—"
            A(f"| {vn} | {fr_raw} | {fr_iv} | {fr_8h} | {oi_usd} | {oi_chg} |")
        A("")
        if b.f_agg:
            a = b.f_agg
            A(f"**تجمیع فاندینگ:** میانگین {a['mean']*100:+.5f}% در {a['n']} صرافی، "
              f"بازه {a['min']*100:+.5f}% تا {a['max']*100:+.5f}%")
            if a.get("disagree"):
                A("")
                A("> ⚠️ **علامت فاندینگ بین صرافی‌ها یکسان نیست.** در بعضی مثبت و در بعضی منفی. "
                  "این یعنی ازدحام یک‌طرفه نیست و خواندن یک صرافی به‌تنهایی گمراه‌کننده است.")
            A("")
    else:
        A("**داده ندارم** — هیچ صرافی پاسخ نداد."); A("")

    A("### موضع‌گیری"); A("")
    if b.v_pos:
        A("| صرافی | کل حساب‌ها | معامله‌گران برتر (حساب) | معامله‌گران برتر (پوزیشن) | تیکر خرید/فروش |")
        A("|---|---|---|---|---|")
        for vn, p in b.v_pos.items():
            A(f"| {vn} | {fmt_num(p.get('global_account'),3)} | {fmt_num(p.get('top_account'),3)} "
              f"| {fmt_num(p.get('top_position'),3)} | {fmt_num(p.get('taker_buy_sell'),3)} |")
        A("")
        ga = [p.get("global_account") for p in b.v_pos.values() if p.get("global_account")]
        tp = [p.get("top_position") for p in b.v_pos.values() if p.get("top_position")]
        if ga and tp:
            mg, mt = float(np.mean(ga)), float(np.mean(tp))
            if mg > 1.15 * mt:
                A(f"> ⚠️ **واگرایی جمعیت و نهنگ:** میانگین کل حساب‌ها {mg:.2f} در برابر "
                  f"معامله‌گران برتر {mt:.2f}. جمعیت لانگ‌تر از پول هوشمند است.")
                A("")
    else:
        A("**داده ندارم** — نیاز به بایننس یا گیت (تنها منابع رایگان تفکیک نهنگ)."); A("")

    # ── بلوک جریان
    A("---"); A(""); A("## ۴ — بلوک جریان (اجباری)"); A("")
    A("| سنجه | مقدار | وضعیت |"); A("|---|---|---|")
    ois = [o["chg24"] for o in b.v_oi.values() if o.get("chg24") is not None]
    n_ok = 0
    if ois:
        A(f"| تغییر بهره باز ۲۴ ساعته | میانگین {np.mean(ois):+.2f}% "
          f"({len(ois)} صرافی) | ✅ |"); n_ok += 1
    else:
        A("| تغییر بهره باز ۲۴ ساعته | **داده ندارم** | ❌ |")
    if b.f_agg:
        A(f"| فاندینگ نرمال‌شده ۸ ساعت | میانگین {b.f_agg['mean']*100:+.5f}% | ✅ |"); n_ok += 1
    else:
        A("| فاندینگ نرمال‌شده ۸ ساعت | **داده ندارم** | ❌ |")
    A("| جریان خالص صرافی | **داده ندارم** | ❌ منبع رایگان ندارد |")
    sc = b.macro.get("stable_change_30d", Field())
    A(f"| جریان استیبل‌کوین ۳۰ روزه | {sc.render('{:+.2f}%')} | {'✅' if sc.ok else '❌'} |")
    n_ok += 1 if sc.ok else 0
    A(""); A(f"**{n_ok} از ۴ سنجه موجود است.**")
    A("قانون سخت جریان برقرار است." if n_ok >= 3 else
      "> ⛔ **قانون سخت جریان نقض شد ← حکم بدون ورود.**")
    A("")

    # ── ماکرو رسمی
    A("---"); A(""); A("## ۵ — ماکرو رسمی (فدرال‌رزرو سنت‌لوئیس)"); A("")
    fr = b.fred or {}
    if fr.get("raw"):
        A("| سری | مقدار | واحد | تاریخ داده |"); A("|---|---|---|---|")
        for sid, r in fr["raw"].items():
            A(f"| {r['label']} | {fmt_num(r['value'],3)} | {r['unit']} | {r['ts'].date()} |")
        A("")
    if fr.get("derived"):
        A("### سنجه‌های مشتق — وصله ۵.۳"); A("")
        A("| سنجه | مقدار | خوانش |"); A("|---|---|---|")
        for k, d in fr["derived"].items():
            A(f"| {d['label']} | {fmt_num(d['value'],3) if d['value'] is not None else '—'} "
              f"| {d['read']} |")
        A("")
    if not fr.get("raw"):
        A("**داده ندارم** — فدرال‌رزرو سنت‌لوئیس پاسخ نداد."); A("")

    # ── رژیم بازار
    A("---"); A(""); A("## ۶ — رژیم بازار رمزارز"); A("")
    A("| سنجه | مقدار |"); A("|---|---|")
    m = b.macro
    for lab, key, f in [("ارزش کل بازار (TOTAL)","total_mcap","{:,.0f}"),
                        ("**TOTAL2** — بدون بیت‌کوین","total2","{:,.0f}"),
                        ("**TOTAL3** — بدون بیت‌کوین و اتریوم","total3","{:,.0f}"),
                        ("TOTAL3 منهای استیبل","total3_ex_stable","{:,.0f}"),
                        ("**تسلط تتر (USDT.D)**","usdt_dominance","{:.2f}%"),
                        ("تسلط یواس‌دی‌سی","usdc_dominance","{:.2f}%"),
                        ("تسلط بیت‌کوین","btc_dominance","{:.2f}%"),
                        ("**تسلط بدون استیبل‌کوین**","btc_dom_ex_stable","{:.2f}%"),
                        ("تسلط اتریوم","eth_dominance","{:.2f}%"),
                        ("سهم استیبل‌کوین","stable_dominance","{:.2f}%"),
                        ("ترس و طمع","fear_greed","{}"),
                        ("ترس و طمع ۷ روز قبل","fear_greed_7d_ago","{}"),
                        ("عرضه استیبل‌کوین","stable_supply","{:,.0f}"),
                        ("تغییر ۳۰ روزه استیبل‌کوین","stable_change_30d","{:+.2f}%")]:
        A(f"| {lab} | {m.get(key, Field()).render(f)} |")
    A("")

    # ── بنیادی
    A("---"); A(""); A("## ۷ — بنیادی و عرضه"); A("")
    A("| سنجه | مقدار |"); A("|---|---|")
    fd = b.fundamental
    for lab, key, f in [("ارزش بازار","mcap","{:,.0f}"),("ارزش رقیق‌شده","fdv","{:,.0f}"),
                        ("عرضه در گردش","circ_supply","{:,.0f}"),("عرضه کل","total_supply","{:,.0f}"),
                        ("**درصد عرضه آزادشده**","float_pct","{:.2f}%"),
                        ("فاصله از سقف تاریخی","from_ath_pct","{:+.2f}%"),
                        ("ارزش کل قفل‌شده","tvl","{:,.0f}"),
                        ("آزادسازی بعدی","next_unlock","{}")]:
        A(f"| {lab} | {fd.get(key, Field()).render(f)} |")
    A("")

    # ── ریسک
    A("---"); A(""); A("## ۸ — حجم و اهرم (ریسک ۲٪)"); A("")
    price = atr = None
    if "1D" in b.candles:
        c = b.candles["1D"]; c = c[c["confirm"]==1]
        if len(c):
            price, atr = float(c.iloc[-1]["close"]), float(c.iloc[-1]["atr14"])
    if b.balance > 0 and price and atr and math.isfinite(atr):
        risk = b.balance*0.02; ap = 100*atr/price
        A(f"موجودی **{b.balance:,.0f}** دلار | ریسک ۲٪ **{risk:,.2f}** دلار | "
          f"ATR روزانه **{ap:.2f}%**"); A("")
        A("| ضریب استاپ | فاصله | حجم پوزیشن | تعداد توکن | سقف اهرم |")
        A("|---|---|---|---|---|")
        for k in (1.0,1.5,2.0,2.5):
            sd = ap*k; size = risk/(sd/100)
            A(f"| {k:g}× ATR | {sd:.2f}% | {size:,.2f} دلار | {size/price:,.2f} | "
              f"{math.floor(100/(sd*1.5))}x |")
        A(""); A("> اهرم خروجی است نه ورودی. ستون آخر سقف است، نه پیشنهاد."); A("")
    else:
        A("**داده ندارم**"); A("")

    A("---"); A(""); A("## ۹ — آنچه هنوز دستی می‌ماند"); A("")
    A("| مورد | جایگزین |"); A("|---|---|")
    A("| نقشه گرمایی لیکوئیدیشن | اسکرین‌شات کوین‌گلس |")
    A("| جریان خالص صرافی | کریپتوکوانت (پولی) یا اتراسکن با کلید |")
    A("| اخبار و کاتالیزور | جست‌وجوی وب کلاود |")
    A(""); A("---"); A("")
    A(f"**دستور بعدی:** این فایل را کپی کن و بنویس «با رادار ۵.۲ تحلیل کن، "
      f"پروفایل {'معامله' if b.profile=='trade' else 'موقعیت'}».")
    A("")
    return "\n".join(L)


def main3() -> int:
    ap = argparse.ArgumentParser(description="رادار ۵.۲ — واکشی چند-صرافی")
    ap.add_argument("symbol")
    ap.add_argument("--balance", type=float, default=0.0)
    ap.add_argument("--profile", choices=["trade","position"], default="trade")
    ap.add_argument("--macro-event", default=None)
    ap.add_argument("--venues", default=",".join(DEFAULT_ORDER),
                    help="ترتیب تلاش، مثل okx,binance,bybit,gate")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--out", default="out")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()

    order = [v.strip().lower() for v in a.venues.split(",") if v.strip().lower() in VENUES]
    if not order:
        print("هیچ صرافی معتبری انتخاب نشد.", file=sys.stderr); return 2

    t0 = time.time()
    b = run3(a.symbol, a.balance, a.profile, a.macro_event, a.deep, order)
    rep = report3(b)

    if a.stdout:
        print(rep)
    else:
        os.makedirs(a.out, exist_ok=True)
        fn = os.path.join(a.out, f"{b.symbol}_{b.generated.strftime('%Y%m%d_%H%M')}.md")
        open(fn, "w", encoding="utf-8").write(rep)
        print(f"\n✅ {fn}  ({time.time()-t0:.1f} ثانیه)", file=sys.stderr)
        print(f"   صرافی‌های پاسخ‌داده: {', '.join(b.v_funding) or 'هیچ‌کدام'}", file=sys.stderr)
        bad = [n for n,ok,_ in b.tests if not ok]
        if bad: print(f"   ⚠️ تست ردشده: {len(bad)}", file=sys.stderr)


    return 0


if __name__ == "__main__":
    sys.exit(main3())
