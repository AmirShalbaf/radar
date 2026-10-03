#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_intake.py  —  نسخه ۱.۵
موتور جمع‌آوری منابع تحلیلی برای چارچوب رادار

فلسفه:
    این اسکریپت «تحلیل» نمی‌کند. فقط متن خام را می‌آورد، شناسنامه می‌زند،
    و خطوطی را که *شاید* ادعای قابل‌تسویه باشند علامت می‌گذارد.
    داوری با انسان و با موتور تحلیل است، نه با این ابزار.

    قانون مادر رادار: «هرگز عدد نساز.» این اسکریپت هیچ عددی استنتاج نمی‌کند.
    فقط اعدادی را که در متن اصلی آمده‌اند نقل می‌کند.

محیط اجرا:
    فقط لپ‌تاپ — یوتیوب آی‌پی مرکز داده را می‌بندد، پس روی گیت‌هاب اجرا
    نمی‌شود. وابستگی‌ها در requirements-intake.txt؛ اگر یکی نبود، اجرا از
    همان اول با نام بسته می‌ایستد. خروجی در پوشه intake/ و سپس پوش به مخزن
    تا موتور تحلیل بتواند آن را بخواند. دفترچه کولب قدیمی منسوخ است.

اجرا:
    python radar_intake.py                       # همه منابع فعال
    python radar_intake.py --source joseph_wang  # فقط یک منبع
    python radar_intake.py --limit 3             # حداکثر ۳ آیتم تازه از هر منبع
    python radar_intake.py --since 2026-07-01    # فقط بعد از این تاریخ
    python radar_intake.py --whisper             # اجازه رونویسی صوتی اگر زیرنویس نبود
    python radar_intake.py --dry-run             # فقط نشان بده چه چیزی می‌آورد
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# تنها منبع اصلی نگاشت رقم — کپی محلی نگیر
from radar_text import EN_DIGITS, fa

# ---------------------------------------------------------------------------
# وابستگی‌ها — ایمپورت محافظت‌شده می‌ماند تا radar_one، radar_digest و آزمون‌ها
# بی‌کتابخانه هم این پیمانه را بخوانند. ولی اجرا اختیاری نیست: main در آغاز
# هر اجرا `missing_deps` را می‌سنجد و با نام بسته می‌ایستد — نشست ۴.
# ---------------------------------------------------------------------------

try:
    import yaml
except ImportError:
    yaml = None

try:
    import requests
except ImportError:
    requests = None

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        AgeRestricted,
        NoTranscriptFound,
        NotTranslatable,
        PoTokenRequired,
        RequestBlocked,          # IpBlocked زیرکلاس همین است
        TranscriptsDisabled,
        TranslationLanguageNotAvailable,
        VideoUnavailable,
        VideoUnplayable,
    )
except ImportError:
    YouTubeTranscriptApi = None

    class _Absent(Exception):
        """کتابخانه نیست. هیچ خطای واقعی با این تطبیق نمی‌کند — پیش از این
        جانشین `Exception` بود و هر except رویش همه‌چیز را می‌بلعید."""

    AgeRestricted = NoTranscriptFound = NotTranslatable = PoTokenRequired = _Absent
    RequestBlocked = TranscriptsDisabled = TranslationLanguageNotAvailable = _Absent
    VideoUnavailable = VideoUnplayable = _Absent


VERSION = "1.5"
UTC = timezone.utc
USER_AGENT = "radar-intake/1.0 (research; contact via github.com/AmirShalbaf/radar)"

# نام ایمپورت ← نام بسته در requirements-intake.txt. آزمون برابری این دو را قفل
# می‌کند تا فهرست سنجش و فهرست نصب از هم جدا نیفتند.
REQUIRED = {
    "yaml": "pyyaml",
    "requests": "requests",
    "feedparser": "feedparser",
    "trafilatura": "trafilatura",
    "youtube_transcript_api": "youtube-transcript-api",
    "yt_dlp": "yt-dlp",
}
WHISPER_ONLY = {"faster_whisper": "faster-whisper"}


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _which(program: str) -> str | None:
    return shutil.which(program)


def missing_deps(whisper: bool) -> list[str]:
    """
    چیزهایی که اجرا بی‌آن‌ها نتیجه غلط می‌دهد، نه نتیجه کمتر.

    درس ایستگاه ۱ نشست ۴: روی لپ‌تاپ هیچ‌کدام از شش کتابخانه نصب نبود و
    اجرا با «۰ سند» و کد خروج صفر تمام می‌شد — شکستی که شبیه روز خلوت بود.
    """
    need = dict(REQUIRED)
    if whisper:
        need.update(WHISPER_ONLY)
    out = [pkg for mod, pkg in need.items() if not _has_module(mod)]
    if whisper and _which("ffmpeg") is None:
        out.append("ffmpeg")
    return out

# ---------------------------------------------------------------------------
# اجبار خروجی یونیکد
#
# درس اجرای ۶ اوت ۲۰۲۶ روی ویندوز فارسی:
#     پایتون خروجی کنسول را با کدگذاری پیش‌فرض سیستم می‌نویسد. روی ویندوز
#     فارسی این cp1256 است که حرف «ی» (\u06cc) را ندارد → UnicodeEncodeError
#     و توقف کامل برنامه، نه فقط بدنمایی.
#
# نکته: این خطا در کولب هرگز رخ نمی‌داد چون لینوکس پیش‌فرض یونیکد است.
# مهاجرت به محیط تازه، خطاهای تازه رو می‌کند.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:                                      # صفحه‌کد کنسول را هم عوض کن
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


# ===========================================================================
# ۱ — نرمال‌سازی متن
# ===========================================================================

# ارقام فارسی و عربی به لاتین. بدون این کار، هیچ الگوی عددی روی متن فارسی
# گیر نمی‌افتد و بخش نامزد ادعا برای منابع فارسی عملاً خالی می‌ماند.
#
# نگاشت از `radar_text.py` می‌آید. تعریف اصلی همین‌جا بود و پوشش هر دو
# خانواده رقم شرقی از همین‌جا کشف شد؛ هنگام ساخت پیمانه مشترک منتقل شد
# تا دو نسخه از هم جدا نیفتند. نام محلی می‌ماند چون بقیه فایل با آن کار می‌کند.
_DIGIT_MAP = EN_DIGITS

# یکسان‌سازی حروف عربی/فارسی که در رونویسی خودکار قاطی می‌شوند
_CHAR_MAP = {
    ord("ي"): "ی",
    ord("ك"): "ک",
    ord("ۀ"): "ه",
    ord("ة"): "ه",
    ord("\u200c"): " ",  # نیم‌فاصله → فاصله، فقط برای تطبیق الگو
}


def normalize_text(text: str, *, keep_zwnj: bool = True) -> str:
    """نرمال‌سازی برای *تطبیق الگو*. متن اصلی جداگانه نگه داشته می‌شود."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DIGIT_MAP)
    cmap = dict(_CHAR_MAP)
    if keep_zwnj:
        cmap.pop(ord("\u200c"), None)
    text = text.translate(cmap)
    return text


def normalize_digits_only(text: str) -> str:
    """فقط ارقام را لاتین می‌کند و متن فارسی را دست‌نخورده می‌گذارد."""
    return (text or "").translate(_DIGIT_MAP)


def collapse_ws(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text or "")).strip()


# ===========================================================================
# ۲ — آشکارساز نامزد ادعا
# ===========================================================================
#
# اصل طراحی: این آشکارساز *پرگو* است، نه دقیق.
# هزینه رد کردن یک ادعای واقعی بالاتر از هزینه دیدن چند خط اضافی است.
# انسان فیلتر نهایی است.

CLAIM_LEXICON: dict[str, list[str]] = {
    # ادعای جهت
    "جهت": [
        r"\bbullish\b", r"\bbearish\b", r"\brally\b", r"\bcrash\b", r"\bdump\b",
        r"\bpump\b", r"\btop\b", r"\bbottom\b", r"\bcapitulation\b",
        r"صعودی", r"نزولی", r"ریزش", r"رشد", r"سقف", r"کف", r"پامپ", r"دامپ",
    ],
    # سطح معاملاتی — قوی‌ترین نشانه ادعای قابل‌تسویه
    "سطح": [
        r"\bsupport\b", r"\bresistance\b", r"\bstop[- ]?loss\b", r"\bentry\b",
        r"\btarget\b", r"\btake[- ]?profit\b", r"\binvalidation\b", r"\bbreakout\b",
        r"حمایت", r"مقاومت", r"حد ?ضرر", r"استاپ", r"ورود", r"هدف", r"تارگت",
        r"ابطال", r"شکست", r"ناحیه",
    ],
    # زمان — بدون این، ادعا قابل تسویه نیست
    "زمان": [
        r"\bby (the )?end of\b", r"\bnext (week|month|quarter|year)\b",
        r"\bwithin \d+\b", r"\bQ[1-4]\b", r"\b20\d{2}\b",
        r"تا پایان", r"هفته آینده", r"ماه آینده", r"سه ?ماهه", r"امسال", r"تا \d",
    ],
    # پیش‌بینی صریح
    "پیش‌بینی": [
        r"\bi (expect|think|believe)\b", r"\bwe (expect|will see)\b",
        r"\bwill (go|hit|reach|drop|fall|rise|break)\b", r"\bshould (hit|reach|go)\b",
        r"\bmy (target|call|view)\b", r"\bprediction\b", r"\bforecast\b",
        r"انتظار دارم", r"فکر می ?کنم", r"پیش ?بینی", r"معتقدم", r"به نظر من",
        r"خواهد (رفت|رسید|شد|شکست)", r"می ?رسه", r"می ?ره",
    ],
    # ماکرو
    "ماکرو": [
        r"\bfed\b", r"\bfomc\b", r"\bcpi\b", r"\bliquidity\b", r"\brate cut\b",
        r"\brate hike\b", r"\byield\b", r"\bqt\b", r"\bqe\b", r"\brecession\b",
        r"فدرال", r"نرخ بهره", r"تورم", r"نقدینگی", r"بازده", r"رکود",
    ],
    # مشتقات و جریان
    "جریان": [
        r"\bfunding\b", r"\bopen interest\b", r"\bliquidation\b", r"\bnetflow\b",
        r"\bgamma\b", r"\bskew\b", r"\bimplied vol\b", r"\betf (in|out)flow\b",
        r"فاندینگ", r"بهره باز", r"لیکوئید", r"جریان خالص",
    ],
}

# الگوهای عددی: قیمت، درصد، سطح با پسوند هزار
#
# نکته‌ای که آزمون پیدا کرد: الگوی [kKmMbB]? بدون مرز کلمه، حرف اولِ کلمه بعدی
# را می‌بلعد. «$72,000 by the end» تبدیل می‌شد به «$72,000 b».
# همه پسوندها اکنون مرز کلمه دارند.
#
# نکته دوم: گروه گیرنده در findall فقط گروه را برمی‌گرداند نه کل تطبیق را.
# «۶۲ هزار» فقط «هزار» می‌داد. همه گروه‌ها غیرگیرنده (?:...) شدند.
NUMBER_PATTERNS = [
    r"\$\s?\d[\d,\.]*(?:\s?[kKmMbB]\b)?",                 # $62,000  $62k
    r"\b\d[\d,]*\.?\d*\s?[kK]\b",                          # 62k
    r"\b\d{1,3},\d{3}\b",                                  # 62,000
    r"\b\d+\.?\d*\s?%",                                    # 12.5%
    r"\b\d{4,7}\b",                                        # 62000
    r"\b\d+\.?\d*\s?(?:هزار|میلیون|میلیارد|دلار|تومان|درصد)",
]

# خطوط تبلیغاتی و تکراری.
# اینها از پنجره *حذف* می‌شوند، نه اینکه امتیاز منفی بگیرند — چون حضورشان
# داخل پنجره، متن نامزد را آلوده می‌کند و خواندنش را سخت.
BOILERPLATE_PATTERNS = [
    # فارسی
    r"لینک\s*(ثبت\s*نام|دسترسی|عضویت)", r"کانال\s*تلگرام", r"پاترون",
    r"حمایت\s*مالی", r"لایک\s*(کنید|یادتون)", r"سابسکرایب", r"دنبال\s*کنید",
    r"عضو\s*(شوید|بشید)", r"کد\s*تخفیف", r"تبلیغ", r"اسپانسر",
    r"توضیحات\s*(ویدیو|هست)", r"زنگوله", r"مشاوره\s*مالی\s*نیست",
    # انگلیسی
    r"\blike (and|&) subscribe\b", r"\bsmash that like\b", r"\bhit the bell\b",
    r"\blink (in|below) the description\b", r"\buse (my )?code\b",
    r"\breferral\b", r"\bsponsored by\b", r"\bnot financial advice\b",
    r"\bjoin (my|our) (telegram|discord|patreon)\b", r"\bsign up (with|at)\b",
    r"\bdisclaimer\b", r"\bpromo code\b",
]

_COMPILED_LEXICON = {
    cat: [re.compile(p, re.IGNORECASE) for p in pats]
    for cat, pats in CLAIM_LEXICON.items()
}
_COMPILED_NUMBERS = [re.compile(p) for p in NUMBER_PATTERNS]
_COMPILED_BOILER = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]


def is_boilerplate(text: str) -> bool:
    """آیا این قطعه تبلیغ یا جمله تکراری کانال است."""
    probe = normalize_text(text or "")
    return any(p.search(probe) for p in _COMPILED_BOILER)


@dataclass
class ClaimCandidate:
    index: int
    timestamp: str | None      # برای ویدئو: mm:ss
    text: str                  # متن اصلی، دست‌نخورده
    categories: list[str]
    numbers: list[str]
    strength: int              # ۰ تا ۵

    def to_row(self, maxlen: int = 220) -> str:
        ts = self.timestamp or "—"
        nums = "، ".join(self.numbers[:4]) if self.numbers else "—"
        cats = "، ".join(self.categories)
        stars = "★" * self.strength + "☆" * (5 - self.strength)
        safe = self.text.replace("|", "/").replace("\n", " ").strip()
        if len(safe) > maxlen:
            safe = safe[: maxlen - 3] + "..."
        return f"| {self.index} | {ts} | {stars} | {cats} | {nums} | {safe} |"


def score_candidate(categories: list[str], numbers: list[str]) -> int:
    """
    قدرت نامزد = چقدر شبیه یک ادعای قابل‌تسویه است.

    ادعای قابل تسویه سه جزء دارد: جهت + آستانه عددی + مهلت.
    هرچه بیشتر داشته باشد، امتیاز بالاتر.
    """
    s = 0
    if numbers:
        s += 2                                     # آستانه عددی
    if "زمان" in categories:
        s += 1                                     # مهلت
    if "پیش‌بینی" in categories:
        s += 1                                     # ادعای صریح
    if "سطح" in categories:
        s += 1                                     # قابل تبدیل به معامله
    if s == 0 and categories:
        s = 1                                      # فقط زمینه
    return min(s, 5)


def extract_claim_candidates(
    segments: list[dict[str, Any]],
    *,
    min_strength: int = 2,
    window: int = 2,
) -> list[ClaimCandidate]:
    """
    segments: [{"text": ..., "start": ثانیه یا None}]

    پنجره‌سازی: یک ادعا معمولاً در دو سه قطعه زیرنویس پخش می‌شود.
    مثال واقعی: «فکر می‌کنم بیت‌کوین» / «تا پایان ماه» / «به ۶۲ هزار می‌رسد».
    هیچ‌کدام به‌تنهایی ادعا نیست؛ کنار هم هست. پس روی پنجره لغزان کار می‌کنیم.
    """
    out: list[ClaimCandidate] = []
    n = len(segments)
    idx = 0
    i = 0
    while i < n:
        if is_boilerplate(segments[i].get("text", "")):
            i += 1
            continue

        # پنجره روی اولین خط تبلیغاتی *بریده* می‌شود، نه اینکه از رویش رد شود.
        chunk = []
        for seg in segments[i : i + window + 1]:
            if is_boilerplate(seg.get("text", "")):
                break
            chunk.append(seg)
        if not chunk:
            i += 1
            continue

        raw = " ".join((c.get("text") or "").strip() for c in chunk).strip()
        if not raw:
            i += 1
            continue

        probe = normalize_digits_only(normalize_text(raw))

        cats: list[str] = []
        for cat, pats in _COMPILED_LEXICON.items():
            if any(p.search(probe) for p in pats):
                cats.append(cat)

        nums: list[str] = []
        for p in _COMPILED_NUMBERS:
            for m in p.findall(probe):
                val = m if isinstance(m, str) else " ".join(x for x in m if x)
                val = val.strip()
                if val and val not in nums:
                    nums.append(val)

        strength = score_candidate(cats, nums)
        if cats and strength >= min_strength:
            start = chunk[0].get("start")
            ts = fmt_ts(start) if start is not None else None
            idx += 1
            out.append(
                ClaimCandidate(
                    index=idx,
                    timestamp=ts,
                    text=raw,
                    categories=cats,
                    numbers=nums,
                    strength=strength,
                )
            )
            i += len(chunk)          # پرش به اندازه پنجره واقعی، نه اسمی
        else:
            i += 1
    return out


def fmt_ts(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ===========================================================================
# ۳ — پیکربندی منابع
# ===========================================================================

@dataclass
class Source:
    key: str
    name_fa: str
    name_en: str = ""
    role: str = "لنز تحلیل‌گر"        # لنز تحلیل‌گر | کتابخانه روش | دفتر ادعاها | لایه کشف
    school: str = ""
    kind: str = "rss"                 # youtube | rss | article
    url: str = ""
    channel_id: str = ""
    handle: str = ""
    lang: list[str] = field(default_factory=lambda: ["en"])
    enabled: bool = True
    scores: bool = False              # آیا حق ورود به امتیازدهی دارد
    notes: str = ""
    conflict: str = ""                # تعارض منافع ثبت‌شده
    link_pattern: str = ""            # فقط برای kind=index
    playlist_id: str = ""             # فقط برای kind=playlist
    collinear_with: str = ""          # هم‌خانواده با کدام منبع (یک رأی، نه دو)
    disabled_reason: str = ""         # چرا خاموش است — در خروجی و INDEX می‌آید

    @classmethod
    def from_dict(cls, key: str, d: dict) -> "Source":
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(key=key, **clean)


def load_sources(path: Path) -> list[Source]:
    if yaml is None:
        raise SystemExit("PyYAML نصب نیست:  pip install pyyaml")
    if not path.exists():
        raise SystemExit(f"فایل پیکربندی پیدا نشد: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    srcs = data.get("sources") or {}
    return [Source.from_dict(k, v or {}) for k, v in srcs.items()]


class SourceFailure(Exception):
    """
    منبع هیچ آیتمی نیاورد و دلیلش معلوم است. با نام منبع در خروجی و سرخط
    INDEX می‌آید و کد خروج را ۳ می‌کند.

    درس ایستگاه ۱ نشست ۴: هر شکست منبع «هیچ آیتمی برنگشت» و کد صفر بود.
    سه هندل ۴۰۴ و انتقال کایکو این‌طور پنهان ماندند.
    """


class IntakeError(Exception):
    """خرابی‌ای که اجرا را از آغاز می‌ایستاند — مثل .state.json خراب."""


def _feed_why(feed) -> str:
    """چرا خوراک خالی آمد — feedparser خطای شبکه را هم به‌جای پرتاب، ضمیمه می‌کند."""
    status = getattr(feed, "status", None)
    exc = getattr(feed, "bozo_exception", None)
    parts = []
    if status is not None:
        parts.append(f"وضعیت {status}")
    if exc is not None:
        parts.append(f"{type(exc).__name__}: {str(exc)[:120]}")
    return "، ".join(parts) or "بی‌آیتم"


# ===========================================================================
# ۴ — واکشی: یوتیوب
# ===========================================================================

YT_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"


def resolve_channel_id(handle_or_url: str, session) -> str | None:
    """
    خوراک رسمی یوتیوب فقط با channel_id کار می‌کند، نه با @handle.

    درس نسخه ۱.۰ (اجرای ۶ اوت ۲۰۲۶):
        نسخه اول اولین «channelId» داخل صفحه را برمی‌داشت. صفحه یوتیوب ده‌ها
        بار این کلمه را دارد — برای ویدئوهای پیشنهادی، کانال‌های مرتبط، تبلیغ.
        نتیجه: دو کانال متفاوت یک شناسه گرفتند و هر دو غلط بود.

        درس عمومی‌تر: وقتی یک الگو در سند چند بار تکرار می‌شود، «اولین تطبیق»
        یک انتخاب دلبخواه است، نه یک استخراج. باید سراغ فراداده‌ای رفت که
        *تعریفاً* یکتاست.

    اکنون فقط از فراداده‌های صاحب صفحه استفاده می‌شود، به ترتیب اعتبار.
    """
    url = handle_or_url
    if not url.startswith("http"):
        url = f"https://www.youtube.com/{handle_or_url.lstrip('/')}"
    try:
        r = session.get(url, timeout=25)
        r.raise_for_status()
    except Exception as e:
        # نشست ۴: پیش از این فقط لاگ و None — منبع بی‌صدا خالی می‌ماند
        raise SourceFailure(f"صفحه کانال {url} — {type(e).__name__}: {e}") from e

    html = r.text

    # ۱ — پیوند متعارف: یکتا و متعلق به صاحب صفحه
    m = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']'
        r'https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})',
        html,
    )
    if m:
        return m.group(1)

    # ۲ — og:url — همان نقش
    m = re.search(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']'
        r'https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})',
        html,
    )
    if m:
        return m.group(1)

    # ۳ — externalId داخل بلوک فراداده کانال (نه هر externalId در صفحه)
    anchor = html.find("channelMetadataRenderer")
    if anchor != -1:
        m = re.search(r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"', html[anchor : anchor + 4000])
        if m:
            return m.group(1)

    # ۴ — آخرین تلاش: تگ فراداده استاندارد
    m = re.search(r'<meta[^>]+itemprop=["\']identifier["\'][^>]+content=["\'](UC[A-Za-z0-9_-]{22})', html)
    if m:
        return m.group(1)

    return None


def verify_channel(cid: str) -> str | None:
    """
    نام واقعی کانال را از خوراک برمی‌گرداند.

    بدون این گام، شناسه غلط بی‌صدا رد می‌شود و تو ویدئوهای یک نفر دیگر را
    به حساب منبع خودت می‌گذاری. این بدترین نوع خطاست: خطایی که خطا به نظر نمی‌رسد.
    """
    if feedparser is None:
        return None
    try:
        feed = feedparser.parse(YT_FEED.format(cid=cid))
        return getattr(feed.feed, "title", None)
    except Exception:
        return None


def discover_feed(site_url: str, session) -> str | None:
    """
    نشانی خوراک را از خود صفحه پیدا می‌کند.

    دلیل وجود: حدس‌زدن نشانی خوراک (/rss.xml, /feed, /rss) کار نمی‌کند —
    کایکو در اجرای اول دقیقاً به همین دلیل خالی برگشت.
    استاندارد وب می‌گوید سایت باید خوراکش را در تگ link اعلام کند. از همان بخوان.
    """
    try:
        r = session.get(site_url, timeout=25)
        r.raise_for_status()
    except Exception:
        return None
    for m in re.finditer(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', r.text, re.I
    ):
        h = re.search(r'href=["\']([^"\']+)["\']', m.group(0))
        if not h:
            continue
        href = h.group(1)
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            base = re.match(r"(https?://[^/]+)", site_url)
            href = (base.group(1) if base else "") + href
        return href
    return None


def fetch_youtube_items(src: Source, session) -> list[dict]:
    """آخرین ویدئوهای کانال از خوراک رسمی. رایگان، بدون کلید، حداکثر ۱۵ مورد."""
    if feedparser is None:
        raise SourceFailure("feedparser نصب نیست")

    cid = src.channel_id
    if not cid:
        cid = resolve_channel_id(src.handle or src.url, session)
        if cid:
            title = verify_channel(cid)
            log(f"    شناسه یافت شد: {cid}")
            if title:
                log(f"    نام واقعی کانال: «{title}»  ← با «{src.name_fa}» تطبیق بده")
            log("    (پس از تأیید، در analysts.yml ذخیره کن تا دفعه بعد سریع‌تر شود)")
    if not cid:
        raise SourceFailure(f"شناسه کانال از «{src.handle or src.url}» پیدا نشد")

    feed = feedparser.parse(YT_FEED.format(cid=cid))
    if not feed.entries:
        raise SourceFailure(f"خوراک کانال {cid} خالی یا در دسترس نیست — {_feed_why(feed)}")
    items = []
    for e in feed.entries:
        vid = getattr(e, "yt_videoid", None) or ""
        if not vid:
            m = re.search(r"v=([A-Za-z0-9_-]{11})", getattr(e, "link", ""))
            vid = m.group(1) if m else ""
        if not vid:
            continue
        items.append(
            {
                "id": vid,
                "title": getattr(e, "title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published": getattr(e, "published", ""),
                "author": getattr(e, "author", src.name_en or src.name_fa),
            }
        )
    return items


# ویدیوی ۳ دقیقه یا کمتر رد می‌شود — تصمیم ۱ کاربر، ۲۹ سپتامبر ۲۰۲۶.
# ایستگاه ۱: ۱۱ از ۱۵ آیتم خوراک رایول پال ویدیوی کوتاه بود، حدود ۲۷ ثانیه.
SHORT_MAX_SECONDS = 180

_ISO_DURATION = re.compile(r"PT(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?")


def video_duration(video_id: str, session) -> tuple[int | None, str]:
    """
    (ثانیه، منشأ). None یعنی «مدت نامعلوم» — ویدیو رد نمی‌شود، برچسب می‌گیرد.

    فقط فراداده خود صفحه ویدیو، به ترتیب اعتبار:
      ۱ — <meta itemprop="duration" content="PT98M34S">
      ۲ — lengthSeconds داخل بلوک videoDetails همان شناسه
    نه نخستین lengthSeconds صفحه — همان درس resolve_channel_id: وقتی الگو در
    سند تکرار می‌شود، اولین تطبیق انتخاب دلبخواه است. سنجش ۲۹ سپتامبر ۲۰۲۶
    روی چهار ویدیو، ۲۵ ثانیه تا ۹۸ دقیقه: هر دو منشأ یکی بودند.
    """
    try:
        r = session.get(f"https://www.youtube.com/watch?v={video_id}", timeout=25)
        r.raise_for_status()
    except Exception as e:
        return None, f"صفحه ویدیو — {type(e).__name__}"
    html = r.text
    m = re.search(r'<meta itemprop="duration" content="(PT[0-9HMS]+)"', html)
    if m:
        d = _ISO_DURATION.fullmatch(m.group(1))
        if d and any(d.groups()):
            h, mi, s = (int(x or 0) for x in d.groups())
            return h * 3600 + mi * 60 + s, "itemprop"
    m = re.search(r'"videoDetails":\{"videoId":"' + re.escape(video_id)
                  + r'".{0,3000}?"lengthSeconds":"([0-9]+)"', html)
    if m:
        return int(m.group(1)), "videoDetails"
    return None, "فراداده مدت در صفحه نبود"


def _snippets_to_dicts(fetched) -> list[dict]:
    """
    خروجی هر دو نسل کتابخانه را به یک شکل درمی‌آورد.

    نسخه قدیم: فهرستی از dict با کلیدهای text و start
    نسخه ۱.x : شیء FetchedTranscript از قطعه‌هایی با ویژگی .text و .start
    """
    out = []
    try:
        raw = fetched.to_raw_data()          # نسخه ۱.x راه رسمی دارد
    except AttributeError:
        raw = fetched
    for s in raw:
        if isinstance(s, dict):
            out.append({"text": s.get("text", ""), "start": s.get("start")})
        else:
            out.append({"text": getattr(s, "text", ""), "start": getattr(s, "start", None)})
    return out


def _get_transcript_list(video_id: str):
    """
    فهرست زیرنویس‌ها، مستقل از نسخه کتابخانه.

    درس اجرای ۶ اوت ۲۰۲۶ (خطای AttributeError):
        متد ایستای list_transcripts در نسخه ۱.۰ حذف شد و جایش
        متد نمونه‌ای list آمد. کد بی‌صدا نمی‌شکند — با خطا می‌شکند،
        که بهتر است. ولی باید هر دو را پوشش داد چون نسخه کولب
        بدون اطلاع به‌روز می‌شود.
    """
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):
        return YouTubeTranscriptApi.list_transcripts(video_id)   # ≤ ۰.۶
    return YouTubeTranscriptApi().list(video_id)                  # ≥ ۱.۰


class TranscriptBlocked(Exception):
    """یوتیوب درخواست را بست — آی‌پی یا توکن. با «زیرنویس ندارد» فرق دارد."""


_BLOCKED = (RequestBlocked, PoTokenRequired)
_UNAVAILABLE = (VideoUnavailable, VideoUnplayable, AgeRestricted)
_NOT_TRANSLATABLE = (NotTranslatable, TranslationLanguageNotAvailable)


def _fetch_one(t, label: str) -> tuple[list[dict], str]:
    try:
        return _snippets_to_dicts(t.fetch()), label
    except _BLOCKED as e:
        raise TranscriptBlocked(f"مسدود ({type(e).__name__})") from e


def fetch_transcript(video_id: str, langs: list[str]) -> tuple[list[dict], str]:
    """
    برمی‌گرداند (قطعات، روش).
    ترتیب اولویت: زیرنویس دستی → زیرنویس خودکار → ترجمه‌شده → هر زبان.
    زیرنویس دستی کیفیت به‌مراتب بالاتری دارد و در شناسنامه ثبت می‌شود.

    قطعات خالی یعنی «زیرنویس ندارد» — ویژگی ویدیو، نه خطا. مسدودی
    TranscriptBlocked است. هر خطای دیگر بالا می‌رود تا صدازننده با نوعش
    ثبتش کند.

    درس ایستگاه ۱ نشست ۴: شش `except Exception` پشت هم هر خطای واکشی —
    مسدودی آی‌پی، خطای شبکه — را «زیرنویس یافت نشد» می‌کرد. از پشت وی‌پی‌ان
    مسدودی دقیقاً شکل «این ویدیو زیرنویس ندارد» می‌گرفت. تنها چیزی که اینجا
    بلعیده می‌شود «این گام پیدا نکرد» است: NoTranscriptFound و ترجمه‌ناپذیری.
    """
    if YouTubeTranscriptApi is None:
        raise RuntimeError("youtube-transcript-api نصب نیست")
    try:
        listing = _get_transcript_list(video_id)
    except _BLOCKED as e:
        raise TranscriptBlocked(f"مسدود ({type(e).__name__})") from e
    except TranscriptsDisabled:
        return [], "زیرنویس ندارد (TranscriptsDisabled)"
    except _UNAVAILABLE as e:
        return [], f"ویدیو در دسترس نیست ({type(e).__name__})"

    # ۱ — دستی
    try:
        t = listing.find_manually_created_transcript(langs)
    except NoTranscriptFound:
        t = None
    if t is not None:
        return _fetch_one(t, f"زیرنویس دستی [{t.language_code}]")
    # ۲ — خودکار
    try:
        t = listing.find_generated_transcript(langs)
    except NoTranscriptFound:
        t = None
    if t is not None:
        return _fetch_one(t, f"زیرنویس خودکار [{t.language_code}]")

    available = list(listing)
    # ۳ — هر زبانی که هست، ترجمه‌شده
    for t in available:
        try:
            tr = t.translate(langs[0])
        except _NOT_TRANSLATABLE:
            continue
        return _fetch_one(tr, f"ترجمه ماشینی از [{t.language_code}]")
    # ۴ — هر زبانی، بدون ترجمه (بهتر از هیچ)
    for t in available:
        return _fetch_one(t, f"زیرنویس [{t.language_code}] — زبان درخواستی نبود")
    return [], "زیرنویس ندارد"


def whisper_fallback(video_url: str, model_size: str = "small") -> tuple[list[dict], str]:
    """
    پشتیبان: اگر زیرنویس نبود، صدا را بگیر و رونویسی کن.
    روی پردازنده لپ‌تاپ کند است، پس پیش‌فرض خاموش.

    ffmpeg پیش از هر چیز سنجیده می‌شود: بدون آن yt-dlp صدا را استخراج
    نمی‌کند و پیامش «دانلود صدا ناموفق» بود — علت واقعی گفته نمی‌شد.
    """
    if _which("ffmpeg") is None:
        return [], "ffmpeg نصب نیست — فقط برای --whisper لازم است"
    try:
        import yt_dlp
        from faster_whisper import WhisperModel
    except ImportError:
        return [], "ویسپر نصب نیست"

    tmp = Path(tempfile.gettempdir()) / "radar_audio"
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / "audio.%(ext)s"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}
        ],
    }
    # کوکی اختیاری — یوتیوب دانلود از سرورهای مرکز داده را مسدود می‌کند
    cookies = os.environ.get("RADAR_COOKIES", "")
    if cookies and Path(cookies).exists():
        opts["cookiefile"] = cookies

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        msg = str(e)
        if "not a bot" in msg or "Sign in to confirm" in msg:
            return [], ("یوتیوب دانلود را مسدود کرد (نشانی مرکز داده). "
                        "ویسپر روی کولب بدون کوکی کار نمی‌کند — از زیرنویس استفاده کن")
        return [], f"دانلود صدا ناموفق ({e.__class__.__name__})"

    mp3 = tmp / "audio.mp3"
    if not mp3.exists():
        return [], "فایل صوتی ساخته نشد"

    try:
        device = "cuda" if os.environ.get("COLAB_GPU") else "cpu"
        model = WhisperModel(model_size, device=device, compute_type="int8")
        segs, info = model.transcribe(str(mp3), beam_size=5)
        out_segs = [{"text": s.text, "start": s.start} for s in segs]
        return out_segs, f"رونویسی ویسپر [{info.language}] مدل {model_size}"
    except Exception as e:
        return [], f"رونویسی ناموفق ({e.__class__.__name__})"
    finally:
        try:
            mp3.unlink()
        except Exception:
            pass


# ===========================================================================
# ۵ — واکشی: خوراک خبری و مقاله
# ===========================================================================

def extract_playlist_id(raw: str) -> str:
    """شناسه پلی‌لیست را از نشانی کامل یا خود شناسه بیرون می‌کشد."""
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", raw or "")
    return m.group(1) if m else (raw or "").strip()


def fetch_playlist_items(src: Source, session) -> list[dict]:
    """
    ویدئوهای یک پلی‌لیست.

    چرا جدا از کانال: خوراک کانال فقط ۱۵ ویدئوی **آخر** را می‌دهد.
    یک دوره آموزشی بیست‌قسمتی از دو سال پیش، هرگز در آن ظاهر نمی‌شود.

    دو مسیر:
      ۱ — yt-dlp: کل پلی‌لیست، با حفظ **ترتیب**. برای دوره آموزشی ترتیب
          خودش اطلاعات است — پارت ۳ بدون پارت ۱ معنا ندارد.
      ۲ — خوراک پلی‌لیست: بدون وابستگی، ولی سقف ۱۵ مورد و ترتیب تضمینی نیست.
    """
    pid = extract_playlist_id(src.playlist_id or src.url)
    if not pid:
        raise SourceFailure("شناسه پلی‌لیست خالی است")

    # مسیر ۱ — شمارش کامل
    first = "yt-dlp هیچ ویدیویی برنگرداند"
    try:
        import yt_dlp

        opts = {"quiet": True, "no_warnings": True,
                "extract_flat": "in_playlist", "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/playlist?list={pid}", download=False
            )
        entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
        if entries:
            log(f"    پلی‌لیست «{info.get('title', '؟')}» — {len(entries)} ویدئو (ترتیب حفظ شد)")
            return [
                {
                    "id": e["id"],
                    "title": f"[{i:02d}] {e.get('title', '')}",   # شماره ترتیب در عنوان
                    "url": f"https://www.youtube.com/watch?v={e['id']}",
                    "published": "",
                    "author": src.name_en or src.name_fa,
                }
                for i, e in enumerate(entries, 1)
            ]
    except ImportError:
        first = "yt-dlp نصب نیست"
        log("    yt-dlp نصب نیست → پشتیبان خوراک (سقف ۱۵ مورد)")
    except Exception as e:
        first = f"شمارش کامل ناموفق ({e.__class__.__name__})"
        log(f"    {first} → پشتیبان خوراک (سقف ۱۵ مورد)")

    # مسیر ۲ — خوراک
    if feedparser is None:
        raise SourceFailure(f"{first}؛ feedparser هم نصب نیست")
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?playlist_id={pid}")
    if not feed.entries:
        raise SourceFailure(f"{first}؛ خوراک پلی‌لیست هم خالی — {_feed_why(feed)}")
    out = []
    for e in feed.entries:
        vid = getattr(e, "yt_videoid", "")
        if vid:
            out.append({
                "id": vid,
                "title": getattr(e, "title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published": getattr(e, "published", ""),
                "author": src.name_en or src.name_fa,
            })
    if out:
        log(f"    {len(out)} ویدئو از خوراک پلی‌لیست")
    return out


def fetch_index_items(src: Source, session) -> list[dict]:
    """
    برای سایت‌هایی که خوراک خبری ندارند.

    دلیل وجود: کایکو مدل ایمیلی دارد و هیچ خوراکی منتشر نمی‌کند.
    بدون این تابع، یکی از سه لنز امتیازدهنده کلاً از دست می‌رفت.

    روش: صفحه فهرست مقالات را بگیر، پیوندهای مقاله را با الگو دربیاور،
    سپس هر مقاله را جداگانه بخوان.
    """
    try:
        r = session.get(src.url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise SourceFailure(f"صفحه فهرست {src.url} — {type(e).__name__}: {e}") from e

    base_m = re.match(r"(https?://[^/]+)", src.url)
    base = base_m.group(1) if base_m else ""
    # مسیر نشانی اسکی است — الگو هم اسکی، وگرنه \w حرف و رقم فارسی را
    # هم می‌گیرد و زباله را شناسه پیوند جا می‌زند
    pat = re.compile(src.link_pattern or r'href="(/insights/[A-Za-z0-9_-]+)"')

    items, seen = [], set()
    for m in pat.finditer(r.text):
        href = m.group(1)
        if href in seen:
            continue
        seen.add(href)
        full = href if href.startswith("http") else base + href

        # عنوان از متن پیوند، اگر بود؛ وگرنه از نامک نشانی
        tail = r.text[m.end() : m.end() + 400]
        t = re.search(r">\s*([^<>]{12,140}?)\s*<", tail)
        title = (t.group(1).strip() if t
                 else href.rstrip("/").split("/")[-1].replace("-", " "))

        items.append({
            "id": hashlib.sha1(full.encode()).hexdigest()[:12],
            "title": collapse_ws(title),
            "url": full,
            "published": "",          # صفحه فهرست معمولاً تاریخ ندارد
            "author": src.name_en or src.name_fa,
        })
        if len(items) >= 25:
            break

    if not items:
        # نشانی نهایی گفته می‌شود: کایکو با ۳۰۱ به برنامه دیگری رفته بود
        raise SourceFailure(f"هیچ پیوند مقاله‌ای با الگوی فعلی — نشانی نهایی {getattr(r, 'url', src.url)}")
    return items


def _entry_date(e) -> str:
    """
    تاریخ ISO جهانی از تاریخ تجزیه‌شده feedparser؛ خالی اگر نبود.

    نشست ۴: رشته خام RSS مثل «Tue, 29 Sep 2026 12:34:56 GMT» است، ولی نام
    فایل، شناسه، INDEX، --since و digest ده نویسه اول را تاریخ ISO می‌گیرند.
    """
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)
    return ""


def fetch_rss_items(src: Source, session) -> list[dict]:
    if feedparser is None:
        raise SourceFailure("feedparser نصب نیست")
    feed = feedparser.parse(src.url)

    # اگر خوراک خالی بود، شاید نشانی غلط است. از خود سایت بپرس.
    if not feed.entries:
        base = re.match(r"(https?://[^/]+)", src.url or "")
        if base:
            found = discover_feed(base.group(1), session)
            if found and found != src.url:
                log(f"    خوراک تازه کشف شد: {found}")
                log("    (در analysts.yml جایگزین کن)")
                feed = feedparser.parse(found)
    if not feed.entries:
        raise SourceFailure(f"خوراک {src.url} خالی یا در دسترس نیست — {_feed_why(feed)}")
    items = []
    for e in feed.entries:
        link = getattr(e, "link", "")
        if not link:
            continue
        items.append(
            {
                "id": hashlib.sha1(link.encode()).hexdigest()[:12],
                "title": getattr(e, "title", ""),
                "url": link,
                "published": _entry_date(e),
                "author": getattr(e, "author", src.name_en or src.name_fa),
            }
        )
    return items


def fetch_article_text(url: str, session) -> tuple[str, str]:
    """
    متن تمیز مقاله. اول trafilatura، بعد پشتیبان ساده.

    نشست ۴: افتادن به پشتیبان پیش از این بی‌صدا بود — شکست trafilatura
    بلعیده می‌شد. حالا دلیل افت در برچسب «روش» شناسنامه می‌آید.
    """
    why = "trafilatura نصب نیست"
    if trafilatura is not None:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                txt = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                )
                if txt and len(txt) > 300:
                    return txt, "trafilatura"
                why = "trafilatura متن کوتاه یا تهی داد"
            else:
                why = "trafilatura صفحه را نگرفت"
        except Exception as e:
            why = f"trafilatura: {type(e).__name__}"
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        html = r.text
        html = re.sub(r"(?is)<(script|style|nav|footer|header|aside).*?</\1>", " ", html)
        txt = re.sub(r"(?s)<[^>]+>", " ", html)
        txt = re.sub(r"&nbsp;?", " ", txt)
        txt = collapse_ws(txt)
        return txt, f"استخراج ساده HTML — {why}"
    except Exception as e:
        return "", f"ناموفق ({e.__class__.__name__}) — {why}"


# نشانه‌های متن بریده. فقط در انتهای متن جست‌وجو می‌شوند، چون بریدگی آنجاست.
# نمونه‌های واقعی ایستگاه ۱ نشست ۴: خلاصه ۷۶ کلمه‌ای وانگ با «[…]»، و
# پیش‌نمایش سابستک الیوت با «Continue reading this post for free».
_TRUNCATION = [
    (re.compile(r"(\[…\]|\[\.\.\.\]|…)\s*$"), "پایان با «…»"),
    (re.compile(r"(?i)continue reading"), "«Continue reading» — پیش‌نمایش"),
    (re.compile(r"(?i)keep reading with"), "«Keep reading» — پیش‌نمایش"),
    (re.compile(r"(?i)this post is for (paid )?subscribers"), "فقط برای مشترک"),
    (re.compile(r"(?i)subscribe to (continue|keep) reading"), "فقط برای مشترک"),
    (re.compile(r"(?i)requires javascript"), "صفحه جاوااسکریپت می‌خواهد — متن نیامد"),
]
MIN_ARTICLE_WORDS = 150


def text_gap(txt: str) -> str | None:
    """
    چرا متن مقاله ناقص است، یا None اگر نشانه‌ای نیست.

    تصمیم ۵ کاربر، ۲۹ سپتامبر ۲۰۲۶: سند ناقص برچسب «متن ناقص» می‌گیرد تا
    نشست ۵ از متن بریده ادعا برندارد. کف طول هم نشانه است، نه اثبات؛ دلیل
    کنار برچسب می‌آید تا خواننده خودش ببیند.
    """
    tail = (txt or "").strip()[-400:]
    reasons = [why for rx, why in _TRUNCATION if rx.search(tail)]
    words = len((txt or "").split())
    if words < MIN_ARTICLE_WORDS:
        reasons.append(f"کوتاه: {words} کلمه، کف {fa(MIN_ARTICLE_WORDS)}")
    # یکتا با حفظ ترتیب
    return "؛ ".join(dict.fromkeys(reasons)) or None


# ===========================================================================
# ۶ — نوشتن خروجی
# ===========================================================================

def slugify(text: str, maxlen: int = 40) -> str:
    # \u0627\u06CC\u0646\u062C\u0627 \w \u0639\u0645\u062F\u0627\u064B \u0645\u0627\u0646\u062F\u0647: \u0628\u0627\u06CC\u062F \u062D\u0631\u0641 \u0648 \u0631\u0642\u0645 \u0641\u0627\u0631\u0633\u06CC \u0631\u0627 \u0646\u06AF\u0647 \u062F\u0627\u0631\u062F\u060C \u0686\u0648\u0646 \u0639\u0646\u0648\u0627\u0646
    # \u0641\u0627\u0631\u0633\u06CC \u0627\u0633\u062A. \u0628\u0631\u062E\u0644\u0627\u0641 \u0627\u0644\u06AF\u0648\u0647\u0627\u06CC \u0634\u0646\u0627\u0633\u0647\u060C \u062F\u0627\u0645\u0646\u0647 \u0648\u0631\u0648\u062F\u06CC \u0627\u0633\u06A9\u06CC \u0646\u06CC\u0633\u062A.
    text = re.sub(r"[^\w\u0600-\u06FF\s-]", "", text or "").strip()
    text = re.sub(r"\s+", "-", text)
    return text[:maxlen].strip("-") or "untitled"


# ---------------------------------------------------------------------------
# چیدمان «متن کامل فقط محلی» — نشست ۴، بند «ز»، تصمیم کاربر ۲۹ سپتامبر ۲۰۲۶
#
# مخزن عمومی است. متن کامل مقاله و زیرنویس دیگران نباید در آن برود.
#   عمومی:  intake/<src>/<name>.md         شناسنامه، پیوند، نامزدهای سقف‌دار
#   محلی:   intake/_local/<src>/<name>.md  سند کامل — در .gitignore
# یک قاعده برای همه منابع. ۹ فایل پیشین دوره ارشیا همان‌طور می‌مانند.
# ---------------------------------------------------------------------------
LOCAL_DIR = "_local"
# گزارش ویدیوی radar_video — خوانده ماست، نه سند جمع‌آوری؛ INDEX و DIGEST
# نمی‌شمارندش. نشست ۶ب.
REPORTS_DIR = "reports"
PUBLIC_MAX_CANDIDATES = 10
PUBLIC_MAX_CHARS = 200


def _public_candidates(cands: list[ClaimCandidate]) -> list[ClaimCandidate]:
    """قوی‌ترها، و به ترتیب زمان برای خواندن. شماره هر ردیف همان شماره نسخه محلی است."""
    top = sorted(cands, key=lambda c: (-c.strength, c.index))[:PUBLIC_MAX_CANDIDATES]
    return sorted(top, key=lambda c: c.index)


def build_documents(
    src: Source,
    item: dict,
    segments: list[dict],
    method: str,
    candidates: list[ClaimCandidate],
    gap: str | None = None,
    *,
    local_rel: str,
    duration: str = "—",
) -> tuple[str, str]:
    """برمی‌گرداند (سند عمومی، سند کامل محلی). local_rel نسبت به پوشه intake است."""
    body_lines = []
    has_ts = any(s.get("start") is not None for s in segments)
    for s in segments:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        if has_ts and s.get("start") is not None:
            body_lines.append(f"[{fmt_ts(s['start'])}] {t}")
        else:
            body_lines.append(t)
    body = "\n".join(body_lines)
    words = len(body.split())

    collected = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc_id = f"{item.get('published','')[:10] or 'nodate'}_{src.key}_{item['id'][:8]}"

    head = [
        "---",
        f"شناسه: {doc_id}",
        f"منبع: {src.name_fa}",
        f"نام لاتین: {src.name_en}",
        f"جایگاه در رادار: {src.role}",
        f"مکتب: {src.school or '—'}",
        f"حق امتیازدهی: {'دارد' if src.scores else 'ندارد — فقط زمینه'}",
        f"عنوان: {item.get('title','').replace(':', ' -')}",
        f"نشانی: {item.get('url','')}",
        f"تاریخ انتشار: {item.get('published') or '—'}",
        f"تاریخ جمع‌آوری: {collected}",
        f"روش استخراج: {method}",
        # نشست ۴: نشست ۵ از متن بریده ادعا برنمی‌دارد
        f"متن: {'ناقص — ' + gap if gap else 'کامل'}",
        f"مدت: {duration}",
        "برچسب معرفتی: نقل‌شده (Reported)",
        f"تعداد کلمه: {words}",
        f"نامزد ادعا: {len(candidates)}",
        f"تعارض منافع: {src.conflict or 'ثبت‌نشده'}",
        f"هم‌خطی با: {src.collinear_with or '—'}",
        f"ساخته‌شده با: radar_intake {VERSION}",
        f"متن محلی: {local_rel}",
        "---",
        "",
        "> **هشدار اجباری رادار:** این متن *داده* نیست، *نقل‌شده* است.",
        "> هیچ عددی از این فایل مستقیم وارد موتور امتیازدهی نمی‌شود.",
        "> اعداد فقط از اسکریپت‌های داده (radar_fetch3 / radar_scan) می‌آیند.",
        "> رونویسی خودکار خطا دارد؛ هر عدد کلیدی باید در ویدئو/مقاله اصلی تأیید شود.",
        "",
    ]

    def candidates_block(rows: list[ClaimCandidate], maxlen: int, note: list[str]) -> list[str]:
        out = ["## نامزدهای ادعا (خودکار — تأییدنشده)", ""]
        if not candidates:
            return out + [
                "هیچ نامزدی با آستانه فعلی پیدا نشد.",
                "",
                "**این خودش یک داده است:** منبعی که ادعای عددی و تاریخ‌دار نمی‌دهد،",
                "قابل تسویه نیست و نمی‌تواند وارد دفتر کالیبراسیون شود.",
            ]
        return out + [
            "قدرت = چقدر شبیه ادعای قابل‌تسویه است. سه جزء لازم: جهت، آستانه عددی، مهلت.",
            *note,
            "",
            "| # | زمان | قدرت | دسته | اعداد | متن |",
            "|---|---|---|---|---|---|",
            *[c.to_row(maxlen) for c in rows],
        ]

    full = (
        "\n".join(head + candidates_block(candidates, 220, [])
                  + ["", "---", "", "## متن کامل", ""])
        + "\n" + body + "\n"
    )

    shown = _public_candidates(candidates)
    note = [f"نمایش {len(shown)} از {len(candidates)} نامزد — قوی‌ترها، هر خط حداکثر "
            f"{fa(PUBLIC_MAX_CHARS)} نویسه. همه نامزدها در نسخه محلی."]
    public = "\n".join(head + candidates_block(shown, PUBLIC_MAX_CHARS, note) + [
        "",
        "---",
        "",
        "> **متن کامل در مخزن عمومی نیست.** مخزن عمومی است و متن کامل مقاله و",
        "> زیرنویس دیگران در آن نمی‌رود — نشست ۴. نسخه کامل فقط روی لپ‌تاپ:",
        f"> `intake/{local_rel}`",
    ]) + "\n"
    return public, full


def write_documents(
    src: Source,
    item: dict,
    segments: list[dict],
    method: str,
    outdir: Path,
    *,
    gap: str | None = None,
    duration: str = "—",
    min_strength: int = 2,
) -> tuple[str, int, str]:
    """
    سند عمومی و نسخه کامل محلی یک آیتم. برمی‌گرداند (نام فایل، شمار نامزد، تاریخ).

    تنها جای نام فایل و چیدمان — radar_video هم از همین می‌نویسد، نشست ۶ب.
    متنی که در دو جا نوشته شود دیر یا زود از هم جدا می‌افتد — رویداد ۲۲.
    """
    cands = extract_claim_candidates(segments, min_strength=min_strength)
    date = (item.get("published") or "")[:10] or datetime.now(UTC).strftime("%Y-%m-%d")
    fname = f"{date}_{slugify(item['title'])}_{item['id'][:6]}.md"
    local_rel = f"{LOCAL_DIR}/{src.key}/{fname}"
    public, full = build_documents(src, item, segments, method, cands, gap,
                                   local_rel=local_rel, duration=duration)
    # نسخه محلی اول: اگر نوشتنش شکست، شناسنامه عمومیِ بی‌متن نمی‌ماند
    (outdir / LOCAL_DIR / src.key).mkdir(parents=True, exist_ok=True)
    (outdir / local_rel).write_text(full, encoding="utf-8")
    (outdir / src.key).mkdir(parents=True, exist_ok=True)
    (outdir / src.key / fname).write_text(public, encoding="utf-8")
    return fname, len(cands), date


# ===========================================================================
# ۷ — وضعیت و فهرست
# ===========================================================================

def load_state(path: Path) -> dict:
    """
    حافظه «دیده‌شده‌ها». نبودش یعنی حافظه خالی؛ خرابی‌اش خطای صریح.

    نشست ۴: پیش از این فایل خراب بی‌صدا حافظه صفر می‌شد و آخر اجرا روی
    همان فایل بازنویسی می‌شد — همان الگوی load_state سبد (ک۲۵) و load_json
    پایشگر (رویداد ۳۹).
    """
    if not path.exists():
        return {"seen": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise IntakeError(
            f"{path} خوانا نیست — {type(e).__name__}: {e}. این حافظه «دیده‌شده‌ها» است؛ "
            f"بازنویسی‌اش یعنی جمع‌آوری دوباره همه‌چیز. از گیت برگردان یا دستی درست کن."
        ) from e
    if not isinstance(data, dict) or not isinstance(data.get("seen", {}), dict):
        raise IntakeError(f"{path} ساختار نادرست دارد — انتظار شیء با کلید seen")
    data.setdefault("seen", {})
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class SourceRun:
    """کارنامه یک منبع در همین اجرا — برای خروجی و سرخط INDEX."""
    key: str
    name: str
    made: int = 0
    short: int = 0                                         # ۳ دقیقه یا کمتر — رد، نه شکست
    unknown_duration: int = 0                              # رد نشد، برچسب خورد
    incomplete: int = 0
    no_text: list[str] = field(default_factory=list)       # ویژگی ویدیو — فقط گزارش
    item_errors: list[str] = field(default_factory=list)   # شکست آیتم
    failure: str = ""                                      # شکست کل منبع

    @property
    def failed(self) -> bool:
        return bool(self.failure or self.item_errors)

    def status(self) -> str:
        if self.failure:
            return "ناموفق"
        if self.item_errors:
            return f"خطای آیتم: {len(self.item_errors)}"
        return "سالم"


@dataclass
class RunReport:
    started: str
    dry_run: bool = False
    sources: list[SourceRun] = field(default_factory=list)
    disabled: list[Source] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(s.failed for s in self.sources)


def _cell(x) -> str:
    """یک خانه جدول مارک‌داون. عنوان «پارت 7 | هر چی…» جدول INDEX را شکسته بود."""
    return str(x).replace("|", "/").replace("\n", " ").strip()


def run_summary(run: RunReport) -> list[str]:
    kind = "اجرای خشک — هیچ فایلی نوشته نشد" if run.dry_run else "اجرای واقعی"
    out = [
        f"## آخرین اجرا — {run.started} — {kind}",
        "",
        f"«کوتاه ردشده» یعنی ویدیوی {fa(SHORT_MAX_SECONDS // 60)} دقیقه یا کمتر — رد، نه شکست. "
        "«مدت نامعلوم» رد نشد و در سند برچسب دارد.",
        "",
        "| منبع | سند تازه | کوتاه ردشده | مدت نامعلوم | متن ناقص | بی‌زیرنویس | وضعیت |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in run.sources:
        out.append(f"| {_cell(s.name)} | {s.made} | {s.short} | {s.unknown_duration} | "
                   f"{s.incomplete} | {len(s.no_text)} | {s.status()} |")
    out += ["", "### منابع ناموفق", ""]
    bad = [s for s in run.sources if s.failed]
    if not bad:
        out.append("هیچ منبعی شکست نخورد.")
    for s in bad:
        if s.failure:
            out.append(f"- **{_cell(s.name)}** (`{s.key}`) — {_cell(s.failure)}")
        for e in s.item_errors:
            out.append(f"- **{_cell(s.name)}** (`{s.key}`) — آیتم: {_cell(e)}")
    no_text = [(s, t) for s in run.sources for t in s.no_text]
    if no_text:
        out += ["", "### بی‌زیرنویس — ویژگی ویدیو، نه شکست", ""]
        out += [f"- {_cell(s.name)}: {_cell(t)}" for s, t in no_text]
    if run.disabled:
        out += ["", "### منابع خاموش", ""]
        out += [f"- **{_cell(s.name_fa)}** (`{s.key}`) — {_cell(s.disabled_reason or 'دلیل ثبت نشده')}"
                for s in run.disabled]
    return out + [""]


def _front_matter(txt: str) -> dict:
    meta = {}
    if txt.startswith("---"):
        block = txt.split("---", 2)[1]
        for line in block.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta


_RUN_HEAD = "## آخرین اجرا"
_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _previous_run_section(index: Path) -> list[str]:
    """
    کارنامه آخرین اجرا از INDEX موجود. بازسازی بی‌اجرا — مثلاً پس از رفع
    ترتیب در ایستگاه ۲ نشست ۴ — نباید رد اجرای واقعی را پاک کند.
    """
    if not index.exists():
        return []
    lines = index.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(_RUN_HEAD)), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ") or lines[i].startswith("### سند ناخوانا")),
               len(lines))
    return lines[start:end]


def rebuild_index(outdir: Path, run: RunReport | None = None) -> list[str]:
    """
    فهرست خوانا از همه فایل‌های جمع‌آوری‌شده. این همان چیزی است که اول می‌خوانم.

    برمی‌گرداند فهرست سندهای ناخوانا. نشست ۴: پیش از این سند ناخوانا بی‌صدا
    از فهرست می‌افتاد؛ حالا ردیفش با «ناخوانا» می‌ماند و در سرخط می‌آید.

    ترتیب: تاریخ‌دارها نزولی، سپس بی‌تاریخ و ناخوانا به ترتیب نام فایل.
    پیش از این مرتب‌سازی رشته‌ای «—» را بالای رقم‌ها می‌گذاشت.
    بی run، کارنامه آخرین اجرا از INDEX موجود نگه داشته می‌شود.
    """
    kept_run = [] if run is not None else _previous_run_section(outdir / "INDEX.md")
    rows: list[tuple[str, str, str]] = []      # (تاریخ ISO یا تهی، مسیر، ردیف)
    problems = []
    for f in sorted(outdir.rglob("*.md")):
        rel = f.relative_to(outdir).as_posix()
        if rel in ("INDEX.md", "DIGEST.md") or rel.startswith(LOCAL_DIR + "/"):
            continue      # نسخه محلی جفت همان شناسنامه است، سند دوم نیست
        if rel.startswith(REPORTS_DIR + "/"):
            continue      # گزارش ویدیو خوانده ماست، نه سند
        try:
            txt = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            problems.append(f"`{rel}` — {type(e).__name__}")
            rows.append(("", rel, f"| — | — | — | — | ⚠ ناخوانا | — | ⚠ ناخوانا | `{rel}` |"))
            continue
        meta = _front_matter(txt)
        text = meta.get("متن", "")
        text_col = "ناقص" if text.startswith("ناقص") else ("کامل" if text else "—")
        dur = meta.get("مدت", "") or "—"
        dur_col = "مدت نامعلوم" if dur.startswith("نامعلوم") else dur
        day = (meta.get("تاریخ انتشار") or "")[:10]
        day = day if _ISO_DAY.fullmatch(day) else ""
        rows.append((day, rel,
            "| {} | {} | {} | {} | {} | {} | {} | `{}` |".format(
                day or "—",
                _cell(meta.get("منبع", "—")),
                _cell(meta.get("جایگاه در رادار", "—")),
                _cell(meta.get("نامزد ادعا", "—")),
                text_col,
                _cell(dur_col),
                _cell(meta.get("عنوان", "—") or "—")[:60],
                rel,
            ),
        ))
    dated = sorted((r for r in rows if r[0]), key=lambda r: (r[0], r[1]), reverse=True)
    undated = sorted((r for r in rows if not r[0]), key=lambda r: r[1])
    header = [
        "# فهرست جمع‌آوری رادار",
        "",
        f"آخرین به‌روزرسانی: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"تعداد سند: {len(rows)}",
        "",
    ]
    if run is not None:
        header += run_summary(run)
    elif kept_run:
        header += kept_run
    if problems:
        header += ["### سند ناخوانا", ""] + [f"- {p}" for p in problems] + [""]
    header += [
        "## اسناد",
        "",
        "| تاریخ | منبع | جایگاه | نامزد | متن | مدت | عنوان | فایل |",
        "|---|---|---|---|---|---|---|---|",
    ]
    (outdir / "INDEX.md").write_text(
        "\n".join(header + [r[2] for r in dated + undated]) + "\n", encoding="utf-8"
    )
    return problems


# ===========================================================================
# ۸ — اجرا
# ===========================================================================

def log(msg: str) -> None:
    print(msg, flush=True)


def make_session():
    if requests is None:
        raise SystemExit("requests نصب نیست:  pip install requests")
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en,fa;q=0.8"})
    return s


def fetch_items(src: Source, session) -> list[dict]:
    if src.kind == "youtube":
        return fetch_youtube_items(src, session)
    if src.kind == "playlist":
        return fetch_playlist_items(src, session)
    if src.kind == "index":
        return fetch_index_items(src, session)
    return fetch_rss_items(src, session)


def process_source(
    src: Source, session, outdir: Path, state: dict, args
) -> SourceRun:
    """
    یک منبع. شکست منبع — SourceFailure — در کارنامه ثبت می‌شود و بقیه منابع
    ادامه می‌دهند. خطای یک آیتم با نوعش ثبت می‌شود و آیتم بعدی امتحان می‌شود.
    مسدودی یوتیوب بقیه ویدیوهای همین منبع را متوقف می‌کند.
    """
    run = SourceRun(src.key, src.name_fa)
    log(f"\n▶ {src.name_fa}  [{src.role}]")
    try:
        items = fetch_items(src, session)
    except SourceFailure as e:
        run.failure = str(e)
        log(f"    ! شکست منبع: {e}")
        return run

    if not items:
        log("    هیچ آیتمی نیامد")
        return run

    seen: dict = state.setdefault("seen", {}).setdefault(src.key, {})

    for item in items:
        if run.made >= args.limit:
            break
        if item["id"] in seen and not args.force:
            continue
        if args.since and item.get("published", "")[:10] < args.since:
            continue

        title = item["title"][:70]
        log(f"    • {title}")

        # ویدیوی کوتاه — پیش از اجرای خشک هم، تا پیش‌نمایش همان اجرای واقعی باشد
        duration = "—"
        if src.kind in ("youtube", "playlist"):
            secs, why = video_duration(item["id"], session)
            if secs is not None and secs <= SHORT_MAX_SECONDS:
                run.short += 1
                log(f"      — رد شد: کوتاه، {fmt_ts(secs)}")
                if not args.dry_run:
                    seen[item["id"]] = {"title": item["title"], "rejected": "کوتاه",
                                        "seconds": secs,
                                        "at": datetime.now(UTC).strftime("%Y-%m-%d")}
                continue
            if secs is None:
                run.unknown_duration += 1
                duration = f"نامعلوم — {why}"
                log(f"      ⚠ مدت نامعلوم — {why}؛ رد نشد")
            else:
                duration = fmt_ts(secs)

        if args.dry_run:
            run.made += 1
            continue

        gap = None
        if src.kind in ("youtube", "playlist"):
            try:
                segs, method = fetch_transcript(item["id"], src.lang)
            except TranscriptBlocked as e:
                run.failure = f"یوتیوب مسدود کرد — {e}؛ ویدیوهای بعدی این منبع امتحان نشد"
                log(f"      ! {run.failure}")
                break
            except Exception as e:
                msg = f"{title} — {type(e).__name__}: {e}"
                run.item_errors.append(msg)
                log(f"      ! خطا: {msg}")
                continue
            if not segs and args.whisper:
                log("      زیرنویس نبود → ویسپر")
                segs, method = whisper_fallback(item["url"], args.whisper_model)
            if not segs:
                run.no_text.append(f"{title} — {method}")
                log(f"      — رد شد: {method}")
                continue
        else:   # rss یا index — هر دو مقاله‌اند
            txt, method = fetch_article_text(item["url"], session)
            if not txt.strip():
                msg = f"{title} — {method}"
                run.item_errors.append(msg)
                log(f"      ! خطا: {msg}")
                continue
            segs = [{"text": p, "start": None} for p in txt.split("\n") if p.strip()]
            gap = text_gap(txt)
            if gap:
                run.incomplete += 1
                log(f"      ⚠ متن ناقص — {gap}")

        fname, ncands, date = write_documents(src, item, segs, method, outdir, gap=gap,
                                              duration=duration, min_strength=args.min_strength)
        seen[item["id"]] = {"title": item["title"], "file": fname, "at": date}
        run.made += 1
        log(f"      ✓ {method} — {ncands} نامزد → {fname}")
        time.sleep(args.sleep)

    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="موتور جمع‌آوری منابع رادار")
    ap.add_argument("--config", default="analysts.yml")
    ap.add_argument("--out", default="intake")
    ap.add_argument("--state", default="intake/.state.json")
    ap.add_argument("--source", action="append", help="فقط این کلید(ها)")
    ap.add_argument("--role", help="فقط منابع با این جایگاه")
    ap.add_argument("--limit", type=int, default=5, help="حداکثر آیتم تازه از هر منبع")
    ap.add_argument("--since", help="فقط بعد از این تاریخ YYYY-MM-DD")
    ap.add_argument("--min-strength", type=int, default=2, dest="min_strength")
    ap.add_argument("--whisper", action="store_true", help="رونویسی صوتی اگر زیرنویس نبود")
    ap.add_argument("--whisper-model", default="small", dest="whisper_model")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--force", action="store_true", help="دوباره‌سازی موارد دیده‌شده")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    missing = missing_deps(args.whisper)
    if missing:
        log("! اجرا متوقف شد — وابستگی نصب نیست:")
        for m in missing:
            if m == "ffmpeg":
                log("    • ffmpeg نصب نیست — برنامه جدا، نه بسته پایتون؛ فقط برای --whisper لازم است")
            else:
                log(f"    • {m}")
        log("  نصب:  pip install -r requirements-intake.txt")
        return 2

    outdir = Path(args.out)
    statepath = Path(args.state)
    try:
        state = load_state(statepath)
    except IntakeError as e:
        log(f"! اجرا متوقف شد — {e}")
        log("  هیچ چیز نوشته نشد.")
        return 2
    outdir.mkdir(parents=True, exist_ok=True)

    chosen = load_sources(Path(args.config))
    if args.source:
        chosen = [s for s in chosen if s.key in args.source]
    if args.role:
        chosen = [s for s in chosen if s.role == args.role]
    sources = [s for s in chosen if s.enabled or args.source]

    if not sources:
        log("هیچ منبع فعالی انتخاب نشد.")
        return 1

    started = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    report = RunReport(started=started, dry_run=args.dry_run,
                       disabled=[s for s in chosen if not s.enabled and not args.source])

    log("=" * 62)
    log(f"  رادار — موتور جمع‌آوری  v{VERSION}")
    log(f"  {started} | {len(sources)} منبع")
    log("=" * 62)

    for src in sources:
        try:
            report.sources.append(process_source(src, make_session(), outdir, state, args))
        except KeyboardInterrupt:
            log("\nمتوقف شد.")
            break
        except Exception as e:
            # خطای پیش‌بینی‌نشده هم بقیه را متوقف نمی‌کند، ولی با نوعش ثبت می‌شود
            r = SourceRun(src.key, src.name_fa,
                          failure=f"خطای پیش‌بینی‌نشده — {type(e).__name__}: {e}")
            report.sources.append(r)
            log(f"    ! {r.failure}")

    problems: list[str] = []
    if not args.dry_run:
        save_state(statepath, state)
        problems = rebuild_index(outdir, report)

    log("")
    log("\n".join(run_summary(report)))
    if problems:
        log("### سند ناخوانا\n")
        log("\n".join(f"- {p}" for p in problems))
    if not args.dry_run:
        log(f"\nفهرست: {outdir}/INDEX.md")
    if report.failed or problems:
        log("\n! کد خروج ۳ — دست‌کم یک منبع یا سند شکست خورد؛ فهرست بالا.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
