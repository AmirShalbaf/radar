"""
آزمون هشدار کهنگی داده‌های دستی در گزارش روزانه و تلگرام — نشست ۳، مورد ۷.

holdings.json بیش از ۷ روز و watch.json بیش از ۱۴ روز کهنه است. سن فقط از
میدان updated داخل فایل — زمان تغییر فایل در رانر گیت‌هاب معنا ندارد، چون
checkout به همه فایل‌ها مهر همان لحظه می‌زند. میدان غایب یا نامعتبر یعنی
کهنه، محافظه‌کارانه. بخش تازگی بالای LATEST.md است تا در پیام تلگرام —
سه هزار و پانصد نویسه نخست — هم بیاید.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 6, 30, tzinfo=UTC)
ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"


def _files(tmp_path, h_updated, w_updated):
    hp, wp = tmp_path / "holdings.json", tmp_path / "watch.json"
    h = {"version": 2, "positions": []}
    if h_updated is not None:
        h["updated"] = h_updated
    w = {"items": []}
    if w_updated is not None:
        w["updated"] = w_updated
    hp.write_text(json.dumps(h), encoding="utf-8")
    wp.write_text(json.dumps(w), encoding="utf-8")
    return hp, wp


def _row(rep: str, name: str) -> str:
    return next(l for l in rep.splitlines() if l.startswith(f"| {name}"))


def test_thresholds() -> None:
    assert P.HOLDINGS_STALE_DAYS == 7
    assert W.STALE_AFTER_DAYS == 14


def test_fresh_files(tmp_path) -> None:
    hp, wp = _files(tmp_path, (NOW - timedelta(days=6)).isoformat(),
                    (NOW - timedelta(days=13)).strftime("%Y-%m-%d"))
    rep, stale = W.staleness_report(str(hp), str(wp), NOW)
    assert not stale
    assert "✅" in _row(rep, "holdings.json") and "✅" in _row(rep, "watch.json")


def test_stale_holdings_and_watch(tmp_path) -> None:
    hp, wp = _files(tmp_path, (NOW - timedelta(days=8)).isoformat(),
                    (NOW - timedelta(days=15)).strftime("%Y-%m-%d"))
    rep, stale = W.staleness_report(str(hp), str(wp), NOW)
    assert stale
    assert "⚠️" in _row(rep, "holdings.json") and "8.0" in _row(rep, "holdings.json")
    assert "⚠️" in _row(rep, "watch.json")


def test_missing_field_is_stale_even_if_mtime_fresh(tmp_path) -> None:
    hp, wp = _files(tmp_path, None, "نه-تاریخ")
    now_ts = NOW.timestamp()
    os.utime(hp, (now_ts, now_ts))
    os.utime(wp, (now_ts, now_ts))
    rep, stale = W.staleness_report(str(hp), str(wp), NOW)
    assert stale
    assert "نامعتبر" in _row(rep, "holdings.json")
    assert "نامعتبر" in _row(rep, "watch.json")


def test_missing_file_is_reported(tmp_path) -> None:
    rep, stale = W.staleness_report(str(tmp_path / "no.json"), str(tmp_path / "no2.json"), NOW)
    assert stale
    assert "فایل نیست" in rep


def test_cli_prints_report(tmp_path, capsys) -> None:
    hp, wp = _files(tmp_path, datetime.now(UTC).isoformat(),
                    datetime.now(UTC).strftime("%Y-%m-%d"))
    assert W.main(["--staleness", "--holdings", str(hp), "--watch", str(wp)]) == 0
    assert "holdings.json" in capsys.readouterr().out


def test_latest_has_staleness_near_top() -> None:
    text = DAILY.read_text(encoding="utf-8")
    start = text.index("- name: ساخت خلاصه امروز\n")
    step = text[start:text.find("\n      - name:", start + 1)]
    assert "python radar_watch.py --staleness" in step
    assert step.index("radar_watch.py --staleness") < step.index("## فایل‌های امروز")
    assert "|| true" not in step
