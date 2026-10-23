"""
ورود دوباره فقط با بسته هفتگی پس از خروج — بازبینی عمیق ۲۳ اکتبر ۲۰۲۶، یافته ت۲.

پیش از این هیچ‌جا سنجیده نمی‌شد که بسته هفتگی پس از خروج آمده باشد. آزمون
tests/test_positions.py:515 خروجِ «اکنون» را با بسته ۲۱ سپتامبر دوباره وارد می‌کرد و
سبز بود. سناریو، استدلال: بسته زیر سطح، خروج دیر ثبت می‌شود — پس از بسته بعدی که
بالای سطح است — و پایشگر بلافاصله «ورود دوباره مجاز» می‌گوید؛ دو کارمزد بی هیچ
اطلاع تازه.

قرارداد: بسته‌ای که ورود دوباره را مجاز می‌کند باید **اکیداً پس از** زمان آخرین
خروج با همان سطح بسته شده باشد — exit یا trim با دلیل invalidation. یک تعریف:
دفتر کل، فرمان reenter، پایشگر و سبد.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_positions as P
import radar_watch as W

UTC = timezone.utc
EXIT_AT = "2026-10-27T09:00:00+00:00"
BEFORE = "2026-10-26T00:00:00+00:00"          # بسته‌ای که خروج را ساخت
AFTER = "2026-11-02T00:00:00+00:00"


def _h(ledger=None, sol=0.0) -> dict:
    return {"version": 2, "updated": "2026-10-27T09:10:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0}, "cash": []},
            "cash": [], "ledger": ledger if ledger is not None else [_exit()],
            "positions": [{"symbol": "SOL", "book": "position",
                           "status": "open" if sol else "exited", "invalidation": 96.71,
                           "invalidation_since": "2026-09-25T21:34:47+00:00",
                           "lots": [{"qty": sol, "account": "A", "entry": 99.0}] if sol else []}]}


def _exit(at=EXIT_AT) -> dict:
    return {"at": at, "action": "exit", "symbol": "SOL", "delta": -6.0, "price": 95.0,
            "level": 96.71, "reason": "invalidation", "no_receipt": True}


def _reenter(closed_at, qty=4.0) -> dict:
    return {"at": "2026-11-02T06:00:00+00:00", "action": "reenter", "symbol": "SOL",
            "delta": qty, "price": 99.0, "weekly_close": 98.0, "week_close_at": closed_at}


J = {"version": 1, "trades": []}


# ═══════════════ دفتر کل ═══════════════

def test_state_carries_last_exit_time() -> None:
    st = P.reentry_state(_h(), "SOL")
    assert st["exit_at"] == EXIT_AT and st["level"] == 96.71


def test_latest_exit_of_same_level_counts() -> None:
    trim = {"at": "2026-10-20T08:00:00+00:00", "action": "trim", "symbol": "SOL",
            "delta": -3.0, "price": 95.0, "reason": "invalidation", "level": 96.71,
            "no_receipt": True}
    ex = dict(_exit(), delta=-3.0)
    st = P.reentry_state(_h(ledger=[trim, ex]), "SOL")
    assert st["exit_at"] == EXIT_AT and st["max_qty"] == 6.0


@pytest.mark.parametrize("closed_at", [BEFORE, EXIT_AT])
def test_reenter_row_with_close_not_after_exit_is_error(closed_at) -> None:
    h = _h(ledger=[_exit(), _reenter(closed_at)], sol=4.0)
    with pytest.raises(P.PositionsError, match="پس از خروج"):
        P.validate(h, J)


def test_reenter_row_with_close_after_exit_passes() -> None:
    P.validate(_h(ledger=[_exit(), _reenter(AFTER)], sol=4.0), J)


# ═══════════════ فرمان ═══════════════

@pytest.fixture
def files(tmp_path):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(J), encoding="utf-8")
    return hp, jp


def _cli(files, monkeypatch, closed_at) -> int:
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (
        {"close": 98.0, "closed_at": closed_at, "venue": "okx"}, []))
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"),
                   "reenter", "--symbol", "SOL", "--qty", "4", "--price", "99", "--account", "A"])


def test_cli_refuses_close_before_exit(files, monkeypatch, capsys) -> None:
    before = files[0].read_text(encoding="utf-8")
    assert _cli(files, monkeypatch, BEFORE) == 2
    assert files[0].read_text(encoding="utf-8") == before
    assert "پس از خروج" in capsys.readouterr().err


def test_cli_accepts_close_after_exit(files, monkeypatch) -> None:
    assert _cli(files, monkeypatch, AFTER) == 0
    row = json.loads(files[0].read_text(encoding="utf-8"))["ledger"][-1]
    assert row["action"] == "reenter" and row["week_close_at"] == AFTER


# ═══════════════ پایشگر و سبد ═══════════════

def _watch_msgs(closed_at) -> list[str]:
    weekly = lambda s: ({"close": 98.0, "closed_at": closed_at, "venue": "okx",
                         "week_open": "2026-10-19T00:00:00+00:00"}, [])
    return W.check_positions({"positions": []}, _h(), {}, datetime(2026, 11, 2, 5, tzinfo=UTC),
                             weekly=weekly, price=lambda s: 98.0)


def test_watch_silent_on_close_before_exit() -> None:
    assert not [m for m in _watch_msgs(BEFORE) if "ورود دوباره مجاز" in m]


def test_watch_allows_on_close_after_exit() -> None:
    assert [m for m in _watch_msgs(AFTER) if "ورود دوباره مجاز" in m]


def _book(closed_at) -> str:
    h = _h()
    st = P.reentry_state(h, "SOL")
    entry = {"symbol": "SOL", "state": st, "weekly": {"close": 98.0, "closed_at": closed_at},
             "why": []}
    return B.build_report(h, [], None, [], "آزمون", reentry=[entry])


def test_book_waits_for_close_after_exit() -> None:
    txt = _book(BEFORE)
    assert "منتظر بسته پس از خروج" in txt and "ورود دوباره مجاز است" not in txt


def test_book_allows_after_exit() -> None:
    txt = _book(AFTER)
    assert "✅ ورود دوباره مجاز" in txt and "ورود دوباره مجاز است" in txt
