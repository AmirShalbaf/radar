#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_frames.py  —  نسخه ۱.۱ — چشم رادار، نشست ۶
فریم‌های نمودار از ویدیوی تحلیل‌گر، کنار متن همان لحظه.

نسخه‌ها — هر تغییر انتخاب لحظه نسخه را بالا می‌برد، چون شناسه فریم را عوض می‌کند:
    ۱.۰  ایستگاه ۱ نشست ۶ — ماسک بسامدی روی همه گام‌ها.
    ۱.۱  ماسک «گام آرام»، 01197ac. کارت‌های نشست ۶ با ۱.۰ ساخته شدند و
         شناسه‌های کوون با این نسخه بازتولید نمی‌شوند — رویداد ۵۹.

فلسفه:
    این اسکریپت نمودار را «نمی‌خواند». فقط لحظه‌ها را انتخاب می‌کند، فریم
    1080p را می‌گیرد و کنار متن همان لحظه می‌گذارد. خواندن فریم کار مدل
    است، در نشست — هیچ نویسه‌خوانی (OCR) در این کد نیست. عدد غلط از عدد
    نداشتن بدتر است.

دو گذر:
    ۱ — نسخه کم‌کیفیت کل ویدیو، فقط برای یافتن لحظه‌ها.
    ۲ — تکه‌های کوتاه 1080p، فقط برای لحظه‌های انتخاب‌شده.

لحظه‌ها — انحراف آگاهانه از PLAN، ایستگاه ۱ نشست ۶:
    تشخیص صحنه ffmpeg روی نمودار تیره تریدینگ‌ویو کور بود — بیشینه امتیاز
    صحنه در ۳۰۷۸۸ فریم ویدیوی کوون 0.203؛ آستانه ۰.۳ صفر لحظه داد. جایش
    «حالت ساکن»: هر نیم ثانیه کسر پیکسل‌های عوض‌شده، با ماسک خودکار ناحیه
    پرجنبش — دوربین چهره، قیمت زنده. حالت ساکن یعنی دست‌کم ۱.۵ ثانیه
    بی‌تغییر. تحلیل در ۳۲۰×۱۸۰ است: در این اندازه نشانگر صلیبی موس زیر
    آستانه می‌رود ولی خط کشیده‌شده می‌ماند.

بودجه — تأیید کاربر:
    اولویت ۱  نامزد ادعا: لحظه خودش، و حالت متمایز قبل و بعد در ±۱۰ ثانیه.
              سقف ۱۲. نامزدی که تنها عددش سال است اولویت ۱ نمی‌گیرد — ک۵۵.
    اولویت ۲  حالت ساکن بلند، به ترتیب مدت — جایی که تحلیل‌گر مکث کرد.
    اولویت ۳  پرکننده شکاف: بازه بالای ۱۲۰ ثانیه بی‌فریم. سقف ۳.
    سقف کل   --max-frames، پیش‌فرض ۲۵.

حذف تکراری: اول زمانی — دو لحظه در یک حالت ساکن یکی‌اند. بعد ادراکی —
تصویر کوچک ۶۴×۳۶ روی ناحیه ماسک‌نشده، برای بازگشت به همان نما. اثر
انگشت تفاضلی (dHash) سنجیده و رد شد: نویز درون یک حالت ساکن تا ۱۵ بیت از
۶۴، و تغییر واقعی از ۱ بیت.

خروجی — فقط محلی، در .gitignore؛ تصویر و متن ویدیو مال صاحبش است:
    frames/<video_id>/<frame_id>.jpg
    frames/<video_id>/frames.json       فهرست ماشینی
    frames/<video_id>/FRAMES.md         هر فریم کنار متن همان لحظه
کارت نمودار — عمومی، چون خوانده ماست نه تصویر:
    intake/charts/<منبع>/<video_id>.json   با اعتبارسنج همین فایل

محیط اجرا:
    فقط لپ‌تاپ، مثل radar_intake.py — یوتیوب آی‌پی مرکز داده را می‌بندد.
    yt-dlp و numpy کتابخانه‌اند؛ ffmpeg و ffprobe برنامه‌اند و جدا نصب
    می‌شوند. اگر یکی نبود، اجرا از همان آغاز با نامش می‌ایستد، کد ۲.
    حافظه: فریم‌های تحلیل حدود ۰.۴ گیگابایت برای هر ساعت ویدیو.

اجرا:
    python radar_frames.py intake/benjamin_cowen/<سند>.md
    python radar_frames.py <سند> --max-frames 15
    python radar_frames.py <سند> --card-template      # قالب کارت، محلی
    python radar_frames.py --validate intake/charts/<منبع>/<video_id>.json

کد خروج: ۰ سالم؛ ۲ پیش‌نیاز یا ورودی یا کارت نامعتبر؛ ۳ دریافت یا استخراج.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from radar_text import fa

VERSION = "1.1"           # ثابت‌های انتخاب پایین با نسخه قفل‌اند — آزمون بخش ۷
UTC = timezone.utc

# ═══════════════ ثابت‌ها — همه از سنجش ایستگاه ۱ نشست ۶ ═══════════════

ANALYSIS_W, ANALYSIS_H = 320, 180
SAMPLE_FPS = 2
PIX_DELTA = 25            # تغییر روشنایی که «عوض‌شده» شمرده می‌شود
MASK_BLOCK = 10           # بلوک ماسک خودکار، پیکسل
MASK_FREQ = 0.02          # بلوکی که در بیش از ۲٪ گام‌ها عوض شود، پرجنبش است
MASK_MIN_CHANGES = 5      # و دست‌کم ۵ بار — در ویدیوی کوتاه یک خط‌کشی خودش ۲٪ گام‌هاست
QUIET_Q = 50              # بسامد فقط در گام‌هایی تا این صدک تغییر کل قاب شمرده می‌شود
MASK_WARN = 0.30          # سهم ماسک بالای این یعنی شاید خود نمودار ماسک شده
STILL = 0.002             # گام زیر این ساکن است
MIN_STILL_SAMPLES = 3     # ۱.۵ ثانیه در ۲ نمونه در ثانیه
MERGE_DIFF = 0.003        # دو حالت همسایه با تفاوت کمتر، یکی‌اند — نقطه نشانگر، برچسب محور
THUMB_W, THUMB_H = 64, 36
THUMB_DELTA = 12
# تصویر کوچک با تفاوت کمتر از این سهم خانه‌ها، تکراری است — فقط میان حالت‌های
# ناهمسایه. واسنجی ویدیوی کوون: نویز درون حالت p90 0.0052؛ خط‌کشی میان دو حالت
# همسایه p10 0.0083 و کمینه 0.0005. پس همسایه‌ها را سنجش پیکسلی ادغام جدا
# کرده و تصویر کوچک فقط بازگشت به همان نما را می‌گیرد. با 0.01 هفت از ۲۵ خط‌کشی
# همسایه حذف می‌شد.
DUP_FRAC = 0.005
SNAP_WINDOW = 3.0         # لحظه ادعای وسط حرکت به نزدیک‌ترین نمونه ساکن در این فاصله
NEIGHBOR_WINDOW = 10.0
TIER1_CAP = 12
GAP_MAX = 120.0
GAP_CAP = 3
DEFAULT_MAX_FRAMES = 25
SECTION_LEN = 2           # ثانیه، تکه 1080p برای هر ثانیه انتخاب‌شده
JPEG_Q = 2                # کیفیت ffmpeg، حدود ۲۰۰ کیلوبایت در 1080p
TRANSCRIPT_WINDOW = 15.0  # متن ±۱۵ ثانیه کنار هر فریم در FRAMES.md

LOW_FORMAT = "bv*[height<=360][vcodec^=avc1]/bv*[height<=360]/wv*"
HIGH_FORMAT = "bv*[height=1080][vcodec^=avc1]/bv*[height=1080]/bv*[height<=1080]"
TARGET_HEIGHT = 1080

FRAMES_DIR = "frames"
CHARTS_DIR = Path("intake") / "charts"
LOCAL_DIR = "_local"      # همان radar_intake.LOCAL_DIR — آزمون برابری قفلش می‌کند
FULL_TEXT = "## متن کامل"
CANDIDATE_HEAD = "| # | زمان | قدرت | دسته | اعداد | متن |"

# دامنه ورودی اسکی است: زمان ویدیو، سال، شناسه. \d رقم فارسی را هم می‌گیرد.
_TS_RE = re.compile(r"^(?:([0-9]+):)?([0-9]{1,2}):([0-9]{2})$")
_LINE_RE = re.compile(r"^\[((?:[0-9]+:)?[0-9]{1,2}:[0-9]{2})\]\s?(.*)$")
_YEAR_RE = re.compile(r"^[0-9]{4}$")
YEAR_MIN = 2009           # نخستین سال بیت‌کوین؛ سقف: سال انتشار به‌علاوه YEAR_AHEAD
YEAR_AHEAD = 5

REQUIRED_MODULES = {"yt_dlp": "yt-dlp"}
REQUIRED_PROGRAMS = ("ffmpeg", "ffprobe")


class FramesError(Exception):
    """خطای اجرا — دریافت، استخراج. کد ۳."""


class DocError(Exception):
    """سند ورودی نامعتبر یا ناقص. کد ۲."""


def missing_deps() -> list[str]:
    """چیزهایی که اجرا بی‌آن‌ها نتیجه غلط یا هیچ می‌دهد — نام بسته یا برنامه."""
    out = [pkg for mod, pkg in REQUIRED_MODULES.items()
           if importlib.util.find_spec(mod) is None]
    out += [p for p in REQUIRED_PROGRAMS if shutil.which(p) is None]
    return out


# ═══════════════ ۱ — خواندن سند radar_intake ═══════════════

def parse_ts(s: str) -> float:
    """«06:45» یا «1:02:03» به ثانیه. ورودی بد خطای صریح است."""
    m = _TS_RE.match((s or "").strip())
    if not m:
        raise DocError(f"زمان نامعتبر: {s!r}")
    h, mm, ss = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return float(h * 3600 + mm * 60 + ss)


def fmt_t(t: float) -> str:
    """زمان برای نمایش: 06:53 یا 1:02:03 — مثل fmt_ts در radar_intake."""
    s = int(t)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def frame_id(video_id: str, t: float) -> str:
    """شناسه فریم: شناسه ویدیو و زمان تا یک‌دهم ثانیه — 2C70_Ms3V9A_06m53.0s."""
    d = round(t, 1)
    h, rem = divmod(d, 3600)
    m, s = divmod(rem, 60)
    head = f"{int(h)}h" if h else ""
    return f"{video_id}_{head}{int(m):02d}m{s:04.1f}s"


@dataclass
class Candidate:
    row: int
    time: str
    seconds: float
    strength: int
    categories: list[str]
    numbers: list[str]
    text: str
    ref_year: int | None = None   # سال انتشار سند؛ None یعنی سال جاری وقت جهانی

    def is_year(self, n: str) -> bool:
        """
        سال فقط YEAR_MIN تا سال مرجع به‌علاوه YEAR_AHEAD — تأیید کاربر، ایستگاه ۲.
        پیش از این هر 19xx و 20xx سال بود و قیمت ARB «۲۰۹۰» سال خوانده شد.
        محدودیت، ک۵۵: قیمتی مثل ۲۰۲۰ برای اتر هنوز سال است؛ رفع کامل با بافت
        جمله در نشست ۵. سال شمسی شناخته نمی‌شود.
        """
        ref = self.ref_year or datetime.now(UTC).year
        return bool(_YEAR_RE.match(n)) and YEAR_MIN <= int(n) <= ref + YEAR_AHEAD

    @property
    def year_only(self) -> bool:
        """تنها عددش سال است — ک۵۵."""
        return bool(self.numbers) and all(self.is_year(n) for n in self.numbers)


def parse_candidates(text: str, ref_year: int | None = None) -> list[Candidate]:
    """جدول نامزد ادعای radar_intake. ستون متن «|» ندارد — to_row آن را «/» می‌کند."""
    lines = text.splitlines()
    try:
        start = lines.index(CANDIDATE_HEAD)
    except ValueError:
        return []
    out = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            raise DocError(f"ردیف نامزد با {len(cells)} ستون: {line[:80]!r}")
        row, ts, stars, cats, nums, body = cells
        if ts == "—":
            continue                     # نامزد بی‌زمان فریم ندارد
        out.append(Candidate(
            row=int(row), time=ts, seconds=parse_ts(ts),
            strength=stars.count("★"),
            categories=[c for c in cats.split("، ") if c],
            numbers=[] if nums == "—" else [n for n in nums.split("، ") if n],
            text=body, ref_year=ref_year))
    return out


def parse_transcript(body: str) -> list[tuple[float, str]]:
    out = []
    for line in body.splitlines():
        m = _LINE_RE.match(line.strip())
        if m:
            out.append((parse_ts(m.group(1)), m.group(2)))
    return out


def _split_front(txt: str) -> tuple[dict, str]:
    meta, body = {}, txt
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2]
    return meta, body


@dataclass
class VideoDoc:
    public_rel: str          # نسبت به ریشه مخزن، با /
    meta: dict
    doc_id: str
    source: str              # نام پوشه منبع
    video_id: str
    url: str
    title: str
    candidates: list[Candidate]
    transcript: list[tuple[float, str]]


def load_doc(path: Path, url: str | None = None) -> VideoDoc:
    """
    سند عمومی یا محلی radar_intake. متن کامل و همه نامزدها فقط در نسخه محلی
    است — نشست ۴ — پس نسخه محلی لازم است؛ نبودش خطای صریح است، نه کار با
    ده نامزد عمومی.
    """
    path = Path(path)
    if not path.exists():
        raise DocError(f"سند نیست: {path}")
    parts = path.resolve().parts
    if "intake" not in parts:
        raise DocError(f"سند باید زیر intake/ باشد: {path}")
    i = len(parts) - 1 - parts[::-1].index("intake")
    intake = Path(*parts[:i + 1])
    rel = Path(*parts[i + 1:])
    if rel.parts and rel.parts[0] == LOCAL_DIR:
        rel = Path(*rel.parts[1:])
    public, local = intake / rel, intake / LOCAL_DIR / rel
    if not local.exists():
        raise DocError(f"متن محلی نیست: {local} — فریم بی‌متن همان لحظه ساخته نمی‌شود")
    meta, body = _split_front(local.read_text(encoding="utf-8"))
    if FULL_TEXT not in body:
        raise DocError(f"بخش «{FULL_TEXT}» در {local} نیست")
    head, full = body.split(FULL_TEXT, 1)
    url = url or meta.get("نشانی", "")
    from radar_one import video_id as _video_id     # تنها منبع الگوی شناسه
    vid = _video_id(url)
    if not vid:
        raise DocError(f"شناسه ویدیوی یوتیوب از نشانی بیرون نیامد: {url!r}")
    transcript = parse_transcript(full)
    if not transcript:
        raise DocError(f"متن کامل {local} زمان [MM:SS] ندارد")
    published = meta.get("تاریخ انتشار", "")
    ref_year = int(published[:4]) if re.match(r"[0-9]{4}-", published) else None
    return VideoDoc(
        public_rel=("intake/" + rel.as_posix()), meta=meta,
        doc_id=meta.get("شناسه", ""), source=rel.parts[0] if len(rel.parts) > 1 else "",
        video_id=vid, url=url, title=meta.get("عنوان", ""),
        candidates=parse_candidates(head, ref_year), transcript=transcript)


# ═══════════════ ۲ — تحلیل حالت ساکن روی نسخه کم‌کیفیت ═══════════════

def auto_mask(frames: np.ndarray) -> tuple[np.ndarray, float]:
    """
    ماسک خودکار ناحیه پرجنبش — دوربین چهره، قیمت زنده، شمع زنده — با یک بلوک
    گسترش کنار می‌رود. برمی‌گرداند (keep، سهم ماسک). keep یعنی پیکسل شمرده‌شده.

    «گام آرام» — تأیید کاربر، ایستگاه ۲ نشست ۶: بسامد تغییر هر بلوک فقط در
    گام‌هایی شمرده می‌شود که تغییر کل قاب تا صدک QUIET_Q است. دوربین چهره در
    گام آرام هم می‌جنبد؛ نمودار فقط در جابه‌جایی، که گام پرتغییر است. بلوکی
    ماسک می‌شود که در بیش از MASK_FREQ گام‌های آرام و دست‌کم MASK_MIN_CHANGES
    بار عوض شود. پیش از این بسامد روی همه گام‌ها بود و در کریپتوسیتی، که خود
    نمودار در ۵.۵٪ گام‌ها عوض می‌شد، ۶۲.۸٪ قاب ماسک شد؛ با گام آرام ۱۳.۰٪.
    """
    n, h, w = frames.shape
    if n < 2:
        return np.ones((h, w), bool), 0.0
    changes = []
    glob = np.zeros(n - 1)
    for i in range(1, n):
        c = np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16)) > PIX_DELTA
        glob[i - 1] = c.mean()
        changes.append(np.packbits(c))          # حافظه: یک بیت برای هر پیکسل
    quiet = glob <= np.percentile(glob, QUIET_Q)
    count = np.zeros((h, w), np.float64)
    for i in np.nonzero(quiet)[0]:
        count += np.unpackbits(changes[i], count=h * w).reshape(h, w)
    nq = int(quiet.sum())
    bh, bw = h // MASK_BLOCK, w // MASK_BLOCK
    blk = count[:bh * MASK_BLOCK, :bw * MASK_BLOCK].reshape(
        bh, MASK_BLOCK, bw, MASK_BLOCK).mean((1, 3)) > max(MASK_FREQ * nq, MASK_MIN_CHANGES)
    grown = blk.copy()
    grown[1:] |= blk[:-1]
    grown[:-1] |= blk[1:]
    grown[:, 1:] |= blk[:, :-1]
    grown[:, :-1] |= blk[:, 1:]
    masked = np.zeros((h, w), bool)
    masked[:bh * MASK_BLOCK, :bw * MASK_BLOCK] = np.kron(grown, np.ones((MASK_BLOCK, MASK_BLOCK), bool))
    return ~masked, float(masked.mean())


def changed_frac(a: np.ndarray, b: np.ndarray, keep: np.ndarray) -> float:
    n = int(keep.sum())
    if n == 0:
        return 0.0
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIX_DELTA
    return float((d & keep).sum()) / n


def step_signal(frames: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """گام i: کسر پیکسل ماسک‌نشده عوض‌شده میان نمونه i-1 و i. گام صفر صفر است."""
    out = np.zeros(len(frames))
    for i in range(1, len(frames)):
        out[i] = changed_frac(frames[i], frames[i - 1], keep)
    return out


@dataclass
class State:
    i0: int                  # نخستین نمونه، شامل
    i1: int                  # آخرین نمونه، شامل
    rep: int = -1            # نمونه نماینده

    def start(self) -> float:
        return self.i0 / SAMPLE_FPS

    def end(self) -> float:
        return self.i1 / SAMPLE_FPS

    def duration(self) -> float:
        return (self.i1 - self.i0 + 1) / SAMPLE_FPS


def still_mask(steps: np.ndarray) -> np.ndarray:
    """نمونه ساکن: گامش و گام بعدش هر دو زیر STILL — یعنی خودش وسط حرکت نیست."""
    s = steps < STILL
    s[0] = True
    nxt = np.append(s[1:], True)
    return s & nxt


def still_states(steps: np.ndarray) -> list[State]:
    """دنباله‌های بیشینه گام زیر STILL، دست‌کم MIN_STILL_SAMPLES نمونه."""
    out, start = [], None
    for i, s in enumerate(steps):
        if s < STILL or i == 0:
            start = i if start is None else start
        else:
            if start is not None and i - start >= MIN_STILL_SAMPLES:
                out.append(State(start, i - 1))
            start = i
    if start is not None and len(steps) - start >= MIN_STILL_SAMPLES:
        out.append(State(start, len(steps) - 1))
    return out


def merge_states(frames: np.ndarray, keep: np.ndarray, states: list[State]) -> list[State]:
    """
    دو حالت همسایه با تفاوت کمتر از MERGE_DIFF یکی می‌شوند: آنچه میانشان
    عوض شد نقطه نشانگر یا برچسب محور بود، نه خط. سنجش ۳۲۰×۱۸۰ ویدیوی کوون:
    حدود ۱۵ از ۱۷ گذار «فقط نقطه» ادغام می‌شوند و ۱۸ از ۲۰ خط‌کشی جدا می‌مانند.
    """
    out: list[State] = []
    for st in states:
        if out and changed_frac(frames[out[-1].i1], frames[st.i0], keep) < MERGE_DIFF:
            out[-1] = State(out[-1].i0, st.i1)
        else:
            out.append(State(st.i0, st.i1))
    return out


def pick_rep(frames: np.ndarray, keep: np.ndarray, st: State, still: np.ndarray) -> int:
    """
    نماینده: نمونه ساکنی که بیشترین تفاوت را با آغاز حالت دارد — بیشترین
    جوهر کشیده‌شده. اگر خطی وسط حالت کشیده و بعد پاک شد، همان لحظه انتخاب
    می‌شود. نمونه وسط حرکت هرگز نماینده نیست. برابری به نمونه دیرتر.
    """
    best, best_d = st.i0, -1.0
    for j in range(st.i0, st.i1 + 1):
        if not still[j]:
            continue
        d = changed_frac(frames[st.i0], frames[j], keep)
        if d >= best_d:
            best, best_d = j, d
    return best


def thumbnail(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape
    ys = np.linspace(0, h, THUMB_H + 1).astype(int)
    xs = np.linspace(0, w, THUMB_W + 1).astype(int)
    f = frame.astype(np.float32)
    return np.array([[f[ys[r]:ys[r + 1], xs[c]:xs[c + 1]].mean() for c in range(THUMB_W)]
                     for r in range(THUMB_H)], np.float32)


def thumb_keep(keep: np.ndarray) -> np.ndarray:
    """خانه تصویر کوچک شمرده می‌شود اگر بیشتر پیکسل‌هایش ماسک‌نشده باشد."""
    return thumbnail(keep.astype(np.uint8) * 255) > 127


def thumb_diff(a: np.ndarray, b: np.ndarray, tkeep: np.ndarray) -> float:
    n = int(tkeep.sum())
    if n == 0:
        return 0.0
    return float(((np.abs(a - b) > THUMB_DELTA) & tkeep).sum()) / n


@dataclass
class Analysis:
    n: int
    duration: float
    keep: np.ndarray
    mask_share: float
    steps: np.ndarray
    still: np.ndarray
    raw_states: int
    states: list[State]
    state_of: np.ndarray       # نمونه ← شماره حالت، یا -1
    thumbs: dict[int, np.ndarray] = field(default_factory=dict)
    tkeep: np.ndarray | None = None
    frames: np.ndarray | None = None

    @property
    def mask_warning(self) -> bool:
        return self.mask_share > MASK_WARN

    def thumb(self, i: int) -> np.ndarray:
        if i not in self.thumbs:
            self.thumbs[i] = thumbnail(self.frames[i])
        return self.thumbs[i]


def analyse(frames: np.ndarray) -> Analysis:
    if frames.ndim != 3 or len(frames) < 2:
        raise FramesError(f"فریم تحلیل کافی نیست: شکل {getattr(frames, 'shape', None)}")
    keep, share = auto_mask(frames)
    steps = step_signal(frames, keep)
    still = still_mask(steps)
    raw = still_states(steps)
    states = merge_states(frames, keep, raw)
    state_of = np.full(len(frames), -1, int)
    for k, st in enumerate(states):
        st.rep = pick_rep(frames, keep, st, still)
        state_of[st.i0:st.i1 + 1] = k
    return Analysis(n=len(frames), duration=len(frames) / SAMPLE_FPS, keep=keep,
                    mask_share=share, steps=steps, still=still, raw_states=len(raw),
                    states=states, state_of=state_of, tkeep=thumb_keep(keep), frames=frames)


# ═══════════════ ۳ — انتخاب لحظه‌ها و حذف تکراری ═══════════════

@dataclass
class Ref:
    doc: str
    row: int
    time: str
    role: str                # claim | before | after
    strength: int
    year_only: bool
    claim_id: str | None = None      # خالی تا نشست ۵ پرش کند

    def to_json(self) -> dict:
        return {"doc": self.doc, "row": self.row, "time": self.time, "role": self.role,
                "strength": self.strength, "year_only": self.year_only,
                "claim_id": self.claim_id}


@dataclass
class Moment:
    t: float
    sample: int
    tier: int
    reasons: list[str]
    refs: list[Ref] = field(default_factory=list)
    state: int = -1


@dataclass
class Selection:
    moments: list[Moment]
    max_frames: int
    tier1_candidates: int
    year_only_candidates: int
    dropped_by_cap: int
    gaps_filled: int
    duplicates_merged: int
    unframed: list[int] = field(default_factory=list)   # ردیف نامزدی که هیچ فریمی به آن وصل نشد


class _Picker:
    def __init__(self, an: Analysis, cap: int):
        self.an, self.cap = an, cap
        self.out: list[Moment] = []
        self.dropped = 0
        self.dups = 0

    def full(self) -> bool:
        return len(self.out) >= self.cap

    def add(self, m: Moment) -> bool:
        """درست اگر فریم تازه شد. تکراری ارجاعش را به فریم موجود می‌دهد."""
        for e in self.out:
            same_state = m.state >= 0 and m.state == e.state
            adjacent = m.state >= 0 and e.state >= 0 and abs(m.state - e.state) == 1
            if same_state or (not adjacent and thumb_diff(
                    self.an.thumb(m.sample), self.an.thumb(e.sample), self.an.tkeep) < DUP_FRAC):
                for r in m.refs:
                    if r not in e.refs:
                        e.refs.append(r)
                for why in m.reasons:
                    if why not in e.reasons:
                        e.reasons.append(why)
                self.dups += 1
                return False
        if self.full():
            self.dropped += 1
            return False
        self.out.append(m)
        return True


def _sample_at(an: Analysis, t: float) -> int:
    return max(0, min(an.n - 1, int(round(t * SAMPLE_FPS))))


def _snap(an: Analysis, t: float) -> tuple[float, int]:
    """لحظه ادعا اگر وسط حرکت بود، به نزدیک‌ترین نمونه ساکن در SNAP_WINDOW."""
    i = _sample_at(an, t)
    if an.still[i]:
        return t, i
    span = int(SNAP_WINDOW * SAMPLE_FPS)
    for d in range(1, span + 1):
        for j in (i - d, i + d):
            if 0 <= j < an.n and an.still[j]:
                return j / SAMPLE_FPS, j
    return t, i


def _state_moment(an: Analysis, k: int, tier: int, why: str) -> Moment:
    st = an.states[k]
    return Moment(t=st.rep / SAMPLE_FPS, sample=st.rep, tier=tier, reasons=[why], state=k)


def _neighbors(an: Analysis, t: float, k: int) -> tuple[int | None, int | None]:
    """حالت متمایز قبل و بعد در ±NEIGHBOR_WINDOW — تأیید کاربر، ایستگاه ۱."""
    lo = an.states[k].start() if k >= 0 else t
    hi = an.states[k].end() if k >= 0 else t
    prev = nxt = None
    for j, st in enumerate(an.states):
        if st.end() < lo and st.end() >= t - NEIGHBOR_WINDOW:
            prev = j
        if nxt is None and st.start() > hi and st.start() <= t + NEIGHBOR_WINDOW:
            nxt = j
    return prev, nxt


def select_moments(an: Analysis, doc: VideoDoc, max_frames: int = DEFAULT_MAX_FRAMES) -> Selection:
    if max_frames < 1:
        raise ValueError("max_frames باید دست‌کم ۱ باشد")
    pk = _Picker(an, max_frames)

    def ref(c: Candidate, role: str) -> Ref:
        return Ref(doc=doc.doc_id, row=c.row, time=c.time, role=role,
                   strength=c.strength, year_only=c.year_only)

    # اولویت ۱ — نامزدهای غیرسالی، قوی‌تر اول
    strong = sorted((c for c in doc.candidates if not c.year_only),
                    key=lambda c: (-c.strength, c.row))
    weak = [c for c in doc.candidates if c.year_only]
    t1_cap = min(TIER1_CAP, max_frames)
    t1 = 0
    for c in strong:
        t, i = _snap(an, c.seconds)
        k = int(an.state_of[i])
        main = Moment(t=t, sample=i, tier=1, reasons=["claim"], refs=[ref(c, "claim")], state=k)
        prev, nxt = _neighbors(an, c.seconds, k)
        group = [main]
        for j, role in ((prev, "before"), (nxt, "after")):
            if j is not None:
                m = _state_moment(an, j, 1, "claim_" + role)
                m.refs = [ref(c, role)]
                group.append(m)
        for m in group:
            if t1 >= t1_cap:
                pk.dropped += 1
                continue
            if pk.add(m):
                t1 += 1

    # اولویت ۲ — حالت ساکن بلند؛ نامزد سال‌محور فقط با مدت حالتش رقابت می‌کند
    pool: list[tuple[float, int, Moment]] = []
    for k, st in enumerate(an.states):
        pool.append((st.duration(), -st.i0, _state_moment(an, k, 2, "long_still")))
    for c in weak:
        t, i = _snap(an, c.seconds)
        k = int(an.state_of[i])
        dur = an.states[k].duration() if k >= 0 else 0.0
        pool.append((dur, -i, Moment(t=t, sample=i, tier=2, reasons=["year_only_claim"],
                                     refs=[ref(c, "claim")], state=k)))
    pool.sort(key=lambda x: (-x[0], -x[1]))
    reserve = min(GAP_CAP, max(0, max_frames - len(pk.out)))
    queue = [m for _, _, m in pool]
    pos = 0
    while pos < len(queue) and len(pk.out) < max_frames - reserve:
        pk.add(queue[pos])
        pos += 1

    # اولویت ۳ — پرکننده شکاف
    filled, tried = 0, set()
    while filled < GAP_CAP and not pk.full():
        times = sorted([0.0, an.duration] + [m.t for m in pk.out])
        gaps = sorted(((b - a, a, b) for a, b in zip(times, times[1:])
                       if b - a > GAP_MAX and (a, b) not in tried), reverse=True)
        if not gaps:
            break
        _, a, b = gaps[0]
        tried.add((a, b))
        inside = [k for k, st in enumerate(an.states) if a < st.rep / SAMPLE_FPS < b]
        if inside:
            k = max(inside, key=lambda k: an.states[k].duration())
            m = _state_moment(an, k, 3, "gap_fill")
        else:
            t, i = _snap(an, (a + b) / 2)
            m = Moment(t=t, sample=i, tier=3, reasons=["gap_fill"], state=int(an.state_of[i]))
        if pk.add(m):
            filled += 1

    # باقی ظرفیت به اولویت ۲
    while pos < len(queue):
        pk.add(queue[pos])
        pos += 1

    pk.out.sort(key=lambda m: m.t)
    framed = {r.row for m in pk.out for r in m.refs}
    return Selection(moments=pk.out, max_frames=max_frames, tier1_candidates=len(strong),
                     year_only_candidates=len(weak), dropped_by_cap=pk.dropped,
                     gaps_filled=filled, duplicates_merged=pk.dups,
                     unframed=sorted(c.row for c in doc.candidates if c.row not in framed))


# ═══════════════ ۴ — ffmpeg و yt-dlp ═══════════════

def decode_gray(video: Path, w: int = ANALYSIS_W, h: int = ANALYSIS_H,
                fps: int = SAMPLE_FPS) -> np.ndarray:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
           "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=gray",
           "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise FramesError(f"ffmpeg نتوانست {video.name} را بخواند: "
                          f"{p.stderr.decode('utf-8', 'replace').strip()[:300]}")
    n = len(p.stdout) // (w * h)
    if n < 2:
        raise FramesError(f"ffmpeg از {video.name} کمتر از دو نمونه داد")
    return np.frombuffer(p.stdout[:n * w * h], np.uint8).reshape(n, h, w)


def extract_jpeg(section: Path, offset: float, out: Path) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{offset:.3f}",
           "-i", str(section), "-frames:v", "1", "-q:v", str(JPEG_Q), "-y", str(out)]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise FramesError(f"استخراج فریم از {section.name} در {offset:.2f}s شکست خورد: "
                          f"{p.stderr.decode('utf-8', 'replace').strip()[:300]}")


def probe_height(video: Path) -> int | None:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=height", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise FramesError(f"ffprobe نتوانست {video.name} را بخواند: {p.stderr.strip()[:200]}")
    txt = p.stdout.strip()
    return int(txt) if re.fullmatch(r"[0-9]+", txt) else None


class YtDlp:
    """دریافت با رابط پایتونی yt-dlp — هم‌الگو با radar_intake. خطا بالا می‌رود."""

    def _run(self, url: str, opts: dict) -> None:
        import yt_dlp
        base = {"quiet": True, "no_warnings": True, "noprogress": True}
        try:
            with yt_dlp.YoutubeDL({**base, **opts}) as y:
                rc = y.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise FramesError(f"yt-dlp: {e}") from e
        if rc:
            raise FramesError(f"yt-dlp با کد {rc} برگشت")

    def low(self, url: str, dest: Path) -> Path:
        self._run(url, {"format": LOW_FORMAT, "outtmpl": str(dest / "low.%(ext)s")})
        got = sorted(dest.glob("low.*"))
        if not got:
            raise FramesError("نسخه کم‌کیفیت دریافت نشد")
        return got[0]

    def sections(self, url: str, starts: list[int], dest: Path) -> dict[int, Path]:
        from yt_dlp.utils import download_range_func
        ranges = [(s, s + SECTION_LEN) for s in starts]
        self._run(url, {"format": HIGH_FORMAT,
                        "outtmpl": str(dest / "sec_%(section_start)s.%(ext)s"),
                        "download_ranges": download_range_func(None, ranges)})
        out = {}
        for s in starts:
            hit = sorted(dest.glob(f"sec_{s}.*")) or sorted(dest.glob(f"sec_{s}.0.*"))
            if hit:
                out[s] = hit[0]
        return out


# ═══════════════ ۵ — خروجی ═══════════════

REASON_FA = {
    "claim": "لحظه نامزد ادعا",
    "claim_before": "حالت متمایز پیش از ادعا",
    "claim_after": "حالت متمایز پس از ادعا",
    "long_still": "حالت ساکن بلند",
    "year_only_claim": "نامزد سال‌محور — اولویت ۲، ک۵۵",
    "gap_fill": "پرکننده شکاف",
}
ROLE_FA = {"claim": "خود ادعا", "before": "پیش از ادعا", "after": "پس از ادعا"}


def manifest(doc: VideoDoc, an: Analysis, sel: Selection, files: dict[str, str],
             missing: list[str], height: int | None, now: datetime) -> dict:
    frames = []
    for m in sel.moments:
        fid = frame_id(doc.video_id, m.t)
        st = an.states[m.state] if m.state >= 0 else None
        frames.append({
            "frame_id": fid, "t": round(m.t, 1), "time": fmt_t(m.t),
            "file": files.get(fid), "tier": m.tier, "reasons": m.reasons,
            "refs": [r.to_json() for r in m.refs],
            "state": None if st is None else {
                "start": round(st.start(), 1), "end": round(st.end(), 1),
                "duration": round(st.duration(), 1)},
        })
    return {
        "schema": 1, "radar_frames": VERSION, "generated_at": now.isoformat(),
        "video_id": doc.video_id, "url": doc.url, "doc_id": doc.doc_id,
        "doc": doc.public_rel, "source": doc.source, "title": doc.title,
        "duration_s": round(an.duration, 1),
        "analysis": {
            "size": f"{ANALYSIS_W}x{ANALYSIS_H}", "fps": SAMPLE_FPS,
            "mask_share": round(an.mask_share, 4), "mask_warning": an.mask_warning,
            "still_states": an.raw_states, "merged_states": len(an.states)},
        "selection": {
            "max_frames": sel.max_frames, "selected": len(sel.moments),
            "candidates": len(doc.candidates), "tier1_candidates": sel.tier1_candidates,
            "year_only_candidates": sel.year_only_candidates,
            "dropped_by_cap": sel.dropped_by_cap, "gaps_filled": sel.gaps_filled,
            "duplicates_merged": sel.duplicates_merged, "unframed_candidates": sel.unframed},
        "high_res": {"height": height, "target": TARGET_HEIGHT},
        "missing": missing,
        "frames": frames,
    }


def render_frames_md(man: dict, doc: VideoDoc) -> str:
    """هر فریم کنار متن ±۱۵ ثانیه همان لحظه. فقط محلی."""
    a, s = man["analysis"], man["selection"]
    lines = [
        f"# فریم‌های نمودار — {doc.title}", "",
        f"- سند: `{doc.public_rel}` — شناسه `{doc.doc_id}`",
        f"- ویدیو: {doc.url}",
        f"- ساخته‌شده با radar_frames {VERSION}، {man['generated_at']}",
        "- **فقط محلی.** تصویر و متن ویدیو مال صاحبش است — `.gitignore`.",
        "- پیش از خواندن: `references/chart-reading.md`.", "",
        "| سنجه | مقدار |", "|---|---|",
        f"| مدت ویدیو | {man['duration_s']} s |",
        f"| سهم ماسک خودکار | {100 * a['mask_share']:.1f}% |",
        f"| حالت ساکن / پس از ادغام | {a['still_states']} / {a['merged_states']} |",
        f"| نامزد ادعا / اولویت ۱ / سال‌محور | {s['candidates']} / {s['tier1_candidates']} "
        f"/ {s['year_only_candidates']} |",
        f"| فریم انتخاب‌شده / سقف | {s['selected']} / {s['max_frames']} |",
        f"| کنارگذاشته به سقف | {s['dropped_by_cap']} |",
        f"| تکراری ادغام‌شده | {s['duplicates_merged']} |",
        f"| نامزد بی‌فریم | {'، '.join(str(r) for r in s['unframed_candidates']) or '—'} |",
        f"| ارتفاع فریم | {man['high_res']['height']} |", "",
    ]
    if a["mask_warning"]:
        lines += [f"> ⛔ **هشدار ماسک:** {100 * a['mask_share']:.1f}% قاب ماسک شد — بالای "
                  f"{fa(int(100 * MASK_WARN))}٪. شاید خود نمودار ماسک شده و لحظه‌ها ناقص‌اند.", ""]
    if man["missing"]:
        lines += [f"> ⛔ **فریم ناموجود:** {len(man['missing'])} — "
                  + "، ".join(f"`{x}`" for x in man["missing"]), ""]
    for f in man["frames"]:
        lines += [f"## {f['frame_id']} — {f['time']}", ""]
        lines += [f"![{f['frame_id']}]({f['file']})" if f["file"] else "**فریم دریافت نشد.**", ""]
        lines.append("- چرا: " + "، ".join(REASON_FA.get(r, r) for r in f["reasons"]))
        if f["state"]:
            lines.append(f"- حالت ساکن: {f['state']['start']} تا {f['state']['end']} s")
        for r in f["refs"]:
            lines.append(f"- نامزد ردیف {r['row']}، {r['time']}، {ROLE_FA.get(r['role'], r['role'])}"
                         f"{' — سال‌محور' if r['year_only'] else ''}")
        lines += ["", "```text"]
        for ts, txt in doc.transcript:
            if abs(ts - f["t"]) <= TRANSCRIPT_WINDOW:
                lines.append(f"[{fmt_t(ts)}] {txt}")
        lines += ["```", ""]
    return "\n".join(lines) + "\n"


def run(doc: VideoDoc, out_root: Path, max_frames: int = DEFAULT_MAX_FRAMES, *,
        downloader=None, decode: Callable = decode_gray, extract: Callable = extract_jpeg,
        height_of: Callable = probe_height, keep_work: bool = False,
        now: datetime | None = None, log: Callable = print) -> tuple[dict, int]:
    """برمی‌گرداند (فهرست، کد خروج). کد ۳ یعنی فریمی دریافت نشد — فهرست با «missing» نوشته می‌شود."""
    now = now or datetime.now(UTC)
    dl = downloader or YtDlp()
    vdir = out_root / doc.video_id
    work = vdir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    stale = list(vdir.glob("*.jpg")) + [p for p in (vdir / "frames.json", vdir / "FRAMES.md") if p.exists()]
    for p in stale:
        p.unlink()
    if stale:
        log(f"  {fa(len(stale))} فایل اجرای پیشین پاک شد")

    log("گذر ۱ — نسخه کم‌کیفیت کل ویدیو")
    low = dl.low(doc.url, work)
    an = analyse(decode(low))
    log(f"  {an.duration:.0f} s، حالت ساکن {an.raw_states}، پس از ادغام {len(an.states)}، "
        f"ماسک {100 * an.mask_share:.1f}%")
    if an.mask_warning:
        log(f"⛔ هشدار ماسک: {100 * an.mask_share:.1f}% قاب ماسک شد — بالای "
            f"{fa(int(100 * MASK_WARN))}٪. شاید خود نمودار ماسک شده است.")
    sel = select_moments(an, doc, max_frames)
    log(f"  {len(sel.moments)} لحظه از سقف {max_frames}؛ کنارگذاشته به سقف {sel.dropped_by_cap}")

    log("گذر ۲ — تکه‌های 1080p")
    starts = sorted({int(math.floor(m.t)) for m in sel.moments})
    got = dl.sections(doc.url, starts, work)
    files, missing, height = {}, [], None
    for m in sel.moments:
        fid = frame_id(doc.video_id, m.t)
        s = int(math.floor(m.t))
        if s not in got:
            missing.append(fid)
            continue
        if height is None:
            height = height_of(got[s])
        out = vdir / f"{fid}.jpg"
        try:
            extract(got[s], m.t - s, out)
        except FramesError as e:
            log(f"⛔ {e}")
            missing.append(fid)
            continue
        files[fid] = out.name
    if height is not None and height < TARGET_HEIGHT:
        log(f"⛔ ارتفاع فریم {height} است، نه {TARGET_HEIGHT} — جزئیات ریز شاید ناخوانا شوند")

    man = manifest(doc, an, sel, files, missing, height, now)
    (vdir / "frames.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    (vdir / "FRAMES.md").write_text(render_frames_md(man, doc), encoding="utf-8")
    if not keep_work:
        shutil.rmtree(work)          # خطا بالا می‌رود — پاک‌سازی بی‌صدا شکست نمی‌خورد
    if missing:
        log(f"⛔ {len(missing)} فریم دریافت یا استخراج نشد: " + "، ".join(missing))
        return man, 3
    return man, 0


# ═══════════════ ۶ — کارت نمودار و اعتبارسنج ═══════════════

CONFIDENCE = ("high", "medium", "low")
UNREADABLE = "ناخوانا"
BARE_NUMBER_KEYS = {"schema", "t", "row", "strength"}   # فراداده، نه خوانده از تصویر
SPEECH_MAX = 300
TEXT_MAX = 200      # هم‌قاعده سقف خط عمومی نشست ۴
CARD_KEYS = ("frame_id", "t", "refs", "recorded_at", "coin", "venue", "timeframe",
             "chart_type", "scale", "price_axis", "levels", "trendlines", "zones",
             "patterns", "indicators", "texts", "speech", "method_notes")
NOT_CHART_KEYS = ("frame_id", "t", "refs", "texts", "speech", "method_notes")
FIELD_KEYS = ("recorded_at", "coin", "venue", "timeframe", "chart_type", "scale")
# منبع آنچه روی صفحه است — نشست ۷: خود گوینده، دیگران، توییت، بی‌تصویر، نامعلوم
SCREEN_KINDS = ("own", "other", "tweet", "none", "unknown")


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_value(obj: dict, where: str, errs: list[str]) -> None:
    """
    شیء مقدار: {value, confidence, from, note?}. قفل کاربر، نشست ۶:
    هر عدد کارت فقط از تصویر است — from باید image باشد؛ هرچه از حرف آمده
    فقط در speech و method_notes. مقدار null یعنی «ناخوانا»، نه حدس.
    """
    v = obj.get("value")
    if obj.get("from") != "image":
        errs.append(f"{where}: from باید «image» باشد، نه {obj.get('from')!r} — "
                    "آنچه از حرف آمده فقط در speech و method_notes")
    if v is None:
        if obj.get("note") != UNREADABLE:
            errs.append(f"{where}: مقدار null بی‌برچسب «{UNREADABLE}»")
        if obj.get("confidence") is not None:
            errs.append(f"{where}: مقدار null با اطمینان {obj.get('confidence')!r}")
        return
    if obj.get("confidence") not in CONFIDENCE:
        errs.append(f"{where}: اطمینان {obj.get('confidence')!r} — باید یکی از {CONFIDENCE}")
    if not (_is_num(v) or isinstance(v, str)):
        errs.append(f"{where}: مقدار از نوع {type(v).__name__}")
    if _is_num(v) and not math.isfinite(v):
        errs.append(f"{where}: مقدار نامتناهی")


def _walk(x, where: str, errs: list[str]) -> None:
    """هر عدد بیرون از شیء مقدار — جز فراداده — عدد بی‌اطمینان است و رد می‌شود."""
    if isinstance(x, dict):
        if "value" in x:
            _check_value(x, where, errs)
            for k, v in x.items():
                if k not in ("value",) and _is_num(v):
                    errs.append(f"{where}.{k}: عدد بی‌اطمینان")
            return
        for k, v in x.items():
            if _is_num(v) and k not in BARE_NUMBER_KEYS:
                errs.append(f"{where}.{k}: عدد بی‌اطمینان {v!r} — باید {{value, confidence, from}} باشد")
            else:
                _walk(v, f"{where}.{k}", errs)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            if _is_num(v):
                errs.append(f"{where}[{i}]: عدد بی‌اطمینان {v!r}")
            else:
                _walk(v, f"{where}[{i}]", errs)


def validate_card(card: dict, where: str = "card") -> list[str]:
    errs: list[str] = []
    if not isinstance(card, dict):
        return [f"{where}: کارت شیء نیست"]
    is_chart = card.get("is_chart", True)
    if not isinstance(is_chart, bool):
        errs.append(f"{where}.is_chart: باید درست یا نادرست باشد")
    for k in (CARD_KEYS if is_chart is not False else NOT_CHART_KEYS):
        if k not in card:
            errs.append(f"{where}: میدان {k} نیست")
    if not isinstance(card.get("t"), (int, float)) or isinstance(card.get("t"), bool):
        errs.append(f"{where}.t: زمان فریم عدد نیست")
    for k in FIELD_KEYS:
        if k in card and not (isinstance(card[k], dict) and "value" in card[k]):
            errs.append(f"{where}.{k}: باید شیء مقدار باشد")
    rec = card.get("recorded_at")
    if isinstance(rec, dict) and isinstance(rec.get("value"), str):
        try:
            if datetime.fromisoformat(rec["value"]).tzinfo is None:
                errs.append(f"{where}.recorded_at: زمان بی‌منطقه")
        except ValueError:
            errs.append(f"{where}.recorded_at: زمان ISO نیست: {rec['value']!r}")
    sp = card.get("speech")
    if not isinstance(sp, str):
        errs.append(f"{where}.speech: باید متن ساده باشد — عدد از حرف فقط به شکل متن")
    elif len(sp) > SPEECH_MAX:
        errs.append(f"{where}.speech: {len(sp)} نویسه، سقف {SPEECH_MAX} — متن ویدیو مال صاحبش است")
    notes = card.get("method_notes")
    if not (isinstance(notes, list) and all(isinstance(n, str) for n in notes)):
        errs.append(f"{where}.method_notes: باید فهرست متن ساده باشد")
    elif any(len(n) > SPEECH_MAX for n in notes):
        errs.append(f"{where}.method_notes: یادداشت بالای {SPEECH_MAX} نویسه")
    for i, t in enumerate(card.get("texts") or []):
        txt = t.get("text") if isinstance(t, dict) else None
        if not isinstance(txt, str):
            errs.append(f"{where}.texts[{i}]: text نیست")
        elif len(txt) > TEXT_MAX:
            errs.append(f"{where}.texts[{i}]: {len(txt)} نویسه، سقف {TEXT_MAX}")
        if isinstance(t, dict) and t.get("confidence") not in CONFIDENCE:
            errs.append(f"{where}.texts[{i}]: اطمینان {t.get('confidence')!r}")
    for i, r in enumerate(card.get("refs") or []):
        if not isinstance(r, dict) or "doc" not in r or "row" not in r or "claim_id" not in r:
            errs.append(f"{where}.refs[{i}]: doc، row و claim_id لازم است")
    # دو میدان اختیاری نشست ۶ب — گزارش ویدیو از همین‌ها می‌خواند، نه از متن آزاد
    cl = card.get("claims")
    if cl is not None:
        if not (isinstance(cl, list) and all(isinstance(c, str) for c in cl)):
            errs.append(f"{where}.claims: باید فهرست متن ساده باشد — ادعا به بیان ما؛ "
                        "عدد حرف فقط به شکل متن")
        elif any(len(c) > TEXT_MAX for c in cl):
            errs.append(f"{where}.claims: ادعای بالای {TEXT_MAX} نویسه")
    sv = card.get("speech_vs_screen")
    if sv is not None:
        if not (isinstance(sv, dict) and set(sv) == {"agree", "note"}):
            errs.append(f"{where}.speech_vs_screen: باید شیء {{agree, note}} باشد")
        else:
            if not (sv["agree"] is None or isinstance(sv["agree"], bool)):
                errs.append(f"{where}.speech_vs_screen.agree: درست، نادرست یا null — "
                            f"نه {sv['agree']!r}")
            if not isinstance(sv["note"], str):
                errs.append(f"{where}.speech_vs_screen.note: باید متن ساده باشد")
            elif len(sv["note"]) > TEXT_MAX:
                errs.append(f"{where}.speech_vs_screen.note: بالای {TEXT_MAX} نویسه")
    # میدان اختیاری screen_source — نشست ۷، آزمون «ترجمه یا تحلیل؟» analysts.yml: آنچه
    # روی صفحه است نمودار خود گوینده است، یا تصویر و توییت دیگران با نام یا واترمارک؟
    src = card.get("screen_source")
    if src is not None:
        if not (isinstance(src, dict) and set(src) == {"kind", "who", "evidence"}):
            errs.append(f"{where}.screen_source: باید شیء {{kind, who, evidence}} باشد")
        else:
            if src["kind"] not in SCREEN_KINDS:
                errs.append(f"{where}.screen_source.kind: {src['kind']!r} — باید یکی از {SCREEN_KINDS}")
            if not (src["who"] is None or isinstance(src["who"], str)):
                errs.append(f"{where}.screen_source.who: متن یا null")
            if not isinstance(src["evidence"], str) or len(src["evidence"]) > TEXT_MAX:
                errs.append(f"{where}.screen_source.evidence: متن ساده تا {TEXT_MAX} نویسه")
    rest = {k: v for k, v in card.items() if k not in ("t", "speech", "method_notes")}
    # میدان اختیاری snap کنار سطح — نشست ۷. عددهایش از کندل است، نه از تصویر؛ پس
    # قالب خودش را radar_history.validate_snap می‌سنجد و از قاعده «فقط تصویر» بیرون است.
    levels = card.get("levels")
    snaps = [(i, lv["snap"]) for i, lv in enumerate(levels if isinstance(levels, list) else [])
             if isinstance(lv, dict) and "snap" in lv]
    if snaps:
        import radar_history as H           # فقط وقتی کارت snap دارد
        for i, s in snaps:
            errs += H.validate_snap(s, f"{where}.levels[{i}].snap")
        rest["levels"] = [{k: v for k, v in lv.items() if k != "snap"} if isinstance(lv, dict) else lv
                          for lv in levels]
    _walk(rest, where, errs)
    return errs


def validate_cards(doc: dict, manifest: dict | None = None) -> list[str]:
    if not isinstance(doc, dict):
        return ["سند کارت شیء نیست"]
    errs = []
    if doc.get("template"):
        errs.append("این قالب پرنشده است — template: true")
    for k in ("schema", "video_id", "doc_id", "cards"):
        if k not in doc:
            errs.append(f"میدان {k} نیست")
    cards = doc.get("cards") or []
    seen = set()
    for i, c in enumerate(cards):
        fid = c.get("frame_id") if isinstance(c, dict) else None
        errs += validate_card(c, f"cards[{i}]({fid})")
        if fid in seen:
            errs.append(f"cards[{i}]: frame_id تکراری {fid}")
        seen.add(fid)
    if manifest is not None:
        mt = {f["frame_id"]: f["t"] for f in manifest.get("frames", [])}
        for c in cards:
            fid = c.get("frame_id") if isinstance(c, dict) else None
            if fid not in mt:
                errs.append(f"{fid}: در فهرست فریم‌ها نیست")
            elif abs(float(c.get("t", -1)) - mt[fid]) > 0.05:
                errs.append(f"{fid}: زمان کارت {c.get('t')} با فهرست {mt[fid]} نمی‌خواند")
        for fid in mt:
            if fid not in seen and fid not in manifest.get("missing", []):
                errs.append(f"{fid}: فریم بی‌کارت")
    return errs


def card_template(man: dict) -> dict:
    """قالب پرنشده — validate_cards ردش می‌کند تا پر شود."""
    def unread() -> dict:
        return {"value": None, "confidence": None, "from": "image", "note": UNREADABLE}
    cards = []
    for f in man["frames"]:
        if not f.get("file"):
            continue
        cards.append({
            "frame_id": f["frame_id"], "t": f["t"], "is_chart": True,
            "refs": f["refs"],
            "recorded_at": {**unread(), "seen": None},
            "coin": unread(), "venue": unread(), "timeframe": unread(),
            "chart_type": unread(), "scale": unread(),
            "price_axis": {"top": unread(), "bottom": unread()},
            "levels": [], "trendlines": [], "zones": [], "patterns": [],
            "indicators": [], "texts": [], "speech": "", "method_notes": [],
            # اختیاری، نشست ۶ب: ادعای قابل‌تسویه به بیان ما؛ و آیا حرف با صفحه
            # می‌خواند — درست، نادرست، یا null یعنی وارسی‌نشدنی
            "claims": [], "speech_vs_screen": {"agree": None, "note": ""}})
    return {"schema": 1, "template": True, "kind": "radar-chart-cards",
            "video_id": man["video_id"], "doc_id": man["doc_id"], "doc": man["doc"],
            "source": man["source"], "url": man["url"], "title": man["title"],
            "frames_tool": f"radar_frames {man['radar_frames']}",
            "guide": "references/chart-reading.md", "cards": cards}


def cards_path(source: str, video_id: str) -> Path:
    return CHARTS_DIR / source / f"{video_id}.json"


# ═══════════════ ۷ — خط فرمان ═══════════════

def _utf8_console() -> None:
    # بدون بلعیدن خطا — ک۵۴. جریانی که reconfigure ندارد دست نمی‌خورد.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def _validate_cli(path: Path, frames_root: Path) -> int:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⛔ کارت خوانده نشد: {path} — {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    man_path = frames_root / str(doc.get("video_id", "")) / "frames.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else None
    errs = validate_cards(doc, man)
    if man is None:
        print(f"⚠️ فهرست فریم {man_path} نیست — هم‌خوانی frame_id سنجیده نشد")
    if errs:
        print(f"⛔ {len(errs)} خطا در {path}:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2
    print(f"✅ {path}: {len(doc.get('cards', []))} کارت معتبر")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    ap = argparse.ArgumentParser(description="فریم نمودار از ویدیوی تحلیل‌گر — رادار، نشست ۶")
    ap.add_argument("doc", nargs="?", help="سند radar_intake، عمومی یا محلی")
    ap.add_argument("--url", help="نشانی ویدیو؛ پیش‌فرض از میدان «نشانی» سند")
    ap.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    ap.add_argument("--out", default=FRAMES_DIR,
                    help="پوشه ریشه فریم‌ها — پوشه، نه فایل؛ پیش‌فرض frames")
    ap.add_argument("--keep-video", action="store_true",
                    help="پوشه _work با ویدیوی کم‌کیفیت و تکه‌ها پاک نشود")
    ap.add_argument("--card-template", action="store_true",
                    help="قالب کارت پرنشده در frames/<video_id>/card_template.json")
    ap.add_argument("--validate", metavar="CARDS_JSON", help="فقط اعتبارسنجی فایل کارت")
    a = ap.parse_args(argv)
    if a.validate:
        return _validate_cli(Path(a.validate), Path(a.out))
    if not a.doc:
        ap.error("سند لازم است، یا --validate")
    if a.max_frames < 1:
        ap.error("--max-frames دست‌کم ۱")
    miss = missing_deps()
    if miss:
        print(f"⛔ پیش‌نیاز نیست: {'، '.join(miss)} — yt-dlp با pip، ffmpeg و ffprobe جدا",
              file=sys.stderr)
        return 2
    try:
        doc = load_doc(Path(a.doc), a.url)
    except DocError as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    print(f"{doc.title} — {doc.video_id}، {len(doc.candidates)} نامزد ادعا")
    try:
        man, code = run(doc, Path(a.out), a.max_frames, keep_work=a.keep_video)
    except FramesError as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 3
    vdir = Path(a.out) / doc.video_id
    if a.card_template:
        p = vdir / "card_template.json"
        p.write_text(json.dumps(card_template(man), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"قالب کارت: {p} — پس از پرکردن در {cards_path(doc.source, doc.video_id)}")
    print(f"{len(man['frames'])} فریم → {vdir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
