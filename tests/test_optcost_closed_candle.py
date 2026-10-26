"""
ت۱ بازبینی ۲۳ اکتبر — متن ۱۸. پیگیری ۱۴ و ۳۰ روزه دفتر هزینه فرصت فقط کندل روزانه‌ای را
می‌خواند که دقیقاً در «روز فروش + ۱۴ روز» یا «+ ۳۰ روز» بسته شده — نه نزدیک‌ترین کندل، که
در ساعت اجرای گردش‌کار کندل باز همان روز بود. شاهد: خروج ۳، ETH، 2478.62 ثبت شد؛ بسته
2026-10-16 00:00 بود 2441.81.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_optcost as RO

UTC = timezone.utc
DAY = 86_400_000


def _bars(start: datetime, days: int, now: datetime) -> list[dict]:
    """کندل روزانه از start تا امروز؛ بسته هر کندل = 1000 + شماره روز؛ آخری باز."""
    out = []
    t0 = int(start.timestamp() * 1000)
    for i in range(days + 1):
        ts = t0 + i * DAY
        if ts > int(now.timestamp() * 1000):
            break
        out.append({"ts": ts, "h": 0.0, "l": 0.0, "c": 1000.0 + i})
    return out


def test_close_at_picks_candle_closed_exactly_then() -> None:
    start = datetime(2026, 10, 2, tzinfo=UTC)
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    bars = _bars(start, 20, now)
    tgt = int((start + timedelta(days=14)).timestamp() * 1000)
    # کندل باز شده در ۱۵ اکتبر، بسته در ۱۶ اکتبر ۰۰:۰۰ — شماره ۱۳
    assert RO.close_at(bars, tgt, int(now.timestamp() * 1000)) == 1013.0
    # کندل بسته‌نشده: هدف در آینده
    assert RO.close_at(bars, tgt + DAY, int(now.timestamp() * 1000)) is None
    # کندل غایب
    assert RO.close_at([b for b in bars if b["c"] != 1013.0], tgt,
                       int(now.timestamp() * 1000)) is None


def test_followup_uses_closed_candle_and_refill(tmp_path, monkeypatch, capsys) -> None:
    now = datetime.now(UTC)
    start = (now - timedelta(days=20)).replace(hour=0, minute=0, second=0, microsecond=0)
    bars = _bars(start - timedelta(days=2), 40, now)
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: bars)
    d = {"rejects": [], "sessions": [], "exits": []}
    rec = RO.add_exit(d, symbol="ETH", action="trim", qty=1.0, price=1000.0, reason="reserve",
                      at=start.isoformat())
    RO.save(d, str(tmp_path / "oc.json"))
    monkeypatch.setattr(RO, "FILE", str(tmp_path / "oc.json"))
    RO._followup_exits(d)
    # روز فروش + ۱۴ = کندل باز شده در روز ۱۳ پس از فروش؛ bars از دو روز پیش شروع شد
    assert d["exits"][0]["p14"] == 1000.0 + 2 + 13
    assert d["exits"][0]["p30"] is None
    # پرکردن دوباره: مقدار غلط پاک و دوباره پر
    d["exits"][0]["p14"] = 1234.5
    n = RO.refill(d, [rec["id"]])
    assert n == 1 and d["exits"][0]["p14"] is None and d["exits"][0]["saved14"] is None
    RO._followup_exits(d)
    assert d["exits"][0]["p14"] == 1015.0


def test_followup_missing_closed_candle_stays_empty(monkeypatch, capsys) -> None:
    now = datetime.now(UTC)
    start = (now - timedelta(days=20)).replace(hour=0, minute=0, second=0, microsecond=0)
    bars = [b for b in _bars(start - timedelta(days=2), 40, now) if b["c"] != 1015.0]
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: bars)
    d = {"rejects": [], "sessions": [], "exits": []}
    RO.add_exit(d, symbol="ETH", action="trim", qty=1.0, price=1000.0, reason="reserve",
                at=start.isoformat())
    RO._followup_exits(d)
    assert d["exits"][0]["p14"] is None
    assert "داده ندارم" in capsys.readouterr().out


def test_reject_followup_uses_closed_candle(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    start = (now - timedelta(days=20)).replace(hour=0, minute=0, second=0, microsecond=0)
    bars = _bars(start - timedelta(days=2), 40, now)
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: bars)
    p = tmp_path / "oc.json"
    p.write_text(json.dumps({"rejects": [{"id": 1, "date": start.strftime("%Y-%m-%d"),
                                          "symbol": "ETH", "price": 1000.0, "blocker": "x",
                                          "entry": None, "stop": None, "target": None,
                                          "p14": None, "p30": None, "r_lost": None,
                                          "r_note": None}],
                             "sessions": [], "exits": []}), encoding="utf-8")
    monkeypatch.setattr(RO, "FILE", str(p))
    RO.cmd_followup(type("A", (), {"refill": None})())
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["rejects"][0]["p14"] == 1015.0


def test_refill_reject_rewrites_old_record(tmp_path, monkeypatch) -> None:
    """ک۱۰۶، متن ۱۹: رد ZEC ۲۲ اوت — عمر بیش از ۳۵ روز و R پرشده؛ فقط با --refill-reject."""
    now = datetime.now(UTC)
    start = (now - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
    bars = _bars(start - timedelta(days=2), 70, now)
    monkeypatch.setattr(RO, "candles_since", lambda sym, days: bars)
    p = tmp_path / "oc.json"
    rec = {"id": 1, "date": start.strftime("%Y-%m-%d"), "symbol": "ZEC", "price": 1000.0,
           "blocker": "x", "entry": 1000.0, "stop": 900.0, "target": 1100.0, "p14": 1234.5,
           "p30": 2345.6, "r_lost": 0.5, "r_note": "پیشین"}
    p.write_text(json.dumps({"rejects": [rec], "sessions": [], "exits": []}), encoding="utf-8")
    monkeypatch.setattr(RO, "FILE", str(p))
    RO.cmd_followup(type("A", (), {"refill": None, "refill_reject": None})())
    assert json.loads(p.read_text(encoding="utf-8"))["rejects"][0]["p14"] == 1234.5
    RO.cmd_followup(type("A", (), {"refill": None, "refill_reject": "1"})())
    r = json.loads(p.read_text(encoding="utf-8"))["rejects"][0]
    assert r["p14"] == 1015.0 and r["p30"] == 1031.0
