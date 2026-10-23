"""
نقشه بی‌شرط پس از مهلت: «تصمیم با تو» در هر سه جا — بازبینی ۲۳ اکتبر ۲۰۲۶، یافته ت۳.

تعریف plan_rule_state برای no_rule می‌گوید «رفتار نقشه رویداد ۳۶: پس از مهلت تصمیم
لازم». سبد همین را می‌گفت، ولی پایشگر و پیام هفتگی «فروش در بازار» می‌گفتند — دو
حکم متضاد برای یک نقشه. نقشه فعلی شرط دارد، پس تا امروز نهفته بود.

قرارداد:
- پایشگر، پس از مهلت و بی on_deadline: پیام «تصمیم لازم» با پله‌های پرنشده، یک بار.
- پیام هفتگی: همان حالت ask — «تصمیم با تو».
- پیش از مهلت بی‌تغییر؛ نقشه با شرط بی‌تغییر.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_positions as P
import radar_watch as W

UTC = timezone.utc
LATE = datetime(2026, 10, 20, 5, 0, tzinfo=UTC)
CLOSE = "2026-10-19T00:00:00+00:00"
PLAN = {"title": "نقشه بی‌شرط", "created": "2026-10-17T15:32:00+00:00",
        "deadline": "2026-10-19T00:00:00+00:00", "account": "LBank",
        "steps": [{"symbol": "ETH", "qty": 0.074, "price": 2490}]}


def _watch(plan=PLAN) -> dict:
    return {"positions": [{"symbol": "ETH", "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"}],
            "reserve_plan": dict(plan)}


def _h() -> dict:
    return {"positions": [{"symbol": "ETH", "book": "position", "status": "open",
                           "invalidation": 2380.56,
                           "invalidation_since": "2026-09-25T21:34:47+00:00",
                           "lots": [{"qty": 0.148257, "account": "LBank", "entry": None}]}],
            "frozen": {"date": "2026-09-25", "members": {"ETH": 0.148257}, "cash": []},
            "ledger": []}


def _weekly(s):
    return ({"close": 2410.51, "closed_at": CLOSE, "venue": "okx",
             "week_open": "2026-10-12T00:00:00+00:00"}, [])


def _deadline_msgs(now, plan=PLAN, regime=None) -> list[str]:
    msgs = W.check_positions(_watch(plan), _h(), {}, now, weekly=_weekly,
                             price=lambda s: 2405.0, regime=regime)
    return [m for m in msgs if "⏰" in m]


def test_rule_state_is_no_rule() -> None:
    assert W.plan_rule_state(PLAN, None) == "no_rule"


def test_watch_expired_no_rule_asks_for_decision() -> None:
    m = _deadline_msgs(LATE)
    assert len(m) == 1
    assert "تصمیم لازم" in m[0] and "شرط مهلت ندارد" in m[0] and "ETH 0.074" in m[0]
    assert "فروش در قیمت بازار از" not in m[0] and "radar_positions.py trim" not in m[0]


def test_watch_expired_no_rule_once() -> None:
    st: dict = {}
    for _ in range(2):
        msgs = W.check_positions(_watch(), _h(), st, LATE, weekly=_weekly,
                                 price=lambda s: 2405.0)
        W.commit_sent(msgs, st)
    again = W.check_positions(_watch(), _h(), st, LATE, weekly=_weekly, price=lambda s: 2405.0)
    assert not [m for m in again if "⏰" in m]


def test_watch_with_rule_still_sells_at_market() -> None:
    plan = dict(PLAN, on_deadline={"cancel_if_band_at_least": "سازنده", "otherwise": "market"})
    reg = {"generated_at": LATE.isoformat(), "trade_band": {"name": "محتاط"}}
    m = _deadline_msgs(LATE, plan, reg)
    assert len(m) == 1 and "فروش در قیمت بازار از" in m[0] and "تصمیم لازم" not in m[0]


def test_digest_expired_no_rule_is_ask() -> None:
    _, text = W.weekly_digest(_watch(), _h(), {}, LATE, weekly=_weekly)
    assert "شرط مهلت ندارد" in text and "تصمیم با تو" in text
    assert "لغو کن و 0.074 را در بازار بفروش" not in text


def test_digest_before_deadline_unchanged() -> None:
    plan = dict(PLAN, deadline="2026-10-25T00:00:00+00:00")
    _, text = W.weekly_digest(_watch(plan), _h(), {}, LATE, weekly=_weekly)
    assert "🗓 مهلت نقشه بی‌شرط" in text and "تصمیم با تو" not in text


def test_book_says_the_same() -> None:
    val = P.value(dict(_h(), cash=[]), {"ETH": 2405.0})
    rv = B.reserve_view(PLAN, _h(), {"ETH": 2405.0}, val, LATE, band=None)
    acts = B._plan_actions(rv)
    assert rv["rule_state"] == "no_rule" and "تصمیم لازم است" in acts[0]
