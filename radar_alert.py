#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_alert.py — لایه هشدار تلگرام رادار، متن ۳۸
=================================================

پایشگر نبض — radar_watch.py — هشدار می‌سازد و همین فایل شکل و صدای آن را تعیین می‌کند.
تصمیم کاربر ۳ و ۴ نوامبر ۲۰۲۶، ک۱۲۹:

    🔴 اقدام          با صدا — کاری که باید انجام شود
    🟠 نمودار را ببین  با صدا، تا سقف روزانه — نگاه لازم، اقدام نه
    🔵 بدان و بیاموز   بی‌صدا — آگاهی و درس

قالب هر هشدار: «چه کنم، چرا، بعدش»، با دکمه پیوندی — نمودار نماد، میز تحلیلگر، گزارش.

ساعت سکوت شب، ۲۳:۰۰ تا ۷:۳۰ تهران: قرمز بی‌صدا می‌رود و در صف تکرار صبح می‌نشیند؛
نخستین اجرای پایشگر از ۷:۳۰ تهران آن را با صدا دوباره می‌فرستد، مگر کار انجام شده باشد.
نارنجی شب بی‌صدا. نارنجی روز تا سقف ORANGE_SOUND_CAP در هر روز تهران با صدا، بیشتر از
آن بی‌صدا و با برچسب — هیچ هشداری حذف نمی‌شود، فقط صدایش.

قرارداد با پایشگر:
- Alert یک str است که مقدارش متن ساده همیشگی پیام است — آزمون‌های قدیمی پایشگر همان
  را می‌سنجند. شکل تازه در میدان‌ها می‌نشیند و prepare آن را به HTML می‌برد.
- prepare حالت را نمی‌نویسد؛ delivered فقط پس از رسید موفق شمارش نارنجی و صف تکرار
  صبح را ثبت می‌کند — همان قاعده «کلید فقط با رسید» پایشگر.
- radar_telegram.send هشداری را که html دارد با parse_mode HTML می‌فرستد و اگر تلگرام
  رد کرد، همان متن ساده را.

فقط کتابخانه استاندارد و radar_telegram.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

import radar_telegram as TG
from radar_anchor import TEHRAN
# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc

LEVELS = {
    "red": ("🔴", "اقدام"),
    "orange": ("🟠", "نمودار را ببین"),
    "blue": ("🔵", "بدان و بیاموز"),
}
QUIET_FROM = time(23, 0)                 # تهران
QUIET_TO = time(7, 30)                   # تهران — تکرار صبح از همین ساعت
ORANGE_SOUND_CAP = 4                     # نارنجی با صدا در هر روز تهران
REPEAT_STALE = timedelta(hours=12)       # تکرار صبح که تا این مدت پس از موعد نرسید، کنار می‌رود
BOX = "_alert"                           # کلید لایه هشدار در watch_state.json
TV_CHART = "https://www.tradingview.com/chart/?symbol=OKX:{sym}USDT"
NOTE_NIGHT_RED = "شب — بی‌صدا؛ از ۷:۳۰ تهران دوباره با صدا، مگر انجام شده باشد"
NOTE_NIGHT = "شب — بی‌صدا"
NOTE_CAP = f"سقف روزانه {fa(ORANGE_SOUND_CAP)} هشدار نارنجی با صدا پر شد — بی‌صدا"
NOTE_REPEAT = "تکرار صبح — هنوز انجام نشده"


class Alert(str):
    """
    هشدار پایشگر. مقدار str متن ساده است؛ level، title، do، why، nxt، cmd و symbol شکل
    تازه‌اند. check داده وارسی «انجام شد» برای تکرار صبح است — تفسیرش با پایشگر.
    """

    def __new__(cls, text: str | None = None, level: str = "blue", title: str | None = None,
                do: str | None = None, why: str | None = None, nxt: str | None = None,
                cmd: str | None = None, symbol: str | None = None, check: dict | None = None,
                notes: list | tuple = ()):
        if level not in LEVELS:
            raise ValueError(f"سطح هشدار ناشناخته: {level!r}")
        if text is None:
            text = plain_of(level, title, do, why, nxt, cmd)
        a = super().__new__(cls, text)
        a.level, a.title, a.do, a.why, a.nxt, a.cmd = level, title, do, why, nxt, cmd
        a.symbol = symbol.upper() if symbol else None
        a.check = dict(check) if check else None
        a.notes = list(notes)
        a.html, a.silent, a.buttons, a.night, a.repeat_id = None, False, None, False, None
        return a


def plain_of(level: str, title, do, why, nxt, cmd=None) -> str:
    """متن ساده هشدار تازه — همان چهار بخش، بی تگ."""
    icon, word = LEVELS[level]
    lines = [f"{icon} {word} — {title}" if title else f"{icon} {word}"]
    for k, v in (("چه کنم", do), ("چرا", why), ("بعدش", nxt)):
        if v:
            lines.append(f"{k}: {v}")
    if cmd:
        lines.append(cmd)
    return "\n".join(lines)


def as_alert(msg, level: str = "orange") -> Alert:
    """پیام ساده قدیمی هم شکل هشدار می‌گیرد — سطح پیش‌فرض نارنجی، بدنه همان متن."""
    return msg if isinstance(msg, Alert) else Alert(str(msg), level)


# ═══════════════════════ قالب ═══════════════════════

def render(a: Alert) -> str:
    """HTML هشدار — سطر سر با نشان سطح، سپس چه کنم، چرا، بعدش؛ یا بدنه متن ساده."""
    E = TG.html_escape
    icon, word = LEVELS[a.level]
    head = f"{icon} <b>{E(word)} — {E(a.title)}</b>" if a.title else f"{icon} <b>{E(word)}</b>"
    lines = [head]
    if a.do or a.why or a.nxt:
        for k, v in (("چه کنم", a.do), ("چرا", a.why), ("بعدش", a.nxt)):
            if v:
                lines.append(f"<b>{k}:</b> {E(v)}")
        if a.cmd:
            lines.append(f"<code>{E(a.cmd)}</code>")
    else:
        lines += [E(s) for s in str(a).split("\n")]
    for n in a.notes:
        lines.append(f"<i>{E(n)}</i>")
    html = TG.rtl("\n".join(lines))
    if len(html) > TG.HTML_MAX:                 # بلند: متن ساده بریده در قالب ساده
        body = TG.clip(str(a), TG.HTML_MAX - len(head) - 200)
        html = TG.rtl("\n".join([head, E(body)] + [f"<i>{E(n)}</i>" for n in a.notes]))
    return html


def buttons_for(a: Alert, env=os.environ) -> list:
    """دکمه‌های پیوندی: نمودار نماد؛ میز تحلیلگر و گزارش کامل اگر نشانی‌شان هست."""
    rows = []
    if a.symbol:
        rows.append([(f"📈 نمودار {a.symbol}", TV_CHART.format(sym=a.symbol))])
    second = []
    desk = env.get("RADAR_DESK_URL", "")
    if desk.startswith("https://"):
        second.append(("📋 میز تحلیلگر", desk))
    repo = env.get("GITHUB_REPOSITORY", "")
    if repo:
        second.append(("📄 گزارش کامل", f"https://github.com/{repo}/blob/main/reports/LATEST.md"))
    if second:
        rows.append(second)
    return rows


# ═══════════════════════ صدا، شب و سقف ═══════════════════════

def is_quiet(now: datetime) -> bool:
    t = now.astimezone(TEHRAN).time()
    return t >= QUIET_FROM or t < QUIET_TO


def next_morning(now: datetime) -> datetime:
    """نخستین ۷:۳۰ تهران پس از اکنون — موعد تکرار صبح."""
    t = now.astimezone(TEHRAN)
    m = t.replace(hour=QUIET_TO.hour, minute=QUIET_TO.minute, second=0, microsecond=0)
    if m <= t:
        m += timedelta(days=1)
    return m.astimezone(UTC)


def _day(now: datetime) -> str:
    return now.astimezone(TEHRAN).strftime("%Y-%m-%d")


def orange_sounded(state: dict | None, now: datetime) -> int:
    o = ((state or {}).get(BOX) or {}).get("orange") or {}
    return int(o.get("n") or 0) if o.get("day") == _day(now) else 0


def prepare(msg, state: dict | None, now: datetime, env=os.environ) -> Alert:
    """صدا، برچسب، دکمه و HTML. حالت را نمی‌نویسد — delivered پس از رسید."""
    a = as_alert(msg)
    night = is_quiet(now)
    if a.level == "blue":
        silent = True
    elif night:
        silent = True
        a.notes.append(NOTE_NIGHT_RED if a.level == "red" and not a.repeat_id else NOTE_NIGHT)
    elif a.level == "orange" and orange_sounded(state, now) >= ORANGE_SOUND_CAP:
        silent = True
        a.notes.append(NOTE_CAP)
    else:
        silent = False
    a.silent, a.night = silent, night
    a.buttons = buttons_for(a, env)
    a.html = render(a)
    return a


def delivered(a: Alert, state: dict | None, now: datetime) -> None:
    """پس از رسید موفق: شمارش نارنجی با صدا، صف تکرار صبح قرمز شب، و برداشتن تکرار انجام‌شده."""
    if state is None or not isinstance(a, Alert):
        return
    box = state.setdefault(BOX, {})
    if a.level == "orange" and not a.silent:
        day = _day(now)
        o = box.get("orange") or {}
        box["orange"] = {"day": day, "n": (int(o.get("n") or 0) if o.get("day") == day else 0) + 1}
    if a.repeat_id:
        box["repeat"] = [r for r in box.get("repeat") or [] if r.get("id") != a.repeat_id]
    elif a.level == "red" and a.night:
        made = now.astimezone(UTC)
        box.setdefault("repeat", []).append({
            "id": f"{made:%Y%m%dT%H%M%S}-{len(box.get('repeat') or [])}",
            "made": made.isoformat(timespec="seconds"),
            "due": next_morning(now).isoformat(timespec="seconds"),
            "text": str(a), "title": a.title, "do": a.do, "why": a.why, "nxt": a.nxt,
            "cmd": a.cmd, "symbol": a.symbol, "check": a.check})


def due_repeats(state: dict | None, now: datetime, still_needed=None) -> list[Alert]:
    """
    قرمزهای شب که موعدشان رسیده. still_needed(ردیف) نادرست یعنی کار انجام شده — بی پیام
    کنار می‌رود. موعد گذشته‌تر از REPEAT_STALE هم کنار می‌رود: پیام صبح آن روز گذشته است.
    """
    if not state:
        return []
    box = state.get(BOX) or {}
    keep, out = [], []
    for r in box.get("repeat") or []:
        try:
            due = datetime.fromisoformat(r["due"])
        except (KeyError, TypeError, ValueError):
            print(f"  ⚠️ ردیف تکرار صبح خوانا نیست — کنار رفت: {r!r}"[:300])
            continue
        if now < due:
            keep.append(r)
            continue
        if now - due > REPEAT_STALE:
            print(f"  تکرار صبح «{r.get('title')}» کهنه شد — کنار رفت")
            continue
        if still_needed is not None and still_needed(r) is False:
            print(f"  تکرار صبح «{r.get('title')}» لازم نیست — انجام شده")
            continue
        keep.append(r)
        a = Alert(r.get("text"), "red", title=r.get("title"), do=r.get("do"), why=r.get("why"),
                  nxt=r.get("nxt"), cmd=r.get("cmd"), symbol=r.get("symbol"),
                  check=r.get("check"), notes=[NOTE_REPEAT])
        a.repeat_id = r.get("id")
        out.append(a)
    if box.get("repeat") is not None:
        box["repeat"] = keep
    return out
