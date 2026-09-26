"""
میانگین ساده ۵۰ هفته بیت‌کوین از regime.json — نشست ۳، ایستگاه آخر، بند ۴.

عدد ثابت 78822.35 در watch.json از بسته ۲۸ سپتامبر کهنه می‌شد. حالا:
- radar_positions.sma_weekly: بسته‌های هفتگی وقت جهانی، فقط هفته‌های
  بسته‌شده، لنگر دوشنبه ۰۰:۰۰ برای همه ردیف‌ها — همان واکشی weekly_close.
- radar_regime میدان btc_sma50w را می‌نویسد: مقدار، هفته، بسته همان هفته.
  میدان ma50w پیشین رژیم کندل هفتگی لنگر هنگ‌کنگ دارد — تعریف دیگری است.
- پایشگر عدد را از regime.json می‌خواند و فقط بسته همان هفته را با آن
  می‌سنجد. regime.json کهنه یا بی‌میدان: هشدار صریح.
- عدد ثابت در watch.json مجاز نیست.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_regime as G
import radar_watch as W

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
MON0 = datetime(2025, 9, 1, tzinfo=UTC)          # دوشنبه


class _Resp:
    def __init__(self, js, code=200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


def _okx_get(n_closed=55, anchor_ok=True):
    """ردیف‌های اوکی‌اکس، تازه‌ترین اول؛ آخری باز. بسته هفته k برابر 100+k."""
    rows = []
    for k in range(n_closed + 1):
        op = MON0 + timedelta(weeks=k)
        if not anchor_ok:
            op -= timedelta(hours=8)
        confirm = "0" if k == n_closed else "1"
        rows.append([str(int(op.timestamp() * 1000)), "1", "1", "1", str(100.0 + k),
                     "1", "1", "1", confirm])
    rows.reverse()

    def get(url, params=None, timeout=None):
        if "okx" in url:
            assert params["bar"] == "1Wutc"
            return _Resp({"code": "0", "data": rows[: int(params["limit"])]})
        return _Resp([], 500)
    return get


NOW = MON0 + timedelta(weeks=55, hours=5)


def test_weekly_closes_utc_closed_only() -> None:
    rows, why = P.weekly_closes("BTC", 50, get=_okx_get(), now=NOW)
    assert rows is not None, why
    assert len(rows) == 50
    assert rows[-1]["closed_at"] == (MON0 + timedelta(weeks=55)).isoformat()
    assert rows[-1]["close"] == 154.0                  # هفته باز کنار رفت
    assert all(datetime.fromisoformat(r["week_open"]).weekday() == 0 for r in rows)


def test_wrong_anchor_is_no_data() -> None:
    rows, why = P.weekly_closes("BTC", 50, get=_okx_get(anchor_ok=False), now=NOW)
    assert rows is None and any("لنگر" in w for w in why)


def test_sma_weekly_value_and_week() -> None:
    s, why = P.sma_weekly("BTC", 50, get=_okx_get(), now=NOW)
    assert s["value"] == pytest.approx(sum(100.0 + k for k in range(5, 55)) / 50)
    assert s["close"] == 154.0 and s["weeks"] == 50
    assert s["week_closed_at"] == (MON0 + timedelta(weeks=55)).isoformat()


def test_sma_weekly_immature() -> None:
    s, why = P.sma_weekly("BTC", 50, get=_okx_get(n_closed=30), now=MON0 + timedelta(weeks=30, hours=5))
    assert s is None and any("نابالغ" in w for w in why)


# ═══════════════ radar_regime ═══════════════

def _inputs(score: float) -> dict:
    return {k: G.Input(key=k, column=c, label=l, weight=G.weights()[k], score=score)
            for k, (c, l) in G.INPUTS.items()}


SMA = {"value": 78822.35, "close": 81179.6, "week_closed_at": "2026-09-21T00:00:00+00:00",
       "week_open": "2026-09-14T00:00:00+00:00", "weeks": 50, "venue": "okx"}


def test_regime_doc_carries_btc_sma50w() -> None:
    now = datetime(2026, 9, 26, 6, 30, tzinfo=UTC)
    inp = _inputs(0.2)
    doc = G.build_doc(G.aggregate(inp), inp, now, btc_sma50w=SMA)
    assert doc["btc_sma50w"]["value"] == 78822.35
    assert "وقت جهانی" in doc["btc_sma50w"]["definition"]
    assert "78822.35" in G.render_md(doc)


def test_regime_doc_records_missing_reason() -> None:
    now = datetime(2026, 9, 26, 6, 30, tzinfo=UTC)
    inp = _inputs(0.2)
    doc = G.build_doc(G.aggregate(inp), inp, now, btc_sma50w=None,
                      btc_sma50w_why=["آزمون: نیامد"])
    assert doc["btc_sma50w"]["value"] is None
    assert "آزمون" in doc["btc_sma50w"]["reason"]


# ═══════════════ پایشگر ═══════════════

WEEK = "2026-09-28T00:00:00+00:00"


def _regime(value=80000.0, week=WEEK, age_days=0.2) -> dict:
    gen = datetime(2026, 9, 28, 7, tzinfo=UTC) - timedelta(days=age_days)
    return {"score": 0.1, "generated_at": gen.isoformat(),
            "btc_sma50w": {"value": value, "week_closed_at": week, "close": 79000.0,
                           "weeks": 50, "venue": "okx"}}


def _watch() -> dict:
    return {"version": 2, "updated": "2026-09-26T00:00:00+00:00",
            "market": [{"symbol": "BTC", "label": "میانگین ساده ۵۰ هفته",
                        "source": "regime.json btc_sma50w"}], "items": []}


ALERT = "📉 هشدار بازار"      # نشانه خود هشدار — متن «سنجیده نشد» هم «هشدار بازار» دارد


def _run(regime, close=79000.0, closed_at=WEEK, state=None):
    wk = lambda s: ({"close": close, "closed_at": closed_at, "venue": "okx"}, [])
    return W.check_positions(_watch(), {"positions": [], "ledger": []},
                             {} if state is None else state,
                             datetime(2026, 9, 28, 8, tzinfo=UTC),
                             weekly=wk, price=lambda s: None, regime=regime)


def test_market_alert_from_regime_same_week_once() -> None:
    st = {}
    m = next(x for x in _run(_regime(), state=st) if ALERT in x)
    assert "79000" in m and "80000" in m and "regime.json" in m
    assert not [x for x in _run(_regime(), state=st) if ALERT in x]


def test_no_alert_above_sma() -> None:
    assert not [x for x in _run(_regime(value=78000.0)) if ALERT in x]


def test_regime_week_older_than_close_waits() -> None:
    msgs = _run(_regime(week="2026-09-21T00:00:00+00:00"))
    assert not [x for x in msgs if ALERT in x]
    assert not [x for x in msgs if "کهنه" in x]


def test_stale_regime_is_explicit_warning() -> None:
    msgs = _run(_regime(age_days=8))
    assert any("regime.json" in x and "کهنه" in x for x in msgs)
    assert not [x for x in msgs if ALERT in x]


def test_missing_field_is_explicit_warning() -> None:
    r = _regime()
    del r["btc_sma50w"]
    assert any("btc_sma50w" in x for x in _run(r))
    assert any("regime.json" in x and "نیست" in x for x in _run(None))


def test_fixed_number_in_watch_is_rejected() -> None:
    w = _watch()
    w["market"][0]["weekly_close_below"] = 78822.35
    with pytest.raises(W.WatchError, match="regime.json"):
        W.validate_watch(w)


def test_real_watch_has_no_fixed_number() -> None:
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    W.validate_watch(w)
    assert all("weekly_close_below" not in m for m in w.get("market", []))


def test_watcher_main_reads_regime_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "watch.json").write_text(json.dumps(_watch(), ensure_ascii=False),
                                         encoding="utf-8")
    r = _regime()
    r["generated_at"] = datetime.now(UTC).isoformat()
    (tmp_path / "reg.json").write_text(json.dumps(r), encoding="utf-8")
    sent: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m))
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (
        {"close": 79000.0, "closed_at": WEEK, "venue": "okx"}, []))
    assert W.main(["--once", "--watch", "watch.json", "--regime-file", "reg.json"]) == 0
    assert any(ALERT in m for m in sent)
