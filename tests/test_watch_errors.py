"""
آزمون خطای بلند پایشگر — نشست ۳، مورد ۷-ج، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

پیش از این:
- load_json خطای خواندن را با except Exception: pass می‌بلعید. watch.json خراب
  یعنی فهرست خالی — پایشگر بی‌صدا هیچ چیز را نمی‌پایید.
- گام نبض `python radar_watch.py --once ... || true` بود. پایشگر که می‌افتاد،
  نه هشدار ابطال می‌آمد و نه خطا.
حالا هر دو بلندند. گام نبض متوقف نمی‌شود تا watch_state.json ثبت شود، ولی
::error:: می‌دهد و پایشگر افتاده خودش به تلگرام خبر می‌دهد.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
PULSE = ROOT / ".github" / "workflows" / "radar-pulse.yml"


@pytest.fixture
def sent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    msgs: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: msgs.append(m))
    return msgs


def test_missing_file_gives_default(tmp_path) -> None:
    assert W.load_json(str(tmp_path / "no.json"), {"a": 1}) == {"a": 1}


def test_corrupt_file_raises(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(W.WatchError):
        W.load_json(str(p), {})


def test_corrupt_watch_is_loud(tmp_path, sent) -> None:
    (tmp_path / "watch.json").write_text("{not json", encoding="utf-8")
    assert W.main(["--once", "--watch", "watch.json"]) == 2
    assert any("watch.json" in m and "خوانا نیست" in m for m in sent)


def test_corrupt_state_is_loud_but_runs(tmp_path, sent) -> None:
    (tmp_path / "watch.json").write_text(json.dumps({"updated": "2026-09-26", "items": []}),
                                         encoding="utf-8")
    (tmp_path / W.STATE_FILE).write_text("{not json", encoding="utf-8")
    assert W.main(["--once", "--watch", "watch.json"]) == 3
    assert any(W.STATE_FILE in m for m in sent)
    assert json.loads((tmp_path / W.STATE_FILE).read_text(encoding="utf-8")) is not None


def test_crash_notifies_and_reraises(tmp_path, sent, monkeypatch) -> None:
    (tmp_path / "watch.json").write_text(json.dumps({"updated": "2026-09-26", "items": []}),
                                         encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("آزمون")
    monkeypatch.setattr(W, "run_once", boom)
    with pytest.raises(RuntimeError):
        W.run_cli(["--once", "--watch", "watch.json"])
    assert any("پایشگر" in m and "افتاد" in m for m in sent)


def _step(name: str) -> str:
    text = PULSE.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_pulse_watch_step_is_loud() -> None:
    step = _step("پایش زنده سطوح")
    assert "|| true" not in step
    assert "::error::" in step
    assert "python radar_watch.py --once" in step


def test_entry_point_is_loud_wrapper() -> None:
    src = (ROOT / "radar_watch.py").read_text(encoding="utf-8")
    assert "sys.exit(run_cli())" in src
