"""
آزمون میدان book در دفترچه — نشست ۳ نقشه رادار ۷، مورد ۱-۱.

تصمیم «دو دفتر» (۲۵ سپتامبر ۲۰۲۶): هر معامله تازه در دفتر معامله است؛
افزودن به دفتر موقعیت فقط با شناسه تصمیم و نام ستاپی که در دفترچه با
book = position ثبت شده باشد. قاعده ضدبهانه: شناسه‌ای که در دفترچه
book = trade دارد هرگز به دفتر موقعیت نمی‌رود — radar_positions.py این را
از همین میدان می‌خواند.

رکورد قدیمی بدون این میدان trade خوانده می‌شود — همان الگوی میدان paper:
پیش‌فرضی که معنای رکورد قدیمی را حفظ می‌کند.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_journal as RJ

BASE = ["radar_journal.py", "add", "--symbol", "TST", "--side", "long",
        "--entry", "100", "--stop", "90", "--size", "100",
        "--setup-name", "الف۱", "--decision-id", "D-2026-09-25-1"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / RJ.DB_NAME
    monkeypatch.setattr(RJ, "DB", str(p))
    return p


def _add(monkeypatch, *extra) -> dict:
    monkeypatch.setattr(sys, "argv", BASE + list(extra))
    RJ.main()
    return RJ.load()["trades"][-1]


def test_books_constant() -> None:
    assert RJ.BOOKS == ("trade", "position")


def test_default_book_is_trade(db, monkeypatch) -> None:
    assert _add(monkeypatch)["book"] == "trade"


def test_position_book_is_recorded(db, monkeypatch) -> None:
    assert _add(monkeypatch, "--book", "position")["book"] == "position"


def test_invalid_book_is_rejected(db, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", BASE + ["--book", "hold"])
    with pytest.raises(SystemExit):
        RJ.main()


def test_legacy_record_reads_as_trade(db) -> None:
    db.write_text(json.dumps({"version": 1, "trades": [
        {"id": 1, "symbol": "ZEC", "status": "closed"}]}), encoding="utf-8")
    assert RJ.load()["trades"][0]["book"] == "trade"


def test_load_accepts_explicit_path(tmp_path) -> None:
    """radar_positions.py دفترچه را از مسیر صریح می‌خواند، نه از متغیر سراسری."""
    p = tmp_path / "other.json"
    p.write_text(json.dumps({"version": 1, "trades": [
        {"id": 7, "symbol": "SOL", "book": "position",
         "decision_id": "D-1", "setup_name": "الف۲"}]}), encoding="utf-8")
    t = RJ.load(str(p))["trades"][0]
    assert t["book"] == "position" and t["decision_id"] == "D-1"


def test_real_journal_still_valid() -> None:
    """رکورد واقعی زی‌کش بی‌تغییر معتبر می‌ماند و trade خوانده می‌شود."""
    t = RJ.load()["trades"][0]
    assert t["symbol"] == "ZEC" and t["book"] == "trade"
