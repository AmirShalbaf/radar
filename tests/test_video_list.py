"""
آزمون «اول فهرست» radar_video.py --list و --pick — تصمیم کاربر، ۸ اکتبر ۲۰۲۶. بدون شبکه.

دیدن کامل توکن زیادی می‌سوزاند و کاربر بعضی ویدیوها را خودش دیده و کم‌محتوا یافته.
پس هیچ ویدیویی بدون انتخاب کاربر کامل دیده نمی‌شود:
  - --list فقط فهرست است: نه دانلود، نه فریم، نه متن کامل، نه نوشتن وضعیت؛ فقط
    فراداده برای مدت. همان قواعد --new — میدان watch، کهنگی ۷ روز، صف پیشنهاد —
    ولی بی‌سقف: همه نامزدها، شماره‌دار. پیشنهادهای صف جدا.
  - --pick فقط شماره‌های انتخاب‌شده را کامل می‌بیند، یکی‌یکی. بقیه «رد به انتخاب
    کاربر» می‌شوند تا فردا دوباره نیایند — و در هیچ آماری «دیده‌شده» شمرده نمی‌شوند.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_intake as I
import radar_video as V
from test_video_new import World, suggest_file

UTC = timezone.utc
NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
DAY = "2026-10-08"
ARGS = ["--config", "analysts.yml", "--intake", "intake", "--frames", "frames"]
SKIP_FA = "رد به انتخاب کاربر"


def ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("شبکه واقعی در آزمون صدا زده شد")
    monkeypatch.setattr(V.YtMeta, "_info", boom)
    monkeypatch.setattr(I, "fetch_youtube_items", boom)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from test_video_new import CONFIG
    monkeypatch.chdir(tmp_path)
    (tmp_path / "analysts.yml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "intake").mkdir()
    return tmp_path


def run_list(w: World, now: datetime = NOW) -> int:
    return V.main(["--list", *ARGS], deps=w.deps(), now=now)


def run_pick(w: World, picks: str, now: datetime = NOW) -> int:
    return V.main(["--pick", picks, *ARGS], deps=w.deps(), now=now)


def listed() -> list[dict]:
    return json.loads(V.list_path(Path("intake")).read_text(encoding="utf-8"))["items"]


def number_of(v: str) -> int:
    return next(it["n"] for it in listed() if it["video_id"] == v)


def videos() -> dict:
    p = Path("intake", V.VIDEO_STATE_NAME)
    return json.loads(p.read_text(encoding="utf-8"))["videos"] if p.exists() else {}


def no_feed(w: World) -> None:
    """--pick از فهرست ذخیره‌شده کار می‌کند؛ خوراک را دوباره نمی‌خواند."""
    def boom(src):
        raise AssertionError(f"--pick خوراک {src.key} را خواند")
    w.feed = boom


# ═══════════════ --list فقط فهرست است ═══════════════

def test_list_takes_nothing_and_marks_nothing(env) -> None:
    w = World()
    for s in ("cryptocity_pro", "tekrargar", "benjamin_cowen"):
        w.add(s, s[:2], ago(1))
    q = w.add(None, "q1", ago(2))
    qf = suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    assert w.frames == [] and w.transcripts == []              # نه فریم، نه متن کامل
    assert not Path("intake", V.VIDEO_STATE_NAME).exists()     # هیچ‌چیز «دیده‌شده» نشد
    assert not Path("intake", ".state.json").exists()
    assert not list(Path("intake").rglob("*.md"))              # سندی ساخته نشد
    assert qf.exists()                                         # صف دست نخورد
    assert V.list_path(Path("intake")).parent == Path("intake", I.LOCAL_DIR)   # فهرست محلی


def test_list_shows_every_candidate_without_cap(env, capsys) -> None:
    w = World()
    made = [w.add(s, f"{s[:2]}{i}", ago(i + j + 1)) for j, s in
            enumerate(["cryptocity_pro", "tekrargar", "benjamin_cowen"]) for i in range(3)]
    q = w.add(None, "q1", ago(2))
    suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    out = capsys.readouterr().out
    for v in made + [q]:
        assert f"https://www.youtube.com/watch?v={v}" in out
    assert sorted(it["n"] for it in listed()) == list(range(1, 11))     # سقف ۳ نیست


def test_list_row_has_analyst_title_tehran_time_duration_link(env, capsys) -> None:
    w = World()
    a = w.add("benjamin_cowen", "a", datetime(2026, 10, 7, 21, 0, tzinfo=UTC), dur=1500,
              title="Bitcoin Dominance Update")
    assert run_list(w) == 0
    row = next(line for line in capsys.readouterr().out.splitlines() if a in line)
    assert row.startswith("| 1 |")
    assert "بنجامین کوون" in row and "Bitcoin Dominance Update" in row
    assert "2026-10-08 00:30" in row          # 21:00 جهانی = 00:30 تهران، روز بعد
    assert "25:00" in row
    assert f"https://www.youtube.com/watch?v={a}" in row


def test_list_keeps_todays_rules(env, capsys) -> None:
    w = World()
    old = w.add("cryptocity_pro", "old", NOW - timedelta(days=7, hours=1))
    fresh = w.add("cryptocity_pro", "new", NOW - timedelta(days=6, hours=23))
    gold = w.add("gareth_soloway", "g1", ago(1), title="Gold Rally Continues")
    btc = w.add("gareth_soloway", "b1", ago(2), title="Bitcoin Breakout Now")
    short = w.add("tekrargar", "s1", ago(1), dur=120)
    w.add("raoul_pal", "r1", ago(1))                          # فقط متن — هرگز نامزد
    seen = w.add("tekrargar", "seen", ago(3))
    skipped = w.add("tekrargar", "skip", ago(4))
    Path("intake", V.VIDEO_STATE_NAME).write_text(json.dumps({"videos": {
        seen: {"status": "seen"}, skipped: {"status": V.USER_SKIPPED}}, "runs": {}}), encoding="utf-8")
    q = w.add(None, "q", NOW - timedelta(days=30))            # پیشنهاد هرگز کهنه نمی‌شود
    suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    assert {it["video_id"] for it in listed()} == {fresh, btc, q}
    out = capsys.readouterr().out
    assert "کهنه" in out and old in out
    assert gold in out and short in out                       # بی‌شماره، ولی گفته می‌شود


@pytest.mark.parametrize("title,edu", [
    ("آموزش تحلیل تکنیکال | صفر تا 100 استراتژی حمایت و مقاومت !", True),
    ("[03] آموزش تحلیل‌ تکنیکال  - استراتژی ترید ارشیاعزیز پور پارت 3", True),
    ("چطور سطح حمایت را رسم کنیم", True),
    ("How to Read the Liquidation Heatmap", True),
    ("Bitcoin: The Indicator Nobody Talks About", True),
    ("چرا بیت کوین سقوط کرد؟ پشت پرده ریزش", False),
    ("تحلیل درست بیت کوین", False),                  # «درست» درس نیست
    ("آینده روشن اتریوم", False),                    # «روشن» روش نیست
    ("Classic Bitcoin Cycle Top", False),             # Classic کلاس نیست
    ("Payrolls Come in Weak, Unemployment Ticks Higher", False),
])
def test_educational_title(title, edu) -> None:
    """هدف یادگیری، ۸ اکتبر: عنوانی که روش یا ابزار یاد می‌دهد «آموزشی» است."""
    assert V.is_educational(title) is edu


def test_educational_titles_are_labeled_and_come_first(env, capsys) -> None:
    w = World()
    news = w.add("tekrargar", "news", ago(1), title="Bitcoin price today")
    edu_en = w.add("benjamin_cowen", "edu1", ago(3), title="How to Read the Liquidation Heatmap")
    edu_fa = w.add("cryptocity_pro", "edu2", ago(2), title="آموزش اندیکاتور CVD")
    q = w.add(None, "q", ago(5), title="پیشنهاد بی‌برچسب")
    suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    # پیشنهاد کاربر اول می‌ماند؛ در منابع رصد آموزشی مقدم، هر گروه تازه‌تر اول
    assert [it["video_id"] for it in listed()] == [q, edu_fa, edu_en, news]
    out = capsys.readouterr().out
    row = {v: next(line for line in out.splitlines() if f"watch?v={v}" in line)
           for v in (news, edu_en, edu_fa)}
    assert V.EDU_LABEL == "آموزشی"
    assert V.EDU_LABEL in row[edu_en] and V.EDU_LABEL in row[edu_fa]
    assert V.EDU_LABEL not in row[news]


def test_suggestions_come_separately(env, capsys) -> None:
    w = World()
    a = w.add("tekrargar", "a", ago(1))
    q = w.add(None, "q", ago(3))
    suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    out = capsys.readouterr().out
    i_sug, i_watch = out.index(f"## {V.SUGGEST_LABEL}"), out.index("## منابع رصد")
    assert i_sug < out.index(f"watch?v={q}") < i_watch < out.index(f"watch?v={a}")


# ═══════════════ --pick: فقط انتخاب کاربر ═══════════════

def test_pick_sees_only_the_chosen_one_by_one_and_skips_the_rest(env) -> None:
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    b = w.add("tekrargar", "b", ago(2))
    c = w.add("benjamin_cowen", "c", ago(3))
    q = w.add(None, "q", ago(4))
    qf = suggest_file(q, "2026-10-07T20:00:00Z", note="یادداشت خصوصی")
    assert run_list(w) == 0
    no_feed(w)
    assert run_pick(w, f"{number_of(c)},{number_of(a)}") == 0
    assert w.frames == [c, a]                                 # به ترتیب کاربر، یکی‌یکی
    st = videos()
    assert st[a]["status"] == st[c]["status"] == "ready"
    assert st[b]["status"] == st[q]["status"] == V.USER_SKIPPED
    assert V.STATUS_FA[V.USER_SKIPPED] == SKIP_FA
    assert st[q]["suggested"] is True
    assert "یادداشت خصوصی" not in json.dumps(st, ensure_ascii=False)
    assert not qf.exists()                                    # از صف رفت، نه پاک بی‌رد
    done = list(Path("intake", I.LOCAL_DIR, V.SUGGEST_DIR, "done").glob(f"{q}__*.json"))
    assert json.loads(done[0].read_text(encoding="utf-8"))["outcome"] == V.USER_SKIPPED
    run = json.loads(Path("intake", V.VIDEO_STATE_NAME).read_text(encoding="utf-8"))["runs"][DAY][-1]
    assert sorted(run["user_skipped"]) == sorted([b, q])


def test_pick_none_skips_everything(env) -> None:
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    b = w.add("tekrargar", "b", ago(2))
    assert run_list(w) == 0
    assert run_pick(w, "none") == 0
    assert w.frames == [] and w.transcripts == []
    assert {v: e["status"] for v, e in videos().items()} == {a: V.USER_SKIPPED, b: V.USER_SKIPPED}


def test_skipped_do_not_come_back_tomorrow(env) -> None:
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    w.add("tekrargar", "b", ago(2))
    w.add("benjamin_cowen", "c", ago(3))
    assert run_list(w) == 0
    assert run_pick(w, str(number_of(a))) == 0
    n = w.add("cryptocity_pro", "n", NOW + timedelta(hours=20))
    assert run_list(w, NOW + timedelta(days=1)) == 0
    assert [it["video_id"] for it in listed()] == [n]


def test_user_skipped_is_never_counted_as_seen(env) -> None:
    w = World()
    w.add("cryptocity_pro", "a", ago(1))
    w.add("tekrargar", "b", ago(2))
    assert run_list(w) == 0
    assert run_pick(w, "none") == 0
    assert all("seen_at" not in e and e["status"] != "seen" for e in videos().values())
    assert V.main(["--daily", "--config", "analysts.yml", "--intake", "intake"], now=NOW) == 0
    text = V.daily_path(Path("intake"), DAY).read_text(encoding="utf-8")
    assert "| ویدیوی دیده‌شده | 0 |" in text
    assert f"| {SKIP_FA} — دیده نشد | 2 |" in text


def test_pick_records_todays_rules_once(env) -> None:
    """کهنه و کوتاهِ فهرست با --pick یک بار در وضعیت می‌نشینند — همان --new."""
    w = World()
    old = w.add("cryptocity_pro", "old", NOW - timedelta(days=8))
    short = w.add("tekrargar", "s1", ago(1), dur=120)
    assert run_list(w) == 0
    assert not Path("intake", V.VIDEO_STATE_NAME).exists()
    assert run_pick(w, "none") == 0
    st = videos()
    assert st[old]["status"] == "stale" and st[short]["status"] == "short"


def test_video_after_the_list_is_not_skipped(env) -> None:
    w = World()
    w.add("cryptocity_pro", "a", ago(2))
    assert run_list(w) == 0
    late = w.add("tekrargar", "late", ago(1))
    no_feed(w)
    assert run_pick(w, "none") == 0
    assert late not in videos()                               # کاربر آن را ندید


def test_block_during_pick_leaves_the_rest_of_the_choice_open(env, capsys) -> None:
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    b = w.add("tekrargar", "b", ago(2))
    c = w.add("benjamin_cowen", "c", ago(3))
    assert run_list(w) == 0
    w.blocked.add(a)
    assert run_pick(w, f"{number_of(a)},{number_of(b)}") == 3
    assert w.frames == []
    st = videos()
    assert a not in st and b not in st                        # انتخاب کاربر، فردا دوباره
    assert st[c]["status"] == V.USER_SKIPPED
    assert "مسدود" in capsys.readouterr().out


# ═══════════════ خطای بلند ═══════════════

@pytest.mark.parametrize("bad", ["0", "4", "1,1", "x", "", "1;2"])
def test_bad_pick_changes_nothing(env, bad, capsys) -> None:
    w = World()
    for i, s in enumerate(("cryptocity_pro", "tekrargar", "benjamin_cowen")):
        w.add(s, s[:2], ago(i + 1))
    assert run_list(w) == 0
    before = V.list_path(Path("intake")).read_text(encoding="utf-8")
    assert run_pick(w, bad) == 2
    assert w.frames == [] and not Path("intake", V.VIDEO_STATE_NAME).exists()
    assert V.list_path(Path("intake")).read_text(encoding="utf-8") == before
    assert capsys.readouterr().err


def test_pick_needs_a_fresh_unused_list(env, capsys) -> None:
    w = World()
    w.add("cryptocity_pro", "a", ago(1))
    assert run_pick(w, "none") == 2                           # فهرستی نیست
    assert "--list" in capsys.readouterr().err
    assert run_list(w) == 0
    assert run_pick(w, "none", NOW + timedelta(hours=25)) == 2      # فهرست کهنه
    assert run_pick(w, "none") == 0
    assert run_pick(w, "none") == 2                           # فهرست مصرف‌شده
    assert "--list" in capsys.readouterr().err


def test_resuggest_after_user_skip_is_accepted(env) -> None:
    """رد به انتخاب کاربر بسته نیست: پیشنهاد صریح دوباره کاربر پذیرفته می‌شود."""
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    assert run_list(w) == 0
    assert run_pick(w, "none") == 0
    res = V.enqueue(Path("intake"), f"https://www.youtube.com/watch?v={a}", "", NOW)
    assert res.rc == 0


def test_resuggested_skip_goes_through_list_and_pick(env) -> None:
    """
    پیشنهاد کاربر بر «رد به انتخاب کاربر» مقدم است — تصمیم کاربر، ۸ اکتبر ۲۰۲۶. تا
    آخر راه، نه فقط ورود به صف؛ و هر دو حالت: ویدیوی رصد ردشده، و پیشنهادی که خودش
    رد شد و نتیجه‌اش در done/ نشسته است.
    """
    w = World()
    a = w.add("cryptocity_pro", "a", ago(1))
    q = w.add(None, "q", ago(2))
    suggest_file(q, "2026-10-07T20:00:00Z")
    assert run_list(w) == 0
    assert run_pick(w, "none") == 0
    assert videos()[a]["status"] == videos()[q]["status"] == V.USER_SKIPPED
    for v in (a, q):
        assert V.enqueue(Path("intake"), f"https://www.youtube.com/watch?v={v}", "", NOW).rc == 0
    later = NOW + timedelta(hours=1)
    assert run_list(w, later) == 0
    assert {it["video_id"] for it in listed() if it["suggested"]} == {a, q}
    assert run_pick(w, f"{number_of(a)},{number_of(q)}", later) == 0
    assert w.frames == [a, q]
    st = videos()
    assert st[a]["status"] == st[q]["status"] == "ready"
    assert st[a]["suggested"] is True and st[a]["source"] == "cryptocity_pro"
