"""
رکورد تصمیم بی‌معامله در دفترچه — مرور هفتگی ۱۷ اکتبر ۲۰۲۶، RD-20261017-01.

چارچوب رادار ۷ بند ۱۰.۱: هر تحلیلی که به حکم می‌رسد شناسه RD-YYYYMMDD-NN می‌گیرد
و در دفترچه باز می‌شود، با «تصمیم انسان: پیروی یا سرپیچی». قرارداد بند ۴:
سرپیچی با برچسب جدا ثبت می‌شود تا پس از بیست مورد سنجیده شود.

تا امروز `add` فقط معامله ثبت می‌کرد — ورود، استاپ و حجم اجباری. تصمیمی مثل
افزایش ذخیره ستاپ ورود ندارد. ثبتش با `add` یعنی عدد ساختگی، و شمارنده بیست
معامله — قاعده سخت ۳ — را هم پر می‌کرد. پس فرمان جدا `decide` و فهرست جدا
`decisions`؛ `trades` دست نمی‌خورد.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_journal as RJ

BASE = ["radar_journal.py", "decide", "--decision-id", "RD-20261017-01",
        "--at", "2026-10-17T15:32:00+00:00", "--action", "افزایش ذخیره",
        "--symbols", "BNB,ETH", "--verdict", "فروش برای ذخیره — ترتیب بخش ۵",
        "--human", "followed"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / RJ.DB_NAME
    monkeypatch.setattr(RJ, "DB", str(p))
    return p


def _run(monkeypatch, argv) -> int:
    monkeypatch.setattr(sys, "argv", argv)
    try:
        return RJ.main()
    except SystemExit as exc:
        return exc.code


def test_decision_recorded_apart_from_trades(db, monkeypatch) -> None:
    assert _run(monkeypatch, BASE + ["--regime", "-0.426", "--band", "محتاط",
                                     "--note", "یادداشت"]) == 0
    d = RJ.load()
    assert d["trades"] == []
    r = d["decisions"][0]
    assert r["decision_id"] == "RD-20261017-01"
    assert r["at"] == "2026-10-17T15:32:00+00:00"
    assert r["action"] == "افزایش ذخیره" and r["symbols"] == ["BNB", "ETH"]
    assert r["setup_name"] == RJ.NO_SETUP
    assert r["human"] == "followed" and r["regime_score"] == -0.426
    assert r["regime_band"] == "محتاط" and r["note"] == "یادداشت"


def test_defied_is_its_own_label(db, monkeypatch) -> None:
    argv = [x if x != "followed" else "defied" for x in BASE]
    assert _run(monkeypatch, argv) == 0
    assert RJ.load()["decisions"][0]["human"] == "defied"


def test_human_label_is_closed_set(db, monkeypatch) -> None:
    argv = [x if x != "followed" else "maybe" for x in BASE]
    assert _run(monkeypatch, argv) == 2
    assert not db.exists()


@pytest.mark.parametrize("bad", ["RD-2026101701", "RD-20261017-1", "D-2026-10-17-1",
                                 "RD-۲۰۲۶۱۰۱۷-۰۱", "RD-20261018-01"])
def test_decision_id_format_and_date(db, monkeypatch, bad) -> None:
    """قالب اسکی؛ و تاریخ شناسه همان تاریخ وقت جهانی --at."""
    argv = list(BASE)
    argv[argv.index("RD-20261017-01")] = bad
    assert _run(monkeypatch, argv) == 2
    assert not db.exists()


def test_at_needs_timezone(db, monkeypatch) -> None:
    argv = list(BASE)
    argv[argv.index("2026-10-17T15:32:00+00:00")] = "2026-10-17T15:32:00"
    assert _run(monkeypatch, argv) == 2


def test_decision_id_is_unique(db, monkeypatch) -> None:
    assert _run(monkeypatch, BASE) == 0
    assert _run(monkeypatch, BASE) == 2
    assert len(RJ.load()["decisions"]) == 1


def test_decision_id_not_reused_from_trade(db, monkeypatch) -> None:
    db.write_text(json.dumps({"version": 1, "trades": [
        {"id": 1, "symbol": "ZEC", "status": "closed", "decision_id": "RD-20261017-01"}]}),
        encoding="utf-8")
    assert _run(monkeypatch, BASE) == 2


def test_report_counts_decisions_and_defiance(db, monkeypatch, capsys) -> None:
    _run(monkeypatch, BASE)
    argv = [x if x != "followed" else "defied" for x in BASE]
    argv[argv.index("RD-20261017-01")] = "RD-20261017-02"
    _run(monkeypatch, argv)
    capsys.readouterr()
    _run(monkeypatch, ["radar_journal.py", "report"])
    out = capsys.readouterr().out
    sec = out[out.index("## تصمیم‌های بی‌معامله"):]
    assert "| پیروی | 1 |" in sec and "| سرپیچی | 1 |" in sec
    assert "RD-20261017-02" in sec


def test_report_without_decisions_unchanged(db, monkeypatch, capsys) -> None:
    _run(monkeypatch, ["radar_journal.py", "report"])
    assert "تصمیم‌های بی‌معامله" not in capsys.readouterr().out
