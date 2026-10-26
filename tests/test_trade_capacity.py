"""
ظرفیت دفتر معامله — بند ۸ متن ۲۰، ۲۷ اکتبر ۲۰۲۶. فقط نمایش.

در گزارش سبد:
  - ظرفیت نقدی = ذخیره منهای هدف ذخیره — هدف از باند خام روز
  - ظرفیت آتی = بر پایه ریسک، زیر سقف ریسک باز رژیم — باند با هیسترزیس دفتر معامله
قاعده نیست: تصمیم کاربر درباره اجرای دفتر معامله با آتی هنوز نیامده؛ پس نه ردیف اقدام
می‌سازد، نه مانعی.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_budget as BG
import radar_positions as P

TIGHT = BG.band_by_name("انقباضی")            # هدف ذخیره ۴۰٪، سقف ریسک ۲٫۵٪
VAL = {"total": 1588.35, "stable_usd": 648.14, "incomplete": False, "missing": []}
H = {"positions": [], "cash": [], "ledger": []}
ORDERS = [
    {"symbol": "ETH", "side": "buy", "type": "trigger", "qty": 0.037, "price": 2550,
     "trigger": 2535, "order_id": "e01c4e5c", "book": "trade", "purpose": "ستاپ ب۱",
     "recorded_at": "2026-10-26T07:35:00+00:00"},
    {"symbol": "TAO", "side": "buy", "type": "limit", "qty": 0.153, "price": 233,
     "trigger": None, "order_id": "d320d08b", "book": "position", "purpose": "بازخرید",
     "recorded_at": "2026-10-26T07:35:00+00:00"},
]


def test_capacity_numbers() -> None:
    heat = P.trade_heat(H, TIGHT, VAL["total"])
    c = B.trade_capacity(VAL, TIGHT, TIGHT, heat, ORDERS)
    target = 0.40 * 1588.35
    assert abs(c["cash"] - (648.14 - target)) < 1e-9                 # 12.80
    assert abs(c["risk_cap"] - 0.025 * 1588.35) < 1e-9               # 39.71
    assert abs(c["risk_left"] - c["risk_cap"]) < 1e-9                # ریسک باز صفر
    assert abs(c["orders_usd"] - (0.037 * 2550 + 0.153 * 233)) < 1e-9
    assert abs(c["cash_after_orders"] - (c["cash"] - c["orders_usd"])) < 1e-9


def test_capacity_with_open_trade_risk() -> None:
    h = {"positions": [{"symbol": "SOL", "book": "trade", "status": "open", "side": "long",
                        "stop": 90.0, "lots": [{"qty": 1.0, "entry": 100.0, "account": "x"}]}],
         "cash": [], "ledger": []}
    heat = P.trade_heat(h, TIGHT, VAL["total"])
    c = B.trade_capacity(VAL, TIGHT, TIGHT, heat, [])
    assert abs(c["risk_left"] - (0.025 * 1588.35 - 10.0)) < 1e-9


def test_section_shown_and_labelled_display_only() -> None:
    heat = P.trade_heat(H, TIGHT, VAL["total"])
    txt = B.build_report(H, [], TIGHT, [], val=VAL, heat=heat, orders=ORDERS)
    sec3 = txt[txt.index("## ۳ — دفتر معامله"):txt.index("## ۴ —")]
    assert "ظرفیت دفتر معامله — فقط نمایش" in sec3
    assert "ظرفیت نقدی" in sec3 and "12.80" in sec3
    assert "ظرفیت آتی" in sec3 and "39.71" in sec3
    assert "تصمیم اجرای دفتر معامله با آتی هنوز نیامده" in sec3
    assert "130.00" in sec3                                          # تعهد سفارش‌های خرید زنده
    # قاعده نیست: هیچ ردیف اقدامی از ظرفیت
    sec6 = txt[txt.index("## ۶ —"):]
    assert "ظرفیت" not in sec6


def test_negative_cash_capacity_and_stale_regime() -> None:
    val = dict(VAL, stable_usd=500.0)
    heat = P.trade_heat(H, TIGHT, val["total"])
    c = B.trade_capacity(val, TIGHT, TIGHT, heat, [])
    assert c["cash"] < 0
    txt = B.build_report(H, [], TIGHT, [], val=val, heat=heat)
    assert "کسری" in txt[txt.index("ظرفیت دفتر معامله"):]
    txt = B.build_report(H, [], None, [], val=val)
    sec3 = txt[txt.index("## ۳ — دفتر معامله"):txt.index("## ۴ —")]
    assert "ظرفیت دفتر معامله" in sec3 and "رژیم کهنه" in sec3
