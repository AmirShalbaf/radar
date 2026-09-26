"""
مرز لنگر کندل در regime_history.json — نشست ۳ب، بند ۳.

دو ورودی رژیم از کندل می‌آیند: میانگین پنجاه‌هفته و جفت اتر به بیت‌کوین. تا
نشست ۳ب لنگرشان هنگ‌کنگ بود؛ از نخستین اجرای وقت جهانی، جهانی. پیش‌نمایش
ایستگاه ۱: تغییر ۳۰ روزه اتر به بیت‌کوین فقط با ۸ ساعت جابه‌جایی لنگر از
+1.976٪ به +0.978٪ رفت و امتیاز نهایی از -0.055 به -0.084. سنجش اعتبار آینده
رژیم (ک۳۵) باید این مرز را ماشین‌خوان ببیند.

قرارداد:
- هر روز تازه میدان anchor دارد.
- نخستین اجرای وقت جهانی روی تاریخچه‌ای که روز بی‌لنگر دارد، یک رکورد
  anchor_boundary در سطح بالا می‌نویسد: تاریخ، از، به، دلیل، ورودی‌ها و قاعده
  خواندن روزهای قدیم. خود کد می‌نویسد، نه دست — پوش پس از دوشنبه است و ربات
  تا آن موقع روزهای بیشتری با لنگر هنگ‌کنگ می‌نویسد.
- روزهای موجود بازنویسی نمی‌شوند؛ مرز دوباره نوشته نمی‌شود.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_regime as G

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _inp(score: float = 0.1) -> dict:
    return {k: G.Input(key=k, column=c, label=lb, weight=G.weights()[k], score=score)
            for k, (c, lb) in G.INPUTS.items()}


def _legacy() -> dict:
    """دو روز پیش از مرز، بدون میدان anchor — شکل واقعی ۲۵ و ۲۶ سپتامبر."""
    rec = {"generated_at": "2026-09-25T12:07:10+00:00", "raw": -0.02, "norm": -0.023,
           "score": -0.023, "band": "محتاط", "coverage": 0.8, "inputs": {"ethbtc": 0.35}}
    return {"version": 1, "days": {"2026-09-25": dict(rec),
                                   "2026-09-26": dict(rec, score=-0.055)}}


def _update(h: dict, now: datetime = NOW) -> dict:
    inp = _inp()
    return G.update_history(h, G.aggregate(inp), inp, now)


def test_new_day_carries_anchor() -> None:
    h = _update(_legacy())
    assert h["days"]["2026-09-29"]["anchor"] == G.CANDLE_ANCHOR == "utc"


def test_first_utc_run_writes_boundary() -> None:
    h = _update(_legacy())
    b = h["anchor_boundary"]
    assert b["date"] == "2026-09-29"
    assert b["from"] == "hk" and b["to"] == "utc"
    assert set(b["inputs"]) == {"ma50w", "ethbtc"}
    assert "لنگر" in b["reason"] and b["rule"]


def test_existing_days_untouched() -> None:
    old = _legacy()
    before = copy.deepcopy(old["days"])
    h = _update(old)
    for d, rec in before.items():
        assert h["days"][d] == rec
    assert old["days"] == before                  # ورودی هم دست نخورد


def test_boundary_written_once() -> None:
    h1 = _update(_legacy())
    h2 = _update(h1, datetime(2026, 9, 30, 12, tzinfo=UTC))
    assert h2["anchor_boundary"] == h1["anchor_boundary"]
    assert h2["days"]["2026-09-29"] == h1["days"]["2026-09-29"]


def test_fresh_history_needs_no_boundary() -> None:
    h = _update({"version": 1, "days": {}})
    assert "anchor_boundary" not in h
    assert h["days"]["2026-09-29"]["anchor"] == "utc"


def test_real_history_days_preserved() -> None:
    """روی نسخه واقعی فایل — فقط خواندن: هر روز موجود بی‌تغییر، مرز ثبت یا حفظ."""
    real = G.load_history(ROOT / "regime_history.json")
    before = copy.deepcopy(real)
    h = _update(real, datetime(2031, 1, 6, 12, tzinfo=UTC))
    for d, rec in before["days"].items():
        assert h["days"][d] == rec
    if "anchor_boundary" in before:
        assert h["anchor_boundary"] == before["anchor_boundary"]
    elif any("anchor" not in r for r in before["days"].values()):
        assert h["anchor_boundary"]["date"] == "2031-01-06"


def test_bad_boundary_is_an_error(tmp_path) -> None:
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"version": 1, "days": {}, "anchor_boundary": "دیروز"}),
                 encoding="utf-8")
    with pytest.raises(G.RegimeError):
        G.load_history(p)


def test_main_writes_boundary_and_report_line(tmp_path, monkeypatch) -> None:
    hp = tmp_path / "hist.json"
    hp.write_text(json.dumps(_legacy(), ensure_ascii=False), encoding="utf-8")
    inp = _inp()
    monkeypatch.setattr(G, "gather", lambda order: {})
    monkeypatch.setattr(G, "measure", lambda src, history, now: inp)
    monkeypatch.setattr(G.P, "sma_weekly", lambda *a, **k: (None, ["آزمون"]))
    rep = tmp_path / "r.md"
    assert G.main(["--json", str(tmp_path / "j.json"), "--history", str(hp),
                   "--report", str(rep)]) == 0
    h = json.loads(hp.read_text(encoding="utf-8"))
    assert h["anchor_boundary"]["to"] == "utc"
    doc = json.loads((tmp_path / "j.json").read_text(encoding="utf-8"))
    assert doc["candle_anchor"] == "utc"
    assert h["anchor_boundary"]["date"] in rep.read_text(encoding="utf-8")
