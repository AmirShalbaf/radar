#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_events.py — تقویم رویداد، آزادسازی توکن و دفتر رویداد، نشست ۱۰ رادار ۷
==============================================================================

چرا این فایل نوشته شد
---------------------
رادار تقویم نداشت. تصمیم فدرال‌رزرو، تورم و اشتغال بازار را جابه‌جا می‌کنند، و
آزادسازی بزرگ توکن در افق معامله ستاپ را می‌کشد — کتابخانه ستاپ، قاتل ب‌۱. شرط
آزادسازی radar_fetch3 هم از ۹ اوت با کد ۴۰۲ خاموش بود — ک۸۷.

منبع‌ها — ایستگاه ۱، رویداد ۸۷
------------------------------
    تصمیم و صورت‌جلسه فدرال‌رزرو   federalreserve.gov/json/calendar.json، وقت شرقی آمریکا
    تورم، اشتغال، شاخص تولیدکننده  FRED، برنامه BLS را بی‌تغییر بازنشر می‌کند؛ وقت مرکزی
    وارسی متقاطع PCE              ICS رسمی BEA — ناهمخوانی خطای صریح است، ف۳۲
    آزادسازی                       داده عمومی DefiLlama؛ شاخص برای نگاشت نماد — ف۳۳
    عرضه در گردش                   CoinGecko، یک درخواست دسته‌ای
    قیمت دفتر رویداد              radar_history.py — کندل ۱ ساعته بسته، اوکی‌اکس اول

وتو — ف۳۱، تصمیم کاربر
---------------------
آزادسازی «بزرگ» در ۳۰ روز آینده: یک پله دست‌کم ۱٪ عرضه در گردش، یا جمع دست‌کم ۲٪.
پاداش استیکینگ و استخراج شمرده نمی‌شود. «داده ناقص» یعنی «نامعلوم» — بررسی دستی
پیش از ورود، نه رد خودکار و نه عبور. وتوی شناخته‌شده بر نامعلوم می‌چربد.

دفتر رویداد
-----------
events_ledger.json: هر رویداد با قیمت پیش، ۲۴ ساعت و ۷ روز — بسته کندل ۱ ساعته‌ای
که در آن لحظه بسته می‌شود. فقط پس از سررسید، از تاریخچه؛ اجرای جاافتاده روز بعد
پر می‌شود. شکست با دلیل ثبت و دوباره امتحان می‌شود — هرگز تخمین.

خروجی
-----
گزارش کامل، بخش «رویدادهای ۱۴ روز آینده» برای LATEST.md، و یک خط ساده برای پیام
تلگرام. منبعی که نیامد کد ۲ می‌دهد، ولی گزارش نوشته می‌شود؛ رویداد کلان آن منبع
از دفتر خوانده می‌شود، با برچسب.

نمونه اجرا
----------
    python radar_events.py
    python radar_events.py --out reports/events-2026-10-08.md --section /tmp/s.md --line /tmp/l.txt
"""

from __future__ import annotations

import argparse
import bisect
import html as _html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

VERSION = "1.0"
UTC = timezone.utc
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
UA = "radar-events/1.0 (+https://github.com/AmirShalbaf/radar)"
TIMEOUT = 60
LEDGER_FILE = "events_ledger.json"

FED_CALENDAR = "https://www.federalreserve.gov/json/calendar.json"
FRED_CAL = "https://fred.stlouisfed.org/releases/calendar?rid={rid}&vs={vs}&ve={ve}"
BEA_ICS = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
LLAMA_INDEX = "https://defillama-datasets.llama.fi/emissionsIndex"
LLAMA_PROTOCOL = "https://defillama-datasets.llama.fi/emissions/{slug}"
CG_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

# ── تصمیم‌های کاربر، ایستگاه ۱ — رویداد ۸۷ ──
HORIZON_DAYS = 30                 # افق وتو و تقویم کامل
SECTION_DAYS = 14                 # بخش LATEST.md و خط تلگرام
LOOKBACK_DAYS = 8                 # رویداد گذشته هنوز ثبت می‌شود تا ۷ روزش پر شود
VETO_SINGLE_PCT = 1.0             # ف۳۱
VETO_TOTAL_PCT = 2.0              # ف۳۱
LEDGER_MIN_PCT = 0.1              # پله‌ها از ۰.۱٪ در دفتر، تا مرز ۱٪ از دو طرف داده بگیرد
EMISSION_CATEGORIES = {"staking", "farming"}
# متن قاعده برای گزارش — رقم فارسی، چون آستانه است نه داده
RULE = (f"تک‌پله {fa(f'{VETO_SINGLE_PCT:g}')}٪ یا جمع {fa(f'{VETO_TOTAL_PCT:g}')}٪ عرضه در "
        f"گردش در {fa(HORIZON_DAYS)} روز")
NO_SCHEDULE = {"BNB":"زمان‌بندی آزادسازی ندارد؛ «قفل» DefiLlama برای BNB توکن سوزانده "
                      "است — تصمیم کاربر، رویداد ۸۷"}

# نوع، عنوان، اهمیت
KINDS = {
    "fomc": ("تصمیم فدرال‌رزرو (FOMC)", "high"),
    "fomc_minutes": ("صورت‌جلسه فدرال‌رزرو (FOMC Minutes)", "medium"),
    "cpi": ("تورم مصرف‌کننده (CPI)", "high"),
    "nfp": ("اشتغال (Employment Situation)", "high"),
    "pce": ("تورم مصرف شخصی (PCE)", "medium"),
    "ppi": ("شاخص قیمت تولیدکننده (PPI)", "medium"),
}
SHORT = {"fomc": "تصمیم فدرال‌رزرو", "cpi": "تورم مصرف‌کننده", "nfp": "اشتغال"}
FRED_RIDS = {"cpi": 10, "nfp": 50, "pce": 54, "ppi": 46}
FRED_NAMES = {"cpi": "Consumer Price Index", "nfp": "Employment Situation",
              "pce": "Personal Income and Outlays", "ppi": "Producer Price Index"}
IMPORTANCE = {"high": "بالا", "medium": "میانه"}
VERDICT = {"veto": "⛔ وتو", "pass": "✅ عبور", "unknown": "❔ نامعلوم"}
G_PORT, G_WATCH, G_CAND = "سبد", "واچ‌لیست", "نامزد اسکنر"
POINTS = {"before": 0, "h24": 24, "d7": 24 * 7}       # ساعت پس از رویداد
DUE_MARGIN = timedelta(minutes=5)                       # کندل تازه‌بسته فرصت انتشار بگیرد
MONTHS = {m: i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"), 1)}


# ═══════════════ کمکی زمان ═══════════════

def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _hm(s: str) -> str:
    """«2026-10-28T18:00:00Z» ← «2026-10-28 18:00»"""
    return f"{s[:10]} {s[11:16]}"


def _ge(a: float, b: float) -> bool:
    """مرز آستانه شامل است — تصمیم «دست‌کم»؛ خطای ممیز شناور ۲٪ را ۱.۹۹۹۹ نکند."""
    return a >= b - 1e-9


def _event(kind: str, when: datetime, source: str) -> dict:
    title, imp = KINDS[kind]
    at = iso(when)
    return {"id": f"{kind}:{at[:10]}", "kind": kind, "title": title, "importance": imp,
            "at": at, "source": source}


# ═══════════════ تقویم کلان ═══════════════

_FED_TIME = re.compile(r"^([0-9]{1,2}):([0-9]{2})\s*([ap])\.?\s*m\.?$", re.I)
_FED_MONTH = re.compile(r"^([0-9]{4})-([0-9]{2})$")


def parse_fed_calendar(doc: dict) -> list[dict]:
    """
    تصمیم و صورت‌جلسه فدرال‌رزرو از calendar.json. «FOMC Meeting» روز دوم جلسه است
    با ساعت اعلام؛ نشست خبری همان روز است و جدا ثبت نمی‌شود. ساعت نامعلوم یعنی
    رویداد ثبت نمی‌شود — حدس زده نمی‌شود.
    """
    out: dict[str, dict] = {}
    for e in (doc or {}).get("events") or []:
        if e.get("type") != "FOMC":
            continue
        title = (e.get("title") or "").strip()
        kind = {"FOMC Meeting": "fomc", "FOMC Minutes": "fomc_minutes"}.get(title)
        if kind is None:
            continue
        m = _FED_MONTH.match(e.get("month") or "")
        days = re.findall(r"[0-9]{1,2}", e.get("days") or "")
        t = _FED_TIME.match((e.get("time") or "").strip())
        if not (m and days and t):
            continue
        hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "p" else 0)
        when = datetime(int(m.group(1)), int(m.group(2)), int(days[-1]), hour,
                        int(t.group(2)), tzinfo=ET)
        ev = _event(kind, when, "federalreserve.gov/json/calendar.json")
        out[ev["id"]] = ev
    return sorted(out.values(), key=lambda x: x["at"])


_FRED_DATE = re.compile(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
                        r"([A-Z][a-z]+) ([0-9]{1,2}), ([0-9]{4})")
_FRED_TIME = re.compile(r"(?<![0-9:])([0-9]{1,2}):([0-9]{2}) (am|pm)\b")
_FRED_LINK = re.compile(r"<a[^>]*[?&]rid=([0-9]+)[^>]*>([^<]+)</a>")


def parse_fred_calendar(html: str, kind: str) -> list[dict]:
    """
    یک انتشار از جدول تقویم FRED: سرتیتر روز، ساعت به وقت مرکزی، پیوند انتشار. هر
    پیوند فقط وقتی رویداد است که شناسه و نامش همان انتشار باشد — پیوند صفحه‌بندی هم
    rid دارد.
    """
    rid, name = FRED_RIDS[kind], FRED_NAMES[kind]
    toks = ([(m.start(), "d", m) for m in _FRED_DATE.finditer(html)]
            + [(m.start(), "t", m) for m in _FRED_TIME.finditer(html)]
            + [(m.start(), "a", m) for m in _FRED_LINK.finditer(html)])
    day = hm = None
    out: dict[str, dict] = {}
    for _, k, m in sorted(toks, key=lambda x: x[0]):
        if k == "d":
            mon = MONTHS.get(m.group(1))
            day = (int(m.group(3)), mon, int(m.group(2))) if mon else None
            hm = None
        elif k == "t":
            hm = (int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0), int(m.group(2)))
        elif day and hm and int(m.group(1)) == rid \
                and _html.unescape(m.group(2)).strip() == name:
            when = datetime(*day, *hm, tzinfo=CT)
            ev = _event(kind, when, f"fred.stlouisfed.org rid={rid} — برنامه BLS/BEA")
            out[ev["id"]] = ev
    return sorted(out.values(), key=lambda x: x["at"])


def parse_bea_ics(text: str) -> dict[str, str]:
    """زمان انتشار «Personal Income and Outlays» از ICS رسمی BEA — روز ← مهر وقت جهانی."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]                     # تاکردن خط ICS
        else:
            lines.append(raw)
    out, ev = {}, None
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            ev = {}
        elif ln == "END:VEVENT" and ev is not None:
            if ev.get("summary", "").startswith("Personal Income and Outlays") and ev.get("at"):
                out[ev["at"][:10]] = ev["at"]
            ev = None
        elif ev is not None and ":" in ln:
            key, val = ln.split(":", 1)
            name, *params = key.split(";")
            if name == "SUMMARY":
                ev["summary"] = val.replace("\\,", ",").replace("\\;", ";")
            elif name == "DTSTART":
                m = re.match(r"([0-9]{8})T([0-9]{6})(Z?)$", val)
                if not m:
                    continue
                naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                tz = UTC
                if not m.group(3):
                    tzid = next((p[5:] for p in params if p.startswith("TZID=")), None)
                    if tzid is None:
                        continue                     # ساعت محلی بی‌منطقه — حدس زده نمی‌شود
                    tz = ZoneInfo(tzid)
                ev["at"] = iso(naive.replace(tzinfo=tz))
    return out


def pce_conflicts(events: list[dict], bea: dict[str, str]) -> list[str]:
    """وارسی متقاطع PCE — ف۳۲. هر ناهمخوانی یک سطر خطای صریح."""
    out = []
    for e in events:
        if e["kind"] != "pce":
            continue
        d = e["at"][:10]
        if d not in bea:
            out.append(f"⛔ PCE {d}: در ICS رسمی BEA نیست — تاریخ FRED وارسی نشد")
        elif bea[d] != e["at"]:
            out.append(f"⛔ PCE {d}: FRED {e['at'][11:16]} UTC، BEA {bea[d][11:16]} UTC — "
                       "ناهمخوان")
    return out


# ═══════════════ آزادسازی ═══════════════

def window_unlocks(doc: dict, now: datetime, days: int) -> dict:
    """
    آزادسازی پنجره (اکنون، اکنون + days]. جمع هر دسته از سری روزانه آزادشده تجمعی —
    پله و خطی هر دو؛ پله‌ها از unlockEvents، با مقدار بی‌پاداش، جمع روز وقت جهانی.
    cover_end آخرین روزی است که DefiLlama مدل کرده.
    """
    t0, t1 = now.timestamp(), (now + timedelta(days=days)).timestamp()
    cats = {lab: cat for cat, labs in (doc.get("categories") or {}).items() for lab in labs}
    by_cat: dict[str, float] = {}
    cover = 0
    for ser in (doc.get("documentedData") or {}).get("data") or []:
        pts = sorted(ser.get("data") or [], key=lambda p: p["timestamp"])
        if not pts:
            continue
        ts = [p["timestamp"] for p in pts]
        cover = max(cover, ts[-1])

        def at(t):
            i = bisect.bisect_right(ts, t) - 1
            return float(pts[i]["unlocked"] or 0.0) if i >= 0 else 0.0
        dv = at(t1) - at(t0)
        if dv:
            cat = cats.get(ser.get("label"), "?")
            by_cat[cat] = by_cat.get(cat, 0.0) + dv
    days_: dict[str, dict] = {}
    for u in (doc.get("metadata") or {}).get("unlockEvents") or []:
        t = u.get("timestamp")
        if not isinstance(t, (int, float)) or not t0 < t <= t1:
            continue
        for a in u.get("cliffAllocations") or []:
            cat = a.get("category") or "?"
            amt = float(a.get("amount") or 0.0)
            if cat in EMISSION_CATEGORIES or amt <= 0:
                continue
            # زمان پله تقریبی و ثانیه‌دار است؛ گرد به ساعت — قیمت دفتر هم از کندل
            # ساعتی است، پس سنجش عوض نمی‌شود و لرزش ثانیه‌ای «بازنگری» نمی‌سازد
            d = datetime.fromtimestamp(t, UTC).replace(minute=0, second=0, microsecond=0)
            rec = days_.setdefault(d.strftime("%Y-%m-%d"),
                                   {"day": d.strftime("%Y-%m-%d"), "at": iso(d), "tokens": 0.0,
                                    "cats": set()})
            rec["tokens"] += amt
            rec["cats"].add(cat)
            rec["at"] = min(rec["at"], iso(d))
    cliffs = [dict(r, cats=sorted(r["cats"])) for _, r in sorted(days_.items())]
    return {"by_cat": by_cat, "cliffs": cliffs,
            "cover_end": datetime.fromtimestamp(cover, UTC) if cover else None}


def unlock_verdict(sym: str, entry: dict | None, doc: dict | None, circ: float | None,
                   now: datetime, days: int = HORIZON_DAYS,
                   missing: str = "در DefiLlama نیست") -> dict:
    """حکم وتوی آزادسازی یک نماد — ف۳۱. وتو، عبور، یا نامعلوم با دلیل."""
    v = {"symbol": sym, "status": "unknown", "why": "", "single_max": None, "total": None,
         "emission": None, "cliffs": [], "cover_end": None,
         "slug": (entry or {}).get("protocolSlug")}
    if sym in NO_SCHEDULE:
        return dict(v, status="pass", why=NO_SCHEDULE[sym])
    if entry is None:
        return dict(v, why=missing)
    if doc is None:
        return dict(v, why="پرونده DefiLlama نیامد")
    if not circ or circ <= 0:
        return dict(v, why="عرضه در گردش CoinGecko نیامد")
    w = window_unlocks(doc, now, days)
    pct = lambda x: 100.0 * x / circ                                     # noqa: E731
    emission = sum(x for c, x in w["by_cat"].items() if c in EMISSION_CATEGORIES)
    total = sum(x for c, x in w["by_cat"].items() if c not in EMISSION_CATEGORIES)
    cliffs = [dict(c, pct=pct(c["tokens"])) for c in w["cliffs"]]
    big = max(cliffs, key=lambda c: c["pct"], default=None)
    v.update(single_max=big["pct"] if big else 0.0, total=pct(total), emission=pct(emission),
             cliffs=cliffs, cover_end=w["cover_end"])
    head = (f"بزرگ‌ترین پله {big['pct']:.2f}٪ در {big['day']}" if big else "بی پله") + \
        f"؛ جمع بی‌پاداش {v['total']:.2f}٪"
    if _ge(v["single_max"], VETO_SINGLE_PCT) or _ge(v["total"], VETO_TOTAL_PCT):
        return dict(v, status="veto", why=head)
    end = now + timedelta(days=days)
    cover = w["cover_end"]
    if cover is None or cover < end:
        till = cover.strftime("%Y-%m-%d") if cover else "هیچ"
        locked = entry.get("totalLocked")
        if not isinstance(locked, (int, float)):
            return dict(v, why=f"پوشش DefiLlama تا {till}؛ قفل باقی‌مانده نامعلوم")
        lp = pct(max(float(locked), 0.0))
        if _ge(lp, VETO_SINGLE_PCT):
            return dict(v, why=f"پوشش DefiLlama تا {till}؛ قفل بی‌زمان‌بندی {lp:.1f}٪ "
                               "عرضه در گردش")
        return dict(v, status="pass",
                    why=f"{head}؛ پوشش تا {till}، باقی‌مانده قفل {lp:.2f}٪ — زیر آستانه")
    return dict(v, status="pass", why=head)


def index_by_symbol(doc: dict) -> dict[str, list[dict]]:
    """شاخص DefiLlama ← نماد به پرونده‌ها. پرونده بی‌نام پرونده کنار می‌رود."""
    out: dict[str, list[dict]] = {}
    for e in (doc or {}).get("data") or []:
        if not e.get("protocolSlug"):
            continue
        sym = (((e.get("tokenPrice") or [{}])[0] or {}).get("symbol") or "").upper()
        if sym:
            out.setdefault(sym, []).append(e)
    return out


def pick_entry(sym: str, m: dict, cg_ids: dict) -> tuple[dict | None, str | None]:
    """یک پرونده برای نماد؛ چند پرونده فقط با شناسه CoinGecko همان نماد جدا می‌شود."""
    es = m.get(sym) or []
    if not es:
        return None, "در DefiLlama نیست"
    if len(es) == 1:
        return es[0], None
    hit = [e for e in es if cg_ids.get(sym) and e.get("gecko_id") == cg_ids.get(sym)]
    if len(hit) == 1:
        return hit[0], None
    return None, "نگاشت مبهم در DefiLlama: " + "، ".join(e["protocolSlug"] for e in es)


# ═══════════════ نمادها ═══════════════

def portfolio_symbols(path: str) -> list[str]:
    """نمادهای پوزیشن باز هر دو دفتر — همان radar_positions.py symbols."""
    import radar_positions as P
    h, _ = P.load(path)
    return list(dict.fromkeys(p["symbol"] for p in h["positions"] if p["status"] == "open"))


def watchlist() -> list[str]:
    import radar_scan
    return list(radar_scan.PRESETS["watch"])


def _cg_ids() -> dict:
    import radar_fetch3 as R
    return dict(R.CG_IDS)


_ROT_ROW = re.compile(r"^\| [0-9]+ \| \*\*([A-Z0-9]+)\*\*", re.M)
_ROT_NAME = re.compile(r"^rotate-([0-9]{4}-[0-9]{2}-[0-9]{2})\.md$")


def rotate_candidates(reports_dir) -> tuple[list[str], str | None]:
    """
    نامزدهای آخرین غربال چرخش. نام rotate-<تاریخ>.md گاهی پوشه است — ک۲۴ و ک۱۴،
    کلید --out؛ آن‌وقت فایل داخلش خوانده می‌شود.
    """
    d = Path(reports_dir)
    found = sorted(((m.group(1), p) for p in (d.iterdir() if d.is_dir() else [])
                    if (m := _ROT_NAME.match(p.name))), key=lambda x: x[0])
    for _, p in reversed(found):
        f = p if p.is_file() else next(iter(sorted(p.glob("*.md"), reverse=True)), None)
        if f is None:
            continue
        syms = list(dict.fromkeys(_ROT_ROW.findall(f.read_text(encoding="utf-8"))))
        return syms, str(f).replace("\\", "/")
    return [], None


# ═══════════════ دفتر رویداد ═══════════════

def load_ledger(path: str) -> dict:
    """فایل غایب یعنی دفتر تازه؛ فایل خراب خطای صریح است — بازنشانی بی‌صدا نه."""
    if not os.path.exists(path):
        return {"version": 1, "events": []}
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or not isinstance(doc.get("events"), list):
        raise ValueError(f"{path}: قالب دفتر رویداد نیست")
    return doc


def save_ledger(path: str, doc: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


def upsert(ledger: dict, events: list[dict], now: datetime, macro_symbols: list[str]) -> None:
    """
    رویداد تازه با first_seen و جای خالی قیمت‌ها. کلان با بیت‌کوین و نمادهای سبد همان
    روز، آزادسازی با خود نماد و بیت‌کوین. جابه‌جایی زمان در revised ثبت می‌شود و
    قیمت‌ها از نو — قیمت پیش زمان قدیم دیگر «پیش» نیست.
    """
    have = {e["id"]: e for e in ledger["events"]}
    for ev in events:
        old = have.get(ev["id"])
        if old is None:
            syms = ([ev["symbol"], "BTC"] if ev["kind"] == "unlock"
                    else list(dict.fromkeys(["BTC"] + list(macro_symbols))))
            new = dict(ev, first_seen=iso(now),
                       prices={s: {p: None for p in POINTS} for s in dict.fromkeys(syms)})
            ledger["events"].append(new)
            have[ev["id"]] = new
            continue
        if old["at"] != ev["at"]:
            old.setdefault("revised", []).append({"from": old["at"], "seen": iso(now)})
            for s in old["prices"]:
                old["prices"][s] = {p: None for p in POINTS}
        for k, val in ev.items():
            if k not in ("id", "first_seen", "prices", "revised"):
                old[k] = val
    ledger["events"].sort(key=lambda e: (e["at"], e["id"]))


def _close_at(at: datetime, hours: int) -> datetime:
    t = at + timedelta(hours=hours)
    return t.replace(minute=0, second=0, microsecond=0)


def fill_prices(ledger: dict, now: datetime, history) -> list[str]:
    """
    قیمت‌های سررسیده و خالی. نقطه = بسته کندل ۱ ساعته‌ای که در ساعت گردشده پایین آن
    لحظه بسته می‌شود؛ «پیش» یعنی آخرین کندل بسته پیش از رویداد. شکست با دلیل در خود
    نقطه می‌ماند و اجرای بعد دوباره امتحان می‌شود.
    """
    notes = []
    for ev in ledger["events"]:
        at = parse_iso(ev["at"])
        for sym, pts in ev.get("prices", {}).items():
            for name, hrs in POINTS.items():
                cur = pts.get(name)
                if cur is not None and "close" in cur:
                    continue
                close_at = _close_at(at, hrs)
                if now < close_at + DUE_MARGIN:
                    continue
                open_ = close_at - timedelta(hours=1)
                try:
                    s = history(sym, "1h", open_, open_)
                    df = s.df
                    row = df[(df["ts"] == open_) & (df["confirm"] == 1)]
                    if row.empty:
                        raise LookupError(f"کندل بسته {iso(open_)} نیامد")
                    pts[name] = {"close": float(row["close"].iloc[-1]),
                                 "candle_open": iso(open_), "venue": s.venue}
                except Exception as exc:
                    why = f"{type(exc).__name__}: {str(exc)[:200]}"
                    pts[name] = {"error": why, "tried_at": iso(now)}
                    notes.append(f"⚠️ دفتر رویداد: {sym} {name} برای {ev['id']} — {why}")
    return notes


# ═══════════════ شبکه ═══════════════

def _fetch(get, url: str, label: str, params: dict | None = None):
    """یک GET با یک تلاش دوباره برای ۴۲۹ و ۵xx. خروجی: پاسخ، یا None و دلیل."""
    last = ""
    for attempt in range(2):
        try:
            r = get(url, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
        except Exception as exc:
            last = f"{label}: {type(exc).__name__} — {str(exc)[:160]}"
        else:
            if r.status_code == 200:
                return r, None
            last = f"{label}: کد {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        if attempt == 0:
            time.sleep(PAUSE_RETRY)
    return None, last


PAUSE_RETRY = 3.0


def _json(get, url, label, params=None):
    r, err = _fetch(get, url, label, params)
    if err:
        return None, err
    try:
        return r.json(), None
    except ValueError:
        pass
    # calendar.json فدرال‌رزرو با BOM آغاز می‌شود — r.json() آن را نمی‌خواند
    try:
        return json.loads(r.content.decode("utf-8-sig")), None
    except (ValueError, UnicodeDecodeError):
        return None, f"{label}: پاسخ JSON نیست"


def _text(get, url, label):
    r, err = _fetch(get, url, label)
    return (None, err) if err else (r.text, None)


def circulating(get, ids: list[str]) -> tuple[dict, str | None]:
    """عرضه در گردش CoinGecko — یک درخواست دسته‌ای برای همه شناسه‌ها."""
    if not ids:
        return {}, None
    out, errs = {}, []
    for i in range(0, len(ids), 200):
        doc, err = _json(get, CG_MARKETS, "CoinGecko",
                         {"vs_currency": "usd", "ids": ",".join(ids[i:i + 200]),
                          "per_page": 250, "page": 1})
        if err:
            errs.append(err)
            continue
        for c in doc or []:
            if isinstance(c, dict) and isinstance(c.get("circulating_supply"), (int, float)):
                out[c["id"]] = float(c["circulating_supply"])
    return out, ("؛ ".join(errs) or None)


def unlock_verdicts(syms: list[str], get, now: datetime,
                    days: int = HORIZON_DAYS) -> tuple[dict, list[str], list[tuple[str, str]]]:
    """
    حکم وتوی همه نمادها: احکام، هشدارها و وضعیت منبع‌ها. هشدار «⛔» یعنی منبعی
    نیامد؛ حکم نمادهای آن منبع «نامعلوم» است، با دلیل.
    """
    verdicts: dict[str, dict] = {}
    notes: list[str] = []
    sources: list[tuple[str, str]] = []
    index, err = _json(get, LLAMA_INDEX, "DefiLlama شاخص")
    if err:
        notes.append(f"⛔ شاخص DefiLlama نیامد — حکم آزادسازی نامعلوم: {err}")
        sources.append(("DefiLlama — شاخص آزادسازی", f"⛔ {err}"))
        for s in syms:
            verdicts[s] = unlock_verdict(s, None, None, None, now, days,
                                         missing="شاخص DefiLlama نیامد")
        return verdicts, notes, sources
    sources.append(("DefiLlama — شاخص آزادسازی", "✅"))
    m, cg = index_by_symbol(index), _cg_ids()
    picks = {s: pick_entry(s, m, cg) for s in syms}
    gecko = {s: (e or {}).get("gecko_id") or cg.get(s) for s, (e, _) in picks.items()}
    circ, cerr = circulating(get, sorted({g for g in gecko.values() if g}))
    if cerr:
        notes.append(f"⛔ عرضه در گردش CoinGecko نیامد — {cerr}")
    sources.append(("CoinGecko — عرضه در گردش", f"⛔ {cerr}" if cerr else "✅"))
    miss = []
    for s, (e, why) in picks.items():
        pdoc = None
        if e is not None and s not in NO_SCHEDULE:
            pdoc, perr = _json(get, LLAMA_PROTOCOL.format(slug=e["protocolSlug"]),
                               f"DefiLlama {e['protocolSlug']}")
            if perr:
                miss.append(perr)
        verdicts[s] = unlock_verdict(s, e, pdoc, circ.get(gecko[s] or ""), now, days,
                                     missing=why or "در DefiLlama نیست")
    if miss:
        notes.append("⛔ پرونده DefiLlama نیامد — " + "؛ ".join(miss))
    sources.append(("DefiLlama — پرونده هر نماد", f"⛔ {len(miss)} نیامد" if miss else "✅"))
    return verdicts, notes, sources


def symbol_unlock(sym: str, get=None, now: datetime | None = None) -> dict:
    """حکم یک نماد — برای شرط آزادسازی radar_fetch3، ک۸۷. همان منبع و همان قاعده."""
    if get is None:
        import requests
        get = requests.Session().get
    now = (now or datetime.now(UTC)).astimezone(UTC)
    return unlock_verdicts([sym.upper()], get, now)[0][sym.upper()]


# ═══════════════ خروجی ═══════════════

def _groups_of(sym: str, groups: dict) -> str:
    return "، ".join(groups.get(sym, []))


def _pct(x) -> str:
    return "—" if x is None else f"{x:.2f}"


def _plain(s: str) -> str:
    """متن ساده تلگرام: بی نویسه‌های قالب Markdown پیام فعلی."""
    return re.sub(r"[*_`\[\]]", "", s.replace("\n", " ")).strip()


def telegram_line(macro: list[dict], verdicts: dict, groups: dict, now: datetime,
                  prefix: str = "") -> str:
    end = iso(now + timedelta(days=SECTION_DAYS))
    hi = [e for e in macro if e["importance"] == "high" and iso(now) <= e["at"] <= end]
    mtxt = "، ".join(f"{SHORT.get(e['kind'], e['title'])} {_hm(e['at'])} UTC" for e in hi) \
        or "رویداد کلان مهمی نیست"
    port = [s for s in verdicts if G_PORT in groups.get(s, [])]
    pv = [s for s in port if verdicts[s]["status"] == "veto"]
    pu = [s for s in port if verdicts[s]["status"] == "unknown"]
    nv = [s for s in verdicts if s not in port and verdicts[s]["status"] == "veto"]
    txt = (f"{prefix}رویداد {fa(SECTION_DAYS)} روز: {mtxt}؛ آزادسازی بزرگ سبد: "
           f"{'، '.join(pv) or 'هیچ'}")
    if pu:
        txt += f"؛ نامعلوم سبد: {'، '.join(pu)}"
    txt += f"؛ وتوی آزادسازی واچ‌لیست و نامزدها: {'، '.join(nv) or 'هیچ'}"
    return _plain(txt)


def _macro_rows(macro: list[dict], start: str, end: str, with_src: bool) -> list[str]:
    rows = []
    for e in macro:
        if not start <= e["at"] <= end:
            continue
        r = f"| {_hm(e['at'])} | {e['title']} | {IMPORTANCE[e['importance']]} |"
        if with_src:
            src = (f"از دفتر — واکشی {e['from_ledger'][:10]}" if e.get("from_ledger")
                   else e["source"])
            r += f" {src} |"
        rows.append(r)
    return rows


def render_section(macro, verdicts, groups, now, report_path: str) -> str:
    start, end = iso(now), iso(now + timedelta(days=SECTION_DAYS))
    o = [f"## رویدادهای {fa(SECTION_DAYS)} روز آینده", "",
         "| زمان (UTC) | رویداد | اهمیت |", "|---|---|---|"]
    rows = _macro_rows(macro, start, end, False)
    port = [s for s in verdicts if G_PORT in groups.get(s, [])]
    for s in port:
        for c in verdicts[s]["cliffs"]:
            if start <= c["at"] <= end and _ge(c["pct"], LEDGER_MIN_PCT):
                rows.append(f"| {_hm(c['at'])} | آزادسازی {s} — {c['pct']:.2f}٪ عرضه در گردش | "
                            f"{'بالا' if _ge(c['pct'], VETO_SINGLE_PCT) else 'میانه'} |")
    o += sorted(rows) or [f"| — | هیچ رویدادی در {fa(SECTION_DAYS)} روز آینده | — |"]
    o += ["", f"### آزادسازی نمادهای سبد — {fa(HORIZON_DAYS)} روز", "",
          "| نماد | حکم | بزرگ‌ترین پله ٪ | جمع بی‌پاداش ٪ | دلیل |", "|---|---|---|---|---|"]
    for s in port:
        v = verdicts[s]
        o.append(f"| {s} | {VERDICT[v['status']]} | {_pct(v['single_max'])} | "
                 f"{_pct(v['total'])} | {v['why'] or '—'} |")
    o += ["", f"آستانه وتو: {RULE} — ف۳۱. گزارش کامل: `{report_path}`", ""]
    return "\n".join(o)


def render_report(macro, verdicts, groups, now, sources, ledger, notes,
                  cand_src: str | None = None) -> str:
    start, end = iso(now), iso(now + timedelta(days=HORIZON_DAYS))
    o = [f"# تقویم رویداد و آزادسازی — {now:%Y-%m-%d}", "",
         f"`radar_events.py` {VERSION} — نشست ۱۰ رادار ۷.", "",
         "| مورد | مقدار |", "|---|---|",
         f"| زمان | {now:%Y-%m-%d %H:%M} UTC |",
         f"| آستانه وتو | {RULE} — ف۳۱ |",
         "| پاداش | استیکینگ و استخراج در وتو شمرده نمی‌شود |",
         "| داده ناقص | «نامعلوم» — بررسی دستی پیش از ورود، نه رد خودکار |",
         f"| نامزدهای اسکنر | {('`' + cand_src + '`') if cand_src else 'گزارش چرخش نیست'} |", ""]
    if notes:
        o += ["## هشدار", ""] + [f"- {n}" for n in notes] + [""]
    o += [f"## ۱ — تقویم کلان {fa(HORIZON_DAYS)} روز آینده", "",
          "| زمان (UTC) | رویداد | اهمیت | منبع |", "|---|---|---|---|"]
    o += _macro_rows(macro, start, end, True) or ["| — | داده ندارم | — | — |"]
    o += ["", f"## ۲ — وتوی آزادسازی {fa(HORIZON_DAYS)} روز آینده", "",
          "| نماد | گروه | حکم | بزرگ‌ترین پله ٪ | روز پله | جمع بی‌پاداش ٪ | پاداش ٪ | دلیل |",
          "|---|---|---|---|---|---|---|---|"]
    order = {"veto": 0, "unknown": 1, "pass": 2}
    for s in sorted(verdicts, key=lambda x: (order[verdicts[x]["status"]], x)):
        v = verdicts[s]
        big = max(v["cliffs"], key=lambda c: c["pct"], default=None)
        o.append(f"| {s} | {_groups_of(s, groups)} | {VERDICT[v['status']]} | "
                 f"{_pct(v['single_max'])} | {big['day'] if big else '—'} | {_pct(v['total'])} | "
                 f"{_pct(v['emission'])} | {v['why'] or '—'} |")
    o += ["", f"## ۳ — پله‌های آزادسازی {fa(HORIZON_DAYS)} روز آینده — از ۰.۱٪", "",
          "| روز | نماد | ٪ عرضه در گردش | توکن | گیرنده |", "|---|---|---|---|---|"]
    steps = sorted(((c["day"], s, c) for s, v in verdicts.items() for c in v["cliffs"]
                    if _ge(c["pct"], LEDGER_MIN_PCT)), key=lambda x: (x[0], x[1]))
    o += [f"| {d} | {s} | {c['pct']:.2f} | {c['tokens']:,.0f} | {'، '.join(c['cats'])} |"
          for d, s, c in steps] or ["| — | هیچ | — | — | — |"]
    evs = ledger.get("events", [])
    done = {p: sum(1 for e in evs for x in e.get("prices", {}).values()
                   if x.get(p) and "close" in x[p]) for p in POINTS}
    o += ["", "## ۴ — دفتر رویداد", "",
          f"`{LEDGER_FILE}`: {len(evs)} رویداد. قیمت پرشده — پیش {done['before']}، ۲۴ ساعت "
          f"{done['h24']}، ۷ روز {done['d7']}. نماد اصلی: بیت‌کوین برای کلان، خود نماد برای "
          "آزادسازی.", "",
          "| رویداد | زمان (UTC) | نماد | پیش | ۲۴ ساعت | ۷ روز |", "|---|---|---|---|---|---|"]
    past = [e for e in evs if e["at"] <= iso(now)][-15:]
    for e in past:
        sym = e.get("symbol") or "BTC"
        p = e.get("prices", {}).get(sym, {})
        base = (p.get("before") or {}).get("close")

        def cell(name):
            x = p.get(name) or {}
            if "close" not in x:
                return "خطا" if "error" in x else "—"
            if base:
                return f"{x['close']:.10g} ({100 * (x['close'] / base - 1):+.2f}٪)"
            return f"{x['close']:.10g}"
        o.append(f"| `{e['id']}` | {_hm(e['at'])} | {sym} | "
                 f"{f'{base:.10g}' if base else cell('before')} | {cell('h24')} | {cell('d7')} |")
    if not past:
        o.append("| — | — | — | — | — | — |")
    o += ["", "## ۵ — منبع‌ها", "", "| منبع | وضعیت |", "|---|---|"]
    o += [f"| {n} | {s} |" for n, s in sources]
    return "\n".join(o) + "\n"


# ═══════════════ main ═══════════════

def _cached(ledger: dict, kinds: set, start: str, end: str) -> list[dict]:
    out = []
    for e in ledger.get("events", []):
        if e["kind"] in kinds and start <= e["at"] <= end:
            out.append({k: e[k] for k in ("id", "kind", "title", "importance", "at", "source")}
                       | {"from_ledger": e.get("first_seen", "")})
    return out


def main(argv=None, get=None, now: datetime | None = None, history=None) -> int:
    ap = argparse.ArgumentParser(description="تقویم رویداد، آزادسازی و دفتر رویداد — نشست ۱۰")
    ap.add_argument("--holdings", default="holdings.json")
    ap.add_argument("--ledger", default=LEDGER_FILE)
    ap.add_argument("--reports-dir", default="reports", dest="reports_dir")
    ap.add_argument("--out", help="گزارش کامل مارک‌داون")
    ap.add_argument("--section", help="بخش ۱۴ روزه برای LATEST.md")
    ap.add_argument("--line", help="یک خط ساده برای پیام تلگرام")
    ap.add_argument("--no-fill", action="store_true", dest="no_fill",
                    help="قیمت‌های دفتر رویداد پر نشوند")
    a = ap.parse_args(argv)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if get is None:
        import requests
        get = requests.Session().get
    if history is None:
        import radar_history as H
        history = H.history

    notes: list[str] = []
    sources: list[tuple[str, str]] = []
    failed = False
    ledger = load_ledger(a.ledger)
    lo = iso(now - timedelta(days=LOOKBACK_DAYS))
    hi = iso(now + timedelta(days=HORIZON_DAYS))

    # ── تقویم کلان
    macro: list[dict] = []
    doc, err = _json(get, FED_CALENDAR, "federalreserve.gov")
    if err:
        failed = True
        notes.append(f"⛔ تقویم فدرال‌رزرو نیامد — {err}. رویدادهایش از دفتر خوانده شد.")
        sources.append(("federalreserve.gov — جلسه و صورت‌جلسه", f"⛔ {err}"))
        macro += _cached(ledger, {"fomc", "fomc_minutes"}, lo, hi)
    else:
        macro += parse_fed_calendar(doc)
        sources.append(("federalreserve.gov — جلسه و صورت‌جلسه", "✅"))
    vs, ve = (now - timedelta(days=LOOKBACK_DAYS)).date(), (now + timedelta(days=HORIZON_DAYS)).date()
    for kind, rid in FRED_RIDS.items():
        html, err = _text(get, FRED_CAL.format(rid=rid, vs=vs, ve=ve), f"FRED rid={rid}")
        evs = [] if err else parse_fred_calendar(html, kind)
        if not err and not evs:
            err = f"FRED rid={rid}: هیچ تاریخی در پنجره — شکل صفحه عوض شده؟"
        if err:
            failed = True
            notes.append(f"⛔ {KINDS[kind][0]} نیامد — {err}. از دفتر خوانده شد.")
            sources.append((f"FRED — {KINDS[kind][0]}", f"⛔ {err}"))
            macro += _cached(ledger, {kind}, lo, hi)
        else:
            macro += evs
            sources.append((f"FRED — {KINDS[kind][0]}", "✅"))
    ics, err = _text(get, BEA_ICS, "bea.gov")
    if err:
        failed = True
        notes.append(f"⛔ ICS رسمی BEA نیامد — وارسی متقاطع PCE انجام نشد: {err}")
        sources.append(("bea.gov — وارسی متقاطع PCE", f"⛔ {err}"))
    else:
        bad = pce_conflicts([e for e in macro if not e.get("from_ledger")
                             and lo <= e["at"] <= hi], parse_bea_ics(ics))
        if bad:
            failed = True
            notes += bad
        sources.append(("bea.gov — وارسی متقاطع PCE", "⛔ ناهمخوان" if bad else "✅ همخوان"))
    macro = sorted({e["id"]: e for e in macro}.values(), key=lambda e: e["at"])

    # ── نمادها
    port = portfolio_symbols(a.holdings)
    watch = watchlist()
    cands, cand_src = rotate_candidates(a.reports_dir)
    groups: dict[str, list[str]] = {}
    for g, syms in ((G_PORT, port), (G_WATCH, watch), (G_CAND, cands)):
        for s in syms:
            groups.setdefault(s.upper(), []).append(g)

    # ── آزادسازی
    verdicts, unotes, usrc = unlock_verdicts(list(groups), get, now)
    failed = failed or any(n.startswith("⛔") for n in unotes)
    notes += unotes
    sources += usrc

    # ── دفتر رویداد
    unlock_events = []
    for s, v in verdicts.items():
        for c in v["cliffs"]:
            if _ge(c["pct"], LEDGER_MIN_PCT) and c["at"] <= hi:
                unlock_events.append({
                    "id": f"unlock:{s}:{c['day']}", "kind": "unlock", "title": f"آزادسازی {s}",
                    "importance": "high" if _ge(c["pct"], VETO_SINGLE_PCT) else "medium",
                    "at": c["at"], "symbol": s, "tokens": c["tokens"],
                    "pct_circ": round(c["pct"], 4), "categories": c["cats"],
                    "source": f"defillama-datasets emissions/{v['slug']}"})
    fresh = [e for e in macro if not e.get("from_ledger") and lo <= e["at"] <= hi]
    upsert(ledger, fresh + unlock_events, now, macro_symbols=port)
    if not a.no_fill:
        notes += fill_prices(ledger, now, history)
    save_ledger(a.ledger, ledger)

    # ── خروجی
    rpath = a.out or "reports/events-<تاریخ>.md"
    report = render_report(macro, verdicts, groups, now, sources, ledger, notes, cand_src)
    section = render_section(macro, verdicts, groups, now, rpath)
    line = telegram_line(macro, verdicts, groups, now,
                         prefix="⚠️ تقویم رویداد ناقص، منبعی نیامد — " if failed else "")
    for path, txt in ((a.out, report), (a.section, section), (a.line, line + "\n")):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(txt, encoding="utf-8")
    print(report)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
