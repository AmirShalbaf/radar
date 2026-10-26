#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_schedule.py — نگهبان تکرار زمان‌بندی گیت‌هاب و دفتر نبض، ت۵
==================================================================

یافته ت۵، متن ۱۸، ۲۶ اکتبر ۲۰۲۶ — از رابط Actions گیت‌هاب، مخزن عمومی:

    نبض «17 */4»     ۳۰ روز: 108 اجرا از 180 نوبت، 3.6 در روز؛ 63 فاصله از 107
                      بیش از ۶ ساعت، بیشترین 12.0 ساعت. نوبت 00:17 و 08:17 تقریباً
                      هرگز ساخته نشد.
    روزانه «30 6»    ۳۰ روز: 4.6 تا 9.4 ساعت دیر، میانه 6.4.
    هفتگی «0 7»      4.4 تا 6.6 ساعت دیر.

زمان ساخت هر اجرا با زمان شروعش یکی است و هر 217 اجرای نبض موفق بود، تلاش اول. پس
اجرا دیر ساخته می‌شود یا اصلاً ساخته نمی‌شود — تأخیر زمان‌بند گیت‌هاب، حدس الف. شکست
و push ردشده نبود، حدس ب؛ اجرای موفق بی‌کامیت هم نه، حدس ج.

راه‌حل بی‌راز تازه: نوبت بیشتر در دقیقه خلوت، و این نگهبان تا نوبت اضافه کار تکراری
نکند. نگهبان فقط از داده مخزن می‌خواند، نه از حافظه اجرا:

    نبض      هر دو ساعت. بی‌کار اگر آخرین نبض موفق کمتر از ۳ ساعت پیش بود — مگر
             پس از آن یک بسته روزانه وقت جهانی آمده باشد. دلیل استثنا: پیام بسته
             هفتگی ۲۶ اکتبر 04:41 رفت؛ نبض 22:30 یکشنبه نباید نوبت 00:41 دوشنبه را
             ببندد. موفق یعنی عکس نبض و پایشگر هر دو با کد ۰ — دفتر pulse_log.json.
    روزانه   نوبت دوم دو ساعت بعد. بی‌کار اگر reports/LATEST.md گزارش همان روز است.
    هفتگی    نوبت دوم دو ساعت بعد. بی‌کار اگر گزارش خودسنجی یا بازبینی هفتگی سبد
             از یکشنبه همین هفته به بعد هست.

اجرای دستی workflow_dispatch همیشه کار می‌کند.

فقط کتابخانه استاندارد — گام نگهبان پیش از نصب وابستگی‌ها اجرا می‌شود.

    python radar_schedule.py due pulse --event schedule --github-output "$GITHUB_OUTPUT"
    python radar_schedule.py record --snapshot-rc 0 --watch-rc 0
    python radar_schedule.py health
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# تنها منبع اصلی کمک‌تابع رقم فارسی — کپی محلی نگیر
from radar_text import fa

UTC = timezone.utc
PULSE_LOG = "pulse_log.json"
# کمینه فاصله دو نبض با کار — تصمیم کاربر، متن ۱۸
PULSE_MIN_GAP_HOURS = 3
# شمار ردیف نگه‌داشته — با نبض دوساعته حدود ده روز
PULSE_KEEP = 120
LATEST = os.path.join("reports", "LATEST.md")
REPORTS = "reports"
# گزارش‌های هفتگی که نشان می‌دهند اجرای هفته کار کرده
WEEKLY_MARKS = ("selfcheck", "book-weekly")
_LATEST_HEAD = re.compile(r"^# گزارش رادار — ([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$")   # اسکی


class ScheduleError(Exception):
    """دفتر نبض خوانا نیست — صریح، نه فهرست خالی بی‌صدا."""


# ═══════════════════════ دفتر نبض ═══════════════════════

def load_log(path: str = PULSE_LOG) -> dict:
    """دفتر غایب یعنی تهی. دفتر خراب خطای صریح است."""
    if not os.path.exists(path):
        return {"version": 1, "runs": []}
    try:
        with open(path, encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, ValueError) as exc:
        raise ScheduleError(f"{os.path.basename(path)} خوانا نیست ({type(exc).__name__})") from exc
    if not isinstance(log, dict) or not isinstance(log.get("runs"), list):
        raise ScheduleError(f"{os.path.basename(path)} ساختار درست ندارد")
    return log


def _at(raw) -> datetime:
    t = datetime.fromisoformat(str(raw))
    if t.tzinfo is None:
        raise ScheduleError(f"مهر دفتر نبض منطقه زمانی ندارد: {raw!r}")
    return t.astimezone(UTC)


def _ok(r: dict) -> bool:
    return r.get("snapshot_rc") == 0 and r.get("watch_rc") == 0


def record(path: str, now: datetime, snapshot_rc: int, watch_rc: int) -> dict:
    """
    یک نبض با کار. دفتر خراب بازنویسی می‌شود ولی بی‌صدا نه: ردیف reset با دلیل.
    نوشتن اتمی، مثل regime.json.
    """
    entry = {"at": now.astimezone(UTC).isoformat(timespec="seconds"),
             "snapshot_rc": snapshot_rc, "watch_rc": watch_rc}
    try:
        log = load_log(path)
    except ScheduleError as exc:
        print(f"⚠️ {exc} — دفتر نبض از نو شروع شد", file=sys.stderr)
        log = {"version": 1, "runs": [], "reset": {"at": entry["at"], "why": str(exc)}}
    log["runs"] = (log["runs"] + [entry])[-PULSE_KEEP:]
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return entry


def last_ok(log: dict) -> datetime | None:
    oks = [_at(r["at"]) for r in log["runs"] if isinstance(r, dict) and _ok(r)]
    return max(oks, default=None)


# ═══════════════════════ نگهبان تکرار ═══════════════════════

def pulse_due(log: dict, now: datetime) -> tuple[bool, str]:
    last = last_ok(log)
    if last is None:
        return True, "نبض موفقی در دفتر نیست"
    if last.date() < now.astimezone(UTC).date():
        return True, (f"آخرین نبض موفق {last:%Y-%m-%d %H:%M} UTC پیش از بسته روزانه امروز است")
    age = (now - last).total_seconds() / 3600
    if age < PULSE_MIN_GAP_HOURS:
        return False, (f"آخرین نبض موفق {last:%H:%M} UTC، {age:.1f} ساعت پیش — کمتر از "
                       f"{fa(PULSE_MIN_GAP_HOURS)} ساعت")
    return True, f"آخرین نبض موفق {age:.1f} ساعت پیش"


def daily_due(now: datetime, latest: str = LATEST) -> tuple[bool, str]:
    today = now.astimezone(UTC).strftime("%Y-%m-%d")
    try:
        with open(latest, encoding="utf-8") as f:
            head = f.readline().strip()
    except OSError:
        return True, f"{latest} نیست"
    m = _LATEST_HEAD.match(head)
    if m and m.group(1) == today:
        return False, f"گزارش روزانه {today} هست — {latest}"
    return True, f"گزارش روزانه {today} نیست — سرخط {head[:60]!r}"


def week_start(now: datetime):
    """یکشنبه همین هفته یا امروز، اگر یکشنبه است — روز اجرای هفتگی."""
    d = now.astimezone(UTC).date()
    return d - timedelta(days=(d.weekday() + 1) % 7)


def weekly_due(now: datetime, reports: str = REPORTS) -> tuple[bool, str]:
    start, today = week_start(now), now.astimezone(UTC).date()
    pat = re.compile(r"^(" + "|".join(WEEKLY_MARKS) + r")-([0-9]{4}-[0-9]{2}-[0-9]{2})\.md$")
    try:
        names = os.listdir(reports)
    except OSError:
        return True, f"پوشه {reports} نیست"
    for n in sorted(names):
        m = pat.match(n)
        if m and os.path.isfile(os.path.join(reports, n)):
            day = datetime.strptime(m.group(2), "%Y-%m-%d").date()
            if start <= day <= today:
                return False, f"گزارش هفتگی همین هفته هست — {n}"
    return True, f"گزارش هفتگی از {start} به بعد نیست"


def due(kind: str, now: datetime, event: str = "schedule", log_path: str = PULSE_LOG,
        latest: str = LATEST, reports: str = REPORTS) -> tuple[bool, str]:
    if event == "workflow_dispatch":
        return True, "اجرای دستی — نگهبان تکرار کنار می‌رود"
    if kind == "daily":
        return daily_due(now, latest)
    if kind == "weekly":
        return weekly_due(now, reports)
    try:
        log = load_log(log_path)
    except ScheduleError as exc:
        # نبض اضافه بهتر از نبض گم‌شده است — اجرا، ولی بلند
        return True, f"{exc} — نگهبان سنجیده نشد"
    return pulse_due(log, now)


# ═══════════════════════ خط سلامت گزارش روزانه ═══════════════════════

def health_line(log: dict, now: datetime) -> str:
    """
    شمار نبض‌های با کار در ۲۴ ساعت گذشته و بیشترین فاصله میان دو نبض پیاپی. فاصله
    نبض پیش از پنجره تا نخستین نبض پنجره هم شمرده می‌شود. بالای سقف عمر نبض —
    STALE_HOURS در radar_snapshot — هشدار می‌گیرد.
    """
    try:
        from radar_snapshot import STALE_HOURS      # تنها منبع سقف عمر نبض
    except SystemExit:                              # radar_snapshot بی requests می‌بندد
        STALE_HOURS = None
    runs = sorted(_at(r["at"]) for r in log["runs"] if isinstance(r, dict) and r.get("at"))
    since = now - timedelta(hours=24)
    win = [t for t in runs if since <= t <= now]
    head = f"🫀 سلامت نبض — ۲۴ ساعت گذشته: {fa(len(win))} نبض"
    if not runs:
        return head + "؛ دفتر نبض هنوز ردیفی ندارد"
    if runs[0] > since:
        head += f"؛ دفتر از {runs[0]:%Y-%m-%d %H:%M} UTC"
    before = [t for t in runs if t < since]
    seq = ([before[-1]] if before else []) + win
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(seq, seq[1:])]
    if not gaps:
        return head + "؛ فاصله‌ای برای سنجش نیست"
    worst = max(gaps)
    line = f"{head}؛ بیشترین فاصله میان دو نبض {worst:.1f} ساعت"
    if STALE_HOURS is not None and worst > STALE_HOURS:
        line += f" — ⚠️ بیش از سقف عمر نبض، {fa(f'{STALE_HOURS:.0f}')} ساعت"
    bad = sum(1 for r in log["runs"] if isinstance(r, dict) and r.get("at")
              and since <= _at(r["at"]) <= now and not _ok(r))
    if bad:
        line += f"؛ {fa(bad)} نبض با خطا"
    return line


# ═══════════════════════ خط فرمان ═══════════════════════

def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="نگهبان تکرار زمان‌بندی و دفتر نبض — ت۵")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("due", help="آیا این نوبت کار کند؟")
    p.add_argument("kind", choices=("pulse", "daily", "weekly"))
    p.add_argument("--event", default="schedule")
    p.add_argument("--github-output", dest="github_output", default=None)
    p.add_argument("--log", default=PULSE_LOG)
    p = sp.add_parser("record", help="ثبت یک نبض با کار")
    p.add_argument("--snapshot-rc", dest="snapshot_rc", type=int, required=True)
    p.add_argument("--watch-rc", dest="watch_rc", type=int, required=True)
    p.add_argument("--log", default=PULSE_LOG)
    p = sp.add_parser("health", help="خط سلامت نبض برای گزارش روزانه")
    p.add_argument("--log", default=PULSE_LOG)
    a = ap.parse_args(argv)
    now = now or datetime.now(UTC)

    if a.cmd == "due":
        run, why = due(a.kind, now, a.event, a.log)
        print(f"{'▶️ اجرا' if run else '⏭ بی‌کار'} — {why}")
        if a.github_output:
            with open(a.github_output, "a", encoding="utf-8") as f:
                f.write(f"run={'true' if run else 'false'}\n")
        return 0
    if a.cmd == "record":
        e = record(a.log, now, a.snapshot_rc, a.watch_rc)
        print(f"دفتر نبض: {e['at']} — عکس {e['snapshot_rc']}، پایشگر {e['watch_rc']}")
        return 0
    try:
        print(health_line(load_log(a.log), now))
    except ScheduleError as exc:
        print(f"🫀 سلامت نبض — ⚠️ {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
