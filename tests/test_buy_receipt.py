"""
رسید خرید add و ورود دوباره پس از ابطال — ک۱۲۷، متن ۳۵، ۲ نوامبر ۲۰۲۶.

یافته جلسه بیرونی روی رونوشت: reenter بی --reserve-plan لات را می‌افزود ولی نقد تتر دست
نمی‌خورد و --gross، --fee و --order-id بی‌صدا نادیده می‌ماندند؛ add اصلاً رسید نمی‌گرفت. با
ورود دوباره SOL نقد دفتر بیش از واقع می‌شد. حالا همان قاعده بازخرید نقشه ذخیره: --gross و
--fee هر دو، یا --no-receipt صریح؛ هزینه از تتر همان حساب، کارمزد کوینی از مقدار دریافتی.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import radar_book as B
import radar_positions as P
import test_positions as T
import test_reenter_after_exit as R

EXIT_AT = "2026-09-26T10:00:00+00:00"
BUY_AT = "2026-09-28T08:00:00+00:00"
# 6 × 95 با کارمزد 0.1٪؛ نقد A پس از خروج: 3 + 570 − 0.57
EXIT = ("--gross", "570", "--fee", "0.57", "--at", EXIT_AT)
CASH_AFTER_EXIT = 572.43


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_prices", lambda syms: {s: 100.0 for s in syms})
    monkeypatch.setattr(P, "CONCENTRATION_CAP_PCT", 100)
    monkeypatch.setattr(P, "level_proposal", lambda sym, price: {
        "level": 90.0, "anchor": 104.0, "atr_w": 10.0, "price": price, "week_close": 104.0,
        "week_closed_at": "2026-09-28T00:00:00+00:00", "distance_atr": 1.4})
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(T._h(), ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(T._j(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "watch.json").write_text('{"positions": []}', encoding="utf-8")
    return hp, jp


def _exited(files, monkeypatch):
    assert T._run(files, "exit", "--symbol", "SOL", "--price", "95", "--level", "100",
                  *EXIT) == 0
    monkeypatch.setattr(P, "weekly_close", lambda sym, get=None, now=None: (
        {"close": 104.0, "closed_at": "2026-09-28T00:00:00+00:00", "venue": "okx"}, []))


def _reenter(files, *extra):
    wp = str(files[0].parent / "watch.json")
    return T._run(files, "reenter", "--symbol", "SOL", "--qty", "4", "--price", "105",
                  "--account", "A", "--level", "90", "--watch", wp, "--at", BUY_AT, *extra)


def _cash(files) -> float:
    return next(c["qty"] for c in T._read(files[0])["cash"] if c["account"] == "A")


def test_reenter_receipt_takes_cash(files, monkeypatch) -> None:
    _exited(files, monkeypatch)
    assert _cash(files) == pytest.approx(CASH_AFTER_EXIT)
    assert _reenter(files, "--gross", "420", "--fee", "0.42", "--order-id", "o-1") == 0
    h = T._read(files[0])
    assert _cash(files) == pytest.approx(CASH_AFTER_EXIT - 420.42)
    row = h["ledger"][-1]
    assert (row["action"], row["delta"], row["at"], row["account"]) == ("reenter", 4.0, BUY_AT, "A")
    assert (row["gross"], row["fee"], row["fee_asset"], row["cost"], row["order_id"]) == \
        (420.0, 0.42, "USDT", 420.42, "o-1")
    sol = next(p for p in h["positions"] if p["symbol"] == "SOL")
    assert sol["lots"][-1] == {"qty": 4.0, "account": "A", "entry": 105.0}
    P.validate(h, T._j())


def test_reenter_fee_in_coin(files, monkeypatch) -> None:
    _exited(files, monkeypatch)
    assert _reenter(files, "--gross", "420", "--fee", "0.004", "--fee-asset", "SOL") == 0
    h = T._read(files[0])
    row = h["ledger"][-1]
    assert row["delta"] == pytest.approx(3.996) and row["cost"] == 420.0
    assert _cash(files) == pytest.approx(CASH_AFTER_EXIT - 420.0)
    P.validate(h, T._j())


def test_reenter_without_receipt_refused(files, monkeypatch, capsys) -> None:
    _exited(files, monkeypatch)
    before = files[0].read_text(encoding="utf-8")
    assert _reenter(files) == 2
    assert "رسید لازم است" in capsys.readouterr().err
    assert files[0].read_text(encoding="utf-8") == before


def test_no_receipt_keeps_cash_and_flags_row(files, monkeypatch) -> None:
    _exited(files, monkeypatch)
    assert _reenter(files, "--no-receipt") == 0
    h = T._read(files[0])
    assert h["ledger"][-1]["no_receipt"] is True and "cost" not in h["ledger"][-1]
    assert _cash(files) == pytest.approx(CASH_AFTER_EXIT)
    P.validate(h, T._j())


def test_receipt_errors_change_nothing(files, monkeypatch, capsys) -> None:
    _exited(files, monkeypatch)
    before = files[0].read_text(encoding="utf-8")
    assert _reenter(files, "--no-receipt", "--gross", "420", "--fee", "0.42") == 2
    assert "هم‌زمان" in capsys.readouterr().err
    assert _reenter(files, "--gross", "400", "--fee", "0.4") == 2
    assert "نمی‌خواند" in capsys.readouterr().err
    assert _reenter(files, "--gross", "420", "--fee", "0.42", "--fee-asset", "BNB") == 2
    assert "--fee-asset" in capsys.readouterr().err
    wp = str(files[0].parent / "watch.json")
    assert T._run(files, "reenter", "--symbol", "SOL", "--qty", "6", "--price", "105",
                  "--account", "A", "--level", "90", "--watch", wp, "--at", BUY_AT,
                  "--gross", "630", "--fee", "0.63") == 2
    assert "کافی نیست" in capsys.readouterr().err
    assert files[0].read_text(encoding="utf-8") == before


def test_add_receipt_and_time(files) -> None:
    hp, jp = files
    jp.write_text(json.dumps(T._j(T._jt("D-9", book="position", sym="LINK")),
                             ensure_ascii=False), encoding="utf-8")
    assert T._run(files, "add", "--symbol", "LINK", "--qty", "0.1", "--price", "14",
                  "--account", "A", "--decision-id", "D-9", "--setup-name", "الف۱",
                  "--gross", "1.4", "--fee", "0.0014", "--at", BUY_AT) == 0
    h = T._read(hp)
    row = h["ledger"][-1]
    assert (row["action"], row["at"], row["cost"], row["account"]) == ("add", BUY_AT, 1.4014, "A")
    assert _cash(files) == pytest.approx(3.0 - 1.4014)
    P.validate(h, json.loads(jp.read_text(encoding="utf-8")))


def test_add_without_receipt_refused(files, capsys) -> None:
    hp, jp = files
    jp.write_text(json.dumps(T._j(T._jt("D-9", book="position", sym="LINK")),
                             ensure_ascii=False), encoding="utf-8")
    assert T._run(files, "add", "--symbol", "LINK", "--qty", "0.1", "--price", "14",
                  "--account", "A", "--decision-id", "D-9", "--setup-name", "الف۱") == 2
    assert "رسید لازم است" in capsys.readouterr().err


def test_tampered_cost_is_caught(files, monkeypatch) -> None:
    _exited(files, monkeypatch)
    assert _reenter(files, "--gross", "420", "--fee", "0.42") == 0
    h = T._read(files[0])
    h["ledger"][-1]["cost"] += 1.0
    next(c for c in h["cash"] if c["account"] == "A")["qty"] -= 1.0   # ناوردای نقد سر جایش
    with pytest.raises(P.PositionsError, match="رسید خرید ناسازگار"):
        P.validate(h, T._j())


def test_reserve_rebuy_refuses_no_receipt(files, capsys) -> None:
    assert T._run(files, "reenter", "--symbol", "SOL", "--qty", "1", "--price", "100",
                  "--account", "A", "--reserve-plan", "2026-10-24T03:46:49+00:00",
                  "--watch", str(files[0].parent / "watch.json"), "--no-receipt") == 2
    assert "بی رسید" in capsys.readouterr().err


def test_suggestions_carry_receipt_and_dormant_level() -> None:
    msg = next(m for m in R._watch_msgs(R.AFTER) if "ورود دوباره مجاز" in m)
    assert "--gross" in msg and "--fee" in msg
    h = R._h()
    st = P.reentry_state(h, "SOL")
    base = {"symbol": "SOL", "state": st, "weekly": {"close": 98.0, "closed_at": R.AFTER},
            "why": []}
    txt = B.build_report(h, [], None, [], "آزمون", reentry=[dict(base, no_level=False)])
    line = next(l for l in txt.splitlines() if "ورود دوباره مجاز است" in l)
    assert "--gross" in line and "--level" not in line
    txt = B.build_report(h, [], None, [], "آزمون", reentry=[dict(base, no_level=True)])
    line = next(l for l in txt.splitlines() if "ورود دوباره مجاز است" in l)
    assert "--gross" in line and "--level <سطح تازه>" in line


def test_dormant_symbols(tmp_path) -> None:
    wp = tmp_path / "watch.json"
    wp.write_text(json.dumps({"dormant": [{"symbol": "sol", "invalidation": 96.7108}]}),
                  encoding="utf-8")
    assert B._dormant(str(wp)) == {"SOL"}
    assert B._dormant(str(tmp_path / "none.json")) == set()
