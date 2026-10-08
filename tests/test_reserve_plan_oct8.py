"""
نقشه ذخیره تازه — کار صفر ب نشست ۱۰، تصمیم کاربر ۸ اکتبر ۲۰۲۶، رویداد ۸۹.

رژیم ۶ و ۷ اکتبر محتاط شد؛ هدف ذخیره ۲۵٪، ذخیره 15.7٪. کاربر در LBank دو فروش
محدود گذاشت: ETH 0.04 در 2625 و BNB 0.12 در 783. مهلت 2026-10-15 00:00 UTC.

قرارداد:
- نقشه رویداد ۳۶ بسته است و به reserve_archive می‌رود، با میدان closed. نقشه
  فعال فقط reserve_plan است.
- on_deadline: اگر باند با هیسترزیس — trade_band — دست‌کم «سازنده» شد، پله‌های
  پرنشده لغو؛ وگرنه در مهلت باقی‌مانده در بازار. باند نامعلوم یعنی «تصمیم لازم»،
  نه بازار و نه لغو.
- rebuy: با سازنده‌شدن تأییدشده همان مقدارهای فروخته‌شده بازخرید. فقط تا مقدار
  فروخته‌شده. بازخرید «نزدیک سطح ابطال» — اصلاح ۹ اکتبر، رویداد ۹۸ — فقط وقتی قیمت
  بالای کف و دست‌کم min_below_sale_pct زیر قیمت واقعی فروش همان پله است.
- گزارش سبد پیشرفت نقشه، شرط مهلت، وضع امروز شرط و نقشه بازخرید را نشان می‌دهد؛
  پایشگر در مهلت همان حکم شرط را می‌فرستد، نه «بازار» بی‌شرط.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_watch as W

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
LATE = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)
TITLE = "نقشه ذخیره ۸ اکتبر — رویداد ۸۹"

PLAN = {
    "title": TITLE,
    "created": "2026-10-08T00:00:00+00:00", "deadline": "2026-10-15T00:00:00+00:00",
    "account": "LBank",
    "on_deadline": {"cancel_if_band_at_least": "سازنده", "otherwise": "market"},
    "steps": [{"symbol": "ETH", "qty": 0.04, "price": 2625},
              {"symbol": "BNB", "qty": 0.12, "price": 783}],
    "rebuy": {"note": "با سازنده‌شدن تأییدشده، یا نزدیک ابطال بالای کف و ۵٪ زیر فروش",
              "steps": [{"symbol": "ETH", "qty": 0.04, "floor": 2380.56,
                         "min_below_sale_pct": 5},
                        {"symbol": "BNB", "qty": 0.12, "floor": 702.39,
                         "min_below_sale_pct": 5}]},
}
OLD_TRIM = {"at": "2026-10-02T08:17:19+00:00", "action": "trim", "symbol": "ETH",
            "delta": -0.0472, "price": 2755.0, "reason": "reserve"}
ETH_FILL = {"at": "2026-10-09T03:00:00+00:00", "action": "trim", "symbol": "ETH",
            "delta": -0.04, "price": 2625.0, "reason": "reserve"}


def _h(ledger=(OLD_TRIM,)) -> dict:
    return {"version": 2, "frozen": {"date": "2026-09-25", "members": {"ETH": 0.5, "BNB": 0.33}},
            "cash": [], "positions": [
        {"symbol": "ETH", "book": "position", "status": "open", "invalidation": 2380.5606,
         "lots": [{"qty": 0.148257, "account": "LBank", "entry": None}]},
        {"symbol": "BNB", "book": "position", "status": "open", "invalidation": 702.3872,
         "lots": [{"qty": 0.326763, "account": "LBank", "entry": None}]}],
        "ledger": list(ledger), "updated": "2026-10-03T06:17:24+00:00", "source": "آزمون"}


PRICES = {"ETH": 2580.0, "BNB": 760.0}
VAL = {"total": 2134.0, "stable_usd": 335.0, "incomplete": False, "missing": []}
REG = {"name": "محتاط", "cap": 4.0, "mult": 0.5, "maxpos": 3, "stable": 25}
BAND = {n: {"name": n, "cap": 0, "mult": 0, "maxpos": 0, "stable": 0}
        for n in ("محتاط", "سازنده", "انبساطی")}


def _watch(plan=PLAN, archive=None) -> dict:
    w = {"version": 2, "updated": "2026-10-08T00:00:00+00:00", "positions": [],
         "reserve_plan": copy.deepcopy(plan), "items": []}
    if archive is not None:
        w["reserve_archive"] = archive
    return w


def _section(txt: str, n: str) -> str:
    start = txt.index(f"## {n} —")
    nxt = txt.find("\n## ", start + 1)
    return txt[start: nxt if nxt > 0 else None]


# ═══════════════ اعتبارسنجی watch.json ═══════════════

def test_valid_plan_passes() -> None:
    W.validate_watch(_watch())


@pytest.mark.parametrize("bad", [
    {"cancel_if_band_at_least": "خوب", "otherwise": "market"},
    {"cancel_if_band_at_least": "سازنده", "otherwise": "hold"},
    {"otherwise": "market"},
    "سازنده",
])
def test_bad_on_deadline_is_loud(bad) -> None:
    with pytest.raises(W.WatchError):
        W.validate_watch(_watch(dict(PLAN, on_deadline=bad)))


@pytest.mark.parametrize("step", [
    {"symbol": "ETH", "qty": 0.04, "floor": 0},
    {"symbol": "ETH", "qty": 0, "floor": 2380.56},
    {"symbol": "ETH", "qty": 0.04},
    {"qty": 0.04, "floor": 2380.56},
])
def test_bad_rebuy_is_loud(step) -> None:
    with pytest.raises(W.WatchError):
        W.validate_watch(_watch(dict(PLAN, rebuy={"steps": [step]})))


def test_active_plan_cannot_be_closed() -> None:
    with pytest.raises(W.WatchError):
        W.validate_watch(_watch(dict(PLAN, closed={"at": "2026-10-08T00:00:00+00:00",
                                                   "reason": "x"})))


def _old(**closed) -> dict:
    return {"title": "نقشه ذخیره ۲۵ سپتامبر — رویداد ۳۶",
            "created": "2026-09-25T16:00:00+00:00", "deadline": "2026-10-05T00:00:00+00:00",
            "steps": [{"symbol": "ETH", "qty": 0.0472, "price": None}],
            **({"closed": closed} if closed else {})}


def test_archive_needs_closed_with_time_and_reason() -> None:
    W.validate_watch(_watch(archive=[_old(at="2026-10-04T14:37:32+00:00", reason="بسته")]))
    for bad in ([_old()], [_old(at="2026-10-04T14:37:32", reason="بسته")],
                [_old(at="2026-10-04T14:37:32+00:00", reason=" ")]):
        with pytest.raises(W.WatchError):
            W.validate_watch(_watch(archive=bad))


# ═══════════════ شرط مهلت ═══════════════

def test_rule_state() -> None:
    assert W.plan_rule_state(PLAN, "محتاط") == "keep"
    assert W.plan_rule_state(PLAN, "انقباضی") == "keep"
    assert W.plan_rule_state(PLAN, "سازنده") == "cancel"
    assert W.plan_rule_state(PLAN, "انبساطی") == "cancel"
    assert W.plan_rule_state(PLAN, None) == "unknown"
    plain = {k: v for k, v in PLAN.items() if k != "on_deadline"}
    assert W.plan_rule_state(plain, "سازنده") == "no_rule"


def _regime(name="محتاط", gen="2026-10-07T13:46:24+00:00") -> dict:
    return {"generated_at": gen, "trade_band": {"name": name}}


def test_regime_trade_band() -> None:
    assert W.regime_trade_band(_regime(), NOW) == ("محتاط", None)
    name, warn = W.regime_trade_band(_regime(gen="2026-09-20T00:00:00+00:00"), NOW)
    assert name is None and "کهنه" in warn
    name, warn = W.regime_trade_band({"generated_at": "2026-10-07T13:46:24+00:00"}, NOW)
    assert name is None and "trade_band" in warn
    assert W.regime_trade_band(None, NOW)[0] is None


# ═══════════════ پایشگر ═══════════════

def _check(now=NOW, regime=None, state=None, h=None, prices=PRICES) -> list[str]:
    return W.check_positions(_watch(), h or _h(), {} if state is None else state, now,
                             weekly=lambda s: (None, []), price=lambda s: prices.get(s),
                             regime=regime)


def test_watch_cautious_before_deadline_quiet() -> None:
    msgs = _check(regime=_regime("محتاط"))
    assert not any("لغو" in m for m in msgs)


def test_watch_cancel_condition_before_deadline_once() -> None:
    st = {}
    msgs = _check(regime=_regime("سازنده"), state=st)
    hit = [m for m in msgs if "شرط لغو" in m]
    assert len(hit) == 1 and "LBank" in hit[0] and "2625" in hit[0] and "783" in hit[0]
    assert not [m for m in _check(regime=_regime("سازنده"), state=st) if "شرط لغو" in m]


def test_watch_deadline_cautious_sells_at_market() -> None:
    msgs = _check(now=LATE, regime=_regime("محتاط", gen="2026-10-14T13:00:00+00:00"))
    m = [x for x in msgs if "مهلت" in x]
    assert m and "بازار" in m[0] and "لغو" not in m[0]


def test_watch_deadline_constructive_cancels() -> None:
    msgs = _check(now=LATE, regime=_regime("سازنده", gen="2026-10-14T13:00:00+00:00"))
    m = [x for x in msgs if "مهلت" in x]
    assert m and "لغو" in m[0] and "قیمت بازار" not in m[0]


def test_watch_deadline_unknown_band_asks() -> None:
    msgs = _check(now=LATE, regime=None)
    m = [x for x in msgs if "مهلت" in x]
    assert m and "نامعلوم" in m[0] and "تصمیم" in m[0] and "قیمت بازار" not in m[0]


def test_watch_step_price_alert_unchanged() -> None:
    msgs = _check(regime=_regime("محتاط"), prices={"ETH": 2630.0, "BNB": 760.0})
    assert any("پله ذخیره ETH 2625 رسید" in m for m in msgs)


def test_run_once_reads_regime_for_plan_rule(tmp_path, monkeypatch) -> None:
    """بی market هم regime.json خوانده شود، اگر نقشه شرط مهلت دارد."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regime.json").write_text(json.dumps(_regime("سازنده", gen=NOW.isoformat())),
                                          encoding="utf-8")
    sent = []
    monkeypatch.setattr(W, "notify", lambda msg, quiet=False: sent.append(msg))
    monkeypatch.setattr(W, "ticker", lambda s: PRICES.get(s))
    monkeypatch.setattr(W, "stale_warning", lambda p: None)
    W.run_once(_watch(), {}, quiet=True, h=_h(), now=NOW, regime_path="regime.json")
    assert any("شرط لغو" in m for m in sent)


# ═══════════════ گزارش سبد ═══════════════

def _view(now=NOW, band="محتاط", h=None):
    return B.reserve_view(PLAN, h or _h(), PRICES, VAL, now, band=band)


def test_view_rule_and_title() -> None:
    assert _view()["title"] == TITLE
    assert _view()["rule_state"] == "keep"
    assert _view(band="سازنده")["rule_state"] == "cancel"
    assert _view(band=None)["rule_state"] == "unknown"


def test_view_old_trims_do_not_fill_new_plan() -> None:
    assert [s["filled"] for s in _view()["steps"]] == [False, False]


def test_view_rebuy_limited_to_sold() -> None:
    rb = {r["symbol"]: r for r in _view()["rebuy"]}
    assert rb["ETH"]["floor"] == 2380.56 and rb["ETH"]["sold"] == 0
    assert rb["ETH"]["dist_pct"] == pytest.approx(100 * (2580.0 / 2380.56 - 1))
    rb = {r["symbol"]: r for r in _view(h=_h((OLD_TRIM, ETH_FILL)))["rebuy"]}
    assert rb["ETH"]["sold"] == pytest.approx(0.04) and rb["BNB"]["sold"] == 0


def _rows(order=("ETH", "BNB", "LINK")) -> list[dict]:
    rs = {"ETH": -0.022, "BNB": -0.016, "LINK": -0.004}
    if order[0] == "LINK":
        rs = {"LINK": -0.05, "ETH": -0.022, "BNB": -0.016}
    out = []
    for s in rs:
        pos = {"symbol": s, "book": "position", "status": "open", "invalidation": 1.0,
               "lots": [{"qty": 1.0, "account": "LBank", "entry": None}]}
        out.append({"pos": pos, "qty": 1.0, "price": 100.0, "value": 100.0, "dust": False,
                    "avg_entry": None, "score": 0.1, "rsi": None, "rs30": rs[s],
                    "strikes": 0, "weekly": None, "weekly_why": []})
    return out


def _report(view, tband=REG, rows=None) -> str:
    return B.build_report(_h(), rows if rows is not None else _rows(), REG, [], "آزمون",
                          val=VAL, reserve=view, tband=tband)


def test_section6_shows_new_plan() -> None:
    s6 = _section(_report(_view()), "۶")
    for x in (TITLE, "2625", "783", "0.04", "0.12", "2026-10-15 00:00", "سازنده", "بازار",
              "2380.56", "702.39", "بازخرید"):
        assert x in s6, x
    assert "رویداد ۳۶" not in s6


def test_section6_cancel_action_before_deadline() -> None:
    s6 = _section(_report(_view(band="سازنده"), tband=BAND["سازنده"]), "۶")
    acts = s6[s6.index("\n1. "):]
    assert "لغو" in acts and "LBank" in acts and "گذشت" not in acts


def test_section6_cancel_with_sale_asks_rebuy() -> None:
    v = _view(band="سازنده", h=_h((OLD_TRIM, ETH_FILL)))
    acts = _section(_report(v, tband=BAND["سازنده"]), "۶")
    acts = acts[acts.index("\n1. "):]
    assert "بازخرید" in acts and "ETH" in acts and "0.04" in acts


def test_section6_deadline_keep_is_market_without_decision() -> None:
    s6 = _section(_report(_view(now=LATE)), "۶")
    acts = s6[s6.index("\n1. "):]
    assert "بازار" in acts and "گذشت" in acts and "تصمیم لازم" not in acts


def test_section6_deadline_unknown_band_asks() -> None:
    s6 = _section(_report(_view(now=LATE, band=None), tband=None), "۶")
    acts = s6[s6.index("\n1. "):]
    assert "تصمیم" in acts and "نامعلوم" in acts


def test_section5_plan_matches_sell_order() -> None:
    s5 = _section(_report(_view()), "۵")
    assert "هم‌خوان" in s5 and "منحرف" not in s5


def test_section5_plan_deviates() -> None:
    s5 = _section(_report(_view(), rows=_rows(("LINK", "ETH", "BNB"))), "۵")
    assert "منحرف" in s5


# ═══════════════ قانون بازخرید — تصمیم کاربر ۹ اکتبر، رویداد ۹۸ ═══════════════
# بازخرید «نزدیک سطح ابطال» فقط بالای کف و دست‌کم ۵٪ زیر قیمت واقعی فروش همان پله.
# وگرنه فقط با سازنده‌شدن تأییدشده باند. فروش در مهلت نزدیک ابطال و بازخرید فوری
# همان‌جا فقط دو بار کارمزد است.

def _fill(price, qty=0.04, sym="ETH", at="2026-10-09T03:00:00+00:00") -> dict:
    return {"at": at, "action": "trim", "symbol": sym, "delta": -qty, "price": price,
            "reason": "reserve"}


def _rb(h, prices, plan=PLAN) -> dict:
    return {r["symbol"]: r for r in W.rebuy_status(plan, h, prices)}


def test_rebuy_rule_floor_is_five() -> None:
    assert W.REBUY_MIN_BELOW_SALE_PCT == 5


@pytest.mark.parametrize("gap", [None, 4, 4.99, "5", 0, 100, -5])
def test_rebuy_step_needs_gap_of_at_least_five(gap) -> None:
    step = {"symbol": "ETH", "qty": 0.04, "floor": 2380.56}
    if gap is not None:
        step["min_below_sale_pct"] = gap
    with pytest.raises(W.WatchError):
        W.validate_watch(_watch(dict(PLAN, rebuy={"steps": [step]})))


@pytest.mark.parametrize("gap", [5, 7.5])
def test_rebuy_step_gap_five_or_more_passes(gap) -> None:
    step = {"symbol": "ETH", "qty": 0.04, "floor": 2380.56, "min_below_sale_pct": gap}
    W.validate_watch(_watch(dict(PLAN, rebuy={"steps": [step]})))


def test_rebuy_unsold() -> None:
    rb = _rb(_h(), PRICES)
    assert rb["ETH"]["window"] == "unsold" and rb["ETH"]["sold"] == 0
    assert rb["ETH"]["sale"] is None and rb["ETH"]["ceiling"] is None


@pytest.mark.parametrize("px,window", [
    (2580.0, "above"),       # بالای سقف 2493.75 — فقط با سازنده‌شدن
    (2493.75, "open"),       # درست ۵٪ زیر فروش
    (2490.0, "open"),
    (2380.57, "open"),       # درست بالای کف
    (2380.56, "below"),      # در کف — ابطال
    (2300.0, "below"),
])
def test_rebuy_window_after_limit_sale(px, window) -> None:
    rb = _rb(_h((OLD_TRIM, ETH_FILL)), {"ETH": px, "BNB": 760.0})
    e = rb["ETH"]
    assert e["sale"] == 2625.0 and e["ceiling"] == pytest.approx(2625.0 * 0.95)
    assert e["sold"] == pytest.approx(0.04) and e["window"] == window
    assert rb["BNB"]["window"] == "unsold"


def test_rebuy_deadline_sale_near_invalidation_has_no_window() -> None:
    """
    مهلت با باند محتاط: باقی‌مانده در بازار، نزدیک ابطال — 2450. سقف 2327.5 زیر
    کف 2380.56 است؛ پس در هیچ قیمتی بازخرید نزدیک ابطال مجاز نیست، حتی 2400.
    """
    for px in (2400.0, 2381.0, 2330.0, 2600.0):
        e = _rb(_h((_fill(2450.0),)), {"ETH": px})["ETH"]
        assert e["ceiling"] == pytest.approx(2327.5) and e["window"] == "no_gap", px


def test_rebuy_sale_without_price_is_no_data() -> None:
    e = _rb(_h((_fill(None),)), {"ETH": 2400.0})["ETH"]
    assert e["sold"] == pytest.approx(0.04) and e["sale"] is None
    assert e["window"] == "no_sale"


def test_rebuy_no_live_price() -> None:
    assert _rb(_h((ETH_FILL,)), {})["ETH"]["window"] == "no_price"


def test_rebuy_two_sales_uses_lowest() -> None:
    """دو پله ETH پر در 2625 و 2700 — سقف از پایین‌تر، محتاطانه‌تر."""
    plan = dict(PLAN, steps=[{"symbol": "ETH", "qty": 0.02, "price": 2625},
                             {"symbol": "ETH", "qty": 0.02, "price": 2700}])
    h = _h((_fill(2625.0, 0.02), _fill(2700.0, 0.02, at="2026-10-10T03:00:00+00:00")))
    e = _rb(h, {"ETH": 2550.0}, plan)["ETH"]
    assert e["sale"] == 2625.0 and e["ceiling"] == pytest.approx(2493.75)
    assert e["window"] == "above"


def test_rebuy_view_carries_rule() -> None:
    rb = {r["symbol"]: r for r in _view(h=_h((OLD_TRIM, ETH_FILL)))["rebuy"]}
    assert rb["ETH"]["window"] == "above" and rb["ETH"]["sale"] == 2625.0
    assert rb["ETH"]["dist_pct"] == pytest.approx(100 * (2580.0 / 2380.56 - 1))


def _rebuy_rows(view) -> dict[str, str]:
    s6 = _section(_report(view), "۶")
    tab = s6[s6.index("**نقشه بازخرید**"):]
    return {ln.split("|")[1].strip(): ln for ln in tab.splitlines()
            if ln.startswith("| ") and ln.split("|")[1].strip() in ("ETH", "BNB")}


def test_section6_rebuy_explains_rule() -> None:
    s6 = _section(_report(_view()), "۶")
    tab = s6[s6.index("**نقشه بازخرید**"):]
    assert "۵٪" in tab and "سازنده" in tab and "قیمت فروش" in tab and "سقف" in tab


def test_section6_rebuy_window_open() -> None:
    v = B.reserve_view(PLAN, _h((OLD_TRIM, ETH_FILL)), {"ETH": 2490.0, "BNB": 760.0},
                       VAL, NOW, band="محتاط")
    rows = _rebuy_rows(v)
    assert "2625" in rows["ETH"] and "2493.75" in rows["ETH"] and "مجاز" in rows["ETH"]
    assert "مجاز" not in rows["BNB"]


def test_section6_rebuy_above_ceiling() -> None:
    rows = _rebuy_rows(_view(h=_h((OLD_TRIM, ETH_FILL))))
    assert "بالای سقف" in rows["ETH"] and "مجاز" not in rows["ETH"]


def test_section6_rebuy_deadline_sale_near_floor() -> None:
    v = B.reserve_view(PLAN, _h((_fill(2450.0),)), {"ETH": 2400.0, "BNB": 760.0},
                       VAL, LATE, band="محتاط")
    rows = _rebuy_rows(v)
    assert "سقف زیر کف" in rows["ETH"] and "مجاز" not in rows["ETH"]


# ═══════════════ قفل داده — watch.json واقعی ═══════════════

def _real() -> dict:
    return json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))


def test_real_watch_has_oct8_plan() -> None:
    w = _real()
    W.validate_watch(w)
    rp = w["reserve_plan"]
    assert "۸۹" in rp["title"] and rp["account"] == "LBank"
    assert rp["deadline"] == "2026-10-15T00:00:00+00:00"
    assert [(s["symbol"], s["qty"], s["price"]) for s in rp["steps"]] == \
        [("ETH", 0.04, 2625), ("BNB", 0.12, 783)]
    assert rp["on_deadline"] == {"cancel_if_band_at_least": "سازنده", "otherwise": "market"}
    assert [(s["symbol"], s["qty"], s["floor"], s["min_below_sale_pct"])
            for s in rp["rebuy"]["steps"]] == \
        [("ETH", 0.04, 2380.56, 5), ("BNB", 0.12, 702.39, 5)]
    assert "2631.24" in rp["note"] and "785.48" in rp["note"]
    assert "۵٪" in rp["rebuy"]["note"] and "۹۸" in rp["rebuy"]["note"]


def test_real_watch_archives_event36_plan() -> None:
    old = [p for p in _real()["reserve_archive"] if p["created"] == "2026-09-25T16:00:00+00:00"]
    assert len(old) == 1 and "۳۶" in old[0]["title"]
    assert datetime.fromisoformat(old[0]["closed"]["at"]).tzinfo is not None
    assert "۸۱" in old[0]["closed"]["reason"]
