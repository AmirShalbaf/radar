#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_brief.py — گردآورنده پیام صبح رادار، متن ۳۷
=====================================================

لایه پیام سه طبقه دارد و فقط این فایل درون رادار را می‌شناسد:

    سازنده‌ها ── سند کناری و فایل داده ──► radar_brief.py ──► reports/brief.json
                                       (مترجم)                   (قرارداد)
    reports/brief.json ──► radar_brief_render.py ──► radar_telegram.py
                            (متن و تصویر)            (ارسال با رسید)

قاعده پایداری — references/brief-contract.md:
- نمایش‌دهنده فقط brief.json را می‌خواند؛ هیچ فایل دیگری از رادار را نه.
- تغییر هر سازنده یا فایل داده فقط همین مترجم را عوض می‌کند. آزمون‌های
  tests/test_brief_contract.py سند هر سازنده را با تابع خود سازنده می‌سازند و
  به مترجم می‌دهند؛ تغییر ناسازگار پیش از push قرمز می‌شود، نه بی‌صدا در تلگرام.
- هر بخش جداست. خطای یک بخش فقط همان بخش را «داده ندارم» با دلیل می‌کند؛ باقی
  پیام می‌رود و فهرست بخش‌های افتاده در خود پیام می‌آید.
- سند کناری کهنه‌تر از MAX_SIDECAR_AGE_H داده امروز نیست و رد می‌شود.

اجرا:
    python radar_brief.py collect --out reports/brief.json
    python radar_brief.py collect --out /tmp/b.json --no-chart     # بی شبکه
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

from radar_text import fa

UTC = timezone.utc
TEHRAN = timezone(timedelta(hours=3, minutes=30))     # ایران از ۲۰۲۲ ساعت تابستانی ندارد
SCHEMA = 1
MAX_SIDECAR_AGE_H = 6.0       # سند کناری امروز؛ کهنه‌تر یعنی سازنده امروز نیفتاده نوشته
CAL_DAYS = 10                 # تقویم پیام صبح
CAL_MAX = 6
TRIG_MAX = 6
CHART_DAYS = 90
LESSON_COOLDOWN_DAYS = 7
WATCH_MAX_AGE_DAYS = 14       # همان سقف بازبینی سطح‌ها — radar_watch
TIER_RED, TIER_AMBER = 3.0, 10.0     # افت لازم تا ابطال، درصد
WIND_EPS = 0.25               # امتیاز ورودی رژیم: کمتر از این نزدیک صفر — خنثی

FILES = {
    "scan": "reports/scan.json", "book": "reports/book.json",
    "levels": "reports/levels.json", "context": "reports/context.json",
    "regime": "regime.json", "watch": "watch.json", "pump": "pump.json",
    "forecasts": "forecasts.json", "optcost": "radar_optcost.json",
    "ledger": "events_ledger.json", "calendar": "events_calendar.json",
    "pulse": "pulse_log.json", "snapshot": "snapshot.json",
    "lessons": "references/lessons.json", "prev": "reports/brief.json",
}
SIDECARS = ("scan", "book", "levels", "context")
WEEKDAY = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")
JALALI_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")


class Missing(Exception):
    """داده لازم نیست یا کهنه است — «داده ندارم» با دلیل، نه خطای برنامه."""


# ═══════════════════════ تاریخ و زمان ═══════════════════════

def jalali(y: int, m: int, d: int) -> tuple[int, int, int]:
    """تبدیل میلادی به شمسی — الگوریتم حسابی رایج، بی کتابخانه."""
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = y + 1 if m > 2 else y
    days = (355666 + 365 * y + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            + d + g_d_m[m - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def tehran(t: datetime) -> datetime:
    return t.astimezone(TEHRAN)


def day_label(t: datetime, with_year: bool = False) -> str:
    """«سه‌شنبه ۱۲ آبان» به وقت تهران."""
    tt = tehran(t)
    jy, jm, jd = jalali(tt.year, tt.month, tt.day)
    s = f"{WEEKDAY[tt.weekday()]} {fa(jd)} {JALALI_MONTHS[jm - 1]}"
    return s + (f" {fa(jy)}" if with_year else "")


def clock(t: datetime) -> str:
    return fa(tehran(t).strftime("%H:%M"))


def _ts(raw) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        try:
            t = datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        except ValueError:
            return None
    return t if t.tzinfo else None


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def drop_pct(price: float, level: float) -> float:
    """افت لازم تا سطح، درصد از قیمت — یک تعریف برای پیام و تصویر."""
    return 100.0 * (price - level) / price


def move_pct(price: float, level: float) -> float:
    """حرکت علامت‌دار لازم تا سطح: مثبت یعنی بالا رفتن."""
    return 100.0 * (level / price - 1.0)


# ═══════════════════════ منبع‌ها ═══════════════════════

class Sources:
    """خواندن تنبل فایل‌ها با مسیر قابل جایگزینی — آزمون پوشه ساختگی می‌دهد."""

    def __init__(self, root: str = ".", now: datetime | None = None, files: dict | None = None):
        self.root, self.now = root, now or datetime.now(UTC)
        self.files = dict(FILES, **(files or {}))
        self._cache: dict = {}

    def path(self, key: str) -> str:
        p = self.files[key]
        return p if os.path.isabs(p) else os.path.join(self.root, p)

    def get(self, key: str, required: bool = True):
        if key in self._cache:
            return self._cache[key]
        p = self.path(key)
        if not os.path.exists(p):
            if required:
                raise Missing(f"`{self.files[key]}` نیست")
            self._cache[key] = None
            return None
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as exc:
            raise Missing(f"`{self.files[key]}` خوانا نیست — {type(exc).__name__}") from exc
        if key in SIDECARS:
            gen = _ts((doc or {}).get("generated"))
            if gen is None:
                raise Missing(f"`{self.files[key]}` مهر زمان ندارد")
            age = (self.now - gen).total_seconds() / 3600
            if age > MAX_SIDECAR_AGE_H:
                raise Missing(f"`{self.files[key]}` کهنه است — {fa(f'{age:.0f}')} ساعت پیش")
        self._cache[key] = doc
        return doc


# ═══════════════════════ بخش‌ها ═══════════════════════

def sec_capital(src: Sources) -> dict:
    b = src.get("book")
    cap, reg = b["capital"], b.get("regime") or {}
    total = cap["total"]
    if not _num(total) or total <= 0:
        raise Missing("کل سرمایه معلوم نیست")
    assets = [{"symbol": "USDT", "value": cap["stable_usd"], "pct": 100 * cap["stable_usd"] / total}]
    for p in b.get("positions") or []:
        if p.get("dust") or not _num(p.get("value")):
            continue
        assets.append({"symbol": p["symbol"], "value": p["value"], "pct": 100 * p["value"] / total})
    assets.sort(key=lambda a: -a["value"])
    risk = b.get("pos_risk_usd")
    return {"total": total, "stable_usd": cap["stable_usd"],
            "stable_pct": 100 * cap["stable_usd"] / total,
            "target_pct": reg.get("stable_target"), "assets": assets,
            "pos_risk_usd": risk, "pos_risk_pct": 100 * risk / total if _num(risk) else None,
            "incomplete": bool(cap.get("incomplete")), "missing": cap.get("missing") or [],
            "prices_at": b["generated"]}


def sec_positions(src: Sources) -> dict:
    b = src.get("book")
    rows = []
    for p in b.get("positions") or []:
        if p.get("dust") or not _num(p.get("price")):
            continue
        inv, px, wk = p.get("invalidation"), p["price"], p.get("weekly_close")
        r = {"symbol": p["symbol"], "value": p.get("value"), "price": px,
             "invalidation": inv, "drop_pct": None, "tier": "none",
             "week_chg_pct": move_pct(wk, px) if _num(wk) and wk > 0 else None}
        if _num(inv) and px > 0:
            d = drop_pct(px, inv)
            r["drop_pct"] = d
            r["tier"] = "red" if d < TIER_RED else "amber" if d < TIER_AMBER else "green"
        rows.append(r)
    rows.sort(key=lambda r: -(r["value"] or 0))
    drops = [r["drop_pct"] for r in rows if _num(r["drop_pct"])]
    return {"rows": rows, "judge": "بسته هفتگی، دوشنبه ۰۳:۳۰ تهران",
            "min_drop_pct": min(drops) if drops else None}


def _band_gaps(score: float) -> tuple[dict | None, dict | None]:
    """فاصله تا باند بالاتر و پایین‌تر — از جدول خود radar_budget، نه عدد اینجا."""
    import radar_budget as BG
    bands = list(BG.BANDS)                    # از بازترین به محافظه‌کارترین
    for i, (floor, name, *_rest) in enumerate(bands):
        if floor is None or score > floor:
            up = ({"name": bands[i - 1][1], "gap": bands[i - 1][0] - score}
                  if i > 0 else None)
            down = ({"name": bands[i + 1][1], "gap": score - floor}
                    if floor is not None and i + 1 < len(bands) else None)
            return up, down
    return None, None


def sec_regime(src: Sources) -> dict:
    r = src.get("regime")
    score = r.get("score")
    if not _num(score):
        raise Missing("امتیاز رژیم نیست")
    gen = _ts(r.get("generated_at"))
    band = r.get("band") or {}
    tb = r.get("trade_band")
    tname = tb.get("name") if isinstance(tb, dict) else tb if isinstance(tb, str) else None
    up, down = _band_gaps(score)
    pillars = [{"label": c.get("label", k), "score": c.get("score")}
               for k, c in (r.get("columns") or {}).items() if isinstance(c, dict)]
    return {"score": score, "band": band.get("name"), "trade_band": tname or band.get("name"),
            "cap_pct": band.get("cap"), "mult": band.get("mult"), "maxpos": band.get("maxpos"),
            "stable_target": band.get("stable"), "up": up, "down": down, "pillars": pillars,
            "generated": gen.isoformat() if gen else None,
            "age_h": (src.now - gen).total_seconds() / 3600 if gen else None}


def sec_winds(src: Sources) -> dict:
    """بادها = ورودی‌های خود مدل رژیم با نشانه امتیازشان. قاعده تازه ساخته نمی‌شود."""
    r = src.get("regime")
    items = []
    for i in r.get("inputs") or []:
        s = i.get("score")
        if not _num(s):
            continue
        d = -1 if s <= -WIND_EPS else 1 if s >= WIND_EPS else 0
        items.append({"label": i.get("label") or i.get("key"), "score": s, "dir": d,
                      "value": i.get("value") if _num(i.get("value")) else None})
    if not items:
        raise Missing("ورودی امتیازدار رژیم نیست")
    items.sort(key=lambda x: x["score"])
    return {"items": items, "neg": sum(x["dir"] < 0 for x in items),
            "neu": sum(x["dir"] == 0 for x in items), "pos": sum(x["dir"] > 0 for x in items)}


def _scan_row(scan: dict, sym: str) -> dict:
    for row in scan.get("rows") or []:
        if str(row.get("symbol", "")).upper() == sym:
            return row
    return {}


def sec_market(src: Sources) -> dict:
    scan = src.get("scan")
    mac = scan.get("macro") or {}

    def mval(k):
        m = mac.get(k) or {}
        v = m.get("value")
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        ts = _ts(m.get("ts"))
        return v, ((src.now - ts).total_seconds() / 3600 if ts else None)

    btc = _scan_row(scan, "BTC")
    px = btc.get("price")
    snap = src.get("snapshot", required=False) or {}
    sgen = _ts(snap.get("generated_utc"))
    srow = (snap.get("symbols") or {}).get("BTC") or {}
    chg24 = None
    if sgen and (src.now - sgen).total_seconds() / 3600 <= MAX_SIDECAR_AGE_H:
        chg24 = srow.get("chg24_pct") if _num(srow.get("chg24_pct")) else None
    sma = ((src.get("regime", required=False) or {}).get("btc_sma50w") or {}).get("value")
    fg, fg_age = mval("fear_greed")
    dom, _ = mval("btc_dominance")
    st30, _ = mval("stable_change_30d")
    crowd = []
    for row in scan.get("rows") or []:
        c, w = row.get("ls_crowd"), row.get("ls_whale")
        if _num(c) and _num(w) and w > 0:
            crowd.append({"symbol": row["symbol"], "crowd": c, "whale": w, "ratio": c / w})
    crowd.sort(key=lambda x: -x["ratio"])
    fund = [row.get("funding_8h") for row in scan.get("rows") or [] if _num(row.get("funding_8h"))]
    return {"btc": {"price": px if _num(px) else None, "chg24": chg24,
                    "rsi": btc.get("rsi") if _num(btc.get("rsi")) else None,
                    "sma50w": sma if _num(sma) else None,
                    "above_sma_pct": move_pct(sma, px) if _num(px) and _num(sma) and sma else None},
            "fear_greed": fg, "fear_greed_age_h": fg_age, "btc_dominance": dom,
            "stable_30d": st30,
            "crowd": crowd, "crowd_flagged": sum(1 for x in crowd if x["ratio"] > 1.5),
            "crowd_n": len(crowd),
            "funding_avg": sum(fund) / len(fund) if fund else None,
            "prices_at": scan["generated"]}


def sec_context(src: Sources) -> dict:
    c = src.get("context")
    rows = [r for r in c.get("rows") or [] if isinstance(r, dict)]
    if not rows:
        raise Missing("سری زمینه نیامد")
    return {"rows": [{"short": r.get("short") or r.get("name"), "value": r.get("value"),
                      "unit": r.get("unit") or "", "chg": r.get("chg"),
                      "chg_unit": r.get("chg_unit"), "lag_days": r.get("lag_days")}
                     for r in rows]}


def sec_calendar(src: Sources) -> dict:
    import radar_calendar as RC
    now, until = src.now, src.now + timedelta(days=CAL_DAYS)
    items, seen = [], set()
    cal = RC.load(src.path("calendar"))
    for e in RC.upcoming(cal, now, CAL_DAYS):
        at = RC.at_of(e)
        win = None
        if at is not None and e["importance"] == "high":
            a, b = RC.no_new_window(e)
            win = [a.isoformat(), b.isoformat()]
        day = (at.date() if at else datetime.fromisoformat(e["date"]).date())
        items.append({"at": at.isoformat() if at else None, "date": day.isoformat(),
                      "name": e["name"], "importance": e["importance"], "window": win,
                      "source": "دستی"})
        if at is not None:
            seen.add(at.replace(second=0, microsecond=0))
    led = src.get("ledger", required=False) or {}
    for e in led.get("events") or []:
        at = _ts(e.get("at"))
        if at is None or not (now <= at <= until) or at.replace(second=0, microsecond=0) in seen:
            continue
        items.append({"at": at.isoformat(), "date": at.date().isoformat(),
                      "name": e.get("title") or e.get("kind"), "importance": e.get("importance"),
                      "window": None, "source": "خودکار"})
    def key(x):
        return x["at"] or (x["date"] + "T00:00:00+00:00")
    items.sort(key=key)
    highs = [_ts(x["at"]) for x in items if x["importance"] == "high" and x["at"]]
    nxt = min(highs) if highs else None
    rank = {"high": 0, "medium": 1, "low": 2}
    if len(items) > CAL_MAX:          # نزدیک‌ترین‌ها، ولی رویداد بالا کنار نمی‌رود
        keep = sorted(items, key=lambda x: (rank.get(x["importance"], 3), key(x)))[:CAL_MAX]
        items = sorted(keep, key=key)
    return {"items": items, "days": CAL_DAYS,
            "next_high_h": (nxt - now).total_seconds() / 3600 if nxt else None}


def _prices(src: Sources) -> dict:
    """قیمت هر نماد از تازه‌ترین سند همین اجرا: سبد، اسکن، نبض."""
    out = {}
    snap = src.get("snapshot", required=False) or {}
    sgen = _ts(snap.get("generated_utc"))
    if sgen and (src.now - sgen).total_seconds() / 3600 <= MAX_SIDECAR_AGE_H:
        for s, row in (snap.get("symbols") or {}).items():
            if _num((row or {}).get("price")):
                out[s.upper()] = row["price"]
    for key in ("scan", "book"):
        try:
            doc = src.get(key)
        except Missing:
            continue
        rows = doc.get("rows") if key == "scan" else doc.get("positions")
        for row in rows or []:
            if _num(row.get("price")):
                out[str(row["symbol"]).upper()] = row["price"]
    return out


def sec_triggers(src: Sources) -> dict:
    prices = _prices(src)
    book = src.get("book")
    watch = src.get("watch", required=False) or {}
    trig = []

    def add(sym, kind, level, judge, label):
        px = prices.get(sym)
        if not (_num(px) and _num(level) and px > 0):
            return
        trig.append({"symbol": sym, "kind": kind, "level": level, "judge": judge,
                     "label": label, "price": px, "move_pct": move_pct(px, level)})

    for p in book.get("positions") or []:
        if not p.get("dust") and _num(p.get("invalidation")):
            add(p["symbol"], "invalidation", p["invalidation"], "weekly", "ابطال — فروش")
    for e in book.get("reentry") or []:
        if _num(e.get("level")):
            add(e["symbol"], "reentry", e["level"], "weekly", "ورود دوباره مجاز")
    for it in watch.get("items") or []:
        sym = str(it.get("symbol", "")).upper()
        for lv in it.get("alerts") or []:
            add(sym, "alert", lv, "live", "هشدار عبور")
        for lv in it.get("ladder") or []:
            add(sym, "ladder", lv, "live", "پله خرید")
        for lv in it.get("targets") or []:
            add(sym, "target", lv, "live", "هدف")
    trig.sort(key=lambda t: abs(t["move_pct"]))
    if not trig:
        raise Missing("ماشه‌ای با قیمت معلوم نیست")
    return {"items": trig[:TRIG_MAX], "total": len(trig)}


def sec_trade(src: Sources) -> dict:
    b = src.get("book")
    t, reg = b.get("trade") or {}, b.get("regime") or {}
    lv = src.get("levels", required=False)
    pump = src.get("pump", required=False) or {}
    secs = pump.get("sections") or {}
    cands = [c.get("symbol") for c in (lv or {}).get("candidates") or []]
    return {"risk_cap_usd": t.get("risk_cap"), "risk_used_usd": t.get("risk_used"),
            "risk_left_usd": t.get("risk_left"), "mult": reg.get("mult"),
            "maxpos": reg.get("maxpos"), "band": reg.get("trade_band"),
            "levels_known": lv is not None, "levels_candidates": cands,
            "pump_cards": pump.get("cards_n"),
            "pump_long": len(secs.get("long") or []), "pump_short": len(secs.get("short") or []),
            "pump_after": len(secs.get("afterpump") or []),
            "setups_ready": len(cands) + int(pump.get("cards_n") or 0)}


def sec_scorecard(src: Sources) -> dict:
    prices = _prices(src)
    oc = src.get("optcost", required=False) or {}
    exits = []
    since = src.now - timedelta(days=30)
    for x in oc.get("exits") or []:
        at = _ts(x.get("at")) or _ts(f"{x.get('date')}T00:00:00+00:00")
        sym = str(x.get("symbol", "")).upper()
        if at is None or at < since or not _num(x.get("price")) or not _num(x.get("qty")):
            continue
        now_px = prices.get(sym)
        saved = x["qty"] * (x["price"] - now_px) if _num(now_px) else None
        exits.append({"symbol": sym, "at": at.isoformat(), "price": x["price"], "qty": x["qty"],
                      "now": now_px, "saved_usd": saved, "reason": x.get("reason")})
    exits.sort(key=lambda e: e["at"], reverse=True)
    fc = src.get("forecasts", required=False) or {}
    open_, briers = [], []
    for f in fc.get("forecasts") or []:
        res = f.get("result")
        if isinstance(res, dict) and _num(res.get("brier")):
            briers.append(res["brier"])
        elif not res:
            sc = sorted(f.get("scenarios") or [], key=lambda s: -(s.get("p") or 0))
            open_.append({"id": f.get("id"), "symbol": f.get("symbol"),
                          "close_at": f.get("close_at"),
                          "top": {"name": sc[0].get("name"), "p": sc[0].get("p"),
                                  "interval": sc[0].get("interval")} if sc else None})
    return {"exits": exits[:3], "forecasts_open": open_, "scored_n": len(briers),
            "brier_mean": sum(briers) / len(briers) if briers else None}


def _next_week_close(now: datetime) -> datetime:
    d = now.astimezone(UTC)
    days = (7 - d.weekday()) % 7 or 7
    return (d + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)


def sec_todo(src: Sources) -> dict:
    items = []
    b = src.get("book", required=False)
    if b is None:
        raise Missing("`reports/book.json` نیست")
    for a in b.get("actions") or []:
        items.append({"level": "red", "text": a})
    w = src.get("watch", required=False)
    up = _ts((w or {}).get("updated"))
    if up is not None:
        age = (src.now - up).total_seconds() / 86400
        if age > WATCH_MAX_AGE_DAYS:
            items.append({"level": "amber", "text": f"بازبینی سطح‌های ابطال — {fa(f'{age:.0f}')} "
                                                     f"روز گذشته، سقف {fa(WATCH_MAX_AGE_DAYS)}"})
    wc = _next_week_close(src.now)
    if (wc - src.now) <= timedelta(days=3):
        items.append({"level": "info", "text": f"بسته هفتگی {day_label(wc)} ساعت {clock(wc)}"})
    fc = src.get("forecasts", required=False) or {}
    for f in fc.get("forecasts") or []:
        ca = _ts(f.get("close_at"))
        if not f.get("result") and ca and src.now <= ca <= src.now + timedelta(days=3):
            items.append({"level": "info", "text": f"پیش‌بینی {f.get('symbol')} — داوری "
                                                    f"{day_label(ca)} ساعت {clock(ca)}"})
    return {"items": items}


def sec_health(src: Sources) -> dict:
    import radar_schedule as RS
    log = src.get("pulse")
    st = RS.health_stats(log, src.now)
    return st


# ═══════════════════════ درس روز ═══════════════════════

def _lesson_ok(cond: dict, data: dict) -> bool:
    """شرط درس: مسیر نقطه‌دار در داده پیام، با یکی از lt، gt، abs_lt، eq، min."""
    cur = data
    for part in str(cond.get("path", "")).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return False
    if "eq" in cond:
        return cur == cond["eq"]
    if not _num(cur):
        return False
    if "lt" in cond and not cur < cond["lt"]:
        return False
    if "gt" in cond and not cur > cond["gt"]:
        return False
    if "abs_lt" in cond and not abs(cur) < cond["abs_lt"]:
        return False
    if "min" in cond and not cur >= cond["min"]:
        return False
    return True


def pick_lesson(lib: dict, data: dict, history: list, now: datetime) -> dict | None:
    """بالاترین اولویتی که شرطش برقرار است و در LESSON_COOLDOWN_DAYS روز اخیر نیامده."""
    recent = set()
    for h in history or []:
        t = _ts(h.get("at")) if isinstance(h, dict) else None
        if t and (now - t) < timedelta(days=LESSON_COOLDOWN_DAYS):
            recent.add(h.get("id"))
    pool = []
    for l in lib.get("lessons") or []:
        conds = l.get("when") or []
        if all(_lesson_ok(c, data) for c in conds):
            pool.append(l)
    pool.sort(key=lambda l: -(l.get("priority") or 0))
    fresh = [l for l in pool if l.get("id") not in recent]
    if fresh:
        return fresh[0]
    # همه در هفته اخیر آمده‌اند: آنکه دیرتر از همه آمده — هرگز روز بی‌درس
    last = {}
    for h in history or []:
        if isinstance(h, dict) and _ts(h.get("at")):
            last[h.get("id")] = _ts(h["at"])
    pool.sort(key=lambda l: last.get(l.get("id"), datetime.min.replace(tzinfo=UTC)))
    return pool[0] if pool else None


# ═══════════════════════ نمودار ═══════════════════════

def chart_fetch(symbol: str, days: int = CHART_DAYS) -> list[list]:
    """بسته روزانه وقت جهانی با کندل زنده آخر — همان مسیر کندل سبد."""
    import radar_book as B
    df = B.candles(symbol, "1D", days + 1)
    if df is None or len(df) < 10:
        raise Missing(f"کندل روزانه {symbol} نیامد")
    df = df.tail(days)
    return [[t.isoformat(), float(c)] for t, c in zip(df["ts"], df["c"]) if math.isfinite(float(c))]


def sec_chart(data: dict, fetch) -> dict:
    series = []
    m = (data.get("market") or {})
    btc_lv = []
    if m.get("ok") and _num((m.get("btc") or {}).get("sma50w")):
        btc_lv.append({"value": m["btc"]["sma50w"], "label": "میانگین ۵۰ هفته", "kind": "sma"})
    series.append({"symbol": "BTC", "points": fetch("BTC"), "levels": btc_lv, "marks": []})
    trig = (data.get("triggers") or {})
    focus = None
    if trig.get("ok"):
        for t in trig["items"]:
            if t["symbol"] != "BTC":
                focus = t["symbol"]
                break
    if focus:
        lv = [{"value": t["level"], "label": t["label"], "kind": t["kind"]}
              for t in trig["items"] if t["symbol"] == focus]
        marks = [{"at": e["at"], "value": e["price"], "label": "فروش"}
                 for e in ((data.get("scorecard") or {}).get("exits") or [])
                 if e["symbol"] == focus][:1]
        series.append({"symbol": focus, "points": fetch(focus), "levels": lv, "marks": marks})
    return {"series": series, "days": CHART_DAYS}


# ═══════════════════════ حکم و سرهم‌کردن ═══════════════════════

SECTIONS = (
    ("capital", sec_capital), ("positions", sec_positions), ("regime", sec_regime),
    ("winds", sec_winds), ("market", sec_market), ("context", sec_context),
    ("calendar", sec_calendar), ("triggers", sec_triggers), ("trade", sec_trade),
    ("scorecard", sec_scorecard), ("todo", sec_todo), ("health", sec_health),
)
TITLES = {"capital": "سرمایه", "positions": "سبد", "regime": "رژیم", "winds": "بادها",
          "market": "بازار", "context": "زمینه", "calendar": "تقویم", "triggers": "ماشه‌ها",
          "trade": "دفتر معامله", "scorecard": "کارنامه", "todo": "کارها", "health": "سلامت",
          "lesson": "درس روز", "chart": "نمودار"}


def _safe(fn, *args) -> dict:
    try:
        out = fn(*args)
        return {"ok": True, **out}
    except Missing as exc:
        return {"ok": False, "why": str(exc)}
    except Exception as exc:                     # بلند در پیام، نه بلعیده
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}


def verdict(data: dict, now: datetime) -> dict:
    todo = data.get("todo") or {}
    must = [i["text"] for i in todo.get("items") or [] if i["level"] == "red"]
    overdue = [i["text"] for i in todo.get("items") or [] if i["level"] == "amber"]
    tr = data.get("trade") or {}
    setups = None
    if tr.get("ok"):
        setups = (tr.get("levels_candidates") or []) + (
            [f"{fa(tr['pump_cards'])} کارت اسکنر"] if tr.get("pump_cards") else [])
    windows = []
    cal = data.get("calendar") or {}
    for e in cal.get("items") or []:
        if e.get("window"):
            a, b = _ts(e["window"][0]), _ts(e["window"][1])
            if b and b >= now:
                windows.append({"name": e["name"], "start": a.isoformat(), "end": b.isoformat(),
                                "active": a <= now <= b})
    if not todo.get("ok"):
        head, level = "⚠️ حکم امروز معلوم نیست — داده سبد نیامد", "unknown"
    elif must:
        head, level = f"🔴 امروز {fa(len(must))} اقدام اجباری داری", "red"
    else:
        head, level = "✅ امروز اقدام اجباری نداری", "green"
    return {"level": level, "headline": head, "must": must, "overdue": overdue,
            "setups": setups, "windows": windows[:2]}


def collect(src: Sources, fetch=None, lessons: bool = True) -> dict:
    now = src.now
    data: dict = {}
    for name, fn in SECTIONS:
        data[name] = _safe(fn, src)
    prev = None
    try:
        prev = src.get("prev", required=False)
    except Missing:
        prev = None
    history = list((prev or {}).get("lesson_history") or [])[-30:]
    lesson = {"ok": False, "why": "درس خاموش"}
    if lessons:
        try:
            lib = src.get("lessons")
            got = pick_lesson(lib, data, history, now)
            lesson = ({"ok": True, **got} if got else {"ok": False, "why": "درسی با شرط امروز نیست"})
        except Missing as exc:
            lesson = {"ok": False, "why": str(exc)}
    data["lesson"] = lesson
    if lesson.get("ok"):
        history.append({"at": now.isoformat(timespec="seconds"), "id": lesson.get("id")})
    if fetch is not None:
        data["chart"] = _safe(sec_chart, data, fetch)
    else:
        data["chart"] = {"ok": False, "why": "نمودار خاموش — بی شبکه"}
    failed = [n for n, s in data.items() if not s.get("ok") and n != "chart"]
    return {
        "schema": SCHEMA, "generated": now.isoformat(timespec="seconds"),
        "day": day_label(now, with_year=True), "clock": clock(now),
        "verdict": verdict(data, now), "sections": data,
        "failed": [{"name": n, "title": TITLES.get(n, n), "why": data[n].get("why")}
                   for n in failed],
        "lesson_history": history,
    }


def validate(doc: dict) -> list[str]:
    """ناوردای قرارداد — نمایش‌دهنده به همین تکیه می‌کند. فهرست خطا؛ تهی یعنی سالم."""
    errs = []
    if doc.get("schema") != SCHEMA:
        errs.append(f"schema {doc.get('schema')!r} نه {SCHEMA}")
    for k in ("generated", "day", "clock", "verdict", "sections", "failed"):
        if k not in doc:
            errs.append(f"کلید {k} نیست")
    secs = doc.get("sections") or {}
    for name in [n for n, _ in SECTIONS] + ["lesson", "chart"]:
        s = secs.get(name)
        if not isinstance(s, dict) or "ok" not in s:
            errs.append(f"بخش {name} نیست یا ok ندارد")
        elif not s["ok"] and not s.get("why"):
            errs.append(f"بخش {name} افتاده ولی دلیل ندارد")
    v = doc.get("verdict") or {}
    if v.get("level") not in ("green", "red", "unknown"):
        errs.append("verdict.level نامعتبر")
    return errs


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="گردآورنده پیام صبح رادار — متن ۳۷")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("collect")
    p.add_argument("--out", default=FILES["prev"])
    p.add_argument("--root", default=".")
    p.add_argument("--no-chart", action="store_true", dest="no_chart")
    a = ap.parse_args(argv)
    src = Sources(a.root, now)
    doc = collect(src, fetch=None if a.no_chart else chart_fetch)
    errs = validate(doc)
    if errs:                                  # باگ مترجم — هرگز سند نیمه‌سالم
        print("⛔ سند پیام صبح با قرارداد نمی‌خواند: " + "؛ ".join(errs))
        return 3
    import radar_sidecar as SC
    SC.write_json(a.out, doc)
    bad = "، ".join(f["title"] for f in doc["failed"]) or "هیچ"
    print(f"✅ {a.out} — بخش‌های افتاده: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
