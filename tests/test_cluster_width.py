"""
آزمون سقف پهنای خوشه در radar_levels.cluster_levels — نشست ۳، مورد ۷.

باگ: خوشه‌بندی زنجیره‌ای بود. هر نقطه به نقطه قبلی وصل می‌شد اگر فاصله‌اش
کمتر از روادار بود، بی‌سقف برای کل خوشه. نتیجه در داده واقعی ۲۵ سپتامبر:
بی‌ان‌بی «۵۸ برخورد» در ناحیه‌ای به پهنای ۳۹.۴٪ — یک ناحیه، نه یک سطح.

تصمیم کاربر: خوشه محدود. همه اعضا در بازه‌ای به پهنای روادار — یک ATR
روزانه — از کوچک‌ترین عضو.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_levels as L


def _width(lv) -> float:
    ps = [v for _, v in lv.members]
    return max(ps) - min(ps)


def test_chain_does_not_merge_beyond_tol() -> None:
    """ده نقطه با گام 0.8؛ روادار 1.0. زنجیره همه را یکی می‌کرد با پهنای 7.2."""
    pts = [(i, 100.0 + 0.8 * i) for i in range(10)]
    out = L.cluster_levels(pts, tol=1.0, n_bars=10)
    assert out, "خوشه‌ای ساخته نشد"
    assert all(_width(lv) <= 1.0 + 1e-9 for lv in out)
    assert max(lv.touches for lv in out) == 2


def test_tight_group_still_clusters() -> None:
    pts = [(0, 100.0), (5, 100.4), (9, 100.9), (12, 130.0)]
    out = L.cluster_levels(pts, tol=1.0, n_bars=13)
    assert len(out) == 1 and out[0].touches == 3


def test_window_anchored_at_smallest_member() -> None:
    """پنجره از کوچک‌ترین عضو شروع می‌شود: 100، 100.6، 101.0 یکی؛ 101.5 بیرون."""
    pts = [(0, 100.0), (1, 100.6), (2, 101.0), (3, 101.5), (4, 102.2)]
    out = L.cluster_levels(pts, tol=1.0, n_bars=5)
    first = min(out, key=lambda lv: lv.price)
    assert sorted(v for _, v in first.members) == [100.0, 100.6, 101.0]
    second = [lv for lv in out if lv is not first]
    assert len(second) == 1 and sorted(v for _, v in second[0].members) == [101.5, 102.2]


def test_single_points_are_not_levels() -> None:
    """یک نقطه خط نیست — حداقل دو برخورد، بدون تغییر."""
    pts = [(0, 100.0), (1, 110.0), (2, 120.0)]
    assert L.cluster_levels(pts, tol=1.0, n_bars=3) == []
