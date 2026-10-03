"""
پله دوم ETH نقشه ذخیره، فروش محدود واقعی LBank — ۲ اکتبر ۲۰۲۶.

از رسید: محدود، 0.0472 در 2755.00، مجموع 130.036، کارمزد 0.130036، سازنده
(Maker)، سفارش ccb9052a-ce7b-4d51-8834-feecf67c83e1. زمان پرشدن 11:47:19
تهران، یعنی 08:17:19 UTC. زمان بالای رسید، 2026-09-27 13:50:41 تهران، زمان
گذاشتن سفارش است، نه پرشدن — ثبت با آن، پیگیری هزینه فرصت را پنج روز جابه‌جا
می‌کرد. خالص 129.905964 تتر به نقد LBank. قفل داده است.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
SALE = {"at": "2026-10-02T08:17:19+00:00", "qty": 0.0472, "price": 2755.0,
        "gross": 130.036, "fee": 0.130036, "net": 129.905964,
        "order_id": "ccb9052a-ce7b-4d51-8834-feecf67c83e1"}
PLACED = "2026-09-27T10:20:41+00:00"           # زمان گذاشتن سفارش — نه زمان ثبت


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_ledger_row_from_receipt() -> None:
    h, _ = P.load(str(ROOT / "holdings.json"), str(ROOT / "radar_journal.json"))
    rows = [r for r in h["ledger"] if r.get("order_id") == SALE["order_id"]]
    assert len(rows) == 1
    r = rows[0]
    assert (r["action"], r["symbol"], r["reason"], r["account"]) == \
        ("trim", "ETH", "reserve", "LBank")
    assert r["at"] == SALE["at"] and r["at"] != PLACED
    assert r["delta"] == -SALE["qty"] and r["price"] == SALE["price"]
    assert (r["gross"], r["fee"], r["net"]) == (SALE["gross"], SALE["fee"], SALE["net"])


def test_optcost_followup_from_fill_day() -> None:
    exits = [x for x in _load("radar_optcost.json")["exits"]
             if x.get("order_id") == SALE["order_id"]]
    assert len(exits) == 1
    x = exits[0]
    assert x["date"] == "2026-10-02" and x["at"] == SALE["at"]
    assert (x["symbol"], x["action"], x["reason"]) == ("ETH", "trim", "reserve")
    assert x["qty"] == SALE["qty"] and x["price"] == SALE["price"]


def test_watch_mark_and_two_steps_left() -> None:
    w, h = _load("watch.json"), _load("holdings.json")
    W.validate_watch(w)
    rp = w["reserve_plan"]
    step = next(s for s in rp["steps"] if s["symbol"] == "ETH" and s["price"] == 2755)
    ex = step["executed"]
    assert ex["order_id"] == SALE["order_id"] and ex["at"] == SALE["at"]
    assert (ex["avg_price"], ex["gross"], ex["fee"]) == (SALE["price"], SALE["gross"], SALE["fee"])
    assert W.unfilled_steps(rp, h) == [{"symbol": "ETH", "qty": 0.0472, "price": 2940},
                                       {"symbol": "SOL", "qty": 0.749, "price": 125.5}]


def test_progress_fill_price_and_time() -> None:
    """پله دوم ETH ردیف ۲ اکتبر را می‌گیرد، نه ردیف بازار ۲۵ سپتامبر."""
    w, h = _load("watch.json"), _load("holdings.json")
    prog = W.reserve_progress(w["reserve_plan"], h)
    s = next(p for p in prog if p["symbol"] == "ETH" and p["price"] == 2755)
    assert s["filled"] and s["fill_price"] == SALE["price"]
    assert s["fill_at"] == datetime(2026, 10, 2, 8, 17, 19, tzinfo=timezone.utc)
