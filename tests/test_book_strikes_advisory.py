"""
ضربه فقط اطلاعی — کار صفر نشست ۱۰، تصمیم کاربر ۶ اکتبر ۲۰۲۶.

قانون سه‌ضربه روی کاهش امتیاز روزانه کار می‌کند و موتور امتیاز در ۲۲ اوت
با radar_validate رد شد — ضریب اطلاعات نزدیک صفر، STATE.md بخش ۴.۲. سه
کاهش پیاپی در عددی که رتبه‌بندی نمی‌کند، خودش نویز است؛ ولی «کاهش ۵۰٪
اجباری» می‌ساخت. تا معیار ضربه نسخه ۷ ساخته شود — نشست ۱۲ بند ۲ — ضربه
فقط شمرده و نشان داده می‌شود: ستون «ض» با برچسب «اطلاعی — مبنای امتیاز
ردشده». هیچ حکم کاهش یا خروج، هیچ ردیف اقدام اجباری و هیچ اثری در ترتیب
فروش. در دفتر روزانه و هفتگی هر دو — هر دو همین build_report هستند؛
هفتگی با --candidates. ابطال با بسته هفتگی دست نمی‌خورد.

همان روز، تصمیم دوم کاربر: خود امتیاز هم. حکم «ضعیف — نامزد فروش» با امتیاز
زیر ‎-0.5 و آزمون جانشینی هم اطلاعی‌اند، با همان برچسب؛ هیچ حکم، ردیف اقدام
یا دلیل فروشی از امتیاز ساخته نمی‌شود. «داده ناکافی» می‌ماند: آن حکم از
نیامدن کندل است، نه از مقدار امتیاز.
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
LABEL = "اطلاعی — مبنای امتیاز ردشده"
# هر نشانه حکم یا اقدامی که پیش از این از ضربه ساخته می‌شد
STRIKE_ACTS = ("کاهش ۵۰٪ اجباری", "خروج کامل (۴ ضربه)", "آماده‌سازی کاهش",
               "کاهش حداقل ۵۰٪", "سه ضربه متوالی", "ضربه متوالی")
# هر نشانه حکم یا اقدامی که پیش از این از امتیاز و جانشینی ساخته می‌شد
SCORE_ACTS = ("نامزد فروش", "چرخش به", "✅ اجرا", "تأیید هفته بعد", "آستانه اجرا",
              "تعویض در هفته")


def _h() -> dict:
    return {"version": 2, "updated": "2026-10-06T00:00:00+00:00", "source": "آزمون",
            "frozen": {"date": "2026-09-25", "members": {}}, "cash": [], "positions": [],
            "ledger": []}


def _row(sym: str, strikes: int, inv=1.0, weekly=None, score=0.5, rs30=0.05,
         swap_edge=None, swap_to=None) -> dict:
    pos = {"symbol": sym, "book": "position", "status": "open", "invalidation": inv,
           "lots": [{"qty": 1.0, "account": "A", "entry": None}]}
    return {"pos": pos, "qty": 1.0, "price": 500.0, "value": 500.0, "dust": False,
            "avg_entry": None, "score": score, "rsi": 55.0, "rs30": rs30,
            "strikes": strikes, "weekly": weekly, "weekly_why": [],
            "swap_edge": swap_edge, "swap_to": swap_to}


def _wk(close: float) -> dict:
    return {"close": close, "closed_at": "2026-10-05T00:00:00+00:00"}


# ═══════════════ حکم ═══════════════

@pytest.mark.parametrize("n", [2, 3, 4, 7])
def test_strikes_make_no_verdict(n) -> None:
    """هر شمار ضربه، با امتیاز و ابطال سالم، همان «نگه‌دار» است."""
    assert B._verdict(_row("AAA", n, weekly=_wk(600.0))) == "نگه‌دار"


def test_invalidation_still_exits() -> None:
    """قفل: ابطال با بسته هفتگی دست نخورد — با ضربه یا بی آن."""
    for n in (0, 4):
        v = B._verdict(_row("AAA", n, inv=550.0, weekly=_wk(520.0)))
        assert v.startswith("⛔ خروج ۱۰۰٪ — بسته هفتگی زیر ابطال")


def test_weak_score_makes_no_verdict() -> None:
    """امتیاز زیر ‎-0.5 دیگر «ضعیف — نامزد فروش» نیست."""
    assert B._verdict(_row("AAA", 0, score=-1.5, weekly=_wk(600.0))) == "نگه‌دار"


def test_swap_edge_makes_no_verdict() -> None:
    """مزیت جانشینی بالای آستانه پیشین هم حکم چرخش نمی‌سازد."""
    r = _row("AAA", 0, weekly=_wk(600.0), swap_edge=0.9, swap_to="BBB")
    assert B._verdict(r) == "نگه‌دار"


def test_missing_data_still_flagged() -> None:
    """قفل: «داده ناکافی» از نیامدن کندل است، نه از مقدار امتیاز — می‌ماند."""
    assert B._verdict(_row("AAA", 0, score=None, weekly=_wk(600.0))) == "داده ناکافی"


# ═══════════════ گزارش ═══════════════

def _report(rows, candidates=()) -> str:
    return B.build_report(_h(), rows, None, list(candidates), "آزمون")


def _score_rows() -> list[dict]:
    return [_row("AAA", 0, score=-1.2, rs30=0.10, swap_edge=2.55, swap_to="CCC"),
            _row("BBB", 0, score=0.8, rs30=-0.05)]


def test_score_column_labeled() -> None:
    book = _report(_score_rows()).split("## ۲")[1].split("## ۳")[0]
    head = [c.strip() for c in
            [l for l in book.splitlines() if l.startswith("| نماد")][0].split("|")]
    assert "امتیاز — اطلاعی" in head


def test_swap_section_is_advisory() -> None:
    rep = _report(_score_rows(), [{"symbol": "CCC", "score": 1.5}])
    swap = rep.split("## ۴")[1].split("## ۵")[0]
    assert LABEL in swap
    # مزیت هنوز نشان داده می‌شود: ۱.۵ − (−۱.۲) − ۰.۱۵ = ۲.۵۵
    assert "+2.55" in swap
    for s in SCORE_ACTS:
        assert s not in rep, s


def test_action_list_ignores_score() -> None:
    rep = _report(_score_rows(), [{"symbol": "CCC", "score": 1.5}])
    act = rep.split("## ۶")[1]
    assert "AAA" not in act and "CCC" not in act


def test_sell_reasons_ignore_score() -> None:
    rep = _report(_score_rows())
    sell = rep.split("## ۵")[1].split("## ۶")[0]
    lines = [l for l in sell.splitlines() if l.startswith("| ") and l[2].isdigit()]
    assert "BBB" in lines[0] and "AAA" in lines[1]
    assert "امتیاز" not in "".join(lines)


def test_column_kept_with_label() -> None:
    rep = _report([_row("AAA", 3), _row("BBB", 4)])
    book = rep.split("## ۲")[1].split("## ۳")[0]
    head = [l for l in book.splitlines() if l.startswith("| نماد")][0]
    assert "ض" in [c.strip().split(" ")[0] for c in head.split("|")]
    assert LABEL in book
    # شمار خود ضربه هنوز در جدول دیده می‌شود
    aaa = [l for l in book.splitlines() if l.startswith("| AAA")][0]
    bbb = [l for l in book.splitlines() if l.startswith("| BBB")][0]
    assert "| 3 |" in aaa and "| 4 |" in bbb


def test_report_has_no_strike_rule_or_action() -> None:
    rep = _report([_row("AAA", 3), _row("BBB", 4)])
    for s in STRIKE_ACTS:
        assert s not in rep, s
    assert "بدون استثنا" not in rep.split("## ۲")[1].split("## ۳")[0]


def test_action_list_ignores_strikes() -> None:
    rep = _report([_row("AAA", 3), _row("BBB", 4)])
    act = rep.split("## ۶")[1]
    assert "AAA" not in act and "BBB" not in act


def test_sell_reasons_ignore_strikes() -> None:
    """ضربه نه ترتیب را عوض می‌کند، نه دلیل فروش است."""
    rep = _report([_row("AAA", 4, rs30=0.10), _row("BBB", 0, rs30=-0.05)])
    sell = rep.split("## ۵")[1].split("## ۶")[0]
    lines = [l for l in sell.splitlines() if l.startswith("| ") and l[2].isdigit()]
    assert "BBB" in lines[0] and "AAA" in lines[1]
    assert "ضربه" not in "".join(lines)


# ═══════════════ main روزانه و هفتگی، بی‌شبکه ═══════════════

def _day(offset: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset)).strftime("%Y-%m-%d")


def _frame(n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = [{"ts": open_ts - pd.Timedelta(days=n - 1 - i), "o": 100.0 + i,
             "h": 102.0 + i, "l": 98.0 + i, "c": 100.0 + i, "v": 10.0}
            for i in range(n)]
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


@pytest.fixture
def run_book(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "holdings.json").write_text(json.dumps({
        "version": 2, "updated": datetime.now(UTC).isoformat(), "source": "آزمون",
        "frozen": {"date": "2026-09-25", "members": {"AAA": 2.0}},
        "cash": [{"asset": "USDT", "qty": 100.0, "account": "A"}], "ledger": [],
        "positions": [{"symbol": "AAA", "book": "position", "status": "open",
                       "lots": [{"qty": 2.0, "account": "A", "entry": None}],
                       "invalidation": None}]}),
        encoding="utf-8")

    def run(extra: list[str], scores: dict | None = None) -> tuple[dict, str]:
        # امتیاز امروز با این کندل حدود ۱.۱ است؛ چهار کاهش پیاپی پیش از آن
        hist = [{"date": _day(i - 4), "score": s} for i, s in enumerate((4.0, 3.5, 3.0, 2.0))]
        (tmp_path / B.STATE_FILE).write_text(json.dumps(
            {"reviews": {"AAA": hist}, "swaps": [], "score_basis": B.SCORE_BASIS}),
            encoding="utf-8")

        def candles(sym, *a, **k):
            df = _frame()
            df.attrs["sym"] = sym
            return df
        monkeypatch.setattr(B, "candles", candles)
        if scores is not None:
            # امتیاز دلخواه هر نماد؛ بیت‌کوین مرجع است و امتیاز نمی‌خواهد
            monkeypatch.setattr(B, "score_position", lambda df, btc, *a, **k: {
                "price": 100.0, "score": scores[df.attrs["sym"]], "rsi": 50.0,
                "rs30": 0.01})
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--regime", "-0.6",
                                          "--out", "out.md", *extra])
        assert B.main() == 0
        saved = json.loads((tmp_path / B.STATE_FILE).read_text(encoding="utf-8"))
        return saved, (tmp_path / "out.md").read_text(encoding="utf-8")
    return run


@pytest.mark.parametrize("extra", [[], ["--candidates", "BBB"]], ids=["daily", "weekly"])
def test_main_counts_but_does_not_act(run_book, extra) -> None:
    saved, rep = run_book(extra)
    # شمارش ادامه دارد: تاریخچه پنج ورودی و چهار ضربه در ستون
    assert len(saved["reviews"]["AAA"]) == 5
    aaa = [l for l in rep.split("## ۲")[1].splitlines() if l.startswith("| AAA")][0]
    assert "| 4 |" in aaa
    for s in STRIKE_ACTS:
        assert s not in rep, s
    assert LABEL in rep


def test_main_weekly_weak_score_and_swap_do_not_act(run_book) -> None:
    """
    هفتگی با نامزد: AAA امتیاز ‎-1.2 — پیش از این «نامزد فروش» — و نامزد BBB
    با ۱.۵، مزیت ۲.۵۵ — پیش از این حکم و ردیف «چرخش به BBB».
    """
    saved, rep = run_book(["--candidates", "BBB"], scores={"AAA": -1.2, "BBB": 1.5})
    assert saved["reviews"]["AAA"][-1]["score"] == -1.2
    for s in SCORE_ACTS + STRIKE_ACTS:
        assert s not in rep, s
    assert "+2.55" in rep.split("## ۴")[1].split("## ۵")[0]
