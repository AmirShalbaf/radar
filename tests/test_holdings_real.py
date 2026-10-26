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
from datetime import datetime
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
        # ردیف adjust حساب ندارد. همه نمادها حالا فقط در LBank‌اند — همین آزمون
        # یک لات LBank برای هر نماد را می‌سنجد؛ adjust BNB، ۳ اکتبر ۲۰۲۶
        acct = r.get("account") or ("LBank" if r["action"] == "adjust" else None)
        key = (r["symbol"], acct) if field == "delta" else r.get("account")
        out[key] = out.get(key, 0.0) + (r.get(field) or 0.0)
    return out


def test_updated_not_before_screenshot(h) -> None:
    """
    منبع — اسکرین‌شات ۲۴ اکتبر ۲۰۲۶، متن ۱۶؛ frozen همان اسکرین‌شات ۲۵ سپتامبر می‌ماند.
    متن ۱۹: فروش ETH با ابطال از رسید ثبت شد و فرمان updated را به زمان ثبت برد؛ پس
    updated پیش از اسکرین‌شات نیست، برابر هم نیست.
    """
    assert "LBank" in h["source"] and "۲۴ اکتبر ۲۰۲۶" in h["source"]
    assert "04:02 UTC" in h["source"] and "1625.64" in h["source"]
    assert datetime.fromisoformat(h["updated"]) >= datetime.fromisoformat(AT_1024)


def test_quantities_match_screenshots(h) -> None:
    pos = {p["symbol"]: p for p in h["positions"]}
    moved = _ledger_by_account(h, "delta")
    for sym, q in LBANK.items():
        lb = [l for l in pos[sym]["lots"] if l["account"] == "LBank"]
        assert len(lb) == 1 and lb[0]["qty"] == pytest.approx(q + moved.get((sym, "LBank"), 0.0),
                                                           abs=1e-12), sym
    # لات صرافی دوم ۲۹ سپتامبر با withdraw از رادار برداشته شد — پول خرج شخصی
    eth2 = [l for l in pos["ETH"]["lots"] if l["account"] == "صرافی دوم"]
    left = SECOND["ETH"][0] + moved.get(("ETH", "صرافی دوم"), 0.0)
    assert left == pytest.approx(0.0, abs=1e-12) and eth2 == []


def test_no_invented_entry_price(h) -> None:
    """قیمت خرید فقط جایی که واقعاً معلوم است — تنها لات معلوم برداشته شد."""
    known = [(p["symbol"], l["account"]) for p in h["positions"] for l in p["lots"]
             if l["entry"] is not None]
    assert known == []


def _cash_rows(h, action) -> dict:
    out: dict = {}
    for r in h["ledger"]:
        c = r.get("cash") if r.get("action") == action else None
        if c:
            out[c["account"]] = out.get(c["account"], 0.0) + c["qty"]
    return out


def test_cash_is_stable_only(h) -> None:
    """زنجیره نقد بیرون از کد: منجمد + خالص فروش‌ها + درآمد — income، متن ۱۶ — − برداشت‌ها."""
    assert {c["asset"] for c in h["cash"]} == {"USDT"}
    got = {c["account"]: c["qty"] for c in h["cash"]}
    net, gone = _ledger_by_account(h, "net"), _cash_rows(h, "withdraw")
    earned = _cash_rows(h, "income")
    want = {a: q + net.get(a, 0.0) + earned.get(a, 0.0) - gone.get(a, 0.0)
            for a, q in CASH.items()}
    assert set(got) == {a for a, q in want.items() if q > 1e-9}
    for acct, q in got.items():
        assert q == pytest.approx(want[acct], abs=1e-9), acct


def test_second_exchange_withdrawn_once() -> None:
    """
    تصمیم کاربر، ۲۹ سپتامبر ۲۰۲۶: ETH و USDT «صرافی دوم» پول خرج شخصی است.
    یک ردیف withdraw، بی‌پیگیری هزینه فرصت و بی‌رکورد دفترچه — الگوی ONDO ک۱۰.
    عددهای پیش از ۲۹ سپتامبر، مثل 2631.20 رویداد ۴۲، این مقدار را هم داشتند.
    """
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    rows = [r for r in h["ledger"] if r["action"] == "withdraw" and r["account"] == "صرافی دوم"]
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"], r["account"]) == ("ETH", -0.15892356, "صرافی دوم")
    assert r["reason"] == "پول خرج شخصی — از رادار حذف شد"
    assert r["cash"] == {"asset": "USDT", "qty": 3.17443595, "account": "صرافی دوم"}
    assert r["at"].startswith("2026-09-29")
    text = json.dumps({k: h[k] for k in ("positions", "cash", "source")}, ensure_ascii=False)
    assert "صرافی دوم" not in text                        # فقط در ردیف دفتر کل
    oc = json.loads((ROOT / "radar_optcost.json").read_text(encoding="utf-8"))
    assert not [x for x in oc.get("exits", []) if abs(x.get("qty", 0) - 0.15892356) < 1e-9]
    jr = (ROOT / "radar_journal.json").read_text(encoding="utf-8")
    assert "0.15892356" not in jr


def test_lbank_cash_withdrawn_once() -> None:
    """
    تصمیم کاربر، ۳ اکتبر ۲۰۲۶: تتر LBank 12.15376371 کمتر از دفتر بود — اختلاف
    دفتر پس از پله دوم ETH با اسکرین‌شات 04:10 UTC. کاربر خودش برداشت، خرج
    شخصی. فقط نقد؛ زمان دقیق نامعلوم، پس زمان اسکرین‌شات و همین در دلیل.
    مثل ک۱۰: بی‌پیگیری هزینه فرصت و بی‌رکورد دفترچه.
    """
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    rows = [r for r in h["ledger"] if r["action"] == "withdraw" and r["account"] == "LBank"
            and r["at"].startswith("2026-10-03")]
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"], r["at"]) == ("USDT", -12.15376371, "2026-10-03T04:10:00+00:00")
    assert r["cash"] == {"asset": "USDT", "qty": 12.15376371, "account": "LBank"}
    assert r["reason"].startswith("پول خرج شخصی — برداشت از LBank")
    assert "نامعلوم" in r["reason"] and "اسکرین‌شات" in r["reason"]
    oc = json.loads((ROOT / "radar_optcost.json").read_text(encoding="utf-8"))
    assert not [x for x in oc.get("exits", []) if x.get("symbol") == "USDT"]
    assert "12.15376371" not in (ROOT / "radar_journal.json").read_text(encoding="utf-8")


def test_bnb_adjust_cause_unknown(h) -> None:
    """
    تصمیم کاربر، ۳ اکتبر ۲۰۲۶: BNB در اسکرین‌شات 0.001443 کمتر از دفتر بود —
    0.44٪، زیر سقف ۱٪ adjust. علت نامعلوم، و همین در دلیل.
    """
    rows = [r for r in h["ledger"] if r["action"] == "adjust" and "۱۱ مهر" in r["reason"]]
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"]) == ("BNB", -0.001443)
    assert r["reason"] == "اختلاف با اسکرین‌شات ۱۱ مهر — علت نامعلوم"
    assert -r["delta"] <= P.ADJUST_MAX * LBANK["BNB"]


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


# ═══════════════ مرور هفتگی ۱۷ اکتبر ۲۰۲۶ — RD-20261017-01 ═══════════════
# اسکرین‌شات‌های LBank، حدود 15:32 تا 15:36 UTC. پیش از فروش: تتر 0.41517649 و
# BNB 0.3277579؛ پس از فروش BNB: تتر 234.98925749. بقیه نمادها با دفتر می‌خوانند.

SEEN_1017 = {"SOL": 5.63105369, "ETH": 0.148257, "AAVE": 1.04895, "LINK": 11.09889,
             "SUI": 81.6183, "ONDO": 115.43866, "TAO": 0.153892, "TRX": 0.6704}


def _rows_1017(h, action) -> list[dict]:
    return [r for r in h["ledger"] if r["action"] == action and r["at"].startswith("2026-10-17")]


def test_1017_withdraw_personal_usdt(h) -> None:
    """برداشت شخصی تتر — مثل ردیف ۳ اکتبر: فقط نقد، زمان اسکرین‌شات پیش از فروش."""
    rows = _rows_1017(h, "withdraw")
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"], r["account"]) == ("USDT", -334.844156, "LBank")
    assert r["at"] == "2026-10-17T15:32:00+00:00"
    assert r["cash"] == {"asset": "USDT", "qty": 334.844156, "account": "LBank"}
    assert r["reason"].startswith("پول خرج شخصی")
    for x in ("نامعلوم", "اسکرین‌شات", "335.25933249", "0.41517649"):
        assert x in r["reason"], x
    assert 335.25933249 - 0.41517649 == pytest.approx(334.844156, abs=1e-9)


def test_1017_bnb_adjust_second_time(h) -> None:
    rows = [r for r in h["ledger"] if r["action"] == "adjust" and "۱۷ اکتبر" in r["reason"]]
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"]) == ("BNB", -0.000448)
    assert r["reason"] == "اختلاف با اسکرین‌شات ۱۷ اکتبر — علت نامعلوم؛ دومین بار پس از ۳ اکتبر"
    assert 0.3282059 - 0.000448 == pytest.approx(0.3277579, abs=1e-12)
    assert -r["delta"] <= P.ADJUST_MAX * 0.3282059
    # adjust پیش از فروش در دفتر کل — پس از فروش سقف ۱٪ مانده ناچیز آن را رد می‌کرد
    i_adj = h["ledger"].index(r)
    i_trim = h["ledger"].index(_rows_1017(h, "trim")[0])
    assert i_adj < i_trim


def test_1017_bnb_reserve_sale(h) -> None:
    rows = _rows_1017(h, "trim")
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"], r["price"], r["reason"]) == ("BNB", -0.327, 718.07, "reserve")
    assert r["order_id"] == "8c103fa9-64c1-493e-9f3d-1f3c3ae36102"
    assert r["at"] == "2026-10-17T15:33:55+00:00" and r["account"] == "LBank"
    assert (r["gross"], r["fee"]) == (234.80889, 0.234809)
    assert r["net"] == pytest.approx(234.574081, abs=1e-9)
    oc = json.loads((ROOT / "radar_optcost.json").read_text(encoding="utf-8"))
    assert [x for x in oc.get("exits", []) if x.get("order_id") == r["order_id"]]


def _upto(h, last: dict) -> dict:
    """همان فایل با دفتر کل تا این ردیف — وضعیت دفتر در لحظه آن اسکرین‌شات."""
    return {**h, "ledger": h["ledger"][:h["ledger"].index(last) + 1]}


def test_1017_matches_screenshots(h) -> None:
    """از ۲۴ اکتبر مقدار فعلی عوض شده؛ پس وضعیت ۱۷ اکتبر از بازپخش دفتر کل تا فروش BNB."""
    then = _upto(h, _rows_1017(h, "trim")[0])
    run = P._replay(then, {}, check_journal=False)["expected"]
    for sym, q in SEEN_1017.items():
        assert run[sym] == pytest.approx(q, abs=1e-12), sym
    assert run["BNB"] == pytest.approx(0.0007579, abs=1e-12)
    assert P.cash_expected(then)[("USDT", "LBank")] == pytest.approx(234.98925749, abs=1e-9)
    assert 0.41517649 + 234.80889 - 0.234809 == pytest.approx(234.98925749, abs=1e-9)


def test_1017_bnb_dust_has_no_level(h) -> None:
    """مانده BNB ناچیز است، مثل TRX: سطح ابطال ندارد؛ کف 702.39 فقط در نقشه بازخرید."""
    bnb = next(p for p in h["positions"] if p["symbol"] == "BNB")
    trx = next(p for p in h["positions"] if p["symbol"] == "TRX")
    assert bnb["invalidation"] is None and "invalidation_since" not in bnb
    assert {k for k in bnb if k != "lots"} == {k for k in trx if k != "lots"}
    assert 0.0007579 * 718.07 < P.DUST_USD


# ═══════════════ متن ۱۶ — ۲۱ تا ۲۴ اکتبر ۲۰۲۶، RD-20261024-01 ═══════════════
# اسکرین‌شات LBank 2026-10-24 04:02 UTC، جمع 1625.64 دلار؛ ساعت اسکرین‌شات وقت تهران بود.
# مقدارها شامل مقدار قفل‌شده در سفارش‌های باز است.

SEEN_1024 = {"SOL": 5.48105369, "AAVE": 1.04895, "LINK": 11.09889, "ETH": 0.037257,
             "SUI": 81.6183, "ONDO": 115.43866, "BNB": 0.0007579, "TRX": 0.6704,
             "TAO": 0.000092}
USDT_1024 = 561.87837649
AT_1024 = "2026-10-24T04:02:00+00:00"
SALES_1024 = [  # نماد، مقدار، قیمت، زمان، سفارش، ناخالص، کارمزد
    ("ETH", 0.074, 2490.0, "2026-10-21T13:06:34+00:00", "7e76721a-0cc5-408a-b3a0-e07b135189bd",
     184.26, 0.18426),
    ("TAO", 0.1538, 254.4, "2026-10-24T03:47:08+00:00", "4395c156-03ce-4604-83c3-ed74a5d55961",
     39.12672, 0.078253),
    ("ETH", 0.037, 2381.81, "2026-10-24T03:48:34+00:00", "a39a661a-34f9-4e1a-b9d6-7e244b797cca",
     88.12697, 0.088127),
    ("SOL", 0.15, 102.56, "2026-10-24T03:49:33+00:00", "fe063a55-bd90-47aa-935d-c7817c807f3d",
     15.384, 0.015384),
]


def _after(h, at: str) -> list[dict]:
    t0 = datetime.fromisoformat(at)
    return [r for r in h["ledger"] if datetime.fromisoformat(r["at"]) > t0]


def test_1024_matches_screenshot(h) -> None:
    """
    اسکرین‌شات ۲۴ اکتبر = وضعیت فعلی منهای ردیف‌های دفتر کل پس از آن — متن ۱۹: فروش ETH
    با ابطال و سود تتر ۲۶ اکتبر. پیش از این برابری مستقیم بود و با هر ثبت تازه می‌شکست.
    """
    pos = {p["symbol"]: p for p in h["positions"]}
    assert {s for s, p in pos.items() if p["status"] == "open"} == set(SEEN_1024)
    later = _after(h, AT_1024)
    for sym, q in SEEN_1024.items():
        moved = sum(r["delta"] for r in later if r["symbol"] == sym and sym != "USDT")
        assert P.position_qty(pos[sym]) - moved == pytest.approx(q, abs=1e-12), sym
    cash = sum(r.get("net") or 0.0 for r in later if r["action"] in ("trim", "exit"))
    cash += sum(r["cash"]["qty"] for r in later if r["action"] == "income")
    cash -= sum(r["cash"]["qty"] for r in later if r["action"] == "withdraw")
    cash -= sum(r.get("cost") or 0.0 for r in later if r["action"] == "reenter")
    assert [c["account"] for c in h["cash"]] == ["LBank"]
    assert h["cash"][0]["qty"] - cash == pytest.approx(USDT_1024, abs=1e-9)


def test_1024_sales_rows_and_optcost(h) -> None:
    oc = json.loads((ROOT / "radar_optcost.json").read_text(encoding="utf-8"))
    for sym, q, px, at, oid, gross, fee in SALES_1024:
        rows = [r for r in h["ledger"] if r.get("order_id") == oid]
        assert len(rows) == 1, oid
        r = rows[0]
        assert (r["action"], r["symbol"], r["delta"], r["price"], r["reason"], r["account"],
                r["at"]) == ("trim", sym, -q, px, "reserve", "LBank", at)
        assert (r["gross"], r["fee"]) == (gross, fee) and gross == pytest.approx(q * px)
        assert r["net"] == pytest.approx(gross - fee, abs=1e-9)
        assert [x for x in oc["exits"] if x.get("order_id") == oid and x["at"] == at]


def test_1023_usdt_income(h) -> None:
    rows = [r for r in h["ledger"] if r["action"] == "income"]
    assert len(rows) == 1
    r = rows[0]
    assert (r["symbol"], r["delta"], r["account"], r["at"]) ==         ("USDT", 0.357453, "LBank", "2026-10-23T12:50:00+00:00")
    assert r["reason"] == "سود خودکار تتر LBank، تجمعی ۱۷ تا ۲۳ اکتبر"
    assert r["cash"] == {"asset": "USDT", "qty": 0.357453, "account": "LBank"}


def test_1024_cash_equations() -> None:
    """دو معادله وارسی متن ۱۶ — محاسبه‌شده از اسکرین‌شات‌ها."""
    assert 234.98925749 + 184.26 - 0.18426 == pytest.approx(419.06499749, abs=1e-9)
    after_income = 419.06499749 + 0.357453
    assert after_income == pytest.approx(419.42245049, abs=1e-9)
    assert (after_income + 39.12672 - 0.078253 + 88.12697 - 0.088127 + 15.384 - 0.015384
            == pytest.approx(USDT_1024, abs=1e-9))


def test_1024_tao_dust_has_no_level(h) -> None:
    """مانده TAO ناچیز است، مثل BNB: سطح ابطال ندارد؛ کف 202.51 فقط در نقشه بازخرید."""
    tao = next(p for p in h["positions"] if p["symbol"] == "TAO")
    bnb = next(p for p in h["positions"] if p["symbol"] == "BNB")
    assert tao["invalidation"] is None and "invalidation_since" not in tao
    assert {k for k in tao if k != "lots"} == {k for k in bnb if k != "lots"}
    assert 0.000092 * 254.4 < P.DUST_USD
