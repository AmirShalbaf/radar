"""
مهر زمانی سطح ابطال — نشست ۳، ایستگاه آخر، بند ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

- invalidation_since در هر دو فایل و updated در watch.json نسخه ۲ مهر کامل
  وقت جهانی با منطقه زمانی‌اند. فقط تاریخ یعنی خطای بارگذاری.
- فقط بسته‌ای داوری می‌شود که زمان بسته‌شدنش اکیداً بعد از مهر است. سطحی که
  دقیقاً در 2026-09-28T00:00:00+00:00 ثبت شده، بسته همان لحظه را داوری
  نمی‌کند؛ سطحی که یک ثانیه قبل ثبت شده، داوری می‌کند.
- watch.json برای هر سکه مهر جدا دارد. updated فقط برای هشدار کهنگی است.
  اشکال پیشین: عوض‌کردن سطح یک سکه updated را برای همه جلو می‌برد و بسته
  هفتگی سکه‌های دیگر، که درست قبل از ویرایش بسته شده بود، داوری نمی‌شد.
- سطح و مهر در دو فایل تکرار شده‌اند. ناهمخوانی در پایشگر و سبد هر دو خطای
  بلند است.
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_positions as P
import radar_watch as W

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
MON = "2026-09-28T00:00:00+00:00"
STAMP = "2026-09-25T21:34:47+00:00"          # زمان واقعی ثبت 08ed69b


def _watch(sol_since=STAMP, eth_since=STAMP, updated="2026-09-25T21:32:45+00:00") -> dict:
    return {"version": 2, "updated": updated, "exit_fraction": 1.0,
            "positions": [
                {"symbol": "SOL", "invalidation": 96.71, "invalidation_since": sol_since,
                 "touches": 4, "warnings": []},
                {"symbol": "ETH", "invalidation": 2380.56, "invalidation_since": eth_since,
                 "touches": 7, "warnings": []}],
            "items": []}


def _h(sol_since=STAMP, eth_since=STAMP, sol_lvl=96.71) -> dict:
    return {"version": 2, "updated": "2026-09-25T05:15:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {"SOL": 6.0, "ETH": 0.4}},
            "cash": [], "ledger": [],
            "positions": [
                {"symbol": "SOL", "book": "position", "status": "open", "invalidation": sol_lvl,
                 "invalidation_since": sol_since,
                 "lots": [{"qty": 6.0, "account": "LBank", "entry": None}]},
                {"symbol": "ETH", "book": "position", "status": "open", "invalidation": 2380.56,
                 "invalidation_since": eth_since,
                 "lots": [{"qty": 0.4, "account": "LBank", "entry": None}]}]}


def _below(closed_at=MON):
    return lambda s: ({"close": {"SOL": 90.0, "ETH": 2000.0}[s], "closed_at": closed_at,
                       "venue": "okx"}, [])


def _judged(msgs, sym) -> bool:
    return any(sym in m and "ابطال هفتگی" in m for m in msgs)


# ═══════════════ قالب ═══════════════

def test_date_only_since_is_load_error() -> None:
    with pytest.raises(P.PositionsError, match="invalidation_since"):
        P.level_since({"symbol": "SOL", "invalidation_since": "2026-09-25"})
    assert P.level_since({"symbol": "SOL", "invalidation_since": STAMP}) == \
        datetime(2026, 9, 25, 21, 34, 47, tzinfo=UTC)


def test_watch_v2_needs_full_stamps() -> None:
    with pytest.raises(W.WatchError, match="updated"):
        W.validate_watch(_watch(updated="2026-09-25"))
    with pytest.raises(W.WatchError, match="invalidation_since"):
        W.validate_watch(_watch(sol_since="2026-09-25"))
    w = _watch()
    del w["positions"][0]["invalidation_since"]
    with pytest.raises(W.WatchError, match="invalidation_since"):
        W.validate_watch(w)
    W.validate_watch(_watch())


# ═══════════════ مرز داوری ═══════════════

@pytest.mark.parametrize("since, want", [
    ("2026-09-28T00:00:00+00:00", False),     # دقیقاً همان لحظه: داوری نمی‌شود
    ("2026-09-27T23:59:59+00:00", True),      # یک ثانیه قبل: داوری می‌شود
    ("2026-09-28T03:30:00+03:30", False),     # همان لحظه با منطقه زمانی دیگر
])
def test_judged_boundary(since, want) -> None:
    assert P.judged(MON, datetime.fromisoformat(since)) is want


def test_watcher_boundary() -> None:
    at = datetime(2026, 9, 28, 4, 40, tzinfo=UTC)
    exact = W.check_positions(_watch(sol_since=MON), _h(sol_since=MON), {}, at,
                              weekly=_below(), price=lambda s: None)
    assert not _judged(exact, "SOL")
    before = W.check_positions(_watch(sol_since="2026-09-27T23:59:59+00:00"),
                               _h(sol_since="2026-09-27T23:59:59+00:00"), {}, at,
                               weekly=_below(), price=lambda s: None)
    assert _judged(before, "SOL")


def _row(since):
    p = _h(sol_since=since)["positions"][0]
    return {"pos": p, "weekly": {"close": 90.0, "closed_at": MON, "venue": "okx"},
            "dust": False, "strikes": 0, "swap_edge": None, "score": 0.1}


def test_book_boundary() -> None:
    assert "زیر ابطال" not in B._verdict(_row(MON))
    assert "زیر ابطال" in B._verdict(_row("2026-09-27T23:59:59+00:00"))


# ═══════════════ مهر هر سکه، نه updated کل فایل ═══════════════

def test_editing_one_coin_does_not_hide_others_weekly_close() -> None:
    """
    ETH دوشنبه ۰۰:۰۰:۰۱ ویرایش شد، پس updated جلو رفت. بسته SOL که یک ثانیه
    پیش از ویرایش بسته شد باید داوری شود؛ بسته ETH نه — سطحش تازه است.
    """
    edit = "2026-09-28T00:00:01+00:00"
    w, h = _watch(eth_since=edit, updated=edit), _h(eth_since=edit)
    msgs = W.check_positions(w, h, {}, datetime(2026, 9, 28, 4, 40, tzinfo=UTC),
                             weekly=_below(), price=lambda s: None)
    assert _judged(msgs, "SOL")
    assert not _judged(msgs, "ETH")


# ═══════════════ ناهمخوانی دو فایل ═══════════════

def test_mismatches_found() -> None:
    assert P.level_mismatches(_h(), _watch()) == []
    assert any("SOL" in m for m in P.level_mismatches(_h(sol_lvl=90.0), _watch()))
    assert any("SOL" in m and "مهر" in m
               for m in P.level_mismatches(_h(sol_since="2026-09-26T00:00:00+00:00"), _watch()))
    w = _watch()
    w["positions"] = w["positions"][:1]
    assert any("ETH" in m and "watch.json" in m for m in P.level_mismatches(_h(), w))


def test_watcher_mismatch_is_loud_and_uses_conservative_level(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "watch.json").write_text(json.dumps(_watch()), encoding="utf-8")
    (tmp_path / "holdings.json").write_text(json.dumps(_h(sol_lvl=91.0), ensure_ascii=False),
                                            encoding="utf-8")
    (tmp_path / "radar_journal.json").write_text('{"version": 1, "trades": []}', encoding="utf-8")
    sent: list[str] = []
    monkeypatch.setattr(W, "notify", lambda m, quiet=False: sent.append(m))
    monkeypatch.setattr(W.P, "weekly_close", lambda s, now=None, get=None: (
        {"close": {"SOL": 95.0, "ETH": 3000.0}[s], "closed_at": MON, "venue": "okx"}, []))
    monkeypatch.setattr(W, "ticker", lambda s: None)
    assert W.main(["--once", "--watch", "watch.json", "--holdings", "holdings.json"]) == 2
    assert any("ناهمخوانی" in m and "SOL" in m for m in sent)
    # بسته 95 زیر سطح بالاتر (96.71) است، نه زیر 91 — محافظه‌کارانه‌تر داوری شد
    assert any("SOL" in m and "ابطال هفتگی" in m for m in sent)


def _frame(price: float, n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = [{"ts": open_ts - pd.Timedelta(days=n - 1 - i), "o": price, "h": price,
             "l": price, "c": price, "v": 1.0} for i in range(n)]
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "j.json").write_text('{"version": 1, "trades": []}', encoding="utf-8")
    monkeypatch.setattr(B, "candles", lambda *a, **k: _frame(100.0))
    monkeypatch.setattr(P, "weekly_close", lambda s, get=None, now=None: (None, ["آزمون"]))

    def go(h, watch=None):
        (tmp_path / "holdings.json").write_text(json.dumps(h, ensure_ascii=False),
                                                encoding="utf-8")
        if watch is not None:
            (tmp_path / "watch.json").write_text(json.dumps(watch, ensure_ascii=False),
                                                 encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--journal", "j.json",
                                          "--regime", "-0.2", "--out", "out.md"])
        rc = B.main()
        return rc, (tmp_path / "out.md").read_text(encoding="utf-8")
    return go


def test_book_mismatch_is_loud(book) -> None:
    rc, rep = book(_h(sol_lvl=91.0), _watch())
    assert rc == 2
    assert "ناهمخوانی" in rep.split("## ۱")[0]


def test_book_consistent_files_pass(book) -> None:
    rc, rep = book(_h(), _watch())
    assert rc == 0 and "ناهمخوانی" not in rep


def test_book_without_watch_file_says_so(book) -> None:
    rc, rep = book(_h())
    assert rc == 0
    assert "watch.json نیست" in rep


# ═══════════════ داده واقعی ═══════════════

def test_real_files_consistent_with_full_stamps() -> None:
    w = json.loads((ROOT / "watch.json").read_text(encoding="utf-8"))
    h = json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    W.validate_watch(w)
    assert P.level_mismatches(h, w) == []
    # مقدار مهر هر سکه را tests/test_approved_levels.py قفل می‌کند؛ اینجا قالب
    for it in w["positions"]:
        assert datetime.fromisoformat(it["invalidation_since"]).tzinfo is not None
    assert datetime.fromisoformat(w["updated"]).tzinfo is not None
