"""
نبض نزدیک رویداد — بند ۴ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

cron نبض ساعتی با دقیقه خلوت. نگهبان: حالت عادی همان ۳ ساعت؛ در پنجره ۶ ساعت پیش تا ۶
ساعت پس از رویداد با اهمیت بالا و ساعت‌دار تقویم دستی، ۵۰ دقیقه. در روز عادی هنوز هر ۳
تا ۴ ساعت یک نبض، نه بیشتر.
"""
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_calendar as RC
import radar_schedule as S

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
FOMC = datetime(2026, 10, 28, 18, 0, tzinfo=UTC)


def _cal():
    return RC.load(str(ROOT / "events_calendar.json"))


def _log(*ats):
    return {"version": 1, "runs": [{"at": t.isoformat(), "snapshot_rc": 0, "watch_rc": 0}
                                   for t in ats]}


def test_pulse_cron_hourly_on_quiet_minute() -> None:
    t = (ROOT / ".github" / "workflows" / "radar-pulse.yml").read_text(encoding="utf-8")
    (c,) = re.findall(r'-\s*cron:\s*"([^"]+)"', t)
    minute, hour = c.split()[:2]
    assert hour == "*" and minute not in ("0", "15", "30", "45")
    assert c.split()[2:] == ["*", "*", "*"]


def test_event_window_gap_fifty_minutes() -> None:
    cal = _cal()
    now = FOMC - timedelta(hours=2)
    run, why = S.pulse_due(_log(now - timedelta(minutes=51)), now, cal)
    assert run and "FOMC" in why
    run, why = S.pulse_due(_log(now - timedelta(minutes=40)), now, cal)
    assert not run and "۵۰ دقیقه" in why
    # بیرون از پنجره، همان ۳ ساعت
    now = FOMC - timedelta(hours=8)
    assert not S.pulse_due(_log(now - timedelta(hours=2)), now, cal)[0]
    # بی تقویم، همان رفتار پیشین
    assert not S.pulse_due(_log(FOMC - timedelta(minutes=51)), FOMC, None)[0]


def test_window_bounds_six_hours_each_side_of_conference() -> None:
    cal = _cal()
    last = lambda t: _log(t - timedelta(minutes=55))              # noqa: E731
    assert not S.pulse_due(last(FOMC - timedelta(hours=6, minutes=1)),
                           FOMC - timedelta(hours=6, minutes=1), cal)[0]
    assert S.pulse_due(last(FOMC - timedelta(hours=6)), FOMC - timedelta(hours=6), cal)[0]
    end = FOMC + timedelta(minutes=30) + timedelta(hours=6)       # کنفرانس 18:30 + ۶ ساعت
    assert S.pulse_due(last(end), end, cal)[0]
    after = end + timedelta(minutes=1)
    # 00:31 روز بعد: بسته روزانه اجرا را می‌سازد، نه پنجره — پس آخرین نبض پس از 00:00
    log = _log(after.replace(hour=0, minute=5))
    assert not S.pulse_due(log, after, cal)[0]


def test_medium_and_undated_events_have_no_window() -> None:
    cal = _cal()
    opt = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)              # اختیار معامله، متوسط
    assert not S.pulse_due(_log(opt - timedelta(hours=1)), opt, cal)[0]
    mid = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)              # انتخابات، بی ساعت
    assert not S.pulse_due(_log(mid - timedelta(hours=1)), mid, cal)[0]


def test_due_reads_calendar_file_and_bad_file_falls_back_loudly(tmp_path) -> None:
    lp = tmp_path / "log.json"
    now = FOMC - timedelta(hours=1)
    lp.write_text(json.dumps(_log(now - timedelta(minutes=55))), encoding="utf-8")
    assert S.due("pulse", now, "schedule", str(lp), events_path=str(ROOT / "events_calendar.json"))[0]
    bad = tmp_path / "cal.json"
    bad.write_text("{", encoding="utf-8")
    run, why = S.due("pulse", now, "schedule", str(lp), events_path=str(bad))
    assert not run and "تقویم" in why
    assert not S.due("pulse", now, "schedule", str(lp),
                     events_path=str(tmp_path / "none.json"))[0]


def _sim_gaps(day, delays):
    """هر نوبت ساعتی :41 با تأخیر تصادفی گیت‌هاب؛ هر اجرا موفق."""
    log = _log(day - timedelta(hours=1, minutes=19))              # 22:41 روز پیش
    got = []
    # نوبت 23:41 در همان روز می‌ماند — اجرای پس از نیمه‌شب نبض بسته روزانه روز بعد است
    delays = delays[:23] + [min(delays[23], 18)]
    for h in range(24):
        t = day.replace(hour=h, minute=41) + timedelta(minutes=delays[h])
        if S.pulse_due(log, t, None)[0]:
            log["runs"].append({"at": t.isoformat(), "snapshot_rc": 0, "watch_rc": 0})
            got.append(t)
    return got


def test_normal_day_three_to_four_hours_not_more() -> None:
    day = datetime(2026, 10, 26, tzinfo=UTC)
    rng = random.Random(20)
    for _ in range(50):
        got = _sim_gaps(day, [rng.randint(0, 40) for _ in range(24)])
        gaps = [(b - a).total_seconds() / 3600 for a, b in zip(got, got[1:])]
        # کمینه ۳ ساعت؛ بیشینه ۴ ساعت به‌علاوه تأخیر نوبت — حدود ۳ تا ۴ ساعت، هرگز کمتر
        assert 6 <= len(got) <= 8
        assert all(3.0 <= g <= 4 + 40 / 60 for g in gaps), gaps
        assert 3.0 <= sum(gaps) / len(gaps) <= 4.0


def test_plan_three_days_this_week() -> None:
    cal = _cal()
    runs = S.plan(datetime(2026, 10, 27, tzinfo=UTC), 3, cal)
    by_day = {}
    for t, _ in runs:
        by_day.setdefault(t.date().isoformat(), []).append(t.strftime("%H:%M"))
    assert by_day["2026-10-27"] == ["00:41", "03:41", "06:41", "09:41", "12:41", "15:41",
                                    "18:41", "21:41"]
    # FOMC: پنجره 12:00 تا 00:30 روز بعد — ساعتی از 12:41
    assert by_day["2026-10-28"] == ["00:41", "03:41", "06:41", "09:41"] + \
        [f"{h:02d}:41" for h in range(12, 24)]
    # PCE بی کنفرانس: پنجره 06:30 تا 18:30؛ 18:41 بیرون است، پس سه ساعت از 17:41
    assert by_day["2026-10-29"] == ["00:41", "03:41"] + [f"{h:02d}:41" for h in range(6, 18)] \
        + ["20:41", "23:41"]


def test_plan_cli(capsys) -> None:
    assert S.main(["plan", "--from", "2026-10-28", "--days", "1",
                   "--events", str(ROOT / "events_calendar.json")]) == 0
    out = capsys.readouterr().out
    assert "2026-10-28" in out and "13:41" in out and "FOMC" in out
