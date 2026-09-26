"""
آزمون radar_positions.py — نشست ۳ نقشه رادار ۷، مورد ۱-۲.

تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶ — «دو دفتر»:
- دفتر موقعیت: کوین‌های موجود امروز. عضویت منجمد.
- دفتر معامله: هر معامله تازه، واقعی یا فرضی.
- قاعده ضدبهانه: هیچ پوزیشنی هرگز از دفتر معامله به دفتر موقعیت نمی‌رود.

holdings.json نسخه ۲ بر پایه **مقدار** است، نه دلار؛ ارزش هر روز از قیمت
زنده. دلار ثابت دلیل کهنه‌شدن نسخه ۱ بود، پس نسخه ۱ خطای صریح می‌دهد.

ناوردا، برای هر نماد دفتر موقعیت:
    مقدار منجمد + جمع تغییرات ثبت‌شده در دفتر کل = مقدار فعلی
هر اختلاف ثبت‌نشده، بالا یا پایین، خطای صریح. تغییر فقط با پنج نوع ردیف:
trim، exit، reenter، add، adjust.

بسته هفتگی = دوشنبه ۰۰:۰۰ به وقت جهانی. اوکی‌اکس با 1Wutc، گیت با 7d.
هیچ‌کدام در دسترس نبود یعنی «داده ندارم» — هرگز بازگشت به 1W هنگ‌کنگ.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 5, 15, tzinfo=UTC)


def _pos(sym, lots, book="position", status="open", **extra) -> dict:
    d = {"symbol": sym, "book": book, "status": status,
         "lots": [{"qty": q, "account": a, "entry": e} for q, a, e in lots],
         "invalidation": None}
    d.update(extra)
    return d


def _h() -> dict:
    return {
        "version": 2, "updated": NOW.isoformat(), "source": "آزمون",
        "frozen": {"date": "2026-09-25",
                   "members": {"SOL": 6.0, "ETH": 0.4, "TRX": 0.67}},
        "cash": [{"asset": "USDT", "qty": 3.0, "account": "A"}],
        "positions": [
            _pos("SOL", [(6.0, "A", None)]),
            _pos("ETH", [(0.25, "A", None), (0.15, "B", 2641.83)]),
            _pos("TRX", [(0.67, "A", None)]),
        ],
        "ledger": [],
    }


def _j(*trades) -> dict:
    return {"version": 1, "trades": list(trades)}


def _jt(did, setup="الف۱", book="trade", paper=False, sym="XYZ") -> dict:
    return {"id": 1, "symbol": sym, "decision_id": did, "setup_name": setup,
            "book": book, "paper": paper, "status": "open"}


def _row(action, sym, delta, **extra) -> dict:
    r = {"at": NOW.isoformat(), "action": action, "symbol": sym, "delta": delta}
    r.update(extra)
    return r


def _set_qty(h, sym, qty, account="A") -> None:
    for p in h["positions"]:
        if p["symbol"] == sym:
            p["lots"] = [{"qty": qty, "account": account, "entry": None}] if qty else []


# ═══════════════ قالب ═══════════════

def test_valid_v2_passes() -> None:
    P.validate(_h(), _j())


def test_v1_is_explicit_error() -> None:
    v1 = {"balance_total": 2070, "stable_usd": 129,
          "positions": [{"symbol": "SOL", "size_usd": 443}]}
    with pytest.raises(P.PositionsError, match="قالب قدیمی — مهاجرت لازم"):
        P.validate(v1, _j())


def test_updated_needs_timezone() -> None:
    h = _h()
    h["updated"] = "2026-09-25T05:15:00"
    with pytest.raises(P.PositionsError, match="منطقه زمانی"):
        P.validate(h, _j())


def test_duplicate_position_symbol_is_error() -> None:
    h = _h()
    h["positions"].append(_pos("SOL", [(1.0, "B", None)]))
    with pytest.raises(P.PositionsError, match="SOL"):
        P.validate(h, _j())


# ═══════════════ ناوردای دفتر کل ═══════════════

@pytest.mark.parametrize("qty", [6.5, 5.5])
def test_unrecorded_change_up_or_down_is_error(qty) -> None:
    h = _h()
    _set_qty(h, "SOL", qty)
    with pytest.raises(P.PositionsError, match="ثبت‌نشده"):
        P.validate(h, _j())


def test_recorded_trim_passes() -> None:
    h = _h()
    _set_qty(h, "SOL", 5.0)
    h["ledger"].append(_row("trim", "SOL", -1.0, price=120.0, reason="reserve"))
    P.validate(h, _j())


def test_trim_needs_known_reason() -> None:
    h = _h()
    _set_qty(h, "SOL", 5.0)
    h["ledger"].append(_row("trim", "SOL", -1.0, price=120.0, reason="حس بد"))
    with pytest.raises(P.PositionsError, match="reserve"):
        P.validate(h, _j())


def test_adjust_within_one_percent_passes() -> None:
    h = _h()
    _set_qty(h, "SOL", 6.05)
    h["ledger"].append(_row("adjust", "SOL", 0.05, reason="پاداش سهام‌گذاری"))
    P.validate(h, _j())


def test_adjust_above_one_percent_is_error() -> None:
    h = _h()
    _set_qty(h, "SOL", 6.12)
    h["ledger"].append(_row("adjust", "SOL", 0.12, reason="پاداش سهام‌گذاری"))
    with pytest.raises(P.PositionsError, match="۱٪"):
        P.validate(h, _j())


def test_add_without_journal_is_error() -> None:
    h = _h()
    _set_qty(h, "SOL", 7.0)
    h["ledger"].append(_row("add", "SOL", 1.0, price=120.0,
                            decision_id="D-9", setup_name="الف۱"))
    with pytest.raises(P.PositionsError, match="دفترچه"):
        P.validate(h, _j())


def test_add_with_position_journal_passes() -> None:
    h = _h()
    _set_qty(h, "SOL", 7.0)
    h["ledger"].append(_row("add", "SOL", 1.0, price=120.0,
                            decision_id="D-9", setup_name="الف۱"))
    P.validate(h, _j(_jt("D-9", book="position", sym="SOL")))


def test_add_with_trade_journal_is_move_error() -> None:
    """قاعده ضدبهانه: شناسه‌ای از دفتر معامله هرگز به دفتر موقعیت نمی‌رود."""
    h = _h()
    _set_qty(h, "SOL", 7.0)
    h["ledger"].append(_row("add", "SOL", 1.0, price=120.0,
                            decision_id="D-9", setup_name="الف۱"))
    with pytest.raises(P.PositionsError, match="جابه‌جایی"):
        P.validate(h, _j(_jt("D-9", book="trade", sym="SOL")))


def test_add_below_frozen_still_needs_journal() -> None:
    """خرید دوباره زیر مقدار منجمد هم ستاپ و شناسه می‌خواهد."""
    h = _h()
    _set_qty(h, "SOL", 5.0)
    h["ledger"] += [_row("trim", "SOL", -2.0, price=120.0, reason="reserve"),
                    _row("add", "SOL", 1.0, price=110.0,
                         decision_id="D-9", setup_name="الف۱")]
    with pytest.raises(P.PositionsError, match="دفترچه"):
        P.validate(h, _j())


def test_new_symbol_without_add_is_error() -> None:
    h = _h()
    h["positions"].append(_pos("LINK", [(10.0, "A", None)]))
    with pytest.raises(P.PositionsError, match="LINK"):
        P.validate(h, _j())


def test_trade_entry_moved_to_position_is_error() -> None:
    h = _h()
    h["positions"].append(_pos("XYZ", [(10.0, "A", 1.0)], decision_id="D-5",
                               setup_name="الف۱"))
    with pytest.raises(P.PositionsError, match="جابه‌جایی"):
        P.validate(h, _j(_jt("D-5", book="trade")))


# ═══════════════ خروج و ورود دوباره ═══════════════

def _exited() -> dict:
    h = _h()
    _set_qty(h, "SOL", 0.0)
    for p in h["positions"]:
        if p["symbol"] == "SOL":
            p["status"] = "exited"
    h["ledger"].append(_row("exit", "SOL", -6.0, price=95.0, level=100.0))
    return h


def test_exit_passes_and_sets_reentry_allowance() -> None:
    h = _exited()
    P.validate(h, _j())
    st = P.reentry_state(h, "SOL")
    assert st == {"level": 100.0, "max_qty": 6.0, "used": 0.0}


def test_exit_must_be_full() -> None:
    h = _h()
    _set_qty(h, "SOL", 1.0)
    h["ledger"].append(_row("exit", "SOL", -5.0, price=95.0, level=100.0))
    with pytest.raises(P.PositionsError, match="کامل"):
        P.validate(h, _j())


def test_reenter_within_allowance_passes() -> None:
    h = _exited()
    _set_qty(h, "SOL", 4.0)
    h["positions"][0]["status"] = "open"
    h["ledger"].append(_row("reenter", "SOL", 4.0, price=105.0,
                            weekly_close=104.0, week_close_at="2026-10-05T00:00:00+00:00"))
    P.validate(h, _j())


def test_reenter_above_allowance_is_error() -> None:
    h = _exited()
    _set_qty(h, "SOL", 7.0)
    h["positions"][0]["status"] = "open"
    h["ledger"].append(_row("reenter", "SOL", 7.0, price=105.0,
                            weekly_close=104.0, week_close_at="2026-10-05T00:00:00+00:00"))
    with pytest.raises(P.PositionsError, match="سهمیه"):
        P.validate(h, _j())


def test_reenter_needs_weekly_close_above_level() -> None:
    h = _exited()
    _set_qty(h, "SOL", 4.0)
    h["positions"][0]["status"] = "open"
    h["ledger"].append(_row("reenter", "SOL", 4.0, price=99.0,
                            weekly_close=100.0, week_close_at="2026-10-05T00:00:00+00:00"))
    with pytest.raises(P.PositionsError, match="بالای سطح"):
        P.validate(h, _j())


def test_status_must_match_quantity() -> None:
    h = _exited()
    h["positions"][0]["status"] = "open"
    with pytest.raises(P.PositionsError, match="وضعیت"):
        P.validate(h, _j())


# ═══════════════ دفتر معامله ═══════════════

def _trade(did="D-7", paper=False, **extra) -> dict:
    d = _pos("XYZ", [(100.0, "A", 1.0)], book="trade", decision_id=did,
             setup_name="الف۱", paper=paper, side="long", stop=0.9,
             opened=NOW.isoformat())
    d.update(extra)
    return d


def test_trade_needs_journal_record() -> None:
    h = _h()
    h["positions"].append(_trade())
    with pytest.raises(P.PositionsError, match="دفترچه"):
        P.validate(h, _j())


def test_trade_with_journal_passes() -> None:
    h = _h()
    h["positions"].append(_trade())
    P.validate(h, _j(_jt("D-7")))


def test_paper_flag_must_match_journal() -> None:
    h = _h()
    h["positions"].append(_trade(paper=True))
    with pytest.raises(P.PositionsError, match="فرضی"):
        P.validate(h, _j(_jt("D-7", paper=False)))


def test_trade_journal_book_must_be_trade() -> None:
    h = _h()
    h["positions"].append(_trade())
    with pytest.raises(P.PositionsError, match="book"):
        P.validate(h, _j(_jt("D-7", book="position")))


# ═══════════════ ارزش‌گذاری ═══════════════

PRICES = {"SOL": 116.45, "ETH": 2680.26, "TRX": 0.3386}


def test_value_from_live_prices() -> None:
    v = P.value(_h(), PRICES)
    rows = {r["symbol"]: r for r in v["rows"]}
    assert rows["SOL"]["value"] == pytest.approx(6.0 * 116.45)
    assert rows["ETH"]["value"] == pytest.approx(0.4 * 2680.26)
    assert v["stable_usd"] == pytest.approx(3.0)
    assert v["total"] == pytest.approx(6 * 116.45 + 0.4 * 2680.26 + 0.67 * 0.3386 + 3.0)
    assert v["incomplete"] is False


def test_dust_below_one_dollar() -> None:
    rows = {r["symbol"]: r for r in P.value(_h(), PRICES)["rows"]}
    assert rows["TRX"]["dust"] is True
    assert rows["SOL"]["dust"] is False


def test_missing_price_is_flagged_not_zero() -> None:
    v = P.value(_h(), {"SOL": 116.45, "ETH": None, "TRX": 0.3386})
    rows = {r["symbol"]: r for r in v["rows"]}
    assert rows["ETH"]["value"] is None
    assert v["incomplete"] is True and v["missing"] == ["ETH"]


def test_paper_trade_not_in_capital() -> None:
    h = _h()
    h["positions"].append(_trade(paper=True))
    v = P.value(h, {**PRICES, "XYZ": 1.0})
    base = P.value(_h(), PRICES)["total"]
    assert v["total"] == pytest.approx(base)


def test_entry_known_only_for_known_lots() -> None:
    rows = {r["symbol"]: r for r in P.value(_h(), PRICES)["rows"]}
    assert rows["ETH"]["avg_entry"] is None          # یک لات قیمت خرید ندارد
    assert rows["ETH"]["known_entry_qty"] == pytest.approx(0.15)


# ═══════════════ حرارت دفتر معامله ═══════════════

def _band(cap=4.0, maxpos=3) -> dict:
    return {"name": "محتاط", "cap": cap, "mult": 0.5, "maxpos": maxpos, "stable": 25}


def test_trade_risk_and_cap() -> None:
    h = _h()
    h["positions"].append(_trade())                           # ریسک 100×0.1 = 10
    t = P.trade_heat(h, _band(), total=1000.0)
    assert t["risk_real"] == pytest.approx(10.0)
    assert t["cap_usd"] == pytest.approx(40.0)
    assert t["effective"] == pytest.approx(10.0)
    assert t["over_cap"] is False


def test_paper_trade_risk_is_separate() -> None:
    h = _h()
    h["positions"].append(_trade(paper=True))
    t = P.trade_heat(h, _band(), total=1000.0)
    assert t["risk_real"] == 0.0 and t["risk_paper"] == pytest.approx(10.0)


def test_max_same_direction_positions() -> None:
    h = _h()
    for i in range(4):
        h["positions"].append(_trade(did=f"D-{i}", symbol=f"A{i}"))
    t = P.trade_heat(h, _band(maxpos=3), total=10_000.0)
    assert t["long_count"] == 4 and t["over_maxpos"] is True


def test_correlation_factor_from_three_alt_longs() -> None:
    """بند ۸.۳ اسکیل: سه لانگ آلت هم‌زمان به بالا، ضریب 1.5."""
    h = _h()
    for i in range(3):
        h["positions"].append(_trade(did=f"D-{i}", symbol=f"A{i}"))
    t = P.trade_heat(h, _band(maxpos=5), total=10_000.0)
    assert t["corr"] == 1.5
    assert t["effective"] == pytest.approx(30.0 * 1.5)
    h2 = _h()
    for i in range(2):
        h2["positions"].append(_trade(did=f"D-{i}", symbol=f"A{i}"))
    h2["positions"].append(_trade(did="D-B", symbol="BTC"))
    assert P.trade_heat(h2, _band(maxpos=5), total=10_000.0)["corr"] == 1.0


# ═══════════════ بسته هفتگی — لنگر وقت جهانی ═══════════════

class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p


def _okx_rows(weeks, last_open=True):
    """سطرهای اوکی‌اکس، جدید به قدیم، هفته‌ها از دوشنبه ۰۰:۰۰ UTC."""
    out = []
    for i, (monday, close) in enumerate(weeks):
        conf = "0" if (i == 0 and last_open) else "1"
        ts = int(monday.timestamp() * 1000)
        out.append([str(ts), "1", "1", "1", str(close), "1", "1", "1", conf])
    return out


MON1 = datetime(2026, 9, 14, tzinfo=UTC)
MON2 = datetime(2026, 9, 21, tzinfo=UTC)


def test_okx_uses_utc_weekly_bar_and_skips_open_week() -> None:
    seen = []

    def get(url, params=None, timeout=None):
        seen.append((url, dict(params or {})))
        return _Resp({"code": "0", "data": _okx_rows([(MON2, 120.0), (MON1, 110.0)])})
    w, why = P.weekly_close("SOL", get=get, now=NOW)
    assert seen[0][1]["bar"] == "1Wutc"
    assert w["close"] == 110.0 and w["venue"] == "okx"
    assert w["closed_at"] == MON2.isoformat()        # بسته هفته = دوشنبه بعد ۰۰:۰۰


def test_gate_fallback_uses_7d() -> None:
    seen = []

    def get(url, params=None, timeout=None):
        seen.append(dict(params or {}))
        if "okx" in url:
            return _Resp({"code": "50001", "data": []})
        return _Resp([[str(int(MON1.timestamp())), "1", "111.0", "1", "1", "1", "1"],
                      [str(int(MON2.timestamp())), "1", "121.0", "1", "1", "1", "1"]])
    w, why = P.weekly_close("SOL", get=get, now=NOW)
    assert any(p.get("interval") == "7d" for p in seen)
    assert w["venue"] == "gate" and w["close"] == 111.0
    assert why                                      # دلیل ردشدن اوکی‌اکس ثبت شد


def test_non_monday_anchor_is_rejected() -> None:
    """لنگر هنگ‌کنگ (یکشنبه 16:00 UTC) پذیرفته نمی‌شود — داده ندارم."""
    sun = datetime(2026, 9, 13, 16, 0, tzinfo=UTC)

    def get(url, params=None, timeout=None):
        if "okx" in url:
            return _Resp({"code": "0", "data": _okx_rows([(sun + timedelta(days=7), 1.0),
                                                          (sun, 2.0)])})
        return _Resp([])
    w, why = P.weekly_close("SOL", get=get, now=NOW)
    assert w is None
    assert any("لنگر" in r for r in why)


def test_no_venue_means_no_data() -> None:
    def get(url, params=None, timeout=None):
        return _Resp({"code": "1", "data": []}) if "okx" in url else _Resp([])
    w, why = P.weekly_close("SOL", get=get, now=NOW)
    assert w is None and why


def test_never_requests_hong_kong_weekly_bar() -> None:
    """
    درخواستی که واقعاً فرستاده می‌شود سنجیده می‌شود، نه متن فایل. تا نشست ۳ب
    این آزمون متن radar_positions.py را برای "1W" می‌گشت؛ ولی "1W" نام داخلی
    تایم‌فریم است و نام درخواستی حالا از radar_anchor می‌آید — تصمیم کاربر،
    ایستگاه ۱ نشست ۳ب: آزمون متنی شکننده است.
    """
    seen = []

    def get(url, params=None, timeout=None):
        seen.append(dict(params or {}))
        return _Resp({"code": "0", "data": _okx_rows([(MON2, 120.0), (MON1, 110.0)])})
    P.weekly_close("SOL", get=get, now=NOW)
    P.weekly_closes("SOL", 1, get=get, now=NOW)
    assert seen and {p["bar"] for p in seen} == {"1Wutc"}


# ═══════════════ فرمان‌ها ═══════════════

@pytest.fixture
def files(tmp_path):
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(_h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(_j(), ensure_ascii=False), encoding="utf-8")
    return hp, jp


def _run(files, *args) -> int:
    """همه مسیرها صریح و موقت — دفتر هزینه فرصت واقعی هرگز لمس نشود."""
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"), *args])


def _read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_cli_trim_writes_ledger_and_keeps_invariant(files) -> None:
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "1.5",
                "--price", "120", "--reason", "reserve") == 0
    h = _read(files[0])
    assert h["ledger"][-1]["action"] == "trim" and h["ledger"][-1]["delta"] == -1.5
    assert P.position_qty(next(p for p in h["positions"] if p["symbol"] == "SOL")) == 4.5
    assert h["updated"] != NOW.isoformat()          # زمان به‌روز شد
    P.validate(h, _j())


def test_cli_trim_multi_account_needs_account(files) -> None:
    assert _run(files, "trim", "--symbol", "ETH", "--qty", "0.1",
                "--price", "2700", "--reason", "reserve") != 0
    assert _read(files[0])["ledger"] == []           # فایل دست نخورد
    assert _run(files, "trim", "--symbol", "ETH", "--qty", "0.1", "--account", "B",
                "--price", "2700", "--reason", "reserve") == 0


def test_cli_exit_then_reenter(files, monkeypatch) -> None:
    assert _run(files, "exit", "--symbol", "SOL", "--price", "95", "--level", "100") == 0
    h = _read(files[0])
    assert next(p for p in h["positions"] if p["symbol"] == "SOL")["status"] == "exited"
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (
        {"close": 104.0, "closed_at": MON2.isoformat(), "venue": "okx"}, []))
    assert _run(files, "reenter", "--symbol", "SOL", "--qty", "4", "--price", "105",
                "--account", "A") == 0
    h = _read(files[0])
    assert next(p for p in h["positions"] if p["symbol"] == "SOL")["status"] == "open"
    assert h["ledger"][-1]["weekly_close"] == 104.0
    P.validate(h, _j())


def test_cli_reenter_below_level_is_refused(files, monkeypatch) -> None:
    _run(files, "exit", "--symbol", "SOL", "--price", "95", "--level", "100")
    before = _read(files[0])
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (
        {"close": 99.0, "closed_at": MON2.isoformat(), "venue": "okx"}, []))
    assert _run(files, "reenter", "--symbol", "SOL", "--qty", "4", "--price", "99",
                "--account", "A") != 0
    assert _read(files[0]) == before


def test_cli_reenter_without_data_is_refused(files, monkeypatch) -> None:
    _run(files, "exit", "--symbol", "SOL", "--price", "95", "--level", "100")
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (None, ["شبکه"]))
    assert _run(files, "reenter", "--symbol", "SOL", "--qty", "4", "--price", "99",
                "--account", "A") != 0


def test_cli_add_needs_position_journal(files) -> None:
    hp, jp = files
    assert _run(files, "add", "--symbol", "LINK", "--qty", "10", "--price", "14",
                "--account", "A", "--decision-id", "D-9", "--setup-name", "الف۱") != 0
    jp.write_text(json.dumps(_j(_jt("D-9", book="position", sym="LINK")),
                             ensure_ascii=False), encoding="utf-8")
    assert _run(files, "add", "--symbol", "LINK", "--qty", "10", "--price", "14",
                "--account", "A", "--decision-id", "D-9", "--setup-name", "الف۱") == 0
    h = _read(hp)
    link = next(p for p in h["positions"] if p["symbol"] == "LINK")
    assert link["book"] == "position" and link["lots"][0]["entry"] == 14.0


def test_cli_adjust(files) -> None:
    assert _run(files, "adjust", "--symbol", "SOL", "--qty", "0.03",
                "--reason", "پاداش سهام‌گذاری") == 0
    assert _run(files, "adjust", "--symbol", "SOL", "--qty", "0.5",
                "--reason", "پاداش سهام‌گذاری") != 0


def test_cli_validate_reports_error_loudly(files, capsys) -> None:
    hp, _ = files
    h = _read(hp)
    _set_qty(h, "SOL", 9.0)
    hp.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
    assert _run(files, "validate") != 0
    assert "ثبت‌نشده" in capsys.readouterr().err


def test_holdings_age_from_updated_field() -> None:
    """کهنگی از میدان updated، نه زمان تغییر فایل — درس regime.json."""
    assert P.age_days(_h(), now=NOW + timedelta(days=8)) == pytest.approx(8.0)


def test_reentry_state_with_add_rows_present() -> None:
    """خواندن سهمیه نباید روی فایلی که ردیف add دارد بیفتد."""
    h = _exited()
    h["frozen"]["members"]["LINK"] = 0.0
    h["positions"].append(_pos("LINK", [(10.0, "A", 14.0)]))
    h["ledger"].append(_row("add", "LINK", 10.0, price=14.0,
                            decision_id="D-9", setup_name="الف۱"))
    assert P.reentry_state(h, "SOL") == {"level": 100.0, "max_qty": 6.0, "used": 0.0}
