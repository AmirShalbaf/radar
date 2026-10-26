"""
گزارش روزانه زودتر و تلاش دوباره push ربات — بند ۵ متن ۲۰، ۲۷ اکتبر ۲۰۲۶.

یافته ت۵: زمان‌بند گیت‌هاب گزارش روزانه را ۴٫۶ تا ۹٫۴ ساعت دیر می‌سازد. نوبت‌های 00:37،
02:37 و 04:37 کنار 06:37 و 08:37، با همان نگهبان. با نبض ساعتی و پنج نوبت روزانه، push
هم‌زمان دو کار محتمل‌تر است: push ردشده تا ۳ بار با git fetch و git merge --no-edit دوباره؛
force و rebase ممنوع؛ تداخل واقعی خطای روشن، نه بی‌صدا.

آزمون‌ها با مخزن بی‌پوشه محلی — بی شبکه.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_schedule as S

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / ".github" / "workflows"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git نصب نیست")


def git(cwd, *args, check=True):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def _commit(repo, name, text, msg):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """
    یک بار در پرونده: مخزن مرکزی، و دو برداشت — ربات و «کار دیگر» که زودتر push
    می‌کند. هر آزمون رونوشت تازه می‌گیرد؛ ساخت گیت روی ویندوز کند است.
    """
    base = tmp_path_factory.mktemp("git_template")
    remote = base / "remote.git"
    git(base, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = base / "seed"
    git(base, "clone", "-q", str(remote), str(seed))
    git(seed, "symbolic-ref", "HEAD", "refs/heads/main")
    for i in range(3):
        _commit(seed, "base.txt", f"پایه {i}\n", f"پایه {i}")
    git(seed, "push", "-q", "origin", "main")
    url = remote.as_uri()
    git(base, "clone", "-q", "--depth", "1", url, str(base / "bot"))   # مثل actions/checkout
    git(base, "clone", "-q", url, str(base / "other"))
    for r in (base / "bot", base / "other"):
        git(r, "config", "user.name", "radar-bot")
        git(r, "config", "user.email", "bot@x")
    return base


@pytest.fixture
def repos(_template, tmp_path):
    for n in ("remote.git", "bot", "other"):
        shutil.copytree(_template / n, tmp_path / n)
    remote, bot, other = tmp_path / "remote.git", tmp_path / "bot", tmp_path / "other"
    for r in (bot, other):
        git(r, "remote", "set-url", "origin", remote.as_uri())
    return remote, bot, other


def test_push_first_try(repos) -> None:
    remote, bot, _ = repos
    _commit(bot, "reports.md", "گزارش\n", "گزارش")
    rc, log = S.push_with_retry(cwd=bot)
    assert rc == 0 and len([x for x in log if x.startswith("push")]) == 1
    assert git(remote, "rev-parse", "main") == git(bot, "rev-parse", "HEAD")


def test_rejected_push_merges_and_retries_no_rebase(repos) -> None:
    remote, bot, other = repos
    theirs = _commit(other, "pulse.md", "نبض\n", "نبض")
    git(other, "push", "-q", "origin", "main")
    mine = _commit(bot, "reports.md", "گزارش\n", "گزارش")
    rc, log = S.push_with_retry(cwd=bot)
    assert rc == 0, log
    head = git(remote, "rev-parse", "main")
    parents = git(remote, "rev-list", "--parents", "-n", "1", head).split()[1:]
    # ادغام، نه بازنویسی: هر دو ثبت با همان شناسه، و ثبت ادغام دو والد دارد
    assert set(parents) == {mine, theirs}
    assert any("merge" in x for x in log)


def test_real_conflict_fails_loudly(repos, capsys) -> None:
    remote, bot, other = repos
    _commit(other, "base.txt", "نسخه دیگر\n", "دیگر")
    git(other, "push", "-q", "origin", "main")
    before = git(remote, "rev-parse", "main")
    _commit(bot, "base.txt", "نسخه ربات\n", "ربات")
    rc, log = S.push_with_retry(cwd=bot)
    assert rc != 0
    assert any("تداخل" in x and "base.txt" in x for x in log)
    assert git(remote, "rev-parse", "main") == before                 # چیزی رانده نشد
    assert git(bot, "status", "--porcelain") == ""                    # ادغام نیمه‌کاره نماند


def test_gives_up_after_three_retries() -> None:
    calls = []

    def run(args, **k):
        calls.append(args[1])
        rc = 1 if args[1] == "push" else 0
        out = "false" if args[1:3] == ["rev-parse", "--is-shallow-repository"] else "main"
        return subprocess.CompletedProcess(args, rc, out, "rejected")
    rc, log = S.push_with_retry(cwd=".", run=run)
    assert rc != 0 and calls.count("push") == 4                       # نخست + ۳ بار دوباره
    assert calls.count("merge") == 3 and "rebase" not in calls
    assert any("۳ بار" in x for x in log)


def test_cli_push_prints_error(repos, capsys) -> None:
    remote, bot, other = repos
    _commit(other, "base.txt", "x\n", "x")
    git(other, "push", "-q", "origin", "main")
    _commit(bot, "base.txt", "y\n", "y")
    import os
    old = os.getcwd()
    os.chdir(bot)
    try:
        assert S.main(["push"]) == 1
    finally:
        os.chdir(old)
    assert "::error::" in capsys.readouterr().out


# ── گردش‌کارها ──

def _text(name):
    return (FLOWS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("wf", ["radar-daily.yml", "radar-pulse.yml", "radar-weekly.yml"])
def test_workflows_push_with_retry_never_rebase_or_force(wf) -> None:
    t = _text(wf)
    assert "python radar_schedule.py push" in t
    code = "\n".join(x for x in t.splitlines() if not x.strip().startswith("#"))
    assert "rebase" not in code.lower()
    assert not re.search(r"git push[^\n]*(--force|-f\b)", t)
    assert not re.search(r"^\s*git push\s*$", t, re.M)                # push خام بی تلاش دوباره


def test_daily_five_slots_same_minute() -> None:
    crons = re.findall(r'-\s*cron:\s*"([^"]+)"', _text("radar-daily.yml"))
    hours = sorted(int(h) for c in crons for h in c.split()[1].split(","))
    assert hours == [0, 2, 4, 6, 8]
    assert {c.split()[0] for c in crons} == {"37"}
    assert all(c.split()[2:] == ["*", "*", "*"] for c in crons)
