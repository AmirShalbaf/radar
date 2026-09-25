"""
خروج جزئی با ابطال در دفتر کل — نشست ۳، مورد ۷-ج، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

سهم خروج با ابطال در watch.json پارامتر است (پیش‌فرض ۱.۰). تا تصمیم نهایی
فقط یک عدد باشد، دفتر کل باید خروج جزئی را هم بپذیرد:
- trim با دلیل invalidation، با سطح اجباری؛
- سهمیه ورود دوباره مقدار خروج جزئی را هم می‌شمارد؛
- exit بعدی با همان سطح به سهمیه اضافه می‌شود، جایگزینش نمی‌کند.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc)


def _h(ledger=None, sol=6.0, status="open") -> dict:
    return {"version": 2, "updated": NOW.isoformat(), "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0}},
            "cash": [], "ledger": ledger or [],
            "positions": [{"symbol": "SOL", "book": "position", "status": status,
                           "invalidation": 96.7,
                           "lots": [{"qty": sol, "account": "A", "entry": None}] if sol else []}]}


def _row(action, delta, **extra) -> dict:
    return {"at": NOW.isoformat(), "action": action, "symbol": "SOL", "delta": delta, **extra}


def test_invalidation_is_a_trim_reason() -> None:
    assert "invalidation" in P.TRIM_REASONS


def test_partial_invalidation_trim_needs_level() -> None:
    h = _h([_row("trim", -3.0, price=95.0, reason="invalidation")], sol=3.0)
    with pytest.raises(P.PositionsError, match="سطح"):
        P.validate(h, {"version": 1, "trades": []})


def test_partial_trim_gives_reentry_allowance() -> None:
    h = _h([_row("trim", -3.0, price=95.0, reason="invalidation", level=96.7)], sol=3.0)
    P.validate(h, {"version": 1, "trades": []})
    st = P.reentry_state(h, "SOL")
    assert st["level"] == 96.7 and st["max_qty"] == 3.0 and st["used"] == 0.0


def test_exit_after_partial_adds_to_allowance() -> None:
    h = _h([_row("trim", -3.0, price=95.0, reason="invalidation", level=96.7),
            _row("exit", -3.0, price=93.0, level=96.7, reason="invalidation")],
           sol=0.0, status="exited")
    P.validate(h, {"version": 1, "trades": []})
    assert P.reentry_state(h, "SOL")["max_qty"] == 6.0


def test_reserve_trim_gives_no_allowance() -> None:
    h = _h([_row("trim", -1.0, price=120.0, reason="reserve")], sol=5.0)
    P.validate(h, {"version": 1, "trades": []})
    assert P.reentry_state(h, "SOL") is None


@pytest.fixture
def files(tmp_path):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps({"version": 1, "trades": []}), encoding="utf-8")
    return hp, jp


def _run(files, *args) -> int:
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"), *args])


def test_cli_partial_invalidation_trim(files) -> None:
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "3", "--price", "95",
                "--reason", "invalidation") == 2              # بدون سطح: خطا
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "3", "--price", "95",
                "--reason", "invalidation", "--level", "96.7") == 0
    h = json.loads(files[0].read_text(encoding="utf-8"))
    assert h["ledger"][-1]["level"] == 96.7
    assert h["positions"][0]["status"] == "open"
    oc = json.loads((files[0].parent / "optcost.json").read_text(encoding="utf-8"))
    assert oc["exits"][-1]["level"] == 96.7
