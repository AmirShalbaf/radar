"""
آزمون شمارش ضربه در radar_book.py — نشست ۱ نقشه رادار ۷.

بازطراحی منطق ضربه مال نشست ۱۲ است. این آزمون‌ها فقط جلوی خرابی‌ای را
می‌گیرند که خود نشست ۱ ساخت.

امتیاز خالی: main به‌جای امتیاز خالی عدد صفر به update_strikes می‌داد.
صفر در تاریخچه می‌نشست و اگر امتیاز قبلی مثبت بود، ضربه ساختگی می‌ساخت —
نقض قانون سوگیری صفر. نشست ۱ با نگهبان قیمت پوچ و نگهبان ۶۰ کندل بسته
امتیاز خالی را بیشتر کرد، پس این خطر را هم بالا برد.
رفع کمینه: امتیاز خالی یعنی تاریخچه آن نماد در این دور دست نخورد —
نه ورودی تازه، نه بازنویسی ورودی امروز. شمارش از همان تاریخچه
دست‌نخورده می‌آید: ضربه تازه اضافه نمی‌شود، ضربه‌های قبلی هم صفر نمی‌شوند.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B

UTC = timezone.utc


def _day(offset: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset)).strftime("%Y-%m-%d")


def _state(*scores: float) -> dict:
    """تاریخچه‌ای که آخرین ورودی‌اش دیروز است."""
    n = len(scores)
    hist = [{"date": _day(i - n), "score": s} for i, s in enumerate(scores)]
    return {"reviews": {"AAA": hist}, "swaps": []}


# ═══════════════ امتیاز خالی ═══════════════

def test_empty_score_leaves_history_untouched() -> None:
    st = _state(0.9, 0.5)
    before = [dict(h) for h in st["reviews"]["AAA"]]
    B.update_strikes(st, "AAA", None)
    assert st["reviews"]["AAA"] == before


def test_empty_score_adds_no_strike_and_keeps_old_ones() -> None:
    """۰.۹ ← ۰.۵ یک ضربه است. دور بی‌داده نه اضافه می‌کند، نه صفر."""
    strikes, _ = B.update_strikes(_state(0.9, 0.5), "AAA", None)
    assert strikes == 1


def test_empty_score_would_have_faked_a_strike() -> None:
    """ثبت خود باگ: صفر به‌جای خالی، از ۰.۵ ضربه دوم می‌ساخت."""
    strikes, _ = B.update_strikes(_state(0.9, 0.5), "AAA", 0.0)
    assert strikes == 2


def test_empty_score_keeps_todays_earlier_entry() -> None:
    """اجرای دوم امروز بی‌داده، امتیاز اجرای اول امروز را پاک نکند."""
    st = _state(0.9)
    st["reviews"]["AAA"].append({"date": _day(0), "score": 0.7})
    B.update_strikes(st, "AAA", None)
    assert st["reviews"]["AAA"][-1] == {"date": _day(0), "score": 0.7}


def test_empty_score_without_history() -> None:
    st = {"reviews": {}, "swaps": []}
    strikes, hist = B.update_strikes(st, "NEW", None)
    assert strikes == 0
    assert hist == []


def test_real_score_still_counts() -> None:
    """قفل، نه قرمز: امتیاز واقعی مثل قبل شمرده می‌شود."""
    strikes, hist = B.update_strikes(_state(0.9, 0.5), "AAA", 0.3)
    assert strikes == 2
    assert hist[-1] == {"date": _day(0), "score": 0.3}


# ═══════════════ main بدون شبکه ═══════════════

def _book_frame(n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = [{"ts": open_ts - pd.Timedelta(days=n - 1 - i), "o": 100.0 + i,
             "h": 102.0 + i, "l": 98.0 + i, "c": 100.0 + i, "v": 10.0}
            for i in range(n)]
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


@pytest.fixture
def run_book(tmp_path, monkeypatch):
    """
    main را در پوشه موقت و بدون شبکه اجرا می‌کند. no_data نمادهایی است
    که واکشی‌شان خالی برمی‌گردد. خروجی: وضعیت ذخیره‌شده و متن گزارش.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "holdings.json").write_text(json.dumps({
        "balance_total": 1000, "stable_usd": 100,
        "positions": [{"symbol": "AAA", "size_usd": 200, "entry": 0,
                       "invalidation": None, "side": "long", "spot": True}]}),
        encoding="utf-8")

    def run(state: dict | None, no_data: tuple = ()) -> tuple[dict, str]:
        if state is not None:
            (tmp_path / B.STATE_FILE).write_text(json.dumps(state),
                                                 encoding="utf-8")
        monkeypatch.setattr(B, "candles", lambda sym, *a, **k:
                            None if sym in no_data else _book_frame())
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--regime", "-0.6",
                                          "--out", "out.md"])
        assert B.main() == 0
        saved = json.loads((tmp_path / B.STATE_FILE).read_text(encoding="utf-8"))
        return saved, (tmp_path / "out.md").read_text(encoding="utf-8")
    return run


def test_main_empty_score_leaves_history_untouched(run_book) -> None:
    """محل فراخوانی: main امتیاز خالی را خالی بفرستد، نه صفر."""
    st = _state(0.9, 0.5)
    saved, _ = run_book(st, no_data=("AAA",))
    assert saved["reviews"]["AAA"] == st["reviews"]["AAA"]
