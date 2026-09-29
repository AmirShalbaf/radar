"""
آزمون قفل analysts.yml — نشست ۴، بند ۲، تصمیم‌های کاربر ۲۹ سپتامبر ۲۰۲۶.

یافته ایستگاه ۱: سه هندل از چهار هندل بی‌شناسه ۴۰۴ می‌داد — کوون، سالووی،
پال — و منبع بی‌صدا «هیچ آیتمی» برمی‌گرداند. شناسه‌ها از جست‌وجوی یوتیوب،
صفحه خود کانال و عنوان خوراک رسمی پیدا و تأیید شدند.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

import radar_intake as I

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "analysts.yml"


def _raw() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def _src() -> dict:
    return {s.key: s for s in I.load_sources(CFG)}


def test_meta_version_and_framework() -> None:
    meta = _raw()["meta"]
    assert meta["version"] == "1.6"
    assert meta["framework"] == "Radar 7"
    assert meta["updated"] == "2026-09-29"      # وقت جهانی، مثل بقیه مخزن


def test_confirmed_channel_ids_and_handles() -> None:
    s = _src()
    want = {
        "benjamin_cowen": ("UCRvqjQPSeaWn-uEx-w0XOIg", "@benjaminjcowen"),
        "gareth_soloway": ("UCwTu6kD2igaLMpxswtcdxlg", "@GarethSolowayProTrader"),
        "raoul_pal": ("UCVFSzL3VuZKP3cN9IXdLOtw", "@RaoulPalTJM"),
        "virtualbacon": ("UCcrEA_xd9Ldf1C8DIJYdyyA", "@VirtualBacon"),
    }
    for key, (cid, handle) in want.items():
        assert (s[key].channel_id, s[key].handle) == (cid, handle), key


def test_soloway_is_personal_channel_not_company() -> None:
    assert _src()["gareth_soloway"].channel_id != "UCZ-J2m1AUSLnifUEKam5_dA"


def test_every_enabled_youtube_source_has_a_valid_id() -> None:
    """بی‌شناسه یعنی مسیر حدس هندل — همان مسیری که بی‌صدا ۴۰۴ می‌داد."""
    for key, s in _src().items():
        if s.enabled and s.kind == "youtube":
            assert re.fullmatch(r"UC[A-Za-z0-9_-]{22}", s.channel_id), key


def test_elliott_enabled_with_official_feed() -> None:
    s = _src()["bob_elliott"]
    assert s.enabled is True
    assert (s.kind, s.url) == ("rss", "https://bobeunlimited.substack.com/feed")


def test_wang_disabled_with_reason_and_kept() -> None:
    s = _src()["joseph_wang"]
    assert s.enabled is False
    assert "فوریه" in s.disabled_reason and "خلاصه" in s.disabled_reason
    assert s.url == "https://fedguy.com/feed/"


def test_kaiko_disabled_with_reason() -> None:
    s = _src()["kaiko"]
    assert s.enabled is False
    assert "PDF" in s.disabled_reason


def test_every_disabled_source_says_why() -> None:
    for key, s in _src().items():
        if not s.enabled:
            assert s.disabled_reason.strip(), key


def test_link_patterns_are_ascii() -> None:
    """مسیر نشانی اسکی است؛ `\\w` حرف و رقم فارسی را هم می‌گیرد — CLAUDE.md."""
    for key, s in _src().items():
        if s.link_pattern:
            assert r"\w" not in s.link_pattern and r"\d" not in s.link_pattern, key
    assert "[A-Za-z0-9_-]" in _src()["kaiko"].link_pattern


def test_scores_field_untouched_until_session_8() -> None:
    """
    میدان scores مال موتور امتیازدهی ردشده است — بخش ۴.۲ STATE.md. تصمیم
    درباره‌اش کار نشست ۸ است؛ تا آن موقع هیچ مقداری عوض نشود.
    """
    want = {
        "joseph_wang": True, "kaiko": True, "bob_elliott": True, "ray_dalio": False,
        "tradecity_pro": False, "no_bs_crypto": False, "cryptocity_pro": False,
        "tekrargar": False, "benjamin_cowen": True, "gareth_soloway": True,
        "raoul_pal": True, "virtualbacon": False, "arshia_course": False,
    }
    assert {k: s.scores for k, s in _src().items()} == want
