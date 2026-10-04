#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_history.py — کندل آزاد در هر تایم‌فریم و هر بازه، و وارسی سطح (snap)
==========================================================================

نشست ۷ نقشه رادار ۷. دو کار:

۱) کندل آزاد:
     python radar_history.py --symbol BTC --tf 1w --from 2018-01-01 --to 2019-12-31
     گزینه‌ها: --venue auto|okx|gate، --csv FILE، --out FILE، --no-table، --no-cache

   - تایم‌فریم: 15m، 1h، 4h، 1d، 1w. لنگر وقت جهانی از radar_anchor.py؛ کندل با
     لنگر دیگر رد می‌شود، هرگز جانشین بی‌صدا.
   - اوکی‌اکس اول، صفحه‌به‌صفحه از --to به عقب. گیت فقط وقتی اوکی‌اکس هیچ داده‌ای
     نداد. دو صرافی هرگز در یک سری ترکیب نمی‌شوند؛ نام صرافی در خروجی می‌آید.
   - تاریخچه صرافی پیش از --from تمام شد؟ صریح «تاریخچه okx از فلان تاریخ».
   - خروجی همیشه ستون تأیید کندل بسته را دارد.
   - --out و --csv مسیر **فایل** می‌گیرند؛ پوشه رد می‌شود — درس ک۱۴.
   - نهان‌گاه محلی .radar_cache/history/ — فقط کندل بسته، چون کندل گذشته عوض
     نمی‌شود. در .gitignore است.
   - بی‌منطقه زمانی یعنی وقت جهانی. تاریخ تنها در --to یعنی پایان همان روز.

۲) وارسی سطح:
     python radar_history.py snap --symbol BTC --tf 4h --at 2026-10-02T08:46:14Z --level 82948.88
     python radar_history.py cards intake/charts/<منبع>/<شناسه>.json [--dry-run]

   - فقط کندل‌هایی که پیش از زمان انتشار ویدیو بسته شده‌اند — نگاه به آینده ممنوع.
   - تعریف سطح ساختاری همان radar_levels.structural_levels است: یک تعریف، نه دو.
   - پهنای «نزدیک» ۰.۲۵ دامنه واقعی همان تایم‌فریم، پنجره ۲۰۰ کندل — ف۱۷ و ف۱۸.
   - «قوی» وقتی خط تصادفی در همان پنجره در ۱۰٪ موارد یا کمتر به این شمار برخورد
     می‌رسد — ف۲۰. شانس از خط‌های هم‌فاصله روی کل دامنه پنجره، همان روش ایستگاه ۱.
   - زیر روزانه «ماشه‌ای، نه ساختاری» — قاعده ۴؛ کارت ستون دوم روزانه هم می‌گیرد.
   - سه حکم: confirmed، not_near، no_data.

فقط محلی یا هر جا که به صرافی راه دارد. آزمون: tests/test_history.py، بی‌شبکه.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import radar_anchor as A
import radar_levels as L          # تعریف سطح ساختاری — یک تعریف، نه دو
from radar_text import fa

VERSION = "1.1"                   # ۱.۱: برش با زمان پایان نمودار کارت و میدان cutoff_basis
UTC = timezone.utc

VENUES = ("okx", "gate")
OKX_URL = "https://www.okx.com/api/v5/market/history-candles"
GATE_URL = "https://api.gateio.ws/api/v4/spot/candlesticks"
OKX_PAGE = 100                    # سقف هر صفحه history-candles اوکی‌اکس
GATE_PAGE = 1000                  # سقف هر درخواست گیت
GATE_MAX_POINTS = 10_000          # گیت فقط این‌قدر کندل اخیر را می‌دهد
PAUSE = 0.12                      # میان صفحه‌ها — سقف نرخ اوکی‌اکس ۲۰ درخواست در ۲ ثانیه
CACHE_DIR = Path(".radar_cache") / "history"
COLS = ["ts", "open", "high", "low", "close", "volume", "confirm"]

# وارسی سطح — دفتر فرض‌ها ف۱۷، ف۱۸، ف۲۰، ف۲۱
LOOKBACK = 200                    # پنجره نگاه به عقب، کندل همان تایم‌فریم — ف۱۸
WIDTH_ATR = 0.25                  # پهنای «نزدیک» بر حسب دامنه واقعی — ف۱۷
MIN_BARS = 60                     # همان آستانه «داده کم» در radar_levels.assess
ATR_N = 14
WARMUP = 3 * ATR_N                # قاعده بلوغ ۳n برای دامنه واقعی
STRONG_CHANCE = 0.10              # «قوی»: خط تصادفی در ۱۰٪ موارد یا کمتر — ف۲۰
GRID = 2001                       # خط‌های هم‌فاصله برای شانس تصادفی
MIN_SAMPLE = 20                   # جمع‌بندی تحلیل‌گر: کمتر یعنی فقط عدد — ف۲۱
ALPHA = 0.05                      # «به‌روشنی بالاتر از شانس» — ف۲۱
SUB_DAILY = ("15m", "1H", "4H")
INDEX_NAMES = {"TOTAL", "TOTAL2", "TOTAL3", "OTHERS"}

SNAP_VERDICTS = ("confirmed", "not_near", "no_data")
SNAP_CLASSES = ("structural", "trigger")
SNAP_STRENGTHS = ("strong", "weak")
SNAP_NUMBERS = ("level", "lookback", "width_atr", "bars", "atr", "touches", "nearest",
                "nearest_touches", "distance_atr", "distance_pct", "chance_pct",
                "strong_min_touches", "chance_at_touches_pct")
SNAP_KEYS = {"from", "tool", "symbol", "venue", "tf", "class", "cutoff", "verdict", "strength",
             "last_bar", "reason", *SNAP_NUMBERS}
# مبنای برش — اختیاری، نسخه ۱.۱: انتشار ویدیو، پایان نمودار کارت، یا پایان نمودار ناخوانا
CUTOFF_BASES = ("publish", "chart_end", "chart_end_unknown")
REASON_MAX = 300

SESSION = requests.Session()


class HistoryError(Exception):
    """کندل نیامد، کوتاه شد یا رد شد — دلیل صریح، هرگز کوتاه‌شدن بی‌صدا."""


# ═══════════════ ۱ — نام، زمان، نماد ═══════════════

_TF = {"15m": "15m", "1h": "1H", "60m": "1H", "4h": "4H", "240m": "4H",
       "1d": "1D", "d": "1D", "1w": "1W", "w": "1W", "7d": "1W"}
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MONDAY = datetime(1970, 1, 5, tzinfo=UTC)         # هفته وقت جهانی از دوشنبه


def norm_tf(raw) -> str:
    """نام داخلی تایم‌فریم: 15m، 1H، 4H، 1D، 1W."""
    k = str(raw).strip().lower()
    if k not in _TF:
        raise ValueError(f"تایم‌فریم ناشناخته: {raw!r} — 15m، 1h، 4h، 1d یا 1w")
    return _TF[k]


def parse_time(raw, end: bool = False) -> datetime:
    """تاریخ یا زمان ISO. بی‌منطقه یعنی وقت جهانی. تاریخ تنها با end یعنی پایان همان روز."""
    s = str(raw).strip()
    if _DATE.fullmatch(s):
        d = datetime.fromisoformat(s).replace(tzinfo=UTC)
        return d + timedelta(days=1) - timedelta(milliseconds=1) if end else d
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (t.replace(tzinfo=UTC) if t.tzinfo is None else t).astimezone(UTC)


def exchange_symbol(coin) -> str | None:
    """
    نماد پایه صرافی از نام روی نمودار: BTCUSD و BTC/USDT یعنی BTC. شاخص تریدینگ‌ویو
    — BTC.D، USDT.D، TOTAL2 — نماد صرافی نیست و None است.
    """
    if not isinstance(coin, str) or not coin.strip():
        return None
    c = coin.strip().upper()
    if c.endswith(".P"):                            # قرارداد دائمی تریدینگ‌ویو
        c = c[:-2]
    if "." in c or c in INDEX_NAMES:
        return None
    c = re.sub(r"[/\-_ ]", "", c)
    for q in ("USDT", "USDC", "USD", "PERP"):
        if c.endswith(q) and len(c) > len(q):
            c = c[:-len(q)]
            break
    return c if re.fullmatch(r"[A-Z0-9]{1,15}", c) else None


def floor_open(t: datetime, tf: str) -> datetime:
    """زمان باز شدن کندلی که t در آن است، روی لنگر وقت جهانی."""
    base = _MONDAY if tf == "1W" else _EPOCH
    sec = A.SECONDS[tf]
    return base + timedelta(seconds=sec * math.floor((t - base).total_seconds() / sec))


def ceil_open(t: datetime, tf: str) -> datetime:
    f = floor_open(t, tf)
    return f if f == t else f + timedelta(seconds=A.SECONDS[tf])


def _ms(t: datetime) -> int:
    return int(round(t.timestamp() * 1000))


def _when(ms: int, tf: str) -> str:
    """مهر زمان خروجی: تاریخ تنها برای روزانه و هفتگی."""
    t = datetime.fromtimestamp(ms / 1000, UTC)
    return t.strftime("%Y-%m-%d") if tf in ("1D", "1W") else t.strftime("%Y-%m-%d %H:%M UTC")


def _num(x) -> str:
    return f"{float(x):.10g}"


# ═══════════════ ۲ — صرافی ═══════════════
# هر سطر داخلی: [ts_ms, open, high, low, close, volume, confirm|None]

def _okx_rows(symbol: str, tf: str, a_ms: int, b_ms: int, get, now: datetime) -> tuple[list, bool]:
    """
    کندل‌های [a, b] اوکی‌اکس، و اینکه آیا تاریخچه صرافی پیش از a تمام شد.
    صفحه‌بندی از b به عقب با after. خطا در میانه، خطای صریح است — هرگز کوتاه بی‌صدا.
    """
    inst, bar = f"{symbol}-USDT", A.HISTORY_BAR["okx"][tf]
    step = A.SECONDS[tf] * 1000
    where = f"اوکی‌اکس {bar} {inst}"
    pages = -(-((b_ms - a_ms) // step + 1) // OKX_PAGE) + 2
    rows, cursor = [], b_ms + 1
    for _ in range(pages):
        try:
            js = get(OKX_URL, params={"instId": inst, "bar": bar, "limit": str(OKX_PAGE),
                                      "after": str(cursor)}, timeout=20).json()
        except (requests.RequestException, ValueError) as exc:
            raise HistoryError(f"{where}: {type(exc).__name__} — {len(rows)} کندل گرفته شده بود؛ "
                               "کوتاه بی‌صدا نمی‌شود") from exc
        if not isinstance(js, dict) or str(js.get("code")) != "0":
            got = js if not isinstance(js, dict) else f"کد {js.get('code')} {js.get('msg') or ''}"
            raise HistoryError(f"{where}: {str(got).strip()}")
        batch = js.get("data") or []
        if not batch:
            return rows, True                       # تاریخچه خود صرافی تمام شد
        for x in batch:
            ts = int(x[0])
            if a_ms <= ts <= b_ms:
                flag = int(x[8]) if len(x) > 8 and str(x[8]) in ("0", "1") else None
                rows.append([ts, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), flag])
        cursor = int(batch[-1][0])                  # کهنه‌ترین همین صفحه
        if cursor <= a_ms:
            return rows, False
        time.sleep(PAUSE)
    raise HistoryError(f"{where}: سقف {pages} صفحه — به آغاز بازه نرسید؛ {len(rows)} کندل")


def _gate_rows(symbol: str, tf: str, a_ms: int, b_ms: int, get, now: datetime) -> tuple[list, int | None]:
    """
    کندل‌های [a, b] گیت با from و to، تکه‌های هزارتایی. گیت فقط ۱۰۰۰۰ کندل اخیر را
    می‌دهد؛ اگر بازه عقب‌تر بود، مرز کهنه‌ترین کندل ممکن برمی‌گردد تا صریح گفته شود.
    """
    pair, interval = f"{symbol}_USDT", A.HISTORY_BAR["gate"][tf]
    step = A.SECONDS[tf] * 1000
    where = f"گیت {interval} {pair}"
    oldest = _ms(floor_open(now, tf)) - (GATE_MAX_POINTS - 1) * step
    clip = oldest if a_ms < oldest else None
    rows, s = [], max(a_ms, oldest)
    while s <= b_ms:
        e = min(b_ms, s + (GATE_PAGE - 1) * step)
        try:
            js = get(GATE_URL, params={"currency_pair": pair, "interval": interval,
                                       "from": s // 1000, "to": e // 1000}, timeout=20).json()
        except (requests.RequestException, ValueError) as exc:
            raise HistoryError(f"{where}: {type(exc).__name__} — {len(rows)} کندل گرفته شده بود؛ "
                               "کوتاه بی‌صدا نمی‌شود") from exc
        if not isinstance(js, list):
            got = (f"{js.get('label') or ''} {js.get('message') or ''}" if isinstance(js, dict) else js)
            raise HistoryError(f"{where}: {str(got).strip()}")
        # قالب گیت: [ts(s), حجم ارز دوم، بسته، بیشینه، کمینه، باز، حجم ارز پایه، بسته‌شده]
        for x in js:
            ts = int(x[0]) * 1000
            if s <= ts <= e:
                flag = (1 if str(x[7]).lower() == "true" else 0) if len(x) > 7 else None
                rows.append([ts, float(x[5]), float(x[3]), float(x[4]), float(x[2]),
                             float(x[6] if len(x) > 6 else x[1]), flag])
        s = e + step
        time.sleep(PAUSE)
    return rows, clip


# ═══════════════ ۳ — نهان‌گاه ═══════════════

def _cache_paths(cache_dir: Path, venue: str, symbol: str, tf: str) -> tuple[Path, Path]:
    d = Path(cache_dir) / venue
    return d / f"{symbol}-{tf}.csv", d / f"{symbol}-{tf}.json"


def _cache_load(cache_dir, venue, symbol, tf) -> tuple[dict[int, list], dict]:
    empty = {"covered": [], "history_start": None}
    if cache_dir is None:
        return {}, empty
    csv, meta_p = _cache_paths(cache_dir, venue, symbol, tf)
    if not csv.exists() or not meta_p.exists():
        return {}, empty
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        rows = {}
        for line in csv.read_text(encoding="utf-8").splitlines()[1:]:
            p = line.split(",")
            rows[int(p[0])] = [int(p[0])] + [float(v) for v in p[1:6]]
    except (OSError, ValueError, IndexError) as exc:
        raise HistoryError(f"نهان‌گاه خراب: {csv} — {type(exc).__name__}. پاکش کن یا --no-cache") from exc
    return rows, {"covered": meta.get("covered") or [], "history_start": meta.get("history_start")}


def _cache_save(cache_dir, venue, symbol, tf, rows: dict[int, list], meta: dict) -> None:
    csv, meta_p = _cache_paths(cache_dir, venue, symbol, tf)
    csv.parent.mkdir(parents=True, exist_ok=True)
    lines = ["ts,open,high,low,close,volume"]
    lines += [",".join([str(k)] + [repr(float(v)) for v in r[1:6]]) for k, r in sorted(rows.items())]
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta_p.write_text(json.dumps({"tool": f"radar_history {VERSION}", **meta}, indent=1), encoding="utf-8")


def _merge(iv: list, step: int) -> list:
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1] + step:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _missing(covered: list, a: int, b: int, step: int) -> list:
    """زیربازه‌های [a, b] که در نهان‌گاه نیستند — روی شبکه کندل."""
    out, cur = [], a
    for c, d in _merge(covered, step):
        if d < cur:
            continue
        if c > b:
            break
        if c > cur:
            out.append([cur, min(b, c - step)])
        cur = max(cur, d + step)
        if cur > b:
            break
    if cur <= b:
        out.append([cur, b])
    return out


# ═══════════════ ۴ — سری ═══════════════

@dataclass
class Series:
    symbol: str
    tf: str
    venue: str
    df: pd.DataFrame
    start: datetime
    end: datetime
    notes: list[str] = field(default_factory=list)
    cached: int = 0
    fetched: int = 0


def _frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLS)
    df = df.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["confirm"] = df["confirm"].astype(int)
    return df


def _venue_history(venue: str, symbol: str, tf: str, a: datetime, b: datetime,
                   cache_dir, get, now: datetime) -> Series:
    step = A.SECONDS[tf] * 1000
    a_ms, b_ms, now_ms = _ms(a), _ms(b), _ms(now)
    last_closed = _ms(floor_open(now, tf)) - step
    cache, meta = _cache_load(cache_dir, venue, symbol, tf)
    covered, hs = [list(x) for x in meta["covered"]], meta["history_start"]
    lo = max(a_ms, hs) if hs is not None else a_ms
    fetch = _okx_rows if venue == "okx" else _gate_rows
    notes, fresh, touched = [], {}, False
    for x, y in (_missing(covered, lo, b_ms, step) if lo <= b_ms else []):
        rows, limit = fetch(symbol, tf, x, y, get, now)
        touched = True
        why = A.check([r[0] for r in rows], tf, f"{venue} {tf} {symbol}")
        if why:
            raise HistoryError(why)
        for r in rows:
            if r[6] is None:                        # صرافی پرچم نداد: باز شدن به‌علاوه طول
                r[6] = 1 if r[0] + step <= now_ms else 0
            fresh[r[0]] = r
        cover_from = x
        if venue == "okx" and limit:                # تاریخچه اوکی‌اکس پیش از x تمام شد — ثابت است
            hs = min((r[0] for r in rows), default=y + step)
        if venue == "gate" and limit:               # پنجره گیت با زمان جلو می‌رود — ذخیره نمی‌شود
            cover_from = max(x, limit)
            notes.append(f"گیت فقط {fa(GATE_MAX_POINTS)} کندل اخیر را می‌دهد — تاریخچه از "
                         f"{_when(limit, tf)}؛ پیش از آن خالی است، نه کوتاه بی‌صدا")
        cover_to = min(y, last_closed)
        if cover_to >= cover_from:
            covered = _merge(covered + [[cover_from, cover_to]], step)

    if cache_dir is not None and touched:
        keep = dict(cache)
        keep.update({k: r[:6] for k, r in fresh.items() if r[6] == 1})
        _cache_save(cache_dir, venue, symbol, tf, keep, {"covered": covered, "history_start": hs})

    out = {k: r + [1] for k, r in cache.items() if a_ms <= k <= b_ms}
    n_cached = len(out)
    for k, r in fresh.items():
        if a_ms <= k <= b_ms:
            n_cached -= k in out
            out[k] = r
    rows = [out[k] for k in sorted(out)]
    if hs is not None and a_ms < hs:
        notes.insert(0, f"تاریخچه {venue} از {_when(hs, tf)} — پیش از آن کندلی نیست؛ "
                        "بازه از همان‌جا، نه کوتاه بی‌صدا")
    if len(rows) > 1:
        gap = (rows[-1][0] - rows[0][0]) // step + 1 - len(rows)
        if gap > 0:
            notes.append(f"شکاف: {gap} کندل در میانه بازه نیست — صرافی کندلی نداد")
    return Series(symbol=symbol, tf=tf, venue=venue, df=_frame(rows), start=a, end=b,
                  notes=notes, cached=n_cached, fetched=len(rows) - n_cached)


def history(symbol: str, tf: str, start: datetime, end: datetime, venue: str = "auto",
            cache_dir=CACHE_DIR, get=None, now: datetime | None = None) -> Series:
    """
    کندل [start, end] روی زمان باز شدن. اوکی‌اکس اول؛ گیت فقط وقتی اوکی‌اکس خطا داد
    یا هیچ کندلی نداد. تاریخچه ناقص اوکی‌اکس با گیت پر نمی‌شود — صرافی‌ها ترکیب نمی‌شوند.
    """
    sym = exchange_symbol(symbol)
    if sym is None:
        raise HistoryError(f"نماد صرافی نیست: {symbol!r}")
    tf = norm_tf(tf)
    now = now or datetime.now(UTC)
    get = get or SESSION.get
    a, b = ceil_open(start, tf), floor_open(min(end, now), tf)
    if b < a:
        raise HistoryError(f"بازه تهی: {start.isoformat()} تا {end.isoformat()}")
    tried = []
    for v in (VENUES if venue == "auto" else (venue,)):
        try:
            s = _venue_history(v, sym, tf, a, b, cache_dir, get, now)
        except HistoryError as exc:
            tried.append(f"{v}: {exc}")
            continue
        if s.df.empty:
            tried.append(f"{v}: هیچ کندلی در بازه")
            continue
        s.notes = [f"{t} — صرافی بعد امتحان شد" for t in tried] + s.notes
        return s
    raise HistoryError(" ؛ ".join(tried))


# ═══════════════ ۵ — خروجی ═══════════════

def render_md(s: Series, table: bool = True) -> str:
    df = s.df
    closed = int((df["confirm"] == 1).sum())
    first, last = (_when(_ms(df["ts"].iloc[i].to_pydatetime()), s.tf) for i in (0, -1))
    lines = [f"# کندل تاریخی — {s.symbol} {s.tf}", "",
             f"ساخته‌شده با radar_history {fa(VERSION)} — "
             f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}", "",
             "| مورد | مقدار |", "|---|---|",
             f"| نماد | {s.symbol}/USDT |",
             f"| صرافی | {s.venue} |",
             f"| تایم‌فریم | {s.tf} — لنگر {A.EXPECT[s.tf]} |",
             f"| بازه درخواستی | {_when(_ms(s.start), s.tf)} تا {_when(_ms(s.end), s.tf)} |",
             f"| بازه واقعی | {first} تا {last} |",
             f"| کندل | {len(df)} — بسته {closed}، باز {len(df) - closed} |",
             f"| از نهان‌گاه / تازه | {s.cached} / {s.fetched} |"]
    if s.notes:
        lines += [""] + [f"⚠️ {n}" for n in s.notes]
    if table:
        lines += ["", "| باز شدن (UTC) | باز | بیشینه | کمینه | پایانی | حجم | تأیید |",
                  "|---|---|---|---|---|---|---|"]
        for r in df.itertuples(index=False):
            lines.append(f"| {_when(_ms(r.ts.to_pydatetime()), s.tf)} | {_num(r.open)} | {_num(r.high)} | "
                         f"{_num(r.low)} | {_num(r.close)} | {_num(r.volume)} | {int(r.confirm)} |")
    return "\n".join(lines) + "\n"


def write_csv(s: Series, path: Path) -> None:
    lines = ["ts,open,high,low,close,volume,confirm,venue"]
    for r in s.df.itertuples(index=False):
        lines.append(",".join([r.ts.isoformat()] + [repr(float(v)) for v in
                              (r.open, r.high, r.low, r.close, r.volume)] + [str(int(r.confirm)), s.venue]))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ═══════════════ ۶ — وارسی سطح (snap) ═══════════════

def _snap_base(tf, cutoff: datetime, level, lookback: int, width_atr: float,
               symbol=None, venue=None) -> dict:
    return {"from": "candles", "tool": f"radar_history {VERSION}", "symbol": symbol, "venue": venue,
            "tf": tf, "class": None if tf is None else ("trigger" if tf in SUB_DAILY else "structural"),
            "level": level, "cutoff": cutoff.astimezone(UTC).isoformat(), "lookback": lookback,
            "width_atr": width_atr, "verdict": "no_data", "strength": None, "bars": 0,
            "last_bar": None, "atr": None, "touches": None, "nearest": None, "nearest_touches": None,
            "distance_atr": None, "distance_pct": None, "chance_pct": None,
            "strong_min_touches": None, "chance_at_touches_pct": None, "reason": None}


def _hit_touches(xs: np.ndarray, prices: np.ndarray, touches: np.ndarray, width: float) -> np.ndarray:
    """شمار برخورد سطحی که هر خط به آن می‌رسد — نزدیک‌ترین سطح، در پهنا — وگرنه صفر."""
    if len(prices) == 0:
        return np.zeros(len(xs), dtype=int)
    d = np.abs(xs[:, None] - prices[None, :])
    j = np.argmin(d, axis=1)
    return np.where(d[np.arange(len(xs)), j] <= width, touches[j], 0)


def snap_frame(df: pd.DataFrame, level, tf: str, cutoff: datetime, *, lookback: int = LOOKBACK,
               width_atr: float = WIDTH_ATR, symbol=None, venue=None) -> dict:
    """
    حکم یک سطح روی کندل‌های df، فقط با کندل‌هایی که تا cutoff بسته شده‌اند.
    دامنه واقعی روی همه کندل‌های پیش از برش؛ سطح‌ها روی آخرین lookback کندل.
    """
    tf = norm_tf(tf)
    if cutoff.tzinfo is None:
        raise ValueError("زمان برش بی‌منطقه است")
    s = _snap_base(tf, cutoff, level, lookback, width_atr, symbol, venue)
    if df is None or df.empty:
        return {**s, "reason": "هیچ کندلی نیامد"}
    why = A.check(list(df["ts"]), tf, "snap")
    if why:
        raise HistoryError(why)
    dur = pd.Timedelta(seconds=A.SECONDS[tf])
    closed = df[(df["confirm"] == 1) & (df["ts"] + dur <= pd.Timestamp(cutoff))].reset_index(drop=True)
    if len(closed):
        s["last_bar"] = closed["ts"].iloc[-1].isoformat()
    s["bars"] = min(len(closed), lookback)
    if not (isinstance(level, (int, float)) and not isinstance(level, bool)
            and math.isfinite(level) and level > 0):
        return {**s, "reason": "قیمت سطح ناخوانا یا نامعتبر"}
    if len(closed) < MIN_BARS:
        return {**s, "reason": f"{len(closed)} کندل بسته پیش از انتشار — دست‌کم {fa(MIN_BARS)} لازم"}
    atr = float(L.atr_wilder(closed, ATR_N).iloc[-1])
    if not (math.isfinite(atr) and atr > 0):
        return {**s, "reason": "دامنه واقعی صفر یا پوچ"}
    win = closed.tail(lookback).reset_index(drop=True)
    res, sup = L.structural_levels(win, atr)
    prices = np.array([x.price for x in res + sup], dtype=float)
    touches = np.array([x.touches for x in res + sup], dtype=int)
    width = width_atr * atr
    grid = np.linspace(float(win["low"].min()), float(win["high"].max()), GRID)
    hits = _hit_touches(grid, prices, touches, width)
    tmax = int(touches.max()) if len(touches) else 0
    strong_min = next((k for k in range(2, tmax + 1) if np.mean(hits >= k) <= STRONG_CHANCE), None)
    s.update(atr=atr, bars=len(win), chance_pct=100 * float(np.mean(hits > 0)),
             strong_min_touches=strong_min, verdict="not_near")
    if not len(prices):
        return {**s, "reason": "هیچ سطح ساختاری در پنجره نیست"}
    j = int(np.argmin(np.abs(prices - level)))
    d = abs(float(prices[j]) - level)
    s.update(nearest=float(prices[j]), nearest_touches=int(touches[j]),
             distance_atr=d / atr, distance_pct=100 * d / level)
    if d <= width:
        at = float(np.mean(hits >= touches[j]))
        s.update(verdict="confirmed", touches=int(touches[j]), chance_at_touches_pct=100 * at,
                 strength="strong" if at <= STRONG_CHANCE else "weak")
    return s


def snap(symbol: str, tf: str, level, cutoff: datetime, *, history_fn=None, daily: bool = True,
         venue: str = "auto", cache_dir=CACHE_DIR, lookback: int = LOOKBACK,
         width_atr: float = WIDTH_ATR) -> dict:
    """snap با واکشی. زیر روزانه، ستون دوم روزانه با همان برش — قاعده ۴ و نشست ۸."""
    tf = norm_tf(tf)
    sym = exchange_symbol(symbol)
    if sym is None:
        return {**_snap_base(tf, cutoff, level, lookback, width_atr, symbol),
                "reason": "شاخص تریدینگ‌ویو یا نماد ناخوانا — نماد صرافی نیست"}
    fn = history_fn or history

    def one(t: str) -> dict:
        start = cutoff - timedelta(seconds=A.SECONDS[t] * (lookback + WARMUP + 5))
        try:
            ser = fn(sym, t, start, cutoff, venue=venue, cache_dir=cache_dir)
        except HistoryError as exc:
            return {**_snap_base(t, cutoff, level, lookback, width_atr, f"{sym}/USDT"),
                    "reason": f"کندل نیامد — {exc}"[:REASON_MAX]}
        return snap_frame(ser.df, level, t, cutoff, lookback=lookback, width_atr=width_atr,
                          symbol=f"{sym}/USDT", venue=ser.venue)

    out = one(tf)
    if daily and tf in SUB_DAILY:
        out["daily"] = one("1D")
    return out


def snap_label(s: dict) -> str:
    """یک خط برای گزارش: «واقعی با N برخورد»، «خط دلخواه» یا «داده کافی نیست»."""
    v = s.get("verdict")
    unknown = " — زمان نمودار نامعلوم" if s.get("cutoff_basis") == "chart_end_unknown" else ""
    if v == "confirmed":
        strength = "قوی" if s.get("strength") == "strong" else "ضعیف"
        trig = " — ماشه‌ای، نه ساختاری" if s.get("class") == "trigger" else ""
        return f"واقعی با {s['touches']} برخورد — {strength}{trig}{unknown}"
    if v == "not_near":
        if s.get("nearest") is None:
            return f"خط دلخواه — هیچ سطح ساختاری در پنجره نیست{unknown}"
        return (f"خط دلخواه — نزدیک‌ترین سطح {s['nearest']:.7g} با {s['nearest_touches']} برخورد، "
                f"{s['distance_atr']:.2f} دامنه واقعی دورتر{unknown}")
    return f"داده کافی نیست — {s.get('reason') or '—'}{unknown}"


def validate_snap(s, where: str = "snap", nested: bool = False) -> list[str]:
    """
    قالب میدان snap کارت. عددهایش از کندل است، نه از تصویر — پس from برابر candles
    و قاعده «هر عدد فقط از تصویر» کارت اینجا جایش را به این قالب می‌دهد.
    """
    if not isinstance(s, dict):
        return [f"{where}: باید شیء باشد"]
    errs = []
    keys = set(s) - ({"daily"} if not nested else set()) - {"cutoff_basis"}
    if "cutoff_basis" in s and s["cutoff_basis"] not in CUTOFF_BASES:
        errs.append(f"{where}.cutoff_basis: {s['cutoff_basis']!r} — باید یکی از {CUTOFF_BASES}")
    if SNAP_KEYS - keys:
        errs.append(f"{where}: میدان نیست — {sorted(SNAP_KEYS - keys)}")
    if keys - SNAP_KEYS:
        errs.append(f"{where}: میدان ناشناخته — {sorted(keys - SNAP_KEYS)}")
    if s.get("from") != "candles":
        errs.append(f"{where}.from: باید «candles» باشد — عدد snap از کندل است، نه از تصویر")
    if not (isinstance(s.get("tool"), str) and s["tool"].startswith("radar_history ")):
        errs.append(f"{where}.tool: نام ابزار و نسخه لازم است")
    v = s.get("verdict")
    if v not in SNAP_VERDICTS:
        errs.append(f"{where}.verdict: {v!r} — باید یکی از {SNAP_VERDICTS}")
    for k in SNAP_NUMBERS:
        x = s.get(k)
        if x is not None and not (isinstance(x, (int, float)) and not isinstance(x, bool)
                                  and math.isfinite(x)):
            errs.append(f"{where}.{k}: عدد نامعتبر {x!r}")
    try:
        if datetime.fromisoformat(str(s.get("cutoff"))).tzinfo is None:
            errs.append(f"{where}.cutoff: زمان بی‌منطقه")
    except ValueError:
        errs.append(f"{where}.cutoff: زمان ISO نیست")
    if v in ("confirmed", "not_near"):
        if s.get("tf") not in A.SECONDS or s.get("class") not in SNAP_CLASSES:
            errs.append(f"{where}: تایم‌فریم یا رده نامعتبر")
        if not isinstance(s.get("venue"), (str, type(None))):
            errs.append(f"{where}.venue: باید متن باشد")
    if v == "confirmed":
        if not (isinstance(s.get("touches"), int) and s["touches"] >= 2):
            errs.append(f"{where}.touches: سطح تأییدشده دست‌کم دو برخورد دارد")
        if s.get("strength") not in SNAP_STRENGTHS:
            errs.append(f"{where}.strength: {s.get('strength')!r}")
    elif s.get("touches") is not None or s.get("strength") is not None:
        errs.append(f"{where}: شمار برخورد و قوت فقط برای سطح تأییدشده")
    if v == "no_data" and not (isinstance(s.get("reason"), str) and s["reason"].strip()):
        errs.append(f"{where}.reason: «داده کافی نیست» بی‌دلیل")
    if isinstance(s.get("reason"), str) and len(s["reason"]) > REASON_MAX:
        errs.append(f"{where}.reason: بالای {REASON_MAX} نویسه")
    if "daily" in s and not nested:
        d = s["daily"]
        errs += validate_snap(d, f"{where}.daily", nested=True)
        if isinstance(d, dict) and d.get("tf") not in ("1D", None):
            errs.append(f"{where}.daily.tf: باید 1D باشد")
    return errs


# ═══════════════ ۷ — جمع‌بندی تحلیل‌گر ═══════════════

def _tail(ps: list[float], k: int) -> float:
    """احتمال دست‌کم k موفقیت از آزمون‌های مستقل با احتمال ps — پواسون‌دوجمله‌ای دقیق."""
    dist = [1.0]
    for p in ps:
        nxt = [0.0] * (len(dist) + 1)
        for j, q in enumerate(dist):
            nxt[j] += q * (1 - p)
            nxt[j + 1] += q * p
        dist = nxt
    return float(sum(dist[k:]))


def summarize(snaps: list[dict]) -> dict:
    """
    سهم سطح‌های تأییدشده در برابر شانس تصادفی همان پنجره‌ها — ف۲۱. خط تکراری
    کارت‌ها یک سطح است. حکم فقط با دست‌کم ۲۰ سطح یکتا با داده.
    """
    uniq: dict = {}
    for s in snaps:
        uniq.setdefault((s.get("symbol"), s.get("tf"), s.get("cutoff"), s.get("level")), s)
    vals = list(uniq.values())
    data = [s for s in vals if s.get("verdict") in ("confirmed", "not_near")
            and s.get("chance_pct") is not None]
    conf = [s for s in data if s["verdict"] == "confirmed"]
    ps = [s["chance_pct"] / 100 for s in data]
    n, k = len(data), len(conf)
    p = _tail(ps, k) if n else None
    return {"rows": len(snaps), "unique": len(vals), "n": n, "confirmed": k,
            "strong": sum(1 for s in conf if s.get("strength") == "strong"),
            "not_near": n - k, "no_data": sum(1 for s in vals if s.get("verdict") == "no_data"),
            "observed_pct": 100 * k / n if n else None,
            "expected_pct": 100 * sum(ps) / n if n else None, "p_value": p,
            "verdict": "small" if n < MIN_SAMPLE else ("above" if p <= ALPHA else "chance")}


def summary_lines(s: dict) -> list[str]:
    pct = lambda x: "—" if x is None else f"{x:.1f}%"
    pv = "—" if s["p_value"] is None else f"{s['p_value']:.4f}"
    lines = ["| سنجه | مقدار |", "|---|---|",
             f"| ردیف سطح در کارت‌ها | {s['rows']} |",
             f"| سطح یکتا | {s['unique']} |",
             f"| داده کافی نیست | {s['no_data']} |",
             f"| سطح یکتا با داده | {s['n']} |",
             f"| واقعی — قوی / همه | {s['strong']} / {s['confirmed']} |",
             f"| خط دلخواه | {s['not_near']} |",
             f"| سهم واقعی | {pct(s['observed_pct'])} |",
             f"| شانس تصادفی همان پنجره‌ها | {pct(s['expected_pct'])} |",
             f"| احتمال این‌همه تأیید از شانس | {pv} |",
             ""]
    if s["verdict"] == "small":
        lines.append(f"**نمونه کم** — {s['n']} سطح یکتا با داده، دست‌کم {fa(MIN_SAMPLE)} لازم. "
                     "فقط عدد؛ حکمی داده نمی‌شود.")
    elif s["verdict"] == "above":
        lines.append("**بالاتر از شانس تصادفی** — سطح‌ها بیش از خط دلخواه با ساختار قیمت می‌خوانند.")
    else:
        lines.append("**از شانس تصادفی جدا نیست** — سطح‌ها بیش از خط دلخواه با ساختار قیمت نمی‌خوانند.")
    lines.append("> سطح‌های یک نماد در یک پنجره مستقل نیستند؛ احتمال بالا خوش‌بینانه است. "
                 "استدلال — محاسبه‌نشده.")
    return lines


# ═══════════════ ۸ — کارت نمودار ═══════════════

def _value(o):
    return o.get("value") if isinstance(o, dict) else None


def card_snap(coin, tf_raw, price, cutoff: datetime, history_fn, **kw) -> dict:
    """snap یک سطح کارت. نماد، تایم‌فریم یا قیمت ناخوانا «داده کافی نیست» است، بی‌واکشی."""
    try:
        tf = norm_tf(tf_raw) if tf_raw else None
    except ValueError:
        tf = None
    lb, wa = kw.get("lookback", LOOKBACK), kw.get("width_atr", WIDTH_ATR)
    base = lambda why: {**_snap_base(tf, cutoff, price if _is_price(price) else None, lb, wa,
                                     coin if isinstance(coin, str) else None), "reason": why}
    if exchange_symbol(coin) is None:
        return base("شاخص تریدینگ‌ویو یا نماد ناخوانا — نماد صرافی نیست")
    if tf is None:
        return base(f"تایم‌فریم ناخوانا یا ناشناخته: {tf_raw!r}")
    if not _is_price(price):
        return base("قیمت سطح ناخوانا")
    return snap(coin, tf, float(price), cutoff, history_fn=history_fn, **kw)


def card_cutoff(card: dict, published: datetime) -> tuple[datetime, str]:
    """
    برش snap یک کارت — نشست ۷: کمینه زمان پایان نمودار و زمان انتشار. ویدیوی آموزشی
    مثال گذشته را نشان می‌دهد و پنجره پیش از انتشار به آن نمی‌رسد. پایان نمودار
    ناخوانا: همان انتشار، با مبنای chart_end_unknown. هرگز پس از انتشار — نگاه به آینده.
    """
    ce = card.get("chart_end")
    if not isinstance(ce, dict):
        return published, "publish"
    if ce.get("value") is None:
        return published, "chart_end_unknown"
    end = datetime.fromisoformat(str(ce["value"])).astimezone(UTC)
    return (end, "chart_end") if end < published else (published, "publish")


def _with_basis(s: dict, basis: str) -> dict:
    s["cutoff_basis"] = basis
    if isinstance(s.get("daily"), dict):
        s["daily"]["cutoff_basis"] = basis
    return s


def _is_price(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def cards_cmd(paths, *, history_fn=None, dry_run: bool = False, venue: str = "auto",
              cache_dir=CACHE_DIR) -> int:
    """
    snap همه سطح‌های خوانده‌شده کارت‌ها، با برش زمان انتشار سند. کارت پس از اعتبارسنجی
    بازنویسی می‌شود؛ نامعتبر دست نمی‌خورد. ناحیه و خط روند وارسی نمی‌شوند.
    """
    import radar_frames as F
    import radar_intake as I
    fn = history_fn or history
    memo: dict = {}

    def cached_fn(sym, tf, start, end, **k):
        key = (sym, tf, end)
        if key not in memo:
            try:
                memo[key] = fn(sym, tf, start, end, **k)
            except HistoryError as exc:
                memo[key] = exc
        if isinstance(memo[key], HistoryError):
            raise memo[key]
        return memo[key]

    rc, by_source = 0, {}
    for path in map(Path, paths):
        doc = json.loads(path.read_text(encoding="utf-8"))
        src_doc = Path(str(doc.get("doc") or ""))
        meta = I._front_matter(src_doc.read_text(encoding="utf-8")) if src_doc.is_file() else {}
        if not meta.get("تاریخ انتشار"):
            print(f"⛔ {path}: زمان انتشار سند {src_doc} پیدا نشد — snap بی برش زمانی ممنوع",
                  file=sys.stderr)
            rc = 2
            continue
        published = parse_time(meta["تاریخ انتشار"])
        snaps = []
        for card in doc.get("cards") or []:
            if card.get("is_chart", True) is False:
                continue
            coin, tf_raw = _value(card.get("coin")), _value(card.get("timeframe"))
            cutoff, basis = card_cutoff(card, published)
            for lv in card.get("levels") or []:
                lv["snap"] = _with_basis(card_snap(coin, tf_raw, _value(lv.get("price")), cutoff, cached_fn,
                                                   venue=venue, cache_dir=cache_dir), basis)
                snaps.append(lv["snap"])
        errs = F.validate_cards(doc)
        if errs:
            print(f"⛔ {path}: کارت پس از snap نامعتبر شد — نوشته نشد:", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            rc = 2
            continue
        if not dry_run:
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        by_source.setdefault(str(doc.get("source")), []).extend(snaps)
        early = sum(1 for s in snaps if s.get("cutoff_basis") == "chart_end")
        unknown = sum(1 for s in snaps if s.get("cutoff_basis") == "chart_end_unknown")
        print(f"{'🔎' if dry_run else '✅'} {path.as_posix()} — {len(snaps)} سطح، انتشار {published.isoformat()}؛ "
              f"برش با پایان نمودار {early}، زمان نمودار نامعلوم {unknown}")
    for src, snaps in by_source.items():
        print(f"\n## {src}\n")
        print("\n".join(summary_lines(summarize(snaps))))
        daily = [s["daily"] for s in snaps if isinstance(s.get("daily"), dict)]
        if daily:
            d = summarize(daily)
            print(f"\nستون روزانه، سطح‌های زیر روزانه: {d['confirmed']} واقعی از {d['n']} با داده؛ "
                  f"{d['no_data']} بی‌داده.")
    return rc


# ═══════════════ ۹ — خط فرمان ═══════════════

def render_snap_md(s: dict) -> str:
    rows = [("حکم", snap_label(s)), ("نماد", s.get("symbol") or "—"), ("صرافی", s.get("venue") or "—"),
            ("تایم‌فریم", s.get("tf") or "—"), ("برش — انتشار ویدیو", s.get("cutoff")),
            ("آخرین کندل بسته", s.get("last_bar") or "—"), ("سطح", s.get("level")),
            ("پنجره / پهنا", f"{s.get('bars')} کندل / {s.get('width_atr')} دامنه واقعی"),
            ("شانس تصادفی پنجره", "—" if s.get("chance_pct") is None else f"{s['chance_pct']:.1f}%"),
            ("کمترین برخورد «قوی»", s.get("strong_min_touches") or "—")]
    lines = ["| مورد | مقدار |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    if isinstance(s.get("daily"), dict):
        lines.append(f"| روزانه، همان برش | {snap_label(s['daily'])} |")
    return "\n".join(lines) + "\n"


def _utf8_console() -> None:
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")


def _common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--venue", choices=("auto",) + VENUES, default="auto")
    ap.add_argument("--cache", default=str(CACHE_DIR), help="پوشه نهان‌گاه")
    ap.add_argument("--no-cache", action="store_true", dest="no_cache")


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv and argv[0] in ("snap", "cards") else "candles"
    ap = argparse.ArgumentParser(prog=f"radar_history.py {cmd}",
                                 description="کندل آزاد و وارسی سطح — نشست ۷ رادار")
    _common(ap)
    if cmd == "cards":
        ap.add_argument("paths", nargs="+")
        ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    else:
        ap.add_argument("--symbol", required=True)
        ap.add_argument("--tf", required=True)
    if cmd == "snap":
        ap.add_argument("--at", required=True, help="زمان انتشار ویدیو — برش")
        ap.add_argument("--level", type=float, required=True)
        ap.add_argument("--lookback", type=int, default=LOOKBACK)
        ap.add_argument("--width", type=float, default=WIDTH_ATR)
    if cmd == "candles":
        ap.add_argument("--from", dest="start", required=True)
        ap.add_argument("--to", dest="end")
        ap.add_argument("--csv", help="فایل CSV — فایل، نه پوشه")
        ap.add_argument("--out", help="فایل مارک‌داون — فایل، نه پوشه")
        ap.add_argument("--no-table", action="store_true", dest="no_table")
    a = ap.parse_args(argv)
    cache = None if a.no_cache else Path(a.cache)
    try:
        if cmd == "cards":
            return cards_cmd(a.paths, dry_run=a.dry_run, venue=a.venue, cache_dir=cache)
        if cmd == "snap":
            s = snap(a.symbol, a.tf, a.level, parse_time(a.at), venue=a.venue, cache_dir=cache,
                     lookback=a.lookback, width_atr=a.width)
            print(render_snap_md(s))
            return 0
        for p in (a.out, a.csv):
            if p and Path(p).is_dir():
                print(f"⛔ {p} پوشه است — --out و --csv مسیر فایل می‌گیرند", file=sys.stderr)
                return 2
        end = parse_time(a.end, end=True) if a.end else datetime.now(UTC)
        s = history(a.symbol, a.tf, parse_time(a.start), end, venue=a.venue, cache_dir=cache)
    except (HistoryError, ValueError) as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 2
    md = render_md(s, table=not a.no_table)
    if a.csv:
        write_csv(s, Path(a.csv))
        print(f"✅ {a.csv}", file=sys.stderr)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"✅ {a.out}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
