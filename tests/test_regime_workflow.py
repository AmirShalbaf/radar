"""
آزمون متن گردش‌کارها برای رژیم — نشست ۲ نقشه رادار ۷، مورد م۵.

- گردش‌کار روزانه گام «ساخت رژیم» را **پیش از** گام سبد اجرا می‌کند، تا
  سبد رژیم امروز را بخواند.
- خطای ساخت با ::error:: و فایل خطا اعلام می‌شود ولی گام‌های بعد متوقف
  نمی‌شوند. بدون `|| true`. رفتار فایل در خطا کار خود radar_regime.py
  است (tests/test_regime_failure.py).
- regime.json و regime_history.json در گام کامیت، در خط git add جدا از
  گزارش‌ها، بدون `|| true`. فایل غایب اعلام می‌شود، نه بلعیده.
- گردش‌کار هفتگی رژیم نمی‌سازد؛ فقط از همان فایل می‌خواند.

الگو: tests/test_report_single_source.py — متن فایل خوانده می‌شود.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "radar-daily.yml"
WEEKLY = ROOT / ".github" / "workflows" / "radar-weekly.yml"
REGIME_STEP = "ساخت رژیم"
BOOK_STEP = "بازبینی سبد و موتور خروج"
COMMIT_STEP = "کامیت گزارش‌ها"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _step(p: Path, name: str) -> str:
    """متن یک گام، از سطر نام تا گام بعد."""
    text = _text(p)
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


def test_daily_has_regime_step_before_book_step() -> None:
    text = _text(DAILY)
    assert f"- name: {REGIME_STEP}\n" in text
    assert text.index(f"- name: {REGIME_STEP}\n") < text.index(f"- name: {BOOK_STEP}\n")


def test_regime_step_runs_after_reports_dir_exists() -> None:
    text = _text(DAILY)
    assert text.index("- name: ساخت پوشه گزارش") < text.index(f"- name: {REGIME_STEP}\n")


def test_regime_step_fails_loudly_but_does_not_stop() -> None:
    step = _step(DAILY, REGIME_STEP)
    assert "python radar_regime.py" in step
    assert "::error::" in step
    assert "regime-error-" in step
    assert "|| true" not in step
    # شکست در شاخه if گرفته می‌شود، پس گام خودش متوقف‌کننده نیست
    assert "if python radar_regime.py" in step or "if ! python radar_regime.py" in step


def test_regime_step_writes_dated_report() -> None:
    assert 'reports/regime-$D.md' in _step(DAILY, REGIME_STEP)


def test_book_step_still_reads_file_not_flag() -> None:
    assert "--regime" not in _step(DAILY, BOOK_STEP)


def test_commit_step_adds_regime_files_separately() -> None:
    step = _step(DAILY, COMMIT_STEP)
    lines = step.splitlines()
    report_line = next(l for l in lines if "git add reports/" in l)
    assert "regime" not in report_line
    regime_lines = [l for l in lines if "regime.json" in l or "regime_history.json" in l]
    assert regime_lines, "regime.json در گام کامیت اضافه نشده"
    assert any("regime.json" in l for l in regime_lines)
    assert any("regime_history.json" in l for l in regime_lines)
    for l in regime_lines:
        assert "|| true" not in l
    assert 'git add "$f"' in step
    assert "::warning::" in step


def test_weekly_does_not_build_regime() -> None:
    text = _text(WEEKLY)
    assert "radar_regime.py" not in text
    assert "--regime-file" not in text
