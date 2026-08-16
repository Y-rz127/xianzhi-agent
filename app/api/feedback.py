"""问题反馈（登录用户带 user_id，未登录可匿名提交）。"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.common import client_error
from app.api.deps import require_admin
from app.core.logger import log
from app.db import repository as repo

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("")
async def submit_feedback(body: dict, token: str = Query(None)):
    """提交问题反馈（登录用户带 user_id，未登录可匿名）。"""
    content = (body.get("content") or "").strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="反馈内容至少 5 个字")
    uid = None
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        fid = await repo.add_feedback(uid, content, body.get("contact", ""))
        return {"id": fid}
    except Exception as e:
        log.exception("提交反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("/answer")
async def submit_answer_feedback(body: dict, token: str = Query(None)):
    """提交单条 AI 回答的点赞/点踩反馈，并自动提取断事知识到命盘画像。"""
    answer = (body.get("answer") or "").strip()
    rating = (body.get("rating") or "").strip()
    if rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating 必须是 up 或 down")
    if len(answer) < 5:
        raise HTTPException(status_code=400, detail="回答内容过短，无法记录反馈")
    uid = None
    if token:
        u = await repo.get_by_token(token)
        if u:
            uid = u["id"]
    try:
        chart_snapshot = body.get("chart_snapshot") or {}
        fid = await repo.add_answer_feedback(
            uid,
            body.get("conversation_id", ""),
            body.get("question", ""),
            answer,
            rating,
            body.get("reason", ""),
            chart_snapshot,
        )

        # 提取断事知识到命盘画像
        # uid 可能为空（匿名用户），用 conversation_id 兜底
        extract_uid = uid or body.get("conversation_id", "") or "anonymous"
        if chart_snapshot:
            birth_time = chart_snapshot.get("birth_time") or ""
            gender = chart_snapshot.get("gender") or ""
            if birth_time and gender:
                try:
                    await _extract_fact_to_profile(
                        extract_uid, birth_time, gender,
                        body.get("conversation_id", ""),
                        body.get("question", ""),
                        answer,
                        rating,
                        body.get("reason", ""),
                        chart_snapshot,
                    )
                except Exception as e:
                    log.warning("提取断事知识失败（不影响主流程）: {}", e)

        return {"id": fid}
    except Exception as e:
        log.exception("提交回答反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))


async def _extract_fact_to_profile(
    user_id: str,
    birth_time: str,
    gender: str,
    conversation_id: str,
    question: str,
    answer: str,
    rating: str,
    reason: str,
    chart_data: dict,
):
    """从反馈中提取断事知识，存入命盘画像和断事知识库。"""
    # 确保命盘画像存在
    pid = await repo.upsert_chart_profile(
        user_id, birth_time, gender, chart_data, interaction_count=1
    )

    # 提取回答摘要（取前 500 字作为断事内容）
    answer_snippet = answer[:500] if answer else ""

    # 根据反馈类型设置置信度
    confidence = "verified" if rating == "up" else "disputed"

    await repo.add_chart_fact(
        user_id=user_id,
        chart_profile_id=pid,
        conversation_id=conversation_id,
        question=question,
        answer_snippet=answer_snippet,
        confidence=confidence,
        reason=reason,
    )

    # 更新画像统计
    profile = await repo.get_chart_profile(user_id, birth_time, gender)
    if profile:
        stats = profile.get("feedback_stats") or {}
        stats["up"] = (stats.get("up") or 0) + (1 if rating == "up" else 0)
        stats["down"] = (stats.get("down") or 0) + (1 if rating == "down" else 0)
        stats["total"] = (stats.get("up") or 0) + (stats.get("down") or 0)
        await repo.update_chart_profile_stats(
            user_id, birth_time, gender,
            feedback_stats=stats,
        )

    log.info(
        "断事知识已提取: user={} chart={}:{} rating={} profile={}",
        user_id, birth_time, gender, rating, pid,
    )


@router.delete("/{fid}", dependencies=[Depends(require_admin)])
async def delete_feedback(fid: str):
    """删除一条反馈；不存在返回 404。"""
    try:
        ok = await repo.delete_feedback(fid)
        if not ok:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("删除反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))
@router.get("", dependencies=[Depends(require_admin)])
async def get_feedback_list(limit: int = Query(default=200, ge=1, le=1000)):
    """管理员查看反馈列表（按时间倒序）。"""
    try:
        items = await repo.list_feedback(limit)
        return {"items": items}
    except Exception as e:
        log.exception("获取反馈列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/answers", dependencies=[Depends(require_admin)])
async def get_answer_feedback_list(
    limit: int = Query(default=200, ge=1, le=1000),
    rating: str | None = Query(default=None),
):
    """管理员查看回答偏好反馈列表。"""
    try:
        items = await repo.list_answer_feedback(limit, rating)
        return {"items": items}
    except Exception as e:
        log.exception("获取回答反馈列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/answers/export/sft", dependencies=[Depends(require_admin)])
async def export_answer_feedback_sft(
    limit: int = Query(default=1000, ge=1, le=10000),
    rating: str = Query(default="up"),
):
    """导出回答反馈为 JSONL SFT 训练样本。"""
    if rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating 必须是 up 或 down")
    try:
        samples = await repo.export_sft_samples(limit=limit, rating=rating)
        content = "\n".join(json.dumps(s, ensure_ascii=False) for s in samples)
        filename = f"xianzhi_sft_{rating}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        return Response(
            content=content,
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.exception("导出 SFT 样本失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("/answers/{fid}/review", dependencies=[Depends(require_admin)])
async def review_answer_feedback(fid: str, body: dict | None = None):
    """标记一条回答反馈为已审核。"""
    reviewer = (body or {}).get("reviewer", "admin")
    try:
        ok = await repo.mark_answer_reviewed(fid, reviewer)
        if not ok:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("审核回答反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("/answers/{fid}/promote", dependencies=[Depends(require_admin)])
async def promote_answer_to_case(fid: str, body: dict | None = None):
    """将一条已审核的回答反馈转为结构化案例（支持好评/差评）。"""
    reviewer = (body or {}).get("reviewer", "admin")
    try:
        result = await repo.promote_to_case(fid, reviewer)
        if result is None:
            raise HTTPException(status_code=400, detail="仅已审核的反馈可转为案例，或反馈不存在")
        case_id, file_path = result
        return {"case_id": case_id, "file_path": file_path}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("好评转案例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/answers/{fid}/promote", dependencies=[Depends(require_admin)])
async def unpromote_answer_to_case(fid: str):
    """取消一条已沉淀的案例：删除 chart_cases 行 + 清空 answer_feedback.case_id 引用。

    幂等：若该反馈未转过案例（answer_feedback.case_id 为空），返回 404。
    """
    try:
        ok = await repo.unpromote_answer_to_case(fid)
        if not ok:
            raise HTTPException(status_code=404, detail="该反馈未转过案例")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("取消案例沉淀失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/answers/export/dpo", dependencies=[Depends(require_admin)])
async def export_dpo_samples(
    limit: int = Query(default=500, ge=1, le=5000),
):
    """导出 DPO 偏好对（chosen/rejected）为 JSONL。"""
    try:
        samples = await repo.export_dpo_samples(limit=limit)
        content = "\n".join(json.dumps(s, ensure_ascii=False) for s in samples)
        filename = f"xianzhi_dpo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        return Response(
            content=content,
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.exception("导出 DPO 样本失败")
        raise HTTPException(status_code=500, detail=client_error(e))


# ---------------- 命盘画像 & 断事知识 API ----------------


@router.get("/profiles")
async def get_chart_profiles(token: str = Query(None)):
    """获取当前用户所有命盘的画像列表。"""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    u = await repo.get_by_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="登录已过期")
    try:
        profiles = await repo.list_chart_profiles_by_user(u["id"])
        return {"profiles": profiles}
    except Exception as e:
        log.exception("获取命盘画像失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/profiles/{profile_id}/facts")
async def get_profile_facts(
    profile_id: str,
    token: str = Query(None),
    confidence: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取指定命盘画像的断事知识列表。"""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    u = await repo.get_by_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="登录已过期")
    try:
        facts = await repo.get_chart_facts(profile_id, confidence, limit)
        return {"facts": facts}
    except Exception as e:
        log.exception("获取断事知识失败")
        raise HTTPException(status_code=500, detail=client_error(e))
