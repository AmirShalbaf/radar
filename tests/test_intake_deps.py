"""
آزمون وابستگی‌های مسیر جمع‌آوری — نشست ۴، بند ۱ و تصمیم ۵ کاربر، ۲۹ سپتامبر ۲۰۲۶.

پیش از این:
- هر شش کتابخانه اختیاری بود. نبودشان اسکریپت را نمی‌کشت؛ هر منبع یک خط
  «نصب نیست» می‌داد، اجرا با «۰ سند» و کد خروج صفر تمام می‌شد و INDEX با
  تاریخ امروز بازسازی می‌شد. روی لپ‌تاپ هیچ‌کدام نصب نبود — ایستگاه ۱.
- ویسپر بدون ffmpeg «دانلود صدا ناموفق» می‌گفت، نه علت واقعی.
حالا کمبود از همان اول با نام بسته و پیام صریح اجرا را می‌ایستاند.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements-intake.txt"
SIX = {"youtube-transcript-api", "feedparser", "yt-dlp", "faster-whisper",
       "trafilatura", "pyyaml"}


def _req_lines() -> dict[str, str]:
    out = {}
    for line in REQ.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)(.*)", line)
        out[m.group(1).lower()] = m.group(2)
    return out


def _empty_config(tmp_path) -> Path:
    cfg = tmp_path / "analysts.yml"
    cfg.write_text("meta: {}\nsources: {}\n", encoding="utf-8")
    return cfg


def _args(tmp_path, *extra) -> list[str]:
    out = tmp_path / "intake"
    return ["--config", str(_empty_config(tmp_path)), "--out", str(out),
            "--state", str(out / ".state.json"), *extra]


# ═══════════════════ فایل وابستگی ═══════════════════

def test_requirements_intake_lists_the_six_with_floor_and_cap() -> None:
    lines = _req_lines()
    assert set(lines) == SIX
    for name, spec in lines.items():
        assert ">=" in spec and "<" in spec.replace("<=", ""), (name, spec)


def test_requirements_intake_builds_on_runtime_file() -> None:
    """requests از requirements.txt می‌آید — هم‌الگوی requirements-dev.txt."""
    assert "-r requirements.txt" in REQ.read_text(encoding="utf-8")


def test_code_checks_exactly_the_packages_of_the_file() -> None:
    """یک منبع: بسته‌هایی که کد می‌سنجد همان‌هایی‌اند که فایل نصب می‌کند."""
    checked = set(I.REQUIRED.values()) | set(I.WHISPER_ONLY.values())
    assert checked == SIX | {"requests"}


def test_dev_requirements_include_intake() -> None:
    """آزمون‌های intake کتابخانه‌های intake را می‌خواهند."""
    dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements-intake.txt" in dev


# ═══════════════════ ایستادن در آغاز ═══════════════════

def test_missing_library_stops_before_writing(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(I, "_has_module", lambda m: m != "feedparser")
    rc = I.main(_args(tmp_path))
    out = capsys.readouterr().out
    assert rc == 2
    assert "feedparser" in out and "requirements-intake.txt" in out
    assert not (tmp_path / "intake").exists()


def test_missing_library_stops_dry_run_too(tmp_path, monkeypatch, capsys) -> None:
    """اجرای خشک بی‌کتابخانه هم همان «۰ مورد» گمراه‌کننده را می‌داد."""
    monkeypatch.setattr(I, "_has_module", lambda m: m != "yt_dlp")
    assert I.main(_args(tmp_path, "--dry-run")) == 2
    assert "yt-dlp" in capsys.readouterr().out


def test_whisper_library_needed_only_with_whisper(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(I, "_has_module", lambda m: m != "faster_whisper")
    monkeypatch.setattr(I, "_which", lambda name: None)
    # بدون --whisper: از سنجش می‌گذرد و به «هیچ منبع فعالی» می‌رسد
    assert I.main(_args(tmp_path, "--dry-run")) == 1


def test_whisper_without_ffmpeg_stops_at_start(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "_which", lambda name: None)
    assert I.main(_args(tmp_path, "--whisper")) == 2
    assert "ffmpeg نصب نیست" in capsys.readouterr().out


def test_whisper_fallback_names_ffmpeg(monkeypatch) -> None:
    """radar_one و سلول‌های دستی هم ویسپر را مستقیم صدا می‌زنند."""
    monkeypatch.setattr(I, "_which", lambda name: None)
    segs, why = I.whisper_fallback("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert segs == []
    assert "ffmpeg نصب نیست" in why
    assert "دانلود صدا ناموفق" not in why


def test_all_present_passes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(I, "_has_module", lambda m: True)
    monkeypatch.setattr(I, "_which", lambda name: "/usr/bin/ffmpeg")
    assert I.main(_args(tmp_path, "--dry-run", "--whisper")) == 1


# ═══════════════════ سرخط ═══════════════════

def test_header_says_laptop_not_colab() -> None:
    head = I.__doc__
    assert "فقط لپ‌تاپ" in head
    assert "گوگل کولب" not in head      # محیط پیشین؛ فقط «منسوخ» می‌تواند بیاید
    assert "requirements-intake.txt" in head
