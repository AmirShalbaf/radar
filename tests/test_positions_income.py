"""
درآمد نقدی — زیرفرمان income، متن ۱۶، ۲۴ اکتبر ۲۰۲۶.

تتر LBank در 2026-10-23 12:50 UTC 0.357453 بیش از دفتر بود: سود خودکار تتر با
برچسب APY 12.74٪، تجمعی ۱۷ تا ۲۳ اکتبر. ناوردای نقد بازبینی ۲۳ اکتبر هر تغییر نقد
را فقط با رسید فروش یا withdraw می‌پذیرد، و adjust برای کوین است — سقف ۱٪ و
ناوردای کوین. پس درآمد نقدی راه ثبت نداشت. تصمیم کاربر: برای نقد از adjust
استفاده نشود.

قرارداد:
- income --asset USDT --account <حساب> --qty <مثبت> --at <مهر کامل> --reason <دلیل>
- فقط استیبل، فقط مقدار مثبت، دلیل و حساب لازم. یک ردیف دفتر کل با میدان cash.
- ناوردای نقد: نقد منجمد + خالص فروش‌ها + درآمد − برداشت‌ها = نقد فعلی.
- ناوردای کوین دست نمی‌خورد؛ نه رکورد هزینه فرصت، نه سهمیه ورود دوباره.
- --at مثل رسید فروش: نه آینده، نه پیش از تاریخ منجمد.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

AT = "2026-10-23T12:50:00+00:00"
REASON = "سود خودکار تتر LBank، تجمعی ۱۷ تا ۲۳ اکتبر"
J = {"version": 1, "trades": []}


def _h() -> dict:
    cash = [{"asset": "USDT", "qty": 419.06499749, "account": "LBank"}]
    return {"version": 2, "updated": "2026-10-21T13:10:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0},
                       "cash": [dict(c) for c in cash]},
            "cash": cash, "ledger": [],
            "positions": [{"symbol": "SOL", "book": "position", "status": "open",
                           "invalidation": None,
                           "lots": [{"qty": 6.0, "account": "LBank", "entry": None}]}]}


@pytest.fixture
def files(tmp_path):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(J), encoding="utf-8")
    return hp, jp


def _run(files, *args) -> int:
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"), *args])


def _read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


INCOME = ["income", "--asset", "USDT", "--account", "LBank", "--qty", "0.357453",
          "--at", AT, "--reason", REASON]


def test_income_adds_cash_and_one_ledger_row(files) -> None:
    assert _run(files, *INCOME) == 0
    h = _read(files[0])
    assert {c["account"]: c["qty"] for c in h["cash"]}["LBank"] == \
        pytest.approx(419.42245049, abs=1e-9)                # 419.06499749 + 0.357453
    row = h["ledger"][-1]
    assert (row["action"], row["symbol"], row["delta"], row["account"], row["at"],
            row["reason"]) == ("income", "USDT", 0.357453, "LBank", AT, REASON)
    assert row["cash"] == {"asset": "USDT", "qty": 0.357453, "account": "LBank"}
    P.validate(h, J)
    assert not (files[0].parent / "optcost.json").exists()      # هزینه فرصت نیست


def test_income_to_new_account_creates_cash_row(files) -> None:
    assert _run(files, "income", "--asset", "USDT", "--account", "B", "--qty", "1.5",
                "--at", AT, "--reason", "سود") == 0
    h = _read(files[0])
    assert {c["account"]: c["qty"] for c in h["cash"]}["B"] == 1.5
    P.validate(h, J)


@pytest.mark.parametrize("qty", ["0", "-0.1"])
def test_income_must_be_positive(files, qty) -> None:
    before = files[0].read_text(encoding="utf-8")
    assert _run(files, "income", "--asset", "USDT", "--account", "LBank", "--qty", qty,
                "--at", AT, "--reason", REASON) == 2
    assert files[0].read_text(encoding="utf-8") == before


def test_income_is_cash_only(files) -> None:
    assert _run(files, "income", "--asset", "SOL", "--account", "LBank", "--qty", "0.1",
                "--at", AT, "--reason", "پاداش") == 2
    assert _read(files[0])["ledger"] == []


@pytest.mark.parametrize("at", ["2026-10-23T12:50:00", "2099-01-01T00:00:00+00:00",
                                "2026-09-24T00:00:00+00:00"])
def test_income_at_full_past_after_frozen(files, at) -> None:
    assert _run(files, "income", "--asset", "USDT", "--account", "LBank", "--qty", "0.1",
                "--at", at, "--reason", REASON) == 2


def test_income_needs_reason_and_account() -> None:
    h = _h()
    base = {"at": AT, "action": "income", "symbol": "USDT", "delta": 0.357453,
            "account": "LBank", "reason": REASON,
            "cash": {"asset": "USDT", "qty": 0.357453, "account": "LBank"}}
    h["cash"][0]["qty"] += 0.357453
    h["ledger"] = [dict(base)]
    P.validate(h, J)
    for bad in (dict(reason=""), dict(account=None), dict(delta=-0.357453),
                dict(cash={"asset": "USDT", "qty": 1.0, "account": "LBank"}),
                dict(symbol="SOL"), dict(cash=None)):
        h["ledger"] = [{**base, **bad}]
        with pytest.raises(P.PositionsError, match="درآمد"):
            P.validate(h, J)


def test_unrecorded_cash_rise_is_still_an_error() -> None:
    """درآمد ثبت‌نشده همان اختلاف ثبت‌نشده است — ناوردای نقد."""
    h = _h()
    h["cash"][0]["qty"] += 0.357453
    with pytest.raises(P.PositionsError, match="نقد"):
        P.validate(h, J)


def test_income_does_not_touch_coin_invariant_or_allowance(files) -> None:
    assert _run(files, *INCOME) == 0
    h = _read(files[0])
    assert P.validate(h, J)["expected"] == {"SOL": 6.0}
    assert P.reentry_state(h, "USDT") is None
