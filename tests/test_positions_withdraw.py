"""
برداشت از رادار — withdraw. تصمیم کاربر، ۲۹ سپتامبر ۲۰۲۶.

ETH 0.15892356 و USDT 3.17443595 «صرافی دوم» پول خرج شخصی است — نه ذخیره،
نه معامله. از امروز انگار جزو رادار نبوده: نه در کل سرمایه، نه ذخیره، نه ریسک.
exit یا trim نیست: پیگیری هزینه فرصت ندارد و در آمار نتیجه‌ها نمی‌آید — همان
الگوی ONDO در ک۱۰. تنها رد: یک ردیف دفتر کل و یک رویداد STATE.

چرا نوع تازه و نه adjust: adjust سقف ۱٪ مقدار نماد دارد — پاداش سهام‌گذاری
و کارمزد — و این برداشت حدود ۴۵٪ ETH است. شل‌کردن آن سقف ناوردا را برای
همه ردیف‌ها سست می‌کرد. withdraw فقط کم می‌کند، دلیل و حساب لازم دارد،
سهمیه ورود دوباره نمی‌سازد، و نقد همان حساب را در همان یک ردیف برمی‌دارد.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_positions as P
from test_positions import NOW, _h, _j, _row

REASON = "پول خرج شخصی — از رادار حذف شد"


@pytest.fixture
def files(tmp_path):
    h = _h()
    h["cash"].append({"asset": "USDT", "qty": 3.17, "account": "B"})
    hp, jp = tmp_path / "holdings.json", tmp_path / "journal.json"
    hp.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
    jp.write_text(json.dumps(_j(), ensure_ascii=False), encoding="utf-8")
    return hp, jp


def _run(files, *args) -> int:
    hp, jp = files
    return P.main(["--holdings", str(hp), "--journal", str(jp),
                   "--optcost", str(hp.parent / "optcost.json"), *args])


def _read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _withdraw(files, *extra) -> int:
    return _run(files, "withdraw", "--symbol", "ETH", "--qty", "0.15", "--account", "B",
                "--reason", REASON, *extra)


def test_withdraw_removes_lot_and_cash_one_row(files) -> None:
    assert _withdraw(files, "--cash", "3.17") == 0
    h = _read(files[0])
    eth = next(p for p in h["positions"] if p["symbol"] == "ETH")
    assert [(l["qty"], l["account"]) for l in eth["lots"]] == [(0.25, "A")]
    assert [c["account"] for c in h["cash"]] == ["A"]        # حساب B کلاً رفت
    row = h["ledger"][-1]
    assert (row["action"], row["symbol"], row["delta"], row["account"], row["reason"]) == \
        ("withdraw", "ETH", -0.15, "B", REASON)
    assert row["cash"] == {"asset": "USDT", "qty": 3.17, "account": "B"}
    assert len(h["ledger"]) == 1
    P.validate(h, _j())


def test_withdraw_is_not_an_outcome(files) -> None:
    """الگوی ONDO ک۱۰: بی‌پیگیری هزینه فرصت، بی‌سهمیه ورود دوباره."""
    assert _withdraw(files, "--cash", "3.17") == 0
    assert not (files[0].parent / "optcost.json").exists()
    h = _read(files[0])
    assert P.reentry_state(h, "ETH") is None


def test_withdraw_leaves_capital(files) -> None:
    before = P.value(_read(files[0]), {"SOL": 100.0, "ETH": 2000.0, "TRX": 0.3})
    assert _withdraw(files, "--cash", "3.17") == 0
    after = P.value(_read(files[0]), {"SOL": 100.0, "ETH": 2000.0, "TRX": 0.3})
    assert after["total"] == pytest.approx(before["total"] - 0.15 * 2000.0 - 3.17)
    assert after["stable_usd"] == pytest.approx(before["stable_usd"] - 3.17)


def test_withdraw_needs_reason_and_account(files) -> None:
    with pytest.raises(SystemExit):
        _run(files, "withdraw", "--symbol", "ETH", "--qty", "0.15", "--account", "B")
    with pytest.raises(SystemExit):
        _run(files, "withdraw", "--symbol", "ETH", "--qty", "0.15", "--reason", REASON)
    assert _read(files[0])["ledger"] == []


def test_withdraw_more_than_account_or_cash_refused(files) -> None:
    assert _run(files, "withdraw", "--symbol", "ETH", "--qty", "0.2", "--account", "B",
                "--reason", REASON) != 0
    assert _withdraw(files, "--cash", "5") != 0
    assert _read(files[0])["ledger"] == []                   # فایل دست نخورد


def test_replay_rules() -> None:
    h = _h()
    h["positions"][1]["lots"] = [{"qty": 0.25, "account": "A", "entry": None}]
    h["ledger"] = [_row("withdraw", "ETH", -0.15, account="B", reason=REASON)]
    P.validate(h, _j())
    for bad in (dict(reason=""), dict(account=None)):
        h["ledger"] = [_row("withdraw", "ETH", -0.15, **{"account": "B", "reason": REASON,
                                                          **bad})]
        with pytest.raises(P.PositionsError):
            P.validate(h, _j())
    h["ledger"] = [_row("withdraw", "ETH", 0.15, account="B", reason=REASON)]
    h["positions"][1]["lots"] = [{"qty": 0.55, "account": "A", "entry": None}]
    with pytest.raises(P.PositionsError, match="کاهش"):
        P.validate(h, _j())


def test_trim_still_goes_to_optcost(files) -> None:
    """قفل: رفتار trim عوض نشد — هنوز رکورد هزینه فرصت می‌سازد."""
    assert _run(files, "trim", "--symbol", "SOL", "--qty", "1", "--price", "100",
                "--reason", "reserve") == 0
    assert (files[0].parent / "optcost.json").exists()
