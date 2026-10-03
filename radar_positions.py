#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_positions.py — دو دفتر و دفتر کل تغییرات، رادار ۷
=======================================================

تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶ — «دو دفتر». سقف ریسک رژیم برای معامله کوتاه
با حد ضرر طراحی شده؛ اعمال لفظی آن روی سبد بلندمدت یعنی فروش حدود ۹۰٪.

    دفتر موقعیت   کوین‌های موجود ۲۵ سپتامبر. عضویت منجمد. ابطال با بسته
                  هفتگی، هدف ذخیره رژیم روی کل سرمایه، سه‌ضربه، نردبان خروج،
                  و ورود دوباره پس از خروج با ابطال.
    دفتر معامله   هر معامله تازه، واقعی یا فرضی. سقف ریسک رژیم فقط اینجا.

قاعده سخت ضدبهانه: هیچ پوزیشنی هرگز از دفتر معامله به دفتر موقعیت نمی‌رود.

holdings.json نسخه ۲ بر پایه **مقدار** است، نه دلار. ارزش هر روز از قیمت
زنده حساب می‌شود؛ دلار ثابت نسخه ۱ دلیل کهنه‌شدن فایل بود. نسخه ۱ خطای
صریح «قالب قدیمی — مهاجرت لازم» می‌دهد.

ناوردای دفتر کل، برای هر نماد دفتر موقعیت:

    مقدار منجمد + جمع تغییرات ثبت‌شده = مقدار فعلی

هر اختلاف ثبت‌نشده، بالا یا پایین، خطای صریح است. تغییر فقط با فرمان و
یک ردیف دفتر کل:

    trim     کاهش، با دلیل reserve (ذخیره) یا rebalance (بازتوازن)
    exit     خروج کامل با ابطال؛ سطح و مقدار، سهمیه ورود دوباره می‌سازند
    reenter  ورود دوباره، فقط اگر بسته هفتگی بالای همان سطح رفت، تا سهمیه
    add      افزایش، فقط با شناسه تصمیم و ستاپ ثبت‌شده در دفترچه با
             book = position
    adjust   پاداش سهام‌گذاری یا کارمزد، حداکثر ۱٪ مقدار نماد در هر ردیف
    withdraw برداشت از رادار — پولی که دیگر جزو سبد نیست، مثل خرج شخصی. فقط
             کاهش، با دلیل و حساب؛ نقد همان حساب در همان ردیف. نه پیگیری
             هزینه فرصت، نه سهمیه ورود دوباره، نه آمار نتیجه — الگوی ONDO ک۱۰.
             با --symbol USDT فقط نقد همان حساب کم می‌شود و ناوردای کوین‌ها
             دست نمی‌خورد. --at زمان برداشت؛ زمان دقیق نامعلوم یعنی زمان شاهد،
             مثل اسکرین‌شات، و همین در دلیل

بسته هفتگی = بسته کندل هفته دوشنبه تا یکشنبه به وقت جهانی، یعنی لحظه
**دوشنبه ۰۰:۰۰ UTC**. اوکی‌اکس با 1Wutc، گیت با 7d. لنگر پیش‌فرض اوکی‌اکس
وقت هنگ‌کنگ است — یکشنبه 16:00 UTC — و هرگز استفاده نمی‌شود. اگر هیچ‌کدام
از دو لنگر وقت جهانی در دسترس نبود: «داده ندارم».

فقط کتابخانه استاندارد، به‌علاوه requests اختیاری برای بسته هفتگی — تا
radar_book.py بتواند بی‌آنکه استقلالش بشکند ایمپورتش کند.

    python radar_positions.py validate
    python radar_positions.py trim --symbol SOL --qty 1.5 --price 120 --reason reserve
    python radar_positions.py exit --symbol SOL --price 95 --level 100
    python radar_positions.py reenter --symbol SOL --qty 4 --price 105 --account LBank
    python radar_positions.py add --symbol LINK --qty 10 --price 14 --account LBank \\
        --decision-id D-... --setup-name ...
    python radar_positions.py adjust --symbol SOL --qty 0.02 --reason "پاداش سهام‌گذاری"
    python radar_positions.py withdraw --symbol USDT --qty 12 --account LBank \\
        --reason "پول خرج شخصی" --at 2026-10-03T04:10:00+00:00
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import radar_anchor as A
import radar_journal as RJ
import radar_optcost as RO

try:
    import requests
except ImportError:
    requests = None

# خطای شبکه صریح، نه `except Exception`: بقیه خطاها باید بالا بروند
NET_ERRORS = (requests.RequestException,) if requests is not None else ()

UTC = timezone.utc
FORMAT_VERSION = 2
# کهنگی holdings.json از میدان updated داخلی — تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶
HOLDINGS_STALE_DAYS = 7
HOLDINGS_FILE = "holdings.json"
BOOKS = RJ.BOOKS
# withdraw تصمیم کاربر، ۲۹ سپتامبر ۲۰۲۶. نوع جدا، نه adjust: سقف ۱٪ adjust
# برای پاداش و کارمزد است و شل‌کردنش ناوردا را برای همه ردیف‌ها سست می‌کرد
ACTIONS = ("trim", "exit", "reenter", "add", "adjust", "withdraw")
# invalidation: خروج جزئی با ابطال — سهم خروج در watch.json پارامتر است
TRIM_REASONS = ("reserve", "rebalance", "invalidation")
ADJUST_MAX = 0.01             # سقف هر ردیف adjust: ۱٪ مقدار نماد
STABLE_ASSETS = {"USDT", "USDC"}
STABLE_PRICE = 1.0            # استیبل با قیمت ثابت ۱ دلار ارزش‌گذاری می‌شود
DUST_USD = 1.0                # زیر ۱ دلار «ناچیز»: در سرمایه هست، سطح و نردبان نه
NON_ALT = {"BTC", "XAUT", "PAXG"} | STABLE_ASSETS
CORR_ALT_LONGS = 3            # بند ۸.۳ اسکیل: از سه لانگ آلت هم‌زمان به بالا
CORR_FACTOR = 1.5
TOL = 1e-9
WEEK = timedelta(days=7)
OKX = "https://www.okx.com/api/v5/market/candles"
GATE = "https://api.gateio.ws/api/v4/spot/candlesticks"
# لنگرهای وقت جهانی — تنها لنگرهای مجاز بسته هفتگی؛ منبع radar_anchor
OKX_WEEK_BAR = A.BAR["okx"]["1W"]
GATE_WEEK_INTERVAL = A.BAR["gate"]["1W"]


class PositionsError(Exception):
    """خطای صریح دفترها — هرگز بی‌صدا بلعیده نمی‌شود."""


# ═══════════════════════ کمک‌تابع‌ها ═══════════════════════

def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _ts(raw, what: str) -> datetime:
    if not isinstance(raw, str):
        raise PositionsError(f"{what} نیست یا رشته نیست")
    try:
        t = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PositionsError(f"{what} قابل‌خواندن نیست: {raw!r}") from exc
    if t.tzinfo is None:
        raise PositionsError(f"{what} منطقه زمانی ندارد: {raw!r}")
    return t


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def position_qty(p: dict) -> float:
    return sum(float(l["qty"]) for l in p.get("lots") or [])


def _journal_index(journal: dict) -> dict:
    return {t.get("decision_id"): t for t in journal.get("trades", [])
            if t.get("decision_id")}


def _book_of(rec: dict) -> str:
    return rec.get("book", "trade")


def age_days(h: dict, now: datetime | None = None) -> float:
    """کهنگی از میدان updated داخل فایل — نه زمان تغییر فایل، که checkout گیت تازه‌اش می‌کند."""
    now = now or datetime.now(UTC)
    return (now - _ts(h.get("updated"), "میدان updated")).total_seconds() / 86400


# ═══════════════════════ اعتبارسنجی ═══════════════════════

def level_since(p: dict) -> datetime | None:
    """
    زمان اعتبار سطح ابطال پوزیشن: میدان اختیاری invalidation_since، مهر کامل
    با منطقه زمانی. فقط تاریخ خطاست — تصمیم کاربر، ۲۶ سپتامبر ۲۰۲۶. غایب
    یعنی None: سطح از قبل معتبر بوده — رفتار پیشین.
    """
    raw = p.get("invalidation_since")
    if raw is None:
        return None
    return _ts(raw, f"{p.get('symbol')}: invalidation_since — مهر کامل با منطقه زمانی لازم است")


# ── قاعده لنگر سطح ابطال — تصمیم کاربر، ۲۶ سپتامبر ۲۰۲۶ ──
# سطح ابطال دست‌کم ۱ دامنه واقعی هفتگی زیر min(قیمت فعلی، آخرین بسته هفتگی
# بسته‌شده). دلیل: سطح‌های ایستگاه دو نسبت به قیمت زنده وسط هفته‌ای صعودی
# انتخاب شدند ولی با بسته هفتگی داوری می‌شوند؛ سطح ONDO از روز اول بالای
# آخرین بسته بود. تنها منبع: radar_levels هنگام انتخاب، پایشگر و سبد هنگام
# بارگذاری.
ANCHOR_ATR = 1.0
ANCHOR_REL_TOL = 1e-9          # دقیقاً ۱ ATR پذیرفته است، حتی با خطای ممیز شناور


def invalidation_anchor(price: float, weekly_close: float) -> float:
    return min(price, weekly_close)


def anchor_ok(level: float, anchor: float, atr_w: float) -> bool:
    gap, need = anchor - level, ANCHOR_ATR * atr_w
    return gap >= need or math.isclose(gap, need, rel_tol=ANCHOR_REL_TOL)


def anchor_violations(watch: dict) -> list[str]:
    """
    قاعده لنگر روی سطح‌های watch.json، از لنگر ثبت‌شده هنگام انتخاب —
    anchor و anchor_atr_w. قیمت امروز معیار نیست: نزدیک شدن قیمت به سطح پس
    از انتخاب، نقض قاعده انتخاب نیست. لنگر غایب هم بی‌صدا نمی‌ماند.
    """
    out: list[str] = []
    for it in watch.get("positions") or []:
        sym, lvl = it.get("symbol"), it.get("invalidation")
        a, atr = it.get("anchor"), it.get("anchor_atr_w")
        if not (_num(a) and _num(atr) and atr > 0 and _num(lvl)):
            out.append(f"{sym}: لنگر سطح ثبت نشده — قاعده لنگر سنجیده نشد")
        elif not anchor_ok(lvl, a, atr):
            out.append(f"{sym}: سطح {lvl} فقط {(a - lvl) / atr:.2f} دامنه واقعی هفتگی (ATR) "
                       f"زیر لنگر {a} است؛ دست‌کم ۱ لازم است")
    return out


def judged(closed_at, since: datetime | None) -> bool:
    """
    آیا بسته هفتگی با سطحی که از since معتبر است داوری می‌شود؟ فقط اگر زمان
    بسته‌شدن اکیداً بعد از since باشد. سطحی که دقیقاً در لحظه بسته‌شدن ثبت
    شده، آن بسته را ندیده — داوری نمی‌کند. تنها منبع: پایشگر و سبد هر دو.
    """
    if since is None:
        return True
    t = closed_at if isinstance(closed_at, datetime) else _ts(closed_at, "زمان بسته هفتگی")
    return t > since


def level_mismatches(h: dict, watch: dict) -> list[str]:
    """
    سطح و مهر ابطال در holdings.json و watch.json تکرار شده‌اند. هر ناهمخوانی
    یک سطر خوانا؛ فهرست خالی یعنی یکی‌اند. پایشگر و سبد هر دو خطای بلند می‌دهند.
    """
    out: list[str] = []
    pos = {p["symbol"]: p for p in h.get("positions", []) if p.get("book") == "position"}
    seen = set()
    for it in watch.get("positions") or []:
        sym = str(it.get("symbol", "")).upper()
        seen.add(sym)
        p = pos.get(sym)
        if p is None:
            out.append(f"{sym} در watch.json هست ولی در دفتر موقعیت holdings.json نیست")
            continue
        wl, hl = it.get("invalidation"), p.get("invalidation")
        if not (_num(wl) and _num(hl) and math.isclose(wl, hl, rel_tol=1e-9)):
            out.append(f"{sym}: سطح ابطال watch.json {wl}، holdings.json {hl}")
        try:
            ws = _ts(it.get("invalidation_since"), f"{sym}: مهر watch.json")
            hs = level_since(p)
        except PositionsError as exc:
            out.append(str(exc))
            continue
        if hs is None or ws != hs:
            out.append(f"{sym}: مهر سطح watch.json {it.get('invalidation_since')}، "
                       f"holdings.json {p.get('invalidation_since')}")
    for sym, p in pos.items():
        if p.get("invalidation") is not None and sym not in seen:
            out.append(f"{sym} در holdings.json سطح ابطال دارد ولی در watch.json نیست — "
                       "پایش نمی‌شود")
    return out


def _check_shape(h) -> None:
    if not isinstance(h, dict) or h.get("version") != FORMAT_VERSION:
        raise PositionsError(
            "قالب قدیمی — مهاجرت لازم. holdings.json باید نسخه ۲ باشد: بر پایه مقدار، "
            "نه دلار، با دو دفتر و دفتر کل تغییرات")
    _ts(h.get("updated"), "میدان updated")
    fr = h.get("frozen")
    if not isinstance(fr, dict) or not isinstance(fr.get("members"), dict):
        raise PositionsError("بخش frozen با فهرست members نیست")
    for s, q in fr["members"].items():
        if not _num(q) or q < 0:
            raise PositionsError(f"مقدار منجمد {s} نامعتبر است: {q!r}")
    for c in h.get("cash") or []:
        if not isinstance(c, dict) or not _num(c.get("qty")) or c["qty"] < 0:
            raise PositionsError(f"ردیف نقد نامعتبر: {c!r}")
    if not isinstance(h.get("positions"), list) or not isinstance(h.get("ledger"), list):
        raise PositionsError("positions یا ledger فهرست نیست")
    seen = set()
    for p in h["positions"]:
        sym = p.get("symbol")
        if not isinstance(sym, str) or not sym:
            raise PositionsError(f"ردیف بی‌نماد: {p!r}")
        if p.get("book") not in BOOKS:
            raise PositionsError(f"{sym}: book باید یکی از {BOOKS} باشد")
        if p.get("status") not in ("open", "exited"):
            raise PositionsError(f"{sym}: وضعیت باید open یا exited باشد")
        for l in p.get("lots") or []:
            if not _num(l.get("qty")) or l["qty"] < 0:
                raise PositionsError(f"{sym}: مقدار لات نامعتبر {l!r}")
            if l.get("entry") is not None and (not _num(l["entry"]) or l["entry"] <= 0):
                raise PositionsError(f"{sym}: قیمت خرید لات نامعتبر {l!r}")
        if p["book"] == "position":
            if sym in seen:
                raise PositionsError(f"{sym} دو بار در دفتر موقعیت آمده است")
            seen.add(sym)
        level_since(p)
        qty = position_qty(p)
        if p["status"] == "exited" and qty > TOL:
            raise PositionsError(f"{sym}: وضعیت exited ولی مقدار {qty} دارد")
        if p["status"] == "open" and qty <= TOL:
            raise PositionsError(f"{sym}: وضعیت open ولی مقدار صفر است")


def _check_moves(h: dict, jidx: dict) -> None:
    """قاعده ضدبهانه: هیچ شناسه دفتر معامله‌ای در دفتر موقعیت ظاهر نشود."""
    for p in h["positions"]:
        did = p.get("decision_id")
        if p["book"] == "position" and did in jidx and _book_of(jidx[did]) == "trade":
            raise PositionsError(
                f"{p['symbol']}: جابه‌جایی از دفتر معامله به دفتر موقعیت ممنوع است "
                f"— شناسه {did} در دفترچه book = trade دارد")


def _check_trades(h: dict, jidx: dict) -> None:
    for p in h["positions"]:
        if p["book"] != "trade":
            continue
        sym, did = p["symbol"], p.get("decision_id")
        if not did or not p.get("setup_name"):
            raise PositionsError(f"{sym}: ردیف دفتر معامله بی‌شناسه تصمیم یا نام ستاپ")
        rec = jidx.get(did)
        if rec is None:
            raise PositionsError(f"{sym}: شناسه {did} در دفترچه نیست")
        if rec.get("setup_name") != p["setup_name"]:
            raise PositionsError(f"{sym}: نام ستاپ با دفترچه نمی‌خواند")
        if _book_of(rec) != "trade":
            raise PositionsError(f"{sym}: رکورد دفترچه {did} book = trade ندارد")
        if bool(rec.get("paper")) != bool(p.get("paper")):
            raise PositionsError(f"{sym}: پرچم فرضی با دفترچه نمی‌خواند")
        if p.get("side") not in ("long", "short") or not _num(p.get("stop")):
            raise PositionsError(f"{sym}: جهت یا حد ضرر دفتر معامله نامعتبر")
        if p["status"] == "open" and any(l.get("entry") is None for l in p["lots"]):
            raise PositionsError(f"{sym}: قیمت خرید هر لات دفتر معامله لازم است")


def _allow(reentry: dict, sym: str, level: float, qty: float) -> None:
    """
    سهمیه ورود دوباره. خروج جزئی و کامل با همان سطح جمع می‌شوند؛ سطح
    تازه سهمیه تازه می‌سازد.
    """
    st = reentry.get(sym)
    if st is not None and _close(st["level"], level):
        st["max_qty"] += qty
    else:
        reentry[sym] = {"level": level, "max_qty": qty, "used": 0.0}


def _replay(h: dict, jidx: dict, check_journal: bool = True) -> dict:
    """
    دفتر کل را به ترتیب بازپخش می‌کند و قاعده هر ردیف را می‌سنجد.
    خروجی: مقدار انتظاری هر نماد، و وضعیت سهمیه ورود دوباره.
    check_journal=False فقط برای خواندن سهمیه است، روی فایلی که پیش‌تر
    اعتبارسنجی شده — یک منطق بازپخش، نه دو.
    """
    run = {s: float(q) for s, q in h["frozen"]["members"].items()}
    reentry: dict[str, dict] = {}
    for i, r in enumerate(h["ledger"], 1):
        act, sym, d = r.get("action"), r.get("symbol"), r.get("delta")
        where = f"ردیف {i} دفتر کل ({act} {sym})"
        if act not in ACTIONS:
            raise PositionsError(f"{where}: نوع ناشناخته؛ مجاز: {ACTIONS}")
        if not isinstance(sym, str) or not _num(d):
            raise PositionsError(f"{where}: نماد یا delta نامعتبر")
        _ts(r.get("at"), f"{where}: زمان")
        cur = run.get(sym, 0.0)
        if act == "trim":
            if r.get("reason") not in TRIM_REASONS:
                raise PositionsError(f"{where}: دلیل باید یکی از {TRIM_REASONS} باشد")
            if not (d < 0 and -d <= cur + TOL) or not _num(r.get("price")):
                raise PositionsError(f"{where}: کاهش نامعتبر یا بی‌قیمت")
            if r["reason"] == "invalidation":
                if not _num(r.get("level")):
                    raise PositionsError(f"{where}: خروج جزئی با ابطال سطح لازم دارد")
                _allow(reentry, sym, float(r["level"]), -d)
        elif act == "exit":
            if not _close(-d, cur) or cur <= TOL:
                raise PositionsError(f"{where}: خروج با ابطال باید کامل باشد "
                                     f"(مقدار {cur}، delta {d})")
            if not _num(r.get("level")) or not _num(r.get("price")):
                raise PositionsError(f"{where}: سطح یا قیمت خروج نیست")
            _allow(reentry, sym, float(r["level"]), cur)
        elif act == "reenter":
            st = reentry.get(sym)
            if st is None:
                raise PositionsError(f"{where}: ورود دوباره بدون خروج با ابطال")
            if not _num(r.get("weekly_close")) or not r["weekly_close"] > st["level"]:
                raise PositionsError(f"{where}: بسته هفتگی باید بالای سطح "
                                     f"{st['level']} باشد")
            _ts(r.get("week_close_at"), f"{where}: زمان بسته هفتگی")
            if not d > 0 or st["used"] + d > st["max_qty"] + TOL:
                raise PositionsError(f"{where}: بیش از سهمیه ورود دوباره "
                                     f"({st['max_qty'] - st['used']} مانده)")
            st["used"] += d
        elif act == "add":
            did, setup = r.get("decision_id"), r.get("setup_name")
            rec = jidx.get(did)
            if not d > 0:
                raise PositionsError(f"{where}: افزایش باید مثبت باشد")
            if check_journal:
                if rec is None or not setup or rec.get("setup_name") != setup:
                    raise PositionsError(f"{where}: شناسه تصمیم و نام ستاپ باید در "
                                         f"دفترچه ثبت شده باشند")
                if _book_of(rec) == "trade":
                    raise PositionsError(f"{where}: جابه‌جایی از دفتر معامله به دفتر "
                                         f"موقعیت ممنوع است — شناسه {did} در دفترچه "
                                         f"book = trade دارد")
        elif act == "adjust":
            if not r.get("reason"):
                raise PositionsError(f"{where}: دلیل لازم است")
            if cur <= TOL or abs(d) > ADJUST_MAX * cur + TOL:
                raise PositionsError(f"{where}: بیش از ۱٪ مقدار نماد ({cur})")
        elif act == "withdraw":
            if not r.get("reason") or not r.get("account"):
                raise PositionsError(f"{where}: دلیل و حساب لازم است")
            if sym in STABLE_ASSETS:
                # برداشت فقط نقد — ۳ اکتبر ۲۰۲۶. نقد در ناوردا نیست؛ پس اینجا فقط
                # هم‌خوانی ردیف با خودش، و مقدار نماد کوینی عوض نمی‌شود
                c = r.get("cash") or {}
                if not (d < 0 and c.get("asset") == sym and c.get("account") == r["account"]
                        and _num(c.get("qty")) and _close(c["qty"], -d)):
                    raise PositionsError(f"{where}: برداشت نقد باید کاهش باشد، با cash همان "
                                         "دارایی و حساب و به اندازه delta")
                continue
            if not (d < 0 and -d <= cur + TOL):
                raise PositionsError(f"{where}: برداشت فقط کاهش است و بیش از مقدار نماد "
                                     f"({cur}) نه")
        run[sym] = cur + d
    return {"expected": run, "reentry": reentry}


def validate(h: dict, journal: dict) -> dict:
    """
    قالب، قاعده ضدبهانه و ناوردای دفتر کل. هر نقض خطای صریح.
    خروجی: نتیجه بازپخش، برای کسی که سهمیه ورود دوباره را می‌خواهد.
    """
    _check_shape(h)
    jidx = _journal_index(journal)
    _check_moves(h, jidx)
    _check_trades(h, jidx)
    rp = _replay(h, jidx)
    actual = {p["symbol"]: position_qty(p) for p in h["positions"]
              if p["book"] == "position"}
    for sym in sorted(set(actual) | set(rp["expected"])):
        want, got = rp["expected"].get(sym, 0.0), actual.get(sym, 0.0)
        if not _close(want, got):
            raise PositionsError(
                f"{sym}: اختلاف ثبت‌نشده — منجمد به‌علاوه دفتر کل {want}، ولی فعلی {got}. "
                "هر تغییر مقدار فقط با فرمان و یک ردیف دفتر کل")
    return rp


def reentry_state(h: dict, symbol: str) -> dict | None:
    """سهمیه ورود دوباره نماد، از بازپخش دفتر کل — نه از میدان ذخیره‌شده."""
    return _replay(h, {}, check_journal=False)["reentry"].get(symbol)


def load(path: str, journal_path: str | None = None) -> tuple[dict, dict]:
    """holdings.json و دفترچه را می‌خواند و اعتبارسنجی می‌کند؛ خطا صریح است."""
    if not os.path.exists(path):
        raise PositionsError(f"فایل {path} نیست")
    try:
        with open(path, encoding="utf-8") as f:
            h = json.load(f)
    except (OSError, ValueError) as exc:
        raise PositionsError(f"{path} خوانا نیست: {type(exc).__name__}") from exc
    journal = RJ.load(journal_path)
    validate(h, journal)
    return h, journal


def save(path: str, h: dict) -> None:
    """نوشتن اتمی: فایل موقت در همان پوشه، سپس جایگزینی."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ═══════════════════════ ارزش‌گذاری و حرارت ═══════════════════════

def value(h: dict, prices: dict) -> dict:
    """
    ارزش هر ردیف از قیمت زنده. قیمت غایب یعنی ارزش غایب و «ناقص» — نه صفر.
    معامله فرضی در سرمایه نیست. استیبل با قیمت ثابت ۱ دلار.
    """
    rows, missing, total = [], [], 0.0
    for p in h["positions"]:
        if p["status"] != "open":
            continue
        qty, px = position_qty(p), prices.get(p["symbol"])
        val = qty * px if _num(px) else None
        known = [l for l in p["lots"] if l.get("entry") is not None]
        kq = sum(l["qty"] for l in known)
        avg = (sum(l["qty"] * l["entry"] for l in known) / kq
               if known and len(known) == len(p["lots"]) and kq > 0 else None)
        paper = bool(p.get("paper"))
        rows.append({"symbol": p["symbol"], "book": p["book"], "qty": qty,
                     "price": px if _num(px) else None, "value": val, "paper": paper,
                     "dust": val is not None and val < DUST_USD,
                     "avg_entry": avg, "known_entry_qty": kq})
        if paper:
            continue
        if val is None:
            missing.append(p["symbol"])
        else:
            total += val
    stable = sum(float(c["qty"]) * STABLE_PRICE for c in h.get("cash") or []
                 if str(c.get("asset", "")).upper() in STABLE_ASSETS)
    other_cash = [c["asset"] for c in h.get("cash") or []
                  if str(c.get("asset", "")).upper() not in STABLE_ASSETS]
    return {"rows": rows, "stable_usd": stable, "total": total + stable,
            "missing": missing, "incomplete": bool(missing),
            "unpriced_cash": other_cash}


def _trade_risk(p: dict) -> float:
    s = 1 if p.get("side", "long") == "long" else -1
    return sum(l["qty"] * s * (l["entry"] - p["stop"]) for l in p["lots"])


def trade_heat(h: dict, band: dict, total: float) -> dict:
    """
    حرارت دفتر معامله. سقف = درصد سقف باند × کل سرمایه. حداکثر پوزیشن
    هم‌جهت از باند، و از سه لانگ آلت هم‌زمان به بالا ضریب همبستگی 1.5
    (بند ۸.۳ اسکیل). معامله فرضی جدا شمرده می‌شود.
    """
    real = [p for p in h["positions"] if p["book"] == "trade"
            and p["status"] == "open" and not p.get("paper")]
    paper = [p for p in h["positions"] if p["book"] == "trade"
             and p["status"] == "open" and p.get("paper")]
    risk_real = sum(_trade_risk(p) for p in real)
    longs = [p for p in real if p.get("side", "long") == "long"]
    shorts = [p for p in real if p.get("side") == "short"]
    alt_longs = [p for p in longs if p["symbol"].upper() not in NON_ALT]
    corr = CORR_FACTOR if len(alt_longs) >= CORR_ALT_LONGS else 1.0
    cap_usd = band["cap"] / 100 * total
    eff = risk_real * corr
    return {"risk_real": risk_real, "risk_paper": sum(_trade_risk(p) for p in paper),
            "corr": corr, "effective": eff, "cap_usd": cap_usd,
            "over_cap": eff > cap_usd + TOL,
            "long_count": len(longs), "short_count": len(shorts),
            "maxpos": band["maxpos"],
            "over_maxpos": len(longs) > band["maxpos"] or len(shorts) > band["maxpos"]}


# ═══════════════════════ بسته هفتگی — لنگر وقت جهانی ═══════════════════════

def _is_monday_utc(t: datetime) -> bool:
    # نگهبان مشترک همه مسیرهای کندل — نشست ۳ب
    return A.anchor_ok(t, "1W")


def _okx_week(symbol: str, get, limit: int = 5) -> tuple[list, str]:
    r = get(OKX, params={"instId": f"{symbol.upper()}-USDT", "bar": OKX_WEEK_BAR,
                         "limit": str(limit)}, timeout=20)
    js = r.json()
    if r.status_code != 200 or str(js.get("code")) != "0" or not js.get("data"):
        return [], f"اوکی‌اکس {OKX_WEEK_BAR}: پاسخ نداد (کد {js.get('code')})"
    rows = [(datetime.fromtimestamp(int(x[0]) / 1000, UTC), float(x[4]),
             x[8] == "1" if len(x) > 8 else None) for x in js["data"]]
    return rows, ""


def _gate_week(symbol: str, get, limit: int = 5) -> tuple[list, str]:
    r = get(GATE, params={"currency_pair": f"{symbol.upper()}_USDT",
                          "interval": GATE_WEEK_INTERVAL, "limit": limit}, timeout=20)
    js = r.json()
    if r.status_code != 200 or not isinstance(js, list) or not js:
        return [], f"گیت {GATE_WEEK_INTERVAL}: پاسخ نداد"
    return [(datetime.fromtimestamp(int(float(x[0])), UTC), float(x[2]), None)
            for x in js], ""


def weekly_close(symbol: str, get=None, now: datetime | None = None
                 ) -> tuple[dict | None, list[str]]:
    """
    آخرین بسته هفتگی **بسته‌شده** به لنگر وقت جهانی: هفته دوشنبه تا یکشنبه،
    بسته در دوشنبه ۰۰:۰۰ UTC. اول اوکی‌اکس 1Wutc، بعد گیت 7d.

    کندلی که زمان باز شدنش دوشنبه ۰۰:۰۰ UTC نیست رد می‌شود — لنگر هنگ‌کنگ
    هرگز جانشین نمی‌شود. هیچ‌کدام نبود یعنی None: «داده ندارم»، با دلیل.
    """
    now = now or datetime.now(UTC)
    if get is None:
        if requests is None:
            return None, ["requests نصب نیست"]
        get = requests.get
    why: list[str] = []
    for venue, fetch in (("okx", _okx_week), ("gate", _gate_week)):
        try:
            rows, err = fetch(symbol, get)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            why.append(f"{venue}: پاسخ نامعتبر ({type(exc).__name__})")
            continue
        except NET_ERRORS as exc:         # ثبت می‌شود و به صرافی بعد می‌رود — بلعیده نه
            why.append(f"{venue}: خطای شبکه ({type(exc).__name__})")
            continue
        if err:
            why.append(err)
            continue
        closed = [r for r in rows if (r[2] is True) or (r[2] is None and r[0] + WEEK <= now)]
        if not closed:
            why.append(f"{venue}: هفته بسته‌شده‌ای نیست")
            continue
        op, close, _ = max(closed, key=lambda r: r[0])
        if not _is_monday_utc(op):
            why.append(f"{venue}: لنگر نادرست — باز شدن {op.isoformat()} دوشنبه ۰۰:۰۰ UTC نیست")
            continue
        return {"close": close, "week_open": op.isoformat(),
                "closed_at": (op + WEEK).isoformat(), "venue": venue}, why
    return None, why


def weekly_closes(symbol: str, n: int, get=None, now: datetime | None = None
                  ) -> tuple[list[dict] | None, list[str]]:
    """
    آخرین n بسته هفتگی بسته‌شده به لنگر وقت جهانی، به ترتیب زمان. همان
    واکشی weekly_close؛ اینجا لنگر **همه** ردیف‌ها سنجیده می‌شود، نه فقط آخری.
    کمتر از n هفته بسته یعنی «نابالغ» — هیچ‌وقت میانگین با پنجره کوتاه‌تر.
    """
    now = now or datetime.now(UTC)
    if get is None:
        if requests is None:
            return None, ["requests نصب نیست"]
        get = requests.get
    why: list[str] = []
    for venue, fetch in (("okx", _okx_week), ("gate", _gate_week)):
        try:
            rows, err = fetch(symbol, get, limit=n + 2)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            why.append(f"{venue}: پاسخ نامعتبر ({type(exc).__name__})")
            continue
        except NET_ERRORS as exc:
            why.append(f"{venue}: خطای شبکه ({type(exc).__name__})")
            continue
        if err:
            why.append(err)
            continue
        closed = sorted((r for r in rows
                         if (r[2] is True) or (r[2] is None and r[0] + WEEK <= now)),
                        key=lambda r: r[0])
        bad = [r[0] for r in closed if not _is_monday_utc(r[0])]
        if bad:
            why.append(f"{venue}: لنگر نادرست — باز شدن {bad[0].isoformat()} دوشنبه ۰۰:۰۰ UTC نیست")
            continue
        if len(closed) < n:
            why.append(f"{venue}: نابالغ — {len(closed)} هفته بسته، {n} لازم")
            continue
        return [{"week_open": op.isoformat(), "closed_at": (op + WEEK).isoformat(),
                 "close": c, "venue": venue} for op, c, _ in closed[-n:]], why
    return None, why


def sma_weekly(symbol: str, n: int = 50, get=None, now: datetime | None = None
               ) -> tuple[dict | None, list[str]]:
    """
    میانگین ساده بسته n هفته بسته‌شده، وقت جهانی — با بسته و زمان همان هفته،
    تا پایشگر فقط بسته همان هفته را با آن بسنجد.
    """
    rows, why = weekly_closes(symbol, n, get, now)
    if rows is None:
        return None, why
    last = rows[-1]
    return {"value": sum(r["close"] for r in rows) / n, "weeks": n, "close": last["close"],
            "week_open": last["week_open"], "week_closed_at": last["closed_at"],
            "venue": last["venue"]}, why


# ═══════════════════════ فرمان‌ها ═══════════════════════

def _now() -> str:
    return datetime.now(UTC).isoformat()


def _find(h: dict, sym: str, book: str = "position") -> dict | None:
    return next((p for p in h["positions"]
                 if p["symbol"] == sym and p["book"] == book), None)


def _receipt_at(raw: str, h: dict) -> str:
    """
    زمان رسید صرافی: مهر کامل با منطقه زمانی، نه در آینده، نه پیش از تاریخ
    منجمد — فروش پیش از آن در مقدار منجمد نشسته است.
    """
    t = _ts(raw, "--at — مهر کامل با منطقه زمانی لازم است")
    if t > datetime.now(UTC) + timedelta(minutes=10):
        raise PositionsError(f"--at در آینده است: {raw}")
    day = datetime.strptime(h["frozen"]["date"], "%Y-%m-%d").replace(tzinfo=UTC)
    if t < day:
        raise PositionsError(f"--at پیش از تاریخ منجمد {h['frozen']['date']} است — آن فروش "
                             "در مقدار منجمد نشسته")
    return t.astimezone(UTC).isoformat()


def _receipt(h: dict, a, row: dict, qty: float, account: str) -> None:
    """
    رسید فروش: مجموع باید با مقدار × قیمت بخواند؛ خالص پس از کارمزد به تتر همان
    حساب اضافه می‌شود. بدون --gross و --fee نقد دست نمی‌خورد — رفتار پیشین.
    """
    if a.gross is None and a.fee is None:
        return
    expect = qty * a.price
    gross = expect if a.gross is None else a.gross
    if not math.isclose(gross, expect, rel_tol=1e-6):
        raise PositionsError(f"مجموع رسید {gross} با مقدار × قیمت {expect} نمی‌خواند")
    fee = a.fee or 0.0
    if not (_num(fee) and 0 <= fee < gross):
        raise PositionsError(f"کارمزد نامعتبر: {fee}")
    net = round(gross - fee, 10)
    row.update(gross=gross, fee=fee, net=net)
    c = next((c for c in h["cash"] if c.get("asset") == "USDT" and c.get("account") == account),
             None)
    if c is None:
        c = {"asset": "USDT", "qty": 0.0, "account": account}
        h["cash"].append(c)
    c["qty"] = round(c["qty"] + net, 10)


def _take(p: dict, qty: float, account: str | None) -> str:
    """کاهش از لات‌های یک حساب، قدیمی‌ترین اول. چند حساب یعنی --account اجباری."""
    accts = {l["account"] for l in p["lots"]}
    if account is None:
        if len(accts) > 1:
            raise PositionsError(f"{p['symbol']} در چند حساب است ({sorted(accts)}) — "
                                 "--account لازم است")
        account = next(iter(accts))
    pool = [l for l in p["lots"] if l["account"] == account]
    if sum(l["qty"] for l in pool) + TOL < qty:
        raise PositionsError(f"{p['symbol']}: حساب {account} این مقدار را ندارد")
    left = qty
    for l in pool:
        cut = min(l["qty"], left)
        l["qty"] -= cut
        left -= cut
        if left <= TOL:
            break
    p["lots"] = [l for l in p["lots"] if l["qty"] > TOL]
    return account


def _apply(h: dict, a, journal: dict) -> dict:
    sym = a.symbol.upper()
    row = {"at": _now(), "action": a.cmd, "symbol": sym}
    if a.cmd in ("trim", "exit", "withdraw") and a.at is not None:
        row["at"] = _receipt_at(a.at, h)
    if a.cmd in ("trim", "exit") and a.order_id:
        row["order_id"] = a.order_id
    p = _find(h, sym)
    if a.cmd == "trim":
        if p is None or p["status"] != "open":
            raise PositionsError(f"{sym} در دفتر موقعیت باز نیست")
        if a.reason == "invalidation" and a.level is None:
            raise PositionsError("خروج جزئی با ابطال: --level لازم است — سطحی که بسته "
                                 "هفتگی زیرش بسته شد")
        acct = _take(p, a.qty, a.account)
        row.update(delta=-a.qty, price=a.price, reason=a.reason, account=acct)
        if a.reason == "invalidation":
            row["level"] = a.level
        _receipt(h, a, row, a.qty, acct)
    elif a.cmd == "exit":
        if p is None or p["status"] != "open":
            raise PositionsError(f"{sym} در دفتر موقعیت باز نیست")
        q = position_qty(p)
        accts = sorted({l["account"] for l in p["lots"]})
        if (a.gross is not None or a.fee is not None) and len(accts) != 1:
            raise PositionsError(f"{sym} در چند حساب است ({accts}) — رسید هر حساب جداست؛ "
                                 "با trim جدا ثبت کن")
        p["lots"], p["status"] = [], "exited"
        row.update(delta=-q, price=a.price, level=a.level, reason="invalidation")
        if len(accts) == 1:
            row["account"] = accts[0]
            _receipt(h, a, row, q, accts[0])
    elif a.cmd == "reenter":
        if p is None:
            raise PositionsError(f"{sym} در دفتر موقعیت نیست")
        st = _replay(h, _journal_index(journal))["reentry"].get(sym)
        if st is None:
            raise PositionsError(f"{sym}: خروج با ابطالی ثبت نشده — ورود دوباره ممکن نیست")
        w, why = weekly_close(sym)
        if w is None:
            raise PositionsError(f"{sym}: داده ندارم — بسته هفتگی به لنگر وقت جهانی "
                                 f"در دسترس نیست ({'؛ '.join(why)})")
        if not w["close"] > st["level"]:
            raise PositionsError(f"{sym}: بسته هفتگی {w['close']} بالای سطح "
                                 f"{st['level']} نیست — ورود دوباره مجاز نیست")
        p["lots"].append({"qty": a.qty, "account": a.account, "entry": a.price})
        p["status"] = "open"
        row.update(delta=a.qty, price=a.price, weekly_close=w["close"],
                   week_close_at=w["closed_at"], venue=w["venue"])
    elif a.cmd == "add":
        if p is None:
            p = {"symbol": sym, "book": "position", "status": "open", "lots": [],
                 "invalidation": None}
            h["positions"].append(p)
        p["lots"].append({"qty": a.qty, "account": a.account, "entry": a.price})
        p["status"] = "open"
        row.update(delta=a.qty, price=a.price, decision_id=a.decision_id,
                   setup_name=a.setup_name)
    elif a.cmd == "adjust":
        if p is None or p["status"] != "open":
            raise PositionsError(f"{sym} در دفتر موقعیت باز نیست")
        if a.qty >= 0:
            accts = {l["account"] for l in p["lots"]}
            acct = a.account or (next(iter(accts)) if len(accts) == 1 else None)
            if acct is None:
                raise PositionsError(f"{sym} در چند حساب است — --account لازم است")
            lot = next((l for l in p["lots"] if l["account"] == acct), None)
            if lot is None:
                raise PositionsError(f"{sym}: حساب {acct} لات ندارد")
            lot["qty"] += a.qty
        else:
            _take(p, -a.qty, a.account)
        row.update(delta=a.qty, reason=a.reason)
    elif a.cmd == "withdraw" and sym in STABLE_ASSETS:
        # برداشت فقط نقد — تصمیم کاربر، ۳ اکتبر ۲۰۲۶؛ مقدار با --qty
        if a.cash is not None:
            raise PositionsError("برداشت نقد: مقدار با --qty است؛ --cash تکراری است")
        c = next((c for c in h["cash"]
                  if c.get("asset") == sym and c.get("account") == a.account), None)
        if c is None or a.qty > c["qty"] + TOL:
            raise PositionsError(f"نقد {sym} حساب {a.account} این مقدار را ندارد: {a.qty}")
        c["qty"] = round(c["qty"] - a.qty, 10)
        if c["qty"] <= TOL:
            h["cash"].remove(c)
        row.update(delta=-a.qty, reason=a.reason, account=a.account,
                   cash={"asset": sym, "qty": a.qty, "account": a.account})
    elif a.cmd == "withdraw":
        if p is None or p["status"] != "open":
            raise PositionsError(f"{sym} در دفتر موقعیت باز نیست")
        acct = _take(p, a.qty, a.account)
        row.update(delta=-a.qty, reason=a.reason, account=acct)
        if a.cash is not None:
            c = next((c for c in h["cash"]
                      if c.get("asset") == "USDT" and c.get("account") == acct), None)
            if c is None or not (_num(a.cash) and 0 < a.cash <= c["qty"] + TOL):
                raise PositionsError(f"نقد تتر حساب {acct} این مقدار را ندارد: {a.cash}")
            c["qty"] = round(c["qty"] - a.cash, 10)
            if c["qty"] <= TOL:
                h["cash"].remove(c)             # حساب خالی از فهرست نقد هم می‌رود
            row["cash"] = {"asset": "USDT", "qty": a.cash, "account": acct}
        if position_qty(p) <= TOL:
            p["status"] = "exited"              # بی‌سهمیه ورود دوباره — ابطال نبود
    h["ledger"].append(row)
    h["updated"] = _now()
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="دو دفتر و دفتر کل تغییرات — رادار ۷")
    ap.add_argument("--holdings", default=HOLDINGS_FILE)
    ap.add_argument("--journal", default=None, help="پیش‌فرض radar_journal.json")
    ap.add_argument("--optcost", default=None, help="پیش‌فرض radar_optcost.json")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("validate", help="اعتبارسنجی بدون تغییر")
    sp.add_parser("symbols", help="نمادهای پوزیشن باز هر دو دفتر، جدا با کاما")
    for name in ("trim", "exit", "reenter", "add", "adjust", "withdraw"):
        p = sp.add_parser(name)
        p.add_argument("--symbol", required=True)
        p.add_argument("--account", default=None, required=name == "withdraw")
        if name != "exit":
            p.add_argument("--qty", type=float, required=True)
        if name not in ("adjust", "withdraw"):
            p.add_argument("--price", type=float, required=True)
        if name in ("trim", "exit", "withdraw"):
            # رسید صرافی — نشست ۳: زمان فروش، نه زمان ثبت؛ برداشت هم از ۳ اکتبر
            p.add_argument("--at", default=None,
                           help="زمان رسید یا برداشت، مهر کامل با منطقه زمانی؛ پیش‌فرض اکنون")
        if name in ("trim", "exit"):
            # نقد خالص به تتر همان حساب
            p.add_argument("--gross", type=float, default=None,
                           help="مجموع رسید به تتر؛ باید با مقدار × قیمت بخواند")
            p.add_argument("--fee", type=float, default=None, help="کارمزد به تتر")
            p.add_argument("--order-id", dest="order_id", default=None)
        if name == "trim":
            p.add_argument("--reason", choices=TRIM_REASONS, required=True)
            p.add_argument("--level", type=float, default=None,
                           help="فقط با --reason invalidation: سطح ابطال نقض‌شده")
        if name == "exit":
            p.add_argument("--level", type=float, required=True,
                           help="سطح ابطال ساختاری که با بسته هفتگی نقض شد")
        if name == "add":
            p.add_argument("--decision-id", dest="decision_id", required=True)
            p.add_argument("--setup-name", dest="setup_name", required=True)
        if name == "adjust":
            p.add_argument("--reason", required=True)
        if name == "withdraw":
            p.add_argument("--reason", required=True)
            p.add_argument("--cash", type=float, default=None,
                           help="تتر همان حساب که با همین ردیف از رادار برداشته می‌شود")
    a = ap.parse_args(argv)

    try:
        h, journal = load(a.holdings, a.journal)
        if a.cmd == "validate":
            print(f"✅ {a.holdings} معتبر است — ناوردای دفتر کل برقرار")
            return 0
        if a.cmd == "symbols":
            syms = [p["symbol"] for p in h["positions"] if p["status"] == "open"]
            print(",".join(dict.fromkeys(syms)))
            return 0
        if a.cmd in ("trim", "reenter", "add", "withdraw") and a.qty <= 0:
            raise PositionsError("مقدار باید مثبت باشد")
        if a.cmd in ("reenter", "add") and not a.account:
            raise PositionsError("--account برای افزایش لازم است")
        h2 = json.loads(json.dumps(h))
        row = _apply(h2, a, journal)
        validate(h2, journal)          # هیچ تغییری بی‌آنکه ناوردا برقرار بماند
    except PositionsError as exc:
        print(f"⛔ {exc}", file=sys.stderr)
        return 2
    save(a.holdings, h2)
    print(f"✅ ثبت شد: {row['action']} {row['symbol']} delta {row['delta']}")
    # هر خروج با ابطال و هر کاهش در دفتر هزینه فرصت، با پیگیری ۱۴ و ۳۰ روزه
    if a.cmd in ("trim", "exit"):
        try:
            d = RO.load(a.optcost)
            rec = RO.add_exit(d, symbol=row["symbol"], action=a.cmd, qty=-row["delta"],
                              price=row["price"], reason=row["reason"],
                              level=row.get("level"), at=row["at"],
                              order_id=row.get("order_id"))
            RO.save(d, a.optcost)
        except (OSError, ValueError) as exc:
            print(f"⛔ ردیف دفتر کل ثبت شد، ولی دفتر هزینه فرصت نه ({type(exc).__name__}: "
                  f"{exc}). دستی ثبت کن تا پیگیری ۱۴ و ۳۰ روزه از دست نرود.",
                  file=sys.stderr)
            return 3
        print(f"   دفتر هزینه فرصت: رکورد خروج {rec['id']} — پیگیری ۱۴ و ۳۰ روزه")
    return 0


if __name__ == "__main__":
    sys.exit(main())
