"""
م۳ و ت۴ بازبینی ۲۳ اکتبر — متن ۱۸.

م۳، تصمیم کاربر: ورودی غایب رژیم آخرین امتیاز معتبرش را تا دو برابر مهلت تازگی‌اش نگه
می‌دارد؛ min(raw, norm) می‌ماند، کمینه سه‌تایی نه. الگوی CLAUDE.md: همان ورودی با داده
کامل و ناقص — ناقص نباید امتیاز بهتر بگیرد. شاهد بازبینی، ۲۲ اکتبر: بی dollar نهایی
-0.522 در برابر -0.670 کامل.

ت۴: مرز سری در regime_history.json میدان series_boundaries، و خط از پیش در گزارش.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_regime as G

UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

# امتیاز ورودی‌های ۲۲ اکتبر — بازبینی: دو ورودی تازه میانگین ‎-1.187، بقیه حدود ‎-0.54
OCT22 = {"money_price": -1.46, "curve": 0.0, "net_liq": -1.15, "dollar": -2.0,
         "ma50w": 0.53, "dom_ex": -1.42, "ethbtc": -1.68, "stable": -0.97,
         "fng": 0.16, "usdt_dom": -0.95}


def _inp(scores: dict, ts: datetime = NOW - timedelta(days=1)) -> dict:
    out = {}
    for k in G.INPUTS:
        col, label = G.INPUTS[k]
        s = scores.get(k)
        out[k] = G.Input(key=k, column=col, label=label, weight=G.weights()[k], score=s,
                         ts=ts if s is not None else None,
                         reason="" if s is not None else "منبع پاسخ نداد")
    return out


def _hist(day: str, scores: dict, input_ts: dict | None = None, carried: dict | None = None,
          gen: str | None = None) -> dict:
    rec = {"generated_at": gen or f"{day}T12:00:00+00:00", "inputs": dict(scores),
           "band": "انقباضی", "coverage": 1.0}
    if input_ts is not None:
        rec["input_ts"] = input_ts
    if carried:
        rec["carried"] = carried
    return {"version": 1, "days": {day: rec}}


def test_missing_dollar_without_carry_scores_better_the_bug() -> None:
    full = G.aggregate(_inp(OCT22))["score"]
    part = G.aggregate(_inp({**OCT22, "dollar": None}))["score"]
    assert part > full                                  # همان ایراد م۳: ناقص بهتر


def test_carry_makes_partial_equal_full() -> None:
    full = G.aggregate(_inp(OCT22))["score"]
    inp = _inp({**OCT22, "dollar": None})
    hist = _hist("2026-10-21", OCT22, input_ts={"dollar": "2026-10-16T00:00:00+00:00"})
    assert G.carry_forward(inp, hist, NOW) == ["dollar"]
    res = G.aggregate(inp)
    assert res["score"] == pytest.approx(full)
    assert res["score"] == min(res["raw"], res["norm"])   # کمینه دوتایی بی‌تغییر
    c = res["carried"][0]
    assert c["key"] == "dollar" and c["from"] == "2026-10-21" and c["limit_days"] == 28
    assert res["missing"] == []


def test_two_missing_inputs_carried() -> None:
    full = G.aggregate(_inp(OCT22))["score"]
    inp = _inp({**OCT22, "dollar": None, "dom_ex": None})
    hist = _hist("2026-10-21", OCT22, input_ts={"dollar": "2026-10-16T00:00:00+00:00",
                                                "dom_ex": "2026-10-21T00:00:00+00:00"})
    G.carry_forward(inp, hist, NOW)
    assert G.aggregate(inp)["score"] == pytest.approx(full)


def test_carry_expires_after_twice_window() -> None:
    inp = _inp({**OCT22, "dollar": None})
    # dollar مهلت ۱۴ روز؛ مشاهده ۲۹ روز پیش — بیش از ۲۸
    hist = _hist("2026-10-21", OCT22, input_ts={"dollar": "2026-09-23T00:00:00+00:00"})
    assert G.carry_forward(inp, hist, NOW) == []
    assert inp["dollar"].score is None


def test_carried_day_is_not_a_source() -> None:
    inp = _inp({**OCT22, "fng": None})
    h = _hist("2026-10-21", OCT22, input_ts={"fng": "2026-10-21T00:00:00+00:00"},
              carried={"fng": "2026-10-20"})
    h["days"]["2026-10-12"] = {"generated_at": "2026-10-12T12:00:00+00:00",
                               "inputs": {**OCT22, "fng": 0.9},
                               "input_ts": {"fng": "2026-10-12T00:00:00+00:00"}}
    # روز ۲۱ جانشین بود؛ روز ۱۲ معتبر ولی ۱۰ روز عمر، سقف ۱۴ روز
    assert G.carry_forward(inp, h, NOW) == ["fng"]
    assert inp["fng"].score == 0.9 and inp["fng"].carried["from"] == "2026-10-12"


def test_legacy_record_without_input_ts_is_worst_case() -> None:
    # fng مهلت ۷: بی input_ts، مشاهده = generated_at منهای ۷ روز
    inp = _inp({**OCT22, "fng": None})
    ok = _hist("2026-10-17", OCT22)                     # 5 + 7 = 12 روز ≤ 14
    assert G.carry_forward(inp, ok, NOW) == ["fng"]
    inp = _inp({**OCT22, "fng": None})
    old = _hist("2026-10-14", OCT22)                    # 8 + 7 = 15 روز > 14
    assert G.carry_forward(inp, old, NOW) == []


def test_history_records_carried_and_input_ts() -> None:
    inp = _inp({**OCT22, "dollar": None})
    hist = _hist("2026-10-21", OCT22, input_ts={"dollar": "2026-10-16T00:00:00+00:00"})
    G.carry_forward(inp, hist, NOW)
    res = G.aggregate(inp)
    h = G.update_history(hist, res, inp, NOW)
    rec = h["days"]["2026-10-22"]
    assert rec["carried"] == {"dollar": "2026-10-21"}
    assert "dollar" not in rec["input_ts"] and "fng" in rec["input_ts"]
    doc = G.build_doc(res, inp, NOW)
    assert doc["carried"][0]["key"] == "dollar"
    md = G.render_md(doc)
    assert "آخرین امتیاز معتبر" in md and "2026-10-21" in md


# ── ت۴: مرز سری ──

def test_series_boundary_recorded_with_effect() -> None:
    before = {k: v for k, v in OCT22.items() if k not in ("dom_ex", "usdt_dom")}
    hist = {"version": 1, "days": {"2026-10-21": {
        "generated_at": "2026-10-21T12:00:00+00:00", "inputs": {**before, "dom_ex": None,
                                                                "usdt_dom": None},
        "coverage": 0.8, "band": "انقباضی"}}}
    inp = _inp(OCT22)
    res = G.aggregate(inp)
    h = G.update_history(hist, res, inp, NOW)
    (b,) = h["series_boundaries"]
    assert b["date"] == "2026-10-22" and b["added"] == ["dom_ex", "usdt_dom"]
    assert b["removed"] == [] and b["coverage_before"] == 0.8 and b["coverage_after"] == 1.0
    without = G.aggregate(_inp(before))["score"]
    assert b["score_effect"] == pytest.approx(res["score"] - without)
    assert b["score_effect"] < 0
    # اجرای دوباره همان روز: یک مرز، نه دو
    h2 = G.update_history(h, res, inp, NOW)
    assert len(h2["series_boundaries"]) == 1
    md = G.render_md(G.build_doc(res, inp, NOW, boundary=b))
    assert "مرز سری امروز" in md and "پوشش 0.80 به 1.00" in md


def test_no_boundary_when_set_unchanged() -> None:
    hist = _hist("2026-10-21", OCT22)
    inp = _inp(OCT22)
    h = G.update_history(hist, G.aggregate(inp), inp, NOW)
    assert not h.get("series_boundaries")


def test_activation_line_from_history_start() -> None:
    now = datetime(2026, 10, 10, 12, tzinfo=UTC)
    hist = {"version": 1, "days": {"2026-09-25": {"btc_dom_ex_stable": 60.0,
                                                  "usdt_dominance": 5.0}}}
    inp = _inp({k: v for k, v in OCT22.items() if k not in ("dom_ex", "usdt_dom")})
    acts = G.activations(hist, inp, now)
    assert {a["key"]: a["date"] for a in acts} == {"dom_ex": "2026-10-22",
                                                   "usdt_dom": "2026-10-22"}
    md = G.render_md(G.build_doc(G.aggregate(inp), inp, now, activation=acts))
    assert "از 2026-10-22 فعال می‌شود" in md
    assert G.activations(hist, _inp(OCT22), now) == []
