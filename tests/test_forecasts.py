"""
دفتر پیش‌بینی — بند ۷ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

forecasts.json و فرمان کوچک افزودن و نمره‌دادن. هر پیش‌بینی: شناسه، تاریخ، منبع پیش‌بینی،
نماد، سناریوها با احتمال، معیار دقیق، مهلت، منبع قیمت. نمره Brier وقتی مهلت گذشت، از بسته
روزانه همان منبعی که بسته هفتگی را می‌خواند — اوکی‌اکس 1Dutc، سپس گیت 1d. خلاصه در گزارش
هفتگی.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_forecast as F
import radar_positions as P

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
CLOSE = datetime(2026, 10, 31, tzinfo=UTC)
OPEN = CLOSE - timedelta(days=1)


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p


def _okx(open_at, close, conf="1"):
    return [str(int(open_at.timestamp() * 1000)), "1", "1", "1", str(close), "1", "1", "1", conf]


def _real():
    return F.load(str(ROOT / "forecasts.json"))


# ── داده واقعی: پیش‌بینی ۲۶ اکتبر برای BTC ──

def test_first_entry_btc_oct26() -> None:
    doc = _real()
    f = doc["forecasts"][0]
    assert f["symbol"] == "BTC" and f["made_at"] == "2026-10-26"
    assert f["close_at"] == "2026-10-31T00:00:00+00:00"
    sc = {s["name"]: (s["p"], s["interval"]) for s in f["scenarios"]}
    assert sc == {"مثبت": (0.20, "(82000,)"), "پایه": (0.50, "[78000,82000]"),
                  "منفی": (0.30, "(,78000)")}
    assert "اوکی‌اکس 1Dutc" in f["price_source"] and "گیت 1d" in f["price_source"]
    assert f["criterion"] and f["source"] and f.get("result") is None


# ── بازه و افراز ──

def test_interval_parse() -> None:
    assert F.parse_interval("[78000,82000]") == (78000.0, True, 82000.0, True)
    assert F.parse_interval("(82000,)") == (82000.0, False, None, False)
    assert F.parse_interval("(,78000)") == (None, False, 78000.0, False)
    for bad in ("78000-82000", "[,]", "[82000,78000]", "(1,1)"):
        with pytest.raises(F.ForecastError):
            F.parse_interval(bad)


@pytest.mark.parametrize("scen,needle", [
    ([("a", 0.5, "(,78000)"), ("b", 0.5, "(78000,)")], "شکاف"),          # 78000 بی‌صاحب
    ([("a", 0.5, "(,78000]"), ("b", 0.5, "[78000,)")], "هم‌پوشانی"),
    ([("a", 0.5, "(,78000)"), ("b", 0.4, "[78000,)")], "جمع احتمال"),
    ([("a", 0.5, "(,70000)"), ("b", 0.5, "[78000,)")], "شکاف"),
    ([("a", 1.0, "[1,)")], "منفی"),                                    # پایین بی‌پوشش
])
def test_partition_errors(scen, needle) -> None:
    f = dict(_real()["forecasts"][0], scenarios=[{"name": n, "p": p, "interval": i}
                                                  for n, p, i in scen])
    with pytest.raises(F.ForecastError, match=needle):
        F.validate({"version": 1, "forecasts": [f]})


@pytest.mark.parametrize("close,want", [(82000.0, "پایه"), (82000.01, "مثبت"),
                                        (78000.0, "پایه"), (77999.99, "منفی")])
def test_outcome_at_boundaries(close, want) -> None:
    assert F.outcome(_real()["forecasts"][0], close) == want


def test_brier() -> None:
    f = _real()["forecasts"][0]
    assert abs(F.brier(f, "پایه") - 0.38) < 1e-12                  # 0.2² + 0.5² + 0.3²
    assert abs(F.brier(f, "مثبت") - (0.8 ** 2 + 0.5 ** 2 + 0.3 ** 2)) < 1e-12


# ── بسته روزانه: همان منبع بسته هفتگی ──

def test_daily_close_okx_utc_bar() -> None:
    seen = []

    def get(url, params=None, timeout=None):
        seen.append((url, dict(params or {})))
        return _Resp({"code": "0", "data": [_okx(OPEN, 79500.5)]})
    d, why = P.daily_close_at("BTC", CLOSE, get=get, now=CLOSE + timedelta(hours=7))
    assert seen[0][1]["bar"] == "1Dutc" and "okx" in seen[0][0]
    assert d == {"close": 79500.5, "open_at": OPEN.isoformat(), "closed_at": CLOSE.isoformat(),
                 "venue": "okx"}


def test_daily_close_gate_fallback_and_none() -> None:
    def get(url, params=None, timeout=None):
        if "okx" in url:
            return _Resp({"code": "50001", "data": []})
        assert params["interval"] == "1d"
        return _Resp([[str(int(OPEN.timestamp())), "1", "80100.0", "1", "1", "1", "1"]])
    d, why = P.daily_close_at("BTC", CLOSE, get=get, now=CLOSE + timedelta(hours=7))
    assert d["venue"] == "gate" and d["close"] == 80100.0 and why

    def none(url, params=None, timeout=None):
        return _Resp({"code": "50001", "data": []}) if "okx" in url else _Resp([])
    d, why = P.daily_close_at("BTC", CLOSE, get=none, now=CLOSE + timedelta(hours=7))
    assert d is None and len(why) == 2


def test_daily_close_not_yet_closed_or_unconfirmed() -> None:
    def get(url, params=None, timeout=None):
        return _Resp({"code": "0", "data": [_okx(OPEN, 79500.5, conf="0")]})
    d, why = P.daily_close_at("BTC", CLOSE, get=get, now=CLOSE - timedelta(minutes=5))
    assert d is None and "بسته نشده" in why[0]
    d, why = P.daily_close_at("BTC", CLOSE, get=get, now=CLOSE + timedelta(hours=1))
    assert d is None                                              # اوکی‌اکس هنوز تأیید نکرده


def test_daily_close_anchor_must_be_midnight_utc() -> None:
    with pytest.raises(ValueError):
        P.daily_close_at("BTC", CLOSE + timedelta(hours=8), get=lambda *a, **k: None,
                         now=CLOSE + timedelta(days=1))


# ── نمره‌دهی ──

def test_score_only_after_deadline_and_once() -> None:
    doc = _real()
    got = []

    def fetch(sym, close_at, now=None):
        got.append(sym)
        return {"close": 80321.4, "open_at": OPEN.isoformat(), "closed_at": CLOSE.isoformat(),
                "venue": "okx"}, []
    assert F.score(doc, CLOSE - timedelta(hours=1), fetch) == (0, [])
    assert got == []
    n, fails = F.score(doc, CLOSE + timedelta(hours=7), fetch)
    assert n == 1 and fails == []
    r = doc["forecasts"][0]["result"]
    assert r["outcome"] == "پایه" and r["close"] == 80321.4 and r["venue"] == "okx"
    assert abs(r["brier"] - 0.38) < 1e-12 and r["p_outcome"] == 0.5
    assert F.score(doc, CLOSE + timedelta(days=2), fetch) == (0, []) and len(got) == 1


def test_score_failure_is_recorded_not_guessed() -> None:
    doc = _real()
    n, fails = F.score(doc, CLOSE + timedelta(hours=7),
                       lambda s, c, now=None: (None, ["okx: پاسخ نداد", "gate: پاسخ نداد"]))
    assert n == 0 and fails and doc["forecasts"][0].get("result") is None
    assert doc["forecasts"][0]["attempts"][-1]["why"]


def test_report_summary() -> None:
    doc = _real()
    F.score(doc, CLOSE + timedelta(hours=7),
            lambda s, c, now=None: ({"close": 83000.0, "open_at": OPEN.isoformat(),
                                     "closed_at": CLOSE.isoformat(), "venue": "okx"}, []))
    md = F.report(doc, CLOSE + timedelta(days=1))
    assert md.startswith("## دفتر پیش‌بینی")
    assert "مثبت" in md and "83000" in md and "0.980" in md               # 0.8² + 0.5² + 0.3²
    line = F.summary_line(doc)
    assert "۱ نمره‌خورده" in line and "0.980" in line


# ── فرمان ──

def test_cli_add_score_report(tmp_path, monkeypatch, capsys) -> None:
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"version": 1, "forecasts": []}), encoding="utf-8")
    args = ["--file", str(p), "add", "--id", "F-T-1", "--made-at", "2026-10-27",
            "--source", "آزمون", "--symbol", "eth", "--close-at", "2026-10-31T00:00:00+00:00",
            "--criterion", "بسته روزانه",
            "--scenario", "بالا|0.4|[2600,)", "--scenario", "پایین|0.6|(,2600)"]
    assert F.main(args) == 0
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["forecasts"][0]["symbol"] == "ETH"
    assert F.main(args) == 2                                               # شناسه تکراری
    assert "تکراری" in capsys.readouterr().err
    bad = args[:-4] + ["--scenario", "بالا|0.4|[2600,)", "--scenario", "پایین|0.5|(,2600)"]
    bad[bad.index("F-T-1")] = "F-T-2"
    assert F.main(bad) == 2
    monkeypatch.setattr(F, "_fetch", lambda: (lambda s, c, now=None: (
        {"close": 2500.0, "open_at": OPEN.isoformat(), "closed_at": CLOSE.isoformat(),
         "venue": "okx"}, [])))
    assert F.main(["--file", str(p), "score"], now=CLOSE + timedelta(hours=7)) == 0
    assert json.loads(p.read_text(encoding="utf-8"))["forecasts"][0]["result"]["outcome"] == "پایین"
    out, line = tmp_path / "r.md", tmp_path / "l.txt"
    assert F.main(["--file", str(p), "report", "--out", str(out), "--line", str(line)],
                  now=CLOSE + timedelta(days=1)) == 0
    assert "F-T-1" in out.read_text(encoding="utf-8")


def test_weekly_workflow_wires_forecasts() -> None:
    import conftest
    assert "forecasts.json" in conftest.DATA_FILES
    y = (ROOT / ".github" / "workflows" / "radar-weekly.yml").read_text(encoding="utf-8")
    assert "python radar_forecast.py score" in y
    assert 'python radar_forecast.py report --out "reports/forecasts-' in y
    assert "forecasts.json" in y[y.index("- name: کامیت"):]
    assert "/tmp/forecast_line.txt" in y[y.index("- name: اعلان تلگرام"):]
