#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_probe.py — سنجش دسترسی منابع، نشست ۱۰ رادار ۷
=====================================================

چرا این فایل نوشته شد
---------------------
ایستگاه ۱ نشست ۱۰ منبع تقویم کلان، آزادسازی توکن، سه منبع تکرارگر و از نشست ۹ اسکنر پامپ را از
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

سنجش CoinGlass — متن ۲۲، ۲۷ اکتبر ۲۰۲۶
----------------------------------------
با --coinglass: یازده نقطه پایانی v4 و سرور MCP رسمی، با کلید COINGLASS_API_KEY. کلید فقط با
سرآیند CG-API-KEY و فقط به میزبان‌های CoinGlass می‌رود — cg_headers — و در هر درخواست جدا،
بی نشست مشترک. از هر پاسخ فقط کد HTTP، کد و پیام خود CoinGlass تا ۱۲۰ نویسه با پوشاندن هر
رشته شبیه کلید، داده آمد یا نه، شمار ردیف و تاریخ آخرین ردیف نگه داشته می‌شود؛ از MCP فقط
پذیرفته شد یا نه و شمار ابزار. مخزن عمومی است: کلید هرگز چاپ و ثبت نمی‌شود. کلید غایب یعنی
گزارش «کلید تنظیم نشده»، بی درخواست و بی شکست. فقط مسیر دستی radar-probe.yml.

نمونه اجرا
----------
    python radar_probe.py
    python radar_probe.py --out reports/probe-sources-2026-10-06.md
    python radar_probe.py --only bls-ics,farside-btc
    python radar_probe.py --coinglass --out reports/probe-coinglass-2026-10-27.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlencode, urlparse

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
    K = "اسکنر پامپ"
    OKX, GATE = "https://www.okx.com/api/v5", "https://api.gateio.ws/api/v4"
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
        # نشانی پیشین radar_fetch3.fetch_unlocks — ۴۰۲؛ از نشست ۱۰ کنار رفت، ک۸۷
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
        # اسکنر پامپ — نشست ۹. ال‌بانک بسته از گیت‌هاب یعنی ستون ال‌بانک «نامعلوم»، نه «نیست»
        Target("okx-tickers-spot", K, f"{OKX}/market/tickers?instType=SPOT", "bot", '"volCcy24h"'),
        Target("okx-instruments-spot", K, f"{OKX}/public/instruments?instType=SPOT", "bot",
               '"listTime"'),
        Target("okx-funding-all", K, f"{OKX}/public/funding-rate?instId=ANY", "bot",
               '"fundingRate"'),
        Target("okx-oi-history", K, f"{OKX}/rubik/stat/contracts/open-interest-history"
               "?instId=BTC-USDT-SWAP&period=1H&limit=2", "bot", '"code":"0"'),
        Target("okx-candles-4h", K, f"{OKX}/market/candles?instId=BTC-USDT&bar=4H&limit=2", "bot",
               '"code":"0"'),
        Target("gate-tickers-spot", K, f"{GATE}/spot/tickers?currency_pair=BTC_USDT", "bot",
               '"quote_volume"'),
        Target("gate-currency-pairs", K, f"{GATE}/spot/currency_pairs/BTC_USDT", "bot",
               '"buy_start"'),
        Target("gate-contracts", K, f"{GATE}/futures/usdt/contracts/BTC_USDT", "bot",
               '"funding_rate"'),
        Target("gate-candles-1h", K, f"{GATE}/spot/candlesticks?currency_pair=BTC_USDT"
               "&interval=1h&limit=2", "bot", '[["'),
        Target("gate-contract-stats", K, f"{GATE}/futures/usdt/contract_stats?contract=BTC_USDT"
               "&interval=1h&limit=2", "bot", '"open_interest"'),
        Target("lbank-pairs", K, "https://api.lbkex.com/v2/currencyPairs.do", "bot", "_usdt"),
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
    if env.get("ImageOS"):
        # متغیرهای خود اجراکننده گیت‌هاب — رویداد ۹۰
        o.append(f"| تصویر اجراکننده | `{env['ImageOS']}` {env.get('ImageVersion', '')} |")
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


# ═══════════════════════ سنجش CoinGlass — متن ۲۲ ═══════════════════════

CG_BASE = "https://open-api-v4.coinglass.com"
CG_MCP = "https://api-mcp.coinglass.com/mcp"
CG_HOSTS = frozenset({"open-api-v4.coinglass.com", "api-mcp.coinglass.com"})
CG_HEADER = "CG-API-KEY"
CG_ENV = "COINGLASS_API_KEY"
# طرح پایه ۳۰ درخواست در دقیقه — مکث ۲٫۵ ثانیه زیر سقف می‌ماند
CG_PAUSE = 2.5
CG_MSG_MAX = 120
MCP_PROTOCOL = "2025-06-18"
# تنها میدان‌هایی که از پاسخ هر نقطه نگه داشته می‌شود — آزمون قفلش می‌کند
CG_ROW_FIELDS = frozenset({"key", "name", "path", "params", "status", "cg_code", "cg_msg",
                           "has_data", "rows", "last", "why"})
# رشته شبیه کلید: دست‌کم ۱۶ نویسه حرف و رقم پیوسته
_KEYLIKE = re.compile(r"[A-Za-z0-9_-]{16,}")


class CGEndpoint(NamedTuple):
    key: str        # شناسه ماشین، لاتین
    name: str       # نام فارسی
    path: str       # مسیر دقیق مستندات v4
    params: dict    # پارامترهای درخواست


# مسیر و پارامتر هر کدام از مستندات رسمی v4، docs.coinglass.com، ۲۷ اکتبر ۲۰۲۶. بازه روزانه:
# طرح پایه بازه کمتر از ۴ ساعت نمی‌دهد. نقشه گرمایی در مستندات فقط از طرح Professional
CG_ENDPOINTS = [
    CGEndpoint("cg-liq-history-btc", "انحلال تجمیعی تاریخی BTC",
               "/api/futures/liquidation/aggregated-history",
               {"exchange_list": "Binance,OKX,Bybit", "symbol": "BTC", "interval": "1d",
                "limit": "30"}),
    CGEndpoint("cg-liq-history-eth", "انحلال تجمیعی تاریخی ETH",
               "/api/futures/liquidation/aggregated-history",
               {"exchange_list": "Binance,OKX,Bybit", "symbol": "ETH", "interval": "1d",
                "limit": "30"}),
    CGEndpoint("cg-liq-coin-list", "انحلال ۲۴ ساعته بر اساس ارز، بایننس",
               "/api/futures/liquidation/coin-list", {"exchange": "Binance"}),
    CGEndpoint("cg-liq-exchange-list", "انحلال ۲۴ ساعته بر اساس صرافی، همه ارزها",
               "/api/futures/liquidation/exchange-list", {"symbol": "", "range": "24h"}),
    CGEndpoint("cg-etf-btc", "جریان صندوق‌های نقدی بیت‌کوین", "/api/etf/bitcoin/flow-history",
               {}),
    CGEndpoint("cg-etf-eth", "جریان صندوق‌های نقدی اتر", "/api/etf/ethereum/flow-history", {}),
    CGEndpoint("cg-oi-history-btc", "بهره باز تجمیعی تاریخی BTC",
               "/api/futures/open-interest/aggregated-history",
               {"symbol": "BTC", "interval": "1d", "limit": "30"}),
    CGEndpoint("cg-funding-oiw-btc", "نرخ تأمین مالی وزنی تاریخی BTC",
               "/api/futures/funding-rate/oi-weight-history",
               {"symbol": "BTC", "interval": "1d", "limit": "30"}),
    CGEndpoint("cg-ls-global-btc", "نسبت لانگ به شورت سراسری BTC، بایننس",
               "/api/futures/global-long-short-account-ratio/history",
               {"exchange": "Binance", "symbol": "BTCUSDT", "interval": "1d", "limit": "30"}),
    CGEndpoint("cg-coinbase-premium", "شاخص صرف Coinbase", "/api/coinbase-premium-index",
               {"interval": "1d", "limit": "30"}),
    CGEndpoint("cg-liq-heatmap-btc", "نقشه گرمایی انحلال BTC، مدل ۱",
               "/api/futures/liquidation/aggregated-heatmap/model1",
               {"symbol": "BTC", "range": "3d"}),
]


def cg_headers(url: str, key: str | None, extra: dict | None = None) -> dict:
    """سرآیند یک درخواست؛ کلید فقط وقتی میزبان دقیقاً یکی از میزبان‌های CoinGlass است."""
    h = {"User-Agent": UA["bot"], "Accept": "application/json", **(extra or {})}
    if key and urlparse(url).hostname in CG_HOSTS:
        h[CG_HEADER] = key
    return h


def cg_mask(text, key: str | None) -> str:
    """کلید و هر رشته شبیه کلید پوشانده، سپس امن برای جدول و بریده تا ۱۲۰ نویسه."""
    s = str(text or "")
    if key:
        s = s.replace(key, "‹کلید›")
    s = _KEYLIKE.sub("‹پوشانده›", s)
    s = re.sub(r"\s+", " ", s.replace("|", "/")).strip()
    return s[:CG_MSG_MAX]


def _day(v) -> str | None:
    """مهر زمانی ثانیه یا میلی‌ثانیه به تاریخ UTC؛ از بزرگی عدد."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x > 1e11:
        x /= 1000
    return datetime.fromtimestamp(x, UTC).strftime("%Y-%m-%d")


def _shape(data) -> tuple[int | None, str | None]:
    """شمار ردیف و تاریخ آخرین ردیف — فقط همین دو از داده."""
    if isinstance(data, dict):                    # نقشه گرمایی: ردیف‌ها شمع قیمت‌اند
        data = data.get("price_candlesticks")
    if not isinstance(data, list):
        return None, None
    ts = []
    for r in data:
        if isinstance(r, dict):
            v = r.get("time", r.get("timestamp"))
        elif isinstance(r, list) and r:
            v = r[0]
        else:
            v = None
        if v is not None:
            ts.append(v)
    days = [d for d in (_day(v) for v in ts) if d]
    return len(data), (max(days) if days else None)


def cg_endpoint(ep: CGEndpoint, key: str, request, pause: float = CG_PAUSE) -> dict:
    """یک نقطه پایانی. هیچ خطایی بیرون نمی‌رود؛ از بدنه فقط میدان‌های CG_ROW_FIELDS."""
    row = {"key": ep.key, "name": ep.name, "path": ep.path, "params": dict(ep.params),
           "status": None, "cg_code": None, "cg_msg": None, "has_data": False, "rows": None,
           "last": None, "why": ""}
    url = CG_BASE + ep.path
    try:
        r = request("GET", url, headers=cg_headers(url, key), params=dict(ep.params),
                    timeout=TIMEOUT)
    except Exception as exc:
        row["why"] = cg_mask(f"{type(exc).__name__}: {exc}", key)
    else:
        row["status"] = r.status_code
        try:
            js = json.loads((r.content or b"").decode("utf-8", "replace"))
        except ValueError:
            js = None
        if isinstance(js, dict):
            row["cg_code"] = cg_mask(js.get("code"), key) or None
            row["cg_msg"] = cg_mask(js.get("msg"), key) or None
            data = js.get("data")
            row["has_data"] = bool(data)
            if row["has_data"]:
                row["rows"], row["last"] = _shape(data)
        else:
            row["why"] = "پاسخ JSON نیست"
    if pause:
        time.sleep(pause)
    return row


def _rpc(r) -> dict | None:
    """پاسخ JSON-RPC از بدنه JSON یا رویدادهای SSE — Streamable HTTP."""
    raw = (r.content or b"").decode("utf-8", "replace")
    try:
        js = json.loads(raw)
        return js if isinstance(js, dict) else None
    except ValueError:
        pass
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                js = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(js, dict) and ("result" in js or "error" in js):
                return js
    return None


def _hdr(r, name: str) -> str | None:
    for k, v in (getattr(r, "headers", None) or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def cg_mcp(key: str, request, pause: float = CG_PAUSE) -> list[dict]:
    """
    initialize، اعلان initialized، سپس tools/list با شناسه جلسه — Streamable HTTP. فقط
    پذیرفته شد یا نه، کد HTTP، شمار ابزار و پیام خطای پوشانده. شناسه جلسه ثبت نمی‌شود.
    """
    base = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    steps: list[dict] = []

    def call(step, body, extra=None):
        out = {"step": step, "ok": False, "status": None, "tools": None, "why": ""}
        try:
            r = request("POST", CG_MCP, headers=cg_headers(CG_MCP, key, {**base, **(extra or {})}),
                        json=body, timeout=TIMEOUT)
        except Exception as exc:
            out["why"] = cg_mask(f"{type(exc).__name__}: {exc}", key)
            steps.append(out)
            return None, out
        finally:
            if pause:
                time.sleep(pause)
        out["status"] = r.status_code
        steps.append(out)
        return r, out

    r, s = call("initialize", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": MCP_PROTOCOL, "capabilities": {},
        "clientInfo": {"name": "radar-probe", "version": VERSION}}})
    if r is None:
        return steps
    js = _rpc(r)
    if not (200 <= r.status_code < 300 and js and "result" in js):
        err = (js or {}).get("error") or {}
        s["why"] = cg_mask(err.get("message") or "پاسخ initialize نتیجه ندارد", key)
        return steps
    s["ok"] = True
    sid = _hdr(r, "Mcp-Session-Id")
    proto = (js["result"].get("protocolVersion") or MCP_PROTOCOL)
    s["why"] = "شناسه جلسه دریافت شد" if sid else "شناسه جلسه در پاسخ نبود"
    extra = {"MCP-Protocol-Version": proto}
    if sid:
        extra["Mcp-Session-Id"] = sid
    r, s = call("notifications/initialized",
                {"jsonrpc": "2.0", "method": "notifications/initialized"}, extra)
    if r is not None:
        s["ok"] = 200 <= r.status_code < 300
    r, s = call("tools/list", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, extra)
    if r is None:
        return steps
    js = _rpc(r)
    tools = ((js or {}).get("result") or {}).get("tools")
    if 200 <= r.status_code < 300 and isinstance(tools, list):
        s["ok"], s["tools"] = True, len(tools)
    else:
        err = (js or {}).get("error") or {}
        s["why"] = cg_mask(err.get("message") or "فهرست ابزار نیامد", key)
    return steps


def render_cg(rows: list[dict], mcp: list[dict], where: str, country: str, now: datetime,
              env, has_key: bool) -> str:
    o = [f"# سنجش دسترسی CoinGlass — {now:%Y-%m-%d}", "",
         f"`radar_probe.py --coinglass` {VERSION} — متن ۲۲. فقط مسیر دستی؛ کلید چاپ و ثبت نمی‌شود.",
         "", "| مورد | مقدار |", "|---|---|",
         f"| محیط | {where} |", f"| کشور آی‌پی خروجی | {country} |",
         f"| زمان | {now:%Y-%m-%d %H:%M} UTC |",
         f"| کلید | {'کلید تنظیم‌شده' if has_key else 'کلید تنظیم نشده'} — {CG_ENV} |"]
    if env.get("GITHUB_RUN_ID"):
        o.append(f"| اجرای گردش‌کار | `{env['GITHUB_RUN_ID']}` |")
    if not has_key:
        return "\n".join(o + ["", f"کلید تنظیم نشده — {CG_ENV} در محیط نیست. هیچ درخواستی "
                                  "فرستاده نشد."]) + "\n"
    got = sum(1 for r in rows if r["has_data"])
    o += ["", f"{fa(got)} از {fa(len(rows))} نقطه داده داد. «کد CoinGlass» و «پیام» از خود پاسخ‌اند؛ "
              "هر رشته شبیه کلید پوشانده شده. از بدنه هیچ چیز دیگری نگه داشته نشد.", "",
          "| نقطه | نام | مسیر و پارامتر | HTTP | کد CoinGlass | پیام | داده | ردیف | آخرین ردیف |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        q = f"`{r['path']}" + (f"?{urlencode(r['params'])}`" if r["params"] else "`")
        msg = r["cg_msg"] or r["why"] or "—"
        o.append(f"| `{r['key']}` | {r['name']} | {q} | {r['status'] if r['status'] is not None else '—'} "
                 f"| {r['cg_code'] or '—'} | {msg} | {'✅' if r['has_data'] else '❌'} "
                 f"| {r['rows'] if r['rows'] is not None else '—'} | {r['last'] or '—'} |")
    o += ["", f"## سرور MCP رسمی — `{CG_MCP}`", "",
          "| گام | پذیرفته | HTTP | شمار ابزار | توضیح |", "|---|---|---|---|---|"]
    for s in mcp:
        o.append(f"| {s['step']} | {'✅' if s['ok'] else '❌'} | "
                 f"{s['status'] if s['status'] is not None else '—'} | "
                 f"{s['tools'] if s['tools'] is not None else '—'} | {s['why'] or '—'} |")
    return "\n".join(o) + "\n"


def main_coinglass(out: str | None, env, now: datetime, request, pause: float) -> int:
    key = env.get(CG_ENV) or None
    where = place(env)
    if not key:
        txt = render_cg([], [], where, "نامعلوم", now, env, has_key=False)
    else:
        country = egress(lambda url, **k: request("GET", url, **k))
        rows = [cg_endpoint(ep, key, request, pause) for ep in CG_ENDPOINTS]
        mcp = cg_mcp(key, request, pause)
        txt = render_cg(rows, mcp, where, country, now, env, has_key=True)
        txt = cg_mask_doc(txt, key)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(txt, encoding="utf-8")
    print(txt)
    return 0


def cg_mask_doc(txt: str, key: str) -> str:
    """کمربند دوم: اگر کلید به هر راهی در متن گزارش رسید، پوشانده شود."""
    return txt.replace(key, "‹کلید›") if key else txt


def main(argv=None, get=None, env=None, now: datetime | None = None,
         pause: float | None = None, request=None) -> int:
    ap = argparse.ArgumentParser(description="سنجش دسترسی منابع نشست ۱۰")
    ap.add_argument("--out", help="مسیر فایل گزارش مارک‌داون")
    ap.add_argument("--only", help="فقط این شناسه‌ها، جدا با کاما")
    ap.add_argument("--coinglass", action="store_true",
                    help="سنجش CoinGlass با کلید COINGLASS_API_KEY — متن ۲۲")
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)
    env = os.environ if env is None else env
    if a.coinglass:
        if request is None:
            import requests
            request = requests.request          # هر درخواست جدا، بی نشست مشترک
        return main_coinglass(a.out, env, now, request, CG_PAUSE if pause is None else pause)
    pause = PAUSE if pause is None else pause
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
