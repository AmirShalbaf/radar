"""
آزمون هدف یادگیری روال ویدیو — تصمیم کاربر، ۸ اکتبر ۲۰۲۶. بدون شبکه.

کاربر ویدیو را بیشتر برای یادگیری رادار برمی‌گزیند، نه برای خلاصه؛ خودش می‌تواند
ویدیو را ببیند. پس گزارش هر ویدیوی دیده‌شده سه بخش ثابت دارد، پیش از جزئیات خوانش:
  - «رادار چه یاد گرفت»: روش در method-library.md، ابزار یا نمودار در
    references/chart-tools.md، نکته خواندن در references/chart-reading.md. هر کدام
    باید در فایلش با نام و شناسه ویدیو آمده باشد؛ وگرنه گزارش ساخته نمی‌شود — گزارشی
    که می‌گوید «یاد گرفت» و فایل خالی است، دروغ می‌گوید.
  - «ادعاها»، همان امروز، برای کارنامه نشست ۵.
  - «درس برای امیر»: ۳ تا ۵ خط ساده.
کارت پیش از ۸ اکتبر این دو میدان را ندارد: گزارش صریح می‌گوید «ثبت نشده»، نه خالی.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I
import radar_video as V
from test_video import VID, report_cards

LEARNED = [
    {"kind": "method", "name": "ر۹۹", "new": True, "note": "خوشه نقدینگی بالای قیمت هدف حرکت است"},
    {"kind": "tool", "name": "نقشه حرارتی لیکوئیدیشن", "new": False, "note": "آستانه نقدینگی را پایین آورد"},
    {"kind": "reading", "name": "د۹۹", "new": True, "note": "رنگ نقشه نسبی است، عدد از راهنمای نشانگر"},
]
LESSON = ["نقشه لیکوئیدیشن جای بسته‌شدن اهرم‌ها را نشان می‌دهد.",
          "کنار سطح روزانه به کار می‌آید، برای هدف کوتاه‌مدت.",
          "احتیاط: نقشه برآورد مدل است، نه سفارش واقعی."]


def learned_cards() -> dict:
    cards = report_cards()
    cards["learned"] = [dict(x) for x in LEARNED]
    cards["amir_lesson"] = list(LESSON)
    return cards


def section(md: str, head: str) -> str:
    return md.split(head, 1)[1].split("\n## ", 1)[0]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "intake").mkdir()
    return tmp_path


def write_cards(cards: dict) -> Path:
    p = Path("intake/charts/single_UCx") / f"{VID}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return p


def write_learning_files(vid: str = VID) -> None:
    Path("references").mkdir(exist_ok=True)
    Path("method-library.md").write_text(f"| ر۹۹ | قاعده | https://youtu.be/{vid} | آزمون‌نشده |\n",
                                          encoding="utf-8")
    Path("references/chart-tools.md").write_text(f"### نقشه حرارتی لیکوئیدیشن\n\nشاهد: `{vid}`\n",
                                                  encoding="utf-8")
    Path("references/chart-reading.md").write_text(f"### د۹۹ — رنگ نسبی\n\nمنبع: `{vid}`\n",
                                                    encoding="utf-8")


def run_report(p: Path) -> int:
    return V.main(["--report", p.as_posix(), "--intake", "intake", "--frames", "frames"])


def report_text() -> Path:
    return Path("intake", I.REPORTS_DIR, "single_UCx", f"{VID}.md")


# ═══════════════ سه بخش ثابت، اول گزارش ═══════════════

def test_report_opens_with_three_fixed_sections() -> None:
    md = V.render_report(learned_cards(), {})
    heads = [line for line in md.splitlines() if line.startswith("## ")]
    assert heads[:3] == [V.LEARNED_HEAD, V.CLAIMS_HEAD, V.LESSON_HEAD]
    assert V.LEARNED_HEAD == "## رادار چه یاد گرفت"
    assert V.CLAIMS_HEAD == "## ادعاها — به بیان ما، نه نقل"
    assert V.LESSON_HEAD == "## درس برای امیر"
    assert md.index(V.LESSON_HEAD) < md.index("## نمودارها")          # جزئیات خوانش پس از سه بخش

    learned = section(md, V.LEARNED_HEAD)
    assert "| روش | ر۹۹ | تازه — آزمون‌نشده | `method-library.md` |" in learned
    assert "| ابزار یا نمودار | نقشه حرارتی لیکوئیدیشن | شاهد تازه | `references/chart-tools.md` |" in learned
    assert "| نکته خواندن نمودار | د۹۹ | تازه | `references/chart-reading.md` |" in learned
    assert "تازه: 2 از 3" in learned

    claims = section(md, V.CLAIMS_HEAD)
    assert "| 01:09 | BTC | 5 | لانگ پس از بسته هفتگی بالای 82,111 — به گفته او |" in claims

    lesson = section(md, V.LESSON_HEAD)
    assert [line for line in lesson.splitlines() if line.startswith("- ")] == [f"- {x}" for x in LESSON]


def test_old_card_keeps_the_sections_and_says_not_recorded() -> None:
    md = V.render_report(report_cards(), {})
    assert "کارت میدان `learned` ندارد" in section(md, V.LEARNED_HEAD)
    assert "کارت میدان `amir_lesson` ندارد" in section(md, V.LESSON_HEAD)


def test_empty_learned_says_nothing_new() -> None:
    cards = learned_cards()
    cards["learned"] = []
    assert "هیچ —" in section(V.render_report(cards, {}), V.LEARNED_HEAD)


# ═══════════════ اعتبارسنجی میدان‌ها ═══════════════

@pytest.mark.parametrize("field,bad", [
    ("learned", "یک رشته"),
    ("learned", [{"kind": "method", "name": "ر۱", "new": True}]),                         # note نیست
    ("learned", [{"kind": "idea", "name": "ر۱", "new": True, "note": "x"}]),              # نوع ناشناخته
    ("learned", [{"kind": "method", "name": "ر۱", "new": "بله", "note": "x"}]),           # new بولی نیست
    ("learned", [{"kind": "method", "name": " ", "new": True, "note": "x"}]),              # نام خالی
    ("learned", [{"kind": "method", "name": "ر۱", "new": True, "note": "x" * 201}]),
    ("amir_lesson", ["یک", "دو"]),                                                         # کمتر از ۳
    ("amir_lesson", ["۱", "۲", "۳", "۴", "۵", "۶"]),                                       # بیش از ۵
    ("amir_lesson", ["یک", "دو", ""]),
    ("amir_lesson", ["یک", "دو", "x" * 201]),
    ("amir_lesson", "یک خط"),
])
def test_learning_fields_are_validated(field, bad) -> None:
    cards = learned_cards()
    cards[field] = bad
    assert any(field in e for e in V.validate_learned(cards))
    assert V.validate_learned(learned_cards()) == []
    assert V.validate_learned(report_cards()) == []                       # کارت پیش از ۸ اکتبر


# ═══════════════ یادگرفته باید در فایلش نوشته شده باشد ═══════════════

def test_report_cli_refuses_learning_not_written_in_its_file(env, capsys) -> None:
    p = write_cards(learned_cards())
    assert run_report(p) == 2
    err = capsys.readouterr().err
    assert "method-library.md" in err and "references/chart-tools.md" in err
    assert not report_text().exists()
    assert not Path("intake", V.VIDEO_STATE_NAME).exists()               # «دیده‌شده» هم نشد

    write_learning_files(vid="otherVID123")                              # نام هست، شناسه این ویدیو نه
    assert run_report(p) == 2
    assert "د۹۹" in capsys.readouterr().err

    write_learning_files()
    assert run_report(p) == 0
    md = report_text().read_text(encoding="utf-8")
    assert md.index(V.LEARNED_HEAD) < md.index(V.CLAIMS_HEAD) < md.index(V.LESSON_HEAD)


def test_report_cli_warns_when_card_has_no_learning(env, capsys) -> None:
    assert run_report(write_cards(report_cards())) == 0
    out = capsys.readouterr().out
    assert "⚠️" in out and "learned" in out and "amir_lesson" in out


# ═══════════════ خلاصه روزانه ═══════════════

def test_daily_block_shows_learning_and_lesson(env) -> None:
    p = write_cards(learned_cards())
    lines = V._video_block(1, VID, {"source": "single_UCx", "cards": p.as_posix()}, {}, Path("intake"))
    text = "\n".join(lines)
    learned = text.split("**رادار چه یاد گرفت:**")[1].split("**درس برای امیر:**")[0]
    assert "- روش ر۹۹ — تازه — آزمون‌نشده — `method-library.md`" in learned
    assert "- ابزار یا نمودار نقشه حرارتی لیکوئیدیشن — شاهد تازه — `references/chart-tools.md`" in learned
    lesson = text.split("**درس برای امیر:**")[1]
    assert [line for line in lesson.splitlines() if line.startswith("- ")] == [f"- {x}" for x in LESSON]


def test_daily_block_of_old_card_says_not_recorded(env) -> None:
    p = write_cards(report_cards())
    text = "\n".join(V._video_block(1, VID, {"source": "single_UCx", "cards": p.as_posix()}, {},
                                    Path("intake")))
    assert "**رادار چه یاد گرفت:**\n\n- ثبت نشده." in text
    assert "**درس برای امیر:**\n\n- ثبت نشده." in text
