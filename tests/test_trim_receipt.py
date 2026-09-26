"""
ثبت فروش واقعی از رسید صرافی — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

پیش از این trim زمان را همیشه «اکنون» می‌گذاشت، نقد را عوض نمی‌کرد و کارمزد
و شناسه سفارش نداشت. رسید زمان دارد و پیگیری ۱۴ و ۳۰ روزه دفتر هزینه فرصت
باید از لحظه فروش شمرده شود، نه از لحظه ثبت.
- --at: مهر کامل با منطقه زمانی؛ نه آینده، نه پیش از تاریخ منجمد.
- --gross باید با مقدار × قیمت بخواند؛ --fee؛ خالص به تتر همان حساب.
- --order-id در ردیف دفتر کل و رکورد دفتر هزینه فرصت.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

AT = "2026-09-25T22:10:21+00:00"


def _h() -> dict:
    return {"version": 2, "updated": "2026-09-25T05:15:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.4, "SOL": 6.0}},
            "cash": [{"asset": "USDT", "qty": 0.1010102, "account": "LBank"},
                     {"asset": "USDT", "qty": 3.0, "account": "B"}],
            "ledger": [],
            "positions": [
                {"symbol": "ETH", "book": "position", "status": "open", "invalidation": None,
                 "lots": [{"qty": 0.25, "account": "LBank", "entry": None},
                          {"qty": 0.15, "account": "B", "entry": 2641.83}]},
                {"symbol": "SOL", "book": "position", "status": "open", "invalidation": None,
                 "lots": [{"qty": 6.0, "account": "LBank", "entry": None}]}]}


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


ETH = ["trim", "--symbol", "ETH", "--account", "LBank", "--qty", "0.0472", "--price", "2685.33",
       "--reason", "reserve"]


def test_receipt_trim_records_time_cash_fee_and_order(files) -> None:
    assert _run(files, *ETH, "--at", AT, "--gross", "126.747576", "--fee", "0.126748",
                "--order-id", "e6c70733-5c87-4de6-bad7-3166860aeb96") == 0
    h = json.loads(files[0].read_text(encoding="utf-8"))
    row = h["ledger"][-1]
    assert row["at"] == AT and row["delta"] == -0.0472 and row["account"] == "LBank"
    assert row["gross"] == 126.747576 and row["fee"] == 0.126748
    assert row["net"] == pytest.approx(126.620828)
    assert row["order_id"] == "e6c70733-5c87-4de6-bad7-3166860aeb96"
    cash = {c["account"]: c["qty"] for c in h["cash"]}
    assert cash["LBank"] == pytest.approx(0.1010102 + 126.620828, abs=1e-9)
    assert cash["B"] == 3.0                                  # حساب دیگر دست نخورد
    oc = json.loads((files[0].parent / "optcost.json").read_text(encoding="utf-8"))
    rec = oc["exits"][-1]
    assert rec["at"] == AT and rec["date"] == "2026-09-25"   # پیگیری از روز فروش
    assert rec["order_id"] == "e6c70733-5c87-4de6-bad7-3166860aeb96"


def test_gross_must_match_qty_times_price(files) -> None:
    assert _run(files, *ETH, "--at", AT, "--gross", "130.0", "--fee", "0.1") == 2
    assert json.loads(files[0].read_text(encoding="utf-8"))["ledger"] == []


@pytest.mark.parametrize("at", ["2026-09-25T22:10:21", "2099-01-01T00:00:00+00:00",
                                "2026-09-24T23:00:00+00:00"])
def test_at_must_be_full_past_and_after_frozen(files, at) -> None:
    assert _run(files, *ETH, "--at", at) == 2
    assert json.loads(files[0].read_text(encoding="utf-8"))["ledger"] == []


def test_without_receipt_cash_unchanged(files) -> None:
    assert _run(files, *ETH) == 0
    h = json.loads(files[0].read_text(encoding="utf-8"))
    assert {c["account"]: c["qty"] for c in h["cash"]}["LBank"] == 0.1010102


def test_invalid_ledger_time_rejected_on_load() -> None:
    h = _h()
    h["ledger"].append({"at": "2026-09-25T22:10:21", "action": "trim", "symbol": "SOL",
                        "delta": -0.749, "price": 121.33, "reason": "reserve"})
    h["positions"][1]["lots"][0]["qty"] = 5.251
    with pytest.raises(P.PositionsError):
        P.validate(h, {"version": 1, "trades": []})
