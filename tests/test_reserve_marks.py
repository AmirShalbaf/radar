"""
علامت «اجراشده» پله‌های نقشه ذخیره — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

منبع حقیقت پر شدن پله همچنان کاهش reserve دفتر کل است — قرار ایستگاه دو.
علامت executed در watch.json برای خواننده است: زمان رسید و شناسه سفارش.
علامتی که دفتر کل پوشش نمی‌دهد هشدار صریح است، نه پله پرشده.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
MARK = {"at": "2026-09-25T22:09:00+00:00", "order_id": "6663fe17-13ce-44a7-927a-fee8784cd6c0"}


def _watch(mark=True) -> dict:
    step1 = {"symbol": "SOL", "qty": 0.749, "price": None}
    if mark:
        step1["executed"] = dict(MARK)
    return {"version": 2, "updated": "2026-09-26T05:04:16+00:00",
            "reserve_plan": {"created": "2026-09-25T16:00:00+00:00",
                             "deadline": "2026-10-05T00:00:00+00:00", "account": "LBank",
                             "steps": [step1, {"symbol": "SOL", "qty": 0.749, "price": 125.5}]},
            "items": []}


def _h(recorded=True) -> dict:
    ledger = [{"at": MARK["at"], "action": "trim", "symbol": "SOL", "delta": -0.749,
               "price": 121.33, "reason": "reserve"}] if recorded else []
    return {"version": 2, "positions": [], "ledger": ledger}


def _run(w, h):
    return W.check_positions(w, h, {}, NOW, weekly=lambda s: (None, ["آزمون"]),
                             price=lambda s: 120.0)


def test_mark_must_have_full_time_and_order_id() -> None:
    w = _watch()
    w["reserve_plan"]["steps"][0]["executed"]["at"] = "2026-09-25"
    with pytest.raises(W.WatchError, match="executed"):
        W.validate_watch(w)
    w = _watch()
    del w["reserve_plan"]["steps"][0]["executed"]["order_id"]
    with pytest.raises(W.WatchError, match="executed"):
        W.validate_watch(w)
    W.validate_watch(_watch())


def test_marked_and_recorded_step_is_silent() -> None:
    msgs = _run(_watch(), _h())
    assert not [m for m in msgs if "پله بازار" in m or "علامت" in m]


def test_mark_without_ledger_row_is_loud() -> None:
    msgs = _run(_watch(), _h(recorded=False))
    assert any("علامت" in m and "دفتر کل" in m and "SOL" in m for m in msgs)


def test_ledger_is_the_truth_not_the_mark() -> None:
    """علامت بدون ردیف دفتر کل پله را پر نمی‌کند — یادآوری پله بازار می‌ماند."""
    msgs = _run(_watch(), _h(recorded=False))
    assert any("پله بازار" in m for m in msgs)
