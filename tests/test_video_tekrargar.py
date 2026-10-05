"""
گزارش تکرارگر — تصمیم کاربر ۴ اکتبر ۲۰۲۶، کار ویژه ۵ اکتبر. بدون شبکه.

برای منبع tekrargar، در گزارش ویدیو و خلاصه روزانه:
  - «نکته‌های آموزشی» با زمان ویدیو — فهرست اختیاری lessons در سند کارت.
  - هر ادعای نقل‌شده با «منبع اصلی»: نام گوینده اصلی؛ ادعا به نام او ثبت می‌شود، نه
    تکرارگر. ادعای نقل‌شده شیء {text, origin, url} است؛ ادعای خود گوینده همان متن ساده.
  - ویدیوی اصلی‌ای که در یک روز دست‌کم دو بار نقل شد، نشانی‌اش در خلاصه روزانه می‌آید.
ارزش تکرارگر خلاصه و آموزش است، نه رأی مستقل — analysts.yml.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_frames as F
import radar_intake as I
import radar_video as V

UTC = timezone.utc
NOW = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
DAY = "2026-10-04"
SOLO = "https://youtu.be/SOLOWAY0001"

CONFIG = """sources:
  tekrargar:
    name_fa: "تکرارگر — حمیدرضا برزگر"
    role: "دفتر ادعاها"
    kind: "youtube"
    channel_id: "UCtttttttttttttttttttttt"
    watch: "full"
  benjamin_cowen:
    name_fa: "بنجامین کوون"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "UCbbbbbbbbbbbbbbbbbbbbbb"
    watch: "full"
"""


def quoted(text, origin="گرت سالووی", url=SOLO):
    return {"text": text, "origin": origin, "url": url}


def card(t, claims, fid=None):
    return {"frame_id": fid or f"v_{int(t)}", "t": t, "refs": [], "is_chart": False, "texts": [],
            "speech": "", "method_notes": [], "claims": claims}


def cards_doc(vid, source="tekrargar", claims_by_card=(), lessons=None):
    cs = [card(30.0 * (i + 1), cl, f"{vid}_{i}") for i, cl in enumerate(claims_by_card)]
    d = {"schema": 1, "video_id": vid, "doc_id": "d", "source": source, "title": f"عنوان {vid}", "cards": cs}
    if lessons is not None:
        d["lessons"] = lessons
    return d


LESSONS = [{"at": "04:30", "text": "داده اشتغال را با اجماع بسنج، نه با عدد خام"},
           {"at": "12:09", "text": "خط روند تا وقتی معتبر است که بسته روزانه زیرش نرود"}]


# ═══════════════ ۱ — قالب کارت ═══════════════

def test_claim_may_be_quoted_object_with_origin():
    c = card(10.0, ["BTC — بالای 85,000 — بی‌مهلت — خود او", quoted("طلا — زیر خط روند — بی‌مهلت")])
    assert F.validate_card(c) == []


@pytest.mark.parametrize("bad", [
    {"text": "ادعا"},                                            # گوینده اصلی نیست
    {"text": "ادعا", "origin": "  "},
    {"text": "ادعا", "origin": "سالووی", "url": 5},
    {"text": "ادعا", "origin": "سالووی", "url": None, "extra": "x"},
    {"text": "x" * (F.TEXT_MAX + 1), "origin": "سالووی", "url": None},
    {"origin": "سالووی", "url": None},
])
def test_bad_quoted_claim_is_rejected(bad):
    assert any("claims" in e for e in F.validate_card(card(10.0, [bad])))


def test_lessons_are_validated():
    assert V.validate_lessons(cards_doc("a", lessons=LESSONS)) == []
    assert V.validate_lessons(cards_doc("a")) == []                  # اختیاری
    for bad in ([{"at": "4.30", "text": "x"}], [{"at": "04:30"}], [{"at": "04:30", "text": ""}],
                [{"at": "04:30", "text": "x" * (F.TEXT_MAX + 1)}], {"at": "04:30", "text": "x"},
                [{"at": "۰۴:۳۰", "text": "x"}]):
        assert V.validate_lessons(cards_doc("a", lessons=bad)), bad


# ═══════════════ ۲ — گزارش ویدیو ═══════════════

def tk_report():
    doc = cards_doc("tk1", claims_by_card=[
        [quoted("USOIL — بازگشت تا حدود 78 دلار — حدود یک ماه")],
        [quoted("طلا — اگر خط روند حمایت کند، ادامه صعود — بی‌مهلت")],
        ["BTC — تا حدود 89,000 روی خط روند — بی‌مهلت — خود او"]], lessons=LESSONS)
    return V.render_report(doc, {})


def test_tekrargar_report_has_lessons_with_video_time():
    md = tk_report()
    sec = md.split("## نکته‌های آموزشی")[1].split("\n## ")[0]
    assert "- 04:30 — داده اشتغال را با اجماع بسنج" in sec and "- 12:09 —" in sec


def test_tekrargar_report_names_the_original_speaker_of_each_quoted_claim():
    md = tk_report()
    sec = md.split("## منبع اصلی ادعاهای نقل‌شده")[1].split("\n## ")[0]
    assert "نقل‌شده: 2 از 3 ادعا" in sec
    assert "| 00:30 | گرت سالووی |" in sec and SOLO in sec
    assert "| 01:30 |" not in sec                                   # ادعای خود او منبع اصلی ندارد
    claims = md.split("## ادعاها")[1].split("\n## ")[0]
    assert "گوینده اصلی: گرت سالووی" in claims                     # به نام گوینده اصلی، نه تکرارگر


def test_tekrargar_report_says_when_nothing_recorded():
    md = V.render_report(cards_doc("tk2", claims_by_card=[["BTC — بالای 90,000 — بی‌مهلت"]]), {})
    assert "## نکته‌های آموزشی" in md and "سند کارت فهرست `lessons` ندارد" in md
    assert "هیچ ادعای نقل‌شده‌ای با گوینده اصلی ثبت نشد" in md


def test_other_sources_get_no_tekrargar_sections():
    md = V.render_report(cards_doc("cw1", source="benjamin_cowen", claims_by_card=[["BTC — بالای 90,000"]],
                                   lessons=LESSONS), {})
    assert "## نکته‌های آموزشی" not in md and "## منبع اصلی" not in md


def test_report_cli_rejects_bad_lessons(env):
    doc = cards_doc("tk3", claims_by_card=[["BTC — بالای 90,000"]], lessons=[{"at": "x", "text": "y"}])
    p = Path("intake/charts/tekrargar/tk3.json")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert V.main(["--report", p.as_posix(), "--intake", "intake", "--frames", "frames"]) == 2


# ═══════════════ ۳ — خلاصه روزانه ═══════════════

@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    return tmp_path


def write(doc):
    p = Path("intake", "charts", doc["source"], f"{doc['video_id']}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return {"source": doc["source"], "title": doc["title"], "status": "seen", "seen_at": f"{DAY}T12:00:00Z",
            "cards": p.as_posix(), "report": f"intake/reports/{doc['source']}/{doc['video_id']}.md"}


def daily(videos):
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps(
        {"schema": 1, "videos": videos, "runs": {}}, ensure_ascii=False), encoding="utf-8")
    Path("intake", ".state.json").write_text(json.dumps({"seen": {}, "imports": []}), encoding="utf-8")
    assert V.main(["--daily", "--config", "analysts.yml", "--intake", "intake"], now=NOW) == 0
    return Path("intake", I.REPORTS_DIR, f"DAILY-{DAY}.md").read_text(encoding="utf-8")


def test_daily_registers_quoted_claims_under_the_original_speaker(env):
    a = cards_doc("tkA", claims_by_card=[[quoted("USOIL — تا حدود 78 دلار — حدود یک ماه")],
                                         ["BTC — تا حدود 89,000 — بی‌مهلت"]], lessons=LESSONS)
    rep = daily({"tkA": write(a)})
    block = rep.split("### 1.")[1]
    assert "گرت سالووی — نقل تکرارگر — USOIL — تا حدود 78 دلار" in block
    assert "تکرارگر — BTC — تا حدود 89,000" in block
    assert "**نکته‌های آموزشی:**" in block and "- 04:30 — داده اشتغال" in block
    assert "**منبع اصلی:**" in block and "- گرت سالووی — 1 ادعا" in block


def test_daily_shows_original_video_link_only_when_quoted_twice(env):
    a = cards_doc("tkA", claims_by_card=[[quoted("USOIL — تا حدود 78 دلار — حدود یک ماه")],
                                         [quoted("XRP — بالای 1.55 — بی‌مهلت", origin="@cryptorover",
                                                 url="https://x.com/cryptorover/status/1")]])
    b = cards_doc("tkB", claims_by_card=[[quoted("طلا — بالای 2,400 — بی‌مهلت")]])
    rep = daily({"tkA": write(a), "tkB": write(b)})
    assert rep.count(SOLO) >= 1 and "2 بار نقل شد" in rep
    assert "https://x.com/cryptorover/status/1" not in rep          # یک بار نقل — نشانی نمی‌آید


def test_daily_for_other_sources_is_unchanged(env):
    c = cards_doc("cwA", source="benjamin_cowen", claims_by_card=[["BTC — نزول — زیر 60,000 — بی‌مهلت"]])
    rep = daily({"cwA": write(c)})
    assert "- 00:30 — BTC — نزول — زیر 60,000 — بی‌مهلت" in rep
    assert "نکته‌های آموزشی" not in rep and "منبع اصلی" not in rep
