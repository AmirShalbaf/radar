#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_digest.py  —  نسخه ۱.۰
لایه تحلیل روی خروجی radar_intake

سه گزارش می‌سازد:
  ۱. واچ‌لیست  — چه کوین‌هایی بررسی می‌کنند، چند بار، با چه جهتی
  ۲. قواعد     — جمله‌های شرطی و قاعده‌مانند از ویدئوهای آموزشی
  ۳. هم‌پوشانی — کدام کوین در چند منبع مستقل تکرار شده

اصل حاکم:
    این ابزار هم تحلیل نمی‌کند. فقط می‌شمارد و دسته‌بندی می‌کند.
    «چند بار گفته شد» با «درست است» هیچ نسبتی ندارد.
    شمارش تکرار، سنجه محبوبیت است، نه سنجه اعتبار.

اجرا:
    python radar_digest.py                      # هر سه گزارش
    python radar_digest.py --report watchlist
    python radar_digest.py --days 14
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from radar_intake import is_boilerplate, normalize_digits_only, normalize_text
except ImportError:  # اجرای مستقل
    def normalize_text(t):  # type: ignore
        return t or ""

    def normalize_digits_only(t):  # type: ignore
        return t or ""

    def is_boilerplate(t):  # type: ignore
        return False

VERSION = "1.1"
UTC = timezone.utc

# اجبار خروجی یونیکد روی ویندوز فارسی — همان دلیل radar_intake
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


# ===========================================================================
# ۱ — فرهنگ کوین‌ها
# ===========================================================================
#
# نکته حیاتی برای منابع فارسی: کانال فارسی می‌گوید «سولانا»، نه «SOL».
# بدون نام فارسی، شمارش روی محتوای فارسی تقریباً صفر می‌شود.
# نام‌های کوتاه و پرابهام (مثل «تون» یا «آپ») عمداً حذف شده‌اند.

COINS: dict[str, list[str]] = {
    # واچ‌لیست امیر
    "BTC":   [r"\bBTC\b", r"\bbitcoin\b", r"بیت\s*کوین"],
    "ETH":   [r"\bETH\b", r"\bethereum\b", r"اتری?وم", r"\bاتر\b"],
    "SOL":   [r"\bSOL\b", r"\bsolana\b", r"سولانا"],
    "TAO":   [r"\bTAO\b", r"\bbittensor\b", r"بیت\s*تنسور", r"\bتائو\b", r"\bتاو\b"],
    "HYPE":  [r"\bHYPE\b", r"\bhyperliquid\b", r"هایپر\s*لیکو?ی?ید", r"هایپ\b"],
    "ONDO":  [r"\bONDO\b", r"ان?دو\b", r"آندو", r"اوندو"],
    "HBAR":  [r"\bHBAR\b", r"\bhedera\b", r"هدرا", r"اچ\s*بار"],
    "XLM":   [r"\bXLM\b", r"\bstellar\b", r"استلار", r"لومنز"],
    "RNDR":  [r"\bRNDR\b", r"\bRENDER\b", r"رندر"],
    "AAVE":  [r"\bAAVE\b", r"آوه\b", r"آوی\b"],
    "DOGE":  [r"\bDOGE\b", r"\bdogecoin\b", r"دوج"],
    "LINK":  [r"\bLINK\b", r"\bchainlink\b", r"چین\s*لینک"],
    "SUI":   [r"\bSUI\b", r"سویی", r"\bسوی\b"],
    "ZEC":   [r"\bZEC\b", r"\bzcash\b", r"زی\s*کش"],
    "BNB":   [r"\bBNB\b", r"بی\s*ان\s*بی", r"بایننس\s*کوین"],
    "XRP":   [r"\bXRP\b", r"\bripple\b", r"ریپل"],
    # بقیه بازار
    "ADA":   [r"\bADA\b", r"\bcardano\b", r"کاردانو", r"\bآدا\b"],
    "AVAX":  [r"\bAVAX\b", r"\bavalanche\b", r"آوالانچ", r"آواکس"],
    "DOT":   [r"\bDOT\b", r"\bpolkadot\b", r"پولکادات"],
    "LTC":   [r"\bLTC\b", r"\blitecoin\b", r"لایت\s*کوین"],
    "XMR":   [r"\bXMR\b", r"\bmonero\b", r"مونرو"],
    "TON":   [r"\bTON\b", r"\btoncoin\b", r"تون\s*کوین"],
    "SHIB":  [r"\bSHIB\b", r"شیبا"],
    "PEPE":  [r"\bPEPE\b", r"پپه"],
    "APT":   [r"\bAPT\b", r"\baptos\b", r"آپتوس"],
    "ARB":   [r"\bARB\b", r"\barbitrum\b", r"آربیتروم"],
    "OP":    [r"\boptimism\b", r"اپتیمیزم"],
    "NEAR":  [r"\bNEAR protocol\b", r"\bنیر\b"],
    "INJ":   [r"\bINJ\b", r"\binjective\b", r"اینجکتیو"],
    "FIL":   [r"\bFIL\b", r"\bfilecoin\b", r"فایل\s*کوین"],
    "TRX":   [r"\bTRX\b", r"\btron\b", r"ترون"],
    "ATOM":  [r"\bATOM\b", r"\bcosmos\b", r"کازموس", r"اتم\b"],
    "UNI":   [r"\bUNI\b", r"\buniswap\b", r"یونی\s*سواپ"],
    "WIF":   [r"\bWIF\b", r"\bdogwifhat\b"],
    "TIA":   [r"\bTIA\b", r"\bcelestia\b", r"سلستیا"],
    "SEI":   [r"\bSEI\b"],
}

AMIR_WATCHLIST = {"BTC", "ETH", "SOL", "TAO", "HYPE", "ONDO", "HBAR", "XLM",
                  "RNDR", "AAVE", "DOGE", "LINK", "SUI", "ZEC", "BNB", "XRP"}

_COIN_RE = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in COINS.items()}

BULL = [r"\bbullish\b", r"\blong\b", r"\bbuy\b", r"\brally\b", r"\bbreakout\b",
        r"\baccumulat", r"صعودی", r"خرید", r"لانگ", r"رشد", r"پامپ", r"شکست\s*مقاومت"]
BEAR = [r"\bbearish\b", r"\bshort\b", r"\bsell\b", r"\bdump\b", r"\bbreakdown\b",
        r"نزولی", r"فروش", r"شورت", r"ریزش", r"دامپ", r"سقوط", r"اصلاح"]

_BULL_RE = [re.compile(p, re.IGNORECASE) for p in BULL]
_BEAR_RE = [re.compile(p, re.IGNORECASE) for p in BEAR]


# ===========================================================================
# ۲ — الگوی قاعده (برای ویدئوهای آموزشی)
# ===========================================================================
#
# قاعده = جمله شرطی. «اگر الف، آنگاه ب.»
# جمله توصیفی («بازار امروز صعودی بود») قاعده نیست و بک‌تست نمی‌شود.

RULE_PATTERNS = [
    # فارسی — شرطی
    #
    # درس آزمون: نسخه اول پایانه فعل مشخص می‌خواست (باشه|باشد|...).
    # فارسی گفتاری پایانه‌های بی‌شماری دارد: میخوره، نباشه، بشکنه، رد کنه.
    # چهار قاعده از شش قاعده نمونه رد شد. حالا بند شرطی را کامل می‌گیریم
    # و فیلترکردن را به نشانگر قابل‌آزمون‌بودن می‌سپاریم.
    # اصل: در پیش‌فیلتر، فراخوانی (Recall) بر دقت (Precision) مقدم است.
    (r"اگر\s+\S.{10,110}", "شرطی"),
    (r"وقتی\s+(که\s+)?\S.{10,110}", "شرطی"),
    (r"هر\s*وقت\s+\S.{10,110}", "شرطی"),
    (r"زمانی\s*که\s+\S.{10,110}", "شرطی"),
    (r"در\s*صورتی\s*که\s+\S.{10,110}", "شرطی"),
    (r"مگر\s*اینکه\s+\S.{10,100}", "شرطی"),
    # فارسی — دستوری
    (r"(هیچ\s*وقت|هرگز)\s+\S.{8,100}", "منع"),
    (r"(همیشه|حتماً?)\s+\S.{8,100}", "الزام"),
    (r"(باید|نباید)\s+\S.{8,100}", "الزام"),
    (r"(قانون|قاعده|اصل)\s*(اول|دوم|سوم|طلایی|مهم)?\s*[:؛]?\s*\S.{8,100}", "قاعده صریح"),
    (r"(نکته|ترفند)\s*(مهم|کلیدی|اصلی)\s*[:؛]?\s*\S.{8,100}", "قاعده صریح"),
    # انگلیسی
    (r"\bif\s+.{10,110}", "شرطی"),
    (r"\bwhen(ever)?\s+.{10,110}", "شرطی"),
    (r"\bnever\s+.{8,100}", "منع"),
    (r"\balways\s+.{8,100}", "الزام"),
    (r"\bthe rule is\b.{8,100}", "قاعده صریح"),
    (r"\byou (should|must|need to)\s+.{8,100}", "الزام"),
    (r"\bmake sure (you|to)\s+.{8,100}", "الزام"),
]

_RULE_RE = [(re.compile(p, re.IGNORECASE), kind) for p, kind in RULE_PATTERNS]

# نشانه اینکه قاعده *قابل کدنویسی* است: عدد یا نام اندیکاتور دارد
TESTABLE_MARKERS = [
    r"\bRSI\b", r"\bMACD\b", r"\bEMA\s*\d*", r"\bSMA\s*\d*", r"\bATR\b",
    r"\bvolume\b", r"\bfibonacci\b", r"\bstop\b", r"\bR\s*/\s*R\b",
    r"شاخص\s*قدرت", r"میانگین\s*متحرک", r"حجم", r"فیبوناچی", r"حد\s*ضرر",
    r"تایم\s*فریم", r"کندل", r"\d+\s*(درصد|%)", r"\b\d{1,3}\b",
]
_TESTABLE_RE = [re.compile(p, re.IGNORECASE) for p in TESTABLE_MARKERS]


# ===========================================================================
# ۳ — خواندن اسناد جمع‌آوری‌شده
# ===========================================================================

@dataclass
class Doc:
    path: Path
    meta: dict
    body: str

    @property
    def source(self) -> str:
        return self.meta.get("منبع", "؟")

    @property
    def role(self) -> str:
        return self.meta.get("جایگاه در رادار", "؟")

    @property
    def date(self) -> str:
        return (self.meta.get("تاریخ انتشار", "") or "")[:10]

    @property
    def title(self) -> str:
        return self.meta.get("عنوان", "")


def load_docs(intake: Path, days: int | None) -> list[Doc]:
    cutoff = None
    if days:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    docs = []
    for f in sorted(intake.rglob("*.md")):
        if f.name == "INDEX.md":
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = {}, txt
        if txt.startswith("---"):
            parts = txt.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = parts[2]
        if "## متن کامل" in body:
            body = body.split("## متن کامل", 1)[1]
        d = Doc(path=f, meta=meta, body=body)
        if cutoff and d.date and d.date < cutoff:
            continue
        docs.append(d)
    return docs


def sentences(body: str) -> list[str]:
    """خطوط مهردار را به جمله می‌شکند و مهر زمانی را نگه می‌دارد."""
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line or is_boilerplate(line):
            continue
        out.append(line)
    return out


# ===========================================================================
# ۴ — گزارش واچ‌لیست
# ===========================================================================

@dataclass
class CoinStat:
    mentions: int = 0
    bull: int = 0
    bear: int = 0
    sources: set[str] = field(default_factory=set)
    samples: list[tuple[str, str]] = field(default_factory=list)  # (منبع، متن)


def report_watchlist(docs: list[Doc]) -> str:
    stats: dict[str, CoinStat] = defaultdict(CoinStat)

    for d in docs:
        for line in sentences(d.body):
            probe = normalize_digits_only(normalize_text(line))
            hits = [c for c, pats in _COIN_RE.items() if any(p.search(probe) for p in pats)]
            if not hits:
                continue
            b = any(p.search(probe) for p in _BULL_RE)
            r = any(p.search(probe) for p in _BEAR_RE)
            for c in hits:
                st = stats[c]
                st.mentions += 1
                st.sources.add(d.source)
                if b and not r:
                    st.bull += 1
                elif r and not b:
                    st.bear += 1
                if len(st.samples) < 3 and (b or r):
                    st.samples.append((d.source, line[:150]))

    if not stats:
        return "## گزارش واچ‌لیست\n\nهیچ نام کوینی پیدا نشد.\n"

    rows = []
    for c, s in sorted(stats.items(), key=lambda kv: -kv[1].mentions):
        if s.bull > s.bear * 1.5:
            lean = "صعودی"
        elif s.bear > s.bull * 1.5:
            lean = "نزولی"
        elif s.bull or s.bear:
            lean = "مختلط"
        else:
            lean = "بی‌جهت"
        inw = "✅" if c in AMIR_WATCHLIST else "➕ تازه"
        rows.append(
            f"| {c} | {s.mentions} | {len(s.sources)} | {s.bull} | {s.bear} | {lean} | {inw} |"
        )

    new_coins = [c for c in stats if c not in AMIR_WATCHLIST]
    missing = [c for c in sorted(AMIR_WATCHLIST) if c not in stats]

    out = [
        "## گزارش ۱ — واچ‌لیست منابع",
        "",
        "**هشدار تفسیر:** تعداد تکرار سنجه *محبوبیت* است، نه *اعتبار*.",
        "کوینی که ده بار نام برده شد، ده برابر بهتر نیست — ده برابر پرسروصداتر است.",
        "",
        "| کوین | تکرار | منابع | صعودی | نزولی | تمایل | در واچ‌لیست تو |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**نام‌های تازه (خارج از واچ‌لیست تو):** {'، '.join(new_coins) if new_coins else 'هیچ'}",
        "",
        f"**در واچ‌لیست تو ولی هیچ‌کس بررسی نکرده:** {'، '.join(missing) if missing else 'هیچ'}",
        "",
        "> کوینی که هیچ‌کس درباره‌اش حرف نمی‌زند، لزوماً بد نیست.",
        "> گاهی یعنی هنوز شلوغ نشده. این ستون را به‌عنوان *سؤال* بخوان، نه *حکم*.",
        "",
    ]

    if any(s.samples for s in stats.values()):
        out += ["### نمونه جمله‌های جهت‌دار", ""]
        for c, s in sorted(stats.items(), key=lambda kv: -kv[1].mentions)[:8]:
            for src, txt in s.samples[:2]:
                out.append(f"- **{c}** ({src}): {txt}")
        out.append("")
    return "\n".join(out)


# ===========================================================================
# ۵ — گزارش قواعد
# ===========================================================================

def report_rules(docs: list[Doc], roles: tuple[str, ...] = ("کتابخانه روش",),
                 all_roles: bool = False) -> str:
    found: list[tuple[str, str, str, bool]] = []   # (منبع، نوع، متن، قابل‌آزمون)
    seen: set[str] = set()

    # قاعده خوب می‌تواند در هر منبعی ظاهر شود، ولی پیش‌فرض روی کتابخانه روش است
    # تا گزارش با توصیف بازار پر نشود. --all-roles این قید را برمی‌دارد.
    pool = docs if all_roles else ([d for d in docs if d.role in roles] or docs)

    for d in pool:
        for line in sentences(d.body):
            probe = normalize_digits_only(normalize_text(line))
            for rx, kind in _RULE_RE:
                m = rx.search(probe)
                if not m:
                    continue
                txt = m.group(0).strip()
                if len(txt) < 15:
                    continue
                key = txt[:60]
                if key in seen:
                    continue
                seen.add(key)
                testable = any(p.search(txt) for p in _TESTABLE_RE)
                found.append((d.source, kind, txt[:200], testable))
                break

    if not found:
        return (
            "## گزارش ۲ — قواعد\n\n"
            "هیچ جمله شرطی یا قاعده‌مانندی پیدا نشد.\n\n"
            "**این خودش یک داده است:** محتوایی که قاعده شرطی نمی‌دهد، "
            "قابل کدنویسی و بک‌تست نیست. توصیف است، نه روش.\n"
        )

    testable = [f for f in found if f[3]]
    soft = [f for f in found if not f[3]]

    out = [
        "## گزارش ۲ — قواعد استخراج‌شده",
        "",
        f"{len(found)} جمله قاعده‌مانند. {len(testable)} مورد قابل کدنویسی.",
        "",
        "**دروازه ورود به رادار** (قانون بازگشت فهرست ردشده‌ها):",
        "آزمون خارج از نمونه، پس از کسر کارمزد و نرخ تأمین مالی، روی حداقل سه دارایی.",
        "",
        "### الف — قابل کدنویسی (عدد یا اندیکاتور دارد)",
        "",
        "| منبع | نوع | قاعده |",
        "|---|---|---|",
    ]
    for src, kind, txt, _ in testable[:30]:
        out.append(f"| {src} | {kind} | {txt.replace('|', '/')} |")

    out += ["", "### ب — کیفی (بدون آستانه عددی — بک‌تست نمی‌شود)", ""]
    if soft:
        out += ["| منبع | نوع | جمله |", "|---|---|---|"]
        for src, kind, txt, _ in soft[:20]:
            out.append(f"| {src} | {kind} | {txt.replace('|', '/')} |")
    else:
        out.append("موردی نبود.")
    out += [
        "",
        "> قاعده بدون آستانه عددی، **نصیحت** است نه روش.",
        "> «صبور باش» بک‌تست نمی‌شود. «اگر شاخص قدرت زیر ۳۰ رفت، وارد نشو» می‌شود.",
        "",
    ]
    return "\n".join(out)


# ===========================================================================
# ۶ — گزارش هم‌پوشانی
# ===========================================================================

def report_overlap(docs: list[Doc]) -> str:
    by_coin: dict[str, set[str]] = defaultdict(set)
    for d in docs:
        for line in sentences(d.body):
            probe = normalize_digits_only(normalize_text(line))
            for c, pats in _COIN_RE.items():
                if any(p.search(probe) for p in pats):
                    by_coin[c].add(d.source)

    multi = {c: s for c, s in by_coin.items() if len(s) >= 2}
    if not multi:
        return "## گزارش ۳ — هم‌پوشانی\n\nهیچ کوینی در بیش از یک منبع نیامد.\n"

    rows = [
        f"| {c} | {len(s)} | {'، '.join(sorted(s))} |"
        for c, s in sorted(multi.items(), key=lambda kv: -len(kv[1]))
    ]
    return "\n".join([
        "## گزارش ۳ — هم‌پوشانی منابع",
        "",
        "| کوین | تعداد منبع | منابع |",
        "|---|---|---|",
        *rows,
        "",
        "**هشدار هم‌خطی — مهم‌ترین بند این گزارش:**",
        "",
        "اگر دو منبع فارسی هر دو از یک منبع انگلیسی ترجمه می‌کنند،",
        "توافقشان **یک رأی** است، نه دو رأی. این همان توهم هم‌گرایی بند ۴.۱ رادار است،",
        "فقط در سطح انسان به‌جای سطح اندیکاتور.",
        "",
        "پیش از شمردن این توافق به‌عنوان تأیید، بپرس: منبع اصلی هر دو کیست؟",
        "",
    ])


# ===========================================================================
# ۷ — اجرا
# ===========================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="لایه تحلیل خروجی جمع‌آوری رادار")
    ap.add_argument("--intake", default="intake")
    ap.add_argument("--out", default="intake/DIGEST.md")
    ap.add_argument("--days", type=int, default=None, help="فقط N روز اخیر")
    ap.add_argument("--report", choices=["watchlist", "rules", "overlap", "all"],
                    default="all")
    ap.add_argument("--all-roles", action="store_true", dest="all_roles",
                    help="استخراج قاعده از همه منابع، نه فقط کتابخانه روش")
    args = ap.parse_args()

    intake = Path(args.intake)
    if not intake.exists():
        print(f"پوشه {intake} نیست. اول radar_intake.py را اجرا کن.")
        return 1

    docs = load_docs(intake, args.days)
    if not docs:
        print("هیچ سندی پیدا نشد.")
        return 1

    srcs = sorted({d.source for d in docs})
    header = [
        "# چکیده منابع رادار",
        "",
        f"ساخته‌شده: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"radar_digest {VERSION}",
        f"اسناد: {len(docs)} | منابع: {len(srcs)}",
        f"بازه: {'همه' if not args.days else f'{args.days} روز اخیر'}",
        "",
        f"منابع: {'، '.join(srcs)}",
        "",
        "> **برچسب معرفتی: نقل‌شده.** هیچ عددی از این گزارش وارد امتیازدهی نمی‌شود.",
        "",
        "---",
        "",
    ]

    parts = []
    if args.report in ("watchlist", "all"):
        parts.append(report_watchlist(docs))
    if args.report in ("rules", "all"):
        parts.append(report_rules(docs, all_roles=args.all_roles))
    if args.report in ("overlap", "all"):
        parts.append(report_overlap(docs))

    text = "\n".join(header) + "\n---\n\n".join(parts)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    print(f"✓ {len(docs)} سند از {len(srcs)} منبع → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
