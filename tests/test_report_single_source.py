"""
آزمون تنها-منبع-اصلی بودن متن گزارش روزانه.

دو باگ که این آزمون‌ها قفلشان می‌کنند، هر دو در گام «ساخت خلاصه امروز»
در `.github/workflows/radar-daily.yml`:

باگ یک — متن پرسش گشایش در سه جا نوشته شده بود: `radar_state.py` در
دو نقطه، و یک heredoc دستی در گردش‌کار. وقتی نسخه از ۶.۰ به ۶.۱ رفت
فقط دو تای اول به‌روز شد و گردش‌کار ماه‌ها «رادار ۶.۰» می‌فرستاد.

باگ دو — گردش‌کار بخش قانون تازگی را با `head -n 6 | tail -n 3` برش
می‌زد، به این فرض که توضیح یک سطر است. سه سطر است: قاعده، نتیجه،
اقدام. پس جمله همیشه درست همان‌جا قطع می‌شد که نتیجه شروع می‌شود.

نکته آزمون: هیچ‌کدام از این آزمون‌ها رشته نسخه را سخت‌نویسی نمی‌کنند.
اگر می‌کردند، خودشان می‌شدند نسخه چهارم همان متن.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_snapshot as SNAP
import radar_state as ST
from radar_text import fa

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "radar-daily.yml"


# ═══════════ باگ یک — پرسش گشایش از ثابت نسخه می‌آید ═══════════

def test_opening_uses_real_version_constant() -> None:
    """
    سرصفحه باید نسخه واقعی را داشته باشد — از روی ثابت ساخته شود،
    نه از رشته سخت‌نویسی‌شده در خود آزمون.
    """
    expected = "رادار " + ST.VERSION.translate(ST.FA_DIGITS)
    assert expected in ST.opening_questions()


def test_opening_has_no_latin_version_digits() -> None:
    """
    شماره نسخه باید با رقم فارسی بیاید، طبق قواعد نگارش پروژه.

    الگو عمداً `[0-9]` است نه `\\d` — در پایتون `\\d` رقم فارسی را هم
    می‌گیرد، چون هر دو در رده یونیکد Nd هستند.
    """
    head = ST.opening_questions().splitlines()[0]
    assert not re.search(r"[0-9]", head)


def test_state_reexports_the_shared_helper() -> None:
    """
    `fa` حالا در `radar_text.py` زندگی می‌کند. `radar_state` همان را
    ایمپورت می‌کند، پس باید **همان شیء** باشد نه کپی.
    """
    assert ST.fa is fa
    assert ST.fa("6.1") == "۶.۱"


def test_opening_has_three_questions_and_the_rule() -> None:
    """محتوای متن نباید در بازآرایی گم شود."""
    t = ST.opening_questions()
    for q in ("۱.", "۲.", "۳."):
        assert q in t
    assert "هیچ کاری" in t


def test_opening_stays_in_sync_when_version_changes(monkeypatch) -> None:
    """
    هسته باگ یک: اگر ثابت نسخه عوض شود، متن باید خودش عوض شود.
    اگر جایی دست‌نویس مانده باشد، این آزمون قرمز می‌شود.
    """
    monkeypatch.setattr(ST, "VERSION", "9.9")
    assert "رادار ۹.۹" in ST.opening_questions()


def test_snapshot_report_uses_the_same_text() -> None:
    """
    تابع snapshot در همین فایل هم باید از همان منبع بخواند، نه نسخه دوم.
    بررسی ایستا: متن دست‌نویس پرسش گشایش نباید در فایل بماند.
    """
    src = (ROOT / "radar_state.py").read_text(encoding="utf-8")
    # سرصفحه فقط یک بار، آن هم داخل خود تابع تنها-منبع
    assert src.count("## پرسش گشایش رادار") == 1


# ═══════════ باگ دو — قانون تازگی سه سطر است ═══════════

def test_freshness_note_has_exactly_three_lines() -> None:
    """سه سطر: قاعده، نتیجه، اقدام."""
    assert len(SNAP.freshness_note()) == 3


def test_freshness_block_contains_all_three_lines() -> None:
    """
    هسته باگ دو: هر سه سطر باید در خروجی باشند. برش قدیمی فقط سطر اول
    را می‌گرفت و جمله را وسط رها می‌کرد.
    """
    out = SNAP.freshness_block()
    for line in SNAP.freshness_note():
        assert line in out


def test_freshness_lines_carry_rule_result_and_action() -> None:
    """هر سه سطر باید محتوای خودشان را داشته باشند، نه فقط تعدادشان درست باشد."""
    rule, result, action = SNAP.freshness_note()
    assert "قانون تازگی" in rule
    assert "داده ندارم" in result          # نتیجه
    assert "پالس تازه" in action           # اقدام


def test_freshness_uses_the_stale_hours_constant() -> None:
    """
    عدد سقف عمر از ثابت می‌آید، نه دست‌نویس — و با رقم فارسی چاپ می‌شود.

    شکل مورد انتظار از خود ثابت ساخته می‌شود، نه سخت‌نویسی. اگر ثابت
    عوض شود، آزمون همراهش عوض می‌شود.
    """
    expected = fa(f"{SNAP.STALE_HOURS:.0f}")
    assert expected in SNAP.freshness_note()[0]


def test_freshness_block_includes_stamp_when_given() -> None:
    """با مهر، عبارت «مهر بالا» مرجع پیدا می‌کند."""
    out = SNAP.freshness_block("2026-09-15 13:30 UTC")
    assert "2026-09-15 13:30 UTC" in out
    assert out.splitlines()[-1] == SNAP.freshness_note()[-1]


def test_freshness_block_without_stamp_is_just_the_note() -> None:
    assert SNAP.freshness_block() == "\n".join(SNAP.freshness_note())


def test_snapshot_body_embeds_the_same_note() -> None:
    """گزارش نبض و خروجی جدا باید از یک منبع بیایند."""
    body, _ = SNAP.build([], {}, [])
    for line in SNAP.freshness_note():
        assert line in body


# ═══════════ گردش‌کار دیگر متن را دوباره نمی‌نویسد ═══════════

def test_workflow_calls_the_scripts_not_a_heredoc() -> None:
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "radar_state.py --opening" in src
    assert "radar_snapshot.py --freshness" in src


def test_workflow_has_no_hardcoded_version_label() -> None:
    """برچسب نسخه نباید در yml دست‌نویس باشد — منشأ باگ یک همین بود."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "پرسش گشایش رادار" not in src


def test_workflow_no_longer_slices_by_line_number() -> None:
    """برش بر پایه شماره سطر ثابت باید رفته باشد — منشأ باگ دو."""
    src = WORKFLOW.read_text(encoding="utf-8")
    assert "head -n 6" not in src
    assert "tail -n 3" not in src
