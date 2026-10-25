"""系统策略拦住 venv 原生扩展时的自愈：把 SQLAlchemy 的 .pyd 停用，改走纯 Python 实现。

症状：日志写 `DLL load failed while importing _util_cy: 应用程序控制策略已阻止此文件`。
这是 Windows 智能应用控制 / AppLocker 拦了未建立信誉的原生二进制，**不是缺包**，
重装依赖、换镜像都没用。后果是 `import sqlalchemy` 直接失败，连带 PG 记忆层、
pgvector 检索、LangGraph checkpointer 全挂，而服务照样"启动成功"，只在真正存对话时报错。

做法：SQLAlchemy 2.1 的 wheel 同时带 `.pyd` 和同名纯 Python `.py`，import 优先取 `.pyd`。
把被拦的 `.pyd` 改名成 `.pyd.blocked`，import 就落到 `.py`，语义完全等价
（`_is_compiled()` 返回 False，只有性能差别）。**必须整包一起停用**：C 版与纯 Python 版的
cdef class 布局不同，混用会报 `anon_map size changed, may indicate binary incompatibility`。

其余原生包（psycopg / greenlet / pydantic_core）没有纯 Python 回落，被拦了只能人工放行，
脚本只报诊断、不硬改。

用法：
    .venv/Scripts/python.exe scripts/ensure_cext_fallback.py   # start.ps1 启动前自动调用

退出码：0 无需处理；2 已修复（可继续启动，新进程即生效）；1 无力修复，stderr 有诊断。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SITE_PACKAGES = _BACKEND_ROOT.parent / ".venv" / "Lib" / "site-packages"

# 探测项：import 名 -> 该包整体停用 .pyd 后能否继续工作
_PROBES: dict[str, bool] = {
    "sqlalchemy": True,
    "psycopg": False,
    "greenlet": False,
    "pydantic_core._pydantic_core": False,
}

# 命中即判定为「系统策略拦截」，与「缺包 / 版本不匹配」区分开
_BLOCK_MARKERS = (
    "应用程序控制策略已阻止",
    "被组策略阻止",
    "DLL load failed",
    "blocked by policy",
)

# 有纯 Python 回落的包：停用时必须整包处理，不能只停被拦的那几个
_FALLBACK_PACKAGES = ("sqlalchemy",)


def _safe(text: str) -> str:
    """把非 ASCII 降级成转义序列后再输出。

    Windows 控制台代码页不一定是 UTF-8：错误详情里一旦带中文（系统消息「应用程序控制
    策略已阻止此文件」就是），整行会变乱码，连 `[cext] FAIL` 这种状态词都看不清。
    状态词本身已全 ASCII，这里只降级详情部分。
    """
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def _probe(module: str) -> tuple[bool, str]:
    """在独立子进程里 import，返回 (是否成功, 错误摘要)。子进程隔离避免污染当前解释器。"""
    proc = subprocess.run(
        [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if proc.returncode == 0:
        return True, ""
    lines = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, lines[-1].strip() if lines else f"exit {proc.returncode}"


def _has_pyd(pkg: str) -> bool:
    pkg_dir = _SITE_PACKAGES / pkg
    return pkg_dir.is_dir() and any(pkg_dir.rglob("*.pyd"))


def _disable_pyd(pkg: str) -> list[str]:
    """把包内全部 .pyd 改名成 .pyd.blocked，返回已停用文件的相对路径。"""
    pkg_dir = _SITE_PACKAGES / pkg
    disabled: list[str] = []
    for src in sorted(pkg_dir.rglob("*.pyd")):
        dst = src.with_suffix(src.suffix + ".blocked")
        if dst.exists():
            src.unlink()  # 上次已停用过同名文件，直接丢弃新装回来的这份
        else:
            src.rename(dst)
        disabled.append(str(src.relative_to(_SITE_PACKAGES)))
    return disabled


def _restore_pyd(pkg: str) -> list[str]:
    """把 .pyd.blocked 改回 .pyd（策略放行后恢复 C 扩展用）。"""
    pkg_dir = _SITE_PACKAGES / pkg
    restored: list[str] = []
    for src in sorted(pkg_dir.rglob("*.pyd.blocked")):
        dst = Path(str(src)[: -len(".blocked")])
        if dst.exists():
            src.unlink()
        else:
            src.rename(dst)
        restored.append(str(dst.relative_to(_SITE_PACKAGES)))
    return restored


def main() -> int:
    if "--restore" in sys.argv:
        for pkg in _FALLBACK_PACKAGES:
            restored = _restore_pyd(pkg)
            print(f"[cext] restored {len(restored)} .pyd in {pkg}")
        return 0

    if not _SITE_PACKAGES.is_dir():
        print(f"[cext] SKIP  venv site-packages not found: {_SITE_PACKAGES}")
        return 0

    # 快速路径：SQLAlchemy 已经没有 .pyd，纯 Python 模式早已生效（pip 重装后才会再出现）
    if not _has_pyd("sqlalchemy"):
        print("[cext] OK    sqlalchemy already runs pure-Python (no .pyd)")
        return 0

    needs_restart = False
    fatal: list[str] = []

    for module, has_fallback in _PROBES.items():
        top = module.split(".")[0]
        if has_fallback and not _has_pyd(top):
            continue
        ok, err = _probe(module)
        if ok:
            print(f"[cext] OK    {module}")
            continue

        if not any(marker in err for marker in _BLOCK_MARKERS):
            print(f"[cext] WARN  {module} import failed but NOT a policy block, skipped: {_safe(err)}")
            continue

        if not (has_fallback and top in _FALLBACK_PACKAGES):
            fatal.append(f"{module}: {err}")
            print(f"[cext] FAIL  {module} blocked by policy and has no pure-Python fallback: {_safe(err)}")
            continue

        disabled = _disable_pyd(top)
        ok2, err2 = _probe(module)
        if ok2:
            needs_restart = True
            print(f"[cext] FIX   {module} blocked by policy -> disabled {len(disabled)} .pyd, pure-Python fallback verified")
            for name in disabled:
                print(f"             .blocked  {name}")
        else:
            fatal.append(f"{module}: after disabling .pyd still failed: {err2}")
            print(f"[cext] FAIL  {module} still failing after disabling .pyd: {_safe(err2)}")

    if fatal:
        print("\n[cext] Cannot auto-fix; needs manual allow-listing (WDAC/AppLocker):", file=sys.stderr)
        for item in fatal:
            print(f"  - {_safe(item)}", file=sys.stderr)
        print("  allow this dir: " + str(_SITE_PACKAGES), file=sys.stderr)
        print("  or run on a machine/container without Smart App Control.", file=sys.stderr)
        return 1

    if needs_restart:
        print("[cext] FIXED - next process will use pure-Python SQLAlchemy (same semantics, slightly slower)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
