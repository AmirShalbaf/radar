"""
رسید اجباری فروش و ناوردای نقد — بازبینی عمیق ۲۳ اکتبر ۲۰۲۶، یافته م۲.

پیش از این trim و exit بی --gross و --fee نقد را دست نمی‌زدند و هیچ خطایی
نمی‌دادند. فرمان‌های پیشنهادی پایشگر و سبد هم این دو را نداشتند. پس پیروی
از پیام خود رادار پول فروش را از دفتر غیب می‌کرد. محاسبه‌شده با پله ETH
0.074 در 2405.07: ذخیره 16.06٪ به‌جای 25.16٪، و کسری تا ۴۰٪ 350.2 به‌جای
243.5 دلار. ناوردای دفتر کل هم نقد را نمی‌سنجید.

قرارداد تازه — تصمیم کاربر، ۲۳ اکتبر ۲۰۲۶:
- trim و exit بی --gross و --fee خطا می‌دهند، مگر با کلید صریح --no-receipt.
- ناوردای نقد در validate، برای هر دارایی و حساب:
      نقد منجمد + خالص فروش‌ها − برداشت‌ها = نقد فعلی
  نقد منجمد در میدان frozen.cash است.
- هر پیامی که فرمان ثبت trim یا exit پیشنهاد می‌دهد، --gross و --fee و
  --order-id را نشان می‌دهد.
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
ROOT = Path(__file__).resolve().parent.parent
AT = "2026-10-17T15:33:55+00:00"


def _h() -> dict:
    cash = [{"asset": "USDT", "qty": 0.5, "account": "LBank"},
            {"asset": "USDT", "qty": 3.0, "account": "B"}]
    return {"version": 2, "updated": "2026-10-17T15:40:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.4, "SOL": 6.0},
                       "cash": [dict(c) for c in cash]},
            "cash": cash, "ledger": [],
            "positions": [
                {"symbol": "ETH", "book": "position", "status": "open", "invalidation": None,
                 "lots": [{"qty": 0.4, "account": "LBank", "entry": None}]},
                {"symbol": "SOL", "book": "position", "status": "open", "invalidation": None,
                 "lots": [{"qty": 4.0, "account": "LBank", "entry": None},
                          {"qty": 2.0, "account": "B", "entry": None}]}]}


def _j() -> dict:
    return {"version": 1, "trades": []}


@pytest.fixture
def files(tmp_path):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(_j()), encoding="utf-8")
    return hp, jp


def _run(files, *args) -> int:
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"), *args])


def _read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


TRIM = ["trim", "--symbol", "ETH", "--qty", "0.074", "--price", "2405.07", "--reason", "reserve"]
GROSS, FEE = "177.97518", "0.177975"


# ═══════════════ رسید اجباری ═══════════════

def test_trim_without_receipt_is_refused(files) -> None:
    before = files[0].read_text(encoding="utf-8")
    assert _run(files, *TRIM) == 2
    assert files[0].read_text(encoding="utf-8") == before        # فایل دست نخورد
    assert not (files[0].parent / "optcost.json").exists()


@pytest.mark.parametrize("half", [["--gross", GROSS], ["--fee", FEE]])
def test_half_receipt_is_refused(files, half) -> None:
    """کارمزد غایب یعنی صفر فرض‌شده و نقد بیش از واقع — هر دو لازم است."""
    assert _run(files, *TRIM, *half) == 2
    assert _read(files[0])["ledger"] == []


def test_full_receipt_credits_cash(files) -> None:
    assert _run(files, *TRIM, "--gross", GROSS, "--fee", FEE, "--at", AT,
                "--order-id", "x-1") == 0
    h = _read(files[0])
    cash = {c["account"]: c["qty"] for c in h["cash"]}
    assert cash["LBank"] == pytest.approx(0.5 + 177.97518 - 0.177975, abs=1e-9)
    assert "no_receipt" not in h["ledger"][-1]
    P.validate(h, _j())


def test_explicit_no_receipt_keeps_cash_and_marks_row(files) -> None:
    assert _run(files, *TRIM, "--no-receipt") == 0
    h = _read(files[0])
    assert {c["account"]: c["qty"] for c in h["cash"]}["LBank"] == 0.5
    assert h["ledger"][-1]["no_receipt"] is True
    P.validate(h, _j())


def test_no_receipt_with_receipt_is_contradiction(files) -> None:
    assert _run(files, *TRIM, "--no-receipt", "--gross", GROSS, "--fee", FEE) == 2
    assert _read(files[0])["ledger"] == []


def test_exit_without_receipt_is_refused(files) -> None:
    assert _run(files, "exit", "--symbol", "ETH", "--price", "2300", "--level", "2380.56") == 2
    assert _read(files[0])["ledger"] == []


def test_exit_with_receipt_credits_cash(files) -> None:
    assert _run(files, "exit", "--symbol", "ETH", "--price", "2300", "--level", "2380.56",
                "--gross", "920", "--fee", "0.92") == 0
    h = _read(files[0])
    assert {c["account"]: c["qty"] for c in h["cash"]}["LBank"] == pytest.approx(919.58)


def test_exit_multi_account_needs_trim_or_explicit_no_receipt(files) -> None:
    args = ["exit", "--symbol", "SOL", "--price", "95", "--level", "96.71"]
    assert _run(files, *args) == 2
    assert _run(files, *args, "--no-receipt") == 0
    assert _read(files[0])["ledger"][-1]["no_receipt"] is True


# ═══════════════ ناوردای نقد ═══════════════

def test_frozen_cash_is_required() -> None:
    h = _h()
    del h["frozen"]["cash"]
    with pytest.raises(P.PositionsError, match="frozen.cash"):
        P.validate(h, _j())


def test_unrecorded_cash_change_is_error() -> None:
    """ویرایش دستی نقد — بالا یا پایین — خطای صریح است، مثل اختلاف مقدار کوین."""
    for qty in (5.0, 0.4):
        h = _h()
        h["cash"][0]["qty"] = qty
        with pytest.raises(P.PositionsError, match="نقد"):
            P.validate(h, _j())


def test_cash_chain_with_sale_and_withdrawals() -> None:
    h = _h()
    h["positions"][0]["lots"][0]["qty"] = 0.3
    h["ledger"] = [
        {"at": AT, "action": "trim", "symbol": "ETH", "delta": -0.1, "price": 2400.0,
         "reason": "reserve", "account": "LBank", "gross": 240.0, "fee": 0.24, "net": 239.76},
        {"at": AT, "action": "withdraw", "symbol": "USDT", "delta": -100.0,
         "reason": "خرج شخصی", "account": "LBank",
         "cash": {"asset": "USDT", "qty": 100.0, "account": "LBank"}},
        {"at": AT, "action": "withdraw", "symbol": "SOL", "delta": -2.0,
         "reason": "خرج شخصی", "account": "B",
         "cash": {"asset": "USDT", "qty": 3.0, "account": "B"}},
    ]
    h["positions"][1]["lots"] = [{"qty": 4.0, "account": "LBank", "entry": None}]
    h["cash"] = [{"asset": "USDT", "qty": 0.5 + 239.76 - 100.0, "account": "LBank"}]
    P.validate(h, _j())
    h["cash"][0]["qty"] += 1.0
    with pytest.raises(P.PositionsError, match="LBank"):
        P.validate(h, _j())


def test_real_holdings_frozen_cash_and_invariant() -> None:
    """
    نقد ۲۵ سپتامبر از اسکرین‌شات — همان CASH آزمون test_holdings_real. زنجیره
    محاسبه‌شده: 0.1010102 + خالص چهار فروش − 12.15376371 − 334.844156 = 234.98925749.
    """
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    assert sorted((c["account"], c["qty"]) for c in h["frozen"]["cash"]) == \
        [("LBank", 0.1010102), ("صرافی دوم", 3.17443595)]
    P.validate(h, json.loads((ROOT / "radar_journal.json").read_text(encoding="utf-8")))


# ═══════════════ پیام‌های پیشنهاد ثبت ═══════════════

RECEIPT = ("--gross", "--fee", "--order-id")


def _has_receipt(text: str) -> bool:
    return all(k in text for k in RECEIPT)


NOW = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
CLOSED = "2026-10-26T00:00:00+00:00"


def _watch(steps, deadline="2026-10-30T00:00:00+00:00", fraction=1.0) -> dict:
    return {"exit_fraction": fraction,
            "positions": [{"symbol": "ETH", "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"}],
            "reserve_plan": {"created": "2026-10-17T15:32:00+00:00", "deadline": deadline,
                             "account": "LBank", "steps": steps}}


def _hp() -> dict:
    h = _h()
    h["positions"][0]["invalidation"] = 2380.56
    h["positions"][0]["invalidation_since"] = "2026-09-25T21:34:47+00:00"
    return h


def _weekly(close):
    return lambda s: ({"close": close, "closed_at": CLOSED, "venue": "okx",
                       "week_open": "2026-10-19T00:00:00+00:00"}, [])


@pytest.mark.parametrize("fraction", [1.0, 0.5])
def test_breach_message_shows_receipt(fraction) -> None:
    msgs = W.check_positions(_watch([], fraction=fraction), _hp(), {}, NOW,
                             weekly=_weekly(2300.0), price=lambda s: 2300.0)
    cmd = [m for m in msgs if "radar_positions.py" in m]
    assert cmd and all(_has_receipt(m) for m in cmd)


def test_reserve_price_hit_message_shows_receipt() -> None:
    msgs = W.check_positions(_watch([{"symbol": "ETH", "qty": 0.074, "price": 2490}]),
                             _hp(), {}, NOW, weekly=_weekly(2500.0), price=lambda s: 2500.0)
    cmd = [m for m in msgs if "radar_positions.py trim" in m]
    assert cmd and all(_has_receipt(m) for m in cmd)


def test_reserve_market_and_deadline_messages_show_receipt() -> None:
    steps = [{"symbol": "ETH", "qty": 0.074, "price": None},
             {"symbol": "SOL", "qty": 1.0, "price": 200.0}]
    live = W.check_positions(_watch(steps), _hp(), {}, NOW, weekly=_weekly(2500.0),
                             price=lambda s: 100.0)
    # پس از مهلت با شرط برقرارنبودن لغو — حکم «فروش در بازار»
    w = _watch(steps, deadline="2026-10-19T00:00:00+00:00")
    w["reserve_plan"]["on_deadline"] = {"cancel_if_band_at_least": "سازنده", "otherwise": "market"}
    reg = {"generated_at": NOW.isoformat(), "trade_band": {"name": "محتاط"}}
    late = W.check_positions(w, _hp(), {}, NOW, weekly=_weekly(2500.0),
                             price=lambda s: 100.0, regime=reg)
    cmd = [m for m in live + late if "radar_positions.py trim" in m]
    assert len(cmd) == 2 and all(_has_receipt(m) for m in cmd)


def test_stray_executed_message_shows_receipt() -> None:
    steps = [{"symbol": "ETH", "qty": 0.074, "price": 2490,
              "executed": {"at": AT, "order_id": "x-9"}}]
    msgs = W.check_positions(_watch(steps), _hp(), {}, NOW, weekly=_weekly(2500.0),
                             price=lambda s: 2400.0)
    cmd = [m for m in msgs if "radar_positions.py trim" in m]
    assert cmd and all(_has_receipt(m) for m in cmd)


def test_book_suggestions_show_receipt() -> None:
    """هر ردیف اقدام سبد که فرمان trim یا exit پیشنهاد می‌دهد."""
    rp = _watch([{"symbol": "ETH", "qty": 0.074, "price": 2490},
                 {"symbol": "SOL", "qty": 1.0, "price": 200.0,
                  "executed": {"at": AT, "order_id": "x-9"}}])["reserve_plan"]
    h = _hp()
    val = P.value(h, {"ETH": 2400.0, "SOL": 100.0})
    texts = []
    for now in (datetime(2026, 10, 20, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)):
        rv = B.reserve_view(rp, h, {"ETH": 2400.0, "SOL": 100.0}, val, now, band="محتاط")
        texts += B._plan_actions(rv) + B._reserve_lines(rv, None)
    rows = [{"pos": h["positions"][0], "qty": 0.4, "price": 2300.0, "value": 920.0,
             "dust": False, "avg_entry": None, "score": None, "rsi": None, "rs30": None,
             "strikes": 0, "weekly": {"close": 2300.0, "closed_at": CLOSED}}]
    reg = BG_row("محتاط")
    texts.append(B.build_report(h, rows, reg, [], val=val))
    texts.append(B.build_report(h, rows[:0], reg, [], val=val))
    cmd = [line for t in texts for line in t.split("\n")
           if "radar_positions.py trim" in line or "radar_positions.py exit" in line]
    assert len(cmd) >= 4
    assert all(_has_receipt(line) for line in cmd), cmd


def BG_row(name: str) -> dict:
    import radar_budget as BG
    return BG.band_by_name(name)
