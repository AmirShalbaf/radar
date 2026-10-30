"""
تقویم رویداد دستی — بند ۳ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

events_calendar.json دستی با زمان UTC، نام و اهمیت؛ یادداشت «طبق منابع خبری، پیش از رویداد
وارسی شود». گزارش روزانه: رویدادهای ۷ روز آینده با ساعت تهران. تلگرام، برای هر رویداد با
اهمیت بالا و ساعت‌دار، دو یادآوری، هر کدام یک بار با کلید پس از ارسال موفق: ۲۴ ساعت مانده،
و ۲ ساعت یا کمتر با «از الان تا ۱ ساعت پس از کنفرانس، موقعیت تازه نه». ردیف اقدام سبد در
همان پنجره: «موقعیت تازه نه».
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_budget as BG
import radar_calendar as RC
import radar_telegram as TG
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 10, 27, 6, 37, tzinfo=UTC)
FOMC = datetime(2026, 10, 28, 18, 0, tzinfo=UTC)


def _real():
    return RC.load(str(ROOT / "events_calendar.json"))


def _cal(*events):
    return {"version": 1, "events": [copy.deepcopy(e) for e in events]}


EV = {"id": "x", "at": "2026-10-28T18:00:00+00:00", "name": "رویداد آزمون", "importance": "high"}


# ── فایل واقعی ──

def test_real_calendar_events() -> None:
    cal = _real()
    by = {e["id"]: e for e in cal["events"]}
    want = {
        "fomc-2026-10": ("2026-10-28T18:00:00+00:00", "high"),
        "pce-2026-09": ("2026-10-29T12:30:00+00:00", "high"),
        "gdp-2026q3-advance": ("2026-10-29T12:30:00+00:00", "medium"),
        "btc-options-2026-10-30": ("2026-10-30T08:00:00+00:00", "medium"),
        "nfp-2026-10": ("2026-11-06T13:30:00+00:00", "high"),
        "cpi-2026-10": ("2026-11-10T13:30:00+00:00", "high"),
    }
    for k, (at, imp) in want.items():
        assert by[k]["at"] == at and by[k]["importance"] == imp, k
    assert by["fomc-2026-10"]["press_at"] == "2026-10-28T18:30:00+00:00"
    mid = by["us-midterms-2026"]
    assert mid["date"] == "2026-11-03" and "at" not in mid and mid["importance"] == "high"
    assert all("طبق منابع خبری، پیش از رویداد وارسی شود" in e["note"] for e in cal["events"])
    assert "2026-11-01" in cal["_یادداشت"]


# ── اعتبارسنجی ──

@pytest.mark.parametrize("patch,needle", [
    ({"at": "2026-10-28T18:00:00"}, "منطقه زمانی"),
    ({"importance": "زیاد"}, "اهمیت"),
    ({"date": "2026-10-28"}, "هر دو"),
    ({"name": ""}, "نام"),
    ({"press_at": "2026-10-28T17:00:00+00:00"}, "کنفرانس"),
])
def test_bad_event_is_loud(patch, needle) -> None:
    with pytest.raises(RC.CalendarError, match=needle):
        RC.validate(_cal(dict(EV, **patch)))


def test_no_time_and_duplicate_id_are_loud() -> None:
    e = {k: v for k, v in EV.items() if k != "at"}
    with pytest.raises(RC.CalendarError, match="زمان"):
        RC.validate(_cal(e))
    with pytest.raises(RC.CalendarError, match="تکراری"):
        RC.validate(_cal(EV, EV))
    with pytest.raises(RC.CalendarError, match="date"):
        RC.validate(_cal(dict(e, date="3 Nov")))


def test_missing_file_is_empty_bad_file_is_loud(tmp_path) -> None:
    assert RC.load(str(tmp_path / "none.json")) == {"version": 1, "events": []}
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(RC.CalendarError):
        RC.load(str(p))


# ── گزارش روزانه: ۷ روز آینده با ساعت تهران ──

def test_upcoming_seven_days_tehran() -> None:
    cal = _real()
    ids = [e["id"] for e in RC.upcoming(cal, NOW, 7)]
    assert ids == ["fomc-2026-10", "pce-2026-09", "gdp-2026q3-advance",
                   "btc-options-2026-10-30", "us-midterms-2026"]
    # رویداد گذشته و بیرون از ۷ روز نه
    assert RC.upcoming(cal, datetime(2026, 10, 29, 13, 0, tzinfo=UTC), 1)[0]["id"] == \
        "btc-options-2026-10-30"
    s = RC.render_section(cal, NOW)
    assert s.startswith("## رویدادهای ۷ روز آینده — تقویم دستی")
    assert "2026-10-28 21:30 تهران" in s and "18:00 UTC" in s       # FOMC
    assert "کنفرانس خبری 22:00 تهران" in s
    assert "2026-10-29 16:00 تهران" in s                              # PCE
    assert "2026-11-03 — انتخابات میان‌دوره‌ای آمریکا" in s and "بی ساعت" in s
    assert "پنجره «موقعیت تازه نه»: 2026-10-28 19:30 تا 23:00 تهران" in s
    assert "طبق منابع خبری، پیش از رویداد وارسی شود" in s


# ── یادآوری تلگرام ──

def test_day_reminder_once_high_timed_only() -> None:
    cal = _real()
    t = FOMC - timedelta(hours=23, minutes=30)
    got = RC.reminders(cal, {}, t)
    assert [k for k, _ in got] == ["event_day_fomc-2026-10"]
    text = got[0][1]
    assert "2026-10-28 21:30 تهران" in text and "۲۴ ساعت" in text
    assert "طبق منابع خبری" in text
    # کلید ثبت‌شده: دوباره نه
    assert RC.reminders(cal, {"event_day_fomc-2026-10": True}, t) == []
    # ۲۵ ساعت مانده: هنوز نه
    assert RC.reminders(cal, {}, FOMC - timedelta(hours=25)) == []
    # اهمیت متوسط هرگز: سررسید اختیار معامله و رشد اقتصادی
    opt = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
    keys = [k for k, _ in RC.reminders(cal, {}, opt - timedelta(hours=1))]
    assert not any("options" in k or "gdp" in k for k in keys)


def test_near_reminder_sentence() -> None:
    cal = _real()
    t = FOMC - timedelta(hours=1, minutes=30)
    got = dict(RC.reminders(cal, {"event_day_fomc-2026-10": True}, t))
    text = got["event_near_fomc-2026-10"]
    assert "از الان تا ۱ ساعت پس از کنفرانس، موقعیت تازه نه" in text
    assert "2026-10-28 23:00 تهران" in text                     # پایان پنجره: 18:30 + ۱ ساعت
    # روز را جاانداخته: فقط نزدیک، نه هر دو
    # (PCE همان لحظه ۲۰ ساعت مانده — یادآوری روز خودش)
    assert [k for k, _ in RC.reminders(cal, {}, t)] == ["event_near_fomc-2026-10",
                                                        "event_day_pce-2026-09"]
    # پس از آغاز، تا پایان پنجره هنوز؛ پس از آن نه
    def fomc(t):
        return [k for k, _ in RC.reminders(cal, {}, t) if "fomc" in k]
    assert fomc(FOMC + timedelta(minutes=20)) == ["event_near_fomc-2026-10"]
    assert "آغاز شده" in dict(RC.reminders(cal, {}, FOMC + timedelta(minutes=20)))[
        "event_near_fomc-2026-10"]
    assert fomc(FOMC + timedelta(hours=1, minutes=31)) == []


def test_pce_has_no_conference() -> None:
    pce = datetime(2026, 10, 29, 12, 30, tzinfo=UTC)
    got = dict(RC.reminders(_real(), {"event_day_pce-2026-09": True}, pce - timedelta(hours=1)))
    text = got["event_near_pce-2026-09"]
    assert "از الان تا ۱ ساعت پس از انتشار، موقعیت تازه نه" in text


def test_no_new_window() -> None:
    cal = _real()
    assert RC.no_new_active(cal, FOMC - timedelta(hours=2, minutes=1)) == []
    act = RC.no_new_active(cal, FOMC - timedelta(hours=2))
    assert [e["id"] for e in act] == ["fomc-2026-10"]
    assert RC.no_new_active(cal, FOMC + timedelta(hours=1, minutes=30))
    assert RC.no_new_active(cal, FOMC + timedelta(hours=1, minutes=31)) == []
    rows = RC.no_new_actions(cal, FOMC)
    assert len(rows) == 1 and rows[0].startswith("**موقعیت تازه نه**")
    assert "2026-10-28 23:00 تهران" in rows[0]


# ── پایشگر: کلید فقط پس از رسید موفق ──

def test_run_once_sends_and_keys_after_receipt(tmp_path, monkeypatch) -> None:
    p = tmp_path / "cal.json"
    p.write_text(json.dumps(_real(), ensure_ascii=False), encoding="utf-8")
    sent = []
    ok = {"v": False}

    def fake(msg, quiet=False):
        sent.append(str(msg))
        return TG.Sent(ok["v"], "200" if ok["v"] else "500")
    monkeypatch.setattr(W, "notify", fake)
    monkeypatch.setattr(W, "stale_warning", lambda path: None)
    state: dict = {}
    t = FOMC - timedelta(hours=23)
    W.run_once({"items": []}, state, quiet=True, now=t, events_path=str(p))
    assert len(sent) == 1 and "event_day_fomc-2026-10" not in state
    ok["v"] = True
    W.run_once({"items": []}, state, quiet=True, now=t, events_path=str(p))
    assert len(sent) == 2 and state.get("event_day_fomc-2026-10") is True
    W.run_once({"items": []}, state, quiet=True, now=t, events_path=str(p))
    assert len(sent) == 2


def test_run_once_bad_calendar_is_loud(tmp_path, monkeypatch, capsys) -> None:
    p = tmp_path / "cal.json"
    p.write_text('{"events": [{"id": "x"}]}', encoding="utf-8")
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: TG.Sent(True, "200"))
    monkeypatch.setattr(W, "stale_warning", lambda path: None)
    W.run_once({"items": []}, {}, quiet=True, now=FOMC, events_path=str(p))
    assert "events_calendar" in capsys.readouterr().out


# ── ردیف اقدام سبد ──

def test_book_action_row_in_window() -> None:
    import radar_book as B
    h = {"positions": [], "cash": [], "ledger": []}
    val = {"total": 1000.0, "stable_usd": 400.0, "incomplete": False, "missing": []}
    reg = BG.band_by_name("انقباضی")
    rows = RC.no_new_actions(_real(), FOMC)
    txt = B.build_report(h, [], reg, [], val=val, event_actions=rows)
    sec6 = txt[txt.index("## ۶ — فهرست اقدام امروز"):]
    assert "**موقعیت تازه نه**" in sec6
    txt = B.build_report(h, [], reg, [], val=val, event_actions=[])
    assert "موقعیت تازه نه" not in txt


def test_workflows_wire_calendar() -> None:
    y = (ROOT / ".github" / "workflows" / "radar-daily.yml").read_text(encoding="utf-8")
    assert "python radar_calendar.py --section" in y
    head = y.index("# گزارش رادار — $D")
    assert y.index("cat /tmp/calendar_section.md", head) < y.index('echo "<!-- رویداد-آغاز -->"')
