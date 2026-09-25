"""
قاعده تغییر سطح ابطال — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

سطح ابطال دفتر موقعیت فقط در بازبینی هفتگی عوض می‌شود. گزارش روزانه سطوح
فقط اطلاع است و watch.json را تغییر نمی‌دهد. دلیل: بازمحاسبه ایستگاه دو
نشان داد انتخاب سطح به لحظه قیمت وابسته است — AAVE و TAO در چهار ساعت
سطح تازه گرفتند. سطحی که با هر اجرا جابه‌جا شود، سطح ابطال نیست.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_levels as L
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"


def _step(name: str) -> str:
    text = DAILY.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_levels_report_says_information_only() -> None:
    rep = L.report([], 2.0)
    assert "فقط اطلاع" in rep
    assert "بازبینی هفتگی" in rep and "watch.json" in rep


def test_levels_run_does_not_touch_watch_or_holdings(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    files = {"watch.json": '{"updated": "2026-09-26", "positions": []}',
             "holdings.json": '{"version": 2}'}
    for n, c in files.items():
        (tmp_path / n).write_text(c, encoding="utf-8")
    monkeypatch.setattr(L, "okx_candles", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["radar_levels.py", "--watchlist", "SOL",
                                      "--out", "levels.md"])
    assert L.main() == 0
    for n, c in files.items():
        assert (tmp_path / n).read_text(encoding="utf-8") == c
    assert (tmp_path / "levels.md").exists()


def test_daily_workflow_never_writes_watch_or_holdings() -> None:
    assert "watch.json" not in _step("سطوح ساختاری سبد")
    commit = _step("کامیت گزارش‌ها")
    for line in commit.splitlines():
        if "git add" in line:
            assert "watch.json" not in line and "holdings.json" not in line


def test_watcher_never_rewrites_watch_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "watch.json"
    body = json.dumps({"updated": "2026-09-26", "items": []})
    p.write_text(body, encoding="utf-8")
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: None)
    W.run_once(json.loads(body), {}, quiet=True, path=str(p))
    assert p.read_text(encoding="utf-8") == body
