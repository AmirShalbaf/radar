"""
ت۵ — زمان‌بندی گیت‌هاب، متن ۱۸، ۲۶ اکتبر ۲۰۲۶.

یافته از رابط Actions: نوبت‌ها دیر ساخته می‌شوند یا اصلاً ساخته نمی‌شوند؛ شکست و
push ردشده نبود. راه‌حل: نوبت بیشتر در دقیقه خلوت و نگهبان تکرار از داده مخزن.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_schedule as S

UTC = timezone.utc
FLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _log(*rows) -> dict:
    return {"version": 1, "runs": [{"at": t, "snapshot_rc": s, "watch_rc": w}
                                   for t, s, w in rows]}


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ── نبض ──

def test_pulse_runs_without_log() -> None:
    assert S.pulse_due({"version": 1, "runs": []}, _t("2026-10-26T10:41:00+00:00"))[0]


def test_pulse_skips_within_three_hours_of_last_ok() -> None:
    log = _log(("2026-10-26T08:45:00+00:00", 0, 0))
    run, why = S.pulse_due(log, _t("2026-10-26T10:41:00+00:00"))
    assert not run and "کمتر از" in why


def test_pulse_runs_after_three_hours() -> None:
    log = _log(("2026-10-26T07:40:00+00:00", 0, 0))
    assert S.pulse_due(log, _t("2026-10-26T10:41:00+00:00"))[0]


def test_failed_pulse_is_not_last_ok() -> None:
    # پایشگر با کد ۴ — پیام نرسید؛ نوبت بعد باید دوباره بفرستد
    log = _log(("2026-10-26T06:41:00+00:00", 0, 0), ("2026-10-26T08:41:00+00:00", 0, 4))
    assert S.pulse_due(log, _t("2026-10-26T10:41:00+00:00"))[0]
    log = _log(("2026-10-26T08:41:00+00:00", 1, 0))
    assert S.pulse_due(log, _t("2026-10-26T10:41:00+00:00"))[0]


def test_daily_close_overrides_gap() -> None:
    # نبض یکشنبه 22:30 نباید نوبت 00:41 دوشنبه را ببندد — بسته هفتگی ۲۶ اکتبر
    log = _log(("2026-10-25T22:32:00+00:00", 0, 0))
    run, why = S.pulse_due(log, _t("2026-10-26T00:41:00+00:00"))
    assert run and "بسته روزانه" in why


def test_manual_dispatch_always_runs(tmp_path) -> None:
    p = tmp_path / "log.json"
    p.write_text(json.dumps(_log(("2026-10-26T10:00:00+00:00", 0, 0))), encoding="utf-8")
    assert S.due("pulse", _t("2026-10-26T10:30:00+00:00"), "workflow_dispatch", str(p))[0]
    assert not S.due("pulse", _t("2026-10-26T10:30:00+00:00"), "schedule", str(p))[0]


def test_corrupt_log_runs_loudly(tmp_path) -> None:
    p = tmp_path / "log.json"
    p.write_text("{not json", encoding="utf-8")
    run, why = S.due("pulse", _t("2026-10-26T10:30:00+00:00"), "schedule", str(p))
    assert run and "خوانا نیست" in why


def test_record_appends_keeps_and_resets_corrupt(tmp_path, capsys) -> None:
    p = tmp_path / "log.json"
    now = _t("2026-10-26T10:41:00+00:00")
    for i in range(S.PULSE_KEEP + 5):
        S.record(str(p), now + timedelta(hours=2 * i), 0, 0)
    log = json.loads(p.read_text(encoding="utf-8"))
    assert len(log["runs"]) == S.PULSE_KEEP
    assert log["runs"][-1]["at"] == (now + timedelta(hours=2 * (S.PULSE_KEEP + 4))).isoformat()
    p.write_text("[", encoding="utf-8")
    S.record(str(p), now, 0, 4)
    log = json.loads(p.read_text(encoding="utf-8"))
    assert log["runs"] == [{"at": now.isoformat(), "snapshot_rc": 0, "watch_rc": 4}]
    assert "خوانا نیست" in log["reset"]["why"]
    assert "از نو" in capsys.readouterr().err


def test_cli_writes_github_output(tmp_path) -> None:
    out = tmp_path / "gh_out"
    log = tmp_path / "log.json"
    log.write_text(json.dumps(_log(("2026-10-26T10:00:00+00:00", 0, 0))), encoding="utf-8")
    S.main(["due", "pulse", "--log", str(log), "--github-output", str(out)],
           now=_t("2026-10-26T11:00:00+00:00"))
    assert out.read_text(encoding="utf-8") == "run=false\n"
    S.main(["due", "pulse", "--log", str(log), "--github-output", str(out)],
           now=_t("2026-10-26T14:00:00+00:00"))
    assert out.read_text(encoding="utf-8") == "run=false\nrun=true\n"


# ── روزانه و هفتگی ──

def test_daily_skips_when_today_report_exists(tmp_path) -> None:
    latest = tmp_path / "LATEST.md"
    latest.write_text("# گزارش رادار — 2026-10-26\n\nبدنه\n", encoding="utf-8")
    assert not S.daily_due(_t("2026-10-26T13:00:00+00:00"), str(latest))[0]
    assert S.daily_due(_t("2026-10-27T13:00:00+00:00"), str(latest))[0]
    assert S.daily_due(_t("2026-10-27T13:00:00+00:00"), str(tmp_path / "none.md"))[0]


def test_weekly_skips_same_week_only(tmp_path) -> None:
    (tmp_path / "selfcheck-2026-10-25.md").write_text("x", encoding="utf-8")
    # یکشنبه ۲۵ اکتبر و دوشنبه پس از آن: همان هفته
    assert not S.weekly_due(_t("2026-10-25T14:00:00+00:00"), str(tmp_path))[0]
    assert not S.weekly_due(_t("2026-10-26T01:00:00+00:00"), str(tmp_path))[0]
    # یکشنبه بعد: هفته تازه
    assert S.weekly_due(_t("2026-11-01T09:11:00+00:00"), str(tmp_path))[0]
    # پوشه‌ای با نام گزارش، ک۱۴، گزارش نیست
    (tmp_path / "book-weekly-2026-11-01.md").mkdir()
    assert S.weekly_due(_t("2026-11-01T09:11:00+00:00"), str(tmp_path))[0]


def test_week_start_is_sunday() -> None:
    assert str(S.week_start(_t("2026-10-25T12:00:00+00:00"))) == "2026-10-25"
    assert str(S.week_start(_t("2026-10-31T23:00:00+00:00"))) == "2026-10-25"
    assert str(S.week_start(_t("2026-11-01T00:00:00+00:00"))) == "2026-11-01"


# ── خط سلامت ──

def test_health_counts_and_max_gap_with_predecessor() -> None:
    log = _log(("2026-10-25T04:36:00+00:00", 0, 0),          # پیش از پنجره
               ("2026-10-25T13:10:00+00:00", 0, 0),
               ("2026-10-25T19:00:00+00:00", 0, 0),
               ("2026-10-25T22:32:00+00:00", 0, 0),
               ("2026-10-26T04:41:00+00:00", 0, 4))
    line = S.health_line(log, _t("2026-10-26T12:00:00+00:00"))
    assert "۴ نبض" in line
    # 13:10 − 04:36 = 8.57 ساعت، از نبض پیش از پنجره
    assert "بیشترین فاصله میان دو نبض 8.6 ساعت" in line
    assert "⚠️ بیش از سقف عمر نبض" in line
    assert "۱ نبض با خطا" in line


def test_health_young_log_says_since() -> None:
    log = _log(("2026-10-26T10:41:00+00:00", 0, 0))
    line = S.health_line(log, _t("2026-10-26T12:00:00+00:00"))
    assert "دفتر از 2026-10-26 10:41 UTC" in line and "فاصله‌ای برای سنجش نیست" in line
    assert "ردیفی ندارد" in S.health_line({"version": 1, "runs": []},
                                           _t("2026-10-26T12:00:00+00:00"))


# ── گردش‌کارها ──

def _text(name: str) -> str:
    return (FLOWS / name).read_text(encoding="utf-8")


def _crons(name: str) -> list[str]:
    return re.findall(r'-\s*cron:\s*"([^"]+)"', _text(name))


# نبض ساعتی از بند ۴ متن ۲۰ — tests/test_pulse_event_window.py


@pytest.mark.parametrize("wf", ["radar-daily.yml", "radar-weekly.yml"])
def test_second_cron_two_hours_later(wf) -> None:
    a, b = _crons(wf)
    ma, ha = a.split()[:2]
    mb, hb = b.split()[:2]
    assert ma == mb and int(hb) - int(ha) == 2
    assert a.split()[2:] == b.split()[2:]
    assert ma not in ("0", "15", "30", "45")


@pytest.mark.parametrize("wf,kind", [("radar-pulse.yml", "pulse"),
                                     ("radar-daily.yml", "daily"),
                                     ("radar-weekly.yml", "weekly")])
def test_guard_job_gates_main_job(wf, kind) -> None:
    t = _text(wf)
    assert f"radar_schedule.py due {kind}" in t
    assert '--event "${{ github.event_name }}"' in t
    assert "needs: due" in t
    assert "if: needs.due.outputs.run == 'true'" in t


def test_pulse_records_log_and_commits_it() -> None:
    t = _text("radar-pulse.yml")
    assert "radar_schedule.py record" in t
    assert "/tmp/snap_rc" in t and "/tmp/watch_rc" in t
    i_rec, i_commit = t.index("radar_schedule.py record"), t.index("- name: کامیت")
    assert i_rec < i_commit
    add = re.search(r"git add ([^\n]+)", t[i_commit:]).group(1)
    assert "pulse_log.json" in add


def test_daily_summary_has_health_line() -> None:
    t = _text("radar-daily.yml")
    s = t[t.index("- name: ساخت خلاصه امروز"):]
    assert "radar_schedule.py health" in s[:s.index("> reports/LATEST.md")]


def test_conftest_protects_pulse_log() -> None:
    import conftest
    assert "pulse_log.json" in conftest.DATA_FILES
