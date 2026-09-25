"""
آزمون هیسترزیس باند برای اندازه‌گیری دفتر معامله — نشست ۳، تصمیم ک۳۲.

قاعده کاربر (۲۵ سپتامبر ۲۰۲۶): پایین‌آمدن باند فوری، بالا رفتن فقط پس از سه
روز متوالی در باند تازه. دلیل: تصمیم دو دفتر فرض عقب‌انداختن آن را از بین
برد — دفتر معامله از همین نشست راه می‌افتد و امتیاز رژیم روی مرز است.

اجرا: بالا رفتن وقتی مجاز است که سه روز **تقویمی پیاپی** — امروز و دو روز
قبل — همه بالای باند مؤثر فعلی باشند؛ آن‌وقت به کمترین باند آن سه روز
می‌رود. روز جاافتاده در تاریخچه یعنی «پیاپی نیست» — بالا رفتن ممنوع.
فقط اندازه‌گیری دفتر معامله؛ هدف ذخیره دفتر موقعیت باند خام روز است.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_budget as BG
import radar_positions as P
import radar_regime as G

UTC = timezone.utc
D0 = date(2026, 9, 25)
M, S, E, K = "محتاط", "سازنده", "انبساطی", "انقباضی"


def _days(*bands, start=D0, skip=()) -> list:
    out, d = [], start
    for b in bands:
        while d in skip:
            d += timedelta(days=1)
        out.append((d, b))
        d += timedelta(days=1)
    return out


def test_band_order_and_lookup() -> None:
    assert BG.BAND_ORDER == ("بحرانی", "انقباضی", "محتاط", "سازنده", "انبساطی")
    assert BG.band_by_name(M) == BG.regime_band(-0.2)
    with pytest.raises(ValueError):
        BG.band_by_name("نامعلوم")


@pytest.mark.parametrize("bands, want", [
    ((M,), M),
    ((M, S), M),                 # یک روز بالا: هنوز نه
    ((M, S, S), M),              # سه روز پنجره هنوز شامل محتاط است
    ((M, S, S, S), S),           # سه روز متوالی در باند تازه
    ((S, S, S, M), M),           # پایین‌آمدن فوری
    ((M, S, E, S), S),           # سه روز بالای محتاط؛ کمترینشان سازنده
    ((M, S, S, K), K),           # پایین‌آمدن فوری، حتی دو پله
    ((M, S, S, S, M, S, S), M),  # پس از پایین‌آمدن، دوباره سه روز لازم است
])
def test_trade_band_sequences(bands, want) -> None:
    assert BG.trade_band(_days(*bands)) == want


def test_gap_day_blocks_going_up() -> None:
    """روز جاافتاده یعنی پیاپی نیست — بالا رفتن ممنوع."""
    days = _days(M, S, S, S, skip={D0 + timedelta(days=2)})
    assert BG.trade_band(days) == M


def test_empty_is_error() -> None:
    with pytest.raises(ValueError):
        BG.trade_band([])


# ═══════════════ radar_regime — ثبت در regime.json و تاریخچه ═══════════════

def test_regime_trade_band_from_history() -> None:
    now = datetime(2026, 9, 28, 6, 30, tzinfo=UTC)
    hist = {"version": 1, "days": {"2026-09-25": {"band": M}, "2026-09-26": {"band": S},
                                   "2026-09-27": {"band": S}}}
    assert G.trade_band_for(hist, S, now) == S
    hist["days"]["2026-09-27"]["band"] = M
    assert G.trade_band_for(hist, S, now) == M


def _inputs(score: float) -> dict:
    return {k: G.Input(key=k, column=c, label=l, weight=G.weights()[k], score=score)
            for k, (c, l) in G.INPUTS.items()}


def test_doc_and_history_carry_trade_band() -> None:
    now = datetime(2026, 9, 26, 6, 30, tzinfo=UTC)
    inp = _inputs(0.2)
    res = G.aggregate(inp)                                  # سازنده
    doc = G.build_doc(res, inp, now, trade_band=M)
    assert doc["trade_band"]["name"] == M
    assert doc["trade_band"] == {**BG.band_by_name(M), "name": M}
    h = G.update_history({"version": 1, "days": {}}, res, inp, now, trade_band=M)
    assert h["days"]["2026-09-26"]["trade_band"] == M
    assert h["days"]["2026-09-26"]["band"] == S


# ═══════════════ radar_book — دفتر معامله با باند مؤثر ═══════════════

def test_load_regime_reads_trade_band(tmp_path) -> None:
    now = datetime.now(UTC)
    p = tmp_path / "regime.json"
    p.write_text(json.dumps({"score": 0.2, "generated_at": now.isoformat(),
                             "trade_band": {"name": M}}), encoding="utf-8")
    r = B.load_regime(p)
    assert r.score == 0.2 and r.trade_band["name"] == M
    assert r.trade_band["cap"] == BG.band_by_name(M)["cap"]    # عدد از منبع واحد


def test_load_regime_bad_trade_band_warns(tmp_path) -> None:
    now = datetime.now(UTC)
    p = tmp_path / "regime.json"
    p.write_text(json.dumps({"score": 0.2, "generated_at": now.isoformat(),
                             "trade_band": {"name": "نامعلوم"}}), encoding="utf-8")
    r = B.load_regime(p)
    assert r.trade_band is None
    assert any("trade_band" in w and "نامعتبر" in w for w in r.warnings)


def _frame(price: float, n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = [{"ts": open_ts - pd.Timedelta(days=n - 1 - i), "o": price, "h": price,
             "l": price, "c": price, "v": 1.0} for i in range(n)]
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


def test_book_trade_cap_uses_trade_band(tmp_path, monkeypatch) -> None:
    """امتیاز سازنده (سقف ۶٪) ولی باند مؤثر محتاط: سقف دفتر معامله ۴٪."""
    monkeypatch.chdir(tmp_path)
    now = datetime.now(UTC)
    (tmp_path / "regime.json").write_text(json.dumps({
        "score": 0.2, "generated_at": now.isoformat(), "trade_band": {"name": M}}),
        encoding="utf-8")
    h = {"version": 2, "updated": now.isoformat(), "source": "آزمون",
         "frozen": {"date": "2026-09-25", "members": {"SOL": 10.0}},
         "cash": [{"asset": "USDT", "qty": 0.0, "account": "A"}], "ledger": [],
         "positions": [{"symbol": "SOL", "book": "position", "status": "open",
                        "lots": [{"qty": 10.0, "account": "A", "entry": None}],
                        "invalidation": None}]}
    (tmp_path / "holdings.json").write_text(json.dumps(h, ensure_ascii=False),
                                            encoding="utf-8")
    jp = tmp_path / "j.json"
    jp.write_text(json.dumps({"version": 1, "trades": []}), encoding="utf-8")
    monkeypatch.setattr(B, "candles", lambda *a, **k: _frame(100.0))
    monkeypatch.setattr(sys, "argv", ["radar_book.py", "--journal", str(jp),
                                      "--out", "out.md"])
    assert B.main() == 0
    rep = (tmp_path / "out.md").read_text(encoding="utf-8")
    row = next(l for l in rep.splitlines() if l.startswith("| **ریسک مؤثر دفتر معامله"))
    assert "40 دلار" in row                     # ۴٪ × 1000، نه ۶٪
    assert "هیسترزیس" in rep and M in rep.split("## ۳")[1]
