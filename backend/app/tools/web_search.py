"""联网搜索工具（Serper）与受限网页抓取。

网页抓取默认关闭；开启后只允许公网 http/https，逐跳校验重定向，
阻止 loopback/私网/link-local/metadata 等 SSRF 目标。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from langchain_core.tools import tool

from app.core.config import settings

_MAX_REDIRECTS = 3
_MAX_BYTES = 1_000_000
_BLOCKED_HOSTS = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "metadata.tencentyun.com",
    "metadata.tencentcloudapi.com",
}
_BLOCKED_HOST_SUFFIXES = (".localhost", ".internal", ".local")
_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure/Tencent 常见 metadata
    ipaddress.ip_address("100.100.100.200"),  # 阿里云 metadata
    ipaddress.ip_address("fd00:ec2::254"),    # AWS IPv6 metadata
}


class BlockedURL(ValueError):
    """URL 被安全策略拒绝。"""


def _is_public_ip(raw: str) -> bool:
    try:
        addr = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr in _METADATA_IPS:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve_public(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise BlockedURL("域名解析失败") from e
    if not infos:
        raise BlockedURL("域名无可用地址")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise BlockedURL("目标地址不在公网范围")


def _check_url(url: str) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise BlockedURL("仅支持 http/https")
    if not parsed.hostname:
        raise BlockedURL("缺少主机名")
    if parsed.username or parsed.password:
        raise BlockedURL("不允许 URL 携带用户信息")
    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or any(host.endswith(s) for s in _BLOCKED_HOST_SUFFIXES):
        raise BlockedURL("目标主机被禁用")
    allowed = [h.strip().lower() for h in settings.web_scrape_allowed_hosts.split(",") if h.strip()]
    if allowed and not any(host == a or host.endswith("." + a) for a in allowed):
        raise BlockedURL("目标主机不在白名单")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as e:
        raise BlockedURL("端口不合法") from e
    if port not in (80, 443):
        raise BlockedURL("仅支持 80/443 端口")
    _resolve_public(host, port)


def _fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; XianzhiBot/1.0)"}
    with httpx.Client(timeout=15, follow_redirects=False, headers=headers) as client:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            _check_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location", "")
                    if not location:
                        raise BlockedURL("重定向缺少 Location")
                    current = urljoin(str(resp.url), location)
                    continue
                resp.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    remaining = _MAX_BYTES - total
                    if remaining <= 0:
                        break
                    chunks.append(chunk[:remaining])
                    total += len(chunks[-1])
                encoding = resp.encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace")
        raise BlockedURL("重定向次数过多")


@tool
def search_web(query: str) -> str:
    """使用 Serper.dev Google Search API 查询最新资讯。query 应为简单关键词。"""
    if not settings.search_api_key:
        return "未配置 SEARCH_API_KEY，无法联网搜索。查询: {}".format(query)
    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": 5},
            headers={"X-API-KEY": settings.search_api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", [])[:5]:
            title = item.get("title", "").strip()
            link = item.get("link", "").strip()
            snippet = item.get("snippet", "").strip()
            if title or snippet:
                results.append("{}\n{}\n{}".format(title, snippet, link).strip())
        if not results:
            return "未搜索到相关结果: {}".format(query)
        return "搜索结果：\n\n" + "\n\n".join(results)
    except Exception as e:
        return "联网搜索失败: {}".format(e)


@tool
def scrape_web_page(url: str) -> str:
    """抓取指定公网网页的文本内容（默认关闭，需启用并通过安全校验）。"""
    if not settings.web_scrape_enabled:
        return "网页抓取未启用（安全策略）"
    try:
        html = _fetch_html(url)
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:3000]
    except BlockedURL as e:
        return "网页抓取被拒绝: {}".format(e)
    except Exception as e:
        return "网页抓取失败: {}".format(e)


search_tools = [search_web]
if settings.web_scrape_enabled:
    search_tools.append(scrape_web_page)
