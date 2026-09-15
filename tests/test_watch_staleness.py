"""
آزمون هشدار کهنگی سطوح پایش در radar_watch.py.

مسئله: پایشگر هر چهار ساعت در `radar-pulse.yml` اجرا می‌شود. اگر سطوح
`watch.json` ماه‌ها دست‌نخورده بماند، پایشگر بی‌صدا سطوح کهنه را می‌سنجد
و خروجی‌اش معتبر به نظر می‌رسد. سکوت اینجا بدترین حالت است.

نکته مهم درباره مهر زمانی: گیت مهر زمانی فایل را ذخیره نمی‌کند. در رانر
گیت‌هاب هر `actions/checkout` به همه فایل‌ها مهر تازه می‌زند، پس سنجش
بر پایه مهر زمانی در رانر **هرگز** فعال نمی‌شود. برای همین میدان صریح
`updated` داخل خود فایل مقدم است و مهر زمانی فقط برای اجرای محلی می‌ماند.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

UTC = timezone.utc


def _write(tmp_path, data, age_days=None):
    """فایل watch می‌سازد. اگر age_days داده شود، مهر زمانی عقب برده می‌شود."""
    p = tmp_path / "watch.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if age_days is not None:
        old = time.time() - age_days * 86_400
        os.utime(p, (old, old))
    return str(p)


ITEMS = {"items": [{"symbol": "ZEC", "side": "long", "alerts": [700.0]}]}


# ─────────────────────── آستانه ───────────────────────

def test_threshold_is_a_named_constant() -> None:
    """آستانه باید ثابت نام‌دار باشد، نه عدد جاافتاده در کد."""
    assert isinstance(W.STALE_AFTER_DAYS, (int, float))
    assert W.STALE_AFTER_DAYS > 0


# ─────────────────────── فایل تازه ───────────────────────

def test_fresh_file_no_warning(tmp_path) -> None:
    """فایل تازه هشدار نمی‌گیرد."""
    p = _write(tmp_path, ITEMS, age_days=1)
    assert W.stale_warning(p) is None


def test_fresh_by_explicit_field(tmp_path) -> None:
    """میدان updated تازه، حتی اگر مهر زمانی قدیمی باشد."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    p = _write(tmp_path, {**ITEMS, "updated": today}, age_days=400)
    assert W.stale_warning(p) is None


def test_just_under_threshold_is_fresh(tmp_path) -> None:
    """درست زیر آستانه هنوز تازه است."""
    p = _write(tmp_path, ITEMS, age_days=W.STALE_AFTER_DAYS - 1)
    assert W.stale_warning(p) is None


# ─────────────────────── فایل کهنه ───────────────────────

def test_stale_file_warns(tmp_path) -> None:
    """فایل کهنه هشدار می‌گیرد."""
    p = _write(tmp_path, ITEMS, age_days=W.STALE_AFTER_DAYS + 10)
    w = W.stale_warning(p)
    assert w is not None
    assert "کهنه" in w


def test_stale_warning_names_the_age(tmp_path) -> None:
    """هشدار باید سن واقعی را بگوید، نه فقط «کهنه»."""
    p = _write(tmp_path, ITEMS, age_days=40)
    w = W.stale_warning(p)
    assert "۴۰" in w or "40" in w


def test_stale_by_explicit_field_beats_fresh_mtime(tmp_path) -> None:
    """
    هسته آزمون: میدان صریح بر مهر زمانی مقدم است. این همان حالتی است که
    در رانر گیت‌هاب رخ می‌دهد — فایل تازه چک‌اوت شده ولی سطوح ماه‌ها کهنه‌اند.
    """
    old = (datetime.now(UTC) - timedelta(days=60)).strftime("%Y-%m-%d")
    p = _write(tmp_path, {**ITEMS, "updated": old}, age_days=0)
    w = W.stale_warning(p)
    assert w is not None
    assert "کهنه" in w


def test_invalid_updated_field_falls_back_to_mtime(tmp_path) -> None:
    """میدان خراب نباید بشکند — به مهر زمانی برمی‌گردد."""
    p = _write(tmp_path, {**ITEMS, "updated": "خراب"},
               age_days=W.STALE_AFTER_DAYS + 5)
    assert W.stale_warning(p) is not None


# ─────────────────────── فایل غایب ───────────────────────

def test_missing_file_no_warning(tmp_path) -> None:
    """فایل غایب هشدار کهنگی نمی‌گیرد — مسئله دیگری است و جای دیگر گزارش می‌شود."""
    assert W.stale_warning(str(tmp_path / "nope.json")) is None


def test_missing_file_age_is_none(tmp_path) -> None:
    assert W.watch_age_days(str(tmp_path / "nope.json")) is None


def test_malformed_json_falls_back_to_mtime(tmp_path) -> None:
    """فایل خراب نباید بشکند."""
    p = tmp_path / "watch.json"
    p.write_text("{ این JSON نیست", encoding="utf-8")
    old = time.time() - (W.STALE_AFTER_DAYS + 5) * 86_400
    os.utime(p, (old, old))
    assert W.stale_warning(str(p)) is not None


# ─────────────────────── اتصال به run_once ───────────────────────

def test_run_once_prints_warning_when_stale(tmp_path, monkeypatch, capsys) -> None:
    """هشدار باید در خروجی بیاید."""
    p = _write(tmp_path, ITEMS, age_days=W.STALE_AFTER_DAYS + 5)
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(W, "check_item", lambda it, st: [])
    W.run_once({"items": []}, {}, quiet=False, path=p)
    assert "کهنه" in capsys.readouterr().out


def test_run_once_sends_warning_to_telegram(tmp_path, monkeypatch) -> None:
    """هشدار باید به تلگرام هم برود، نه فقط خروجی."""
    p = _write(tmp_path, ITEMS, age_days=W.STALE_AFTER_DAYS + 5)
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    sent = []
    monkeypatch.setattr(W, "notify", lambda msg, quiet=False: sent.append(msg))
    W.run_once({"items": []}, {}, quiet=False, path=p)
    assert any("کهنه" in m for m in sent)


def test_run_once_telegram_warning_once_per_day(tmp_path, monkeypatch) -> None:
    """
    پایش هر چهار ساعت یعنی شش اجرا در روز. هشدار یکسان شش بار در تلگرام
    نویز است — روزی یک بار می‌رود، ولی در خروجی هر بار می‌ماند.
    """
    p = _write(tmp_path, ITEMS, age_days=W.STALE_AFTER_DAYS + 5)
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    sent = []
    monkeypatch.setattr(W, "notify", lambda msg, quiet=False: sent.append(msg))
    state = {}
    for _ in range(6):
        W.run_once({"items": []}, state, quiet=False, path=p)
    assert len([m for m in sent if "کهنه" in m]) == 1


def test_run_once_no_warning_when_fresh(tmp_path, monkeypatch, capsys) -> None:
    """فایل تازه هیچ هشداری تولید نمی‌کند."""
    p = _write(tmp_path, ITEMS, age_days=1)
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    sent = []
    monkeypatch.setattr(W, "notify", lambda msg, quiet=False: sent.append(msg))
    W.run_once({"items": []}, {}, quiet=False, path=p)
    assert not sent
    assert "کهنه" not in capsys.readouterr().out


def test_run_once_missing_file_does_not_crash(tmp_path, monkeypatch) -> None:
    """فایل غایب نباید run_once را بشکند."""
    monkeypatch.setattr(W, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(W, "notify", lambda msg, quiet=False: None)
    assert W.run_once({"items": []}, {}, quiet=True,
                      path=str(tmp_path / "nope.json")) == 0


# ─────────────────────── فایل نمونه ───────────────────────

def test_sample_carries_updated_field() -> None:
    """
    نمونه --init باید میدان updated داشته باشد، وگرنه کاربر تازه هرگز
    از وجودش خبردار نمی‌شود و در رانر هشدار بی‌اثر می‌ماند.
    """
    assert "updated" in W.SAMPLE
