"""`backend/start.ps1` 的编码与启动方式守卫（PowerShell 5.1 专属约束）。

背景（2026-10-25）：改这个脚本时往 `Write-Host` 里加了中文字符串，编辑器写回的是
**无 BOM 的 UTF-8**，而 PowerShell 5.1 对无 BOM 脚本按系统 ANSI(936/GBK) 解码 ——
中文变成 `鍘熺敓鎵╁睍`，全角括号的尾字节把字符串引号一起吃掉，整个脚本 ParserError，
`./start.ps1` 直接跑不起来。原来的中文只在注释里，GBK 解错后仍是注释，所以一直没炸。

三条断言守的都是「平时看不见、一碰就炸」的约束：

1. 必须有 UTF-8 BOM（否则 PS 5.1 走 GBK）；
2. 非注释行全 ASCII（BOM 万一丢了，字符串字面量也不会把引号吃掉）；
3. `Start-Process` 不许带 `-RedirectStandard*`：本机同时有 `http_proxy` 与 `HTTP_PROXY`
   （仅大小写不同），带重定向时 Start-Process 会把环境变量塞进忽略大小写的字典，
   抛 `ArgumentException: 已添加项。字典中的关键字:"http_proxy"...`，表现是脚本静默退出。
"""

from __future__ import annotations

import re
from pathlib import Path

START_PS1 = Path(__file__).resolve().parents[1] / "start.ps1"


def _lines() -> list[str]:
    return START_PS1.read_text(encoding="utf-8-sig").splitlines()


def _code_lines() -> list[str]:
    """非空、非注释的代码行（注释里的中文 GBK 误解码也无害，不参与断言）。"""
    return [ln for ln in _lines() if ln.strip() and not ln.strip().startswith("#")]


def test_start_ps1_is_utf8_with_bom():
    """PowerShell 5.1 靠 BOM 才能认出 UTF-8；没有 BOM 就按 GBK 解码。"""
    assert START_PS1.read_bytes()[:3] == b"\xef\xbb\xbf", (
        "start.ps1 丢了 UTF-8 BOM：PS 5.1 会按 GBK 解码，中文字符串会吃掉引号导致 ParserError"
    )


def test_start_ps1_code_lines_are_ascii_only():
    """代码行里不许出现非 ASCII —— 中文只允许留在注释里。"""
    offenders = [ln for ln in _code_lines() if not ln.isascii()]
    assert not offenders, (
        "start.ps1 的代码行含非 ASCII 字符（中文请只写在注释里，字符串用英文）：\n"
        + "\n".join(offenders)
    )


def test_start_ps1_does_not_redirect_start_process_output():
    """-Background 分支不许用 -RedirectStandard*，（http_proxy/HTTP_PROXY 会把它打挂）。"""
    offenders = [ln for ln in _code_lines() if re.search(r"-RedirectStandard(Output|Error)\b", ln)]
    assert not offenders, (
        "start.ps1 又给 Start-Process 加了 -RedirectStandard*：本机 http_proxy 与 HTTP_PROXY "
        "仅大小写不同，会抛 ArgumentException「已添加项」。日志看 backend/logs/xianzhi_*.log：\n"
        + "\n".join(offenders)
    )
