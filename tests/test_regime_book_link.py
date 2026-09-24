"""
آزمون پیوند رژیم و سبد — نشست ۲ نقشه رادار ۷، مورد م۴.

radar_regime.py دو وضعیت می‌سازد که گزارش سبد باید ببیند:
- پوشش کم: regime.json ساخته می‌شود ولی با low_coverage — زیر ۵۰٪ وزن.
- خطای ساخت: فایل معتبر قبلی می‌ماند و فقط last_build_error می‌گیرد؛
  سند خطا فقط وقتی نوشته می‌شود که فایل معتبری نبود.

load_regime به‌جای تاپل یک NamedTuple برمی‌گرداند — score، source،
warnings — تا افزودن میدان بعدی مصرف‌کننده‌ها را نشکند. میدان شناخته‌شده
با شکل نادرست هشدار «نامعتبر» می‌گیرد، نه نادیده‌گرفتن بی‌صدا.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_regime as G

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
STALE = "رژیم کهنه — بازمحاسبه لازم است"


def _write(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def _doc(**extra) -> dict:
    d = {"score": -0.2, "generated_at": (NOW - timedelta(days=1)).isoformat()}
    d.update(extra)
    return d


# ═══════════════ شکل خروجی ═══════════════

def test_returns_named_tuple(tmp_path) -> None:
    r = B.load_regime(_write(tmp_path / "regime.json", _doc()), now=NOW)
    assert isinstance(r, B.RegimeInfo)
    assert B.RegimeInfo._fields == ("score", "source", "warnings")
    assert r.score == -0.2
    assert r.warnings == []


def test_missing_file_has_empty_warnings(tmp_path) -> None:
    r = B.load_regime(tmp_path / "regime.json", now=NOW)
    assert r.score is None and r.warnings == []


# ═══════════════ پوشش کم ═══════════════

def test_low_coverage_warns_with_percent(tmp_path) -> None:
    r = B.load_regime(_write(tmp_path / "regime.json",
                             _doc(coverage=0.42, low_coverage=True)), now=NOW)
    assert r.score == -0.2
    assert any("پوشش کم" in w and "42" in w for w in r.warnings)


def test_normal_coverage_has_no_warning(tmp_path) -> None:
    r = B.load_regime(_write(tmp_path / "regime.json",
                             _doc(coverage=0.8, low_coverage=False)), now=NOW)
    assert r.warnings == []


def test_round_trip_with_regime_builder(tmp_path) -> None:
    """سندی که خود radar_regime می‌سازد، برچسبش در سبد دیده شود."""
    inp = {k: G.Input(key=k, column=c, label=l, weight=G.weights()[k],
                      score=None, reason="غایب")
           for k, (c, l) in G.INPUTS.items()}
    inp["money_price"].score = -1.0
    doc = G.build_doc(G.aggregate(inp), inp, NOW)
    p = tmp_path / "regime.json"
    G.write_json(p, doc)
    r = B.load_regime(p, now=NOW + timedelta(hours=1))
    assert r.score == doc["score"]
    assert any("پوشش کم" in w and "10" in w for w in r.warnings)


# ═══════════════ خطای ساخت ═══════════════

def test_valid_file_with_build_error_keeps_score(tmp_path) -> None:
    """آخرین رژیم معتبر می‌ماند؛ خطا کنارش گفته می‌شود."""
    err = {"at": (NOW - timedelta(hours=2)).isoformat(), "error": "کوین‌گکو پاسخ نداد"}
    r = B.load_regime(_write(tmp_path / "regime.json",
                             _doc(last_build_error=err)), now=NOW)
    assert r.score == -0.2
    assert any("آخرین ساخت رژیم خطا داد" in w and "کوین‌گکو پاسخ نداد" in w
               and "2026-09-25 10:00 UTC" in w for w in r.warnings)


def test_error_doc_is_stale_with_reason(tmp_path) -> None:
    doc = {"generated_at": NOW.isoformat(), "error": "پوشش صفر"}
    r = B.load_regime(_write(tmp_path / "regime.json", doc), now=NOW)
    assert r.score is None
    assert "ساخت رژیم خطا داد" in r.source and "پوشش صفر" in r.source


def test_error_doc_with_score_is_still_stale(tmp_path) -> None:
    """محافظه‌کارانه: سند خطا حتی با امتیاز، امتیاز نمی‌دهد."""
    doc = {"score": 0.8, "generated_at": NOW.isoformat(), "error": "خطا"}
    r = B.load_regime(_write(tmp_path / "regime.json", doc), now=NOW)
    assert r.score is None


def test_stale_by_age_still_reports_build_error(tmp_path) -> None:
    doc = {"score": 0.8,
           "generated_at": (NOW - timedelta(days=9)).isoformat(),
           "last_build_error": {"at": NOW.isoformat(), "error": "شبکه"}}
    r = B.load_regime(_write(tmp_path / "regime.json", doc), now=NOW)
    assert r.score is None
    assert "بیش از ۷ روز" in r.source
    assert any("شبکه" in w for w in r.warnings)


@pytest.mark.parametrize("extra", [
    {"low_coverage": "yes"},
    {"last_build_error": "شبکه"},
    {"last_build_error": {"at": NOW.isoformat()}},
])
def test_malformed_known_field_warns(tmp_path, extra) -> None:
    """میدان شناخته‌شده با شکل نادرست: هشدار «نامعتبر»، نه نادیده‌گرفتن."""
    r = B.load_regime(_write(tmp_path / "regime.json", _doc(**extra)), now=NOW)
    assert r.score == -0.2
    assert any("نامعتبر" in w for w in r.warnings)


# ═══════════════ گزارش سبد — main بدون شبکه ═══════════════

def _book_frame(n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = [{"ts": open_ts - pd.Timedelta(days=n - 1 - i), "o": 100.0 + i,
             "h": 102.0 + i, "l": 98.0 + i, "c": 100.0 + i, "v": 10.0}
            for i in range(n)]
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


@pytest.fixture
def run_book(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "holdings.json", {
        "balance_total": 1000, "stable_usd": 100,
        "positions": [{"symbol": "AAA", "size_usd": 200, "entry": 0,
                       "invalidation": None, "side": "long", "spot": True}]})
    monkeypatch.setattr(B, "candles", lambda *a, **k: _book_frame())

    def run(doc: dict) -> str:
        _write(tmp_path / "regime.json", doc)
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--out", "out.md"])
        assert B.main() == 0
        return (tmp_path / "out.md").read_text(encoding="utf-8")
    return run


def test_report_shows_low_coverage_and_build_error(run_book) -> None:
    now = datetime.now(UTC)
    rep = run_book({"score": -0.2, "generated_at": (now - timedelta(hours=3)).isoformat(),
                    "coverage": 0.42, "low_coverage": True,
                    "last_build_error": {"at": now.isoformat(), "error": "دیفای‌لاما"}})
    row = next(l for l in rep.splitlines() if l.startswith("| هشدار رژیم |"))
    assert "پوشش کم" in row and "دیفای‌لاما" in row
    head = rep.split("## ۱ —")[0]
    assert "پوشش کم" in head and "آخرین ساخت رژیم خطا داد" in head
    assert "محتاط" in next(l for l in rep.splitlines() if l.startswith("| رژیم |"))


def test_report_error_doc_is_stale(run_book) -> None:
    rep = run_book({"generated_at": datetime.now(UTC).isoformat(),
                    "error": "پوشش صفر"})
    assert STALE in rep
    assert "پوشش صفر" in rep
