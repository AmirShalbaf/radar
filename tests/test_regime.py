"""
آزمون radar_regime.py — نشست ۲ نقشه رادار ۷، مورد م۳.

همه بدون شبکه و با داده مصنوعی. نگاشت‌ها فرضیه‌اند، نه اندازه‌گیری
(references/macro-liquidity.md)؛ این آزمون‌ها فقط قفل می‌کنند که کد همان
فرضیه تأییدشده را اجرا می‌کند:

- علامت «انتظار بازار از مسیر نرخ»: بالای سقف محدوده منفی است.
- «قیمت پول» = ترکیب مسیر نرخ و بازده واقعی — هم‌خانواده‌اند و یک خبر
  نباید دو بار شمرده شود. جزء غایب با قانون سوگیری صفر در سطح ترکیب.
- خام = Σ وزن×امتیاز موجود ÷ Σ همه وزن‌ها؛ نرمال = همان صورت ÷ Σ وزن
  موجود؛ نهایی = کمینه دو — همیشه محافظه‌کارانه‌تر.
- مهلت تازگی بر اساس آهنگ انتشار هر سری: روزانه ۷ روز، هفتگی ۱۴ روز.
- تسلط‌ها روند ۳۰ روزه‌شان را از regime_history.json می‌گیرند.
"""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_fetch3 as R
import radar_regime as G

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
NOW = datetime(2026, 9, 25, 7, 0, tzinfo=UTC)
COLS = ["ts", "open", "high", "low", "close", "vol"]


# ═══════════════ نگاشت‌ها ═══════════════

@pytest.mark.parametrize("x, s", [(0.5, -1.0), (1.0, -2.0), (3.0, -2.0),
                                  (0.0, 0.0), (-0.5, 1.0), (-2.0, 2.0)])
def test_rate_path_above_ceiling_is_negative(x, s) -> None:
    """الزام ۵: بالای سقف محدوده یعنی باد مخالف — امتیاز منفی."""
    assert G.score_input("rate_path", x) == pytest.approx(s)


@pytest.mark.parametrize("x, s", [(1.0, 0.0), (2.0, -1.0), (1.5, -0.5),
                                  (0.0, 1.0), (2.78, -1.78), (2.2, -1.2),
                                  (3.5, -2.0), (-1.5, 2.0)])
def test_real_yield(x, s) -> None:
    """
    k = 1.0، خنثی 1.0. با k = 0.5 هر بازده واقعی بالای ۲٪ در ‎-2 اشباع
    می‌شد و ورودی کور بود: گشایش واقعی از 2.78 به 2.2 هیچ اثری نداشت.
    """
    assert G.score_input("real_10y", x) == pytest.approx(s)


def test_real_yield_is_not_blind_between_2_2_and_2_78() -> None:
    assert G.score_input("real_10y", 2.2) > G.score_input("real_10y", 2.78)


@pytest.mark.parametrize("x, s", [(0.55, 0.0), (2.0, 0.0), (0.0, 0.0),
                                  (-0.25, -0.5), (-0.5, -1.0), (-3.0, -1.0)])
def test_curve_only_inversion_is_penalised(x, s) -> None:
    """شیب مثبت نشانه روشنی ندارد؛ فقط وارونگی جریمه می‌شود، کف ‎-1."""
    assert G.score_input("curve", x) == pytest.approx(s)


@pytest.mark.parametrize("x, s", [(90, 1.0), (75, 1.0), (62.5, 0.5),
                                  (50, 0.0), (25, -1.0), (5, -1.0)])
def test_fear_greed_is_capped_at_one(x, s) -> None:
    assert G.score_input("fng", x) == pytest.approx(s)


@pytest.mark.parametrize("key, x, s", [
    ("net_liq", 0.5, 0.5), ("net_liq", -3.0, -2.0),
    ("dollar", 1.0, -1.0), ("dollar", -2.5, 2.0),
    ("ma50w", 15.0, 1.5), ("ma50w", -25.0, -2.0),
    ("dom_ex", 1.0, -1.0), ("dom_ex", -0.5, 0.5),
    ("ethbtc", 5.0, 1.0), ("ethbtc", -12.0, -2.0),
    ("stable", 1.5, 1.5), ("stable", -0.5, -0.5),
    ("usdt_dom", 0.5, -1.0), ("usdt_dom", -0.25, 0.5),
])
def test_other_mappings(key, x, s) -> None:
    assert G.score_input(key, x) == pytest.approx(s)


def test_money_price_both_present_is_mean() -> None:
    assert G.money_price(-2.0, -1.0) == pytest.approx(-1.5)


@pytest.mark.parametrize("rate, real, s", [
    (-1.0, None, -1.0),     # جزء منفی تنها: نرمال محافظه‌کارانه‌تر است
    (1.0, None, 0.5),       # جزء مثبت تنها: خام محافظه‌کارانه‌تر است
    (None, 2.0, 1.0),
])
def test_money_price_one_missing_uses_zero_bias_rule(rate, real, s) -> None:
    assert G.money_price(rate, real) == pytest.approx(s)


def test_money_price_both_missing_is_absent() -> None:
    assert G.money_price(None, None) is None


def test_weights_follow_the_columns() -> None:
    w = G.weights()
    assert sum(w.values()) == pytest.approx(1.0)
    liq = [k for k, (c, _) in G.INPUTS.items() if c == "liquidity"]
    assert sorted(liq) == ["curve", "dollar", "money_price", "net_liq"]
    assert all(w[k] == pytest.approx(0.10) for k in liq)
    assert w["ma50w"] == pytest.approx(0.35 / 3)
    assert w["fng"] == pytest.approx(0.25 / 3)
    assert "dom" not in G.INPUTS          # تسلط با استیبل حذف شد


# ═══════════════ تجمیع — قانون سوگیری صفر ═══════════════

def _inp(key: str, score: float | None) -> G.Input:
    col, label = G.INPUTS[key]
    return G.Input(key=key, column=col, label=label, weight=G.weights()[key],
                   score=score, reason="" if score is not None else "غایب")


def _all(score: float) -> dict:
    return {k: _inp(k, score) for k in G.INPUTS}


def test_all_present_raw_equals_norm() -> None:
    res = G.aggregate(_all(0.5))
    assert res["coverage"] == pytest.approx(1.0)
    assert res["raw"] == pytest.approx(0.5)
    assert res["norm"] == pytest.approx(0.5)
    assert res["score"] == pytest.approx(0.5)


def test_column_absent_positive_takes_raw() -> None:
    """ستون اشتها کاملاً غایب؛ نرمال مثبت ← خام محافظه‌کارانه‌تر است."""
    inp = _all(1.0)
    for k in ("stable", "fng", "usdt_dom"):
        inp[k] = _inp(k, None)
    res = G.aggregate(inp)
    assert res["coverage"] == pytest.approx(0.75)
    assert res["raw"] == pytest.approx(0.75)
    assert res["norm"] == pytest.approx(1.0)
    assert res["score"] == pytest.approx(0.75)
    assert res["columns"]["appetite"]["score"] is None


def test_column_absent_negative_takes_norm() -> None:
    """نرمال منفی ← خود نرمال محافظه‌کارانه‌تر است."""
    inp = _all(-1.0)
    for k in ("stable", "fng", "usdt_dom"):
        inp[k] = _inp(k, None)
    res = G.aggregate(inp)
    assert res["raw"] == pytest.approx(-0.75)
    assert res["norm"] == pytest.approx(-1.0)
    assert res["score"] == pytest.approx(-1.0)


def test_exact_band_boundary_goes_lower() -> None:
    res = G.aggregate(_all(-0.50))
    assert res["band"]["name"] == "انقباضی"


def test_low_coverage_label() -> None:
    inp = {k: _inp(k, None) for k in G.INPUTS}
    inp["money_price"] = _inp("money_price", 1.0)
    res = G.aggregate(inp)
    assert res["coverage"] == pytest.approx(0.10)
    assert res["low_coverage"] is True


def test_low_coverage_threshold_is_below_half() -> None:
    """«زیر ۵۰٪» پوشش کم است؛ خود ۵۰٪ نه. با این وزن‌ها هیچ ترکیبی دقیقاً
    ۵۰٪ نمی‌سازد، پس مرز روی کمک‌تابع قفل می‌شود."""
    assert G.is_low_coverage(0.4999) is True
    assert G.is_low_coverage(0.50) is False


def test_coverage_scenarios_30_and_55_percent() -> None:
    inp = _all(0.2)
    for k in ("ma50w", "dom_ex", "ethbtc", "stable", "fng", "usdt_dom", "curve"):
        inp[k] = _inp(k, None)
    res = G.aggregate(inp)          # فقط سه ورودی نقدینگی: ۳۰٪
    assert res["coverage"] == pytest.approx(0.30)
    assert res["low_coverage"] is True
    inp = _all(0.2)
    for k in ("stable", "fng", "usdt_dom", "money_price", "curve"):
        inp[k] = _inp(k, None)
    res = G.aggregate(inp)          # نقدینگی ۲۰٪ + چرخه ۳۵٪ = ۵۵٪
    assert res["coverage"] == pytest.approx(0.55)
    assert res["low_coverage"] is False


def test_zero_coverage_is_an_error() -> None:
    with pytest.raises(G.RegimeError):
        G.aggregate({k: _inp(k, None) for k in G.INPUTS})


# ═══════════════ اندازه‌گیری از منابع مصنوعی ═══════════════

def _fred(ages: dict | None = None, **vals) -> dict:
    """داده FRED مصنوعی به همان قالب fetch_fred؛ ages عمر هر سری به روز."""
    ages = ages or {}
    sids = ["DGS2", "DFEDTARU", "DFEDTARL", "DGS10", "T10YIE", "DGS30",
            "WALCL", "RRPONTSYD", "WTREGEN", "DTWEXBGS"]
    raw = {s: {"value": 1.0, "prev30": 1.0,
               "ts": NOW - timedelta(days=ages.get(s, 1))} for s in sids}

    def st(*ss):
        return {"sources": list(ss), "ts": min(raw[s]["ts"] for s in ss)}
    der = {
        "rate_path": {"value": vals.get("rate_path", 0.5),
                      **st("DGS2", "DFEDTARU", "DFEDTARL")},
        "real_10y": {"value": vals.get("real_10y", 1.5), **st("DGS10", "T10YIE")},
        "curve_30_2": {"value": vals.get("curve", 0.55), **st("DGS30", "DGS2")},
        "net_liq_trend": {"value": -20.0, "pct": vals.get("net_liq", -0.4),
                          **st("WALCL", "RRPONTSYD", "WTREGEN")},
        "dollar_30d": {"value": vals.get("dollar", 1.0), **st("DTWEXBGS")},
    }
    return {"raw": raw, "derived": der}


def _macro(age_days: float = 0.5, tether_ts: bool = True) -> dict:
    ts = NOW - timedelta(days=age_days)
    return {
        "stable_change_30d": R.Field(1.5, "DefiLlama", ts),
        "fear_greed": R.Field(62, "Alternative.me", ts),
        "btc_dominance": R.Field(57.0, "CoinGecko", ts),
        "btc_dom_ex_stable": R.Field(61.0, "محاسبه‌شده", ts),
        "usdt_dominance": R.Field(5.0, "محاسبه‌شده", ts if tether_ts else None),
    }


def _frame(n: int, bar: str, px, now: datetime = NOW) -> pd.DataFrame:
    """قاب کندل مصنوعی؛ سطر آخر کندل باز است."""
    step = pd.Timedelta(seconds=R.BAR_SECONDS[bar])
    open_ts = pd.Timestamp(now) - step / 2
    rows = []
    for i in range(n):
        p = px(i)
        ts = open_ts - step * (n - 1 - i)
        rows.append([int(ts.timestamp() * 1000), p, p, p, p, 1.0])
    df = R._df(rows, COLS)
    df["confirm"] = [1] * (n - 1) + [0]
    return R.enrich(df)


def _candles(now: datetime = NOW) -> tuple[dict, pd.DataFrame]:
    """بیت‌کوین: قیمت زنده ۱۱۰، ۵۰ هفته بسته آخر همه ۱۰۰. اتر به بیت‌کوین: ‎+5% در ۳۰ روز."""
    daily = _frame(700, "1D", lambda i: 110.0 if i == 699 else 105.0, now)
    weekly = _frame(80, "1W", lambda i: 100.0 if i >= 29 else 50.0, now)
    pair = _frame(60, "1D", lambda i: 0.0315 if i >= 50 else 0.03, now)
    return {"1D": daily, "1W": weekly}, pair


def _src(**over) -> dict:
    btc, pair = _candles()
    src = {"fred": _fred(), "macro": _macro(), "btc": btc, "ethbtc": pair}
    src.update(over)
    return src


def _history(days_back: int = 30, dom: float = 60.0, usdt: float = 5.5) -> dict:
    d = (NOW - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return {"version": 1, "days": {d: {"btc_dom_ex_stable": dom,
                                       "usdt_dominance": usdt}}}


def test_measure_all_inputs_from_synthetic_sources() -> None:
    inp = G.measure(_src(), _history(), NOW)
    # قیمت پول: مسیر نرخ ‎+0.5 ← ‎-1؛ بازده واقعی 1.5 ← ‎-0.5؛ میانگین ‎-0.75
    assert inp["money_price"].score == pytest.approx(-0.75)
    assert inp["curve"].score == pytest.approx(0.0)
    assert inp["net_liq"].score == pytest.approx(-0.4)
    assert inp["dollar"].score == pytest.approx(-1.0)
    assert inp["ma50w"].value == pytest.approx(10.0)
    assert inp["ma50w"].score == pytest.approx(1.0)
    assert inp["ethbtc"].value == pytest.approx(5.0)
    assert inp["dom_ex"].value == pytest.approx(1.0)
    assert inp["dom_ex"].score == pytest.approx(-1.0)
    assert inp["usdt_dom"].value == pytest.approx(-0.5)
    assert inp["usdt_dom"].score == pytest.approx(1.0)
    assert inp["stable"].score == pytest.approx(1.5)
    assert inp["fng"].score == pytest.approx(0.48)


@pytest.mark.parametrize("sid, age, ok", [
    ("DGS2", 7, True), ("DGS2", 8, False),          # روزانه: ۷ روز
    ("DTWEXBGS", 13, True), ("DTWEXBGS", 15, False),  # هفتگی: ۱۴ روز
    ("WALCL", 13, True), ("WALCL", 15, False),
])
def test_freshness_follows_release_cadence(sid, age, ok) -> None:
    key = {"DGS2": "money_price", "DTWEXBGS": "dollar", "WALCL": "net_liq"}[sid]
    inp = G.measure(_src(fred=_fred(ages={sid: age})), _history(), NOW)
    if key == "money_price" and not ok:
        # مسیر نرخ کهنه شد؛ بازده واقعی تنها می‌ماند: ‎-0.5 ← قانون سوگیری صفر ‎-0.5
        assert inp[key].score == pytest.approx(-0.5)
        assert "DGS2" in inp[key].detail
    else:
        assert (inp[key].score is not None) is ok
        if not ok:
            assert sid in inp[key].reason and "کهنه" in inp[key].reason


def test_freshness_table_is_recorded() -> None:
    assert G.FRESH_DAYS["DGS2"] == 7
    assert G.FRESH_DAYS["WALCL"] == 14
    assert G.FRESH_DAYS["WTREGEN"] == 14
    assert G.FRESH_DAYS["DTWEXBGS"] == 14


def test_stale_macro_input_is_absent_not_old_number() -> None:
    inp = G.measure(_src(macro=_macro(age_days=8)), _history(), NOW)
    assert inp["stable"].score is None
    assert "کهنه" in inp["stable"].reason


def test_unknown_age_is_absent() -> None:
    inp = G.measure(_src(macro=_macro(tether_ts=False)), _history(), NOW)
    assert inp["usdt_dom"].score is None
    assert "عمر نامعلوم" in inp["usdt_dom"].reason


def test_dominance_without_history_is_absent() -> None:
    inp = G.measure(_src(), {"version": 1, "days": {}}, NOW)
    for k in ("dom_ex", "usdt_dom"):
        assert inp[k].score is None
        assert "تاریخچه" in inp[k].reason


@pytest.mark.parametrize("back, ok", [(26, False), (27, True), (33, True),
                                      (34, False)])
def test_history_window_27_to_33_days(back, ok) -> None:
    inp = G.measure(_src(), _history(days_back=back), NOW)
    assert (inp["dom_ex"].score is not None) is ok


def test_history_picks_closest_to_30_days() -> None:
    h = {"version": 1, "days": {
        (NOW - timedelta(days=28)).strftime("%Y-%m-%d"): {"btc_dom_ex_stable": 50.0},
        (NOW - timedelta(days=30)).strftime("%Y-%m-%d"): {"btc_dom_ex_stable": 60.0},
    }}
    inp = G.measure(_src(), h, NOW)
    assert inp["dom_ex"].value == pytest.approx(1.0)


def test_missing_candles_are_absent() -> None:
    inp = G.measure(_src(btc={}, ethbtc=None), _history(), NOW)
    assert inp["ma50w"].score is None
    assert inp["ethbtc"].score is None


# ═══════════════ خروجی — قرارداد regime.json و تاریخچه ═══════════════

def test_doc_contract_and_book_reader_round_trip(tmp_path) -> None:
    """خواننده خود سبد باید همان امتیاز را بخواند — قرارداد نشست ۱."""
    inp = G.measure(_src(), _history(), NOW)
    res = G.aggregate(inp)
    doc = G.build_doc(res, inp, NOW)
    p = tmp_path / "regime.json"
    G.write_json(p, doc)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["score"] == res["score"]
    assert datetime.fromisoformat(loaded["generated_at"]).tzinfo is not None
    assert loaded["freshness_days"]["WALCL"] == 14
    assert "فرضیه" in loaded["note"]
    r = B.load_regime(p, now=NOW + timedelta(hours=1))
    score, note = r.score, r.source
    assert score == res["score"]


def test_history_records_scores_and_dominance() -> None:
    inp = G.measure(_src(), _history(), NOW)
    res = G.aggregate(inp)
    h = G.update_history(_history(), res, inp, NOW)
    day = h["days"][NOW.strftime("%Y-%m-%d")]
    assert day["btc_dom_ex_stable"] == pytest.approx(61.0)
    assert day["usdt_dominance"] == pytest.approx(5.0)
    assert day["btc_dominance"] == pytest.approx(57.0)
    for k in ("raw", "norm", "score", "band", "coverage", "inputs"):
        assert k in day
    assert day["inputs"]["money_price"] == pytest.approx(-0.75)
    # باند هر روز ثبت می‌شود — شمارش جابه‌جایی باند برای قاعده هیسترزیس
    assert day["band"] == res["band"]["name"]
    # تاریخچه پیشین پاک نمی‌شود
    assert len(h["days"]) == 2


def test_corrupt_history_is_an_error(tmp_path) -> None:
    p = tmp_path / "regime_history.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(G.RegimeError):
        G.load_history(p)


def test_missing_history_is_empty(tmp_path) -> None:
    assert G.load_history(tmp_path / "nope.json") == {"version": 1, "days": {}}


def test_report_says_hypothesis_and_lists_missing() -> None:
    inp = G.measure(_src(), {"version": 1, "days": {}}, NOW)
    md = G.render_md(G.build_doc(G.aggregate(inp), inp, NOW))
    assert "فرضیه، نه اندازه‌گیری" in md
    assert "تاریخچه" in md
    assert "تولید: **2026-09-25 07:00 UTC**" in md


def test_reference_file_is_labelled_hypothesis() -> None:
    ref = (ROOT / "references" / "macro-liquidity.md").read_text(encoding="utf-8")
    assert "فرضیه، نه اندازه‌گیری" in ref
    for k in G.INPUTS:
        assert f"`{k}`" in ref


# ═══════════════ main بدون شبکه ═══════════════

@pytest.fixture
def fake_net(monkeypatch):
    """همه واکشی‌ها مصنوعی؛ empty یعنی هیچ منبعی پاسخ نداد."""
    def install(empty: bool = False):
        now = datetime.now(UTC)
        btc, pair = _candles(now)
        fred = {"raw": {}, "derived": {}} if empty else _fred()
        if not empty:
            for r in fred["raw"].values():
                r["ts"] = now - timedelta(days=1)

        def fetch_macro(out):
            if not empty:
                for k, f in _macro().items():
                    out[k] = R.Field(f.value, f.source, now - timedelta(hours=6))

        def candles_first_ok(base, order, want, tests):
            if empty:
                return {}, None, None
            return (btc, "okx", None) if base == "BTC" else ({"1D": btc["1D"]}, "okx", pair)

        monkeypatch.setattr(R, "fetch_fred", lambda http_text: fred)
        monkeypatch.setattr(R, "fetch_macro", fetch_macro)
        monkeypatch.setattr(R, "probe_venues", lambda order: (list(order), []))
        monkeypatch.setattr(R, "candles_first_ok", candles_first_ok)
        monkeypatch.setattr(R, "FAILURES", [])
    return install


def test_main_writes_three_files(fake_net, tmp_path) -> None:
    fake_net()
    j, h, r = tmp_path / "regime.json", tmp_path / "hist.json", tmp_path / "r.md"
    rc = G.main(["--json", str(j), "--history", str(h), "--report", str(r)])
    assert rc == 0
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert math.isfinite(doc["score"])
    assert json.loads(h.read_text(encoding="utf-8"))["days"]
    assert "رژیم" in r.read_text(encoding="utf-8")


def test_main_zero_coverage_fails_loudly(fake_net, tmp_path) -> None:
    fake_net(empty=True)
    j = tmp_path / "regime.json"
    rc = G.main(["--json", str(j), "--history", str(tmp_path / "h.json"),
                 "--report", str(tmp_path / "r.md")])
    assert rc != 0
    assert not j.exists()
