"""先知（Xianzhi）相关接口聚合。

历史：本文件曾含全部路由（~700 行）。2026-09-15 拆为——
- app.api.xianzhi_chat   （SSE / WebSocket / 同步 对话）
- app.api.xianzhi_chart  （缓存统计 / 岁运关系现算 / 直接排盘 / 八字反推）
- app.api.xianzhi_kline  （命理 K 线：确定性运势评分 → 年 OHLCV + 大运带）
- app.api.xianzhi_report （报告任务提交 / 查询 / 下载）
- app.api._xianzhi_common（命盘挂载 / 线程安全通知桥 / 保活循环 等共享辅助）

本文件保留 router 聚合 + 会话类路由（/sessions*），并 re-export 少量被单测直接
依赖的符号（make_chart_notifier / ws_keepalive_loop / get_relations 等），
以保证 app.api.xianzhi 这一导入路径的向后兼容。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent.context import AppContext
from app.api import (
    _xianzhi_common,
    data_access as repo,
    xianzhi_chart,
    xianzhi_chat,
    xianzhi_kline,
    xianzhi_report,
)
from app.api.deps import app_context_dependency, require_admin

chat_router = xianzhi_chat.router
chart_router = xianzhi_chart.router
kline_router = xianzhi_kline.router
report_router = xianzhi_report.router

# 单测直接依赖的符号：保持 ``app.api.xianzhi`` 这一导入路径的向后兼容
WS_PING_SECONDS = _xianzhi_common.WS_PING_SECONDS
make_chart_notifier = _xianzhi_common.make_chart_notifier
make_progress_notifier = _xianzhi_common.make_progress_notifier
ws_keepalive_loop = _xianzhi_common.ws_keepalive_loop
get_relations = xianzhi_chart.get_relations
_compute_chart_payload = xianzhi_chart._compute_chart_payload
_PILLAR_CACHE = xianzhi_chart._PILLAR_CACHE

router = APIRouter(prefix="/xianzhi", tags=["Xianzhi"])
router.include_router(chat_router)
router.include_router(chart_router)
router.include_router(kline_router)
router.include_router(report_router)


@router.get("/sessions", dependencies=[Depends(require_admin)])
async def list_xianzhi_sessions(prefix: str = "web-xianzhi"):
    """获取先知会话列表。
    prefix 可选值：web-xianzhi（默认，PC 端）/ mp-xianzhi（小程序端）。
    """
    return await repo.get_session_info(prefix)


@router.get("/sessions/mine")
async def list_my_sessions(token: str = Query(None)):
    """我的对话：按登录用户隔离的先知会话列表（小程序「我的」页用）。"""
    user = await repo.get_by_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return await repo.get_session_info(prefix="mp-xianzhi", user_id=user["id"])


async def _check_session_access(session_id: str, token: str | None):
    """会话归属校验：user_id 非空的会话仅限本人 token 访问（防越权枚举）。

    - 游客会话（session_metadata.user_id 为空，如 PC web 无登录场景）放行；
    - 有归属会话：token 无效或与归属用户不一致 → 403。
      （小程序端 get/del 请求自动携带 token query，正常用户不受影响）
    """
    owner = await repo.get_session_owner(session_id)
    if not owner:
        return
    user = await repo.get_by_token(token) if token else None
    if not user or user["id"] != owner:
        raise HTTPException(status_code=403, detail="无权访问该会话")


@router.delete("/sessions/{session_id}")
async def delete_xianzhi_session(session_id: str, token: str = Query(None)):
    """删除先知会话（含消息记录）。有归属的会话需本人 token。"""
    await _check_session_access(session_id, token)
    await repo.delete_session(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/messages")
async def get_xianzhi_session_messages(session_id: str, token: str = Query(None)):
    """获取会话的完整消息记录。有归属的会话需本人 token。"""
    await _check_session_access(session_id, token)
    return await repo.get_messages(session_id)


@router.get("/sessions/{session_id}/birth-info")
async def get_xianzhi_session_birth_info(
    session_id: str,
    token: str = Query(None),
    app_ctx: AppContext = Depends(app_context_dependency),
):
    """从会话恢复命盘上下文（出生信息）。

    三级来源，取到即返回：
    1. 会话实例内存（`_last_birth_info`）——最新，本轮刚挂的盘也拿得到；
    2. PG `session_birth_info`——挂盘时即落库，进程重启/换端/换实例都能恢复（权威兜底）；
    3. 会话历史里的排盘工具调用参数——兼容旧数据（本表上线前的老会话）。

    出生信息属敏感个人数据，有归属的会话需本人 token。
    """
    await _check_session_access(session_id, token)
    try:
        agent, _ = app_ctx.get_xianzhi(session_id)
        current = getattr(agent, "_last_birth_info", None) or {}
        if current.get("time") and current.get("gender"):
            return {"time": current["time"], "gender": current["gender"]}
    except Exception:
        pass
    stored = await repo.get_session_birth_info(session_id)
    if stored and stored.get("time") and stored.get("gender"):
        return {"time": stored["time"], "gender": stored["gender"]}
    info = await repo.get_birth_info_from_session(session_id)
    return info or {"time": None, "gender": None}
