"""
آزمون منبع رژیم — نشست ۱ نقشه رادار ۷، مورد ۳.

باگ: گام بازبینی سبد در radar-daily.yml با
`--regime "${RADAR_REGIME:--1.0}"` اجرا می‌شد و این متغیر هیچ‌جا مقدار
نمی‌گرفت. پس هر روز رژیم انقباضی به گزارش سبد تزریق می‌شد. گردش‌کار
هفتگی هم در اجرای زمان‌بندی‌شده `-1.0` می‌گذاشت، و خود radar_book.py
پیش‌فرض 0.0 داشت — اجرای محلی بی‌صدا «سازنده» می‌گرفت.

رفع موقت تا نشست ۲: رژیم از regime.json خوانده می‌شود. اگر فایل نبود،
خراب بود یا عمرش بالای هفت روز بود، گزارش صریح می‌گوید «رژیم کهنه —
بازمحاسبه لازم است» و هیچ مقدار پیش‌فرضی جا نمی‌زند.

قالب کمینه regime.json: دو میدان score و generated_at. خواننده فقط همین
دو را لازم دارد و میدان اضافه را نادیده می‌گیرد، تا نشست ۲ بتواند میدان
اضافه کند بی‌آنکه چیزی بشکند.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"
WEEKLY = ROOT / ".github" / "workflows" / "radar-weekly.yml"

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
STALE = "رژیم کهنه — بازمحاسبه لازم است"
BANDS = ("انبساطی", "سازنده", "محتاط", "انقباضی", "بحرانی")


def _write(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def _doc(score=-0.6, age=timedelta(days=1), **extra) -> dict:
    d = {"score": score, "generated_at": (NOW - age).isoformat()}
    d.update(extra)
    return d


# ═══════════════ load_regime ═══════════════

def test_fresh_file_gives_score(tmp_path) -> None:
    r = B.load_regime(_write(tmp_path / "regime.json", _doc()), now=NOW)
    score, note = r.score, r.source
    assert score == -0.6
    assert "regime.json" in note


def test_extra_fields_are_ignored(tmp_path) -> None:
    """نشست ۲ میدان اضافه می‌نویسد — خواننده نباید بشکند."""
    doc = _doc(name="انقباضی", cap=2.5, missing=["DXY"], raw=-0.4, norm=-0.6)
    score = B.load_regime(_write(tmp_path / "regime.json", doc), now=NOW).score
    assert score == -0.6


def test_missing_file(tmp_path) -> None:
    r = B.load_regime(tmp_path / "regime.json", now=NOW)
    score, note = r.score, r.source
    assert score is None
    assert "نیست" in note


def test_eight_days_is_stale(tmp_path) -> None:
    p = _write(tmp_path / "regime.json", _doc(age=timedelta(days=8)))
    r = B.load_regime(p, now=NOW)
    score, note = r.score, r.source
    assert score is None
    assert "بیش از ۷ روز" in note


def test_exactly_seven_days_is_fresh(tmp_path) -> None:
    """«بالای هفت روز» کهنه است؛ خود هفت روز هنوز نه."""
    p = _write(tmp_path / "regime.json", _doc(age=timedelta(days=7)))
    score = B.load_regime(p, now=NOW).score
    assert score == -0.6


def test_naive_timestamp_is_invalid(tmp_path) -> None:
    """generated_at بدون منطقه زمانی نامعتبر است — عمرش را نمی‌شود دانست."""
    doc = {"score": -0.6, "generated_at": "2026-09-24T12:00:00"}
    r = B.load_regime(_write(tmp_path / "regime.json", doc), now=NOW)
    score, note = r.score, r.source
    assert score is None
    assert "منطقه زمانی" in note


def test_future_timestamp_is_invalid(tmp_path) -> None:
    p = _write(tmp_path / "regime.json", _doc(age=timedelta(days=-1)))
    r = B.load_regime(p, now=NOW)
    score, note = r.score, r.source
    assert score is None
    assert "آینده" in note


@pytest.mark.parametrize("content", [
    "{not json",
    "[1, 2]",
    json.dumps({"generated_at": NOW.isoformat()}),
    json.dumps({"score": "abc", "generated_at": NOW.isoformat()}),
    json.dumps({"score": True, "generated_at": NOW.isoformat()}),
    '{"score": NaN, "generated_at": "2026-09-25T00:00:00+00:00"}',
    json.dumps({"score": -0.6}),
    json.dumps({"score": -0.6, "generated_at": "دیروز"}),
])
def test_broken_file_gives_none_with_reason(tmp_path, content) -> None:
    """فایل خراب یعنی «رژیم کهنه» با دلیل — نه سقوط و نه مقدار جانشین."""
    p = tmp_path / "regime.json"
    p.write_text(content, encoding="utf-8")
    r = B.load_regime(p, now=NOW)
    score, note = r.score, r.source
    assert score is None
    assert note


# ═══════════════ main بدون شبکه ═══════════════

def _book_frame(n: int = 700) -> pd.DataFrame:
    open_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)
    rows = []
    for i in range(n):
        p = 100 + 0.05 * i
        rows.append({"ts": open_ts - pd.Timedelta(days=n - 1 - i),
                     "o": p, "h": p * 1.02, "l": p * 0.98, "c": p, "v": 10.0})
    df = pd.DataFrame(rows)
    df["confirm"] = [1] * (n - 1) + [0]
    return df


@pytest.fixture
def run_book(tmp_path, monkeypatch):
    """main را در پوشه موقت و بدون شبکه اجرا می‌کند؛ متن گزارش را برمی‌گرداند."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "holdings.json", {
        "balance_total": 1000, "stable_usd": 100,
        "positions": [{"symbol": "AAA", "size_usd": 200, "entry": 0,
                       "invalidation": None, "side": "long", "spot": True}]})
    monkeypatch.setattr(B, "candles", lambda *a, **k: _book_frame())

    def run(*args: str) -> str:
        monkeypatch.setattr(sys, "argv", ["radar_book.py", "--out", "out.md",
                                          *args])
        assert B.main() == 0
        return (tmp_path / "out.md").read_text(encoding="utf-8")
    return run


def _row(rep: str, head: str) -> str:
    return next(l for l in rep.splitlines() if l.startswith(f"| {head}"))


def test_main_without_regime_says_stale(run_book) -> None:
    """بدون کلید و بدون فایل: برچسب صریح، بدون هیچ باند جانشین."""
    rep = run_book()
    assert STALE in rep
    for head in ("رژیم |", "**هدف ذخیره استیبل"):
        cell = _row(rep, head).split("|")[2]
        assert not any(b in cell for b in BANDS)
        assert "٪" not in cell
    # حرارت حسابداری است و می‌ماند؛ فقط سقفش معلوم نیست
    assert "رژیم کهنه" in _row(rep, "**ریسک مؤثر")
    assert "مقایسه ممکن نیست" in rep


def test_main_stale_file_says_stale(run_book, tmp_path) -> None:
    doc = {"score": 0.8,
           "generated_at": (datetime.now(UTC) - timedelta(days=9)).isoformat()}
    _write(tmp_path / "regime.json", doc)
    rep = run_book()
    assert STALE in rep
    assert "انبساطی" not in _row(rep, "رژیم |")


def test_main_fresh_file_is_used(run_book, tmp_path) -> None:
    doc = {"score": -0.6,
           "generated_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    _write(tmp_path / "regime.json", doc)
    rep = run_book()
    assert STALE not in rep
    assert "انقباضی" in _row(rep, "رژیم |")
    assert "regime.json" in _row(rep, "منبع رژیم")


def test_main_manual_regime_wins(run_book, tmp_path) -> None:
    """کلید دستی بر فایل مقدم است و منبعش «دستی» نوشته می‌شود."""
    doc = {"score": 0.8,
           "generated_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    _write(tmp_path / "regime.json", doc)
    rep = run_book("--regime", "-0.6")
    assert "انقباضی" in _row(rep, "رژیم |")
    assert "دستی" in _row(rep, "منبع رژیم")


# ═══════════════ گردش‌کارها ═══════════════

def _step(path: Path, name: str) -> str:
    """متن یک گام گردش‌کار، از سطر نام تا گام بعد."""
    text = path.read_text(encoding="utf-8")
    start = text.index(f"- name: {name}")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_daily_injects_no_regime() -> None:
    text = DAILY.read_text(encoding="utf-8")
    assert "RADAR_REGIME" not in text
    step = _step(DAILY, "بازبینی سبد و موتور خروج")
    assert "--regime" not in step


def test_daily_book_step_fails_loudly() -> None:
    """بی‌صدا نه، ولی توقف هم نه: خطا اعلام و فایل خطا ساخته شود."""
    step = _step(DAILY, "بازبینی سبد و موتور خروج")
    assert "|| true" not in step
    assert "::error::" in step
    assert "book-error-" in step


def test_weekly_injects_no_default_regime() -> None:
    text = WEEKLY.read_text(encoding="utf-8")
    assert "'-1.0'" not in text
    assert 'default: "-1.0"' not in text


def test_weekly_input_passes_through_env() -> None:
    """ورودی دستی از راه env برسد، نه با جاگذاری مستقیم در متن فرمان."""
    step = _step(WEEKLY, "بازبینی سبد با نامزدهای چرخش")
    run = step[step.index("run: |"):]
    assert "${{ github.event.inputs.regime" not in run
    assert "github.event.inputs.regime" in step


def test_weekly_book_step_fails_loudly() -> None:
    step = _step(WEEKLY, "بازبینی سبد با نامزدهای چرخش")
    assert "|| true" not in step.split("python radar_book.py")[1]
    assert "::error::" in step
    assert "book-error-" in step
