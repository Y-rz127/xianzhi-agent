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


async def _uid_from_token(token: str | None) -> str | None:
    """解析可选 token 为 user_id；未提供或无效返回 None。"""
    if not token:
        return None
    u = await repo.get_by_token(token)
    return u["id"] if u else None


async def _require_uid(token: str | None) -> str:
    """解析 token 为 user_id；缺失或失效抛 401。"""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    u = await repo.get_by_token(token)
    if not u:
        raise HTTPException(status_code=401, detail="登录已过期")
    return u["id"]


@router.post("")
async def submit_feedback(body: dict, token: str = Query(None)):
    """提交问题反馈（登录用户带 user_id，未登录可匿名）。"""
    content = (body.get("content") or "").strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="反馈内容至少 5 个字")
    try:
        fid = await repo.add_feedback(await _uid_from_token(token), content, body.get("contact", ""))
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
    try:
        uid = await _uid_from_token(token)
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
        if chart_snapshot:
            await _try_extract_fact(uid, body, chart_snapshot, answer, rating)
        return {"id": fid}
    except Exception as e:
        log.exception("提交回答反馈失败")
        raise HTTPException(status_code=500, detail=client_error(e))


async def _try_extract_fact(uid, body, chart_snapshot, answer, rating):
    """断事知识提取为尽力而为，失败不影响反馈主流程。"""
    birth_time = chart_snapshot.get("birth_time") or ""
    gender = chart_snapshot.get("gender") or ""
    if not birth_time or not gender:
        return
    # 匿名用户用 conversation_id 兜底身份
    extract_uid = uid or body.get("conversation_id", "") or "anonymous"
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


async def _extract_fact_to_profile(user_id, birth_time, gender, conversation_id, question, answer, rating, reason, chart_data):
    """从反馈中提取断事知识，存入命盘画像和断事知识库。"""
    pid = await repo.upsert_chart_profile(user_id, birth_time, gender, chart_data, interaction_count=1)
    answer_snippet = answer[:500] if answer else ""
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
    profile = await repo.get_chart_profile(user_id, birth_time, gender)
    if profile:
        stats = profile.get("feedback_stats") or {}
        stats["up"] = (stats.get("up") or 0) + (1 if rating == "up" else 0)
        stats["down"] = (stats.get("down") or 0) + (1 if rating == "down" else 0)
        stats["total"] = stats["up"] + stats["down"]
        await repo.update_chart_profile_stats(user_id, birth_time, gender, feedback_stats=stats)
    log.info("断事知识已提取: user={} chart={}:{} rating={} profile={}", user_id, birth_time, gender, rating, pid)


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
        return {"items": await repo.list_feedback(limit)}
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
        return {"items": await repo.list_answer_feedback(limit, rating)}
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

    幂等：该反馈未转过案例（case_id 为空）时返回 404。
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
    uid = await _require_uid(token)
    try:
        return {"profiles": await repo.list_chart_profiles_by_user(uid)}
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
    await _require_uid(token)
    try:
        return {"facts": await repo.get_chart_facts(profile_id, confidence, limit)}
    except Exception as e:
        log.exception("获取断事知识失败")
        raise HTTPException(status_code=500, detail=client_error(e))
