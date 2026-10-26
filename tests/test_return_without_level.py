"""
بازگشت بی‌سطح — بند ۹ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

اگر بازخرید ذخیره یا ورود دوباره برای ارزی ثبت شود که سطح ابطال ندارد — مثل ETH پس از
ابطال ۲۶ اکتبر — ثبت بدون سطح تازه پذیرفته نیست. سطح تازه یا با --level داده می‌شود، یا با
--suggest-level از همان روش pick_invalidation پیشنهاد می‌شود و کاربر با --level تأیید می‌کند.
ارز با همان سطح به پایش برمی‌گردد: holdings.json و watch.json، با لنگر.

داده: رونوشت holdings.json و watch.json واقعی — conftest — بی شبکه.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_watch as W

UTC = timezone.utc
AT = "2026-11-02T09:00:00+00:00"
PROPOSAL = {"level": 2210.5, "anchor": 2400.0, "atr_w": 150.0, "price": 2450.0,
            "week_close": 2400.0, "week_closed_at": "2026-11-02T00:00:00+00:00",
            "atr_d": 60.0, "touches": 3, "tf": "هفتگی", "width_pct": 0.8,
            "distance_atr": (2400.0 - 2210.5) / 150.0}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(P, "_prices", lambda syms: {s: 100.0 for s in syms})
    monkeypatch.setattr(P, "CONCENTRATION_CAP_PCT", 100)
    monkeypatch.setattr(P, "_now", lambda: AT)
    monkeypatch.setattr(P, "_clock", lambda: datetime(2026, 11, 2, 9, tzinfo=UTC))
    # بسته هفتگی ۲ نوامبر بالای سطح ابطال‌شده 2380.5606 و پس از خروج — ت۲
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (
        {"close": 2420.0, "closed_at": "2026-11-02T00:00:00+00:00", "venue": "okx"}, []))
    calls = []

    def proposal(sym, price):
        calls.append((sym, price))
        return dict(PROPOSAL)
    monkeypatch.setattr(P, "level_proposal", proposal)
    return calls


def _files():
    return (Path("holdings.json").read_text(encoding="utf-8"),
            Path("watch.json").read_text(encoding="utf-8"))


T2 = ["--holdings", "holdings.json", "--optcost", "oc.json", "reenter", "--symbol", "ETH",
      "--qty", "0.0372", "--price", "2450", "--account", "LBank", "--at", AT]


def test_real_eth_has_no_level() -> None:
    h = json.loads(Path("holdings.json").read_text(encoding="utf-8"))
    eth = next(p for p in h["positions"] if p["symbol"] == "ETH")
    assert eth["invalidation"] is None
    w = json.loads(Path("watch.json").read_text(encoding="utf-8"))
    assert not any(d["symbol"] == "ETH" for d in w.get("dormant") or [])


def test_reenter_without_level_refused(env, capsys) -> None:
    before = _files()
    assert P.main(T2) == 2
    err = capsys.readouterr().err
    assert "سطح ابطال ندارد" in err and "--level" in err and "--suggest-level" in err
    assert _files() == before


def test_reenter_with_level_returns_to_watch(env) -> None:
    assert P.main(T2 + ["--level", "2200"]) == 0
    h = json.loads(Path("holdings.json").read_text(encoding="utf-8"))
    w = json.loads(Path("watch.json").read_text(encoding="utf-8"))
    eth = next(p for p in h["positions"] if p["symbol"] == "ETH")
    assert eth["invalidation"] == 2200.0 and eth["invalidation_since"] == AT
    item = next(it for it in w["positions"] if it["symbol"] == "ETH")
    assert item["invalidation"] == 2200.0 and item["invalidation_since"] == AT
    assert item["anchor"] == 2400.0 and item["anchor_atr_w"] == 150.0
    assert item["anchor_week_closed_at"] == "2026-11-02T00:00:00+00:00"
    assert P.level_mismatches(h, w) == [] and P.anchor_violations(w) == []
    row = h["ledger"][-1]
    assert row["action"] == "reenter" and row["invalidation"] == 2200.0
    W.validate_watch(w)


def test_level_must_obey_anchor_rule(env, capsys) -> None:
    before = _files()
    assert P.main(T2 + ["--level", "2350"]) == 2          # فقط 0.33 دامنه واقعی هفتگی زیر لنگر
    assert "ATR" in capsys.readouterr().err
    assert P.main(T2 + ["--level", "2450"]) == 2          # برابر قیمت ورود
    assert "زیر قیمت" in capsys.readouterr().err
    assert _files() == before


def test_level_without_anchor_data_is_kept_loud(env, monkeypatch, capsys) -> None:
    def down(sym, price):
        raise P.PositionsError("کندل نیامد")
    monkeypatch.setattr(P, "level_proposal", down)
    assert P.main(T2 + ["--level", "2200"]) == 0
    assert "لنگر سنجیده نشد" in capsys.readouterr().out
    w = json.loads(Path("watch.json").read_text(encoding="utf-8"))
    assert P.anchor_violations(w)                          # بی لنگر: پایشگر بلند می‌گوید


def test_suggest_level_writes_nothing(env, capsys) -> None:
    before = _files()
    assert P.main(T2 + ["--suggest-level"]) == 0
    out = capsys.readouterr().out
    assert "2210.5" in out and "pick_invalidation" in out and "--level 2210.5" in out
    assert "هیچ ثبتی نشد" in out
    assert _files() == before
    assert env == [("ETH", 2450.0)]


def test_suggest_level_none_found(env, monkeypatch, capsys) -> None:
    monkeypatch.setattr(P, "level_proposal", lambda sym, price: dict(
        PROPOSAL, level=None, reason="سطح معتبری نیست"))
    assert P.main(T2 + ["--suggest-level"]) == 2
    assert "سطح معتبری نیست" in capsys.readouterr().out


def test_level_refused_when_position_has_one(env, capsys) -> None:
    args = [a if a != "ETH" else "SOL" for a in T2]
    assert P.main(args + ["--level", "90"]) == 2
    assert "بازبینی هفتگی" in capsys.readouterr().err


def test_reserve_reenter_without_level_refused_then_with_level(env, monkeypatch, capsys) -> None:
    import radar_watch as RW
    monkeypatch.setattr(RW, "rebuy_verdict", lambda row, released: (True, "آزمون"))
    res = ["--holdings", "holdings.json", "--optcost", "oc.json", "reenter", "--symbol", "ETH",
           "--qty", "0.037", "--price", "2300", "--account", "LBank", "--at", AT,
           "--reserve-plan", "2026-10-24T03:46:49+00:00", "--gross", "85.1", "--fee", "0.0851"]
    before = _files()
    assert P.main(res) == 2
    assert "سطح ابطال ندارد" in capsys.readouterr().err
    assert _files() == before
    assert P.main(res + ["--level", "2150"]) == 0
    h = json.loads(Path("holdings.json").read_text(encoding="utf-8"))
    w = json.loads(Path("watch.json").read_text(encoding="utf-8"))
    assert next(p for p in h["positions"] if p["symbol"] == "ETH")["invalidation"] == 2150.0
    assert P.level_mismatches(h, w) == []
    assert h["ledger"][-1]["quota"] == "reserve"


def test_tao_dormant_still_restores_without_level(env, monkeypatch) -> None:
    import radar_watch as RW
    monkeypatch.setattr(RW, "rebuy_verdict", lambda row, released: (True, "آزمون"))
    res = ["--holdings", "holdings.json", "--optcost", "oc.json", "reenter", "--symbol", "TAO",
           "--qty", "0.1", "--price", "233", "--account", "LBank", "--at", AT,
           "--reserve-plan", "2026-10-24T03:46:49+00:00", "--gross", "23.3", "--fee", "0.0233"]
    assert P.main(res) == 0
    h = json.loads(Path("holdings.json").read_text(encoding="utf-8"))
    assert next(p for p in h["positions"] if p["symbol"] == "TAO")["invalidation"] == 202.5065
