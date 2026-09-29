"""
لغو پله نقشه ذخیره — تصمیم کاربر، ۲۹ سپتامبر ۲۰۲۶.

پله SOL 0.749 در 131.5 هرگز در LBank گذاشته نشد و لغو است. دلیل: پس از
withdraw، پرشدن هر چهار پله ذخیره را به 29.2٪ می‌برد و با سه پله حدود ۲۵٪
می‌شود. پله حذف‌شده از SOL است، چون طبق ترتیب فروش، ETH با قدرت نسبی ضعیف‌تر
اول فروخته می‌شود.

قرارداد:
- پله از reserve_plan پاک نمی‌شود؛ میدان cancelled با زمان کامل و دلیل.
- پله لغوشده در این‌ها نمی‌آید: پله‌های مانده، یادآوری و هشدار مهلت و رسیدن
  قیمت پایشگر، «ذخیره اگر همه پر شوند»، و «بالاترین قیمت پله مانده» روش ک۴۲.
  بخش ۶ سبد فقط یک سطر «لغوشده» با دلیلش دارد.
- پله لغوشده هرگز با ردیف دفتر کل پرشده شمرده نمی‌شود، حتی اگر روزی همان
  مقدار SOL فروخته شود.
- اعتبارسنجی watch.json میدان تازه را می‌شناسد؛ لغو بی‌زمان یا بی‌دلیل خطای بلند.
"""
import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_watch as W
from test_watch_positions import _all_above, _h, _run, _watch

UTC = timezone.utc
WHY = "با سه پله ذخیره حدود ۲۵٪؛ ETH با قدرت نسبی ضعیف‌تر اول فروخته می‌شود"
CANCEL = {"at": "2026-09-29T14:00:00+00:00", "reason": WHY}


def _cw(**cancel) -> dict:
    """نقشه SOL پایشگر با پله سوم لغوشده."""
    w = _watch()
    w["reserve_plan"]["steps"][2]["cancelled"] = dict(CANCEL, **cancel)
    return w


def _trims(qty: float) -> list:
    return [{"at": "2026-09-30T10:00:00+00:00", "action": "trim", "symbol": "SOL",
             "delta": -qty, "price": 132.0, "reason": "reserve"}]


# ═══════════════ اعتبارسنجی ═══════════════

def test_valid_cancel_passes() -> None:
    W.validate_watch(_cw())


@pytest.mark.parametrize("bad", [{"at": None}, {"at": "2026-09-29"}, {"reason": ""},
                                 {"reason": None}])
def test_cancel_needs_full_time_and_reason(bad) -> None:
    with pytest.raises(W.WatchError, match="cancelled"):
        W.validate_watch(_cw(**bad))


def test_cancel_not_a_dict_is_error() -> None:
    w = _watch()
    w["reserve_plan"]["steps"][2]["cancelled"] = True
    with pytest.raises(W.WatchError, match="cancelled"):
        W.validate_watch(w)


def test_cancelled_and_executed_is_error() -> None:
    w = _cw()
    w["reserve_plan"]["steps"][2]["executed"] = {"at": "2026-09-30T10:00:00+00:00",
                                                 "order_id": "x"}
    with pytest.raises(W.WatchError, match="لغو"):
        W.validate_watch(w)


# ═══════════════ پرشدن و مانده ═══════════════

def test_cancelled_never_filled_even_with_sale() -> None:
    rp = _cw()["reserve_plan"]
    h = _h(ledger=_trims(3 * 0.749), sol=6.0 - 3 * 0.749)
    assert W.step_filled(rp, h) == [True, True, False]
    assert W.unfilled_steps(rp, h) == []
    prog = W.reserve_progress(rp, h)
    assert prog[2]["filled"] is False and prog[2]["cancelled"]["reason"] == WHY


def test_unfilled_excludes_cancelled() -> None:
    assert W.unfilled_steps(_cw()["reserve_plan"], _h()) == [
        {"symbol": "SOL", "qty": 0.749, "price": None},
        {"symbol": "SOL", "qty": 0.749, "price": 125.5}]


def test_cancelled_middle_step_does_not_block_next() -> None:
    w = _watch()
    w["reserve_plan"]["steps"][1]["cancelled"] = dict(CANCEL)
    rp = w["reserve_plan"]
    h = _h(ledger=_trims(2 * 0.749), sol=6.0 - 2 * 0.749)
    assert W.step_filled(rp, h) == [True, False, True]


# ═══════════════ پیام‌های پایشگر ═══════════════

def test_no_price_alert_for_cancelled_step() -> None:
    msgs = _run(_cw(), _h(), {}, _all_above(),
                price=lambda s: {"SOL": 133.0}.get(s, 1.0))
    assert any("پله ذخیره" in x and "125.5" in x for x in msgs)
    assert not any("پله ذخیره" in x and "131.5" in x for x in msgs)


def test_deadline_alert_without_cancelled() -> None:
    msgs = _run(_cw(), _h(), {}, _all_above(), now=datetime(2026, 10, 5, 4, 40, tzinfo=UTC))
    m = next(x for x in msgs if "مهلت" in x)
    assert "125.5" in m and "131.5" not in m


# ═══════════════ سبد — بخش ۶ و روش ک۴۲ ═══════════════

H = {"positions": [{"symbol": "SOL", "book": "position", "status": "open",
                    "lots": [{"qty": 5.631054, "account": "LBank", "entry": None}]}],
     "ledger": [{"at": "2026-09-25T22:09:00+00:00", "action": "trim", "symbol": "SOL",
                 "delta": -0.749, "price": 121.33, "reason": "reserve"}],
     "updated": "2026-09-29T13:48:00+00:00", "source": "آزمون"}
VAL = {"total": 2236.0, "stable_usd": 218.0, "incomplete": False, "missing": []}
NOW = datetime(2026, 9, 29, 15, 0, tzinfo=UTC)


def _plan() -> dict:
    return copy.deepcopy(_cw()["reserve_plan"])


def test_book_view_k42_ignores_cancelled() -> None:
    v = B.reserve_view(_plan(), H, {"SOL": 121.0}, VAL, NOW)
    assert [(s["price"]) for s in v["left"]] == [125.5]
    assert [s["price"] for s in v["cancelled"]] == [131.5]
    proceeds = 0.749 * 125.5 * (1 - B.RESERVE_FEE)
    total = 2236.0 - 5.631054 * 121.0 + (5.631054 - 0.749) * 125.5 + proceeds
    assert v["after"]["total"] == pytest.approx(total)       # بالاترین قیمت 125.5، نه 131.5
    assert v["after"]["stable"] == pytest.approx(218.0 + proceeds)


def test_section6_one_cancelled_line() -> None:
    v = B.reserve_view(_plan(), H, {"SOL": 121.0}, VAL, NOW)
    reg = {"name": "محتاط", "cap": 4.0, "mult": 0.5, "maxpos": 3, "stable": 25}
    txt = B.build_report(H, [], reg, [], "آزمون", val=VAL, reserve=v)
    s6 = txt[txt.index("## ۶ —"):]
    left = s6[s6.index("**مانده"): s6.index("**لغوشده")]
    assert "125.5" in left and "131.5" not in left
    lines = [ln for ln in s6.splitlines() if "لغوشده" in ln]
    assert len(lines) == 1 and "131.5" in lines[0] and WHY in lines[0]
    assert "1 پله مانده" in s6