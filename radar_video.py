#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_video.py  —  نسخه ۱.۰ — «دیدن کامل» با یک پیوند، نشست ۶ب
کاربر فقط پیوند می‌دهد — ویدیو یا پلی‌لیست، حتی از کانالی که در
analysts.yml نیست — و رادار آن را کامل می‌بیند.

مسیر:
    ۱ — پیوند بی‌شبکه دسته‌بندی می‌شود: ویدیو یا پلی‌لیست. پیوند کانال رد می‌شود.
    ۲ — فراداده با yt-dlp، بی‌دانلود: کانال، تاریخ انتشار، مدت.
    ۳ — منبع: کانالی که در analysts.yml هست همان منبع را می‌گیرد. کانال ناشناخته
        برچسب «تک‌ویدیو» می‌خورد و بدون حق رأی است — scores: false. افزودن دائمی
        به analysts.yml فقط با تأیید کاربر؛ این اسکریپت فقط پیشنهاد چاپ می‌کند.
    ۴ — متن: زیرنویس با radar_intake، سند عمومی و محلی با write_documents —
        همان قالب نشست ۴. ویدیوی ۳ دقیقه یا کمتر رد می‌شود — ف۸.
    ۵ — فریم: radar_frames روی همان سند، به‌علاوه قالب کارت.
    ۶ — خواندن فریم و نوشتن کارت کار مدل در نشست است. سپس --report از کارت
        اعتبارسنجی‌شده، گزارش ساده فارسی در intake/reports/ می‌سازد.

پلی‌لیست:
    ترتیب قسمت‌ها حفظ می‌شود و شماره قسمت در عنوان سند می‌آید. بدون --limit
    فقط فهرست و برآورد زمان، و می‌ایستد — هیچ فایلی نوشته نمی‌شود. با --limit N،
    N قسمت تازه به ترتیب؛ قسمت پیشین و کوتاه شمرده نمی‌شوند.

ویدیوی درون پلی‌لیست — watch?v=…&list=… — اگر آن پلی‌لیست منبع analysts.yml
است، منبع و شماره قسمت را از آن می‌گیرد؛ وگرنه منبع از کانال است.

بازاستفاده — هیچ‌چیز بی‌صدا بازنویسی نمی‌شود:
    سند موجود دوباره گرفته نمی‌شود. سند پیش از نشست ۴ — متن کامل در خود سند
    عمومی، مثل ۹ قسمت نخست دوره ارشیا — پیشین است و دست نمی‌خورد؛ فریمش هم
    ساخته نمی‌شود، چون radar_frames نسخه محلی می‌خواهد. فریم موجود دوباره ساخته نمی‌شود مگر با
    --force. اگر کارت نمودار ویدیو هست، فریم حتی با --force ساخته نمی‌شود —
    شناسه‌های کارت از فهرست فریم جدا می‌افتند، درس رویداد ۵۹.

محیط اجرا: فقط لپ‌تاپ — یوتیوب آی‌پی مرکز داده را می‌بندد. متن کامل و فریم
فقط محلی؛ سند عمومی، کارت نمودار و گزارش عمومی‌اند.

اجرا:
    python radar_video.py <پیوند ویدیو>
    python radar_video.py <پیوند پلی‌لیست>                # فهرست و برآورد، بی‌اجرا
    python radar_video.py <پیوند پلی‌لیست> --limit 3      # سه قسمت تازه
    python radar_video.py <پیوند> --max-frames 15
    python radar_video.py --report intake/charts/<منبع>/<video_id>.json

کد خروج: ۰ سالم؛ ۲ پیش‌نیاز، پیوند یا کارت نامعتبر؛ ۳ دست‌کم یک قسمت شکست خورد.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import radar_frames as F
import radar_history as H            # حکم و جمع‌بندی وارسی سطح — نشست ۷
import radar_intake as I
from radar_one import video_id as _video_id     # تنها منبع الگوی شناسه ویدیو
from radar_text import fa

VERSION = "1.0"
UTC = timezone.utc

SINGLE_ROLE = "تک‌ویدیو"
SINGLE_PREFIX = "single_"
STATE_NAME = ".state.json"

# برآورد زمان — محاسبه‌شده از دو اجرای واقعی نشست ۶: 210 s برای ویدیوی 1026 s
# و 183 s برای 846 s، یعنی 0.205 و 0.216 برابر مدت. حجم محلی 5.01 و 6.33 MB.
FRAMES_SECONDS_PER_VIDEO_SECOND = 0.22
EPISODE_OVERHEAD_S = 15            # فراداده و زیرنویس، برآورد — اندازه‌گیری نشده
LOCAL_MB_PER_VIDEO = 6.5


# ═══════════════ ۱ — پیوند، بی‌شبکه ═══════════════

class LinkError(ValueError):
    """پیوند ویدیو یا پلی‌لیست یوتیوب نیست. کد ۲."""


_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
          "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}
# شناسه‌ها اسکی‌اند — نه \w، که حرف و رقم فارسی را هم می‌گیرد
_LIST_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")
_BARE_VIDEO = re.compile(r"[A-Za-z0-9_-]{11}")
_BARE_PLAYLIST = re.compile(r"(?:PL|OL|UU|FL)[A-Za-z0-9_-]{10,}")
# فهرست خودکار یوتیوب — میکس، پسندیده‌ها، بعداً ببین — پلی‌لیست ثابت عمومی نیست
_AUTO_LISTS = ("RD", "LL", "WL", "UL")


@dataclass(frozen=True)
class Link:
    kind: str                  # video | playlist
    video_id: str = ""
    playlist_id: str = ""
    note: str = ""

    @property
    def url(self) -> str:
        if self.kind == "playlist":
            return f"https://www.youtube.com/playlist?list={self.playlist_id}"
        return f"https://www.youtube.com/watch?v={self.video_id}"


def parse_link(raw: str) -> Link:
    """
    ویدیو یا پلی‌لیست، فقط از روی پیوند. ویدیوی درون پلی‌لیست — watch?v=…&list=…
    — ویدیو است: کاربر روی همان قسمت بود. یادداشت می‌گوید کل پلی‌لیست چطور.
    """
    s = (raw or "").strip()
    if _BARE_VIDEO.fullmatch(s):
        return Link("video", video_id=s)
    if _BARE_PLAYLIST.fullmatch(s):
        return Link("playlist", playlist_id=s)
    u = urlparse(s if "://" in s else "https://" + s)
    if (u.hostname or "").lower() not in _HOSTS:
        raise LinkError(f"پیوند یوتیوب نیست: {s[:80]!r}")
    m = _LIST_RE.search(s)
    pid = m.group(1) if m else ""
    auto = pid.startswith(_AUTO_LISTS)
    if u.path.rstrip("/") == "/playlist":
        if not pid:
            raise LinkError("پیوند پلی‌لیست شناسه list ندارد")
        if auto:
            raise LinkError(f"فهرست خودکار یوتیوب ({pid[:2]}) پلی‌لیست ثابت نیست — "
                            "پیوند خود ویدیو را بده")
        return Link("playlist", playlist_id=pid)
    vid = _video_id(s)
    if vid:
        if not pid or auto:
            return Link("video", video_id=vid)
        # شناسه پلی‌لیست می‌ماند: اگر منبع شناخته‌شده analysts.yml باشد، منبع و
        # شماره قسمت از آن می‌آید — main
        note = (f"این ویدیو درون پلی‌لیست {pid} است؛ فقط همین ویدیو دیده می‌شود. "
                f"برای کل پلی‌لیست: https://www.youtube.com/playlist?list={pid}")
        return Link("video", video_id=vid, playlist_id=pid, note=note)
    if re.match(r"^/(@|channel/|c/|user/)", u.path):
        raise LinkError("پیوند کانال است، نه ویدیو یا پلی‌لیست — کانال ثابت در "
                        "analysts.yml با radar_intake جمع می‌شود")
    raise LinkError(f"شناسه ویدیو یا پلی‌لیست در پیوند نیست: {s[:80]!r}")


# ═══════════════ ۲ — فراداده با yt-dlp ═══════════════

class MetaError(Exception):
    """yt-dlp فراداده نداد. blocked یعنی یوتیوب بست — قسمت‌های بعد امتحان نمی‌شوند."""

    def __init__(self, msg: str, blocked: bool = False):
        super().__init__(msg)
        self.blocked = blocked


# نشانه مسدودی آی‌پی یا ربات — نه «در کشور شما در دسترس نیست»، که مال یک ویدیوست
_BLOCK_HINTS = ("Sign in to confirm", "not a bot", "HTTP Error 429")


class YtMeta:
    """فراداده با رابط پایتونی yt-dlp، بی‌دانلود — هم‌الگو با radar_frames.YtDlp."""

    def _info(self, url: str, flat: bool) -> dict:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        if flat:
            opts["extract_flat"] = "in_playlist"
        else:
            opts["noplaylist"] = True
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e)
            raise MetaError(f"yt-dlp: {msg[:300]}",
                            blocked=any(h in msg for h in _BLOCK_HINTS)) from e
        if not isinstance(info, dict):
            raise MetaError(f"yt-dlp برای {url} فراداده نداد")
        return info

    def video(self, vid: str) -> dict:
        return self._info(f"https://www.youtube.com/watch?v={vid}", flat=False)

    def playlist(self, pid: str) -> dict:
        return self._info(f"https://www.youtube.com/playlist?list={pid}", flat=True)


def item_from_info(info: dict, title_prefix: str = "") -> dict:
    """آیتم هم‌شکل radar_intake. تاریخ انتشار به وقت جهانی — قاعده نشست ۴."""
    vid = info.get("id") or ""
    ts = info.get("timestamp") or info.get("release_timestamp")
    up = str(info.get("upload_date") or "")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        published = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif re.fullmatch(r"[0-9]{8}", up):
        published = f"{up[:4]}-{up[4:6]}-{up[6:]}"
    else:
        published = ""
    return {"id": vid, "title": title_prefix + (info.get("title") or ""),
            "url": f"https://www.youtube.com/watch?v={vid}", "published": published,
            "author": info.get("channel") or info.get("uploader") or ""}


def _seconds(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


# ═══════════════ ۳ — منبع ═══════════════

def resolve_source(sources: list[I.Source], info: dict, playlist_id: str = "") -> I.Source:
    """
    منبع analysts.yml اگر کانال یا پلی‌لیست شناخته است — خاموش هم شناخته است.
    وگرنه منبع موقت «تک‌ویدیو»، بدون حق رأی، که در analysts.yml نوشته نمی‌شود.
    """
    if playlist_id:
        for s in sources:
            if s.kind == "playlist" and I.extract_playlist_id(s.playlist_id or s.url) == playlist_id:
                return s
    cid = info.get("channel_id") or ""
    for s in sources:
        if s.kind == "youtube" and s.channel_id and s.channel_id == cid:
            return s
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", cid):
        raise MetaError(f"شناسه کانال از فراداده نیامد: {cid!r} — منبع ساخته نمی‌شود")
    name = info.get("channel") or info.get("uploader") or cid
    lang = str(info.get("language") or "").split("-")[0].lower()
    langs = [x for x in dict.fromkeys([lang, "en", "fa"]) if re.fullmatch(r"[a-z]{2,3}", x)]
    return I.Source(key=SINGLE_PREFIX + cid, name_fa=name, name_en=name, role=SINGLE_ROLE,
                    kind="youtube", channel_id=cid, handle=info.get("uploader_id") or "",
                    lang=langs, enabled=False, scores=False,
                    notes="کانال ناشناخته — radar_video؛ افزودن دائمی فقط با تأیید کاربر")


def analysts_suggestion(src: I.Source) -> list[str]:
    """پیشنهاد ردیف analysts.yml — چاپ می‌شود، نوشته نمی‌شود."""
    return [
        "```yaml",
        f"  {src.key}:            # کلید، جایگاه و مکتب را کاربر تعیین کند",
        f'    name_fa: "{src.name_fa}"',
        f'    name_en: "{src.name_en}"',
        '    role: ""              # ؟',
        '    school: ""            # ؟',
        '    kind: "youtube"',
        f'    channel_id: "{src.channel_id}"',
        f"    lang: [{', '.join(src.lang)}]",
        "    scores: false",
        "    enabled: true",
        "```",
    ]


# ═══════════════ ۴ — دیدن یک ویدیو ═══════════════

def find_doc(intake: Path, vid: str) -> Path | None:
    """
    سند عمومی همین ویدیو، از هر منبع. نام فایل شش نویسه شناسه را دارد —
    write_documents — و میدان «نشانی» سند تأییدش می‌کند.
    """
    for f in sorted(intake.glob(f"*/*_{vid[:6]}.md")):
        if f.parent.name in (I.LOCAL_DIR, I.REPORTS_DIR, F.CHARTS_DIR.name):
            continue
        meta = I._front_matter(f.read_text(encoding="utf-8"))
        if _video_id(meta.get("نشانی", "")) == vid:
            return f
    return None


def is_legacy(doc: Path) -> bool:
    """
    سند پیش از نشست ۴: متن کامل در خود سند عمومی، بی‌نسخه محلی — ۹ قسمت
    نخست دوره ارشیا. دست نمی‌خورد: بازگیری‌اش سند دوم با نام دیگر می‌ساخت.
    """
    return F.FULL_TEXT in doc.read_text(encoding="utf-8")


def known_playlist(sources: list[I.Source], pid: str) -> bool:
    return bool(pid) and any(s.kind == "playlist" and I.extract_playlist_id(s.playlist_id or s.url) == pid
                             for s in sources)


def run_frames(doc_path: Path, out_root: Path, max_frames: int) -> tuple[dict, int]:
    return F.run(F.load_doc(doc_path), out_root, max_frames)


@dataclass
class Deps:
    """هر چیزی که به شبکه یا برنامه بیرونی می‌رود — آزمون جانشینش می‌کند."""
    meta: object
    transcript: Callable
    frames: Callable
    whisper: Callable | None = None
    missing: Callable = None

    @classmethod
    def real(cls, whisper: bool) -> "Deps":
        return cls(meta=YtMeta(), transcript=I.fetch_transcript, frames=run_frames,
                   whisper=I.whisper_fallback if whisper else None, missing=missing_deps)


def missing_deps(listing_only: bool, whisper: bool = False) -> list[str]:
    if listing_only:
        return [] if importlib.util.find_spec("yt_dlp") else ["yt-dlp"]
    return list(dict.fromkeys(I.missing_deps(whisper) + F.missing_deps()))


@dataclass
class Ctx:
    deps: Deps
    sources: list[I.Source]
    intake: Path
    frames_root: Path
    state: dict
    max_frames: int
    force: bool = False
    wrote_docs: bool = False
    log: Callable = print


@dataclass
class Episode:
    pos: int | None
    video_id: str
    title: str = ""
    source: str = ""
    role: str = ""
    doc: str = ""
    frames_md: str = ""
    template: str = ""
    cards: str = ""
    nframes: int = 0
    status: str = ""
    detail: str = ""
    failed: bool = False
    single: I.Source | None = None


def _done(ctx: Ctx, vid: str) -> str:
    """چرا قسمت پیشین است — سند قدیمی، یا سند با کارت یا فریم؛ تهی یعنی تازه."""
    doc = find_doc(ctx.intake, vid)
    if doc is None:
        return ""
    if is_legacy(doc):
        return "سند قدیمی"
    cards = ctx.intake / F.CHARTS_DIR.name / doc.parent.name / f"{vid}.json"
    if cards.exists():
        return "کارت هست"
    return "فریم هست" if (ctx.frames_root / vid / "frames.json").exists() else ""


def see_video(ctx: Ctx, vid: str, *, pos: int | None = None, playlist_id: str = "",
              info: dict | None = None) -> Episode:
    """
    یک ویدیو تا فریم و قالب کارت. TranscriptBlocked و MetaError مسدودی بالا
    می‌روند تا صدازننده قسمت‌های بعد را نگه دارد.
    """
    ep = Episode(pos, vid)
    info = info or ctx.deps.meta.video(vid)
    item = item_from_info(info, f"[{pos:02d}] " if pos else "")
    ep.title = item["title"]
    src = resolve_source(ctx.sources, info, playlist_id)
    ep.source, ep.role = src.key, src.role
    if src.role == SINGLE_ROLE:
        ep.single = src
    secs = _seconds(info.get("duration"))

    pub = find_doc(ctx.intake, vid)
    if pub is not None and is_legacy(pub):
        ep.doc = pub.as_posix()
        ep.status = "پیشین — سند قدیمی"
        ep.detail = ("متن کامل در خود سند عمومی، پیش از نشست ۴ — دست نمی‌خورد؛ "
                     "radar_frames نسخه محلی می‌خواهد، پس فریم ساخته نشد")
        ctx.log(f"  سند قدیمی: {ep.doc} — {ep.detail}")
        return ep
    if pub is not None and (ctx.intake / I.LOCAL_DIR / pub.relative_to(ctx.intake)).exists():
        ctx.log(f"  سند موجود — بازاستفاده: {pub.as_posix()}")
    else:
        if pub is not None:
            ctx.log(f"  سند عمومی هست ولی متن محلی نیست — دوباره گرفته می‌شود: {pub.as_posix()}")
        if secs is not None and secs <= I.SHORT_MAX_SECONDS:
            ep.status, ep.detail = "رد شد — کوتاه", f"{I.fmt_ts(secs)}، ف۸"
            ctx.log(f"  — رد شد: کوتاه، {I.fmt_ts(secs)}")
            return ep
        duration = I.fmt_ts(secs) if secs is not None else "نامعلوم — yt-dlp مدت نداد"
        segs, method = ctx.deps.transcript(vid, src.lang)
        if not segs and ctx.deps.whisper is not None:
            ctx.log("  زیرنویس نبود → ویسپر")
            segs, method = ctx.deps.whisper(item["url"])
        if not segs:
            ep.status, ep.detail, ep.failed = "بی‌زیرنویس", method, True
            ctx.log(f"  ⛔ بی‌زیرنویس — {method}؛ بی‌متن، فریم ساخته نمی‌شود. --whisper را امتحان کن")
            return ep
        fname, ncands, date = I.write_documents(src, item, segs, method, ctx.intake, duration=duration)
        pub = ctx.intake / src.key / fname
        seen = ctx.state.setdefault("seen", {}).setdefault(src.key, {})
        seen[vid] = {"title": item["title"], "file": fname, "at": date, "by": f"radar_video {VERSION}"}
        ctx.wrote_docs = True
        ctx.log(f"  ✓ {method} — {ncands} نامزد → {pub.as_posix()}")
    ep.doc = pub.as_posix()

    folder = pub.parent.name                  # منبع کارت همان پوشه سند است — radar_frames
    vdir = ctx.frames_root / vid
    cards = ctx.intake / F.CHARTS_DIR.name / folder / f"{vid}.json"
    ep.frames_md = (vdir / "FRAMES.md").as_posix()
    ep.template = (vdir / "card_template.json").as_posix()
    ep.cards = cards.as_posix()
    if cards.exists():
        ep.status = "پیشین — کارت هست"
        ep.detail = "فریم دوباره ساخته نمی‌شود، حتی با --force — شناسه کارت از فهرست جدا می‌افتد"
        ctx.log(f"  کارت نمودار هست: {cards.as_posix()} — {ep.detail}")
        return ep
    if (vdir / "frames.json").exists() and not ctx.force:
        man = json.loads((vdir / "frames.json").read_text(encoding="utf-8"))
        ep.nframes = len(man.get("frames", []))
        ep.status, ep.detail = "پیشین — فریم هست", "برای ساخت دوباره --force"
        ctx.log(f"  فریم هست: {ep.frames_md} — دوباره ساخته نشد")
        return ep

    man, code = ctx.deps.frames(pub, ctx.frames_root, ctx.max_frames)
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "card_template.json").write_text(
        json.dumps(F.card_template(man), ensure_ascii=False, indent=1), encoding="utf-8")
    ep.nframes = len(man.get("frames", []))
    notes = []
    if man.get("missing"):
        notes.append(f"{len(man['missing'])} فریم دریافت نشد")
    if (man.get("analysis") or {}).get("mask_warning"):
        notes.append("⛔ هشدار ماسک")
    ep.detail = "؛ ".join(notes)
    ep.failed = code != 0
    ep.status = "سالم" if code == 0 else "فریم ناقص"
    return ep


def _attempt(ctx: Ctx, vid: str, **kw) -> tuple[Episode, bool]:
    """(قسمت، مسدود شد؟). هر خطا با نوعش ثبت می‌شود — هیچ‌کدام بی‌صدا نیست."""
    try:
        return see_video(ctx, vid, **kw), False
    except I.TranscriptBlocked as e:
        ep = Episode(kw.get("pos"), vid, status="مسدود", detail=f"یوتیوب بست — {e}", failed=True)
        return ep, True
    except MetaError as e:
        ep = Episode(kw.get("pos"), vid, status="مسدود" if e.blocked else "شکست",
                     detail=str(e), failed=True)
        return ep, e.blocked
    except (F.DocError, F.FramesError, OSError) as e:
        return Episode(kw.get("pos"), vid, status="شکست",
                       detail=f"{type(e).__name__}: {e}", failed=True), False
    except Exception as e:      # پیش‌بینی‌نشده — ثبت با نوعش، قسمت بعد ادامه می‌دهد
        return Episode(kw.get("pos"), vid, status="شکست",
                       detail=f"پیش‌بینی‌نشده — {type(e).__name__}: {e}", failed=True), False


# ═══════════════ ۵ — پلی‌لیست ═══════════════

def playlist_entries(pinfo: dict) -> list[dict]:
    """قسمت‌ها به ترتیب پلی‌لیست، با شماره جایگاه از ۱."""
    out = []
    for e in pinfo.get("entries") or []:
        if isinstance(e, dict) and e.get("id"):
            out.append({"pos": len(out) + 1, "id": e["id"], "title": e.get("title") or "",
                        "duration": _seconds(e.get("duration"))})
    return out


def estimate(entries: list[dict], status: dict[str, str]) -> dict:
    fresh = [e for e in entries if status[e["id"]] in ("تازه", "مدت نامعلوم")]
    known = [e["duration"] for e in fresh if e["duration"] is not None]
    run_s = sum(FRAMES_SECONDS_PER_VIDEO_SECOND * d + EPISODE_OVERHEAD_S for d in known)
    return {"fresh": len(fresh), "unknown": len(fresh) - len(known),
            "total_s": sum(known), "run_min": math.ceil(run_s / 60) if known else 0,
            "mb": round(LOCAL_MB_PER_VIDEO * len(fresh))}


def render_listing(link: Link, pinfo: dict, entries: list[dict], status: dict[str, str]) -> str:
    est = estimate(entries, status)
    count = lambda word: sum(1 for e in entries if status[e["id"]].startswith(word))
    lines = [
        f"# پلی‌لیست — {I._cell(pinfo.get('title') or link.playlist_id)}", "",
        f"- شناسه: `{link.playlist_id}` — {link.url}",
        f"- کانال: {I._cell(pinfo.get('channel') or pinfo.get('uploader') or '—')}",
        f"- قسمت‌ها: {len(entries)} — به ترتیب خود پلی‌لیست",
        "- **هیچ فایلی نوشته نشد.** بدون `--limit` فقط فهرست و برآورد.", "",
        "| # | شناسه | مدت | عنوان | وضعیت |", "|---|---|---|---|---|",
    ]
    for e in entries:
        dur = I.fmt_ts(e["duration"]) if e["duration"] is not None else "—"
        lines.append(f"| {e['pos']:02d} | `{e['id']}` | {dur} | {I._cell(e['title'])[:60]} "
                     f"| {status[e['id']]} |")
    lines += [
        "", "## برآورد", "",
        "| مورد | مقدار |", "|---|---|",
        f"| قسمت تازه | {est['fresh']} |",
        f"| مدت نامعلوم، درون تازه‌ها | {est['unknown']} |",
        f"| کوتاه — رد می‌شود | {count('کوتاه')} |",
        f"| پیشین — سند قدیمی، یا سند با فریم یا کارت | {count('پیشین')} |",
        f"| مدت کل قسمت‌های تازه با مدت معلوم | {I.fmt_ts(est['total_s'])} |",
        f"| اجرای اسکریپت، برآورد | حدود {est['run_min']} دقیقه |",
        f"| فضای محلی، برآورد | حدود {est['mb']} MB |", "",
        f"- مبنای برآورد، محاسبه‌شده از دو اجرای نشست ۶: 210 s برای ویدیوی 1026 s و "
        f"183 s برای 846 s — حدود {fa(FRAMES_SECONDS_PER_VIDEO_SECOND)} برابر مدت، به‌علاوه "
        f"{fa(EPISODE_OVERHEAD_S)} ثانیه برای هر قسمت.",
        f"- کوتاه یعنی {fa(I.SHORT_MAX_SECONDS // 60)} دقیقه یا کمتر — ف۸.",
        f"- خواندن فریم و نوشتن کارت کار مدل در نشست است و در برآورد نیست — تا "
        f"{fa(F.DEFAULT_MAX_FRAMES)} فریم برای هر قسمت.", "",
        f'اجرا: `python radar_video.py "{link.url}" --limit N`',
    ]
    return "\n".join(lines) + "\n"


# ═══════════════ ۶ — خلاصه اجرا ═══════════════

def render_summary(head: str, eps: list[Episode], untried: list[dict]) -> str:
    lines = [f"# دیدن کامل — {I._cell(head)}", "",
             "| # | ویدیو | منبع | جایگاه | فریم | وضعیت |", "|---|---|---|---|---|---|"]
    for e in eps:
        pos = f"{e.pos:02d}" if e.pos else "—"
        status = e.status + (f" — {I._cell(e.detail)}" if e.detail else "")
        lines.append(f"| {pos} | `{e.video_id}` {I._cell(e.title)[:50]} | {e.source or '—'} "
                     f"| {e.role or '—'} | {e.nframes} | {status} |")
    if untried:
        lines += ["", f"**امتحان نشد — پس از مسدودی:** {len(untried)} قسمت: "
                  + "، ".join(f"{u['pos']:02d}" for u in untried)]
    ready = [e for e in eps if e.frames_md and e.status in ("سالم", "فریم ناقص", "پیشین — فریم هست")]
    if ready:
        lines += ["", "## برای خواندن — کار مدل در نشست", "",
                  "پیش از خواندن: `references/chart-reading.md`.", ""]
        for e in ready:
            lines += [f"- `{e.frames_md}` — قالب کارت `{e.template}`",
                      f"  - پس از پرکردن: `{e.cards}`",
                      f"  - سپس: `python radar_frames.py --validate {e.cards}` و "
                      f"`python radar_video.py --report {e.cards}`"]
    singles = {e.single.key: e.single for e in eps if e.single is not None}
    if singles:
        lines += ["", "## کانال ناشناخته — پیشنهاد، نه ثبت", "",
                  f"برچسب «{SINGLE_ROLE}»، بدون حق رأی. افزودن دائمی به `analysts.yml` "
                  "فقط با تأیید کاربر.", ""]
        for s in singles.values():
            lines += analysts_suggestion(s) + [""]
    return "\n".join(lines) + "\n"


# ═══════════════ ۷ — گزارش ویدیو از کارت ═══════════════

CONF_FA = {"high": "بالا", "medium": "متوسط", "low": "پایین"}
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
CLAIM_MAX = 200                  # هم‌سقف F.TEXT_MAX — ادعا به بیان ما


def _val(o) -> str:
    """شیء مقدار کارت برای نمایش: عدد لاتین با جداکننده، «ناخوانا» برای null."""
    if not isinstance(o, dict) or "value" not in o:
        return "—"
    v = o["value"]
    if v is None:
        return F.UNREADABLE
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.8f}".rstrip("0").rstrip(".")
    return str(v)


def _conf(*objs) -> str:
    cs = [o.get("confidence") for o in objs if isinstance(o, dict) and o.get("value") is not None]
    if not cs:
        return "—"
    return CONF_FA.get(min(cs, key=lambda c: _CONF_RANK.get(c, -1)), "—")


def _count_values(x, acc: list[int]) -> None:
    """[خوانده، ناخوانا] — هر شیء مقدار کارت."""
    if isinstance(x, dict):
        if "value" in x and x.get("from") == "image":
            acc[1 if x["value"] is None else 0] += 1
            return
        for v in x.values():
            _count_values(v, acc)
    elif isinstance(x, list):
        for v in x:
            _count_values(v, acc)


def _drawn(lv: dict) -> str:
    d = lv.get("drawn_at")
    if isinstance(d, dict):
        d = d.get("value")
    return f"روی {d}" if isinstance(d, str) and d else ""


NOT_SNAPPED = "وارسی نشده"


def _snap_cells(lv: dict) -> tuple[str, str]:
    """
    (حکم کندل، ستون روزانه) — نشست ۷. حکم از تایم‌فریم خود نمودار؛ ستون روزانه فقط
    برای سطح زیر روزانه، برای قاعده ۴ و نشست ۸.
    """
    s = lv.get("snap")
    if not isinstance(s, dict):
        return NOT_SNAPPED, "—"
    d = s.get("daily")
    return H.snap_label(s), (H.snap_label(d) if isinstance(d, dict) else "—")


def _marks(card: dict) -> list[tuple[str, str, str, str, str, str]]:
    """(نوع، قیمت، اطمینان، برچسب، حکم کندل، روزانه) — سطح، ناحیه، خط روند."""
    out = []
    for lv in card.get("levels") or []:
        unit = lv.get("unit") or ""
        kind = {"horizontal": "سطح افقی"}.get(lv.get("kind"), lv.get("kind") or "سطح")
        label = "، ".join(x for x in (lv.get("label") or "", _drawn(lv)) if x)
        out.append((kind, _val(lv.get("price")) + unit, _conf(lv.get("price")), label, *_snap_cells(lv)))
    for z in card.get("zones") or []:
        unit = z.get("unit") or ""
        out.append(("ناحیه", f"{_val(z.get('low'))} تا {_val(z.get('high'))}{unit}",
                    _conf(z.get("low"), z.get("high")), z.get("label") or "", "—", "—"))
    for t in card.get("trendlines") or []:
        p1, p2 = t.get("p1") or {}, t.get("p2") or {}
        kind = "مسیر پیش‌بینی" if t.get("kind") == "projection" else "خط روند"
        span = f"{_val(p1.get('time'))} تا {_val(p2.get('time'))}"
        out.append((kind, f"{_val(p1.get('price'))} تا {_val(p2.get('price'))}",
                    _conf(p1.get("price"), p2.get("price")),
                    "، ".join(x for x in (t.get("label") or "", span) if x), "—", "—"))
    return out


def _snap_section(charts: list[dict]) -> list[str]:
    """جمع‌بندی وارسی سطح این ویدیو، در برابر شانس تصادفی همان پنجره‌ها — ف۲۱."""
    lines = ["", "## وارسی سطح با کندل", "",
             "> هر سطح با کندل واقعی پیش از انتشار ویدیو سنجیده شد — `radar_history.py cards`.",
             "> ناحیه و خط روند وارسی نمی‌شوند. زیر روزانه «ماشه‌ای، نه ساختاری» است — قاعده ۴.", ""]
    snaps = [lv["snap"] for c in charts for lv in (c.get("levels") or [])
             if isinstance(lv, dict) and isinstance(lv.get("snap"), dict)]
    if not snaps:
        return lines + [f"{NOT_SNAPPED} — کارت میدان snap ندارد."]
    lines += H.summary_lines(H.summarize(snaps))
    daily = [s["daily"] for s in snaps if isinstance(s.get("daily"), dict)]
    if daily:
        d = H.summarize(daily)
        lines += ["", f"ستون روزانه، برای سطح‌های زیر روزانه: {d['confirmed']} واقعی از {d['n']} "
                      f"سطح یکتا با داده؛ {d['no_data']} بی‌داده."]
    return lines


METHOD_KEYS = ("area", "rule", "where", "library")
METHODS_HEAD = "## روش‌های گوینده — در برابر method-library.md"


def validate_methods(cards: dict) -> list[str]:
    """
    فهرست اختیاری methods سند کارت — نشست ۶ب، خواسته کاربر: روش گوینده با جایش
    در کتابخانه روش، یا «تازه». داوری ماست، نه خوانده از تصویر؛ پس فقط متن، بی‌عدد.
    """
    m = cards.get("methods")
    if m is None:
        return []
    if not isinstance(m, list):
        return ["methods: باید فهرست باشد"]
    errs = []
    for i, x in enumerate(m):
        if not (isinstance(x, dict) and set(x) == set(METHOD_KEYS)
                and all(isinstance(x[k], str) and x[k].strip() for k in METHOD_KEYS)):
            errs.append(f"methods[{i}]: باید شیء متنی ناتهی {{{', '.join(METHOD_KEYS)}}} باشد")
        elif len(x["rule"]) > F.TEXT_MAX:
            errs.append(f"methods[{i}].rule: بالای {F.TEXT_MAX} نویسه")
    return errs


def _methods_section(cards: dict) -> list[str]:
    lines = ["", METHODS_HEAD, ""]
    ms = cards.get("methods")
    if not ms:
        return lines + ["ثبت نشده — سند کارت فهرست `methods` ندارد."]
    fresh = sum(1 for x in ms if x["library"].startswith("تازه"))
    lines += [f"روش تازه: {fresh} از {len(ms)} — بقیه در `method-library.md` هست یا نزدیکش."]
    for area in dict.fromkeys(x["area"] for x in ms):
        lines += ["", f"### {I._cell(area)}", "", "| قاعده | کجا | method-library |", "|---|---|---|"]
        lines += [f"| {I._cell(x['rule'])} | {I._cell(x['where'])} | {I._cell(x['library'])} |"
                  for x in ms if x["area"] == area]
    return lines


def render_report(cards: dict, meta: dict, man: dict | None = None) -> str:
    """
    گزارش ساده فارسی یک ویدیو، فقط از کارت اعتبارسنجی‌شده. عمومی است: هیچ
    حرف گوینده نقل نمی‌شود — speech کارت در گزارش نمی‌آید؛ ادعا از claims، که
    به بیان ماست و سقف دارد.
    """
    cs = cards.get("cards") or []
    charts = [c for c in cs if c.get("is_chart", True) is not False]
    acc = [0, 0]
    _count_values(cs, acc)
    role = meta.get("جایگاه در رادار", "") or "—"
    vote = " — بدون حق رأی" if role == SINGLE_ROLE else ""
    t = lambda c: F.fmt_t(c.get("t", 0))
    lines = [
        f"# گزارش ویدیو — {I._cell(cards.get('title') or meta.get('عنوان') or '—')}", "",
        "> خوانده مدل از فریم، با راهنمای `references/chart-reading.md`. هر عدد از",
        "> تصویر است، نه از حرف. این گزارش نقل‌شده است، نه داده — هیچ عددش مستقیم",
        "> وارد موتور نمی‌شود. حرف گوینده نقل نمی‌شود؛ ادعاها به بیان ما هستند.", "",
        "| مورد | مقدار |", "|---|---|",
        f"| منبع | {I._cell(meta.get('منبع') or cards.get('source') or '—')} |",
        f"| جایگاه | {I._cell(role)}{vote} |",
        f"| تاریخ انتشار | {(meta.get('تاریخ انتشار') or '—')[:10]} |",
        f"| مدت | {I._cell(meta.get('مدت') or '—')} |",
        f"| نشانی | {cards.get('url') or meta.get('نشانی') or '—'} |",
        f"| خوانده | {I._cell(cards.get('read_by') or '—')}، {cards.get('read_at') or '—'} |",
        f"| ابزار فریم | {cards.get('frames_tool') or '—'} |",
        f"| کارت | {len(cs)} — {len(charts)} نمودار |",
        f"| مقدار خوانده از تصویر / ناخوانا | {acc[0]} / {acc[1]} |",
        f"| فایل کارت | `intake/{F.CHARTS_DIR.name}/{cards.get('source')}/{cards.get('video_id')}.json` |",
    ]

    # نمودارها — کارت‌های پیاپی با یک نما یک ردیف‌اند
    lines += ["", "## نمودارها", "", "| زمان | نماد | تایم‌فریم | مقیاس | کارت |", "|---|---|---|---|---|"]
    groups: list[list] = []
    for c in charts:
        key = (_val(c.get("coin")), _val(c.get("timeframe")), _val(c.get("scale")))
        if groups and groups[-1][0] == key:
            groups[-1][1].append(c)
        else:
            groups.append([key, [c]])
    for (coin, tf, scale), g in groups:
        span = t(g[0]) if len(g) == 1 else f"{t(g[0])} تا {t(g[-1])}"
        lines.append(f"| {span} | {I._cell(coin)} | {I._cell(tf)} | {I._cell(scale)} | {len(g)} |")
    other = [c for c in cs if c.get("is_chart", True) is False]
    if other:
        lines += ["", f"فریم غیرنمودار: {len(other)} — " + "، ".join(t(c) for c in other)]

    # سطح‌ها و خط‌ها — تکراری‌ها یک ردیف، با شمار تکرار
    lines += ["", "## سطح‌ها و خط‌ها — هر عدد از تصویر", "",
              "| زمان | نماد | نوع | قیمت | اطمینان | برچسب | وارسی کندل | روزانه |",
              "|---|---|---|---|---|---|---|---|"]
    rows: dict[tuple, list] = {}
    for c in charts:
        coin, tf = _val(c.get("coin")), _val(c.get("timeframe"))
        for kind, price, conf, label, snap_txt, daily_txt in _marks(c):
            k = (coin, tf, kind, price, label, snap_txt, daily_txt)
            if k in rows:
                rows[k][1] += 1
            else:
                rows[k] = [t(c), 1, conf]
    if not rows:
        lines.append("| — | — | — | — | — | هیچ سطح یا خطی خوانده نشد | — | — |")
    for (coin, tf, kind, price, label, snap_txt, daily_txt), (first, n, conf) in rows.items():
        when = first + (f" (×{n})" if n > 1 else "")
        lines.append(f"| {when} | {I._cell(coin)} | {kind} | {I._cell(price)} | {conf} "
                     f"| {I._cell(label)[:80]} | {I._cell(snap_txt)} | {I._cell(daily_txt)} |")
    lines += _snap_section(charts)

    # روش
    notes = list(dict.fromkeys(n for c in cs for n in (c.get("method_notes") or [])))
    pats = list(dict.fromkeys(_val(p.get("name")) for c in charts for p in (c.get("patterns") or [])
                              if isinstance(p, dict)))
    inds = list(dict.fromkeys(_val(i.get("name")) for c in charts for i in (c.get("indicators") or [])
                              if isinstance(i, dict)))
    lines += ["", "## روش", ""]
    if inds:
        lines.append("- اندیکاتورها: " + "، ".join(inds))
    if pats:
        lines.append("- الگوهای نام‌برده: " + "، ".join(pats))
    lines += [f"- {I._cell(n)}" for n in notes] or ["- یادداشت روشی ثبت نشده."]
    lines += _methods_section(cards)

    # ادعاها
    lines += ["", "## ادعاها — به بیان ما، نه نقل", ""]
    if any("claims" in c for c in cs):
        claim_rows = [(c, cl) for c in cs for cl in (c.get("claims") or [])]
        if claim_rows:
            lines += ["| زمان | نماد صفحه | نامزد | ادعا |", "|---|---|---|---|"]
            for c, cl in claim_rows:
                refs = "، ".join(str(r.get("row")) for r in c.get("refs") or [] if r.get("role") == "claim")
                coin = _val(c.get("coin")) if c.get("is_chart", True) is not False else "—"
                lines.append(f"| {t(c)} | {I._cell(coin)} | {refs or '—'} | {I._cell(cl)[:CLAIM_MAX]} |")
        else:
            lines.append("هیچ ادعای قابل‌تسویه‌ای در کارت‌ها ثبت نشد.")
    else:
        lines.append("کارت‌ها میدان `claims` ندارند — خوانده پیش از نشست ۶ب.")
    if man and (man.get("selection") or {}).get("unframed_candidates"):
        un = man["selection"]["unframed_candidates"]
        lines += ["", "نامزد ادعای بی‌فریم: " + "، ".join(str(r) for r in un)]

    # حرف و صفحه
    lines += ["", "## حرف و صفحه", ""]
    svs = [(c, c["speech_vs_screen"]) for c in cs if isinstance(c.get("speech_vs_screen"), dict)]
    if not svs:
        lines.append("ثبت نشده — کارت‌ها میدان `speech_vs_screen` ندارند، خوانده پیش از نشست ۶ب.")
    else:
        n_ok = sum(1 for _, s in svs if s.get("agree") is True)
        bad = [(c, s) for c, s in svs if s.get("agree") is False]
        n_na = sum(1 for _, s in svs if s.get("agree") is None)
        lines += ["| می‌خواند | نمی‌خواند | وارسی‌نشدنی |", "|---|---|---|",
                  f"| {n_ok} | {len(bad)} | {n_na} |", ""]
        if bad:
            lines.append("جاهایی که حرف و صفحه نخواندند:")
            lines += [f"- {t(c)} — صفحه {I._cell(_val(c.get('coin')))}: {I._cell(s.get('note') or '—')}"
                      for c, s in bad]
        else:
            lines.append("هیچ ناهمخوانی‌ای ثبت نشد.")

    lines += ["", f"> ساخته‌شده با radar_video {VERSION} از کارت اعتبارسنجی‌شده."]
    return "\n".join(lines) + "\n"


def report_path(intake: Path, cards: dict) -> Path:
    return intake / I.REPORTS_DIR / str(cards.get("source")) / f"{cards.get('video_id')}.md"


def report_cli(cards_path: Path, intake: Path, frames_root: Path) -> int:
    try:
        cards = json.loads(cards_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⛔ کارت خوانده نشد: {cards_path} — {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    man_path = frames_root / str(cards.get("video_id", "")) / "frames.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else None
    errs = F.validate_cards(cards, man) + validate_methods(cards)
    if errs:
        print(f"⛔ کارت نامعتبر — {len(errs)} خطا؛ گزارش ساخته نشد:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2
    if man is None:
        print(f"⚠️ فهرست فریم {man_path} نیست — هم‌خوانی frame_id سنجیده نشد")
    meta = {}
    doc = Path(str(cards.get("doc") or ""))
    if doc.is_file():
        meta = I._front_matter(doc.read_text(encoding="utf-8"))
    else:
        print(f"⚠️ سند {doc} نیست — شناسنامه گزارش فقط از کارت")
    out = report_path(intake, cards)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(cards, meta, man), encoding="utf-8")
    print(f"✅ گزارش: {out.as_posix()}")
    return 0


# ═══════════════ ۸ — خط فرمان ═══════════════

def main(argv: list[str] | None = None, deps: Deps | None = None) -> int:
    F._utf8_console()
    ap = argparse.ArgumentParser(description="دیدن کامل یک ویدیو یا پلی‌لیست — رادار، نشست ۶ب")
    ap.add_argument("link", nargs="?", help="پیوند ویدیو یا پلی‌لیست یوتیوب")
    ap.add_argument("--limit", type=int, help="پلی‌لیست: چند قسمت تازه، به ترتیب")
    ap.add_argument("--max-frames", type=int, default=F.DEFAULT_MAX_FRAMES)
    ap.add_argument("--force", action="store_true",
                    help="فریم موجود دوباره ساخته شود — نه وقتی کارت نمودار هست")
    ap.add_argument("--whisper", action="store_true", help="رونویسی صوتی اگر زیرنویس نبود")
    ap.add_argument("--report", metavar="CARDS_JSON", help="فقط گزارش ویدیو از کارت")
    ap.add_argument("--config", default="analysts.yml")
    ap.add_argument("--intake", default="intake", help="پوشه، نه فایل")
    ap.add_argument("--frames", default=F.FRAMES_DIR, help="پوشه ریشه فریم‌ها — پوشه، نه فایل")
    a = ap.parse_args(argv)
    intake, frames_root = Path(a.intake), Path(a.frames)
    if a.report:
        return report_cli(Path(a.report), intake, frames_root)
    if not a.link:
        ap.error("پیوند لازم است، یا --report")
    if a.limit is not None and a.limit < 1:
        ap.error("--limit دست‌کم ۱")
    if a.max_frames < 1:
        ap.error("--max-frames دست‌کم ۱")
    try:
        link = parse_link(a.link)
    except LinkError as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    deps = deps or Deps.real(a.whisper)
    listing = link.kind == "playlist" and a.limit is None
    miss = deps.missing(listing, a.whisper)
    if miss:
        print(f"⛔ پیش‌نیاز نیست: {'، '.join(miss)} — pip install -r requirements-intake.txt؛ "
              "ffmpeg و ffprobe جدا", file=sys.stderr)
        return 2
    try:
        state = I.load_state(intake / STATE_NAME)
    except I.IntakeError as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    ctx = Ctx(deps=deps, sources=I.load_sources(Path(a.config)), intake=intake,
              frames_root=frames_root, state=state, max_frames=a.max_frames, force=a.force)

    eps: list[Episode] = []
    untried: list[dict] = []
    if link.kind == "video":
        if a.limit is not None:
            print("ℹ️ --limit فقط برای پلی‌لیست است — نادیده گرفته شد")
        if link.note:
            print(f"ℹ️ {link.note}")
        pos, pl = None, ""
        if known_playlist(ctx.sources, link.playlist_id):
            try:
                pinfo = deps.meta.playlist(link.playlist_id)
            except MetaError as e:
                print(f"⛔ فهرست پلی‌لیست گرفته نشد — {e}", file=sys.stderr)
                return 3
            hit = next((x for x in playlist_entries(pinfo) if x["id"] == link.video_id), None)
            if hit:
                pos, pl = hit["pos"], link.playlist_id
                print(f"ℹ️ قسمت {hit['pos']:02d} از پلی‌لیست شناخته‌شده {link.playlist_id} — "
                      "منبع از analysts.yml")
            else:
                print(f"⚠️ ویدیو در پلی‌لیست {link.playlist_id} نیست — منبع از کانال")
        print(f"▶ ویدیو {link.video_id}")
        ep, _ = _attempt(ctx, link.video_id, pos=pos, playlist_id=pl)
        eps.append(ep)
        head = ep.title or link.video_id
    else:
        try:
            pinfo = deps.meta.playlist(link.playlist_id)
        except MetaError as e:
            print(f"⛔ فهرست پلی‌لیست گرفته نشد — {e}", file=sys.stderr)
            return 3
        entries = playlist_entries(pinfo)
        if not entries:
            print(f"⛔ پلی‌لیست {link.playlist_id} قسمتی ندارد یا خوانده نشد", file=sys.stderr)
            return 3
        head = pinfo.get("title") or link.playlist_id
        if listing:
            status = {}
            for e in entries:
                why = _done(ctx, e["id"])
                if why:
                    status[e["id"]] = f"پیشین — {why}"
                elif e["duration"] is not None and e["duration"] <= I.SHORT_MAX_SECONDS:
                    status[e["id"]] = "کوتاه — رد می‌شود"
                elif e["duration"] is None:
                    status[e["id"]] = "مدت نامعلوم"
                else:
                    status[e["id"]] = "تازه"
            print(render_listing(link, pinfo, entries, status), end="")
            return 0
        taken = 0
        for i, e in enumerate(entries):
            why = _done(ctx, e["id"])
            if why:
                eps.append(Episode(e["pos"], e["id"], title=e["title"], status=f"پیشین — {why}"))
                continue
            if taken >= a.limit:
                break
            if e["duration"] is not None and e["duration"] <= I.SHORT_MAX_SECONDS:
                eps.append(Episode(e["pos"], e["id"], title=e["title"], status="رد شد — کوتاه",
                                   detail=f"{I.fmt_ts(e['duration'])}، ف۸"))
                continue
            print(f"▶ قسمت {e['pos']:02d} — {e['id']}")
            ep, blocked = _attempt(ctx, e["id"], pos=e["pos"], playlist_id=link.playlist_id)
            eps.append(ep)
            taken += 1
            if blocked:
                untried = [x for x in entries[i + 1:] if not _done(ctx, x["id"])]
                break

    problems: list[str] = []
    if ctx.wrote_docs:
        I.save_state(intake / STATE_NAME, ctx.state)
        problems = I.rebuild_index(intake)
    print()
    print(render_summary(head, eps, untried), end="")
    for p in problems:
        print(f"⛔ سند ناخوانا در INDEX: {p}")
    return 3 if any(e.failed for e in eps) or untried or problems else 0


if __name__ == "__main__":
    sys.exit(main())
