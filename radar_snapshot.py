#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_snapshot.py — نبض چهارساعته بازار، رادار ۷ فاز ۱
=======================================================

مسئله‌ای که حل می‌کند
---------------------
گردش‌کار روزانه فقط یک بار در روز داده می‌آورد. جلسه‌ای که ساعت‌ها بعد
شروع شود، با داده کهنه کار می‌کند بی‌آنکه بداند کهنه است.

این اسکریپت هر چهار ساعت یک «عکس سبک» می‌گیرد:

    قیمت لحظه‌ای + تغییر ۲۴ ساعته      (اوکی‌اکس، جایگزین: گیت)
    نرخ تأمین مالی (Funding)            (اوکی‌اکس، بازار دائمی)
    بهره باز (Open Interest)            (اوکی‌اکس، بازار دائمی)
    تغییر بهره باز نسبت به پالس قبلی    (از snapshot.json قبلی)

و دو خروجی می‌نویسد:

    snapshot.json        — ماشین‌خوان، با مهر زمانی
    reports/SNAPSHOT.md  — انسان‌خوان، با قانون تازگی در سرصفحه

قانون تازگی (هسته فاز ۱)
------------------------
هر عدد این فایل مهر زمانی دارد. اگر بیش از «سقف عمر» از مهر گذشته باشد،
داده کهنه است و طبق قانون مادر داده یعنی «داده ندارم».
سقف عمر پیش‌فرض: ۵ ساعت (یک پالس + یک ساعت جا برای تأخیر اجرا).

نمادها از کجا می‌آیند
---------------------
اجتماع سه منبع، بدون تکرار:
    ۱) نمادهای سبد از holdings.json
    ۲) نمادهای فهرست پایش از watch.json
    ۳) هسته همیشگی: BTC و ETH

اجرا
----
    python radar_snapshot.py
    python radar_snapshot.py --symbols BTC,ETH,SOL
    python radar_snapshot.py --out reports/SNAPSHOT.md --json snapshot.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("نیاز به requests: pip install requests")
    sys.exit(1)

VERSION = "7.0-p1"
UTC = timezone.utc
OKX = "https://www.okx.com"
GATE = "https://api.gateio.ws/api/v4"
STALE_HOURS = 5.0          # سقف عمر داده این فایل
PAUSE = 0.25               # احترام به سقف نرخ صرافی

CORE = ["BTC", "ETH"]


# ─────────────────────── واکشی ───────────────────────

def _get_json(url: str, params: dict | None = None, timeout: int = 15):
    try:
        r = requests.get(url, params=params, timeout=timeout,
                         headers={"User-Agent": "radar-snapshot/" + VERSION})
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def okx_ticker(sym: str) -> dict | None:
    """قیمت لحظه‌ای و باز ۲۴ ساعت قبل از اوکی‌اکس."""
    j = _get_json(f"{OKX}/api/v5/market/ticker",
                  {"instId": f"{sym}-USDT"})
    if j and j.get("code") == "0" and j.get("data"):
        d = j["data"][0]
        try:
            last = float(d["last"])
            op24 = float(d.get("open24h") or 0)
            chg = (last - op24) / op24 * 100 if op24 else None
            return {"price": last, "chg24": chg, "src": "okx"}
        except Exception:
            return None
    return None


def gate_ticker(sym: str) -> dict | None:
    """جایگزین قیمت: گیت. تغییر ۲۴ ساعته را خودش می‌دهد."""
    j = _get_json(f"{GATE}/spot/tickers", {"currency_pair": f"{sym}_USDT"})
    if isinstance(j, list) and j:
        d = j[0]
        try:
            return {"price": float(d["last"]),
                    "chg24": float(d.get("change_percentage") or 0),
                    "src": "gate"}
        except Exception:
            return None
    return None


def okx_funding(sym: str) -> float | None:
    """نرخ تأمین مالی بازار دائمی، به درصدِ هر دوره (اوکی‌اکس: ۸ ساعته)."""
    j = _get_json(f"{OKX}/api/v5/public/funding-rate",
                  {"instId": f"{sym}-USDT-SWAP"})
    if j and j.get("code") == "0" and j.get("data"):
        try:
            return float(j["data"][0]["fundingRate"]) * 100
        except Exception:
            return None
    return None


def okx_oi(sym: str, price: float | None) -> float | None:
    """بهره باز بازار دائمی به دلار (تقریب: بهره باز به واحد کوین × قیمت)."""
    j = _get_json(f"{OKX}/api/v5/public/open-interest",
                  {"instType": "SWAP", "instId": f"{sym}-USDT-SWAP"})
    if j and j.get("code") == "0" and j.get("data"):
        try:
            oi_ccy = float(j["data"][0]["oiCcy"])
            return oi_ccy * price if price else None
        except Exception:
            return None
    return None


# ─────────────────────── نمادها ───────────────────────

def load_symbols(args_symbols: str | None) -> list[str]:
    if args_symbols:
        return sorted({s.strip().upper() for s in args_symbols.split(",") if s.strip()})
    syms: set[str] = set(CORE)
    try:
        with open("holdings.json", encoding="utf-8") as f:
            for p in json.load(f).get("positions", []):
                if p.get("symbol"):
                    syms.add(p["symbol"].upper())
    except Exception:
        pass
    try:
        with open("watch.json", encoding="utf-8") as f:
            for it in json.load(f).get("items", []):
                if it.get("symbol"):
                    syms.add(it["symbol"].upper())
    except Exception:
        pass
    return sorted(syms)


# ─────────────────────── گزارش ───────────────────────

def fmt(v, d=4):
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.{d}f}".rstrip("0").rstrip(".")


def build(rows: list[dict], prev: dict, failures: list[str]) -> tuple[str, dict]:
    now = datetime.now(UTC)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    prev_at = prev.get("generated_utc", "—")

    lines = [
        "# نبض بازار — عکس چهارساعته",
        "",
        f"تولید: **{stamp}**",
        f"پالس قبلی: {prev_at}",
        "",
        f"**قانون تازگی:** اگر بیش از {STALE_HOURS:.0f} ساعت از مهر بالا گذشته،",
        "این داده کهنه است و طبق قانون مادر داده یعنی «داده ندارم».",
        "برای تصمیم، اول پالس تازه بگیر.",
        "",
        "| نماد | قیمت | تغییر ۲۴س ٪ | فاندینگ ۸س ٪ | بهره باز (دلار) | تغییر بهره باز از پالس قبل ٪ | منبع |",
        "|---|---|---|---|---|---|---|",
    ]

    js = {"version": VERSION, "generated_utc": stamp,
          "stale_after_hours": STALE_HOURS, "symbols": {}}

    prev_syms = prev.get("symbols", {})
    for r in rows:
        s = r["symbol"]
        oi_prev = (prev_syms.get(s) or {}).get("oi_usd")
        oi_chg = None
        if r.get("oi_usd") and oi_prev:
            oi_chg = (r["oi_usd"] - oi_prev) / oi_prev * 100
        lines.append(
            f"| {s} | {fmt(r.get('price'))} | {fmt(r.get('chg24'), 2)} | "
            f"{fmt(r.get('funding'), 4)} | {fmt(r.get('oi_usd'), 0)} | "
            f"{fmt(oi_chg, 2)} | {r.get('src') or '—'} |")
        js["symbols"][s] = {
            "price": r.get("price"), "chg24_pct": r.get("chg24"),
            "funding_8h_pct": r.get("funding"), "oi_usd": r.get("oi_usd"),
            "oi_chg_pct_vs_prev": oi_chg, "source": r.get("src"),
        }

    lines += [
        "",
        "خواندن ستون‌ها: فاندینگ مثبت یعنی لانگ‌ها هزینه می‌دهند (ازدحام لانگ).",
        "جهش بهره باز همراه فاندینگ به‌شدت مثبت و بدون رشد قیمت، الگوی هشدار",
        "پامپ اهرمی است — بند بلوک جریان رادار.",
        "",
    ]

    if failures:
        lines += ["## منابعی که پاسخ ندادند", ""]
        lines += [f"- {f}" for f in failures]
        lines += ["", "نبود داده یعنی «داده ندارم»، نه صفر.", ""]

    return "\n".join(lines), js


# ─────────────────────── اجرا ───────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=f"نبض بازار — رادار {VERSION}")
    ap.add_argument("--symbols", help="فهرست جدا با کاما؛ پیش‌فرض: سبد + پایش + هسته")
    ap.add_argument("--out", default="reports/SNAPSHOT.md")
    ap.add_argument("--json", default="snapshot.json")
    a = ap.parse_args()

    syms = load_symbols(a.symbols)
    prev = {}
    if os.path.exists(a.json):
        try:
            with open(a.json, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    rows, failures = [], []
    for s in syms:
        t = okx_ticker(s) or gate_ticker(s)
        if not t:
            failures.append(f"{s}: قیمت از هیچ صرافی نیامد")
            rows.append({"symbol": s})
            continue
        time.sleep(PAUSE)
        fu = okx_funding(s)
        time.sleep(PAUSE)
        oi = okx_oi(s, t["price"])
        if fu is None:
            failures.append(f"{s}: فاندینگ نیامد (شاید بازار دائمی ندارد)")
        rows.append({"symbol": s, "price": t["price"], "chg24": t["chg24"],
                     "funding": fu, "oi_usd": oi, "src": t["src"]})
        time.sleep(PAUSE)

    ok = [r for r in rows if r.get("price") is not None]
    if not ok:
        print("هیچ نمادی قیمت نگرفت — خروجی نوشته نمی‌شود.", file=sys.stderr)
        return 1

    rep, js = build(rows, prev, failures)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(rep)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False, indent=2)

    print(f"✅ {a.out} — {len(ok)} از {len(rows)} نماد", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
