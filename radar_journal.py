#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar_journal.py — ژورنال و موتور کالیبراسیون رادار
=====================================================

چرا وجود دارد: وزن‌ها و آستانه‌های رادار **فرض** هستند، نه نتیجه آزمون.
تا وقتی پیش‌بینی چارچوب کنار نتیجه واقعی ثبت نشود، هیچ‌چیز یاد گرفته نمی‌شود
و چارچوب برای همیشه روی حدس‌های روز اول قفل می‌ماند.

    python radar_journal.py add --symbol ZEC --side long --entry 524 \\
        --stop 476 --target 575 --size 200 --verdict no-entry \\
        --decision entered --rr 1.32 --ev -0.60 --note "خلاف حکم چارچوب" \\
        --setup-name "ب۱ — بازپس‌گیری پس از دررفتگی عمیق" --decision-id D-2026-09-05-1

    python radar_journal.py update          # قیمت زنده، R تحقق‌نیافته، هشدارها
    python radar_journal.py close --id 1 --exit 575 --reason target
    python radar_journal.py report          # گزارش کالیبراسیون
    python radar_journal.py list

فایل داده: journal.json کنار همین اسکریپت. **در .gitignore بگذارش** —
موقعیت‌های معاملاتی داده شخصی است.
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone

UTC = timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "journal.json")

# پیش از کتابخانه ستاپ، رکوردها نام ستاپ و شناسه تصمیم نداشتند.
# قانون سوگیری صفر: خالی نگذار، ولی هم برچسبش بزن که «نامشخص» است.
UNKNOWN_SETUP = "نامشخص — پیش از کتابخانه ستاپ"


def load() -> dict:
    if not os.path.exists(DB):
        return {"version": 1, "trades": []}
    try:
        with open(DB, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as exc:
        print(f"خطا در خواندن ژورنال: {exc}", file=sys.stderr)
        sys.exit(1)
    for t in d.get("trades", []):
        t.setdefault("setup_name", UNKNOWN_SETUP)
        t.setdefault("decision_id", UNKNOWN_SETUP)
    return d


def save(d: dict) -> None:
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def price_now(symbol: str) -> float | None:
    """قیمت زنده. اگر شبکه نبود None — هرگز عدد ساختگی."""
    try:
        sys.path.insert(0, HERE)
        import radar_fetch3 as R
        d = R.okx_get("/api/v5/market/ticker",
                      {"instId": f"{symbol.upper()}-USDT"}, label="قیمت زنده")
        if d and d[0].get("last"):
            return float(d[0]["last"])
    except Exception:
        pass
    return None


def r_multiple(t: dict, px: float) -> float | None:
    """نتیجه برحسب R — واحد استاندارد مقایسه معاملات با اندازه متفاوت."""
    risk = abs(t["entry"] - t["stop"])
    if risk <= 0:
        return None
    move = (px - t["entry"]) if t["side"] == "long" else (t["entry"] - px)
    return move / risk


# ═══════════════════ دستورها ═══════════════════

def cmd_add(a) -> None:
    d = load()
    tid = max([t["id"] for t in d["trades"]], default=0) + 1
    risk_pct = 100 * abs(a.entry - a.stop) / a.entry
    t = {
        "id": tid,
        "opened": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": a.symbol.upper(), "side": a.side,
        "entry": a.entry, "stop": a.stop, "target": a.target,
        # نقطه ابطال با استاپ فرق دارد: استاپ یک سفارش است که روی سایه
        # فعال می‌شود؛ ابطال یک **حکم ساختاری** است که فقط با بسته‌شدن
        # کندل روزانه سنجیده می‌شود.
        "invalidation": a.invalidation,
        "setup_name": a.setup_name, "decision_id": a.decision_id,
        "size_usd": a.size, "leverage": a.leverage,
        "risk_pct": round(risk_pct, 2),
        "risk_usd": round(a.size * risk_pct / 100, 2),
        # ── ثبت پیش‌بینی چارچوب در لحظه تصمیم. این ستون قلب کالیبراسیون است.
        "framework_verdict": a.verdict,       # enter / no-entry / wait
        "user_decision": a.decision,           # followed / entered / skipped
        "rr_planned": a.rr, "ev_planned": a.ev,
        "regime_score": a.regime, "coin_score": a.score,
        "note": a.note, "status": "open",
        "exit": None, "closed": None, "exit_reason": None,
        "r_realized": None,
    }
    d["trades"].append(t)
    save(d)
    print(f"✅ ثبت شد — شناسه {tid}")
    print(f"   {t['symbol']} {t['side']} | ورود {a.entry} | استاپ {a.stop} "
          f"({risk_pct:.2f}%) | ریسک {t['risk_usd']} دلار")
    if a.verdict != "enter" and a.decision == "entered":
        print("   ⚠️ این معامله **خلاف حکم چارچوب** ثبت شد — "
              "داده کالیبراسیون ارزشمندی می‌سازد.")


def cmd_update(a) -> None:
    d = load()
    op = [t for t in d["trades"] if t["status"] == "open"]
    if not op:
        print("موقعیت بازی نیست.")
        return
    print(f"{'#':<4}{'نماد':<8}{'جهت':<7}{'ورود':>10}{'الان':>10}"
          f"{'R':>8}{'سود/زیان':>11}  وضعیت")
    print("-" * 74)
    for t in op:
        px = price_now(t["symbol"])
        if px is None:
            print(f"{t['id']:<4}{t['symbol']:<8}{t['side']:<7}"
                  f"{t['entry']:>10.4f}{'—':>10}{'—':>8}{'—':>11}  قیمت در دسترس نیست")
            continue
        r = r_multiple(t, px)
        pnl = t["size_usd"] * (px / t["entry"] - 1) * (1 if t["side"] == "long" else -1)
        # هشدارها: نزدیکی به استاپ یا هدف
        st = ""
        d_stop = abs(px - t["stop"]) / px * 100
        d_tgt = abs(t["target"] - px) / px * 100 if t.get("target") else None
        if (t["side"] == "long" and px <= t["stop"]) or \
           (t["side"] == "short" and px >= t["stop"]):
            st = "⛔ استاپ رد شد — ببند"
        elif d_stop < 2:
            st = f"⚠️ {d_stop:.1f}٪ تا استاپ"
        elif t.get("target") and (
                (t["side"] == "long" and px >= t["target"]) or
                (t["side"] == "short" and px <= t["target"])):
            st = "🎯 هدف خورد"
        elif d_tgt is not None and d_tgt < 2:
            st = f"🎯 {d_tgt:.1f}٪ تا هدف"
        else:
            st = "باز"
        print(f"{t['id']:<4}{t['symbol']:<8}{t['side']:<7}{t['entry']:>10.4f}"
              f"{px:>10.4f}{r:>+8.2f}{pnl:>+11.2f}  {st}")
    print()
    print("R = نتیجه تقسیم بر ریسک اولیه. R=+۲ یعنی دو برابر آنچه ریسک کردی سود کردی.")


def cmd_close(a) -> None:
    d = load()
    t = next((x for x in d["trades"] if x["id"] == a.id), None)
    if not t:
        print(f"معامله {a.id} پیدا نشد."); return
    if t["status"] != "open":
        print(f"معامله {a.id} از قبل بسته است."); return
    t["exit"] = a.exit
    t["closed"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    t["exit_reason"] = a.reason
    t["r_realized"] = round(r_multiple(t, a.exit), 3)
    t["status"] = "closed"
    t["lesson"] = a.lesson
    pnl = t["size_usd"] * (a.exit / t["entry"] - 1) * (1 if t["side"] == "long" else -1)
    t["pnl_usd"] = round(pnl, 2)
    save(d)
    print(f"✅ بسته شد — {t['symbol']} {t['side']}")
    print(f"   R محقق‌شده: {t['r_realized']:+.2f} | سود/زیان: {pnl:+.2f} دلار")


def cmd_list(a) -> None:
    d = load()
    if not d["trades"]:
        print("ژورنال خالی است."); return
    for t in d["trades"]:
        r = f"{t['r_realized']:+.2f}R" if t["r_realized"] is not None else "باز"
        print(f"[{t['id']:>2}] {t['opened'][:10]} {t['symbol']:<6} {t['side']:<5} "
              f"ورود {t['entry']:<10.4f} → {r:<8} "
              f"| حکم چارچوب: {t['framework_verdict']:<9} تصمیم: {t['user_decision']}")


def cmd_report(a) -> None:
    """
    گزارش کالیبراسیون — تنها بخشی که واقعاً یاد می‌گیرد.

    پرسش مرکزی: آیا وقتی چارچوب «ورود» گفت، نتیجه بهتر از وقتی بود که
    «بدون ورود» گفت و تو وارد شدی؟ اگر نه، وزن‌ها یا آستانه‌ها غلط‌اند.
    """
    import statistics as st
    d = load()
    cl = [t for t in d["trades"] if t["status"] == "closed" and t["r_realized"] is not None]
    op = [t for t in d["trades"] if t["status"] == "open"]

    print("# گزارش کالیبراسیون رادار\n")
    print(f"تاریخ: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"معاملات بسته: **{len(cl)}** | باز: **{len(op)}**\n")

    if len(cl) < 5:
        print(f"> ⚠️ فقط {len(cl)} معامله بسته ثبت شده. **زیر ۵ مورد، هیچ نتیجه‌ای")
        print("> آماری معتبر نیست.** ادامه بده تا نمونه جمع شود. نتایج زیر")
        print("> صرفاً توصیفی‌اند، نه شاهد.\n")

    if not cl:
        print("هنوز معامله بسته‌ای نیست.")
        return

    rs = [t["r_realized"] for t in cl]
    wins = [r for r in rs if r > 0]
    print("## ۱ — عملکرد کلی\n")
    print("| سنجه | مقدار |")
    print("|---|---|")
    print(f"| تعداد | {len(cl)} |")
    print(f"| نرخ برد | {100*len(wins)/len(cl):.0f}٪ |")
    print(f"| **مجموع R** | **{sum(rs):+.2f}** |")
    print(f"| میانگین R | {st.mean(rs):+.3f} |")
    print(f"| میانه R | {st.median(rs):+.3f} |")
    print(f"| بهترین | {max(rs):+.2f} |  ")
    print(f"| بدترین | {min(rs):+.2f} |")
    if len(rs) > 1:
        print(f"| انحراف معیار R | {st.stdev(rs):.3f} |")
    print()

    # ── آزمون مرکزی: حکم چارچوب در برابر نتیجه
    print("## ۲ — آیا حکم چارچوب ارزش داشت؟\n")
    groups: dict[str, list[float]] = {}
    for t in cl:
        key = f"{t['framework_verdict']} / {t['user_decision']}"
        groups.setdefault(key, []).append(t["r_realized"])
    print("| حکم چارچوب / تصمیم تو | تعداد | میانگین R | مجموع R |")
    print("|---|---|---|---|")
    for k, v in sorted(groups.items(), key=lambda x: -st.mean(x[1])):
        print(f"| {k} | {len(v)} | {st.mean(v):+.3f} | {sum(v):+.2f} |")
    print()

    aligned = [t["r_realized"] for t in cl
               if (t["framework_verdict"] == "enter" and t["user_decision"] in ("followed", "entered"))]
    against = [t["r_realized"] for t in cl
               if t["framework_verdict"] != "enter" and t["user_decision"] == "entered"]
    if aligned and against:
        da = st.mean(aligned) - st.mean(against)
        print(f"**هم‌جهت با چارچوب:** {st.mean(aligned):+.3f}R میانگین ({len(aligned)} مورد)")
        print(f"**خلاف چارچوب:** {st.mean(against):+.3f}R میانگین ({len(against)} مورد)")
        print()
        if da > 0.3:
            print("> ✅ چارچوب ارزش افزوده دارد — پیروی از آن نتیجه بهتری داده.")
        elif da < -0.3:
            print("> ⛔ **معاملات خلاف چارچوب بهتر بوده‌اند.** یا آستانه‌ها")
            print("> بیش از حد سخت‌گیرانه‌اند، یا نمونه هنوز کوچک است.")
        else:
            print("> ⚪ تفاوت معنادار نیست. نمونه بیشتری لازم است.")
        print()

    # ── آیا R/R پیش‌بینی‌شده با نتیجه رابطه دارد؟
    pairs = [(t["rr_planned"], t["r_realized"]) for t in cl if t.get("rr_planned")]
    if len(pairs) >= 5:
        print("## ۳ — آیا R/R پیش‌بینی‌شده پیش‌بین خوبی بود؟\n")
        hi = [r for rr, r in pairs if rr >= 2.0]
        lo = [r for rr, r in pairs if rr < 2.0]
        print("| گروه | تعداد | میانگین R |")
        print("|---|---|---|")
        if hi: print(f"| R/R پیش‌بینی ≥ ۲ | {len(hi)} | {st.mean(hi):+.3f} |")
        if lo: print(f"| R/R پیش‌بینی < ۲ | {len(lo)} | {st.mean(lo):+.3f} |")
        print()
        if hi and lo and st.mean(hi) <= st.mean(lo):
            print("> ⚠️ **آستانه ۲:۱ در داده تو تفکیک نمی‌کند.** بازنگری لازم است.")
            print()

    # ── دلایل خروج
    print("## ۴ — دلایل خروج\n")
    rz: dict[str, list[float]] = {}
    for t in cl:
        rz.setdefault(t.get("exit_reason") or "نامشخص", []).append(t["r_realized"])
    print("| دلیل | تعداد | میانگین R |")
    print("|---|---|---|")
    for k, v in sorted(rz.items(), key=lambda x: -len(x[1])):
        print(f"| {k} | {len(v)} | {st.mean(v):+.3f} |")
    print()

    # ── درس‌ها
    ls = [(t["symbol"], t["r_realized"], t.get("lesson"))
          for t in cl if t.get("lesson")]
    if ls:
        print("## ۵ — درس‌های ثبت‌شده\n")
        for s, r, l in ls:
            print(f"- **{s}** ({r:+.2f}R): {l}")
        print()

    print("---\n")
    print("**این گزارش را در گفت‌وگو با کلاود بچسبان و بنویس «کالیبراسیون رادار».**")


def daily_close(symbol: str) -> tuple[float, str] | None:
    """آخرین کندل روزانه **بسته‌شده**. کندل باز شمرده نمی‌شود."""
    try:
        sys.path.insert(0, HERE)
        import radar_fetch3 as R
        d = R.okx_get("/api/v5/market/candles",
                      {"instId": f"{symbol.upper()}-USDT", "bar": "1D", "limit": "3"},
                      label="کندل روزانه")
        if not d:
            return None
        for row in d:                       # از جدید به قدیم
            if str(row[8]) == "1":          # confirm == 1
                ts = datetime.fromtimestamp(int(row[0]) / 1000, UTC)
                return float(row[4]), ts.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def cmd_check(a) -> None:
    """
    بررسی خودکار موقعیت‌های باز. برای اجرا در گیت‌هاب اکشنز طراحی شده.
    خروجی: خطوط هشدار. کد خروج ۱ اگر هشداری هست، ۰ اگر نیست.
    """
    d = load()
    op = [t for t in d["trades"] if t["status"] == "open"]
    alerts: list[str] = []
    for t in op:
        sym = t["symbol"]
        px = price_now(sym)
        dc = daily_close(sym)

        # ۱ — ابطال ساختاری: فقط با بسته روزانه
        inv = t.get("invalidation")
        if inv and dc:
            close, day = dc
            broken = close < inv if t["side"] == "long" else close > inv
            if broken:
                alerts.append(
                    f"⛔ {sym}: بسته روزانه {day} = {close:.4f} — "
                    f"نقطه ابطال {inv} نقض شد. تز باطل است، دستی ببند.")

        # ۲ — استاپ سخت
        if px is not None:
            hit = px <= t["stop"] if t["side"] == "long" else px >= t["stop"]
            if hit:
                alerts.append(f"⛔ {sym}: قیمت {px:.4f} از استاپ {t['stop']} رد شد.")
            else:
                dist = abs(px - t["stop"]) / px * 100
                if dist < 2.5:
                    alerts.append(f"⚠️ {sym}: {dist:.1f}٪ تا استاپ ({px:.4f})")
            if t.get("target"):
                reached = px >= t["target"] if t["side"] == "long" else px <= t["target"]
                if reached:
                    alerts.append(f"🎯 {sym}: هدف {t['target']} خورد — قیمت {px:.4f}")
                else:
                    dt = abs(t["target"] - px) / px * 100
                    if dt < 2.5:
                        alerts.append(f"🎯 {sym}: {dt:.1f}٪ تا هدف ({px:.4f})")

        # ۳ — مهلت بازبینی
        try:
            opened = datetime.strptime(t["opened"][:10], "%Y-%m-%d").replace(tzinfo=UTC)
            days = (datetime.now(UTC) - opened).days
            if days >= 7 and days % 7 == 0:
                alerts.append(f"📅 {sym}: {days} روز باز است — بازبینی دوره‌ای")
        except Exception:
            pass

    if alerts:
        print("\n".join(alerts))
        sys.exit(1)
    print("بدون هشدار — همه موقعیت‌ها در محدوده.")


def main() -> int:
    ap = argparse.ArgumentParser(description="ژورنال و کالیبراسیون رادار")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="ثبت معامله جدید")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", choices=["long", "short"], required=True)
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float, default=None)
    p.add_argument("--invalidation", type=float, default=None,
                   help="سطح ابطال ساختاری — با بسته روزانه سنجیده می‌شود")
    p.add_argument("--setup-name", dest="setup_name", required=True,
                   help="نام ستاپ از کتابخانه ستاپ — بدون آن ورود تعریف‌شده نیست")
    p.add_argument("--decision-id", dest="decision_id", required=True,
                   help="شناسه تصمیم — همان که در تحلیل باز شد")
    p.add_argument("--size", type=float, required=True, help="حجم دلاری")
    p.add_argument("--leverage", type=float, default=1.0)
    p.add_argument("--verdict", default="unknown",
                   choices=["enter", "no-entry", "wait", "unknown"],
                   help="حکم چارچوب در لحظه تصمیم")
    p.add_argument("--decision", default="entered",
                   choices=["followed", "entered", "skipped"],
                   help="تصمیم تو")
    p.add_argument("--rr", type=float, default=None, help="R/R پیش‌بینی‌شده")
    p.add_argument("--ev", type=float, default=None, help="امید ریاضی درصدی")
    p.add_argument("--regime", type=float, default=None, help="امتیاز رژیم")
    p.add_argument("--score", type=float, default=None, help="امتیاز کوین")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="قیمت زنده و هشدار موقعیت‌های باز")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("close", help="بستن معامله")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--exit", type=float, required=True)
    p.add_argument("--reason", default="manual",
                   choices=["target", "stop", "invalidation", "manual", "time"])
    p.add_argument("--lesson", default="", help="درس این معامله")
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("list", help="فهرست همه معاملات")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("check", help="بررسی خودکار — برای گیت‌هاب اکشنز")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("report", help="گزارش کالیبراسیون")
    p.set_defaults(func=cmd_report)

    a = ap.parse_args()
    a.func(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
