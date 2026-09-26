"""
آزمون holdings.json واقعی — نشست ۳ نقشه رادار ۷، مورد ۱-۵.

سبد واقعی از اسکرین‌شات‌های ۲۵ سپتامبر ۲۰۲۶، حدود ۰۵:۱۵ به وقت جهانی.
جمع در آن لحظه حدود ۲٬۵۶۸ دلار؛ با قیمت بسته ساعت ۰۵:۰۰ از اوکی‌اکس
2,571.17 دلار سنجیده شد — پس رقم اشتباه‌تایپ‌شده‌ای نیست.

همه در دفتر موقعیت؛ دفتر معامله خالی. قیمت خرید فقط برای لات ETH صرافی
دوم معلوم است؛ بقیه خالی می‌ماند و هیچ عددی ساخته نمی‌شود. HYPE و XRP
دیگر در سبد نیستند.

این آزمون فایل واقعی را فقط می‌خواند؛ نگهبان conftest.py جلوی هر تغییر
را می‌گیرد.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

ROOT = Path(__file__).resolve().parent.parent

# رقم‌ها عیناً از اسکرین‌شات — عمداً رشته‌ای جدا از فایل
LBANK = {"SOL": 6.38005369, "ETH": 0.242657, "BNB": 0.3296489, "AAVE": 1.04895,
         "LINK": 11.09889, "SUI": 81.6183, "ONDO": 115.43866, "TAO": 0.153892,
         "TRX": 0.6704}
SECOND = {"ETH": (0.15892356, 2641.83)}
CASH = {"LBank": 0.1010102, "صرافی دوم": 3.17443595}


@pytest.fixture(scope="module")
def h() -> dict:
    return json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))


def test_real_file_is_v2_and_valid(h) -> None:
    assert h["version"] == 2
    P.load(str(ROOT / "holdings.json"))          # با دفترچه واقعی


# از ۲۶ سپتامبر دفتر کل ردیف دارد — پله اول نقشه ذخیره. اسکرین‌شات در frozen و
# این رقم‌ها قفل می‌ماند؛ وضعیت فعلی = اسکرین‌شات + ردیف‌های دفتر کل، به تفکیک حساب.


def _ledger_by_account(h, field) -> dict:
    out: dict = {}
    for r in h["ledger"]:
        key = (r["symbol"], r.get("account")) if field == "delta" else r.get("account")
        out[key] = out.get(key, 0.0) + (r.get(field) or 0.0)
    return out


def test_updated_not_before_screenshot(h) -> None:
    from datetime import datetime
    assert "۰۵:۱۵" in h["source"]
    assert datetime.fromisoformat(h["updated"]) >= datetime.fromisoformat("2026-09-25T05:15:00+00:00")


def test_quantities_match_screenshots(h) -> None:
    pos = {p["symbol"]: p for p in h["positions"]}
    moved = _ledger_by_account(h, "delta")
    for sym, q in LBANK.items():
        lb = [l for l in pos[sym]["lots"] if l["account"] == "LBank"]
        assert len(lb) == 1 and lb[0]["qty"] == pytest.approx(q + moved.get((sym, "LBank"), 0.0),
                                                           abs=1e-12), sym
    eth2 = [l for l in pos["ETH"]["lots"] if l["account"] == "صرافی دوم"]
    assert len(eth2) == 1
    assert (eth2[0]["qty"], eth2[0]["entry"]) == SECOND["ETH"]


def test_no_invented_entry_price(h) -> None:
    """قیمت خرید فقط جایی که واقعاً معلوم است."""
    known = [(p["symbol"], l["account"]) for p in h["positions"] for l in p["lots"]
             if l["entry"] is not None]
    assert known == [("ETH", "صرافی دوم")]


def test_cash_is_stable_only(h) -> None:
    assert {c["asset"] for c in h["cash"]} == {"USDT"}
    got = {c["account"]: c["qty"] for c in h["cash"]}
    net = _ledger_by_account(h, "net")
    assert set(got) == set(CASH)
    for acct, q in CASH.items():
        assert got[acct] == pytest.approx(q + net.get(acct, 0.0), abs=1e-9), acct


def test_all_in_position_book_trade_book_empty(h) -> None:
    assert {p["book"] for p in h["positions"]} == {"position"}
    assert all(p["status"] == "open" for p in h["positions"])


def test_frozen_is_the_screenshot_and_invariant_holds(h) -> None:
    assert h["frozen"]["date"] == "2026-09-25"
    want = dict(LBANK)
    want["ETH"] += SECOND["ETH"][0]
    assert h["frozen"]["members"] == pytest.approx(want)
    P.validate(h, json.loads((ROOT / "radar_journal.json").read_text(encoding="utf-8")))


def test_sold_positions_are_gone(h) -> None:
    syms = {p["symbol"] for p in h["positions"]}
    assert "HYPE" not in syms and "XRP" not in syms
    assert syms == set(LBANK)
