"""用户自定义模型的纯构造与 URL 安全校验（不访问数据库）。

数据读取与实例缓存放在 ``app/db/user_llm.py``，避免 core 层反向依赖 db。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

from app.core.config import settings

# 云厂商元数据端点特征（打中这些 = 拿服务器凭据，必拒）
_METADATA_HOST_HINTS = (
    "metadata.google.internal",
    "metadata.aliyuncs.com",
    "metadata.internal",
    "100.100.100.200",  # 阿里云元数据
    "169.254.169.254",  # AWS/GCP/Azure 链路本地（同时被 _is_blocked_ip 拦）
)


class InvalidBaseURLError(ValueError):
    """用户提供的模型 base_url 不合法/不安全。"""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _check_host(host: str) -> None:
    host = (host or "").lower().rstrip(".")
    if not host:
        raise InvalidBaseURLError("缺少主机名")
    if any(hint in host for hint in _METADATA_HOST_HINTS):
        raise InvalidBaseURLError("该地址不可用")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
        raise InvalidBaseURLError("该地址不可用")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked_ip(ip):
            raise InvalidBaseURLError("该地址不可用")
        return
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise InvalidBaseURLError("域名解析失败，请检查地址") from exc
    if not infos:
        raise InvalidBaseURLError("域名无可用地址")
    for info in infos:
        addr = info[4][0]
        try:
            parsed_ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            continue
        if _is_blocked_ip(parsed_ip):
            raise InvalidBaseURLError("该地址不可用")


def validate_llm_base_url(url: str) -> str:
    """校验并规范化用户模型 base_url；不合法抛 InvalidBaseURLError。返回去掉尾斜杠的地址。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise InvalidBaseURLError("仅支持 http/https 地址")
    if parsed.username or parsed.password:
        raise InvalidBaseURLError("地址不能包含账号信息")
    if parsed.query or parsed.fragment:
        raise InvalidBaseURLError("地址不能包含查询参数或片段")
    try:
        parsed.port
    except ValueError as exc:
        raise InvalidBaseURLError("端口不合法") from exc
    _check_host(parsed.hostname or "")
    return raw.rstrip("/")


def build_user_model(cfg: dict) -> ChatOpenAI:
    """按用户配置构造 ChatOpenAI。

    不附加 enable_thinking：用户接入的 OpenAI 兼容服务不保证认识该参数，
    传了会被 400 拒绝；思考块由发送侧 guard / 落库侧 clean 兜底。
    max_retries=0：失败由上层 overlay 回退（_invoke 内 try/except）。
    """
    return ChatOpenAI(
        model=cfg["llm_model"],
        base_url=cfg["llm_base_url"],
        api_key=cfg["llm_api_key"],
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        max_retries=0,
    )
