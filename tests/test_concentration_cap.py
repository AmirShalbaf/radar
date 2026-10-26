"""
سقف تمرکز — بند ۴ متن ۱۸، تصمیم کاربر ۲۵ اکتبر ۲۰۲۶. سهم هیچ ارزی پس از خرید از ۳۰٪ کل
سرمایه بیشتر نمی‌شود — add، reenter و پیشنهاد بازخرید. فروش اجباری نیست؛ ارزی که الان
بالای سقف است فقط خرید تازه نمی‌گیرد. سهمی از بودجه که سقف جلویش را می‌گیرد به نامزد
پذیرفته‌شده بعدی می‌رسد؛ اگر نامزدی نماند، در ذخیره می‌ماند و دلیلش گفته می‌شود.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import radar_book as B
import radar_budget as BG
import radar_positions as P
import radar_rebuy as RB
import test_rebuy_quality as T


def _val(**v):
    total = v.pop("total")
    return {"rows": [{"symbol": s, "book": "position", "value": x, "paper": False, "dust": False}
                     for s, x in v.items()],
            "total": total, "stable_usd": total - sum(v.values()), "incomplete": False,
            "missing": []}


def test_cap_is_thirty_percent_single_source() -> None:
    assert P.CONCENTRATION_CAP_PCT == 30


def test_share_after_and_room() -> None:
    val = _val(SOL=525.0, ETH=100.0, total=1500.0)
    assert P.coin_value(val, "SOL") == pytest.approx(525.0)
    assert P.share_pct(val, "SOL") == pytest.approx(35.0)
    assert P.cap_room(val, "SOL") == pytest.approx(0.0)              # ۳۵٪ — بالای سقف
    assert P.cap_room(val, "ETH") == pytest.approx(350.0)            # ۳۰٪ × 1500 − 100
    assert P.share_after(val, "ETH", 350.0, spent_cash=350.0) == pytest.approx(30.0)
    # add بی کاهش نقد: کل سرمایه هم بزرگ می‌شود
    assert P.share_after(val, "ETH", 300.0, spent_cash=0.0) == pytest.approx(400 / 1800 * 100)


def test_allocation_spills_past_cap_then_reserve() -> None:
    q = T._q(SOL=(0.15, "2026-10-24T03:49:33+00:00"))
    data = {"SOL": T._d(100.0, 96.7, 9.0), "ETH": T._d(100.0, 95.0, 3.0),
            "TAO": T._d(100.0, 80.0, 2.0), "ONDO": T._d(100.0, 60.0, -20.0)}
    val = _val(SOL=525.0, ETH=430.0, TAO=0.0, total=1500.0)
    ev = RB.evaluate(data, T.LISTED, q, 100.0, val=val)
    why = {r["symbol"]: r["why"] for r in ev["rejected"]}
    assert "بالای سقف تمرکز" in why["SOL"] and "35.0٪" in why["SOL"]
    got = {r["symbol"]: r["usd"] for r in ev["ranked"]}
    assert got["ETH"] == pytest.approx(20.0)                      # تا 450 = ۳۰٪
    assert got["TAO"] == pytest.approx(80.0)                      # سهم بسته‌شده به بعدی
    eth = next(r for r in ev["ranked"] if r["symbol"] == "ETH")
    assert "سقف تمرکز جلوی 80 دلار را گرفت" in eth["why"]
    ev = RB.evaluate({"SOL": T._d(100.0, 96.7, 9.0), "ETH": T._d(100.0, 95.0, 3.0)},
                     T.LISTED, q, 100.0, val=val)
    assert ev["left"] == pytest.approx(80.0)
    txt = "\n".join(RB.lines({"from": "انقباضی", "to": "محتاط", "day": "2026-10-28",
                              "target": 25, "old_target": 40}, 100.0, ev, val))
    assert "در ذخیره می‌ماند: 80 دلار — سقف تمرکز جلوی بخشی را گرفت" in txt


def test_book_shows_share_and_flag() -> None:
    val = _val(SOL=525.0, ETH=100.0, total=1500.0)
    txt = B.build_report(T._h(), [], BG.band_by_name("انقباضی"), [], val=val)
    assert "### سهم هر ارز — سقف تمرکز ۳۰٪" in txt
    assert "| SOL | 525 | 35.0٪ | ⛔ بالای سقف — خرید تازه ممنوع |" in txt
    assert "| ETH | 100 | 6.7٪ | زیر سقف — جا 350 دلار |" in txt


# ── فرمان‌ها ──

@pytest.fixture
def files(tmp_path, monkeypatch):
    return T.make_files(tmp_path, monkeypatch)


def test_reserve_reenter_above_cap_needs_labeled_deviation(files, capsys) -> None:
    # SOL حدود 548 از کل حدود 1460 — ۳۷٪؛ قیمت 97 در پنجره نزدیک ابطال، پس فقط سقف منفی است
    assert P.main(T._re("SOL", 0.15, 97.0)) == 2
    err = capsys.readouterr().err
    assert "سقف تمرکز" in err and "حکم بازخرید منفی" not in err
    assert P.main(T._re("SOL", 0.15, 97.0, extra=("--deviation", "RD-20261028-01"))) == 0
    row = T._load(files)["ledger"][-1]
    assert row["deviation"] == "RD-20261028-01" and row["share_after_pct"] > 30


def test_reserve_reenter_under_cap_records_share(files) -> None:
    assert P.main(T._re("TAO", 0.1, 233.0)) == 0
    row = T._load(files)["ledger"][-1]
    assert "deviation" not in row and row["share_after_pct"] < 5


def test_add_refused_above_cap_unless_labeled_deviation(files, capsys) -> None:
    j = json.loads((files / "radar_journal.json").read_text(encoding="utf-8"))
    j["trades"].append({"decision_id": "D-1", "setup_name": "ب۱", "book": "position"})
    (files / "radar_journal.json").write_text(json.dumps(j), encoding="utf-8")
    base = ["--holdings", "holdings.json", "--journal", "radar_journal.json", "--optcost",
            "oc.json", "add", "--symbol", "SOL", "--qty", "1", "--price", "100",
            "--account", "LBank", "--decision-id", "D-1", "--setup-name", "ب۱"]
    assert P.main(base) == 2
    assert "سقف تمرکز" in capsys.readouterr().err
    assert P.main(base + ["--deviation", "RD-20261028-02"]) == 2      # پیروی، نه سرپیچی
    assert P.main(base + ["--deviation", "RD-20261028-01"]) == 0
    row = T._load(files)["ledger"][-1]
    assert row["deviation"] == "RD-20261028-01" and row["share_after_pct"] > 30
    small = base[:]
    small[small.index("SOL")] = "AAVE"
    small[small.index("--qty") + 1] = "0.1"
    small[small.index("--price") + 1] = "150"
    assert P.main(small) == 0
    assert "deviation" not in T._load(files)["ledger"][-1]


def test_missing_price_refuses(files, monkeypatch, capsys) -> None:
    monkeypatch.setattr(P, "_prices", lambda syms: {s: None for s in syms})
    assert P.main(T._re("TAO", 0.1, 233.0)) == 2
    assert "داده ندارم" in capsys.readouterr().err
