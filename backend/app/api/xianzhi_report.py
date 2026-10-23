"""先知报告任务接口：后台异步队列（提交 / 状态查询 / 产物下载）。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import get_paid_principal
from app.core.config import settings
from app.core.http.client_ip import client_ip_from_request
from app.core.quota import enforce_quota

router = APIRouter(tags=["Xianzhi"])

# 提交节流：每 kind 每 IP 10 分钟内最多 3 次（报告是重资产动作：CPU/LLM 配额）
_REPORT_TASK_SUBMIT_LIMIT = 3
_REPORT_TASK_SUBMIT_WINDOW = 600


def _build_task_params(birth_time: str, gender: str, sections: str) -> dict:
    """任务参数（含口径版本）。

    ver 参与 params 全等比较：口径版本一 bump，旧任务不再被幂等复用，
    用户重新生成才会得到新口径的报告（旧任务自带旧正文）。
    """
    from app.tools.report_prompts import REPORT_PROMPT_VERSION

    return {"birth_time": birth_time, "gender": gender, "sections": sections, "ver": REPORT_PROMPT_VERSION}


@router.post("/report/tasks")
async def submit_report_task(
    payload: dict,
    request: Request,
    principal: dict = Depends(get_paid_principal),
):
    """提交报告生成任务，返回 task_id；生成在后台队列执行，轮询 GET /report/tasks/{id} 取状态。

    kind: basic_report(排盘 PDF) | full_report(LLM Markdown) | full_report_pdf(LLM PDF)
    """
    from app.core.redis_client import rate_limit_allow
    from app.db import report_tasks
    from app.tasks.worker import enqueue
    from app.tools.report_tasks import KINDS

    kind = (payload.get("kind") or "").strip()
    birth_time = (payload.get("birth_time") or "").strip()
    gender = (payload.get("gender") or "").strip()
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {'/'.join(KINDS)}")
    if not birth_time or not gender:
        raise HTTPException(status_code=400, detail="birth_time 和 gender 必填")

    uid = principal["id"]
    ip = client_ip_from_request(request)
    params = _build_task_params(birth_time, gender, (payload.get("sections") or "").strip())
    # 幂等复用：同参数任务未过期直接返回旧 task_id（复用不产生新成本，不消耗配额）
    existing = await asyncio.to_thread(report_tasks.find_same_task, kind, params, uid)
    if existing:
        row = await asyncio.to_thread(report_tasks.get_task, existing)
        if row:
            return {"task_id": existing, "status": row["status"]}

    verdict = await rate_limit_allow(
        f"task-submit:{kind}:{ip}", _REPORT_TASK_SUBMIT_LIMIT, _REPORT_TASK_SUBMIT_WINDOW
    )
    if verdict is False:
        raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")
    # 原子查重+建任务：并发提交同一参数时只有一个任务会被创建，避免 find→create 竞态
    task_id, status, created = await asyncio.to_thread(
        report_tasks.get_or_create_task, kind, params, uid
    )
    if not created:
        return {"task_id": task_id, "status": status}
    # 配额只在真正新建任务时扣：并发重复提交的失败方在上面已复用旧任务返回
    try:
        await enforce_quota("report", principal, ip, settings.paid_quota_report_daily)
    except Exception:
        await asyncio.to_thread(report_tasks.delete_task, task_id)
        raise
    try:
        await asyncio.to_thread(report_tasks.delete_old)
    except Exception:
        pass
    try:
        await enqueue(task_id)
    except Exception:
        await asyncio.to_thread(report_tasks.fail, task_id, "任务队列不可用，请稍后重试")
        raise HTTPException(status_code=503, detail="任务队列不可用，请稍后重试")
    return {"task_id": task_id, "status": status}


@router.get("/report/tasks/{task_id}")
async def get_report_task(task_id: str, principal: dict = Depends(get_paid_principal)):
    """查询任务状态；full_report 完成后 content 字段直接携带 Markdown 文本。"""
    from app.db import report_tasks

    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None or row["user_id"] != principal["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = {
        "task_id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
    if row["kind"] == "full_report" and row["status"] == "done" and row["payload"]:
        result["content"] = bytes(row["payload"]).decode("utf-8", errors="replace")
    return result


@router.get("/report/tasks/{task_id}/result")
async def get_report_task_result(task_id: str, principal: dict = Depends(get_paid_principal)):
    """下载任务产物（PDF / Markdown 文件）。"""
    from app.db import report_tasks
    from app.tools.report_tasks import KINDS

    row = await asyncio.to_thread(report_tasks.get_task, task_id)
    if row is None or row["user_id"] != principal["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row["status"] in ("pending", "running"):
        raise HTTPException(status_code=409, detail="任务尚未完成")
    if row["status"] != "done" or row["payload"] is None:
        raise HTTPException(status_code=410, detail=f"任务生成失败：{row['error'] or '未知错误'}")
    prefix, media = KINDS[row["kind"]]
    ext = "md" if row["kind"] == "full_report" else "pdf"
    return Response(
        content=bytes(row["payload"]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{prefix}.{ext}"'},
    )
