"""
بخش ۶ گزارش سبد و نقشه ذخیره فعال — نشست ۳ب، بند ۶.

ایراد پیداشده پس از پوش نشست ۳، ۲۶ سپتامبر: بخش ۶ book-2026-09-26.md گفت
«فروش 437 دلار به ترتیب بخش ۵» — یعنی ETH، BNB، SOL… — و reserve_plan فعال
watch.json را نمی‌دید. نقشه آگاهانه از آن ترتیب منحرف است — رویداد ۳۶.

قرارداد:
- نقشه فعال و مهلت نگذشته: بخش ۶ پیشرفت نقشه را نشان می‌دهد — پله‌های
  اجراشده با قیمت و زمان پرشدن از دفتر کل؛ پله‌های مانده با نماد، مقدار و
  قیمت محدود؛ مهلت؛ ذخیره امروز؛ و ذخیره اگر همه پر شوند، روش ک۴۲: هر پله در
  قیمت خودش، کارمزد 0.1٪، بقیه قیمت‌ها مثل امروز.
- بخش ۵ مرجع می‌ماند، با یک سطر انحراف آگاهانه.
- پس از مهلت با پله مانده: صریح می‌گوید و تصمیم می‌خواهد؛ بازگشت بی‌صدا به
  فهرست فروش نه.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_watch as W

UTC = timezone.utc
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

PLAN = {
    "created": "2026-09-25T16:00:00+00:00", "deadline": "2026-10-05T00:00:00+00:00",
    "account": "LBank",
    "steps": [
        {"symbol": "ETH", "qty": 0.0472, "price": None,
         "executed": {"at": "2026-09-25T22:10:21+00:00", "order_id": "e6c7"}},
        {"symbol": "ETH", "qty": 0.0472, "price": 2790},
        {"symbol": "ETH", "qty": 0.0472, "price": 2940},
        {"symbol": "SOL", "qty": 0.749, "price": None,
         "executed": {"at": "2026-09-25T22:09:00+00:00", "order_id": "6663"}},
        {"symbol": "SOL", "qty": 0.749, "price": 125.5},
        {"symbol": "SOL", "qty": 0.749, "price": 131.5},
    ]}
LEDGER = [
    {"at": "2026-09-25T22:09:00+00:00", "action": "trim", "symbol": "SOL", "delta": -0.749,
     "price": 121.33, "reason": "reserve"},
    {"at": "2026-09-25T22:10:21+00:00", "action": "trim", "symbol": "ETH", "delta": -0.0472,
     "price": 2685.33, "reason": "reserve"},
]
H = {"positions": [], "ledger": LEDGER, "updated": "2026-09-26T05:10:00+00:00",
     "source": "آزمون"}
PRICES = {"ETH": 2684.18, "SOL": 121.35}
VAL = {"total": 2633.0, "stable_usd": 221.0, "incomplete": False, "missing": []}
REG = {"name": "محتاط", "cap": 4.0, "mult": 0.5, "maxpos": 3, "stable": 25}


def _view(now=NOW, plan=PLAN, h=H):
    return B.reserve_view(plan, h, PRICES, VAL, now)


def _report(view) -> str:
    return B.build_report(H, [], REG, [], "آزمون", val=VAL, reserve=view)


def _section(txt: str, n: str) -> str:
    start = txt.index(f"## {n} —")
    nxt = txt.find("\n## ", start + 1)
    return txt[start: nxt if nxt > 0 else None]


# ═══════════════ پیشرفت پله‌ها — از دفتر کل ═══════════════

def test_progress_fill_price_and_time_from_ledger() -> None:
    prog = W.reserve_progress(PLAN, H)
    assert [p["filled"] for p in prog] == [True, False, False, True, False, False]
    eth = prog[0]
    assert eth["fill_price"] == 2685.33
    assert eth["fill_at"] == datetime.fromisoformat("2026-09-25T22:10:21+00:00")
    assert prog[1]["fill_price"] is None and prog[1]["fill_at"] is None


def test_progress_agrees_with_step_filled() -> None:
    """step_filled تنها تعریف «پرشده» است — پایشگر و سبد یکی."""
    assert [p["filled"] for p in W.reserve_progress(PLAN, H)] == W.step_filled(PLAN, H)


# ═══════════════ عدد ذخیره اگر همه پر شوند — روش ک۴۲ ═══════════════

def test_if_all_filled_k42_method() -> None:
    v = _view()
    fee = B.RESERVE_FEE
    assert fee == pytest.approx(0.001)
    proceeds = (0.0472 * 2790 + 0.0472 * 2940 + 0.749 * 125.5 + 0.749 * 131.5) * (1 - fee)
    sold_now = 0.0944 * 2684.18 + 1.498 * 121.35
    assert v["after"]["stable"] == pytest.approx(221.0 + proceeds)
    assert v["after"]["total"] == pytest.approx(2633.0 - sold_now + proceeds)
    assert v["after"]["pct"] == pytest.approx(100 * (221.0 + proceeds)
                                              / (2633.0 - sold_now + proceeds))


def test_if_all_filled_needs_live_price() -> None:
    v = B.reserve_view(PLAN, H, {"ETH": 2684.18}, VAL, NOW)
    assert v["after"] is None and v["missing"] == ["SOL"]


# ═══════════════ گزارش ═══════════════

def test_section6_shows_plan_not_sell_order() -> None:
    s6 = _section(_report(_view()), "۶")
    assert "به ترتیب بخش ۵" not in s6
    for x in ("2685.33", "2026-09-25 22:10", "121.33", "2026-09-25 22:09",
              "2790", "2940", "125.5", "131.5", "0.0472", "0.749",
              "2026-10-05 00:00", "رویداد ۳۶"):
        assert x in s6, x
    v = _view()
    assert f"{v['after']['stable']:,.0f}" in s6
    assert f"{v['after']['pct']:.1f}٪" in s6
    assert "221" in s6                              # ذخیره امروز


def test_section5_stays_with_deviation_line() -> None:
    s5 = _section(_report(_view()), "۵")
    assert "نقشه فعال آگاهانه از این ترتیب منحرف است — رویداد ۳۶" in s5


def test_section1_points_to_plan() -> None:
    s1 = _section(_report(_view()), "۱")
    assert "ترتیب فروش در بخش ۵" not in s1
    assert "بخش ۶" in s1


def test_after_deadline_asks_for_decision() -> None:
    s6 = _section(_report(_view(now=datetime(2026, 10, 5, 1, tzinfo=UTC))), "۶")
    assert "مهلت" in s6 and "گذشت" in s6 and "تصمیم" in s6
    assert "به ترتیب بخش ۵" not in s6
    for x in ("2790", "2940", "125.5", "131.5"):
        assert x in s6


def test_no_plan_keeps_sell_order() -> None:
    """قفل: بی‌نقشه، رفتار پیشین — فروش به ترتیب بخش ۵."""
    s6 = _section(_report(None), "۶")
    assert "به ترتیب بخش ۵" in s6


def test_completed_plan_with_gap_asks_for_decision() -> None:
    h = dict(H, ledger=LEDGER + [
        {"at": f"2026-09-2{d}T10:00:00+00:00", "action": "trim", "symbol": s, "delta": -q,
         "price": p, "reason": "reserve"}
        for d, s, q, p in ((6, "ETH", 0.0472, 2790), (7, "ETH", 0.0472, 2940),
                           (6, "SOL", 0.749, 125.5), (7, "SOL", 0.749, 131.5))])
    s6 = _section(_report(_view(h=h)), "۶")
    assert "کامل شد" in s6 and "تصمیم" in s6
    assert "به ترتیب بخش ۵" not in s6


def test_stray_mark_is_loud() -> None:
    """علامت اجراشده در watch.json بی‌ردیف دفتر کل پر حساب نمی‌شود — و گفته می‌شود."""
    s6 = _section(_report(_view(h=dict(H, ledger=[]))), "۶")
    assert "دفتر کل" in s6 and "e6c7" in s6


def test_main_reads_plan_from_watch(tmp_path, monkeypatch) -> None:
    import json
    import radar_positions as P
    monkeypatch.chdir(tmp_path)
    (tmp_path / "watch.json").write_text(json.dumps(
        {"version": 2, "updated": "2026-09-26T05:04:16+00:00", "positions": [],
         "reserve_plan": PLAN, "items": []}), encoding="utf-8")
    monkeypatch.setattr(P, "load", lambda *a, **k: (dict(H, positions=[], cash=[]), {}))
    monkeypatch.setattr(B, "candles", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["radar_book.py", "--regime", "-0.05", "--out", "o.md"])
    B.main()
    s6 = _section((tmp_path / "o.md").read_text(encoding="utf-8"), "۶")
    assert "2790" in s6 and "به ترتیب بخش ۵" not in s6
