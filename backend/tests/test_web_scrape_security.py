"""网页抓取 SSRF 防护测试（不发起网络请求）。"""
from __future__ import annotations

import pytest

from app.tools import web_search
from app.tools.web_search import BlockedURL, _check_url, _is_public_ip

pytestmark = pytest.mark.security


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.100.100.200",
        "0.0.0.0",
        "::1",
        "fd00:ec2::254",
    ],
)
def test_private_loopback_linklocal_and_metadata_ips_are_blocked(ip: str) -> None:
    assert _is_public_ip(ip) is False


@pytest.mark.parametrize(
    "ip",
    ["93.184.216.34", "1.1.1.1", "2606:2800:220:1:248:1893:25c8:1946"],
)
def test_public_ips_are_allowed(ip: str) -> None:
    assert _is_public_ip(ip) is True


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://127.0.0.1:8123/api/health",
        "http://localhost/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://metadata.tencentyun.com/",
        "http://user:pass@93.184.216.34/",
        "http://93.184.216.34:8080/",
    ],
)
def test_check_url_blocks_ssrf_targets(url: str) -> None:
    with pytest.raises(BlockedURL):
        _check_url(url)


def test_check_url_allows_public_ip() -> None:
    _check_url("http://93.184.216.34/")


def test_allowlist_rejects_other_hosts(monkeypatch) -> None:
    monkeypatch.setattr(web_search.settings, "web_scrape_allowed_hosts", "93.184.216.34")
    _check_url("http://93.184.216.34/")
    with pytest.raises(BlockedURL):
        _check_url("http://1.1.1.1/")


def test_scrape_tool_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(web_search.settings, "web_scrape_enabled", False)
    out = web_search.scrape_web_page.func("http://127.0.0.1:8123/api/health")
    assert "未启用" in out
