"""
آزمون رقم فارسی و تله عبارت باقاعده.

دو موضوع جدا ولی هم‌ریشه، هر دو از همان درس رویداد ۲۲:

۱) کمک‌تابع `fa` اول در `radar_state.py` بود. دومین مصرف‌کننده که پیدا
   شد، انتخاب بین کپی محلی و ایمپورت بود. کپی همان «متنی که در دو جا
   نوشته می‌شود» بود، پس `radar_text.py` ساخته شد — فقط کتابخانه
   استاندارد، تا استقلال فایل‌های مستقل نشکند.

۲) در پایتون `\\d` رقم فارسی را هم می‌گیرد و `\\w` حرف فارسی را. گاهی
   همان چیزی است که می‌خواهی، گاهی تله. این آزمون‌ها هر دو سمت را قفل
   می‌کنند: جایی که باید اسکی بماند، و جایی که باید فارسی بگیرد.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_text as T

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════ کمک‌تابع ═══════════════════

def test_fa_converts_digits() -> None:
    assert T.fa("6.1") == "۶.۱"
    assert T.fa(14) == "۱۴"
    assert T.fa("2026-09-15") == "۲۰۲۶-۰۹-۱۵"


def test_fa_leaves_letters_alone_but_converts_every_digit() -> None:
    """
    حرف دست‌نخورده می‌ماند، ولی **هر** رقم تبدیل می‌شود — حتی داخل یک
    شناسه مثل «p1». این رفتار عمدی است و در مستند تابع ثبت شده.
    """
    assert T.fa("رادار") == "رادار"
    assert T.fa("7.0-p1") == "۷.۰-p۱"


def test_en_is_the_inverse() -> None:
    for s in ["6.1", "14", "2026-09-15", "7.0-p1"]:
        assert T.en(T.fa(s)) == s


def test_en_also_handles_arabic_indic_digits() -> None:
    """
    رقم عربی (U+0660) نویسه دیگری است، نه نمایش دیگر رقم فارسی
    (U+06F0). متن رونویسی‌شده خودکار هر دو را می‌دهد.
    """
    assert T.en("٠١٢٣٤٥٦٧٨٩") == "0123456789"
    assert T.en("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert "٤" != "۴"          # واقعاً دو نویسه جدا


def test_fa_accepts_non_string() -> None:
    assert T.fa(5.0) == "۵.۰"
    assert T.fa(0) == "۰"


# ═══════════════════ تنها منبع اصلی ═══════════════════

def test_no_local_copy_of_fa_anywhere() -> None:
    """
    هسته درس: تعریف `fa` فقط یک جا باشد. اگر کسی کپی محلی بگیرد، دیر یا
    زود دو نسخه از هم جدا می‌افتند.
    """
    definers = [p.name for p in ROOT.glob("radar_*.py")
                if re.search(r"^def fa\(", p.read_text(encoding="utf-8"), re.M)]
    assert definers == ["radar_text.py"], definers


def test_no_local_digit_table_copy() -> None:
    """
    جدول ترجمه هم نباید جای دیگری ساخته شود.

    یک نسخه سوم در `radar_intake.py` بود که همین آزمون پیدایش کرد — و
    از مال اولیه کامل‌تر بود، چون رقم عربی را هم پوشش می‌داد. همان به
    منبع اصلی منتقل شد، نه برعکس.
    """
    copies = [p.name for p in ROOT.glob("radar_*.py")
              if "۰۱۲۳۴۵۶۷۸۹" in p.read_text(encoding="utf-8")
              and p.name != "radar_text.py"]
    assert copies == [], copies


def test_intake_digit_map_is_the_shared_one() -> None:
    """نگاشت محلی intake باید همان شیء مشترک باشد، نه کپی."""
    import radar_intake as IN
    assert IN._DIGIT_MAP is T.EN_DIGITS


def test_intake_still_normalizes_both_families() -> None:
    """رفتار پیش از یکی‌سازی نباید عوض شده باشد."""
    import radar_intake as IN
    assert IN.normalize_digits_only("۶۲ هزار") == "62 هزار"
    assert IN.normalize_digits_only("٦٢ ألف") == "62 ألف"


def test_radar_text_needs_only_stdlib() -> None:
    """
    دلیل وجود این پیمانه این بود که هر فایلی بتواند بی‌هزینه ایمپورتش
    کند. اگر روزی وابستگی سنگین بگیرد، آن دلیل از بین می‌رود.
    """
    src = (ROOT / "radar_text.py").read_text(encoding="utf-8")
    for heavy in ("import pandas", "import numpy", "import requests",
                  "import radar_"):
        assert heavy not in src


# ═══════════════════ رقم فارسی در خروجی ═══════════════════

def test_snapshot_freshness_uses_persian_digits() -> None:
    """باگ گزارش‌شده: «5 ساعت» به‌جای «۵ ساعت»."""
    import radar_snapshot as SNAP
    rule = SNAP.freshness_note()[0]
    assert "۵" in rule
    assert not re.search(r"[0-9]", rule)


def test_watch_staleness_uses_persian_digits(tmp_path) -> None:
    """همان الگو در هشدار کهنگی پایش."""
    import json
    import os
    import time
    import radar_watch as W

    p = tmp_path / "watch.json"
    p.write_text(json.dumps({"items": []}), encoding="utf-8")
    old = time.time() - (W.STALE_AFTER_DAYS + 10) * 86_400
    os.utime(p, (old, old))

    warn = W.stale_warning(str(p))
    assert warn is not None
    # نام فایل اسکی است و می‌ماند؛ فقط بخش نثر سنجیده می‌شود
    prose = warn.replace(p.name, "")
    assert not re.search(r"[0-9]", prose), prose


def test_state_version_label_is_persian() -> None:
    import radar_state as ST
    assert f"رادار {T.fa(ST.VERSION)}" in ST.opening_questions()


# ═══════════════════ تله عبارت باقاعده ═══════════════════

def test_python_backslash_d_really_matches_persian() -> None:
    """
    ثبت خود تله، تا کسی فرض نکند `\\d` فقط اسکی است. اگر روزی رفتار
    پایتون عوض شد، این آزمون خبر می‌دهد.
    """
    assert re.search(r"\d", "۵") is not None
    assert re.search(r"\w", "الف") is not None
    assert re.search(r"[0-9]", "۵") is None


def test_ascii_only_patterns_reject_persian_digits() -> None:
    """
    الگوهایی که دامنه ورودی‌شان اسکی است نباید رقم فارسی بگیرند.
    نمونه: خواندن شماره نسخه از متن کد.
    """
    import radar_state as ST
    pat = re.compile(r'VERSION\s*=\s*["\']([0-9.]+)["\']')
    assert pat.search('VERSION = "6.1"').group(1) == "6.1"
    assert pat.search('VERSION = "۶.۱"') is None
    # و خود تابع هم همان را می‌خواند
    assert ST.file_version("radar_state.py") == ST.VERSION


def test_youtube_id_patterns_are_ascii_only() -> None:
    """
    شناسه یوتیوب فقط [A-Za-z0-9_-] است. با `\\w` یک رشته فارسی
    یازده‌نویسه‌ای به‌عنوان شناسه پذیرفته می‌شد.
    """
    import radar_one as ONE
    assert ONE.video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert ONE.video_id("https://youtu.be/ابجدهوزحطیک") == ""
    assert ONE.video_id("ابجدهوزحطیک") == ""


def test_no_ascii_domain_pattern_still_uses_w_or_d() -> None:
    """
    بررسی ایستا: هیچ الگوی شناسه‌ای نباید به `[\\w-]` برگردد.
    """
    for name in ("radar_one.py", "radar_intake.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        assert r"[\w-]" not in src, name


def test_persian_number_detection_is_deliberately_kept() -> None:
    """
    سمت دیگر سکه: در `radar_intake.py` گرفتن رقم فارسی توسط `\\d`
    **عمدی** است. اگر کسی آن را هم «اصلاح» کند، شناسایی عدد در متن
    فارسی تحلیل‌گر می‌شکند. این آزمون جلویش را می‌گیرد.
    """
    import radar_intake as IN
    hits = [p for p in IN._COMPILED_NUMBERS if p.search("۶۲ هزار دلار")]
    assert hits, "الگوی عدد فارسی دیگر تطبیق نمی‌کند"


def test_persian_markers_still_match_in_digest() -> None:
    """همان قاعده در radar_digest.py."""
    import radar_digest as DG
    assert any(p.search("حدود ۵۰ درصد") for p in DG._TESTABLE_RE)
