"""
پیام روزانه و هفتگی تلگرام با رسید، و خط سبد بالای پیام روزانه — بازبینی ۲۳ اکتبر
۲۰۲۶، یافته م۴.

پیش از این گام تلگرام روزانه و هفتگی با `curl -s ... > /dev/null` می‌فرستاد و
«ارسال شد» را بی‌شرط چاپ می‌کرد؛ قاعده CLAUDE.md می‌گوید radar_telegram.py تنها
راه ارسال است. LATEST.md هم نه رژیم داشت، نه هدف، نه کسری، نه اقدام سبد: جهش هدف
از 25٪ به 40٪ در ۲۰ اکتبر هیچ پیامی نساخت.

قرارداد:
- python radar_telegram.py --file <مسیر> یا --text <متن>: متن ساده، با رسید. کد ۰
  برای موفق و برای «کلید تنظیم نشده»؛ کد ۴ برای ناموفق، مثل پایشگر؛ کد ۲ برای
  فایل غایب. بریدن به نویسه، نه بایت — head -c وسط حرف فارسی می‌برید.
- گام تلگرام روزانه و هفتگی: فقط radar_telegram.py؛ ناموفق یعنی ::error::.
- radar_book.py --line: یک خط — رژیم و باند، هدف ذخیره، ذخیره فعلی، کسری، و یک
  «اقدام سبد»: نخستین ردیف بخش ۶. LATEST.md آن را درست زیر سرتیتر می‌گذارد.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_book as B
import radar_budget as BG
import radar_telegram as TG

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"


def _step(wf: str, name: str) -> str:
    text = (WF / wf).read_text(encoding="utf-8")
    start = text.index(f"- name: {name}\n")
    nxt = text.find("\n      - name:", start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


# ═══════════════ فرمان radar_telegram.py ═══════════════

class _Sent(list):
    reply: dict


@pytest.fixture
def sent(monkeypatch):
    out = _Sent()
    reply = {"r": TG.Sent(True, "کد 200")}

    def fake(text):
        out.append(text)
        return reply["r"]
    monkeypatch.setattr(TG, "send", fake)
    out.reply = reply
    return out


def test_cli_sends_file_and_prints_receipt(tmp_path, sent, capsys) -> None:
    p = tmp_path / "m.txt"
    p.write_text("# گزارش رادار\nخط دوم", encoding="utf-8")
    assert TG.main(["--file", str(p)]) == 0
    assert sent == ["# گزارش رادار\nخط دوم"]
    assert "✅" in capsys.readouterr().out


def test_cli_failure_is_exit_4_with_receipt(tmp_path, sent, capsys) -> None:
    sent.reply["r"] = TG.Sent(False, "کد 400: Bad Request")
    assert TG.main(["--text", "سلام"]) == 4
    assert "⛔" in capsys.readouterr().out and "کد 400" in "".join(sent) + "کد 400"


def test_cli_missing_keys_is_not_failure(sent, capsys) -> None:
    sent.reply["r"] = TG.Sent(None, "کلید تلگرام تنظیم نشده: TELEGRAM_BOT_TOKEN")
    assert TG.main(["--text", "سلام"]) == 0
    assert "تنظیم نشده" in capsys.readouterr().out


def test_cli_missing_file_is_exit_2(tmp_path, sent) -> None:
    assert TG.main(["--file", str(tmp_path / "نیست.txt")]) == 2
    assert sent == []


def test_cli_cuts_by_character_not_byte(tmp_path, sent) -> None:
    p = tmp_path / "long.txt"
    p.write_text("ذخیره " * 2000, encoding="utf-8")
    assert TG.main(["--file", str(p)]) == 0
    assert len(sent[0]) <= TG.MAX_CHARS and sent[0].endswith("…")
    sent[0].encode("utf-8")                                 # حرف نیمه‌کاره ندارد


# ═══════════════ گردش‌کارها ═══════════════

@pytest.mark.parametrize("wf", ["radar-daily.yml", "radar-weekly.yml"])
def test_telegram_steps_use_receipt_function(wf) -> None:
    s = _step(wf, "اعلان تلگرام")
    assert "curl" not in s and "/dev/null" not in s
    assert "python radar_telegram.py" in s and "::error::" in s
    assert "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}" in s
    assert "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}" in s


def test_daily_book_step_writes_line_and_summary_puts_it_on_top() -> None:
    b = _step("radar-daily.yml", "بازبینی سبد و موتور خروج")
    assert "--line /tmp/book_line.txt" in b and "/tmp/book_line.txt" in b.split("::error::")[1]
    s = _step("radar-daily.yml", "ساخت خلاصه امروز")
    assert s.index('echo "# گزارش رادار — $D"') < s.index("book_line") < s.index("تولیدشده خودکار")


# ═══════════════ خط سبد ═══════════════

def _line(reg_name="انقباضی", score=-0.6698777, total=1641.0, stable=234.98925749,
          incomplete=False, plan=True) -> str:
    reg = BG.band_by_name(reg_name) if reg_name else None
    val = {"total": total, "stable_usd": stable, "incomplete": incomplete,
           "missing": ["ETH"] if incomplete else []}
    h = {"positions": [], "ledger": [], "updated": "2026-10-17T20:42:09+00:00",
         "source": "آزمون"}
    rv = None
    if plan:
        from datetime import datetime, timezone
        rp = {"title": "نقشه ذخیره ۱۷ اکتبر", "created": "2026-10-17T15:32:00+00:00",
              "deadline": "2026-10-19T00:00:00+00:00", "account": "LBank",
              "on_deadline": {"cancel_if_band_at_least": "سازنده", "otherwise": "market"},
              "steps": [{"symbol": "ETH", "qty": 0.074, "price": 2490}]}
        hp = dict(h, positions=[{"symbol": "ETH", "book": "position", "status": "open",
                                 "lots": [{"qty": 0.148257, "account": "LBank", "entry": None}]}])
        rv = B.reserve_view(rp, hp, {"ETH": 2405.07}, val,
                            datetime(2026, 10, 22, 12, tzinfo=timezone.utc), band=reg_name)
    s: dict = {}
    B.build_report(h, [], reg, [], "آزمون", val=val, reserve=rv, tband=reg,
                   regime_score=score if reg else None, summary=s)
    return s["line"]


def test_line_has_regime_target_reserve_gap_and_action() -> None:
    line = _line()
    assert "\n" not in line
    for x in ("رژیم -0.670", "باند انقباضی", "هدف ذخیره 40٪", "ذخیره 235 دلار (14.3٪)",
              "کسری 421 دلار", "اقدام سبد:", "نقشه ذخیره ۱۷ اکتبر", "بازار"):
        assert x in line, x
    assert "`" not in line and "**" not in line and "--gross" not in line


def test_line_stale_regime_says_so() -> None:
    line = _line(reg_name=None, plan=False)
    assert "رژیم کهنه" in line and "هدف ذخیره" not in line


def test_line_without_actions() -> None:
    line = _line(reg_name="انبساطی", score=0.7, stable=500.0, plan=False)
    assert "کسری ندارد" in line and "اقدام سبد: هیچ اقدام اجباری" in line


def test_line_flags_incomplete_value() -> None:
    assert "⚠️ ارزش ناقص" in _line(incomplete=True)
