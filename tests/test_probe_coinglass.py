"""
سنجش دسترسی CoinGlass — بند ۱ متن ۲۲، ۲۷ اکتبر ۲۰۲۶. فقط مسیر دستی، بی چاپ کلید.

کلید از COINGLASS_API_KEY، فقط با سرآیند CG-API-KEY و فقط به میزبان‌های CoinGlass، در هر
درخواست جدا. برای هر نقطه پایانی فقط کد HTTP، کد و پیام خود CoinGlass تا ۱۲۰ نویسه با
پوشاندن هر رشته شبیه کلید، داده آمد یا نه، شمار ردیف و تاریخ آخرین ردیف. سرور MCP رسمی:
initialize، شناسه جلسه، tools/list — فقط پذیرفته شد یا نه و شمار ابزار.

آزمون‌ها بی‌شبکه، با پاسخ ساختگی. مخزن عمومی است: کلید ساختگی در هیچ خروجی نیست.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import radar_probe as PR

UTC = timezone.utc
NOW = datetime(2026, 10, 27, 14, 0, tzinfo=UTC)
KEY = "0123456789abcdef0123456789abcdef"            # ساختگی، شکل کلید CoinGlass
CG_HOSTS = {"open-api-v4.coinglass.com", "api-mcp.coinglass.com"}
MS = 1761523200000                                  # 2025-10-27 00:00 UTC


class _R:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}


def _ok(rows):
    return _R(200, {"code": "0", "msg": "success", "data": rows})


def fake_server(calls, echo_key=False, mcp=True):
    """پاسخ ساختگی هر نقطه؛ echo_key یعنی سرور کلید را در پیام و داده برگرداند."""
    def request(method, url, headers=None, params=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": dict(headers or {}),
                      "params": dict(params or {}), "json": json})
        host = urlparse(url).hostname
        if host == "ipinfo.io":
            return _R(200, b"US\n")
        if host == "api-mcp.coinglass.com":
            if not mcp:
                return _R(401, {"jsonrpc": "2.0", "id": 1,
                                "error": {"code": -32001, "message": "bad key " + KEY}})
            m = (json or {}).get("method")
            if m == "initialize":
                body = ("event: message\ndata: " + __import__("json").dumps(
                    {"jsonrpc": "2.0", "id": 1, "result": {
                        "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                        "serverInfo": {"name": "cg", "version": "1"}}}) + "\n\n").encode()
                return _R(200, body, {"Content-Type": "text/event-stream",
                                      "Mcp-Session-Id": "sess-ABCDEF0123456789XYZ"})
            if m == "notifications/initialized":
                return _R(202, b"")
            if m == "tools/list":
                return _R(200, {"jsonrpc": "2.0", "id": 2, "result": {
                    "tools": [{"name": f"t{i}"} for i in range(7)]}},
                    {"Content-Type": "application/json"})
            return _R(400, b"")
        path = urlparse(url).path
        if echo_key:
            return _R(200, {"code": "401", "msg": f"Invalid API key: {KEY} please check",
                            "data": [{"time": MS, "secret": KEY}]}, {"X-Echo": KEY})
        if path.endswith("/aggregated-heatmap/model1"):
            return _R(200, {"code": "400", "msg": "Upgrade plan", "data": None})
        if "/etf/" in path:
            return _ok([{"timestamp": MS - 86400000, "flow_usd": 1.0},
                        {"timestamp": MS, "flow_usd": 2.0}])
        if path == "/api/coinbase-premium-index":
            return _ok([{"time": MS // 1000 - 86400, "premium": 1},
                        {"time": MS // 1000, "premium": 2}])
        if path.endswith("/coin-list") or path.endswith("/exchange-list"):
            return _ok([{"symbol": "BTC"}, {"symbol": "ETH"}, {"symbol": "SOL"}])
        return _ok([{"time": MS - 2 * 86400000}, {"time": MS - 86400000}, {"time": MS}])
    return request


def _run(tmp_path, calls, env=None, **kw):
    out = tmp_path / "cg.md"
    env = {"COINGLASS_API_KEY": KEY, "GITHUB_ACTIONS": "true"} if env is None else env
    rc = PR.main(["--coinglass", "--out", str(out)], env=env, now=NOW, pause=0,
                 request=fake_server(calls, **kw))
    return rc, out.read_text(encoding="utf-8")


# ── فهرست نقطه‌ها: مسیر دقیق مستندات v4 ──

def test_endpoint_list_matches_docs() -> None:
    eps = {e.key: e for e in PR.CG_ENDPOINTS}
    want = {
        "cg-liq-history-btc": "/api/futures/liquidation/aggregated-history",
        "cg-liq-history-eth": "/api/futures/liquidation/aggregated-history",
        "cg-liq-coin-list": "/api/futures/liquidation/coin-list",
        "cg-liq-exchange-list": "/api/futures/liquidation/exchange-list",
        "cg-etf-btc": "/api/etf/bitcoin/flow-history",
        "cg-etf-eth": "/api/etf/ethereum/flow-history",
        "cg-oi-history-btc": "/api/futures/open-interest/aggregated-history",
        "cg-funding-oiw-btc": "/api/futures/funding-rate/oi-weight-history",
        "cg-ls-global-btc": "/api/futures/global-long-short-account-ratio/history",
        "cg-coinbase-premium": "/api/coinbase-premium-index",
        "cg-liq-heatmap-btc": "/api/futures/liquidation/aggregated-heatmap/model1",
    }
    assert {k: e.path for k, e in eps.items()} == want
    assert eps["cg-liq-history-eth"].params["symbol"] == "ETH"
    assert eps["cg-ls-global-btc"].params == {"exchange": "Binance", "symbol": "BTCUSDT",
                                             "interval": "1d", "limit": "30"}
    assert eps["cg-liq-exchange-list"].params["range"] == "24h"
    # طرح پایه: بازه دست‌کم ۴ ساعت — همه بازه‌ها روزانه
    assert all(e.params.get("interval") in (None, "1d") for e in PR.CG_ENDPOINTS)
    assert PR.CG_BASE == "https://open-api-v4.coinglass.com"
    assert PR.CG_MCP == "https://api-mcp.coinglass.com/mcp"


# ── سرآیند کلید فقط به میزبان CoinGlass، هر درخواست جدا ──

def test_key_header_only_to_coinglass_hosts(tmp_path) -> None:
    calls = []
    rc, _ = _run(tmp_path, calls)
    assert rc == 0
    hosts = {urlparse(c["url"]).hostname for c in calls}
    assert "ipinfo.io" in hosts and CG_HOSTS <= hosts
    for c in calls:
        host = urlparse(c["url"]).hostname
        if host in CG_HOSTS:
            assert c["headers"].get("CG-API-KEY") == KEY
        else:
            assert "CG-API-KEY" not in c["headers"] and KEY not in json.dumps(c)
        assert KEY not in c["url"] and KEY not in json.dumps(c["params"])


def test_header_helper_refuses_other_hosts() -> None:
    assert PR.cg_headers("https://open-api-v4.coinglass.com/api/x", KEY)["CG-API-KEY"] == KEY
    assert PR.cg_headers("https://api-mcp.coinglass.com/mcp", KEY)["CG-API-KEY"] == KEY
    for url in ("https://fred.stlouisfed.org/x", "https://www.okx.com/api",
                "https://open-api-v4.coinglass.com.evil.test/x", "https://coinglass.com/x"):
        assert "CG-API-KEY" not in PR.cg_headers(url, KEY)


def test_general_probe_never_sends_key(tmp_path) -> None:
    seen = []

    def get(url, headers=None, **k):
        seen.append(dict(headers or {}))
        return _R(200, b"x")
    PR.main(["--out", str(tmp_path / "p.md"), "--only", "coinglass-api,ff-json"], get=get,
            env={"COINGLASS_API_KEY": KEY}, now=NOW, pause=0)
    assert seen and all("CG-API-KEY" not in h and KEY not in json.dumps(h) for h in seen)


# ── کلید در هیچ خروجی ──

def test_key_never_in_any_output_even_if_echoed(tmp_path, capsys) -> None:
    calls = []
    rc, rep = _run(tmp_path, calls, echo_key=True, mcp=False)
    out = capsys.readouterr()
    assert rc == 0
    for text in (rep, out.out, out.err):
        assert KEY not in text and KEY[:16] not in text
    assert "Invalid API key" in rep                      # پیام می‌ماند، کلید نه


def test_key_in_exception_is_masked() -> None:
    def boom(method, url, **k):
        raise ConnectionError(f"failed with header {KEY}")
    row = PR.cg_endpoint(PR.CG_ENDPOINTS[0], KEY, boom, pause=0)
    assert KEY not in json.dumps(row, ensure_ascii=False) and "ConnectionError" in row["why"]


def test_mask_keylike_and_cut() -> None:
    s = PR.cg_mask("bad token AbCdEf0123456789ZYXWvu here | " + "x" * 300, None)
    assert "AbCdEf0123456789ZYXWvu" not in s and "|" not in s and len(s) <= 120
    assert PR.cg_mask(f"k={KEY}", KEY).count("‹") == 1


# ── فقط همین میدان‌ها از بدنه ──

def test_row_keeps_only_allowed_fields(tmp_path) -> None:
    calls = []
    eps = {e.key: e for e in PR.CG_ENDPOINTS}
    req = fake_server(calls)
    row = PR.cg_endpoint(eps["cg-oi-history-btc"], KEY, req, pause=0)
    assert set(row) == PR.CG_ROW_FIELDS
    assert row["status"] == 200 and row["cg_code"] == "0" and row["cg_msg"] == "success"
    assert row["has_data"] is True and row["rows"] == 3 and row["last"] == "2025-10-27"
    prem = PR.cg_endpoint(eps["cg-coinbase-premium"], KEY, req, pause=0)
    assert prem["last"] == "2025-10-27"                 # ثانیه، نه میلی‌ثانیه
    etf = PR.cg_endpoint(eps["cg-etf-btc"], KEY, req, pause=0)
    assert etf["rows"] == 2 and etf["last"] == "2025-10-27"
    lst = PR.cg_endpoint(eps["cg-liq-coin-list"], KEY, req, pause=0)
    assert lst["rows"] == 3 and lst["last"] is None
    hm = PR.cg_endpoint(eps["cg-liq-heatmap-btc"], KEY, req, pause=0)
    assert hm["cg_code"] == "400" and hm["has_data"] is False and hm["rows"] is None


def test_heatmap_dict_rows_from_candles() -> None:
    def req(method, url, **k):
        return _R(200, {"code": "0", "msg": "success", "data": {
            "y_axis": [1, 2], "liquidation_leverage_data": [[0, 0, 5]],
            "price_candlesticks": [[MS // 1000 - 3600, "1", "1", "1", "1", "9"],
                                   [MS // 1000, "1", "1", "1", "1", "9"]]}})
    eps = {e.key: e for e in PR.CG_ENDPOINTS}
    row = PR.cg_endpoint(eps["cg-liq-heatmap-btc"], KEY, req, pause=0)
    assert row["has_data"] and row["rows"] == 2 and row["last"] == "2025-10-27"


# ── بی کلید ──

def test_no_key_reports_and_does_not_fail(tmp_path) -> None:
    calls = []
    rc, rep = _run(tmp_path, calls, env={"GITHUB_ACTIONS": "true"})
    assert rc == 0 and "کلید تنظیم نشده" in rep and calls == []


# ── سرور MCP ──

def test_mcp_initialize_session_and_tools(tmp_path) -> None:
    calls = []
    rc, rep = _run(tmp_path, calls)
    mcp = [c for c in calls if urlparse(c["url"]).hostname == "api-mcp.coinglass.com"]
    assert [c["json"]["method"] for c in mcp] == ["initialize", "notifications/initialized",
                                                    "tools/list"]
    assert "Mcp-Session-Id" not in mcp[0]["headers"]
    assert mcp[2]["headers"]["Mcp-Session-Id"] == "sess-ABCDEF0123456789XYZ"
    assert mcp[2]["headers"]["MCP-Protocol-Version"] == "2025-06-18"
    assert "text/event-stream" in mcp[0]["headers"]["Accept"]
    assert "sess-ABCDEF0123456789XYZ" not in rep          # شناسه جلسه ثبت نمی‌شود
    line = [l for l in rep.splitlines() if "tools/list" in l][0]
    assert "✅" in line and "| 7 |" in line


def test_mcp_rejected_stops_and_masks(tmp_path) -> None:
    calls = []
    rc, rep = _run(tmp_path, calls, mcp=False)
    mcp = [c for c in calls if urlparse(c["url"]).hostname == "api-mcp.coinglass.com"]
    assert len(mcp) == 1 and rc == 0
    line = [l for l in rep.splitlines() if "initialize" in l][0]
    assert "❌" in line and "401" in line and KEY not in rep


# ── مکث ──

def test_pause_between_requests(tmp_path, monkeypatch) -> None:
    slept = []
    monkeypatch.setattr(PR.time, "sleep", lambda s: slept.append(s))
    calls = []
    PR.main(["--coinglass", "--out", str(tmp_path / "c.md")], env={"COINGLASS_API_KEY": KEY},
            now=NOW, request=fake_server(calls))
    cg = [c for c in calls if urlparse(c["url"]).hostname in CG_HOSTS]
    assert len(slept) >= len(cg) - 1 and min(slept) >= PR.CG_PAUSE >= 2.0


def test_report_lists_paths_and_plan_note(tmp_path) -> None:
    calls = []
    _, rep = _run(tmp_path, calls)
    assert rep.startswith("# سنجش دسترسی CoinGlass — 2026-10-27")
    assert "/api/etf/bitcoin/flow-history" in rep and "symbol=BTC" in rep
    assert "کلید تنظیم‌شده" in rep and "گیت‌هاب" in rep
