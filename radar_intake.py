#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_intake.py  —  نسخه ۱.۰
موتور جمع‌آوری منابع تحلیلی برای چارچوب رادار ۵.۳

فلسفه:
    این اسکریپت «تحلیل» نمی‌کند. فقط متن خام را می‌آورد، شناسنامه می‌زند،
    و خطوطی را که *شاید* ادعای قابل‌تسویه باشند علامت می‌گذارد.
    داوری با انسان و با موتور تحلیل است، نه با این ابزار.

    قانون مادر رادار: «هرگز عدد نساز.» این اسکریپت هیچ عددی استنتاج نمی‌کند.
    فقط اعدادی را که در متن اصلی آمده‌اند نقل می‌کند.

محیط اجرا:
    گوگل کولب (دسترسی آزاد به اینترنت). خروجی در پوشه intake/ و سپس
    ارسال به مخزن گیت‌هاب تا موتور تحلیل بتواند آن را بخواند.

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
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# وابستگی‌های اختیاری — نبودشان اسکریپت را نمی‌کشد، فقط قابلیت را خاموش می‌کند
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
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:
    YouTubeTranscriptApi = None
    NoTranscriptFound = TranscriptsDisabled = VideoUnavailable = Exception


VERSION = "1.3"
UTC = timezone.utc
USER_AGENT = "radar-intake/1.0 (research; contact via github.com/AmirShalbaf/radar)"


# ===========================================================================
# ۱ — نرمال‌سازی متن
# ===========================================================================

# ارقام فارسی و عربی به لاتین. بدون این کار، هیچ الگوی عددی روی متن فارسی
# گیر نمی‌افتد و بخش نامزد ادعا برای منابع فارسی عملاً خالی می‌ماند.
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_LATIN_DIGITS = "0123456789"

_DIGIT_MAP = {ord(p): l for p, l in zip(_PERSIAN_DIGITS, _LATIN_DIGITS)}
_DIGIT_MAP.update({ord(a): l for a, l in zip(_ARABIC_DIGITS, _LATIN_DIGITS)})

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

    def to_row(self) -> str:
        ts = self.timestamp or "—"
        nums = "، ".join(self.numbers[:4]) if self.numbers else "—"
        cats = "، ".join(self.categories)
        stars = "★" * self.strength + "☆" * (5 - self.strength)
        safe = self.text.replace("|", "/").replace("\n", " ").strip()
        if len(safe) > 220:
            safe = safe[:217] + "..."
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
        log(f"    ! دریافت صفحه کانال ناموفق: {e}")
        return None

    html = r.text

    # ۱ — پیوند متعارف: یکتا و متعلق به صاحب صفحه
    m = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']'
        r'https://www\.youtube\.com/channel/(UC[\w-]{22})',
        html,
    )
    if m:
        return m.group(1)

    # ۲ — og:url — همان نقش
    m = re.search(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']'
        r'https://www\.youtube\.com/channel/(UC[\w-]{22})',
        html,
    )
    if m:
        return m.group(1)

    # ۳ — externalId داخل بلوک فراداده کانال (نه هر externalId در صفحه)
    anchor = html.find("channelMetadataRenderer")
    if anchor != -1:
        m = re.search(r'"externalId"\s*:\s*"(UC[\w-]{22})"', html[anchor : anchor + 4000])
        if m:
            return m.group(1)

    # ۴ — آخرین تلاش: تگ فراداده استاندارد
    m = re.search(r'<meta[^>]+itemprop=["\']identifier["\'][^>]+content=["\'](UC[\w-]{22})', html)
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
        log("    ! feedparser نصب نیست")
        return []

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
        log("    ! شناسه کانال پیدا نشد")
        return []

    feed = feedparser.parse(YT_FEED.format(cid=cid))
    items = []
    for e in feed.entries:
        vid = getattr(e, "yt_videoid", None) or ""
        if not vid:
            m = re.search(r"v=([\w-]{11})", getattr(e, "link", ""))
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


def fetch_transcript(video_id: str, langs: list[str]) -> tuple[list[dict], str]:
    """
    برمی‌گرداند (قطعات، روش).
    ترتیب اولویت: زیرنویس دستی → زیرنویس خودکار → ترجمه‌شده.
    زیرنویس دستی کیفیت به‌مراتب بالاتری دارد و در شناسنامه ثبت می‌شود.
    """
    if YouTubeTranscriptApi is None:
        return [], "کتابخانه نصب نیست"
    try:
        listing = _get_transcript_list(video_id)
    except (TranscriptsDisabled, VideoUnavailable) as e:
        return [], f"در دسترس نیست ({type(e).__name__})"
    except Exception as e:
        return [], f"خطا ({e.__class__.__name__}: {e})"

    # ۱ — دستی
    try:
        t = listing.find_manually_created_transcript(langs)
        return _snippets_to_dicts(t.fetch()), f"زیرنویس دستی [{t.language_code}]"
    except Exception:
        pass
    # ۲ — خودکار
    try:
        t = listing.find_generated_transcript(langs)
        return _snippets_to_dicts(t.fetch()), f"زیرنویس خودکار [{t.language_code}]"
    except Exception:
        pass
    # ۳ — هر زبانی که هست، ترجمه‌شده
    try:
        for t in listing:
            try:
                tr = t.translate(langs[0])
                return _snippets_to_dicts(tr.fetch()), f"ترجمه ماشینی از [{t.language_code}]"
            except Exception:
                continue
    except Exception:
        pass
    # ۴ — هر زبانی، بدون ترجمه (بهتر از هیچ)
    try:
        for t in listing:
            try:
                return _snippets_to_dicts(t.fetch()), f"زیرنویس [{t.language_code}] — زبان درخواستی نبود"
            except Exception:
                continue
    except Exception:
        pass
    return [], "زیرنویس یافت نشد"


def whisper_fallback(video_url: str, model_size: str = "small") -> tuple[list[dict], str]:
    """
    پشتیبان: اگر زیرنویس نبود، صدا را بگیر و رونویسی کن.
    فقط در کولب با پردازنده گرافیکی معنا دارد. کند و پرهزینه است، پس پیش‌فرض خاموش.
    """
    try:
        import yt_dlp
        from faster_whisper import WhisperModel
    except ImportError:
        return [], "ویسپر نصب نیست"

    tmp = Path("/tmp/radar_audio")
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
    m = re.search(r"[?&]list=([\w-]+)", raw or "")
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
        log("    ! شناسه پلی‌لیست خالی است")
        return []

    # مسیر ۱ — شمارش کامل
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
        log("    yt-dlp نصب نیست → پشتیبان خوراک (سقف ۱۵ مورد)")
    except Exception as e:
        log(f"    شمارش کامل ناموفق ({e.__class__.__name__}) → پشتیبان خوراک")

    # مسیر ۲ — خوراک
    if feedparser is None:
        return []
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?playlist_id={pid}")
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
        log(f"    ! دریافت صفحه فهرست ناموفق: {e.__class__.__name__}")
        return []

    base_m = re.match(r"(https?://[^/]+)", src.url)
    base = base_m.group(1) if base_m else ""
    pat = re.compile(src.link_pattern or r'href="(/insights/[\w\-]+)"')

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
        log("    ! هیچ پیوند مقاله‌ای با الگوی فعلی پیدا نشد")
    return items


def fetch_rss_items(src: Source, session) -> list[dict]:
    if feedparser is None:
        log("    ! feedparser نصب نیست")
        return []
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
                "published": getattr(e, "published", getattr(e, "updated", "")),
                "author": getattr(e, "author", src.name_en or src.name_fa),
            }
        )
    return items


def fetch_article_text(url: str, session) -> tuple[str, str]:
    """متن تمیز مقاله. اول trafilatura، بعد پشتیبان ساده."""
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
        except Exception:
            pass
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        html = r.text
        html = re.sub(r"(?is)<(script|style|nav|footer|header|aside).*?</\1>", " ", html)
        txt = re.sub(r"(?s)<[^>]+>", " ", html)
        txt = re.sub(r"&nbsp;?", " ", txt)
        txt = collapse_ws(txt)
        return txt, "استخراج ساده HTML"
    except Exception as e:
        return "", f"ناموفق ({e.__class__.__name__})"


# ===========================================================================
# ۶ — نوشتن خروجی
# ===========================================================================

def slugify(text: str, maxlen: int = 40) -> str:
    text = re.sub(r"[^\w\u0600-\u06FF\s-]", "", text or "").strip()
    text = re.sub(r"\s+", "-", text)
    return text[:maxlen].strip("-") or "untitled"


def build_document(
    src: Source,
    item: dict,
    segments: list[dict],
    method: str,
    candidates: list[ClaimCandidate],
) -> str:
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
        f"تاریخ انتشار: {item.get('published','—')}",
        f"تاریخ جمع‌آوری: {collected}",
        f"روش استخراج: {method}",
        "برچسب معرفتی: نقل‌شده (Reported)",
        f"تعداد کلمه: {words}",
        f"نامزد ادعا: {len(candidates)}",
        f"تعارض منافع: {src.conflict or 'ثبت‌نشده'}",
        f"هم‌خطی با: {src.collinear_with or '—'}",
        f"ساخته‌شده با: radar_intake {VERSION}",
        "---",
        "",
        "> **هشدار اجباری رادار:** این متن *داده* نیست، *نقل‌شده* است.",
        "> هیچ عددی از این فایل مستقیم وارد موتور امتیازدهی نمی‌شود.",
        "> اعداد فقط از اسکریپت‌های داده (radar_fetch3 / radar_scan) می‌آیند.",
        "> رونویسی خودکار خطا دارد؛ هر عدد کلیدی باید در ویدئو/مقاله اصلی تأیید شود.",
        "",
    ]

    mid = ["## نامزدهای ادعا (خودکار — تأییدنشده)", ""]
    if candidates:
        mid += [
            "قدرت = چقدر شبیه ادعای قابل‌تسویه است. سه جزء لازم: جهت، آستانه عددی، مهلت.",
            "",
            "| # | زمان | قدرت | دسته | اعداد | متن |",
            "|---|---|---|---|---|---|",
        ]
        mid += [c.to_row() for c in candidates]
    else:
        mid += [
            "هیچ نامزدی با آستانه فعلی پیدا نشد.",
            "",
            "**این خودش یک داده است:** منبعی که ادعای عددی و تاریخ‌دار نمی‌دهد،",
            "قابل تسویه نیست و نمی‌تواند وارد دفتر کالیبراسیون شود.",
        ]
    mid += ["", "---", "", "## متن کامل", ""]

    return "\n".join(head + mid) + "\n" + body + "\n"


# ===========================================================================
# ۷ — وضعیت و فهرست
# ===========================================================================

def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_index(outdir: Path) -> None:
    """فهرست خوانا از همه فایل‌های جمع‌آوری‌شده. این همان چیزی است که اول می‌خوانم."""
    rows = []
    for f in sorted(outdir.rglob("*.md")):
        if f.name == "INDEX.md":
            continue
        meta = {}
        try:
            txt = f.read_text(encoding="utf-8")
            if txt.startswith("---"):
                block = txt.split("---", 2)[1]
                for line in block.strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
        except Exception:
            continue
        rows.append(
            "| {} | {} | {} | {} | {} | `{}` |".format(
                meta.get("تاریخ انتشار", "—")[:10],
                meta.get("منبع", "—"),
                meta.get("جایگاه در رادار", "—"),
                meta.get("نامزد ادعا", "۰"),
                (meta.get("عنوان", "—") or "—")[:60],
                f.relative_to(outdir).as_posix(),
            )
        )
    header = [
        "# فهرست جمع‌آوری رادار",
        "",
        f"آخرین به‌روزرسانی: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"تعداد سند: {len(rows)}",
        "",
        "| تاریخ | منبع | جایگاه | نامزد | عنوان | فایل |",
        "|---|---|---|---|---|---|",
    ]
    (outdir / "INDEX.md").write_text(
        "\n".join(header + sorted(rows, reverse=True)) + "\n", encoding="utf-8"
    )


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


def process_source(
    src: Source, session, outdir: Path, state: dict, args
) -> int:
    log(f"\n▶ {src.name_fa}  [{src.role}]")
    if src.kind == "youtube":
        items = fetch_youtube_items(src, session)
    elif src.kind == "playlist":
        items = fetch_playlist_items(src, session)
    elif src.kind == "index":
        items = fetch_index_items(src, session)
    else:
        items = fetch_rss_items(src, session)

    if not items:
        log("    هیچ آیتمی برنگشت")
        return 0

    seen: dict = state.setdefault("seen", {}).setdefault(src.key, {})
    made = 0

    for item in items:
        if made >= args.limit:
            break
        if item["id"] in seen and not args.force:
            continue
        if args.since and item.get("published", "")[:10] < args.since:
            continue

        log(f"    • {item['title'][:70]}")
        if args.dry_run:
            made += 1
            continue

        if src.kind in ("youtube", "playlist"):
            segs, method = fetch_transcript(item["id"], src.lang)
            if not segs and args.whisper:
                log("      زیرنویس نبود → ویسپر")
                segs, method = whisper_fallback(item["url"], args.whisper_model)
        else:   # rss یا index — هر دو مقاله‌اند
            txt, method = fetch_article_text(item["url"], session)
            segs = [{"text": p, "start": None} for p in txt.split("\n") if p.strip()]

        if not segs:
            log(f"      ! رد شد: {method}")
            continue

        cands = extract_claim_candidates(segs, min_strength=args.min_strength)
        doc = build_document(src, item, segs, method, cands)

        sub = outdir / src.key
        sub.mkdir(parents=True, exist_ok=True)
        date = (item.get("published") or "")[:10] or datetime.now(UTC).strftime("%Y-%m-%d")
        fname = f"{date}_{slugify(item['title'])}_{item['id'][:6]}.md"
        (sub / fname).write_text(doc, encoding="utf-8")

        seen[item["id"]] = {"title": item["title"], "file": fname, "at": date}
        made += 1
        log(f"      ✓ {method} — {len(cands)} نامزد → {fname}")
        time.sleep(args.sleep)

    return made


def main() -> int:
    ap = argparse.ArgumentParser(description="موتور جمع‌آوری منابع رادار ۵.۳")
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
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    statepath = Path(args.state)
    state = load_state(statepath)

    sources = load_sources(Path(args.config))
    if args.source:
        sources = [s for s in sources if s.key in args.source]
    if args.role:
        sources = [s for s in sources if s.role == args.role]
    sources = [s for s in sources if s.enabled or args.source]

    if not sources:
        log("هیچ منبع فعالی انتخاب نشد.")
        return 1

    log("=" * 62)
    log(f"  رادار — موتور جمع‌آوری  v{VERSION}")
    log(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | {len(sources)} منبع")
    log("=" * 62)

    total = 0
    for src in sources:
        try:
            total += process_source(src, make_session(), outdir, state, args)
        except KeyboardInterrupt:
            log("\nمتوقف شد.")
            break
        except Exception as e:
            log(f"    ! خطای منبع {src.key}: {e.__class__.__name__}: {e}")

    if not args.dry_run:
        save_state(statepath, state)
        rebuild_index(outdir)

    log("\n" + "=" * 62)
    if args.dry_run:
        log(f"  اجرای خشک — {total} مورد *ساخته می‌شد*. هیچ فایلی نوشته نشد.")
        log("  برای اجرای واقعی، --dry-run را بردار.")
    else:
        log(f"  {total} سند تازه ساخته شد → {outdir}/")
        log(f"  فهرست: {outdir}/INDEX.md")
    log("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
