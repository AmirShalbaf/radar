"""
آزمون اندازه‌گیری دفتر معامله در radar_size.py — نشست ۳، تصمیم کاربر ۲۶ سپتامبر ۲۰۲۶.

پیش از این امتیاز رژیم دستی و اجباری بود و باند خام می‌ساخت؛ هیسترزیس ک۳۲
به ابزار اندازه‌گیری نمی‌رسید. حالا:
- پیش‌فرض: باند مؤثر دفتر معامله از regime.json، با همان load_regime و
  effective_trade_band سبد — یک منبع.
- امتیاز دستی فقط با کلید صریح --regime، با هشدار.
- رژیم کهنه یا غایب بدون کلید دستی: خطای صریح، نه باند جانشین.
به‌علاوه باگ نمایش عدد: با صفر رقم اعشار، 500 «5» چاپ می‌شد — اینجا و در
radar_snapshot.py.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_size as Z
import radar_snapshot as S

UTC = timezone.utc
ARGS = ["--balance", "1000", "--score", "1.0", "--entry", "100", "--stop", "95",
        "--invalidation", "94", "--target", "120", "--win-prob", "0.5"]


def test_fmt_zero_decimals() -> None:
    assert Z.fmt(500.0, 0) == "500"
    assert Z.fmt(1000.0, 0) == "1,000"
    assert Z.fmt(2.5) == "2.5"
    assert S.fmt(500.0, 0) == "500"
    assert S.fmt(20.0, 0) == "20"
    assert S.fmt(2.50, 4) == "2.5"


@pytest.fixture
def size(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def go(extra=(), regime: dict | None = None):
        if regime is not None:
            (tmp_path / "regime.json").write_text(json.dumps(regime, ensure_ascii=False),
                                                  encoding="utf-8")
        rc = Z.main([*ARGS, *extra])
        c = capsys.readouterr()
        return rc, c.out, c.err
    return go


def _row(out: str, head: str) -> str:
    return next(l for l in out.splitlines() if l.startswith(f"| {head}"))


def test_band_from_regime_file_with_hysteresis(size) -> None:
    """امتیاز 0.2 سازنده است، ولی باند مؤثر محتاط: سقف ۴٪."""
    rc, out, _ = size(regime={"score": 0.2, "generated_at": datetime.now(UTC).isoformat(),
                              "trade_band": {"name": "محتاط"}})
    assert rc == 0
    assert "محتاط" in _row(out, "باند اندازه‌گیری")
    assert "هیسترزیس" in _row(out, "باند اندازه‌گیری")
    assert "4.0٪" in _row(out, "سقف ریسک باز کل")
    assert "regime.json" in _row(out, "منبع رژیم")


def test_missing_regime_file_is_error(size) -> None:
    rc, out, err = size()
    assert rc == 2
    assert "رژیم کهنه" in err


def test_stale_regime_file_is_error(size) -> None:
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    rc, _, err = size(regime={"score": 0.2, "generated_at": old})
    assert rc == 2 and "رژیم کهنه" in err


def test_manual_score_only_with_explicit_key_and_warning(size) -> None:
    rc, out, _ = size(extra=("--regime", "0.2"))
    assert rc == 0
    assert "سازنده" in _row(out, "باند اندازه‌گیری")
    assert "امتیاز رژیم دستی" in out.split("## ۱")[0]


def test_regime_is_not_required_argument() -> None:
    src = (Path(Z.__file__)).read_text(encoding="utf-8")
    assert 'add_argument("--regime", type=float, required=True' not in src
