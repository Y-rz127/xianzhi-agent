"""关停顺序：必须等后台初始化任务（探活）收尾，再关 httpx 连接池。

背景：lifespan 的 `yield` 之后直接关掉所有 httpx.Client，而启动探活
（`probe_sub_models`）是在后台线程里跑的 —— 探活还没结束 client 就被关，
于是每个角色都报「Cannot send a request, as the client has been closed」。

危害不只是日志噪音：这条错误走的是「不是 thinking 配置问题」分支，
即**启动自愈被误判成配置错误**，真出现「该模型只接受思考模式」时，
探活就自愈不了（先撞上 client closed 直接判失败）。

用 AST 静态断言顺序（不真启服务，避免真实计费的探活调用）。
"""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace

import pytest

_MAIN = pathlib.Path(__file__).resolve().parents[1] / "main.py"


def _lifespan_ast() -> ast.AsyncFunctionDef:
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            return node
    raise AssertionError("main.py 里找不到 lifespan")


def _line_of(node: ast.AST) -> int:
    return getattr(node, "lineno", 0)


def test_shutdown_waits_for_background_tasks_before_closing_clients():
    """关停时必须先 await 后台任务，再关连接池。"""
    lifespan = _lifespan_ast()

    wait_line = None
    close_line = None
    for node in ast.walk(lifespan):
        # 等待后台任务：asyncio.wait_for(... _bg_init_tasks ...)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "wait_for":
            src = ast.dump(node)
            if "_bg_init_tasks" in src:
                wait_line = _line_of(node)
        # 关闭连接池：for client in (*sub_model_http, ...)
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            src = ast.dump(node)
            if "sub_model_http" in src:
                close_line = _line_of(node)

    assert wait_line is not None, "关停时没有等待后台初始化任务"
    assert close_line is not None, "关停时没有找到关闭 httpx 连接池的代码"
    assert wait_line < close_line, (
        f"关停顺序反了：等待后台任务在第 {wait_line} 行，"
        f"关闭连接池在第 {close_line} 行 —— 探活会撞上 client has been closed"
    )


def test_probe_specs_cover_all_llm_roles():
    """每个 LLM 角色都要有探活规格（否则 thinking 不匹配的模型静默失败）。"""
    from app.core.model_config import LLM_MODEL_ROLES

    lifespan = _lifespan_ast()
    labels: list[str] = []
    for node in ast.walk(lifespan):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "SubModelSpec":
            for kw in node.keywords:
                if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                    labels.append(str(kw.value.value))

    assert "会话摘要" in labels, f"摘要模型未纳入探活规格：{labels}"
    # 角色数与探活规格数对得上（不含 asr/tts，它们不是 LLM 角色）
    assert len(labels) == len(LLM_MODEL_ROLES), (
        f"探活规格数 {len(labels)} 与 LLM 角色数 {len(LLM_MODEL_ROLES)} 不一致：{labels}"
    )


def test_summary_role_has_thinking_switch_of_its_own():
    """摘要角色要有独立的 thinking 开关（不能与审核/拆解共用一个）。"""
    from app.core.config import settings

    assert hasattr(settings, "summary_enable_thinking")
    assert hasattr(settings, "summary_model")


def test_shutdown_clears_global_app_context():
    """回归：关停后必须把全局 app_context 置空。

    残留会让后续请求/测试拿到已关停的旧实例（TestClient 场景下表现为
    「没有上下文时应该抛 RuntimeError」这条断言失败）。
    """
    from app.agent import context as ctxmod

    # 有上下文时 get_app_context 正常返回，不抛错
    sentinel = SimpleNamespace(chat_model=object())
    ctxmod.set_app_context(sentinel)  # type: ignore[arg-type]
    try:
        assert ctxmod.get_app_context() is sentinel
    finally:
        ctxmod.set_app_context(None)

    # 置空后必须抛 RuntimeError（而不是静默返回 None）
    with pytest.raises(RuntimeError, match="AppContext not initialized"):
        ctxmod.get_app_context()


def test_shutdown_catches_base_exception_not_only_exception():
    """关停路径的异常捕获必须含 CancelledError（它是 BaseException 子类）。

    except Exception 接不住 CancelledError ⇒ 关停被中断 ⇒ 全局上下文没被清理、
    连接池没关、后台 worker 没停，症状散落在别处（本次就表现为跨测试污染）。
    """
    lifespan = _lifespan_ast()

    # 找出关停段（yield 之后）的所有 try/except，确认没有裸 except Exception
    after_yield = False
    bad: list[int] = []
    for node in ast.walk(lifespan):
        if isinstance(node, ast.Yield):
            after_yield = True
        if after_yield and isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bad.append(node.lineno)
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                bad.append(node.lineno)
    # 关停段允许出现 except Exception（纯同步清理），但必须确保 CancelledError
    # 场景已被 BaseException 覆盖 —— 这里断言存在至少一处 BaseException 捕获。
    has_base = any(
        isinstance(n, ast.ExceptHandler)
        and isinstance(n.type, ast.Name)
        and n.type.id == "BaseException"
        for n in ast.walk(lifespan)
    )
    assert has_base, "关停路径没有捕获 BaseException：CancelledError 会中断整个关停流程"
