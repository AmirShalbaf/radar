"""
بازخرید با انتخاب کیفی — بند ۳ متن ۱۸، ک۸۸ و ک۹۵. تصمیم کاربر ۲۵ اکتبر ۲۰۲۶: «مقدار از
رژیم، انتخاب با کیفیت»؛ جانشین «بازخرید فقط همان ارزها» در رویداد ۱۰۳.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
import radar_rebuy as RB
import radar_watch as W
import radar_telegram as TG

UTC = timezone.utc
NOW = datetime(2026, 10, 28, 13, 0, tzinfo=UTC)


def _t(s):
    return datetime.fromisoformat(s)


# ── دفتر ساختگی: دو نقشه، یکی بایگانی ──

def _trim(sym, qty, price, at):
    return {"at": at, "action": "trim", "symbol": sym, "delta": -qty, "price": price,
            "reason": "reserve", "account": "LBank", "gross": qty * price,
            "fee": round(qty * price * 0.001, 10), "net": round(qty * price * 0.999, 10)}


def _h():
    ledger = [_trim("BNB", 0.327, 718.07, "2026-10-17T15:33:55+00:00"),
              _trim("ETH", 0.074, 2490.0, "2026-10-21T13:06:34+00:00"),
              _trim("TAO", 0.1538, 254.4, "2026-10-24T03:47:08+00:00"),
              _trim("ETH", 0.037, 2381.81, "2026-10-24T03:48:34+00:00"),
              _trim("SOL", 0.15, 102.56, "2026-10-24T03:49:33+00:00")]
    members = {"SOL": 5.63105369, "ETH": 0.148257, "BNB": 0.3277579, "TAO": 0.153892,
               "AAVE": 1.04895}
    cash0 = 100.0
    net = sum(r["net"] for r in ledger)
    pos = []
    for s, q in members.items():
        left = q - sum(-r["delta"] for r in ledger if r["symbol"] == s)
        inv = {"SOL": 96.7108, "ETH": 2380.5606, "AAVE": 106.892}.get(s)
        p = {"symbol": s, "book": "position", "status": "open", "invalidation": inv,
             "lots": [{"qty": left, "account": "LBank", "entry": None}]}
        if inv:
            p["invalidation_since"] = "2026-09-25T21:34:47+00:00"
        pos.append(p)
    return {"version": 2, "updated": "2026-10-24T04:02:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": members,
                       "cash": [{"asset": "USDT", "qty": cash0, "account": "LBank"}]},
            "cash": [{"asset": "USDT", "qty": round(cash0 + net, 10), "account": "LBank"}],
            "positions": pos, "ledger": ledger}


P17 = {"title": "نقشه ۱۷", "created": "2026-10-17T15:32:00+00:00",
       "deadline": "2026-10-19T00:00:00+00:00", "account": "LBank",
       "steps": [{"symbol": "BNB", "qty": 0.327, "price": None},
                 {"symbol": "ETH", "qty": 0.074, "price": 2490}],
       "rebuy": {"steps": [{"symbol": "BNB", "qty": 0.327, "floor": 702.39, "min_below_sale_pct": 5},
                           {"symbol": "ETH", "qty": 0.074, "floor": 2380.56, "min_below_sale_pct": 5}]},
       "closed": {"at": "2026-10-21T13:06:34+00:00", "reason": "همه پله‌ها اجرا شد"}}
P08 = {"title": "نقشه ۸", "created": "2026-10-08T00:00:00+00:00",
       "deadline": "2026-10-15T00:00:00+00:00",
       "steps": [{"symbol": "ETH", "qty": 0.04, "price": 2625,
                  "cancelled": {"at": "2026-10-17T15:32:00+00:00", "reason": "لغو"}}],
       "rebuy": {"steps": [{"symbol": "ETH", "qty": 0.04, "floor": 2380.56, "min_below_sale_pct": 5}]},
       "closed": {"at": "2026-10-17T15:32:00+00:00", "reason": "اجرا نشد"}}
P24 = {"title": "نقشه ۲۴", "created": "2026-10-24T03:46:49+00:00",
       "deadline": "2026-10-26T00:00:00+00:00", "account": "LBank",
       "steps": [{"symbol": "TAO", "qty": 0.1538, "price": 254.4},
                 {"symbol": "ETH", "qty": 0.037, "price": None},
                 {"symbol": "SOL", "qty": 0.15, "price": None},
                 {"symbol": "ETH", "qty": 0.0372, "price": 2430}],
       "rebuy": {"steps": [{"symbol": "TAO", "qty": 0.1538, "floor": 202.51, "min_below_sale_pct": 5},
                           {"symbol": "ETH", "qty": 0.0742, "floor": 2380.56, "min_below_sale_pct": 5},
                           {"symbol": "SOL", "qty": 0.15, "floor": 96.71, "min_below_sale_pct": 5}]}}


def _watch():
    return {"version": 2, "updated": "2026-10-17T15:40:00+00:00",
            "positions": [{"symbol": "SOL", "invalidation": 96.7108,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"},
                          {"symbol": "ETH", "invalidation": 2380.5606,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"},
                          {"symbol": "AAVE", "invalidation": 106.892,
                           "invalidation_since": "2026-09-25T21:34:47+00:00"}],
            "reserve_plan": json.loads(json.dumps(P24)),
            "reserve_archive": [json.loads(json.dumps(P08)), json.loads(json.dumps(P17))],
            "dormant": [{"symbol": "TAO", "invalidation": 202.5065,
                         "invalidation_since": "2026-09-26T05:04:16+00:00", "touches": 4,
                         "warnings": [295.35], "anchor": 261.67, "anchor_atr_w": 46.990697,
                         "reason": "ناچیز پس از فروش ذخیره ۲۴ اکتبر"}]}


# ── سهمیه ──

def test_quota_table_all_plans() -> None:
    rows = {(r["plan"], r["symbol"]): r for r in RB.quota_table(_watch(), _h())}
    assert rows[("نقشه ۱۷", "BNB")]["open"] == pytest.approx(0.327)
    assert rows[("نقشه ۱۷", "ETH")]["open"] == pytest.approx(0.074)
    # نقشه ۸: پله‌ها لغو شد، فروشی نبود؛ فروش‌های پس از بستنش شمرده نمی‌شوند
    assert rows[("نقشه ۸", "ETH")]["sold"] == 0
    assert rows[("نقشه ۲۴", "TAO")]["open"] == pytest.approx(0.1538)
    assert rows[("نقشه ۲۴", "ETH")]["sold"] == pytest.approx(0.037)
    assert rows[("نقشه ۲۴", "SOL")]["open"] == pytest.approx(0.15)
    q = RB.open_quota(list(rows.values()))
    assert q["ETH"]["qty"] == pytest.approx(0.111)
    assert q["ETH"]["last_sale"] == _t("2026-10-24T03:48:34+00:00")


def test_rebought_reduces_quota() -> None:
    h = _h()
    h["ledger"].append({"at": "2026-10-28T10:00:00+00:00", "action": "reenter", "symbol": "TAO",
                        "delta": 0.1, "price": 233.0, "account": "LBank", "quota": "reserve",
                        "plan": P24["created"], "gross": 23.3, "fee": 0.0233,
                        "fee_asset": "USDT", "cost": 23.3233})
    rows = {(r["plan"], r["symbol"]): r for r in RB.quota_table(_watch(), h)}
    assert rows[("نقشه ۲۴", "TAO")]["rebought"] == pytest.approx(0.1)
    assert rows[("نقشه ۲۴", "TAO")]["open"] == pytest.approx(0.0538)


def test_plan_without_rebuy_listed() -> None:
    w = _watch()
    w["reserve_archive"].insert(0, {"title": "نقشه ۲۵ سپتامبر", "created": "2026-09-25T16:00:00+00:00",
                                    "deadline": "2026-10-05T00:00:00+00:00", "steps": [],
                                    "closed": {"at": "2026-10-04T14:37:32+00:00", "reason": "x"}})
    rows = RB.quota_table(w, _h())
    assert rows[0]["plan"] == "نقشه ۲۵ سپتامبر" and rows[0]["symbol"] is None


# ── بودجه ──

def _regime(tb, at="2026-10-28T12:00:00+00:00"):
    return {"generated_at": at, "score": -0.4, "band": {"name": tb}, "trade_band": {"name": tb}}


def _hist(*bands, start="2026-10-20"):
    d0 = datetime.fromisoformat(start)
    return {"days": {f"{d0 + timedelta(days=i):%Y-%m-%d}": {"band": b, "trade_band": b}
                     for i, b in enumerate(bands)}}


def test_release_when_band_rises() -> None:
    hist = _hist("انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی",
                 "انقباضی")
    rel, why = RB.band_release(_regime("محتاط"), hist, NOW)
    assert rel == {"from": "انقباضی", "to": "محتاط", "day": "2026-10-28", "target": 25,
                   "old_target": 40}


def test_no_release_when_band_falls_or_stays() -> None:
    hist = _hist("محتاط", "محتاط", "انقباضی")
    assert RB.band_release(_regime("انقباضی", "2026-10-23T12:00:00+00:00"), hist,
                           datetime(2026, 10, 23, 13, tzinfo=UTC)) == (None, None)
    hist = _hist("انقباضی", "محتاط", "محتاط", "محتاط")
    rel, _ = RB.band_release(_regime("محتاط", "2026-10-24T12:00:00+00:00"), hist,
                             datetime(2026, 10, 24, 13, tzinfo=UTC))
    assert rel["day"] == "2026-10-21"                  # تغییر قدیمی‌تر، هنوز آخرین تغییر
    rel, why = RB.band_release(_regime("محتاط", "2026-10-10T12:00:00+00:00"), hist, NOW)
    assert rel is None and "کهنه" in why


def test_budget() -> None:
    rel = {"target": 25}
    assert RB.budget(rel, {"stable_usd": 640.0, "total": 1600.0}) == pytest.approx(240.0)
    assert RB.budget(rel, {"stable_usd": 640.0, "total": 1600.0, "incomplete": True}) is None
    assert RB.budget(None, {"stable_usd": 640.0, "total": 1600.0}) is None


# ── پذیرش و رتبه ──

VA = {"val": 90.0, "vah": 110.0, "poc": 100.0}
LISTED = ["BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "LINK", "AAVE", "SUI", "BNB"]


def _d(px, lvl, rs, va=VA):
    return {"price": px, "level": lvl, "level_src": "watch.json", "va": va, "rs30": rs}


def _data(**over):
    base = {"SOL": _d(100.0, 96.7, 3.0), "ETH": _d(100.0, 95.0, 1.0), "TAO": _d(100.0, 80.0, 2.0),
            "HYPE": _d(100.0, 70.0, 9.0), "ONDO": _d(100.0, 60.0, -20.0),
            "LINK": _d(100.0, 60.0, -8.0), "AAVE": _d(100.0, 60.0, -5.0),
            "SUI": _d(100.0, 60.0, -3.0), "BNB": _d(100.0, 60.0, 0.5)}
    base.update(over)
    return base


def _q(**syms):
    return {s: {"qty": q, "last_sale": _t(at), "floor": 1.0, "plans": []}
            for s, (q, at) in syms.items()}


def test_rejections_have_reasons() -> None:
    data = _data(ETH=_d(94.0, 95.0, 1.0), TAO=_d(85.0, 80.0, 2.0),
                 BNB=_d(100.0, None, 0.5), BTC=_d(80000.0, None, 0.0))
    ev = RB.evaluate(data, LISTED, {}, 100.0)
    why = {r["symbol"]: r["why"] for r in ev["rejected"]}
    assert "زیر سطح ابطال" in why["ETH"]
    assert "زیر ناحیه ارزش ۱۵ روزه" in why["TAO"]
    assert "سطح ابطال ساختاری ندارد" in why["BNB"]
    assert "معیار قدرت نسبی" in why["BTC"]
    # یک‌سوم پایین فهرست پایش: ۹ نماد بی BTC با داده — سه پایین‌ترین ONDO، LINK، AAVE
    assert "یک‌سوم پایین" in why["ONDO"] and "یک‌سوم پایین" in why["LINK"]
    assert "یک‌سوم پایین" in why["AAVE"]
    assert "SUI" not in why


def test_replacement_needs_five_points() -> None:
    q = _q(SOL=(0.15, "2026-10-24T03:49:33+00:00"))
    ev = RB.evaluate(_data(HYPE=_d(100.0, 70.0, 7.9)), LISTED, q, 50.0)
    assert [r["symbol"] for r in ev["ranked"]][0] == "SOL"           # 7.9 < 3.0 + 5
    ev = RB.evaluate(_data(HYPE=_d(100.0, 70.0, 8.0)), LISTED, q, 50.0)
    top = ev["ranked"][0]
    assert top["symbol"] == "HYPE" and top["replaces"] == "SOL" and "جایگزین SOL" in top["why"]


def test_tie_breaks_by_most_recent_sale() -> None:
    q = _q(SOL=(0.15, "2026-10-24T03:49:33+00:00"), TAO=(0.1538, "2026-10-24T03:47:08+00:00"))
    ev = RB.evaluate(_data(SOL=_d(100.0, 96.7, 2.0), TAO=_d(100.0, 80.0, 2.0)), LISTED, q, 10.0)
    syms = [r["symbol"] for r in ev["ranked"] if r["quota"] > 0]
    assert syms[:2] == ["SOL", "TAO"]


def test_allocation_quota_limit_then_next_then_reserve() -> None:
    q = _q(SOL=(0.15, "2026-10-24T03:49:33+00:00"))
    data = {"SOL": _d(100.0, 96.7, 3.0), "ETH": _d(100.0, 95.0, 1.0),
            "ONDO": _d(100.0, 60.0, -20.0)}
    ev = RB.evaluate(data, LISTED, q, 40.0)
    got = {r["symbol"]: r["usd"] for r in ev["ranked"]}
    assert got["SOL"] == pytest.approx(15.0)            # سهمیه 0.15 × 100
    assert got["ETH"] == pytest.approx(25.0)
    assert ev["left"] == pytest.approx(0.0)
    ev = RB.evaluate({"SOL": _d(100.0, 96.7, 3.0)}, LISTED, q, 40.0)
    assert ev["left"] == pytest.approx(25.0)
    txt = "\n".join(RB.lines({"from": "انقباضی", "to": "محتاط", "day": "2026-10-28",
                              "target": 25, "old_target": 40}, 40.0, ev,
                             {"stable_usd": 640.0, "total": 2400.0}))
    assert "در ذخیره می‌ماند: 25 دلار" in txt


# ── حکم بازخرید همان ارز — rebuy_status ──

def test_verdict_from_rebuy_status() -> None:
    w, h = _watch(), _h()
    st = {r["symbol"]: r for r in W.rebuy_status(w["reserve_plan"], h, {"TAO": 233.0, "SOL": 99.0,
                                                                         "ETH": 2500.0})}
    assert W.rebuy_verdict(st["TAO"], released=False)[0]           # پنجره نزدیک ابطال باز
    ok, why = W.rebuy_verdict(st["SOL"], released=False)
    assert not ok and "سقف" in why
    assert W.rebuy_verdict(st["SOL"], released=True)[0]
    below = W.rebuy_status(w["reserve_plan"], h, {"SOL": 96.0})
    assert not W.rebuy_verdict([r for r in below if r["symbol"] == "SOL"][0], released=True)[0]


# ── ک۸۸: reenter با سهمیه reserve ──

PX = {"SOL": 100.0, "ETH": 2500.0, "BNB": 700.0, "TAO": 233.0, "AAVE": 150.0}


@pytest.fixture
def files(tmp_path, monkeypatch):
    return make_files(tmp_path, monkeypatch)


def make_files(tmp_path, monkeypatch):
    """پرونده‌های فرمان در پوشه موقت؛ قیمت سقف تمرکز ساختگی — بند ۴ متن ۱۸."""
    monkeypatch.chdir(tmp_path)
    if hasattr(P, "_prices"):
        monkeypatch.setattr(P, "_prices", lambda syms: {s: PX.get(s) for s in syms})
    (tmp_path / "holdings.json").write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "watch.json").write_text(json.dumps(_watch(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "radar_journal.json").write_text(json.dumps({"version": 1, "trades": [], "decisions": [
        {"decision_id": "RD-20261028-01", "human": "defied", "action": "بازخرید SOL"},
        {"decision_id": "RD-20261028-02", "human": "followed", "action": "x"}]}), encoding="utf-8")
    (tmp_path / "regime.json").write_text(json.dumps(_regime("انقباضی")), encoding="utf-8")
    (tmp_path / "regime_history.json").write_text(json.dumps(_hist("انقباضی")), encoding="utf-8")
    monkeypatch.setattr(P, "_now", lambda: "2026-10-28T13:00:00+00:00")
    monkeypatch.setattr(P, "_clock", lambda: NOW)
    return tmp_path


BASE = ["--holdings", "holdings.json", "--journal", "radar_journal.json", "--optcost", "oc.json",
        "reenter", "--account", "LBank", "--at", "2026-10-28T12:00:00+00:00"]


def _re(sym, qty, price, gross=None, fee="0.05", plan=P24["created"], extra=()):
    g = gross if gross is not None else f"{qty * price:.10g}"
    return BASE + ["--symbol", sym, "--qty", str(qty), "--price", str(price),
                   "--reserve-plan", plan, "--gross", g, "--fee", fee, *extra]


def _load(p):
    return json.loads((p / "holdings.json").read_text(encoding="utf-8"))


def test_reenter_reserve_needs_receipt(files, capsys) -> None:
    args = [a for a in _re("TAO", 0.1, 233.0) if a not in ("--gross", "23.3", "--fee", "0.05")]
    assert P.main(args) == 2
    assert "رسید" in capsys.readouterr().err


def test_reenter_reserve_pays_cash_and_restores_tao(files) -> None:
    before = _load(files)
    cash0 = before["cash"][0]["qty"]
    assert P.main(_re("TAO", 0.1, 233.0)) == 0
    h = _load(files)
    row = h["ledger"][-1]
    assert row["quota"] == "reserve" and row["plan"] == P24["created"]
    assert row["cost"] == pytest.approx(23.35) and row["gross"] == pytest.approx(23.3)
    assert h["cash"][0]["qty"] == pytest.approx(cash0 - 23.35)
    tao = next(p for p in h["positions"] if p["symbol"] == "TAO")
    assert tao["invalidation"] == 202.5065
    assert tao["invalidation_since"] == "2026-09-26T05:04:16+00:00"
    w = json.loads((files / "watch.json").read_text(encoding="utf-8"))
    assert any(it["symbol"] == "TAO" for it in w["positions"]) and not w.get("dormant")
    assert P.level_mismatches(h, w) == []
    P.validate(h, {"trades": []})                      # ناوردای کوین و نقد


def test_reenter_reserve_over_quota(files, capsys) -> None:
    assert P.main(_re("TAO", 0.2, 233.0)) == 2
    assert "سهمیه" in capsys.readouterr().err


def test_reenter_reserve_negative_verdict_needs_labeled_deviation(files, capsys) -> None:
    # SOL در 99: بالای سقف 97.432 و بودجه آزاد نشده
    assert P.main(_re("SOL", 0.15, 99.0)) == 2
    assert "سرپیچی" in capsys.readouterr().err
    assert P.main(_re("SOL", 0.15, 99.0, extra=("--deviation", "RD-20261028-02"))) == 2
    assert P.main(_re("SOL", 0.15, 99.0, extra=("--deviation", "RD-20261028-01"))) == 0
    row = _load(files)["ledger"][-1]
    assert row["deviation"] == "RD-20261028-01" and row["window"] == "above"


def test_reenter_reserve_fee_in_coin(files) -> None:
    cash0 = _load(files)["cash"][0]["qty"]
    q0 = next(p for p in _load(files)["positions"] if p["symbol"] == "TAO")["lots"][0]["qty"]
    assert P.main(_re("TAO", 0.1, 233.0, fee="0.0002", extra=("--fee-asset", "TAO"))) == 0
    h = _load(files)
    tao = next(p for p in h["positions"] if p["symbol"] == "TAO")
    assert sum(l["qty"] for l in tao["lots"]) == pytest.approx(q0 + 0.0998)
    assert h["cash"][0]["qty"] == pytest.approx(cash0 - 23.3)


def test_reenter_reserve_unknown_plan_or_symbol(files, capsys) -> None:
    assert P.main(_re("TAO", 0.1, 233.0, plan="2026-10-01T00:00:00+00:00")) == 2
    assert P.main(_re("AAVE", 0.1, 150.0)) == 2


# ── ک۹۵: یادآوری بودجه آزادشده در پایشگر ──

def test_budget_alert_once_per_band_change(monkeypatch) -> None:
    w, h = _watch(), _h()
    hist = _hist("انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی", "انقباضی",
                 "انقباضی")
    prices = {"SOL": 100.0, "ETH": 2500.0, "BNB": 700.0, "TAO": 233.0, "AAVE": 150.0}
    rs = {"SOL": 3.0, "ETH": 2.0, "BNB": 1.0, "TAO": 4.0, "AAVE": 0.0}
    data = {s: _d(p, p * 0.8, rs[s], va={"val": p * 0.9, "vah": p * 1.1, "poc": p})
            for s, p in prices.items()}
    state: dict = {}
    msgs = W.budget_alert(w, h, state, NOW, regime=_regime("محتاط"), history=hist,
                          price=prices.get, gather=lambda syms, quotas: data,
                          listed=lambda: LISTED)
    assert len(msgs) == 1
    m = msgs[0]
    assert "بودجه آزادشده" in m and "از انقباضی به محتاط" in m and "فهرست رتبه‌دار" in m
    W.commit_sent(msgs, state)
    assert W.budget_alert(w, h, state, NOW, regime=_regime("محتاط"), history=hist,
                          price=prices.get, gather=lambda syms, quotas: data,
                          listed=lambda: LISTED) == []


# ── گزارش سبد: سهمیه همه نقشه‌ها، زیربخش انتخاب کیفی و ردیف اقدام یک‌باره ──

import radar_book as B
import radar_budget as BG


def _rb(today="2026-10-28", amount=240.0):
    rel = {"from": "انقباضی", "to": "محتاط", "day": "2026-10-28", "target": 25, "old_target": 40}
    ev = RB.evaluate(_data(), LISTED, _q(SOL=(0.15, "2026-10-24T03:49:33+00:00")), amount)
    return {"rows": RB.quota_table(_watch(), _h()), "release": rel, "warn": None,
            "amount": amount, "ev": ev, "val": {"stable_usd": 640.0, "total": 1600.0},
            "today": today}


def test_book_shows_quotas_selection_and_one_time_action() -> None:
    txt = B.build_report(_h(), [], BG.band_by_name("محتاط"), [], rebuy=_rb())
    assert "### سهمیه بازخرید باز — همه نقشه‌ها" in txt
    assert "| نقشه ۱۷ | BNB | 0.327 | 0.327 | 0 | **0.327** |" in txt
    assert "### بازخرید با انتخاب کیفی" in txt and "فهرست رتبه‌دار" in txt
    assert "1. **بودجه آزادشده** — باند با هیسترزیس از انقباضی به محتاط" in txt
    later = B.build_report(_h(), [], BG.band_by_name("محتاط"), [], rebuy=_rb(today="2026-10-29"))
    assert "### بازخرید با انتخاب کیفی" in later
    assert "**بودجه آزادشده** — باند با هیسترزیس از انقباضی به محتاط؛" not in later


def test_book_without_release_says_why() -> None:
    rb = {"rows": RB.quota_table(_watch(), _h()), "release": None, "warn": None,
          "amount": None, "ev": None, "val": {"stable_usd": 1.0, "total": 2.0}, "today": None}
    txt = B.build_report(_h(), [], BG.band_by_name("انقباضی"), [], rebuy=rb)
    assert "بودجه آزادشده: نیست — آخرین تغییر باند با هیسترزیس" in txt


def test_rebuy_view_reads_files_and_injected_data(tmp_path) -> None:
    (tmp_path / "r.json").write_text(json.dumps(_regime("محتاط")), encoding="utf-8")
    (tmp_path / "hh.json").write_text(json.dumps(_hist(*["انقباضی"] * 8)), encoding="utf-8")
    val = {"stable_usd": 640.0, "total": 1600.0}
    rv = B.rebuy_view(_watch(), _h(), val, {}, None, str(tmp_path / "r.json"),
                      str(tmp_path / "hh.json"), now=NOW,
                      gather=lambda syms, quotas: {s: _data().get(s, _d(None, None, None))
                                                   for s in syms},
                      listed=lambda: LISTED)
    assert rv["release"]["to"] == "محتاط" and rv["amount"] == pytest.approx(240.0)
    assert rv["today"] == "2026-10-28"
    assert rv["ev"]["ranked"][0]["usd"] > 0
    manual = B.rebuy_view(_watch(), _h(), val, {}, None, "x", "y", regime_manual=True)
    assert manual["release"] is None and "دستی" in manual["warn"]
