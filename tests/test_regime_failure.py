"""
آزمون رفتار خطای ساخت رژیم — نشست ۲ نقشه رادار ۷، مورد م۵.

تصمیم: اگر ساخت رژیم خطا داد، regime.json معتبر قبلی بازنویسی نمی‌شود.
آخرین رژیم معتبر می‌ماند و قاعده عمر هفت‌روزه سبد خودش کهنگی را می‌سنجد.
خطا با میدان last_build_error همراه زمانش در همان فایل ثبت می‌شود و سبد
آن را کنار رژیم نشان می‌دهد. فقط اگر فایل معتبری نبود — غایب، خراب، یا
خودش سند خطا — سند خطا نوشته می‌شود.

«معتبر» یعنی ساختار درست — score متناهی و generated_at با منطقه زمانی —
نه تازگی. فایل معتبر ولی کهنه هم نگه داشته می‌شود؛ کهنگی کار سبد است.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_fetch3 as R
import radar_regime as G

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 6, 30, tzinfo=UTC)


def _valid(age_days: float = 1.0, **extra) -> dict:
    d = {"score": -0.2, "generated_at": (NOW - timedelta(days=age_days)).isoformat(),
         "coverage": 0.8, "low_coverage": False, "band": {"name": "محتاط"}}
    d.update(extra)
    return d


def _write(p: Path, obj) -> Path:
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ═══════════════ record_build_error ═══════════════

def test_valid_file_is_kept_and_marked(tmp_path) -> None:
    p = _write(tmp_path / "regime.json", _valid())
    before = _read(p)
    G.record_build_error(p, "پوشش صفر", NOW)
    after = _read(p)
    assert after["score"] == before["score"]
    assert after["generated_at"] == before["generated_at"]
    assert after["band"] == before["band"]
    assert after["last_build_error"] == {"at": NOW.isoformat(), "error": "پوشش صفر"}


def test_valid_but_old_file_is_still_kept(tmp_path) -> None:
    """کهنگی کار سبد است، نه دلیل بازنویسی."""
    p = _write(tmp_path / "regime.json", _valid(age_days=9))
    G.record_build_error(p, "شبکه", NOW)
    assert _read(p)["score"] == -0.2


@pytest.mark.parametrize("content", [
    None,                                         # فایل نیست
    "{not json",                                  # خراب
    json.dumps({"generated_at": NOW.isoformat(), "error": "قبلی"}),  # سند خطا
    json.dumps({"score": -0.2, "generated_at": "2026-09-24T00:00:00"}),  # بی‌منطقه
])
def test_no_valid_file_gets_error_doc(tmp_path, content) -> None:
    p = tmp_path / "regime.json"
    if content is not None:
        p.write_text(content, encoding="utf-8")
    G.record_build_error(p, "پوشش صفر", NOW)
    doc = _read(p)
    assert doc["error"] == "پوشش صفر"
    assert doc["generated_at"] == NOW.isoformat()
    assert "score" not in doc


# ═══════════════ main بدون شبکه ═══════════════

@pytest.fixture
def paths(tmp_path):
    return tmp_path / "regime.json", tmp_path / "hist.json", tmp_path / "r.md"


def _argv(paths, *extra) -> list[str]:
    j, h, r = paths
    return ["--json", str(j), "--history", str(h), "--report", str(r), *extra]


@pytest.fixture
def empty_net(monkeypatch):
    """هیچ منبعی پاسخ نمی‌دهد — پوشش صفر."""
    monkeypatch.setattr(R, "fetch_fred", lambda http_text: {"raw": {}, "derived": {}})
    monkeypatch.setattr(R, "fetch_macro", lambda out: None)
    monkeypatch.setattr(R, "probe_venues", lambda order: (list(order), []))
    monkeypatch.setattr(R, "candles_first_ok", lambda *a, **k: ({}, None, None))
    monkeypatch.setattr(R, "FAILURES", [])


def test_main_failure_keeps_previous_valid_regime(empty_net, paths) -> None:
    j, h, _ = paths
    _write(j, _valid(age_days=0.5))
    _write(h, {"version": 1, "days": {"2026-09-24": {"score": -0.2}}})
    hist_before = h.read_text(encoding="utf-8")
    assert G.main(_argv(paths)) != 0
    doc = _read(j)
    assert doc["score"] == -0.2
    assert "پوشش صفر" in doc["last_build_error"]["error"]
    assert h.read_text(encoding="utf-8") == hist_before     # تاریخچه دست نخورد
    info = B.load_regime(j)
    assert info.score == -0.2
    assert any("آخرین ساخت رژیم خطا داد" in w for w in info.warnings)


def test_main_failure_without_valid_file_writes_error_doc(empty_net, paths) -> None:
    j = paths[0]
    assert G.main(_argv(paths)) != 0
    info = B.load_regime(j)
    assert info.score is None
    assert "ساخت رژیم خطا داد" in info.source


def test_main_unexpected_exception_is_recorded(monkeypatch, paths, capsys) -> None:
    """خطای پیش‌بینی‌نشده هم ثبت می‌شود و ردش چاپ می‌شود — بی‌صدا نه."""
    def boom(order):
        raise RuntimeError("انفجار آزمایشی")
    monkeypatch.setattr(G, "gather", boom)
    j = paths[0]
    _write(j, _valid(age_days=0.5))
    assert G.main(_argv(paths)) != 0
    assert "RuntimeError" in _read(j)["last_build_error"]["error"]
    assert "Traceback" in capsys.readouterr().err


def test_main_stdout_failure_writes_nothing(empty_net, paths) -> None:
    j = paths[0]
    assert G.main(_argv(paths, "--stdout")) != 0
    assert not j.exists()


def test_success_after_failure_clears_the_mark(monkeypatch, paths) -> None:
    j = paths[0]
    _write(j, _valid(last_build_error={"at": NOW.isoformat(), "error": "دیروز"}))
    inp = {k: G.Input(key=k, column=c, label=l, weight=G.weights()[k], score=0.1)
           for k, (c, l) in G.INPUTS.items()}
    monkeypatch.setattr(G, "gather", lambda order: {})
    monkeypatch.setattr(G, "measure", lambda src, history, now: inp)
    assert G.main(_argv(paths)) == 0
    assert "last_build_error" not in _read(j)
