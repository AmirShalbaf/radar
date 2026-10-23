"""
کسری پس از نقشه و برچسب «مهلت گذشته» — بازبینی عمیق ۲۳ اکتبر ۲۰۲۶، یافته م۱.

پیش از این تا نقشه ذخیره پله مانده داشت، ردیف کسری اصلاً ساخته نمی‌شد و
بخش ۱ «نقشه ذخیره فعال است» می‌گفت — حتی چهار روز پس از مهلت. گزارش سبد
۲۲ اکتبر، محاسبه‌شده: اگر پله ETH پر شود ذخیره 419 از 1653، یعنی 25.4٪؛
هدف انقباضی 40٪ یعنی 661؛ کسری پس از نقشه 242 دلار در هیچ ردیف اقدامی نبود.

قرارداد:
- بخش ۶، جدول نقشه: ردیف «کسری پس از نقشه» — عدد، یا «هیچ» اگر نقشه به هدف
  می‌رسد، یا «داده ندارم» با دلیل.
- فهرست اقدام: اگر کسری پس از نقشه مثبت است، یک ردیف صریح با تصمیم لازم.
- پس از مهلت، بخش ۱ و ۵ «نقشه مهلت‌گذشته» می‌گویند، نه «نقشه فعال».
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_budget as BG

UTC = timezone.utc
LIVE = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
LATE = datetime(2026, 10, 22, 12, 17, tzinfo=UTC)

PLAN = {"title": "نقشه ذخیره ۱۷ اکتبر — پس از برداشت تتر",
        "created": "2026-10-17T15:32:00+00:00", "deadline": "2026-10-19T00:00:00+00:00",
        "account": "LBank",
        "on_deadline": {"cancel_if_band_at_least": "سازنده", "otherwise": "market"},
        "steps": [{"symbol": "ETH", "qty": 0.074, "price": 2490}]}
ETH_Q, SOL_Q, STABLE = 0.148257, 5.631054, 234.98925749
PRICES = {"ETH": 2405.07, "SOL": 104.51}
H = {"positions": [
        {"symbol": "ETH", "book": "position", "status": "open", "invalidation": 2380.5606,
         "lots": [{"qty": ETH_Q, "account": "LBank", "entry": None}]},
        {"symbol": "SOL", "book": "position", "status": "open", "invalidation": 96.7108,
         "lots": [{"qty": SOL_Q, "account": "LBank", "entry": None}]}],
     "ledger": [], "updated": "2026-10-17T20:42:09+00:00", "source": "آزمون"}
TOTAL = ETH_Q * 2405.07 + SOL_Q * 104.51 + STABLE
VAL = {"total": TOTAL, "stable_usd": STABLE, "incomplete": False, "missing": []}

# روش ک۴۲ — همان عدد «اگر همه پر شوند» گزارش
PROCEEDS = 0.074 * 2490 * (1 - B.RESERVE_FEE)
AFTER_STABLE = STABLE + PROCEEDS
AFTER_TOTAL = TOTAL - ETH_Q * 2405.07 + (ETH_Q - 0.074) * 2490 + PROCEEDS


def _report(now, band="انقباضی", prices=PRICES) -> str:
    reg = BG.band_by_name(band)
    view = B.reserve_view(PLAN, H, prices, VAL, now, band=band)
    return B.build_report(H, [], reg, [], "آزمون", val=VAL, reserve=view, tband=reg)


def _section(txt: str, n: str) -> str:
    start = txt.index(f"## {n} —")
    nxt = txt.find("\n## ", start + 1)
    return txt[start: nxt if nxt > 0 else None]


def _actions(txt: str) -> list[str]:
    return [l for l in _section(txt, "۶").split("\n") if l[:2].strip().rstrip(".").isdigit()]


def test_numbers_are_the_k42_method() -> None:
    gap = 0.40 * AFTER_TOTAL - AFTER_STABLE
    assert gap == pytest.approx(57.9, abs=0.1)              # محاسبه‌شده با همین داده
    v = B.reserve_view(PLAN, H, PRICES, VAL, LATE, band="انقباضی")
    assert v["after"]["stable"] == pytest.approx(AFTER_STABLE)
    assert v["after"]["total"] == pytest.approx(AFTER_TOTAL)


@pytest.mark.parametrize("now", [LIVE, LATE])
def test_gap_after_plan_row_and_action(now) -> None:
    txt = _report(now)
    gap = 0.40 * AFTER_TOTAL - AFTER_STABLE
    assert f"| کسری پس از نقشه | {gap:,.0f} دلار" in _section(txt, "۶")
    acts = [a for a in _actions(txt) if "کسری پس از نقشه" in a]
    assert len(acts) == 1 and f"{gap:,.0f} دلار" in acts[0] and "تصمیم لازم است" in acts[0]


def test_plan_that_reaches_target_has_no_gap_action() -> None:
    txt = _report(LATE, band="محتاط")                        # هدف 25٪ کمتر از 35٪ پس از نقشه
    assert "| کسری پس از نقشه | هیچ — نقشه به هدف 25٪ می‌رسد |" in _section(txt, "۶")
    assert not [a for a in _actions(txt) if "کسری پس از نقشه" in a]


def test_gap_after_plan_without_price_is_no_data() -> None:
    txt = _report(LATE, prices={"SOL": 104.51})
    assert "| کسری پس از نقشه | داده ندارم — قیمت زنده نیامد: ETH |" in _section(txt, "۶")


def test_expired_plan_is_labelled_not_active() -> None:
    txt = _report(LATE)
    one, five = _section(txt, "۱"), _section(txt, "۵")
    assert "نقشه ذخیره فعال است" not in one
    assert "مهلت نقشه ذخیره گذشت" in one and "2026-10-19 00:00 UTC" in one
    assert "نقشه فعال" not in five and "نقشه مهلت‌گذشته" in five


def test_live_plan_keeps_active_label() -> None:
    txt = _report(LIVE)
    assert "نقشه ذخیره فعال است" in _section(txt, "۱")
    assert "نقشه فعال" in _section(txt, "۵")
