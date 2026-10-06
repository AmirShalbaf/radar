#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_probe.py — سنجش دسترسی منابع، نشست ۱۰ رادار ۷
=====================================================

چرا این فایل نوشته شد
---------------------
ایستگاه ۱ نشست ۱۰ منبع تقویم کلان، آزادسازی توکن و سه منبع تکرارگر را از
لپ‌تاپ سنجید. اجراکننده گیت‌هاب آی‌پی مرکز داده دارد و همان پاسخ را نمی‌گیرد:
بایننس آنجا ۴۵۱ است و یوتیوب بسته. پس هر منبع باید از همان محیطی سنجیده
شود که گردش‌کار در آن اجرا می‌شود.

چه می‌کند
---------
هر منبع یک درخواست GET. ثبت می‌شود: کد پاسخ، اندازه، زمان، و اینکه نشانه
محتوای درست در پاسخ هست یا نه. پاسخ ۲۰۰ بی‌نشانه — مثل پیام «کلید لازم است»
— «پاسخ بی‌نشانه» است، نه «باز». هیچ داده‌ای ذخیره نمی‌شود.

منبع بسته داده سنجش است، نه خطای اسکریپت: اجرا با کد ۰ تمام می‌شود و همه
سطرها در گزارش می‌آیند. فقط خرابی خود اسکریپت گام گردش‌کار را می‌اندازد.

نمونه اجرا
----------
    python radar_probe.py
    python radar_probe.py --out reports/probe-sources-2026-10-06.md
    python radar_probe.py --only bls-ics,farside-btc
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

VERSION = "1.0"
UTC = timezone.utc
TIMEOUT = 60                      # شاخص آزادسازی DefiLlama حدود ۲۲ مگابایت است
PAUSE = 0.3                       # میان درخواست‌ها، تا سقف نرخ نخورد
REASON_MAX = 120                  # بلندای توضیح هر سطر
FRED_DAYS = 60                    # پنجره تقویم FRED از امروز

UA = {
    # همان شناسه‌ای که radar_events.py خواهد فرستاد
    "bot": "radar-events/1.0 (+https://github.com/AmirShalbaf/radar)",
    "browser": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
}

VERDICT = {"open": "✅ باز", "closed": "❌ بسته", "no_marker": "⚠️ پاسخ بی‌نشانه",
           "error": "❌ خطا"}


class Target(NamedTuple):
    key: str        # شناسه ماشین، لاتین
    group: str      # دسته برای گزارش
    url: str
    ua: str         # کلید UA
    marker: str     # نشانه محتوای درست


def targets(now: datetime) -> list[Target]:
    """فهرست منابع ایستگاه ۱ — همان سنجش لپ‌تاپ، تا دو ستون مقایسه‌پذیر باشند."""
    vs = now.strftime("%Y-%m-%d")
    ve = (now + timedelta(days=FRED_DAYS)).strftime("%Y-%m-%d")
    M, U, T, C = "تقویم کلان", "آزادسازی و عرضه", "سه منبع تکرارگر", "شاهد"
    return [
        Target("fed-calendar-json", M, "https://www.federalreserve.gov/json/calendar.json",
               "bot", "FOMC"),
        Target("fed-fomc-page", M,
               "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
               "bot", "Meetings"),
        Target("fred-calendar-cpi", M,
               f"https://fred.stlouisfed.org/releases/calendar?rid=10&vs={vs}&ve={ve}",
               "bot", "Consumer Price Index"),
        Target("bea-ics", M,
               "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics",
               "bot", "BEGIN:VCALENDAR"),
        Target("bea-ics-browser", M,
               "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics",
               "browser", "BEGIN:VCALENDAR"),
        Target("bls-ics", M, "https://www.bls.gov/schedule/news_release/bls.ics",
               "bot", "BEGIN:VCALENDAR"),
        Target("bls-ics-browser", M, "https://www.bls.gov/schedule/news_release/bls.ics",
               "browser", "BEGIN:VCALENDAR"),
        # نشانی کنونی radar_fetch3.fetch_unlocks — از لپ‌تاپ ۴۰۲
        Target("llama-emissions-api", U, "https://api.llama.fi/emissions", "bot", "gecko_id"),
        Target("llama-ds-list", U,
               "https://defillama-datasets.llama.fi/emissionsProtocolsList", "bot",
               "sui-foundation"),
        Target("llama-ds-protocol", U,
               "https://defillama-datasets.llama.fi/emissions/layerzero", "bot",
               "unlockEvents"),
        Target("llama-ds-index", U, "https://defillama-datasets.llama.fi/emissionsIndex",
               "bot", "protocolSlug"),
        Target("coingecko-markets", U,
               "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
               "&ids=layerzero,sui", "bot", "circulating_supply"),
        Target("farside-btc", T, "https://farside.co.uk/btc/", "browser", "IBIT"),
        Target("farside-btc-bot", T, "https://farside.co.uk/btc/", "bot", "IBIT"),
        Target("coinglass-api", T,
               "https://open-api-v4.coinglass.com/api/futures/supported-coins", "bot",
               '"data"'),
        Target("coinglass-site", T, "https://www.coinglass.com/LiquidationData", "browser",
               "Liquidation"),
        Target("ff-json", T, "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
               "bot", '"title"'),
        Target("ff-xml", T, "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
               "bot", "<weeklyevents"),
        Target("ff-site", T, "https://www.forexfactory.com/calendar", "browser", "calendar"),
        # شاهد: دو منبعی که گردش‌کار روزانه امروز از همین محیط می‌خواند
        Target("okx-candles", C,
               "https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H"
               "&limit=2", "bot", '"code":"0"'),
        Target("fred-graph", C, "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF",
               "bot", "DFF"),
    ]


def classify(status: int | None, marker_ok: bool) -> str:
    if status is None:
        return "error"
    if 200 <= status < 300:
        return "open" if marker_ok else "no_marker"
    return "closed"


_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def snippet(body: bytes) -> str:
    """عنوان صفحه، یا آغاز متن — امن برای خانه جدول: بی خط عمودی و بی سطر تازه."""
    m = _TITLE.search(body[:20000])
    raw = m.group(1) if m else body[:400]
    s = raw.decode("utf-8", "replace")
    s = re.sub(r"\s+", " ", s.replace("|", "/")).strip()
    return s[:REASON_MAX]


def probe(t: Target, get, timeout: int = TIMEOUT, pause: float = PAUSE) -> dict:
    """یک درخواست. هیچ خطایی بیرون نمی‌رود — خطا خودش داده سنجش است."""
    t0 = time.monotonic()
    row = {"key": t.key, "group": t.group, "ua": t.ua, "url": t.url, "status": None,
           "bytes": 0, "secs": 0.0, "verdict": "error", "why": ""}
    try:
        r = get(t.url, headers={"User-Agent": UA[t.ua], "Accept": "*/*"}, timeout=timeout)
    except Exception as exc:
        row["why"] = f"{type(exc).__name__}: {str(exc)[:REASON_MAX]}"
    else:
        body = r.content or b""
        ok = t.marker.encode() in body
        row.update(status=r.status_code, bytes=len(body),
                   verdict=classify(r.status_code, ok),
                   why="" if ok else snippet(body))
    row["secs"] = time.monotonic() - t0
    if pause:
        time.sleep(pause)
    return row


def place(env) -> str:
    return "گیت‌هاب" if env.get("GITHUB_ACTIONS") == "true" else "محلی"


def egress(get) -> str:
    """کشور آی‌پی خروجی — فقط برای خواندن نتیجه؛ نیامد یعنی «نامعلوم»."""
    try:
        r = get("https://ipinfo.io/country", headers={"User-Agent": UA["bot"]}, timeout=15)
        s = (r.content or b"").decode("utf-8", "replace").strip()
        if r.status_code == 200 and re.fullmatch(r"[A-Z]{2}", s):
            return s
    except Exception:
        pass        # کشور فقط برچسب است؛ نیامدنش در گزارش «نامعلوم» نوشته می‌شود
    return "نامعلوم"


def render(rows: list[dict], where: str, country: str, now: datetime, env) -> str:
    o = [f"# سنجش دسترسی منابع — {now:%Y-%m-%d}", "",
         f"`radar_probe.py` {VERSION} — نشست ۱۰، ایستگاه ۱.", "",
         "| مورد | مقدار |", "|---|---|",
         f"| محیط | {where} |",
         f"| کشور آی‌پی خروجی | {country} |",
         f"| زمان | {now:%Y-%m-%d %H:%M} UTC |"]
    if env.get("GITHUB_RUN_ID"):
        o.append(f"| اجرای گردش‌کار | `{env['GITHUB_RUN_ID']}` |")
    n_open = sum(r["verdict"] == "open" for r in rows)
    o += ["", f"{fa(n_open)} از {fa(len(rows))} منبع باز. «پاسخ بی‌نشانه» یعنی پاسخ آمد "
          "ولی نشانه محتوای درست در آن نبود — مثل پیام «کلید لازم است». ستون توضیح "
          "عنوان صفحه یا آغاز پاسخ است.", "",
          "| دسته | منبع | شناسه مرورگر | کد | اندازه (بایت) | زمان (ثانیه) | داوری | توضیح |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        code = "—" if r["status"] is None else str(r["status"])
        o.append(f"| {r['group']} | `{r['key']}` | {r['ua']} | {code} | {r['bytes']:,} | "
                 f"{r['secs']:.1f} | {VERDICT[r['verdict']]} | {r['why'] or '—'} |")
    o += ["", "نشانی‌ها:", ""]
    o += [f"- `{r['key']}`: {r['url']}" for r in rows]
    return "\n".join(o) + "\n"


def main(argv=None, get=None, env=None, now: datetime | None = None,
         pause: float = PAUSE) -> int:
    ap = argparse.ArgumentParser(description="سنجش دسترسی منابع نشست ۱۰")
    ap.add_argument("--out", help="مسیر فایل گزارش مارک‌داون")
    ap.add_argument("--only", help="فقط این شناسه‌ها، جدا با کاما")
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)
    env = os.environ if env is None else env
    if get is None:
        import requests
        get = requests.Session().get
    ts = targets(now)
    if a.only:
        want = [k.strip() for k in a.only.split(",") if k.strip()]
        bad = sorted(set(want) - {t.key for t in ts})
        if bad:
            ap.error(f"شناسه ناشناخته: {', '.join(bad)}")
        ts = [t for t in ts if t.key in want]
    rows = [probe(t, get, pause=pause) for t in ts]
    txt = render(rows, place(env), egress(get), now, env)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
