"""
آزمون خروج‌ها و کاهش‌های دفتر موقعیت در دفتر هزینه فرصت — نشست ۳، مورد ۱-۳.

تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶: هر خروج با ابطال، و هر کاهش (trim) برای
ذخیره یا بازتوازن، در دفتر هزینه فرصت ثبت شود. پیگیری ۱۴ و ۳۰ روزه نشان
می‌دهد فروش کمک کرده یا نه — و هزینه ساختن ذخیره هم سنجیده می‌شود.

«کمک کرد» یعنی قیمت پس از فروش پایین‌تر بوده؛ دلار جلوگیری‌شده =
مقدار × (قیمت فروش − قیمت بعدی). مثبت یعنی فروش ضرر را کم کرد.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_optcost as RO
import radar_positions as P

UTC = timezone.utc


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "radar_optcost.json"
    monkeypatch.setattr(RO, "FILE", str(p))
    return p


def test_old_file_without_exits_still_loads(db) -> None:
    db.write_text(json.dumps({"rejects": [], "sessions": []}), encoding="utf-8")
    assert RO.load()["exits"] == []


def test_add_exit_record_fields() -> None:
    d = {"rejects": [], "sessions": [], "exits": []}
    r = RO.add_exit(d, symbol="SOL", action="exit", qty=6.0, price=95.0,
                    reason="invalidation", level=100.0)
    assert r["id"] == 1 and r["symbol"] == "SOL" and r["action"] == "exit"
    assert r["level"] == 100.0 and r["book"] == "position"
    for k in ("p14", "p30", "chg14", "chg30", "saved14", "saved30"):
        assert r[k] is None


def _bars(start: datetime, prices: dict) -> list[dict]:
    """کندل روزانه مصنوعی: کلید روز پس از فروش، مقدار بسته."""
    return [{"ts": int((start + timedelta(days=k)).timestamp() * 1000),
             "h": v, "l": v, "c": v} for k, v in sorted(prices.items())]


def test_followup_fills_14_and_30_days(db, monkeypatch) -> None:
    start = datetime.now(UTC) - timedelta(days=31)
    d = {"rejects": [], "sessions": [], "exits": []}
    r = RO.add_exit(d, symbol="SOL", action="trim", qty=2.0, price=100.0,
                    reason="reserve")
    r["date"] = start.strftime("%Y-%m-%d")
    RO.save(d)
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: _bars(
        start.replace(hour=0, minute=0, second=0, microsecond=0),
        {0: 100.0, 14: 90.0, 30: 110.0}))
    RO.cmd_followup(None)
    r = RO.load()["exits"][0]
    assert r["p14"] == 90.0 and r["p30"] == 110.0
    assert r["chg14"] == pytest.approx(-10.0)
    assert r["saved14"] == pytest.approx(20.0)       # فروش در ۱۴ روز کمک کرد
    assert r["saved30"] == pytest.approx(-20.0)      # در ۳۰ روز هزینه داشت


def test_followup_waits_before_14_days(db, monkeypatch) -> None:
    d = {"rejects": [], "sessions": [], "exits": []}
    RO.add_exit(d, symbol="SOL", action="exit", qty=6.0, price=95.0,
                reason="invalidation", level=100.0)
    RO.save(d)
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: _bars(
        datetime.now(UTC), {0: 95.0}))
    RO.cmd_followup(None)
    assert RO.load()["exits"][0]["p14"] is None


def test_report_has_exits_section(db, capsys) -> None:
    d = {"rejects": [], "sessions": [], "exits": []}
    a = RO.add_exit(d, symbol="SOL", action="trim", qty=2.0, price=100.0, reason="reserve")
    a.update(p14=90.0, chg14=-10.0, saved14=20.0)
    RO.add_exit(d, symbol="TAO", action="exit", qty=0.15, price=280.0,
                reason="invalidation", level=290.0)
    RO.save(d)
    RO.cmd_report(type("A", (), {"out": None})())
    out = capsys.readouterr().out
    assert "خروج و کاهش دفتر موقعیت" in out
    assert "SOL" in out and "TAO" in out
    assert "در انتظار" in out                       # TAO هنوز پیگیری ندارد


# ═══════════════ سیم‌کشی به radar_positions ═══════════════

NOW = datetime(2026, 9, 25, 5, 15, tzinfo=UTC)


def _h() -> dict:
    return {"version": 2, "updated": NOW.isoformat(), "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0}},
            "cash": [], "ledger": [],
            "positions": [{"symbol": "SOL", "book": "position", "status": "open",
                           "lots": [{"qty": 6.0, "account": "A", "entry": None}],
                           "invalidation": None}]}


@pytest.fixture
def files(tmp_path, db):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps({"version": 1, "trades": []}), encoding="utf-8")
    return hp, jp, db


def _run(files, *args) -> int:
    hp, jp, db = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(db), *args])


def test_positions_trim_records_optcost(files) -> None:
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "1.5", "--price", "120",
                "--reason", "reserve") == 0
    ex = RO.load()["exits"]
    assert len(ex) == 1
    assert (ex[0]["action"], ex[0]["reason"], ex[0]["qty"], ex[0]["price"]) == \
        ("trim", "reserve", 1.5, 120.0)


def test_positions_exit_records_optcost_with_level(files) -> None:
    assert _run(files, "exit", "--symbol", "SOL", "--price", "95", "--level", "100") == 0
    ex = RO.load()["exits"][0]
    assert ex["action"] == "exit" and ex["level"] == 100.0 and ex["qty"] == 6.0
    assert ex["reason"] == "invalidation"


def test_positions_adjust_does_not_record(files) -> None:
    assert _run(files, "adjust", "--symbol", "SOL", "--qty", "0.03",
                "--reason", "پاداش سهام‌گذاری") == 0
    assert RO.load()["exits"] == []


def test_refused_command_records_nothing(files) -> None:
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "9", "--price", "120",
                "--reason", "reserve") != 0
    assert RO.load()["exits"] == []
