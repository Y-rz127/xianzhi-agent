"""`scripts/ensure_cext_fallback.py` 的停用/还原语义。

为什么守：Windows 智能应用控制 / AppLocker 会拦 venv 里未建立信誉的 `.pyd`。一旦拦到
sqlalchemy 的 `_util_cy.pyd`，`import sqlalchemy` 直接 ImportError，PG 记忆层与 pgvector
检索一起挂，而服务照样"启动成功"——只在真正存对话、真正检索时才炸。修复是把 `.pyd`
改名 `.pyd.blocked`，让 import 落到同名纯 Python `.py`。

两条最容易改错的语义：
1) **必须整包停用**。只停被拦的那几个会留下「C 版 + 纯 Python 版混用」，实测报
   `anon_map size changed, may indicate binary incompatibility`（Cython cdef class 布局不同）。
2) **幂等**。pip 重装会把 `.pyd` 装回来，重复跑不能报错，也不能把已 `.blocked` 的又改回去。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "ensure_cext_fallback", _BACKEND / "scripts" / "ensure_cext_fallback.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


CEXT = _load_script()

_BLOCKED_ERR = (
    "ImportError: DLL load failed while importing _util_cy: 应用程序控制策略已阻止此文件。"
)


def _fake_site(tmp_path: Path, files: list[str]) -> Path:
    for rel in files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00")
    return tmp_path


def test_disable_moves_every_pyd_in_package(tmp_path, monkeypatch):
    """整包停用：包内所有 .pyd 都要变成 .pyd.blocked，不能只停被拦的那一个。"""
    _fake_site(
        tmp_path,
        [
            "sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd",
            "sqlalchemy/engine/_util_cy.cp312-win_amd64.pyd",
            "sqlalchemy/util/_collections_cy.cp312-win_amd64.pyd",
        ],
    )
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)

    moved = CEXT._disable_pyd("sqlalchemy")

    assert len(moved) == 3
    assert not list((tmp_path / "sqlalchemy").rglob("*.pyd"))
    assert len(list((tmp_path / "sqlalchemy").rglob("*.pyd.blocked"))) == 3


def test_disable_is_idempotent_after_pip_reinstall(tmp_path, monkeypatch):
    """pip 重装把 .pyd 装回来后再跑一次：新装的那份被丢弃，.blocked 不会翻倍。"""
    _fake_site(tmp_path, ["sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd"])
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)
    CEXT._disable_pyd("sqlalchemy")

    # 模拟 pip 重装：同名 .pyd 又出现了
    reinstalled = tmp_path / "sqlalchemy" / "sql" / "_util_cy.cp312-win_amd64.pyd"
    reinstalled.write_bytes(b"\x00")
    CEXT._disable_pyd("sqlalchemy")

    assert not reinstalled.exists()
    assert len(list((tmp_path / "sqlalchemy").rglob("*.pyd.blocked"))) == 1


def test_restore_round_trip(tmp_path, monkeypatch):
    """策略放行后 --restore 能把 .blocked 全部改回 .pyd。"""
    _fake_site(
        tmp_path,
        [
            "sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd",
            "sqlalchemy/engine/_util_cy.cp312-win_amd64.pyd",
        ],
    )
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)
    CEXT._disable_pyd("sqlalchemy")

    CEXT._restore_pyd("sqlalchemy")

    assert len(list((tmp_path / "sqlalchemy").rglob("*.pyd"))) == 2
    assert not list((tmp_path / "sqlalchemy").rglob("*.pyd.blocked"))


def test_main_skips_probe_when_already_pure_python(tmp_path, monkeypatch):
    """已经是纯 Python 模式（无 .pyd）时走快速路径，不花子进程探测成本。"""
    (tmp_path / "sqlalchemy").mkdir()
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)
    monkeypatch.setattr(CEXT, "_probe", _fail_probe)

    assert CEXT.main() == 0


def _fail_probe(module: str) -> tuple[bool, str]:
    """快速路径下不该再探测；真被调用了就让测试挂掉。"""
    raise AssertionError(f"快速路径不该探测 {module}")


def test_main_repairs_blocked_extension(tmp_path, monkeypatch):
    """探测命中「策略拦截」→ 整包停用 → 复验通过 → 返回 2（调用方需用新进程启动）。"""
    _fake_site(tmp_path, ["sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd"])
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)

    def fake_probe(module: str) -> tuple[bool, str]:
        if module.startswith("sqlalchemy"):
            still_pyd = any((tmp_path / "sqlalchemy").rglob("*.pyd"))
            return (False, _BLOCKED_ERR) if still_pyd else (True, "")
        return True, ""

    monkeypatch.setattr(CEXT, "_probe", fake_probe)

    assert CEXT.main() == 2
    assert not list((tmp_path / "sqlalchemy").rglob("*.pyd"))


def test_main_fails_for_package_without_pure_python_fallback(tmp_path, monkeypatch):
    """psycopg 这类没有纯 Python 回落的包被拦，只能返 1 让人工放行，脚本不许硬改。"""
    _fake_site(tmp_path, ["sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd"])
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)

    def fake_probe(module: str) -> tuple[bool, str]:
        if module.startswith("sqlalchemy"):
            still_pyd = any((tmp_path / "sqlalchemy").rglob("*.pyd"))
            return (False, _BLOCKED_ERR) if still_pyd else (True, "")
        if module == "psycopg":
            return False, _BLOCKED_ERR
        return True, ""

    monkeypatch.setattr(CEXT, "_probe", fake_probe)

    assert CEXT.main() == 1


def test_main_ignores_errors_that_are_not_policy_blocks(tmp_path, monkeypatch):
    """缺包/版本不匹配的报错不归这个脚本管：不返 1、不动文件。"""
    _fake_site(tmp_path, ["sqlalchemy/sql/_util_cy.cp312-win_amd64.pyd"])
    monkeypatch.setattr(CEXT, "_SITE_PACKAGES", tmp_path)

    def fake_probe(module: str) -> tuple[bool, str]:
        if module.startswith("sqlalchemy"):
            return False, "ModuleNotFoundError: No module named 'sqlalchemy'"
        return True, ""

    monkeypatch.setattr(CEXT, "_probe", fake_probe)

    assert CEXT.main() == 0
    assert len(list((tmp_path / "sqlalchemy").rglob("*.pyd"))) == 1
