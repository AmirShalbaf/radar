#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_calendar.py — تقویم رویداد دستی، بند ۳ متن ۲۰، ۲۷ اکتبر ۲۰۲۶
====================================================================

events_calendar.json دستی است: هر رویداد شناسه، نام، اهمیت و زمان. زمان یا مهر کامل UTC
در at — با press_at اختیاری برای کنفرانس خبری — یا فقط date برای رویداد بی‌ساعت. زمان‌ها
طبق منابع خبری‌اند و پیش از رویداد وارسی می‌شوند؛ کنار radar_events.py که تقویم کلان را
خودکار از منابع رسمی می‌سازد، نه جانشینش.

سه کار، هر سه فقط برای رویداد **با اهمیت بالا و ساعت‌دار**:

    یادآوری روز    یک بار، وقتی رویداد در ۲۴ ساعت آینده است و بیش از ۲ ساعت مانده
    یادآوری نزدیک  یک بار، وقتی ۲ ساعت یا کمتر مانده — تا پایان پنجره پایین
    موقعیت تازه نه  پنجره از ۲ ساعت پیش تا ۱ ساعت پس از کنفرانس، یا پس از انتشار
                   اگر کنفرانسی نیست: ردیف اقدام سبد

کلید هر یادآوری فقط پس از رسید موفق — پایشگر radar_watch آن را در Msg می‌پیچد. نگهبان
نبض radar_schedule پنجره ۶ ساعت پیش تا ۶ ساعت پس از همین رویدادها را از اینجا می‌خواند
— بند ۴. پس فقط کتابخانه استاندارد.

    python radar_calendar.py --section /tmp/calendar_section.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

from radar_anchor import TEHRAN
# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
CALENDAR_FILE = "events_calendar.json"
IMPORTANCE = {"high": "بالا", "medium": "متوسط", "low": "پایین"}
SECTION_DAYS = 7                       # گزارش روزانه — تصمیم کاربر، متن ۲۰
REMIND_DAY = timedelta(hours=24)       # یادآوری نخست
REMIND_NEAR = timedelta(hours=2)       # یادآوری دوم و آغاز پنجره «موقعیت تازه نه»
NO_NEW_AFTER = timedelta(hours=1)      # پایان پنجره پس از کنفرانس، یا انتشار
PULSE_SPAN = timedelta(hours=6)        # پنجره نبض نزدیک رویداد، دو سو — بند ۴
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")       # اسکی


class CalendarError(Exception):
    """تقویم خوانا یا درست نیست — صریح، نه فهرست خالی بی‌صدا."""


def _ts(raw, what: str) -> datetime:
    try:
        t = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError) as exc:
        raise CalendarError(f"{what}: مهر نامعتبر {raw!r}") from exc
    if t.tzinfo is None:
        raise CalendarError(f"{what}: مهر بی منطقه زمانی — مهر کامل UTC لازم است")
    return t.astimezone(UTC)


def validate(cal) -> None:
    if not isinstance(cal, dict) or not isinstance(cal.get("events"), list):
        raise CalendarError("events_calendar.json باید events فهرستی داشته باشد")
    seen: set = set()
    for i, e in enumerate(cal["events"], 1):
        where = f"رویداد {i}"
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"].strip():
            raise CalendarError(f"{where}: شناسه id لازم است")
        where += f" ({e['id']})"
        if e["id"] in seen:
            raise CalendarError(f"{where}: شناسه تکراری")
        seen.add(e["id"])
        if not isinstance(e.get("name"), str) or not e["name"].strip():
            raise CalendarError(f"{where}: نام لازم است")
        if e.get("importance") not in IMPORTANCE:
            raise CalendarError(f"{where}: اهمیت باید یکی از {'، '.join(IMPORTANCE)} باشد")
        has_at, has_date = "at" in e, "date" in e
        if has_at and has_date:
            raise CalendarError(f"{where}: هر دو at و date — یکی بس است")
        if not (has_at or has_date):
            raise CalendarError(f"{where}: زمان لازم است — at با ساعت یا date بی ساعت")
        if has_at:
            at = _ts(e["at"], f"{where}: at")
            if "press_at" in e and _ts(e["press_at"], f"{where}: press_at") < at:
                raise CalendarError(f"{where}: کنفرانس خبری press_at پیش از خود رویداد است")
        else:
            if not isinstance(e["date"], str) or not _DATE.match(e["date"]):
                raise CalendarError(f"{where}: date باید YYYY-MM-DD باشد")
            if "press_at" in e:
                raise CalendarError(f"{where}: رویداد بی ساعت کنفرانس ساعت‌دار ندارد")
        if "note" in e and not isinstance(e["note"], str):
            raise CalendarError(f"{where}: یادداشت متن نیست")


def load(path: str = CALENDAR_FILE) -> dict:
    """فایل غایب یعنی تقویم تهی. فایل خراب خطای صریح است."""
    if not os.path.exists(path):
        return {"version": 1, "events": []}
    try:
        with open(path, encoding="utf-8") as f:
            cal = json.load(f)
    except (OSError, ValueError) as exc:
        raise CalendarError(f"{os.path.basename(path)} خوانا نیست ({type(exc).__name__})") from exc
    validate(cal)
    return cal


# ═══════════════════════ زمان و پنجره ═══════════════════════

def at_of(e: dict) -> datetime | None:
    return _ts(e["at"], e["id"]) if "at" in e else None


def end_of(e: dict) -> datetime:
    """پایان رویداد ساعت‌دار: کنفرانس خبری اگر هست، وگرنه خود انتشار."""
    return _ts(e["press_at"], e["id"]) if "press_at" in e else at_of(e)


def _sort_key(e: dict) -> datetime:
    return at_of(e) or datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=UTC)


def timed_high(cal: dict) -> list[dict]:
    return [e for e in cal["events"] if e["importance"] == "high" and "at" in e]


def no_new_window(e: dict) -> tuple[datetime, datetime]:
    return at_of(e) - REMIND_NEAR, end_of(e) + NO_NEW_AFTER


def no_new_active(cal: dict, now: datetime) -> list[dict]:
    """رویدادهای با اهمیت بالا که اکنون در پنجره «موقعیت تازه نه»اند — دو سر بسته."""
    out = []
    for e in timed_high(cal):
        a, b = no_new_window(e)
        if a <= now <= b:
            out.append(e)
    return sorted(out, key=_sort_key)


def pulse_window(cal: dict, now: datetime) -> dict | None:
    """نخستین رویداد با اهمیت بالا که اکنون در ۶ ساعت پیش تا ۶ ساعت پس از آن است — بند ۴."""
    for e in sorted(timed_high(cal), key=_sort_key):
        if at_of(e) - PULSE_SPAN <= now <= end_of(e) + PULSE_SPAN:
            return e
    return None


def upcoming(cal: dict, now: datetime, days: int = SECTION_DAYS) -> list[dict]:
    """رویدادهای از اکنون تا days روز بعد؛ رویداد بی‌ساعت از امروز تا همان روز."""
    until = now + timedelta(days=days)
    out = []
    for e in cal["events"]:
        if "at" in e:
            if now <= at_of(e) <= until:
                out.append(e)
        else:
            d = date.fromisoformat(e["date"])
            if now.astimezone(UTC).date() <= d <= until.astimezone(UTC).date():
                out.append(e)
    return sorted(out, key=_sort_key)


def _th(t: datetime, with_date: bool = True) -> str:
    return f"{t.astimezone(TEHRAN):{'%Y-%m-%d %H:%M' if with_date else '%H:%M'}} تهران"


def _after_word(e: dict) -> str:
    return "کنفرانس" if "press_at" in e else "انتشار"


# ═══════════════════════ نمایش ═══════════════════════

def render_section(cal: dict, now: datetime, days: int = SECTION_DAYS) -> str:
    o = [f"## رویدادهای {fa(days)} روز آینده — تقویم دستی", ""]
    evs = upcoming(cal, now, days)
    if not evs:
        o.append(f"رویدادی در {fa(days)} روز آینده در events_calendar.json نیست.")
    for e in evs:
        imp = f"اهمیت {IMPORTANCE[e['importance']]}"
        at = at_of(e)
        if at is None:
            o.append(f"- {e['date']} — {e['name']}؛ بی ساعت؛ {imp}")
            continue
        line = f"- {_th(at)} ({at:%H:%M} UTC) — {e['name']}"
        if "press_at" in e:
            line += f"؛ کنفرانس خبری {_th(end_of(e), with_date=False)}"
        line += f"؛ {imp}"
        if e["importance"] == "high":
            a, b = no_new_window(e)
            same = a.astimezone(TEHRAN).date() == b.astimezone(TEHRAN).date()
            line += (f"؛ پنجره «موقعیت تازه نه»: {_th(a)[:-len(' تهران')]} تا "
                     f"{_th(b, with_date=not same)}")
        o.append(line)
    o += ["", "طبق منابع خبری، پیش از رویداد وارسی شود — events_calendar.json، دستی. تقویم "
              "خودکار منابع رسمی جداست: radar_events.py."]
    return "\n".join(o)


def reminders(cal: dict, state: dict, now: datetime) -> list[tuple[str, str]]:
    """
    (کلید، متن) یادآوری‌های این اجرا. state دست نمی‌خورد — کلید فقط پس از رسید موفق،
    با Msg پایشگر. نبض جاافتاده روز را جبران نمی‌کند اگر ۲ ساعت یا کمتر مانده: فقط نزدیک.
    """
    out = []
    for e in sorted(timed_high(cal), key=_sort_key):
        at, (_, end) = at_of(e), no_new_window(e)
        left = at - now
        note = f"\n{e['note']}" if e.get("note") else ""
        when = f"{_th(at)} ({at:%Y-%m-%d %H:%M} UTC)"
        if "press_at" in e:
            when += f"، کنفرانس خبری {_th(end_of(e), with_date=False)}"
        if REMIND_NEAR < left <= REMIND_DAY:
            key = f"event_day_{e['id']}"
            if not state.get(key):
                out.append((key, (
                    f"📅 یادآوری رویداد — {e['name']}: {when}؛ کمتر از {fa(24)} ساعت دیگر، "
                    f"اهمیت بالا.\nپنجره «موقعیت تازه نه» از {_th(at - REMIND_NEAR)} تا "
                    f"{_th(end, with_date=False)}." + note)))
        elif left <= REMIND_NEAR and now <= end:
            key = f"event_near_{e['id']}"
            if not state.get(key):
                mins = int(left.total_seconds() // 60)
                left_txt = (f"{fa(mins)} دقیقه دیگر" if mins > 0 else "آغاز شده")
                out.append((key, (
                    f"⏰ {e['name']} — {left_txt}، {when}.\n"
                    f"از الان تا ۱ ساعت پس از {_after_word(e)}، موقعیت تازه نه — تا "
                    f"{_th(end)}." + note)))
    return out


def no_new_actions(cal: dict, now: datetime) -> list[str]:
    """ردیف اقدام سبد در پنجره «موقعیت تازه نه»."""
    out = []
    for e in no_new_active(cal, now):
        _, end = no_new_window(e)
        out.append(f"**موقعیت تازه نه** — {e['name']}؛ تا {_th(end)} ({end:%H:%M} UTC): از "
                   f"{fa(2)} ساعت پیش تا ۱ ساعت پس از {_after_word(e)} — events_calendar.json")
    return out


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="تقویم رویداد دستی — بند ۳ متن ۲۰")
    ap.add_argument("--calendar", default=CALENDAR_FILE)
    ap.add_argument("--section", default=None, help="بخش گزارش روزانه؛ بی آن چاپ")
    ap.add_argument("--days", type=int, default=SECTION_DAYS)
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)
    rc = 0
    try:
        text = render_section(load(a.calendar), now, a.days)
    except CalendarError as exc:
        text = f"## رویدادهای {fa(a.days)} روز آینده — تقویم دستی\n\n⚠️ {exc}"
        rc = 2
    if a.section:
        with open(a.section, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
