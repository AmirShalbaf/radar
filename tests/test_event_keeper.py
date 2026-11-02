"""
نگهبان پنجره رویداد — ک۱۰۹، متن ۳۶، ۲ نوامبر ۲۰۲۶.

یافته: زمان‌بند گیت‌هاب نوبت ساعتی نبض را در روز رویداد هم می‌اندازد — ۲۸ و ۲۹ اکتبر دو
نبض از ۱۲ نوبت پنجره. راه: کار بلند radar-event-keeper.yml از ۲۴ ساعت پیش از آغاز پنجره
بیدار می‌ماند و در پنجره هر وقت آخرین نبض موفق دفتر به ۵۰ دقیقه رسید، نبض را با
workflow_dispatch راه می‌اندازد؛ هر اجرا ۵ ساعت و نیم و سپس جانشین، تا سقف نسل.
داده: تقویم ساختگی — آزمون با ویرایش تقویم واقعی نمی‌شکند. بی شبکه.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_schedule as S

UTC = timezone.utc
FLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "radar-event-keeper.yml"
EV = datetime(2026, 11, 6, 13, 30, tzinfo=UTC)
START, END = EV - timedelta(hours=6), EV + timedelta(hours=6)


def _cal(*extra) -> dict:
    return {"version": 1, "events": [
        {"id": "nfp", "at": EV.isoformat(), "name": "اشتغال", "importance": "high"},
        {"id": "low", "at": (EV - timedelta(hours=2)).isoformat(), "name": "کم",
         "importance": "medium"},
        {"id": "day", "date": "2026-11-05", "name": "بی ساعت", "importance": "high"},
        *extra]}


def _step(now, started=None, last=None, kicked=None, cal=None):
    return S.keeper_step(cal or _cal(), now, started or now, last, kicked)


def test_next_window_only_timed_high() -> None:
    e, a, b = S.next_window(_cal(), EV - timedelta(days=2))
    assert e["id"] == "nfp" and (a, b) == (START, END)
    assert S.next_window(_cal(), END + timedelta(seconds=1)) is None


def test_exit_when_window_far_or_gone() -> None:
    assert _step(START - timedelta(hours=25))[0] == "exit"
    assert _step(END + timedelta(minutes=1))[0] == "exit"


def test_sleep_until_window_start_within_lead() -> None:
    now = START - timedelta(hours=3)
    act, why, wake = _step(now)
    assert act == "sleep" and wake == START and "اشتغال" in why
    act, _, wake = _step(now, started=now - timedelta(hours=4))
    assert act == "sleep" and wake == now - timedelta(hours=4) + S.KEEPER_SPAN


def test_pulse_when_last_ok_is_old_or_missing() -> None:
    assert _step(START)[0] == "pulse"
    assert _step(START + timedelta(hours=1), last=START + timedelta(minutes=5))[0] == "pulse"


def test_sleep_while_fresh_or_settling() -> None:
    now = START + timedelta(hours=1)
    act, _, wake = _step(now, last=now - timedelta(minutes=10))
    assert act == "sleep" and wake == now + timedelta(minutes=40)
    act, _, wake = _step(now, last=now - timedelta(hours=2), kicked=now - timedelta(minutes=5))
    assert act == "sleep" and wake == now + timedelta(minutes=10)


def test_sleep_never_past_window_end() -> None:
    now = END - timedelta(minutes=5)
    act, _, wake = _step(now, last=now - timedelta(minutes=1))
    assert act == "sleep" and wake == END


def test_handoff_after_span() -> None:
    now = START + timedelta(hours=1)
    assert _step(now, started=now - S.KEEPER_SPAN)[0] == "handoff"


def _fakes(start, fail=()):
    t = [start]
    sent = []

    def dispatch(wf, inputs):
        sent.append((t[0], wf, dict(inputs)))
        return (wf not in fail), ("خطای آزمون" if wf in fail else "")
    return t, sent, (lambda: t[0]), (lambda s: t.__setitem__(0, t[0] + timedelta(seconds=s))), dispatch


def test_loop_hands_off_with_next_gen() -> None:
    t, sent, clock, sleep, dispatch = _fakes(START - timedelta(hours=10))
    assert S.keeper(_cal(), 2, clock, sleep, lambda: None, dispatch, out=lambda s: None) == 0
    assert sent == [(START - timedelta(hours=10) + S.KEEPER_SPAN, S.KEEPER_WORKFLOW, {"gen": "3"})]


def test_loop_gen_cap_is_loud() -> None:
    t, sent, clock, sleep, dispatch = _fakes(START - timedelta(hours=10))
    lines = []
    assert S.keeper(_cal(), S.KEEPER_MAX_GEN, clock, sleep, lambda: None, dispatch,
                    out=lines.append) == 1
    assert sent == [] and any("::error::" in s for s in lines)


def test_loop_failed_pulse_retries_after_settle_and_fails_job() -> None:
    # دفتر خوانا ولی نبض تازه‌ای در آن نمی‌نشیند: پس از فرصت ثبت، دوباره
    t, sent, clock, sleep, dispatch = _fakes(START, fail=(S.PULSE_WORKFLOW,))
    lines = []
    old = START - timedelta(hours=2)
    rc = S.keeper(_cal(), 0, clock, sleep, lambda: old, dispatch, out=lines.append)
    pulses = [x[0] for x in sent if x[1] == S.PULSE_WORKFLOW]
    assert pulses[:2] == [START, START + S.KEEPER_SETTLE]
    assert any("::warning::" in s for s in lines)
    assert rc == 1                                   # کار قرمز؛ صاحب مخزن ایمیل شکست می‌گیرد


def test_failed_handoff_is_loud() -> None:
    t, sent, clock, sleep, dispatch = _fakes(START - timedelta(hours=10),
                                             fail=(S.KEEPER_WORKFLOW,))
    lines = []
    assert S.keeper(_cal(), 0, clock, sleep, lambda: None, dispatch, out=lines.append) == 1
    assert any("::error::" in s for s in lines)


def test_simulation_covers_window_every_fifty_minutes() -> None:
    evs = S.keeper_simulate(_cal(), START - timedelta(hours=24))
    pulses = [t for t, w in evs if w == S.PULSE_WORKFLOW]
    assert pulses[0] == START and all(START <= p <= END for p in pulses)
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(pulses, pulses[1:])]
    assert min(gaps) >= S.PULSE_EVENT_GAP_MIN and max(gaps) <= 60
    assert len(pulses) >= 13
    gens = [w for _, w in evs if w.startswith(S.KEEPER_WORKFLOW)]
    assert gens and len(gens) < S.KEEPER_MAX_GEN


def test_simulation_skips_when_github_pulse_is_fresh() -> None:
    own = [START + timedelta(minutes=20)]
    evs = S.keeper_simulate(_cal(), START + timedelta(minutes=30), pulses=own)
    first = next(t for t, w in evs if w == S.PULSE_WORKFLOW)
    assert first == own[0] + timedelta(minutes=S.PULSE_EVENT_GAP_MIN)


def test_no_window_means_no_dispatch() -> None:
    assert S.keeper_simulate({"version": 1, "events": []}, START) == []


def _run(results):
    calls = []

    def run(args, **kw):
        calls.append(args)
        rc, out = results.pop(0)
        return subprocess.CompletedProcess(args, rc, stdout=out, stderr="")
    return run, calls


def test_remote_last_ok_reads_fresh_log() -> None:
    log = {"version": 1, "runs": [{"at": "2026-11-06T08:10:00+00:00", "snapshot_rc": 0,
                                   "watch_rc": 0},
                                  {"at": "2026-11-06T09:10:00+00:00", "snapshot_rc": 1,
                                   "watch_rc": 0}]}
    run, calls = _run([(0, ""), (0, json.dumps(log))])
    assert S.remote_last_ok(run=run) == datetime(2026, 11, 6, 8, 10, tzinfo=UTC)
    assert calls[0][:2] == ["git", "fetch"] and calls[1][-1] == "FETCH_HEAD:pulse_log.json"
    # بی --depth: «--depth=1» رونوشت کامل لپ‌تاپ را کم‌عمق می‌کرد — بازبینی متن ۳۶
    assert not any(str(x).startswith("--depth") for x in calls[0])


def test_remote_last_ok_is_none_on_failure() -> None:
    assert S.remote_last_ok(run=_run([(1, "")])[0]) is None
    assert S.remote_last_ok(run=_run([(0, ""), (0, "خراب")])[0]) is None


def test_gh_dispatch_arguments() -> None:
    run, calls = _run([(0, "")])
    assert S.gh_dispatch(S.KEEPER_WORKFLOW, {"gen": "4"}, run=run) == (True, "")
    assert calls[0] == ["gh", "workflow", "run", S.KEEPER_WORKFLOW, "--ref", "main",
                        "-f", "gen=4"]


def test_cli_plan_prints_dispatches(tmp_path, capsys) -> None:
    p = tmp_path / "cal.json"
    p.write_text(json.dumps(_cal(), ensure_ascii=False), encoding="utf-8")
    assert S.main(["keeper-plan", "--from", (START - timedelta(hours=1)).isoformat(),
                   "--events", str(p)]) == 0
    out = capsys.readouterr().out
    assert "radar-pulse.yml" in out and "07:30 UTC" in out
    assert S.main(["keeper-plan", "--from", "2026-11-06T06:00:00", "--events", str(p)]) == 2


def test_cli_broken_calendar_is_loud(tmp_path, capsys) -> None:
    p = tmp_path / "cal.json"
    p.write_text("{", encoding="utf-8")
    assert S.main(["keeper", "--events", str(p)]) == 1
    assert "::error::" in capsys.readouterr().out


def test_workflow_shape() -> None:
    t = FLOW.read_text(encoding="utf-8")
    (c,) = re.findall(r'-\s*cron:\s*"([^"]+)"', t)
    minute, hour = c.split()[:2]
    assert hour == "*" and minute not in ("0", "15", "30", "41", "45")
    assert "workflow_dispatch:" in t and "gen:" in t
    assert re.search(r"permissions:\s*\n\s*contents: read\s*\n\s*actions: write", t)
    assert re.search(r"group: radar-event-keeper\s*\n\s*cancel-in-progress: false", t)
    assert re.findall(r"runs-on:\s*(\S+)", t) == ["ubuntu-24.04"]
    (tm,) = re.findall(r"timeout-minutes:\s*(\d+)", t)
    assert S.KEEPER_SPAN.total_seconds() / 60 < int(tm) < 360
    assert 'python radar_schedule.py keeper --gen "$KEEPER_GEN"' in t
    assert "KEEPER_GEN: ${{ inputs.gen || '0' }}" in t
    assert '--gen "${{' not in t                       # ورودی هرگز مستقیم در فرمان پوسته
    assert "GH_TOKEN: ${{ github.token }}" in t
    assert "git push" not in t and "pip install" not in t


def test_blind_reader_keeps_fifty_minute_cadence() -> None:
    # دفتر ناخوانا: راه‌اندازی خود نگهبان نبض فرض می‌شود — هر ۵۰ دقیقه، نه هر ۱۵ دقیقه
    t, sent, clock, sleep, dispatch = _fakes(START)
    S.keeper(_cal(), 0, clock, sleep, lambda: None, dispatch, out=lambda s: None)
    pulses = [x[0] for x in sent if x[1] == S.PULSE_WORKFLOW]
    gaps = {(b - a).total_seconds() / 60 for a, b in zip(pulses, pulses[1:])}
    assert pulses[0] == START and gaps == {float(S.PULSE_EVENT_GAP_MIN)}
