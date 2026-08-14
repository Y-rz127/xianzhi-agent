"""问题反馈（登录用户带 user_id，未登录可匿名提交）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.common import api_guard, jsonl_attachment
from app.api.deps import require_admin, require_user_by_token, user_id_from_token
from app.db import user_data
from app.logger import log

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("")
async def submit_feedback(body: dict, token: str = Query(None)):
    """提交问题反馈（登录用户带 user_id，未登录可匿名）。"""
    content = (body.get("content") or "").strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="反馈内容至少 5 个字")
    uid = user_id_from_token(token) or None
    with api_guard("提交反馈失败"):
        fid = user_data.add_feedback(uid, content, body.get("contact", ""))
        return {"id": fid}


@router.post("/answer")
async def submit_answer_feedback(body: dict, token: str = Query(None)):
    """提交单条 AI 回答的点赞/点踩反馈，并自动提取断事知识到命盘画像。"""
    answer = (body.get("answer") or "").strip()
    rating = (body.get("rating") or "").strip()
    if rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating 必须是 up 或 down")
    if len(answer) < 5:
        raise HTTPException(status_code=400, detail="回答内容过短，无法记录反馈")
    uid = user_id_from_token(token) or None
    with api_guard("提交回答反馈失败"):
        chart_snapshot = body.get("chart_snapshot") or {}
        fid = user_data.add_answer_feedback(
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
                    _extract_fact_to_profile(
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


def _extract_fact_to_profile(
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
    pid = user_data.upsert_chart_profile(
        user_id, birth_time, gender, chart_data, interaction_count=1
    )

    # 提取回答摘要（取前 500 字作为断事内容）
    answer_snippet = answer[:500] if answer else ""

    # 根据反馈类型设置置信度
    confidence = "verified" if rating == "up" else "disputed"

    user_data.add_chart_fact(
        user_id=user_id,
        chart_profile_id=pid,
        conversation_id=conversation_id,
        question=question,
        answer_snippet=answer_snippet,
        confidence=confidence,
        reason=reason,
    )

    # 更新画像统计
    profile = user_data.get_chart_profile(user_id, birth_time, gender)
    if profile:
        stats = profile.get("feedback_stats") or {}
        stats["up"] = (stats.get("up") or 0) + (1 if rating == "up" else 0)
        stats["down"] = (stats.get("down") or 0) + (1 if rating == "down" else 0)
        stats["total"] = (stats.get("up") or 0) + (stats.get("down") or 0)
        user_data.update_chart_profile_stats(
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
    with api_guard("删除反馈失败"):
        ok = user_data.delete_feedback(fid)
        if not ok:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return {"ok": True}


@router.get("", dependencies=[Depends(require_admin)])
async def get_feedback_list(limit: int = Query(default=200, ge=1, le=1000)):
    """管理员查看反馈列表（按时间倒序）。"""
    with api_guard("获取反馈列表失败"):
        return {"items": user_data.list_feedback(limit)}


@router.get("/answers", dependencies=[Depends(require_admin)])
async def get_answer_feedback_list(
    limit: int = Query(default=200, ge=1, le=1000),
    rating: str | None = Query(default=None),
):
    """管理员查看回答偏好反馈列表。"""
    with api_guard("获取回答反馈列表失败"):
        return {"items": user_data.list_answer_feedback(limit, rating)}


@router.get("/answers/export/sft", dependencies=[Depends(require_admin)])
async def export_answer_feedback_sft(
    limit: int = Query(default=1000, ge=1, le=10000),
    rating: str = Query(default="up"),
):
    """导出回答反馈为 JSONL SFT 训练样本。"""
    if rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating 必须是 up 或 down")
    with api_guard("导出 SFT 样本失败"):
        samples = user_data.export_sft_samples(limit=limit, rating=rating)
        return jsonl_attachment(samples, f"xianzhi_sft_{rating}")


@router.post("/answers/{fid}/review", dependencies=[Depends(require_admin)])
async def review_answer_feedback(fid: str, body: dict | None = None):
    """标记一条回答反馈为已审核。"""
    reviewer = (body or {}).get("reviewer", "admin")
    with api_guard("审核回答反馈失败"):
        ok = user_data.mark_answer_reviewed(fid, reviewer)
        if not ok:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return {"ok": True}


@router.post("/answers/{fid}/promote", dependencies=[Depends(require_admin)])
async def promote_answer_to_case(fid: str, body: dict | None = None):
    """将一条已审核的回答反馈转为结构化案例（支持好评/差评）。"""
    reviewer = (body or {}).get("reviewer", "admin")
    with api_guard("好评转案例失败"):
        result = user_data.promote_to_case(fid, reviewer)
        if result is None:
            raise HTTPException(status_code=400, detail="仅已审核的反馈可转为案例，或反馈不存在")
        case_id, file_path = result
        return {"case_id": case_id, "file_path": file_path}


@router.get("/answers/export/dpo", dependencies=[Depends(require_admin)])
async def export_dpo_samples(
    limit: int = Query(default=500, ge=1, le=5000),
):
    """导出 DPO 偏好对（chosen/rejected）为 JSONL。"""
    with api_guard("导出 DPO 样本失败"):
        samples = user_data.export_dpo_samples(limit=limit)
        return jsonl_attachment(samples, "xianzhi_dpo")


# ---------------- 命盘画像 & 断事知识 API ----------------


@router.get("/profiles")
async def get_chart_profiles(token: str = Query(None)):
    """获取当前用户所有命盘的画像列表。"""
    user = require_user_by_token(token)
    with api_guard("获取命盘画像失败"):
        return {"profiles": user_data.list_chart_profiles_by_user(user["id"])}


@router.get("/profiles/{profile_id}/facts")
async def get_profile_facts(
    profile_id: str,
    token: str = Query(None),
    confidence: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取指定命盘画像的断事知识列表。"""
    require_user_by_token(token)
    with api_guard("获取断事知识失败"):
        return {"facts": user_data.get_chart_facts(profile_id, confidence, limit)}