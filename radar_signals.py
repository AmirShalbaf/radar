#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_signals.py — هشدارهای تازه پایشگر، متن ۳۸
==================================================

دو هشدار تازه در مسیر نبض — تصمیم کاربر ۳ و ۴ نوامبر ۲۰۲۶، ک۱۲۹. هر دو فقط اطلاع‌اند و
هیچ حکم خرید یا فروشی نمی‌سازند. کلید هر پیام فقط پس از رسید موفق — make همان Msg پایشگر.

۱. اهرم داغ — 🟠
   فاندینگ و بهره باز بالا می‌روند ولی قیمت درجاست: پول اهرمی تازه وارد شده و قیمت را
   جلو نبرده — بازار برای تخلیه پرفشار است. شرط، هر سه با هم:
       فاندینگ ۸ ساعته ≥ +۰.۰۳٪ — همان مرز «فاندینگ داغ» درس funding_hot — یا ≤ −۰.۰۱٪
       بهره باز ۲۴ ساعت، به واحد کوین، دست‌کم +۱۰٪
       |تغییر قیمت ۲۴ ساعت| حداکثر ۲٪ — از شمع بسته ساعتی
   فاندینگ از snapshot.json همین نبض؛ بهره باز فقط وقتی فاندینگ داغ است واکشی می‌شود —
   درخواست کم. آستانه‌ها فرضیه آزمون‌نشده‌اند — ک۱۳۰.

۲. نتیجه رویداد — 🔵
   نیم ساعت پس از رویداد کلان با اهمیت بالا: عدد واقعی در برابر انتظار — اگر در تقویم
   دستی ثبت شده — واکنش ۳۰ دقیقه بیت‌کوین از دو شمع بسته ۱۵ دقیقه‌ای، و درس از واکنش ۲۴
   ساعته رویدادهای همنوع پیشین در events_ledger.json. رکورد واکنش در watch_state.json.

فقط کتابخانه استاندارد، requests و radar_history — دیر، فقط در مسیر نبض.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import radar_alert as AL
import radar_positions as P
from radar_anchor import TEHRAN
# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
OKX = "https://www.okx.com"

LEV_FUND_LONG = 0.03          # فاندینگ ۸ ساعته، درصد — همان مرز درس funding_hot
LEV_FUND_SHORT = -0.01        # فاندینگ منفی: شورت‌ها می‌پردازند
LEV_OI_MIN_PCT = 10.0         # بهره باز ۲۴ ساعت، واحد کوین
LEV_FLAT_PCT = 2.0            # بیشینه |تغییر قیمت ۲۴ ساعت|
SNAP_MAX_AGE_H = 5.0          # همان سقف عمر snapshot.json — radar_snapshot.STALE_HOURS
RUBIK_PAUSE = 0.45            # سقف نرخ آمار اوکی‌اکس — همان radar_pump

RESULT_AFTER = timedelta(minutes=30)
RESULT_MAX_AGE = timedelta(hours=12)       # دیرتر از این، پیام صبح جای نتیجه را گرفته
RESULT_NO_DATA_AFTER = timedelta(hours=3)  # پس از این، بی واکنش هم فرستاده می‌شود
NO_NEW_AFTER = timedelta(hours=1)          # پایان پنجره رویداد بی تقویم دستی — radar_calendar


def _n(x: float) -> str:
    """عدد بازار در پیام: رقم لاتین — همان radar_watch._n."""
    return f"{x:.10g}"


def _th(t: datetime) -> str:
    return f"{t.astimezone(TEHRAN):%Y-%m-%d %H:%M} تهران"


def _ts(raw) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace(" UTC", "+00:00"))
    except (TypeError, ValueError):
        try:
            t = datetime.strptime(str(raw)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    return t if t.tzinfo else None


class _Keyed(AL.Alert):
    """جانشین Msg پایشگر برای استفاده بیرون از آن — کلید با commit."""

    def __new__(cls, text, what, sets, pops=(), **alert):
        a = super().__new__(cls, text, **alert)
        a.what, a.sets, a.pops = what, dict(sets), tuple(pops)
        return a

    def commit(self, state: dict) -> None:
        state.update(self.sets)


# ═══════════════════════ ۱ — اهرم داغ ═══════════════════════

def okx_oi_points(sym: str, get=None) -> tuple[list | None, str | None]:
    """بهره باز ساعتی قرارداد دائمی اوکی‌اکس — [(ms، کوین)] صعودی. خطا: None با دلیل."""
    try:
        import requests
        get = get or requests.get
        r = get(f"{OKX}/api/v5/rubik/stat/contracts/open-interest-history",
                params={"instId": f"{sym.upper()}-USDT-SWAP", "period": "1H", "limit": "30"},
                timeout=15)
        js = r.json()
        if js.get("code") != "0":
            return None, f"کد {js.get('code')} {js.get('msg') or ''}".strip()
        pts = sorted((int(x[0]), float(x[2])) for x in js.get("data") or [] if len(x) > 2)
        return pts, None
    except Exception as exc:                  # شبکه و پاسخ نامعتبر — صریح در گزارش پایش
        return None, f"{type(exc).__name__}: {str(exc)[:120]}"


def oi_change_24h(points: list) -> tuple[float | None, str | None]:
    """تغییر ۲۴ ساعته بهره باز از تازه‌ترین نقطه تا نقطه دقیقاً ۲۴ ساعت پیش از آن."""
    if not points:
        return None, "نقطه‌ای نیست"
    by = dict(points)
    t1, b = points[-1]
    a = by.get(t1 - 24 * 3_600_000)
    if not a or a <= 0:
        return None, "نقطه ۲۴ ساعت پیش نیست"
    return 100.0 * (b / a - 1.0), None


def price_change_24h(rows: list) -> tuple[float | None, float | None, float | None]:
    """تغییر قیمت ۲۴ ساعت از شمع بسته ساعتی، و کف و سقف همان ۲۴ ساعت."""
    if not rows:
        return None, None, None
    last = rows[-1]
    base = next((r for r in rows if r["open"] == last["open"] - timedelta(hours=24)), None)
    if base is None or base["close"] <= 0:
        return None, None, None
    win = [r for r in rows if r["open"] > base["open"]]
    return (100.0 * (last["close"] / base["close"] - 1.0),
            min(r["low"] for r in win), max(r["high"] for r in win))


def heat_side(fund: float | None) -> str | None:
    if fund is None:
        return None
    if fund >= LEV_FUND_LONG - 1e-12:
        return "long"
    if fund <= LEV_FUND_SHORT + 1e-12:
        return "short"
    return None


def _snapshot_fresh(snap: dict | None, now: datetime) -> str | None:
    if not isinstance(snap, dict):
        return "snapshot.json نیست یا خوانا نیست"
    gen = _ts(snap.get("generated_utc"))
    if gen is None:
        return "snapshot.json مهر زمان ندارد"
    age = (now - gen).total_seconds() / 3600
    if age > SNAP_MAX_AGE_H:
        return f"snapshot.json کهنه است — {age:.1f} ساعت"
    return None


def leverage_heat(symbols: list[str], state: dict, now: datetime, make=None, hourly=None,
                  snapshot: dict | None = None, oi=None, h: dict | None = None,
                  pause: float = RUBIK_PAUSE) -> list:
    """
    هشدار اهرم داغ برای هر نماد، حداکثر یک بار در روز وقت جهانی. state دست نمی‌خورد —
    کلید با commit پس از رسید. hourly(نماد) همان شمع ساعتی هشدار تکان؛ oi(نماد) نقطه‌های
    بهره باز. موقعیت ناچیز — زیر DUST_USD — جز BTC و ETH هشدار نمی‌گیرد.
    """
    make = make or _Keyed
    oi = oi or okx_oi_points
    why = _snapshot_fresh(snapshot, now)
    if why:
        print(f"  اهرم داغ: {why} — سنجیده نشد")
        return []
    rows_by = snapshot.get("symbols") or {}
    held = {p["symbol"].upper(): P.position_qty(p) for p in (h or {}).get("positions", [])
            if p.get("book") == "position" and p.get("status") == "open"}
    day = now.astimezone(UTC).strftime("%Y-%m-%d")
    out, fetched = [], 0
    for sym in symbols:
        sym = sym.upper()
        key = f"lev_heat_{sym}_{day}"
        if state.get(key):
            continue
        row = rows_by.get(sym) or {}
        fund = row.get("funding_8h_pct")
        fund = float(fund) if isinstance(fund, (int, float)) and not isinstance(fund, bool) else None
        px = row.get("price")
        if sym not in ("BTC", "ETH") and isinstance(px, (int, float)) and \
                held.get(sym, 0.0) * px < P.DUST_USD:
            continue
        side = heat_side(fund)
        if side is None:
            continue                            # فاندینگ عادی: بی واکشی
        try:
            rows, rwhy = hourly(sym) if hourly else (None, ["شمع ساعتی نیست"])
        except Exception as exc:                 # داده ندارم، نه افتادن پایشگر — مثل هشدار تکان
            rows, rwhy = None, [f"{type(exc).__name__}: {str(exc)[:120]}"]
        chg, lo, hi = price_change_24h(rows or [])
        if chg is None:
            print(f"  اهرم داغ {sym}: تغییر ۲۴ ساعت قیمت سنجیده نشد — {'؛ '.join(rwhy or []) or 'شمع ۲۴ ساعت پیش نیست'}")
            continue
        if abs(chg) > LEV_FLAT_PCT + 1e-9:
            continue
        if fetched and pause:
            time.sleep(pause)
        fetched += 1
        pts, owhy = oi(sym)
        oi24, why2 = oi_change_24h(pts or [])
        if oi24 is None:
            print(f"  اهرم داغ {sym}: بهره باز سنجیده نشد — {owhy or why2}")
            continue
        if oi24 < LEV_OI_MIN_PCT - 1e-9:
            continue
        crowd = "لانگ‌ها" if side == "long" else "شورت‌ها"
        title = f"اهرم داغ {sym} — {crowd} انباشته، قیمت درجا"
        do = (f"نمودار {sym} را ببین؛ خرید اهرمی تازه نه. موقعیت اسپات را برای این هشدار نفروش"
              if side == "long" else
              f"نمودار {sym} را ببین؛ شورت تازه نه — خطر جهش رو به بالا")
        why = (f"بهره باز ۲۴ ساعت {oi24:+.1f}٪، فاندینگ {fund:+.4f}٪ در ۸ ساعت، قیمت ۲۴ ساعت "
               f"{chg:+.1f}٪ — {crowd} تازه بی پیشرفت قیمت")
        nxt = (f"اگر بسته ساعتی زیر کف ۲۴ ساعت {_n(lo)} رفت، تخلیه {crowd} محتمل‌تر است؛ اگر با حجم "
               f"از سقف {_n(hi)} گذشت، فشار رفع می‌شود. فرضیه آزمون‌نشده — ک۱۳۰"
               if side == "long" else
               f"اگر بسته ساعتی بالای سقف ۲۴ ساعت {_n(hi)} رفت، تخلیه {crowd} محتمل‌تر است؛ اگر "
               f"زیر کف {_n(lo)} بسته شد، فشار رفع می‌شود. فرضیه آزمون‌نشده — ک۱۳۰")
        text = "🔥 " + AL.plain_of("orange", title, do, why, nxt)
        rec = {"side": side, "oi24_pct": round(oi24, 2), "funding_8h_pct": fund,
               "chg24_pct": round(chg, 2), "at": now.astimezone(UTC).isoformat(timespec="seconds")}
        out.append(make(text, f"اهرم داغ {sym}", {key: rec}, level="orange", title=title,
                        do=do, why=why, nxt=nxt, symbol=sym))
    return out


# ═══════════════════════ ۲ — نتیجه رویداد ═══════════════════════

def macro_events(cal: dict | None, ledger: dict | None) -> list[dict]:
    """
    رویدادهای کلان با اهمیت بالا: تقویم دستی ساعت‌دار، سپس دفتر خودکار بی آزادسازی؛
    هم‌دقیقه یکی — دستی مقدم، نوعش از دفتر.
    """
    import radar_calendar as RC
    out, seen = [], {}
    led = [e for e in (ledger or {}).get("events") or []
           if e.get("importance") == "high" and e.get("kind") != "unlock" and _ts(e.get("at"))]
    led_by = {_ts(e["at"]).replace(second=0, microsecond=0): e for e in led}
    for e in RC.timed_high(cal) if cal else []:
        at = RC.at_of(e)
        m = at.replace(second=0, microsecond=0)
        le = led_by.get(m)
        out.append({"id": e["id"], "at": at, "name": e["name"], "end": RC.no_new_window(e)[1],
                    "kind": (le or {}).get("kind"), "expected": e.get("expected"),
                    "actual": e.get("actual"), "lesson": e.get("lesson")})
        seen[m] = True
    for m, e in led_by.items():
        if m in seen:
            continue
        at = _ts(e["at"])
        out.append({"id": e["id"], "at": at, "name": e.get("title") or e["id"],
                    "end": at + NO_NEW_AFTER, "kind": e.get("kind"),
                    "expected": None, "actual": None, "lesson": None})
    return sorted(out, key=lambda x: x["at"])


def reaction_30m(at: datetime, now: datetime, history=None) -> dict:
    """
    واکنش ۳۰ دقیقه بیت‌کوین: باز شمع ۱۵ دقیقه‌ای رویداد تا بسته شمع بعدی، هر دو بسته.
    history همان radar_history.history — آزمون جایش ساختگی می‌گذارد. خطا بلند.
    """
    if history is None:
        import radar_history as RH
        history = RH.history
    u = at.astimezone(UTC)
    t0 = u.replace(minute=u.minute - u.minute % 15, second=0, microsecond=0)
    t1 = t0 + timedelta(minutes=15)
    s = history("BTC", "15m", t0, t1, cache_dir=None, now=now)
    df = s.df[s.df["confirm"] == 1]
    a = df[df["ts"] == t0]
    b = df[df["ts"] == t1]
    if a.empty or b.empty:
        raise LookupError(f"شمع بسته ۱۵ دقیقه‌ای {t0:%H:%M} یا {t1:%H:%M} UTC نیامد")
    p0, p30 = float(a["open"].iloc[-1]), float(b["close"].iloc[-1])
    win = df[(df["ts"] >= t0) & (df["ts"] <= t1)]
    return {"p0": p0, "p30": p30, "chg_pct": 100.0 * (p30 / p0 - 1.0),
            "lo": float(win["low"].min()), "hi": float(win["high"].max()), "venue": s.venue}


def prior_reactions(ledger: dict | None, kind: str | None, before: datetime) -> list[tuple]:
    """واکنش ۲۴ ساعته بیت‌کوین رویدادهای همنوع پیشین در دفتر — (تاریخ، درصد)."""
    if not kind:
        return []
    out = []
    for e in (ledger or {}).get("events") or []:
        at = _ts(e.get("at"))
        if e.get("kind") != kind or at is None or at >= before:
            continue
        btc = (e.get("prices") or {}).get("BTC") or {}
        b, d = (btc.get("before") or {}).get("close"), (btc.get("h24") or {}).get("close")
        if isinstance(b, (int, float)) and isinstance(d, (int, float)) and b > 0:
            out.append((at, 100.0 * (d / b - 1.0)))
    return sorted(out)


def _result_line(ev: dict) -> str:
    a, x = ev.get("actual"), ev.get("expected")
    if a and x:
        return f"عدد واقعی {a}، انتظار بازار {x}"
    if x:
        return f"انتظار بازار {x}؛ عدد واقعی در تقویم ثبت نشده"
    if a:
        return f"عدد واقعی {a}؛ انتظار بازار ثبت نشده"
    return "عدد واقعی و انتظار بازار در تقویم دستی ثبت نشده"


def event_results(cal: dict | None, ledger: dict | None, state: dict, now: datetime,
                  make=None, history=None) -> list:
    """
    پیام نتیجه هر رویداد کلان با اهمیت بالا، یک بار، از نیم ساعت تا ۱۲ ساعت پس از آن.
    شمع نیامد: تا ۳ ساعت تلاش دوباره، سپس پیام بی واکنش با دلیل.
    """
    make = make or _Keyed
    out = []
    for ev in macro_events(cal, ledger):
        at = ev["at"]
        if not (at + RESULT_AFTER <= now <= at + RESULT_MAX_AGE):
            continue
        key = f"event_result_{ev['id']}"
        if state.get(key):
            continue
        try:
            r = reaction_30m(at, now, history)
            react = (f"واکنش ۳۰ دقیقه بیت‌کوین {r['chg_pct']:+.2f}٪ — از {_n(r['p0'])} به "
                     f"{_n(r['p30'])}، دامنه {_n(r['lo'])} تا {_n(r['hi'])}")
        except Exception as exc:                 # بلند در گزارش پایش؛ تلاش دوباره یا پیام بی واکنش
            why = f"{type(exc).__name__}: {str(exc)[:160]}"
            if now - at < RESULT_NO_DATA_AFTER:
                print(f"  نتیجه رویداد {ev['id']}: واکنش سنجیده نشد — {why}؛ اجرای بعد")
                continue
            r, react = None, f"واکنش ۳۰ دقیقه: داده ندارم — {why}"
        prior = prior_reactions(ledger, ev.get("kind"), at)
        if ev.get("lesson"):
            lesson = f"درس: {ev['lesson']}"
        elif prior:
            last = prior[-3:]
            vals = "، ".join(f"{d:%m-%d} {p:+.1f}٪" for d, p in last)
            lesson = (f"درس از دفتر: بیت‌کوین ۲۴ ساعت پس از {fa(len(last))} رویداد همنوع پیشین — "
                      f"{vals}. واکنش نیم‌ساعت اول را با ۲۴ ساعت بعد مقایسه کن؛ دفتر رویداد "
                      "۲۴ ساعت و ۷ روز همین یکی را خودش ثبت می‌کند")
        else:
            lesson = ("درس: نخستین رویداد این نوع در دفتر — ۲۴ ساعت و ۷ روز بعد را "
                      "events_ledger.json خودش ثبت می‌کند تا رفتار بازار در برابر این داده سنجیده شود")
        do = (f"کاری لازم نیست جز قاعده پنجره: تا {_th(ev['end'])} خرید تازه نه"
              if now < ev["end"] else "پنجره «موقعیت تازه نه» تمام شده؛ تصمیم تازه فقط طبق برنامه")
        title = f"نتیجه {ev['name']}"
        why = f"{_result_line(ev)}؛ {react}"
        text = "📊 " + AL.plain_of("blue", title, do, why, lesson)
        rec = {"at": at.isoformat(), "kind": ev.get("kind"), "seen": now.astimezone(UTC).isoformat(
            timespec="seconds"), "expected": ev.get("expected"), "actual": ev.get("actual")}
        if r:
            rec.update(p0=r["p0"], p30=r["p30"], chg30_pct=round(r["chg_pct"], 3),
                       lo=r["lo"], hi=r["hi"], venue=r["venue"])
        out.append(make(text, f"نتیجه رویداد {ev['id']}", {key: rec}, level="blue", title=title,
                        do=do, why=why, nxt=lesson, symbol="BTC"))
    return out
