"""
پله اول نقشه ذخیره، دو فروش واقعی LBank — نشست ۳، ۲۶ سپتامبر ۲۰۲۶.

از رسیدها، زمان تهران به وقت جهانی برگردانده شد:
- SOL: بازار، 0.749 در 121.33، مجموع 90.87617، کارمزد 0.090876،
  2026-09-25T22:09:00Z، سفارش 6663fe17-13ce-44a7-927a-fee8784cd6c0
- ETH: بازار، 0.0472 در 2685.33، مجموع 126.747576، کارمزد 0.126748،
  2026-09-25T22:10:21Z، سفارش e6c70733-5c87-4de6-bad7-3166860aeb96
خالص پس از کارمزد، جمعاً 217.406122 تتر، به نقد LBank. قفل داده است.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
SALES = {
    "SOL": {"at": "2026-09-25T22:09:00+00:00", "qty": 0.749, "price": 121.33,
            "gross": 90.87617, "fee": 0.090876, "order_id": "6663fe17-13ce-44a7-927a-fee8784cd6c0"},
    "ETH": {"at": "2026-09-25T22:10:21+00:00", "qty": 0.0472, "price": 2685.33,
            "gross": 126.747576, "fee": 0.126748, "order_id": "e6c70733-5c87-4de6-bad7-3166860aeb96"},
}


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _plan36(w: dict) -> dict:
    """نقشه رویداد ۳۶ — از ۸ اکتبر در reserve_archive، رویداد ۸۹. داده همان است."""
    return next(p for p in w["reserve_archive"] if p["created"] == "2026-09-25T16:00:00+00:00")


def test_ledger_has_both_receipts() -> None:
    h = _load("holdings.json")
    rows = [r for r in h["ledger"] if r["action"] == "trim" and r["reason"] == "reserve"]
    # دو ردیف نخست؛ پله دوم ETH، ۲ اکتبر، در test_reserve_step2_real.py
    assert [r["symbol"] for r in rows[:2]] == ["SOL", "ETH"]    # به ترتیب زمان رسید
    for r in rows[:2]:
        s = SALES[r["symbol"]]
        assert r["at"] == s["at"] and r["delta"] == -s["qty"] and r["price"] == s["price"]
        assert r["gross"] == s["gross"] and r["fee"] == s["fee"]
        assert r["order_id"] == s["order_id"] and r["account"] == "LBank"


def test_cash_and_quantities() -> None:
    """
    سهم پله اول در نقد LBank. از ۲ اکتبر ردیف‌های بعدی هم هست؛ وضعیت فعلی —
    اسکرین‌شات به‌علاوه همه ردیف‌ها — در test_holdings_real.py سنجیده می‌شود.
    """
    h, j = P.load(str(ROOT / "holdings.json"), str(ROOT / "radar_journal.json"))
    ids = {s["order_id"] for s in SALES.values()}
    rows = [r for r in h["ledger"] if r.get("order_id") in ids]
    assert len(rows) == 2
    for r in rows:
        assert r["net"] == pytest.approx(r["gross"] - r["fee"], abs=1e-9)
    assert sum(r["net"] for r in rows) == pytest.approx(217.406122, abs=1e-9)
    cash = {c["account"]: c["qty"] for c in h["cash"]}
    lots = {p["symbol"]: {l["account"]: l["qty"] for l in p["lots"]} for p in h["positions"]}
    # «صرافی دوم» ۲۹ سپتامبر با withdraw از رادار رفت — ETH رادار فقط LBank است
    assert "صرافی دوم" not in cash and "صرافی دوم" not in lots["ETH"]


def test_optcost_followup_from_sale_day() -> None:
    exits = {r["order_id"]: r for r in _load("radar_optcost.json")["exits"]}
    for sym, s in SALES.items():
        r = exits[s["order_id"]]
        assert r["symbol"] == sym and r["date"] == "2026-09-25" and r["at"] == s["at"]
        assert r["action"] == "trim" and r["reason"] == "reserve"


def test_watch_marks_and_no_market_reminder() -> None:
    w, h = _load("watch.json"), _load("holdings.json")
    W.validate_watch(w)
    steps = _plan36(w)["steps"]
    marked = {s["executed"]["order_id"]: s for s in steps if s.get("executed")}
    for sym, sale in SALES.items():
        s = marked[sale["order_id"]]
        assert s["symbol"] == sym and s["price"] is None        # پله بازار
    # هیچ پله بازاری یادآوری «مانده» نمی‌گیرد؛ فهرست کامل مانده در پله دوم
    assert all(s["price"] is not None for s in W.unfilled_steps(_plan36(w), h))


def test_sol_131_5_cancelled_with_reason() -> None:
    """
    تصمیم کاربر، ۲۹ سپتامبر ۲۰۲۶: پله SOL 0.749 در 131.5 هرگز در LBank گذاشته نشد
    و لغو است. پله پاک نشد؛ میدان cancelled با زمان کامل و دلیل دارد.
    """
    from datetime import datetime
    rp = _plan36(_load("watch.json"))
    sol = [s for s in rp["steps"] if s["symbol"] == "SOL"]
    assert [s["price"] for s in sol] == [None, 125.5, 131.5]
    c = sol[2]["cancelled"]
    assert datetime.fromisoformat(c["at"]).tzinfo is not None and c["at"].startswith("2026-09-29")
    assert "withdraw" in c["reason"] and "ETH" in c["reason"]
    # ۴ اکتبر دو پله دیگر هم لغو شدند — test_reserve_step2_real؛ لغو ۲۹ سپتامبر فقط همین یکی است
    assert [s["price"] for s in rp["steps"]
            if "cancelled" in s and s["cancelled"]["at"].startswith("2026-09-29")] == [131.5]
    assert "لغو" in rp["note"] and "سه پله" in rp["note"]


def test_eth_step2_moved_below_utc_resistance() -> None:
    """
    نشست ۳ب، بند ۷: قیمت پله دوم ETH در نقشه از 2790 به 2755 رفت — زیر مقاومت
    2760.76 با لنگر جهانی. مقاومت 131.81 که دلیل پله سوم SOL بود، با لنگر
    جهانی دیگر نیست. note نقشه هر دو را می‌گوید.

    اصلاح ۲۹ سپتامبر: شب ۲۷ سپتامبر سفارشی در LBank نبود؛ 2755 قیمت نقشه بود،
    نه جابه‌جایی سفارش. note نباید جابه‌جایی سفارش ادعا کند.
    """
    rp = _plan36(_load("watch.json"))
    assert [s["price"] for s in rp["steps"] if s["symbol"] == "ETH"] == [None, 2755, 2940]
    assert "2760.76" in rp["note"] and "131.81" in rp["note"]
    assert "2790" in rp["note"]                      # قیمت پیشین نقشه ثبت شده، نه پاک
    assert "جابه‌جا کرد" not in rp["note"] and "قیمت نقشه" in rp["note"]
