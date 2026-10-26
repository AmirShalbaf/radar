"""
فهرست سفارش‌های زنده — بند ۱ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

ساختار ساده در watch.json بخش orders: نماد، سمت، نوع، مقدار، قیمت، ماشه، شناسه، دفتر،
هدف، زمان ثبت. با validate. دو سفارش زنده از یادداشت نقشه بایگانی‌شده ۲۴ اکتبر به این
ساختار رفتند. در پیام روزانه تلگرام و در هشدار تکان نشان داده می‌شوند — فقط نمایش.
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_watch as W

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 10, 27, 8, 41, tzinfo=UTC)

ETH = {"symbol": "ETH", "side": "buy", "type": "trigger", "qty": 0.037, "price": 2550,
       "trigger": 2535, "order_id": "e01c4e5c-d85c-41fc-aac4-805c985be802", "book": "trade",
       "purpose": "ستاپ ب۱", "recorded_at": "2026-10-26T07:35:00+00:00",
       "note": "استثنای آگاهانه: اگر پر شود، ذخیره موقتاً حدود ۳۵٪"}
TAO = {"symbol": "TAO", "side": "buy", "type": "limit", "qty": 0.153, "price": 233,
       "trigger": None, "order_id": "d320d08b-4974-4ce2-9bd5-ec6b472ec7c8", "book": "position",
       "purpose": "بازخرید", "recorded_at": "2026-10-26T07:35:00+00:00"}


def _w(*orders):
    return {"orders": [copy.deepcopy(o) for o in orders]}


def _real():
    return json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))


# ── اعتبارسنجی ──

def test_valid_orders_pass() -> None:
    W.validate_watch(_w(ETH, TAO))


@pytest.mark.parametrize("field,bad,needle", [
    ("side", "long", "سمت"),
    ("type", "market", "نوع"),
    ("qty", 0, "مقدار"),
    ("price", -1, "قیمت"),
    ("order_id", "", "شناسه"),
    ("book", "spot", "دفتر"),
    ("purpose", " ", "هدف"),
    ("recorded_at", "2026-10-26", "recorded_at"),
])
def test_bad_field_is_loud(field, bad, needle) -> None:
    o = dict(TAO, **{field: bad})
    with pytest.raises(W.WatchError, match=needle):
        W.validate_watch(_w(o))


def test_trigger_rules() -> None:
    # ماشه‌دار بی ماشه، و محدود با ماشه — هر دو خطای صریح
    with pytest.raises(W.WatchError, match="ماشه"):
        W.validate_watch(_w(dict(ETH, trigger=None)))
    with pytest.raises(W.WatchError, match="ماشه"):
        W.validate_watch(_w(dict(TAO, trigger=230)))


def test_duplicate_order_id_is_loud() -> None:
    with pytest.raises(W.WatchError, match="تکراری"):
        W.validate_watch(_w(TAO, dict(ETH, order_id=TAO["order_id"])))


def test_orders_must_be_list() -> None:
    with pytest.raises(W.WatchError, match="orders"):
        W.validate_watch({"orders": {"ETH": 1}})


# ── داده واقعی: دو سفارش از یادداشت نقشه ۲۴ اکتبر ──

def test_real_watch_has_the_two_live_orders() -> None:
    w = _real()
    W.validate_watch(w)
    got = {o["order_id"]: o for o in w["orders"]}
    assert set(got) == {ETH["order_id"], TAO["order_id"]}
    for want in (ETH, TAO):
        o = got[want["order_id"]]
        for k, v in want.items():
            assert o.get(k) == v, (want["symbol"], k, o.get(k))


# ── نمایش ──

def test_order_lines_text() -> None:
    lines = W.order_lines(_w(ETH, TAO))
    assert len(lines) == 2
    eth, tao = lines
    assert "خرید ماشه‌دار ETH 0.037" in eth and "ماشه 2535" in eth and "حد 2550" in eth
    assert "دفتر معامله" in eth and "ستاپ ب۱" in eth and "۳۵٪" in eth
    assert "e01c4e5c" in eth
    assert "خرید محدود TAO 0.153 در 233" in tao and "دفتر موقعیت" in tao and "بازخرید" in tao
    assert W.order_lines({}) == []


def test_orders_section_cli(tmp_path, capsys) -> None:
    p = tmp_path / "w.json"
    p.write_text(json.dumps(_w(ETH, TAO), ensure_ascii=False), encoding="utf-8")
    assert W.main(["--orders", "--watch", str(p)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## سفارش‌های زنده")
    assert "ETH" in out and "TAO" in out and "فقط نمایش" in out


def test_orders_section_empty_and_bad(tmp_path, capsys) -> None:
    p = tmp_path / "w.json"
    p.write_text("{}", encoding="utf-8")
    assert W.main(["--orders", "--watch", str(p)]) == 0
    assert "سفارش زنده‌ای ثبت نشده" in capsys.readouterr().out
    p.write_text(json.dumps(_w(dict(TAO, side="x"))), encoding="utf-8")
    assert W.main(["--orders", "--watch", str(p)]) == 2
    assert "سمت" in capsys.readouterr().out


# ── هشدار تکان ──

def _bars(closes, end=NOW):
    last_open = end.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return [{"open": last_open - timedelta(hours=len(closes) - 1 - i), "close": float(c),
             "low": float(c) * 0.999, "high": float(c) * 1.001} for i, c in enumerate(closes)]


def test_shake_alert_shows_live_orders() -> None:
    w = {"positions": [{"symbol": "SOL", "invalidation": 96.7108,
                        "invalidation_since": "2026-09-25T21:34:47+00:00"}],
         "orders": [ETH, TAO]}
    h = {"positions": [{"symbol": "SOL", "book": "position", "status": "open",
                        "invalidation": 96.7108,
                        "invalidation_since": "2026-09-25T21:34:47+00:00",
                        "lots": [{"qty": 5.0, "account": "LBank", "entry": None}]}],
         "ledger": [], "cash": []}
    btc = [80000.0] * 26 + [81000, 82000, 83000, 84500.0]          # +5.6٪ در ۴ ساعت
    feed = {"BTC": _bars(btc), "SOL": _bars([110.0] * 30)}
    msgs = W.shake_alerts(w, h, {}, NOW, hourly=lambda s: (feed.get(s), []),
                          sigma=lambda s, hrs: (None, ["آزمون"]))
    assert len(msgs) == 1
    m = msgs[0]
    assert "سفارش‌های زنده:" in m
    assert "خرید ماشه‌دار ETH 0.037" in m and "خرید محدود TAO 0.153 در 233" in m
    # بی سفارش، بی سطر
    w.pop("orders")
    msgs = W.shake_alerts(w, h, {}, NOW, hourly=lambda s: (feed.get(s), []),
                          sigma=lambda s, hrs: (None, ["آزمون"]))
    assert "سفارش‌های زنده" not in msgs[0]


def test_shake_action_points_to_same_symbol_order() -> None:
    sol_order = dict(TAO, symbol="SOL", price=95.0, order_id="x-1")
    w = {"positions": [{"symbol": "SOL", "invalidation": 96.7108,
                        "invalidation_since": "2026-09-25T21:34:47+00:00"}],
         "orders": [sol_order]}
    h = {"positions": [{"symbol": "SOL", "book": "position", "status": "open",
                        "invalidation": 96.7108,
                        "invalidation_since": "2026-09-25T21:34:47+00:00",
                        "lots": [{"qty": 5.0, "account": "LBank", "entry": None}]}],
         "ledger": [], "cash": []}
    sol = [100.0] * 26 + [101, 102, 104, 105.0]
    feed = {"BTC": _bars([80000.0] * 30), "SOL": _bars(sol)}
    m = W.shake_alerts(w, h, {}, NOW, hourly=lambda s: (feed.get(s), []),
                       sigma=lambda s, hrs: (None, ["آزمون"]))[0]
    assert "اقدام: سفارش زنده SOL را ببین" in m


def test_daily_workflow_puts_orders_in_telegram_part() -> None:
    """بخش سفارش در LATEST.md پیش از نشانه بخش رویداد — همان بخشی که به تلگرام می‌رود."""
    y = (ROOT / ".github" / "workflows" / "radar-daily.yml").read_text(encoding="utf-8")
    assert "python radar_watch.py --orders --watch watch.json > /tmp/orders.md" in y
    head = y.index("# گزارش رادار — $D")
    cat = y.index("cat /tmp/orders.md", head)
    assert y.index("} > reports/LATEST.md") > cat
    assert cat < y.index('echo "<!-- رویداد-آغاز -->"')
