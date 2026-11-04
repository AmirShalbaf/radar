"""
قرارداد لایه پیام صبح — متن ۳۷، references/brief-contract.md.

نگهبان اصلی این آزمون‌هاست: سند هر سازنده با تابع خود سازنده ساخته می‌شود و به
مترجم radar_brief داده می‌شود. تغییر ناسازگار در اسکن، سبد، سطوح، زمینه یا فایل‌های
داده — مثلاً در بازبینی Fable — همین‌جا قرمز می‌شود، نه بی‌صدا در تلگرام.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import brief_fixture as F
import radar_brief as BR
import radar_levels as LV
import radar_sidecar as SC

UTC = timezone.utc
LESSONS = str(ROOT / "references" / "lessons.json")


def _src(now=None):
    return BR.Sources(".", now or datetime.now(UTC), files={"lessons": LESSONS})


def _doc(now=None, **kw):
    now = now or datetime.now(UTC)
    F.write_all(".", now, **kw)
    return BR.collect(_src(now), fetch=F.fake_fetch())


def test_full_collect_every_section_ok_and_valid():
    doc = _doc()
    assert BR.validate(doc) == []
    assert doc["failed"] == [], doc["failed"]
    s = doc["sections"]
    assert s["capital"]["total"] > 0 and s["positions"]["rows"]
    assert s["chart"]["ok"] and s["chart"]["series"][0]["symbol"] == "BTC"
    json.dumps(doc, allow_nan=False)              # سند همیشه JSON سالم


def test_missing_sidecar_breaks_only_its_sections():
    now = datetime.now(UTC)
    F.write_all(".", now)
    os.remove("reports/scan.json")
    doc = BR.collect(_src(now), fetch=None)
    s = doc["sections"]
    assert not s["market"]["ok"] and "scan.json" in s["market"]["why"]
    assert s["capital"]["ok"] and s["triggers"]["ok"] and s["regime"]["ok"]
    assert BR.validate(doc) == []
    assert any(f["name"] == "market" for f in doc["failed"])


def test_stale_sidecar_is_rejected_not_shown_as_today():
    now = datetime.now(UTC)
    F.write_all(".", now)
    SC.write_json("reports/book.json", F.book(now - timedelta(hours=BR.MAX_SIDECAR_AGE_H + 1)))
    doc = BR.collect(_src(now), fetch=None)
    assert not doc["sections"]["capital"]["ok"]
    assert "کهنه" in doc["sections"]["capital"]["why"]
    assert doc["verdict"]["level"] == "unknown"


def test_exception_in_one_section_is_isolated(monkeypatch):
    def boom(src):
        raise ValueError("خراب")
    monkeypatch.setattr(BR, "SECTIONS", tuple((n, boom if n == "winds" else f) for n, f in BR.SECTIONS))
    doc = _doc()
    assert not doc["sections"]["winds"]["ok"] and "ValueError" in doc["sections"]["winds"]["why"]
    assert doc["sections"]["capital"]["ok"] and BR.validate(doc) == []


def test_verdict_red_when_book_has_mandatory_action():
    doc = _doc(actions=["ذخیره استیبل — فروش ۱۲۰ دلار به ترتیب بخش ۵"])
    v = doc["verdict"]
    assert v["level"] == "red" and v["must"] and "۱" in v["headline"]


def test_drop_and_tiers_one_definition():
    assert BR.drop_pct(100, 90) == pytest.approx(10.0)
    assert BR.move_pct(100, 110) == pytest.approx(10.0)
    rows = {r["symbol"]: r for r in _doc()["sections"]["positions"]["rows"]}
    link = rows["LINK"]
    assert link["drop_pct"] == pytest.approx(100 * (11.078 - link["invalidation"]) / 11.078)
    assert link["tier"] == "amber" and rows["SUI"]["tier"] == "green"


def test_jalali_and_tehran_labels():
    assert BR.jalali(2026, 11, 3) == (1405, 8, 12)
    assert BR.jalali(2026, 3, 21) == (1405, 1, 1)
    assert BR.jalali(2026, 3, 20) == (1404, 12, 29)
    t = datetime(2026, 11, 3, 7, 16, tzinfo=UTC)
    assert BR.day_label(t, True) == "سه‌شنبه ۱۲ آبان ۱۴۰۵" and BR.clock(t) == "۱۰:۴۶"


def test_band_gaps_come_from_budget_table():
    up, down = BR._band_gaps(-0.816)
    assert up["name"] == "محتاط" and up["gap"] == pytest.approx(0.316)
    assert down["name"] == "بحرانی" and down["gap"] == pytest.approx(0.384)


def test_producer_docs_are_plain_json():
    now = datetime.now(UTC)
    d = F.scan(now)
    json.dumps(d, allow_nan=False)
    btc = next(r for r in d["rows"] if r["symbol"] == "BTC")
    assert btc["vs_ema200"] is None                     # پوچ تهی می‌شود، نه صفر
    assert d["macro"]["fear_greed"]["value"] == 26
    b = F.book(now)
    for k in ("capital", "regime", "trade", "positions", "reentry", "actions", "pos_risk_usd"):
        assert k in b, k
    json.dumps(b, allow_nan=False)


def test_levels_candidates_single_definition_for_report_and_doc():
    now = datetime.now(UTC)
    rows = []
    for s, trend, rr in (("AAA", "صعودی", 2.5), ("BBB", "بی‌ساختار", 3.0), ("CCC", "صعودی", 1.0)):
        rows.append(LV.Assessment(symbol=s, price=10.0, atr=0.5, trend=trend, rr=rr,
                                  rr_tactical=float("nan"), verdict="روی سطح",
                                  support=LV.Level(9.5, 3, 0, "حمایت"),
                                  resistance=LV.Level(12.0, 2, 0, "مقاومت")))
    assert [a.symbol for a in LV.candidates(rows, 2.0)] == ["AAA"]
    doc = LV.levels_doc(rows, 2.0, now)
    assert [c["symbol"] for c in doc["candidates"]] == ["AAA"]
    rep = LV.report(rows, 2.0, now=now)
    assert "### AAA" in rep and "### BBB" not in rep


def test_lessons_library_is_well_formed():
    lib = json.loads(Path(LESSONS).read_text(encoding="utf-8"))
    names = {n for n, _ in BR.SECTIONS}
    ids = set()
    for l in lib["lessons"]:
        assert l["id"] not in ids
        ids.add(l["id"])
        assert l["title"] and 2 <= len(l["points"]) <= 5 and l.get("practice")
        for c in l["when"]:
            assert c["path"].split(".")[0] in names, c
            assert set(c) - {"path"} <= {"lt", "gt", "abs_lt", "eq", "min"}


def test_lesson_choice_and_cooldown():
    lib = json.loads(Path(LESSONS).read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    data = {"market": {"btc": {"above_sma_pct": 1.0}, "fear_greed": 50}, "positions": {"ok": True}}
    assert BR.pick_lesson(lib, data, [], now)["id"] == "btc_sma50w"
    hist = [{"at": (now - timedelta(days=1)).isoformat(), "id": "btc_sma50w"}]
    assert BR.pick_lesson(lib, data, hist, now)["id"] == "weekly_close_rule"
    hist.append({"at": now.isoformat(), "id": "weekly_close_rule"})
    assert BR.pick_lesson(lib, data, hist, now)["id"] == "btc_sma50w"   # هرگز روز بی‌درس


def test_lesson_history_carries_forward():
    now = datetime.now(UTC)
    doc1 = _doc(now)
    SC.write_json("reports/brief.json", doc1)
    doc2 = BR.collect(_src(now + timedelta(hours=1)), fetch=None)
    assert len(doc2["lesson_history"]) == len(doc1["lesson_history"]) + 1
    assert doc2["sections"]["lesson"]["id"] != doc1["sections"]["lesson"]["id"]


def test_real_data_files_still_parse():
    """نگهبان فایل‌های داده واقعی — رونوشت conftest. تغییر شکل‌شان مترجم را قرمز می‌کند."""
    src = _src()
    for name in ("regime", "winds", "health", "calendar", "scorecard"):
        sec = BR._safe(dict(BR.SECTIONS)[name], src)
        assert sec["ok"], (name, sec.get("why"))


def test_live_repo_documents_keep_their_shape():
    """پس از نخستین اجرای گردش‌کار: سندهای واقعی مخزن با قرارداد می‌خوانند."""
    keys = {"scan.json": ("rows", "macro", "generated"),
            "book.json": ("capital", "positions", "reentry", "trade", "generated"),
            "levels.json": ("candidates", "rows", "generated"),
            "context.json": ("rows", "generated")}
    seen = 0
    for name, need in keys.items():
        p = ROOT / "reports" / name
        if p.exists():
            seen += 1
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in need:
                assert k in d, (name, k)
    p = ROOT / "reports" / "brief.json"
    if p.exists():
        seen += 1
        assert BR.validate(json.loads(p.read_text(encoding="utf-8"))) == []
    if not seen:
        pytest.skip("سند واقعی هنوز ساخته نشده — پیش از نخستین اجرای روزانه پس از متن ۳۷")


def test_cli_collect_writes_valid_document(capsys):
    F.write_all(".", datetime.now(UTC))
    assert BR.main(["collect", "--out", "reports/brief_cli.json", "--no-chart"]) == 0
    doc = json.loads(Path("reports/brief_cli.json").read_text(encoding="utf-8"))
    assert BR.validate(doc) == [] and "✅" in capsys.readouterr().out
