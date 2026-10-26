#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_forecast.py — دفتر پیش‌بینی، بند ۷ متن ۲۰، ۲۷ اکتبر ۲۰۲۶
================================================================

هر پیش‌بینی در forecasts.json:

    id            شناسه، یکتا
    made_at       تاریخ پیش‌بینی، YYYY-MM-DD
    source        منبع پیش‌بینی — چه کسی گفت
    symbol        نماد
    scenarios     سناریوها: name، p احتمال، interval بازه قیمت با نماد ریاضی —
                  «[78000,82000]» دو سر بسته، «(82000,)» بالای 82000، «(,78000)» زیر آن.
                  بازه‌ها باید کل محور قیمت را بی شکاف و بی هم‌پوشانی بپوشانند و جمع
                  احتمال ۱ باشد — پس هر بسته دقیقاً یک سناریو دارد
    criterion     معیار دقیق به زبان ساده
    close_at      مهلت: لحظه بسته‌شدن کندل روزانه وقت جهانی، ۰۰:۰۰ UTC
    price_source  منبع قیمت — بسته روزانه همان منبعی که بسته هفتگی را می‌خواند:
                  radar_positions.daily_close_at، اوکی‌اکس 1Dutc سپس گیت 1d

نمره Brier چندگزینه‌ای وقتی مهلت گذشت: جمع (p − o)² روی سناریوها، o یک برای سناریوی
رخ‌داده و صفر برای بقیه. صفر کامل است، ۲ بدترین؛ پیش‌بینی یکنواخت سه‌گزینه‌ای 0.667.
بسته‌ای که نیامد نمره نمی‌سازد — تلاش با دلیل در attempts، و اجرای بعد دوباره.

    python radar_forecast.py add --id F-20261027-01 --made-at 2026-10-27 --source "..." \\
        --symbol BTC --close-at 2026-10-31T00:00:00+00:00 --criterion "..." \\
        --scenario "مثبت|0.20|(82000,)" --scenario "پایه|0.50|[78000,82000]" \\
        --scenario "منفی|0.30|(,78000)"
    python radar_forecast.py score
    python radar_forecast.py report --out reports/forecasts-2026-11-01.md --line /tmp/l.txt
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
FILE = "forecasts.json"
PRICE_SOURCE = ("بسته روزانه وقت جهانی — اوکی‌اکس 1Dutc، سپس گیت 1d؛ همان منبع بسته هفتگی، "
                "radar_positions.daily_close_at")
P_TOL = 1e-9
_INTERVAL = re.compile(r"^([\[(])\s*([0-9.]*)\s*,\s*([0-9.]*)\s*([\])])$")      # اسکی
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class ForecastError(Exception):
    """دفتر پیش‌بینی خوانا یا درست نیست — صریح."""


def parse_interval(s: str) -> tuple:
    """«[lo,hi]» به (lo، lo بسته؟، hi، hi بسته؟)؛ سر خالی یعنی بی‌کران و همیشه باز."""
    m = _INTERVAL.match(str(s).strip())
    if not m:
        raise ForecastError(f"بازه نامعتبر {s!r} — مثل [78000,82000] یا (82000,) یا (,78000)")
    lo = float(m.group(2)) if m.group(2) else None
    hi = float(m.group(3)) if m.group(3) else None
    if lo is None and hi is None:
        raise ForecastError(f"بازه {s!r} هر دو سرش خالی است")
    lo_c = m.group(1) == "[" and lo is not None
    hi_c = m.group(4) == "]" and hi is not None
    if lo is not None and hi is not None and (lo > hi or (lo == hi and not (lo_c and hi_c))):
        raise ForecastError(f"بازه {s!r} تهی است")
    return lo, lo_c, hi, hi_c


def _ts(raw, what: str) -> datetime:
    try:
        t = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError) as exc:
        raise ForecastError(f"{what}: مهر نامعتبر {raw!r}") from exc
    if t.tzinfo is None:
        raise ForecastError(f"{what}: مهر بی منطقه زمانی")
    return t.astimezone(UTC)


def _check_partition(scen: list[dict], where: str) -> None:
    iv = sorted((parse_interval(s["interval"]) + (s["name"],) for s in scen),
                key=lambda x: (-math.inf if x[0] is None else x[0]))
    if iv[0][0] is not None:
        raise ForecastError(f"{where}: بازه‌ها از منفی بی‌نهایت شروع نمی‌شوند — زیر "
                            f"{iv[0][0]:g} بی سناریو است")
    if iv[-1][2] is not None:
        raise ForecastError(f"{where}: بالای {iv[-1][2]:g} بی سناریو است")
    for a, b in zip(iv, iv[1:]):
        if a[2] is None or b[0] is None or a[2] < b[0] or (a[2] == b[0] and not a[3] and not b[1]):
            raise ForecastError(f"{where}: شکاف میان «{a[4]}» و «{b[4]}»")
        if a[2] > b[0] or (a[2] == b[0] and a[3] and b[1]):
            raise ForecastError(f"{where}: هم‌پوشانی «{a[4]}» و «{b[4]}»")


def validate(doc) -> None:
    if not isinstance(doc, dict) or not isinstance(doc.get("forecasts"), list):
        raise ForecastError("forecasts.json باید forecasts فهرستی داشته باشد")
    seen: set = set()
    for i, f in enumerate(doc["forecasts"], 1):
        where = f"پیش‌بینی {i}"
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not f["id"].strip():
            raise ForecastError(f"{where}: شناسه لازم است")
        where += f" ({f['id']})"
        if f["id"] in seen:
            raise ForecastError(f"{where}: شناسه تکراری")
        seen.add(f["id"])
        for k in ("source", "symbol", "criterion", "price_source"):
            if not isinstance(f.get(k), str) or not f[k].strip():
                raise ForecastError(f"{where}: {k} لازم است")
        if not isinstance(f.get("made_at"), str) or not _DATE.match(f["made_at"]):
            raise ForecastError(f"{where}: made_at باید YYYY-MM-DD باشد")
        c = _ts(f.get("close_at"), f"{where}: close_at")
        if (c.hour, c.minute, c.second, c.microsecond) != (0, 0, 0, 0):
            raise ForecastError(f"{where}: close_at باید ۰۰:۰۰ UTC باشد — بسته روزانه")
        scen = f.get("scenarios")
        if not isinstance(scen, list) or not scen or not all(isinstance(s, dict) for s in scen):
            raise ForecastError(f"{where}: دست‌کم یک سناریو لازم است")
        names = [s.get("name") for s in scen]
        if any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != len(names):
            raise ForecastError(f"{where}: نام سناریوها خالی یا تکراری است")
        for s in scen:
            if not isinstance(s.get("p"), (int, float)) or isinstance(s["p"], bool) \
                    or not 0 <= s["p"] <= 1:
                raise ForecastError(f"{where}: احتمال «{s['name']}» باید میان ۰ و ۱ باشد")
        _check_partition(scen, where)
        total = sum(s["p"] for s in scen)
        if abs(total - 1) > P_TOL:
            raise ForecastError(f"{where}: جمع احتمال {total:g} است، نه ۱")


def load(path: str = FILE) -> dict:
    if not os.path.exists(path):
        return {"version": 1, "forecasts": []}
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise ForecastError(f"{os.path.basename(path)} خوانا نیست ({type(exc).__name__})") from exc
    validate(doc)
    return doc


def save(path: str, doc: dict) -> None:
    validate(doc)
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# ═══════════════════════ پیامد و نمره ═══════════════════════

def _inside(x: float, iv: tuple) -> bool:
    lo, lo_c, hi, hi_c = iv
    if lo is not None and (x < lo or (x == lo and not lo_c)):
        return False
    if hi is not None and (x > hi or (x == hi and not hi_c)):
        return False
    return True


def outcome(f: dict, close: float) -> str:
    hit = [s["name"] for s in f["scenarios"] if _inside(close, parse_interval(s["interval"]))]
    if len(hit) != 1:                    # افراز سنجیده شده؛ این یعنی باگ، نه داده
        raise ForecastError(f"{f['id']}: بسته {close} در {len(hit)} سناریو افتاد")
    return hit[0]


def brier(f: dict, name: str) -> float:
    return sum((s["p"] - (1.0 if s["name"] == name else 0.0)) ** 2 for s in f["scenarios"])


def _fetch():
    """تابع بسته روزانه — آزمون جایش داده ساختگی می‌گذارد."""
    import radar_positions as P
    return lambda sym, close_at, now=None: P.daily_close_at(sym, close_at, now=now)


def score(doc: dict, now: datetime, fetch=None) -> tuple[int, list[str]]:
    """پیش‌بینی‌های سررسیده بی نمره را نمره می‌دهد. (شمار نمره‌خورده، دلیل‌های ناکام)."""
    fetch = fetch or _fetch()
    n, fails = 0, []
    for f in doc["forecasts"]:
        if f.get("result") is not None:
            continue
        c = _ts(f["close_at"], f["id"])
        if now < c:
            continue
        d, why = fetch(f["symbol"], c, now=now)
        if d is None:
            msg = "؛ ".join(why) or "بی‌دلیل"
            f.setdefault("attempts", []).append({"at": now.isoformat(timespec="seconds"),
                                                 "why": msg})
            fails.append(f"{f['id']}: داده ندارم — {msg}")
            continue
        name = outcome(f, d["close"])
        f["result"] = {"close": d["close"], "venue": d["venue"], "closed_at": d["closed_at"],
                       "outcome": name, "p_outcome": next(s["p"] for s in f["scenarios"]
                                                          if s["name"] == name),
                       "brier": round(brier(f, name), 6),
                       "scored_at": now.isoformat(timespec="seconds")}
        n += 1
    return n, fails


# ═══════════════════════ گزارش ═══════════════════════

def _scen_txt(f: dict) -> str:
    return "، ".join(f"{s['name']} {s['p'] * 100:.0f}٪ {s['interval']}" for s in f["scenarios"])


def summary_line(doc: dict) -> str:
    done = [f for f in doc["forecasts"] if f.get("result")]
    open_ = len(doc["forecasts"]) - len(done)
    if not done:
        return f"🎯 دفتر پیش‌بینی: هنوز نمره‌ای نیست؛ {fa(open_)} باز"
    mean = sum(f["result"]["brier"] for f in done) / len(done)
    return (f"🎯 دفتر پیش‌بینی: {fa(len(done))} نمره‌خورده، میانگین Brier {mean:.3f} — صفر کامل، "
            f"۲ بدترین؛ {fa(open_)} باز")


def report(doc: dict, now: datetime) -> str:
    o = ["## دفتر پیش‌بینی — نمره Brier", "",
         f"تولید {now.astimezone(UTC):%Y-%m-%d %H:%M} UTC. Brier = جمع (احتمال − پیامد)² روی "
         "سناریوها؛ صفر کامل، ۲ بدترین.", "", summary_line(doc), ""]
    if not doc["forecasts"]:
        return "\n".join(o + ["پیش‌بینی‌ای ثبت نشده."])
    o += ["| شناسه | نماد | منبع | مهلت | سناریوها | بسته | پیامد | احتمال پیامد | Brier |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f in doc["forecasts"]:
        r = f.get("result")
        if r:
            cells = (f"{r['close']:g} ({r['venue']})", r["outcome"], f"{r['p_outcome']:.2f}",
                     f"{r['brier']:.3f}")
        else:
            last = (f.get("attempts") or [{}])[-1].get("why")
            cells = ("—", "داده ندارم — " + last if last else "باز", "—", "—")
        o.append(f"| {f['id']} | {f['symbol']} | {f['source']} | {f['close_at'][:16]}Z | "
                 f"{_scen_txt(f)} | " + " | ".join(cells) + " |")
    return "\n".join(o)


# ═══════════════════════ فرمان ═══════════════════════

def _scenario(raw: str) -> dict:
    parts = raw.split("|")
    if len(parts) != 3:
        raise ForecastError(f"سناریو {raw!r} — قالب «نام|احتمال|بازه»")
    try:
        p = float(parts[1])
    except ValueError as exc:
        raise ForecastError(f"احتمال سناریو {raw!r} عدد نیست") from exc
    return {"name": parts[0].strip(), "p": p, "interval": parts[2].strip()}


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="دفتر پیش‌بینی — بند ۷ متن ۲۰")
    ap.add_argument("--file", default=FILE)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add", help="افزودن یک پیش‌بینی")
    p.add_argument("--id", required=True)
    p.add_argument("--made-at", dest="made_at", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--close-at", dest="close_at", required=True)
    p.add_argument("--criterion", required=True)
    p.add_argument("--scenario", action="append", required=True,
                   help="«نام|احتمال|بازه»، مثل «پایه|0.50|[78000,82000]»")
    p.add_argument("--price-source", dest="price_source", default=PRICE_SOURCE)
    sp.add_parser("score", help="نمره پیش‌بینی‌های سررسیده")
    p = sp.add_parser("report", help="گزارش و خط خلاصه")
    p.add_argument("--out", default=None)
    p.add_argument("--line", default=None)
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)
    try:
        doc = load(a.file)
        if a.cmd == "add":
            doc["forecasts"].append({
                "id": a.id, "made_at": a.made_at, "source": a.source,
                "symbol": a.symbol.upper(), "criterion": a.criterion,
                "close_at": a.close_at, "price_source": a.price_source,
                "scenarios": [_scenario(s) for s in a.scenario], "result": None})
            save(a.file, doc)
            print(f"✅ پیش‌بینی {a.id} ثبت شد — مهلت {a.close_at}")
            return 0
        if a.cmd == "score":
            n, fails = score(doc, now)
            save(a.file, doc)
            print(f"نمره تازه: {fa(n)}")
            for x in fails:
                print(f"⚠️ {x}")
            return 2 if fails else 0
    except ForecastError as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 2
    md, line = report(doc, now), summary_line(doc)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
    if a.line:
        with open(a.line, "w", encoding="utf-8") as f:
            f.write(line + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
