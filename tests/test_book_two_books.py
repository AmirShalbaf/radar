"""
آزمون گزارش دو دفتر در radar_book.py — نشست ۳ نقشه رادار ۷، مورد ۱-۴.

تصمیم کاربر، ۲۵ سپتامبر ۲۰۲۶: سقف ریسک رژیم برای معامله کوتاه با حد ضرر
طراحی شده؛ اعمال لفظی آن روی سبد بلندمدت یعنی فروش حدود ۹۰٪. پس:
- دفتر موقعیت با سقف رژیم مقایسه نمی‌شود. ریسکش تا ابطال فقط گزارش می‌شود.
  هدف ذخیره رژیم روی کل سرمایه است. ابطال با بسته هفتگی وقت جهانی.
- دفتر معامله: سقف = درصد سقف × کل سرمایه، حداکثر پوزیشن هم‌جهت، و ضریب
  همبستگی. معامله فرضی جدا و بیرون از سرمایه.
ارزش از قیمت زنده × مقدار؛ قالب ۱ و نقض ناوردا خطای صریح.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_positions as P

UTC = timezone.utc


def _frame(price: float, n: int = 700) -> pd.DataFrame:
    """قاب روزانه به قالب سبد؛ سطر آخر کندل باز با قیمت زنده price."""
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = []
    for i in range(n):
        c = price * (0.7 + 0.3 * i / (n - 1))
        rows.append({"ts": open_ts - pd.Timedelta(days=n - 1 - i),
                     "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 10.0})
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


def _pos(sym, qty, entry=None, inv=None, book="position", **extra) -> dict:
    d = {"symbol": sym, "book": book, "status": "open",
         "lots": [{"qty": qty, "account": "A", "entry": entry}], "invalidation": inv}
    d.update(extra)
    return d


def _holdings(positions, cash=100.0, members=None, ledger=None) -> dict:
    mem = members if members is not None else {
        p["symbol"]: sum(l["qty"] for l in p["lots"])
        for p in positions if p["book"] == "position"}
    return {"version": 2, "updated": datetime.now(UTC).isoformat(), "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": mem},
            "cash": [{"asset": "USDT", "qty": cash, "account": "A"}],
            "positions": positions, "ledger": ledger or []}


PRICES = {"BTC": 80000.0, "SOL": 100.0, "ETH": 2000.0, "TRX": 0.3, "XYZ": 1.0,
          "A0": 1.0, "A1": 1.0, "A2": 1.0}


@pytest.fixture
def run(tmp_path, monkeypatch):
    """main سبد در پوشه موقت، بدون شبکه. weekly: نماد ← بسته هفتگی یا None."""
    monkeypatch.chdir(tmp_path)
    jp = tmp_path / "journal.json"
    jp.write_text(json.dumps({"version": 1, "trades": []}), encoding="utf-8")
    monkeypatch.setattr(B, "candles", lambda sym, *a, **k: _frame(PRICES[sym]))
    calls: list[str] = []

    def go(h: dict, weekly: dict | None = None, journal: list | None = None,
           regime: str = "-0.2") -> tuple[int, str]:
        (tmp_path / "holdings.json").write_text(json.dumps(h, ensure_ascii=False),
                                                encoding="utf-8")
        if journal is not None:
            jp.write_text(json.dumps({"version": 1, "trades": journal},
                                     ensure_ascii=False), encoding="utf-8")

        def wc(sym, get=None, now=None):
            calls.append(sym)
            v = (weekly or {}).get(sym)
            return (None, ["آزمون: داده نیست"]) if v is None else (
                {"close": v, "closed_at": "2026-09-21T00:00:00+00:00", "venue": "okx"}, [])
        monkeypatch.setattr(P, "weekly_close", wc)
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--journal", str(jp),
                                          "--regime", regime, "--out", "out.md"])
        rc = B.main()
        out = tmp_path / "out.md"
        return rc, (out.read_text(encoding="utf-8") if out.exists() else "")
    go.calls = calls
    return go


def _row(rep: str, head: str) -> str:
    return next(l for l in rep.splitlines() if l.startswith(f"| {head}"))


# ═══════════════ بارگذاری ═══════════════

def test_v1_holdings_fail_loudly(run, tmp_path, capsys) -> None:
    rc, _ = run({"balance_total": 2070, "stable_usd": 129,
                 "positions": [{"symbol": "SOL", "size_usd": 443}]})
    assert rc != 0
    assert "قالب قدیمی — مهاجرت لازم" in capsys.readouterr().err


def test_invariant_violation_fails_loudly(run, capsys) -> None:
    h = _holdings([_pos("SOL", 6.0)], members={"SOL": 5.0})
    rc, _ = run(h)
    assert rc != 0
    assert "ثبت‌نشده" in capsys.readouterr().err


# ═══════════════ سرمایه و ذخیره ═══════════════

def test_capital_is_live_value_plus_stable(run) -> None:
    rc, rep = run(_holdings([_pos("SOL", 6.0), _pos("ETH", 0.5)], cash=100.0))
    assert rc == 0
    assert "1,700" in _row(rep, "کل سرمایه")          # 600 + 1000 + 100


def test_stable_target_on_total_capital(run) -> None:
    """محتاط: هدف ۲۵٪ × 1700 = 425؛ کسری 425 − 100 = 325."""
    rc, rep = run(_holdings([_pos("SOL", 6.0), _pos("ETH", 0.5)], cash=100.0))
    assert "کسری: 325 دلار" in rep


def test_position_book_not_compared_with_regime_cap(run) -> None:
    """ریسک دفتر موقعیت فقط گزارش می‌شود؛ هشدار ⛔ حرارت برای آن نیست."""
    rc, rep = run(_holdings([_pos("SOL", 6.0, inv=10.0), _pos("ETH", 0.5, inv=100.0)]))
    assert "فقط گزارش" in _row(rep, "ریسک دفتر موقعیت تا ابطال")
    assert "⛔ **حرارت سبد" not in rep
    assert "دفتر معامله خالی است" in rep


# ═══════════════ دفتر موقعیت — ابطال هفتگی ═══════════════

def test_weekly_close_below_invalidation_is_exit(run) -> None:
    rc, rep = run(_holdings([_pos("SOL", 6.0, inv=95.0)]), weekly={"SOL": 90.0})
    assert "بسته هفتگی زیر ابطال" in _row(rep, "SOL")


def test_weekly_close_above_invalidation_holds(run) -> None:
    """قیمت زنده زیر ابطال، ولی بسته هفتگی بالای آن: هنوز ابطال نیست."""
    rc, rep = run(_holdings([_pos("SOL", 6.0, inv=95.0)]), weekly={"SOL": 99.0})
    assert "زیر ابطال" not in _row(rep, "SOL")


def test_weekly_close_missing_says_no_data(run) -> None:
    rc, rep = run(_holdings([_pos("SOL", 6.0, inv=95.0)]), weekly={})
    assert "داده ندارم" in _row(rep, "SOL")


def test_weekly_close_comes_from_positions_module(run) -> None:
    """یک منبع برای لنگر وقت جهانی: radar_positions.weekly_close."""
    run(_holdings([_pos("SOL", 6.0, inv=95.0), _pos("ETH", 0.5)]), weekly={"SOL": 99.0})
    assert run.calls == ["SOL"]           # فقط پوزیشنی که ابطال دارد


def test_pnl_only_with_known_entry(run) -> None:
    rc, rep = run(_holdings([_pos("SOL", 6.0, entry=80.0), _pos("ETH", 0.5)]))
    assert "+25.0٪" in _row(rep, "SOL")
    assert "+" not in _row(rep, "ETH").split("|")[5]      # ستون سود و زیان خالی


def test_dust_not_in_sell_order_or_missing_invalidation(run) -> None:
    rc, rep = run(_holdings([_pos("SOL", 6.0), _pos("TRX", 0.67)]))
    assert "ناچیز" in _row(rep, "TRX")
    sell = rep.split("## ۵")[1].split("## ۶")[0]
    assert "TRX" not in sell
    missing = next(l for l in rep.splitlines() if "سطح ابطال ندارند" in l)
    assert "TRX" not in missing and "SOL" in missing


def test_reentry_watch_for_exited_position(run) -> None:
    ledger = [{"at": datetime.now(UTC).isoformat(), "action": "exit", "symbol": "SOL",
               "delta": -6.0, "price": 90.0, "level": 95.0, "reason": "invalidation"}]
    h = _holdings([{"symbol": "SOL", "book": "position", "status": "exited",
                    "lots": [], "invalidation": 95.0}, _pos("ETH", 0.5)],
                  members={"SOL": 6.0, "ETH": 0.5}, ledger=ledger)
    rc, rep = run(h, weekly={"SOL": 97.0})
    assert rc == 0
    line = next(l for l in rep.splitlines() if l.startswith("| SOL") and "95" in l)
    assert "ورود دوباره مجاز" in line and "6" in line


# ═══════════════ دفتر معامله ═══════════════

def _trade(sym, did, qty=100.0, entry=1.0, stop=0.5, paper=False) -> dict:
    return _pos(sym, qty, entry=entry, book="trade", decision_id=did,
                setup_name="الف۱", paper=paper, side="long", stop=stop,
                opened=datetime.now(UTC).isoformat())


def _jt(did, paper=False) -> dict:
    return {"id": 1, "symbol": "X", "decision_id": did, "setup_name": "الف۱",
            "book": "trade", "paper": paper, "status": "open"}


def test_trade_book_over_cap_blocks_new_entries(run) -> None:
    """ریسک 100×0.5 = 50؛ سقف ۴٪ × (600+100+100) = 32 ← ⛔."""
    h = _holdings([_pos("SOL", 6.0), _trade("XYZ", "D-1")])
    rc, rep = run(h, journal=[_jt("D-1")])
    sec = rep.split("## ۳")[1].split("## ۴")[0]
    assert "⛔" in sec and "ورود تازه" in sec


def test_paper_trade_separate_and_not_capital(run) -> None:
    h = _holdings([_pos("SOL", 6.0), _trade("XYZ", "D-1", paper=True)])
    rc, rep = run(h, journal=[_jt("D-1", paper=True)])
    assert "700" in _row(rep, "کل سرمایه")                 # فرضی بیرون از سرمایه
    sec = rep.split("## ۳")[1].split("## ۴")[0]
    assert "فرضی" in sec and "⛔" not in sec


def test_correlation_and_maxpos_shown(run) -> None:
    trades = [_trade(f"A{i}", f"D-{i}", qty=1.0, entry=1.0, stop=0.9) for i in range(3)]
    h = _holdings([_pos("SOL", 6.0)] + trades)
    rc, rep = run(h, journal=[_jt(f"D-{i}") for i in range(3)])
    sec = rep.split("## ۳")[1].split("## ۴")[0]
    assert "1.50" in sec and "3 از 3" in sec


def test_reentry_watch_for_partial_invalidation_exit(run) -> None:
    """خروج جزئی با ابطال: پوزیشن باز می‌ماند ولی سهمیه ورود دوباره دارد."""
    ledger = [{"at": datetime.now(UTC).isoformat(), "action": "trim", "symbol": "SOL",
               "delta": -3.0, "price": 90.0, "level": 95.0, "reason": "invalidation"}]
    h = _holdings([_pos("SOL", 3.0, inv=95.0), _pos("ETH", 0.5)],
                  members={"SOL": 6.0, "ETH": 0.5}, ledger=ledger)
    rc, rep = run(h, weekly={"SOL": 97.0})
    assert rc == 0
    line = next(l for l in rep.splitlines() if l.startswith("| SOL") and "95" in l
                and "ورود دوباره" in l)
    assert "3" in line


def test_week_closed_before_level_set_is_not_judged(run) -> None:
    """
    یافته پیش‌نمایش ۲۵ سپتامبر: بسته هفتگی ONDO تا ۲۱ سپتامبر زیر سطحی بود که
    ۲۵ سپتامبر گذاشته شد. سبد نباید گذشته‌نگر حکم خروج بدهد.
    """
    p = _pos("SOL", 6.0, inv=95.0, invalidation_since="2026-09-25")
    rc, rep = run(_holdings([p]), weekly={"SOL": 90.0})       # بسته 2026-09-21
    row = _row(rep, "SOL")
    assert "زیر ابطال" not in row and "سطح تازه" in row
    assert "خروج کامل" not in rep.split("## ۶")[1]
