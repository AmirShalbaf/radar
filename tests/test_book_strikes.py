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
        "version": 2, "updated": datetime.now(UTC).isoformat(), "source": "آزمون",
        "frozen": {"date": "2026-09-25", "members": {"AAA": 2.0}},
        "cash": [{"asset": "USDT", "qty": 100.0, "account": "A"}], "ledger": [],
        "positions": [{"symbol": "AAA", "book": "position", "status": "open",
                       "lots": [{"qty": 2.0, "account": "A", "entry": None}],
                       "invalidation": None}]}),
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
    st["score_basis"] = B.SCORE_BASIS        # دور عادی، نه خط پایه
    saved, _ = run_book(st, no_data=("AAA",))
    assert saved["reviews"]["AAA"] == st["reviews"]["AAA"]


# ═══════════════ مبنای امتیاز — score_basis ═══════════════
#
# از کامیت 5526c40 امتیاز سبد با کندل بسته حساب می‌شود و با امتیازهای
# پیشین مقایسه‌پذیر نیست. قانون سه‌ضربه هر امتیاز را با قبلی می‌سنجد،
# پس نخستین دور پس از پوش ضربه ساختگی می‌گرفت یا از دست می‌داد.
# رفع: میدان score_basis. اگر مبنا فرق داشت، آن دور فقط خط پایه تازه
# ثبت می‌شود و هیچ ضربه‌ای شمرده نمی‌شود. تاریخچه مبنای قدیم بایگانی
# می‌شود، نه اینکه کنار تازه بماند — وگرنه زنجیره کاهش فردا از مرز
# دو مبنا رد می‌شود.


def test_begin_round_without_basis_resets_and_archives() -> None:
    st = _state(2.0, 1.5)
    old = st["reviews"]
    assert B.begin_round(st) is True
    assert st["reviews"] == {}
    assert st["score_basis"] == B.SCORE_BASIS
    assert st["archive"][-1]["basis"] is None
    assert st["archive"][-1]["reviews"] == old


def test_begin_round_other_basis_is_archived_by_name() -> None:
    st = _state(2.0, 1.5)
    st["score_basis"] = "old-v0"
    assert B.begin_round(st) is True
    assert st["archive"][-1]["basis"] == "old-v0"


def test_begin_round_same_basis_touches_nothing() -> None:
    st = _state(2.0, 1.5)
    st["score_basis"] = B.SCORE_BASIS
    before = json.loads(json.dumps(st))
    assert B.begin_round(st) is False
    assert st == before


def test_begin_round_fresh_state_archives_nothing() -> None:
    st = {"reviews": {}, "swaps": []}
    assert B.begin_round(st) is True
    assert "archive" not in st


def test_main_basis_change_counts_no_strike(run_book) -> None:
    """
    تاریخچه ۲.۰ ← ۱.۵ و امتیاز امروز حدود ۱.۱: بدون رفع دو ضربه
    ساختگی می‌گرفت و حکم «آماده‌سازی کاهش». با رفع: خط پایه تازه.
    """
    st = _state(2.0, 1.5)
    saved, rep = run_book(st)
    assert saved["score_basis"] == B.SCORE_BASIS
    assert len(saved["reviews"]["AAA"]) == 1
    assert saved["archive"][-1]["reviews"] == st["reviews"]
    assert _strike_cell(rep, "AAA") == "0"
    assert "خط پایه تازه" in rep


def _strike_cell(rep: str, sym: str) -> str:
    """خانه ستون «ض» سطر یک نماد در جدول دفتر موقعیت."""
    book = rep.split("## ۲")[1].split("## ۳")[0].splitlines()
    head = [c.strip() for c in next(l for l in book if l.startswith("| نماد")).split("|")]
    row = [c.strip() for c in next(l for l in book if l.startswith(f"| {sym} ")).split("|")]
    return row[next(i for i, c in enumerate(head) if c.startswith("ض"))]


def test_main_same_basis_still_counts(run_book) -> None:
    """
    قفل: دور عادی با همان مبنا مثل قبل ضربه می‌شمارد. از ۶ اکتبر ضربه فقط
    اطلاعی است — شمار در ستون «ض» می‌آید، حکمی نمی‌سازد؛ ک۸۵.
    """
    st = _state(2.0, 1.5)
    st["score_basis"] = B.SCORE_BASIS
    saved, rep = run_book(st)
    assert len(saved["reviews"]["AAA"]) == 3
    assert _strike_cell(rep, "AAA") == "2"
    assert "آماده‌سازی کاهش" not in rep
    assert "خط پایه تازه" not in rep


# ═══════════════ مبنای ۲ — لنگر وقت جهانی، نشست ۳ب ═══════════════
#
# کندل روزانه سبد از لنگر هنگ‌کنگ (1D، بسته 16:00 UTC) به وقت جهانی رفت.
# میانگین‌ها، RSI و قدرت نسبی ۸ ساعت جابه‌جا شدند؛ پیش‌نمایش ایستگاه ۱:
# قدرت نسبی ۳۰ روزه SOL از +7.39٪ به +5.85٪. امتیاز دو لنگر مقایسه‌پذیر
# نیست. ضربه‌های مبنای ۱ در ۲۶ سپتامبر: SOL، ETH و BNB هر کدام یکی.

V1 = "closed-candle-v1"


def test_basis_changed_for_utc_anchor() -> None:
    assert B.SCORE_BASIS != V1
    assert "utc" in B.SCORE_BASIS


def test_v1_history_with_strike_becomes_baseline() -> None:
    """الگوی book_state.json ۲۶ سپتامبر: SOL 1.8 ← 1.8 ← 1.45، یک ضربه."""
    st = {"reviews": {"SOL": [{"date": _day(-3), "score": 1.8},
                              {"date": _day(-2), "score": 1.8},
                              {"date": _day(-1), "score": 1.45}]},
          "swaps": [], "score_basis": V1}
    old = json.loads(json.dumps(st["reviews"]))
    assert B.begin_round(st) is True
    assert st["reviews"] == {}
    assert st["archive"][-1]["basis"] == V1
    assert st["archive"][-1]["reviews"] == old
    strikes, _ = B.update_strikes(st, "SOL", 1.0)          # کاهش، ولی خط پایه
    assert strikes == 0


def test_baseline_message_says_why(run_book) -> None:
    st = _state(2.0, 1.5)
    st["score_basis"] = V1
    _, rep = run_book(st)
    assert "خط پایه تازه" in rep
    assert B.SCORE_BASIS_WHY in rep and "لنگر" in B.SCORE_BASIS_WHY
