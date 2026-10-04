"""
آزمون خلاصه روزانه radar_video.py --daily — نشست ۷ب، کار چهار. بدون شبکه.

intake/reports/DAILY-<تاریخ>.md، ساده و کوتاه:
  - برای هر ویدیوی دیده‌شده: گوینده، ادعاهای عددی، سطح‌ها با حکم snap، «ترجمه یا
    تحلیل؟» برای تکرارگر، و روش تازه اگر بود.
  - برای منابع فقط‌متن: یک خط برای هر سند تازه با قوی‌ترین نامزد ادعا.
  - در پایان: ماند برای فردا و شمار کوتاه‌های ردشده.
  - شبی که جمع‌آوری متن اجرا نشد صریح گفته می‌شود — نه سکوت.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I
import radar_video as V

UTC = timezone.utc
NOW = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)
DAY = "2026-10-04"
SECRET = "full transcript sentence that must stay local"
TK, CW = "tkVIDEO0001", "cwVIDEO0001"

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
  gareth_soloway:
    name_fa: "گرت سالووی"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "UCgggggggggggggggggggggg"
    watch: "crypto_title"
    watch_keywords: [bitcoin]
  raoul_pal:
    name_fa: "رایول پال"
    role: "لنز تحلیل‌گر"
    kind: "youtube"
    channel_id: "UCrrrrrrrrrrrrrrrrrrrrrr"
    watch: "text"
"""


def num(v, conf="high"):
    return {"value": v, "confidence": conf, "from": "image"}


def snap(level, verdict="confirmed", touches=3, strength="weak"):
    s = {"verdict": verdict, "symbol": "BTC", "tf": "1d", "cutoff": "2026-10-03T16:00:00Z",
         "level": level, "chance_pct": 30.0, "class": "structural"}
    if verdict == "confirmed":
        s.update(touches=touches, strength=strength)
    else:
        s.update(nearest=None)
    return s


def write_cards(vid, source, *, screen=None, claims=(), methods=None, doc=""):
    card = {"frame_id": "f", "t": 69.0, "is_chart": True, "coin": num("BTC"), "timeframe": num("1D"),
            "levels": [{"price": num(82000), "kind": "horizontal", "snap": snap(82000)},
                       {"price": num(90000), "kind": "horizontal",
                        "snap": snap(90000, verdict="not_near")}],
            "claims": list(claims), "speech": SECRET}
    if screen:
        card["screen_source"] = screen
    cards = {"video_id": vid, "source": source, "title": f"عنوان {vid}", "doc": doc, "cards": [card]}
    if methods is not None:
        cards["methods"] = methods
    p = Path("intake", "charts", source, f"{vid}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return p


def write_doc(source, fname, title, rows, local_body=None):
    """سند عمومی با جدول نامزد، به قالب build_documents."""
    local_rel = f"{I.LOCAL_DIR}/{source}/{fname}"
    head = ["---", f"منبع: {source}", f"عنوان: {title}", "تاریخ انتشار: 2026-10-03T10:00:00Z",
            f"متن محلی: {local_rel}", "---", "", "## نامزدهای ادعا (خودکار — تأییدنشده)", "",
            "| # | زمان | قدرت | دسته | اعداد | متن |", "|---|---|---|---|---|---|"]
    body = [f"| {i} | 00:{i:02d} | {'★' * s}{'☆' * (5 - s)} | جهت | 1 | {t} |"
            for i, (s, t) in enumerate(rows, 1)]
    p = Path("intake", source, fname)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    if local_body is not None:
        lp = Path("intake", local_rel)
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(local_body, encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    return tmp_path


def put_state(videos=None, runs=None, imports=None):
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps(
        {"schema": 1, "videos": videos or {}, "runs": runs or {}}, ensure_ascii=False), encoding="utf-8")
    Path("intake", ".state.json").write_text(json.dumps(
        {"seen": {}, "imports": imports or []}, ensure_ascii=False), encoding="utf-8")


def daily(extra=()) -> str:
    assert V.main(["--daily", "--config", "analysts.yml", "--intake", "intake", *extra], now=NOW) == 0
    return Path("intake", I.REPORTS_DIR, f"DAILY-{DAY}.md").read_text(encoding="utf-8")


VOICE = "\n".join(["## متن کامل", "", "[00:01] سالووی میگه بیت کوین تا ۸۵ هزار",
                   "[00:04] و به نظر من اتریوم تا آخر هفته به ۲۵۰۰ میرسه"])


def seen_tekrargar():
    doc = write_doc("tekrargar", "2026-10-04_x_tkVIDE.md", "عنوان تکرارگر", [(3, "ادعا")],
                    local_body=VOICE)
    write_cards(TK, "tekrargar", doc=doc.as_posix(),
                screen={"kind": "tweet", "who": "@TedPillows", "evidence": "واترمارک"},
                claims=["BTC — صعود — بالای 85,000 — تا پایان اکتبر — نقل از سالووی",
                        "بازار هیجانی است — بی‌عدد"],
                methods=[{"area": "ورود", "rule": "شکست با بسته روزانه", "where": "01:09",
                          "library": "تازه"},
                         {"area": "ورود", "rule": "فقط در جهت روند", "where": "02:00", "library": "ر۱"}])
    return {"source": "tekrargar", "title": f"عنوان {TK}", "status": "seen", "suggested": True,
            "seen_at": f"{DAY}T12:00:00Z", "report": f"intake/reports/tekrargar/{TK}.md",
            "cards": f"intake/charts/tekrargar/{TK}.json"}


def test_seen_video_section(env) -> None:
    put_state(videos={TK: seen_tekrargar()})
    rep = daily()
    assert rep.startswith(f"# خلاصه روزانه رصد — {DAY}")
    assert "تکرارگر — حمیدرضا برزگر" in rep and V.SUGGEST_LABEL in rep
    assert "BTC — صعود — بالای 85,000 — تا پایان اکتبر — نقل از سالووی" in rep
    assert "بازار هیجانی است" not in rep and "ادعای بی‌عدد: 1" in rep
    assert "واقعی با 3 برخورد — ضعیف" in rep
    assert "سطح دیگر — خط دلخواه یا بی‌داده: 1" in rep               # خلاصه کوتاه است
    assert "## ترجمه یا تحلیل؟" in rep or "ترجمه یا تحلیل؟" in rep
    assert "«فلانی می‌گوید / میگه»: 1" in rep and "«به نظر من»: 1" in rep
    assert "توییت یا پست: 1" in rep
    assert "شکست با بسته روزانه" in rep and "فقط در جهت روند" not in rep    # فقط روش تازه
    assert f"intake/reports/tekrargar/{TK}.md" in rep
    assert SECRET not in rep


def test_level_table_lists_only_confirmed_and_counts_the_rest(env) -> None:
    """
    اجرای واقعی ۴ اکتبر: جدول سطح کریپتوسیتی ۴۵ ردیف شد — خلاصه «ساده و کوتاه» نبود.
    فقط سطحی که در یکی از دو ستون «واقعی» است ردیف می‌گیرد؛ بقیه یک خط شمارش، و جدول
    کامل در گزارش ویدیو.
    """
    p = write_cards(CW, "benjamin_cowen")
    cards = json.loads(p.read_text(encoding="utf-8"))
    lv = cards["cards"][0]["levels"]
    # برچسب خط دلخواه با نزدیک‌ترین سطح «… دامنه واقعی دورتر» دارد — تله واژه «واقعی»،
    # پیداشده در خلاصه واقعی ۴ اکتبر
    lv[1]["snap"].update(nearest=91000.0, nearest_touches=3, distance_atr=0.5)
    lv.append({"price": num(70000), "kind": "horizontal", "snap": {**snap(70000, verdict="not_near"),
                                                                     "daily": snap(70000)}})
    lv.append({"price": num(60000), "kind": "horizontal",
               "snap": {"verdict": "no_data", "symbol": "BTC", "tf": "1d", "cutoff": "c", "level": 60000,
                        "reason": "داده کم"}})
    p.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    put_state(videos={CW: {"source": "benjamin_cowen", "title": "t", "status": "seen",
                           "seen_at": f"{DAY}T10:00:00Z", "report": "intake/reports/benjamin_cowen/x.md"}})
    rep = daily()
    assert "| 82,000 |" in rep                         # واقعی روی تایم خود نمودار
    assert "| 70,000 |" in rep                         # واقعی فقط در ستون روزانه
    assert "| 90,000 |" not in rep and "| 60,000 |" not in rep
    assert "سطح دیگر — خط دلخواه یا بی‌داده: 2 — جدول کامل در گزارش ویدیو" in rep


def test_translation_section_only_for_tekrargar(env) -> None:
    write_cards(CW, "benjamin_cowen", claims=["BTC — نزول — زیر 60,000 — بی‌مهلت"])
    put_state(videos={CW: {"source": "benjamin_cowen", "title": "t", "status": "seen",
                           "seen_at": f"{DAY}T10:00:00Z"}})
    rep = daily()
    assert "بنجامین کوون" in rep and "ترجمه یا تحلیل؟" not in rep
    assert "روش تازه‌ای ثبت نشد" in rep


def test_seen_on_another_day_is_not_listed(env) -> None:
    write_cards(CW, "benjamin_cowen")
    put_state(videos={CW: {"source": "benjamin_cowen", "title": "t", "status": "seen",
                           "seen_at": "2026-10-03T10:00:00Z"}})
    assert CW not in daily()


def test_text_only_docs_one_line_with_strongest_candidate(env) -> None:
    rp = write_doc("raoul_pal", "2026-10-03_macro_rpVIDE.md", "Macro Summer",
                   [(2, "ضعیف‌تر"), (4, "BTC to 150k by Q2"), (4, "دومی هم‌قدرت")])
    tk = write_doc("tekrargar", "2026-10-03_t_tkOTHE.md", "ویدیوی تکرارگر", [(5, "دیده‌شدنی")])
    gs_off = write_doc("gareth_soloway", "2026-10-03_g_gsOFFF.md", "Gold Rally", [(3, "gold 3000")])
    gs_on = write_doc("gareth_soloway", "2026-10-03_b_gsONNN.md", "Bitcoin Now", [(3, "btc 90k")])
    docs = [p.relative_to("intake").as_posix() for p in (rp, tk, gs_off, gs_on)]
    put_state(imports=[{"at": f"{DAY}T05:00:00Z", "stamp": "20261003T223000Z",
                        "started": "2026-10-03 22:30 UTC", "exit_code": 0, "docs": docs, "failures": []}])
    rep = daily()
    assert "Macro Summer" in rep and "BTC to 150k by Q2" in rep and "ضعیف‌تر" not in rep
    assert "Gold Rally" in rep and "gold 3000" in rep          # سالووی غیرکریپتویی فقط متن است
    assert "دیده‌شدنی" not in rep and "btc 90k" not in rep     # دیدن کامل، نه فقط متن
    assert "کد خروج 0" in rep and "2026-10-03 22:30 UTC" in rep


def test_no_nightly_run_is_explicit(env) -> None:
    put_state()
    assert "اجرای شبانه ثبت نشد" in daily()


def test_nightly_failure_is_shown(env) -> None:
    put_state(imports=[{"at": f"{DAY}T05:00:00Z", "stamp": "s", "started": "2026-10-03 22:30 UTC",
                        "exit_code": 3, "docs": [],
                        "failures": ["تکرارگر (`tekrargar`) — یوتیوب مسدود کرد"]}])
    rep = daily()
    assert "کد خروج 3" in rep and "یوتیوب مسدود کرد" in rep


def test_end_lists_deferred_and_short_count(env) -> None:
    later = "laterPICKED"
    runs = {DAY: [
        {"deferred": [{"video_id": "deferVID001", "source": "tekrargar", "title": "فردا",
                       "published": "2026-10-03T10:00:00Z", "suggested": False},
                      {"video_id": later, "source": "tekrargar", "title": "بعد دیده شد",
                       "published": "2026-10-03T10:00:00Z", "suggested": False}],
         "short": ["short000001", "short000002"], "stale": [], "off_topic": [], "failed": [],
         "feed_failures": [], "picked": []},
        {"deferred": [], "short": ["short000002"], "stale": [], "off_topic": [], "failed": [],
         "feed_failures": [], "picked": [later]}]}
    put_state(videos={later: {"status": "ready", "source": "tekrargar", "picked_at": f"{DAY}T19:00:00Z"}},
              runs=runs)
    rep = daily()
    end = rep.split("## پایان روز", 1)[1]
    assert "deferVID001" in end and later not in end.split("### ماند برای فردا", 1)[1].split("###")[0]
    assert "کوتاه ردشده — ف۸: 2" in end


def test_ready_unread_is_listed(env) -> None:
    put_state(videos={"readyVID001": {"status": "ready", "source": "tekrargar", "title": "منتظر",
                                      "cards": "intake/charts/tekrargar/readyVID001.json"}})
    rep = daily()
    assert "آماده، هنوز خوانده نشده" in rep and "readyVID001" in rep


def test_channel_candidate_with_school_table_reminder(env) -> None:
    cid = "UC" + "q" * 22
    vids = {f"q{i}_________": {"source": V.SINGLE_PREFIX + cid, "channel_id": cid, "channel": "Quant Q",
                               "suggested": True, "status": "seen"} for i in range(3)}
    put_state(videos=vids)
    rep = daily()
    assert "نامزد فهرست رصد" in rep and "Quant Q" in rep and "جدول مکاتب" in rep


def test_cli_rebuild_is_said_not_silent(env, capsys) -> None:
    put_state()
    daily(["--date", DAY])
    assert "DAILY-2026-10-04.md" in capsys.readouterr().out
    daily()
    assert "بازسازی" in capsys.readouterr().out


def test_daily_is_not_a_document_in_index(env) -> None:
    put_state()
    daily()
    I.rebuild_index(Path("intake"))
    assert "DAILY" not in Path("intake", "INDEX.md").read_text(encoding="utf-8")


def test_bad_date_is_rejected(env) -> None:
    put_state()
    with pytest.raises(SystemExit):
        V.main(["--daily", "--date", "۲۰۲۶-۱۰-۰۴", "--intake", "intake"], now=NOW)
