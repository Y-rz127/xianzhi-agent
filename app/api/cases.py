"""命盘快照（命例）管理：cases 表（Bazi 结构）的增删改查与 JSON 导入导出。

注意与 chart_cases 区分：chart_cases 是用户反馈转换的结构化案例库
（promote_to_case 写入），本模块操作的是 Web 端新建命例的 cases 表。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.common import client_error
from app.api.deps import require_admin
from app.core.logger import log
from app.domain.bazi_engine import extract_bazi_brief

router = APIRouter(prefix="/cases", tags=["Cases"])

# PostgreSQL 不可用时回退到本地 JSON 文件存储
_fallback_file = Path("./data/cases.json")

_table_ready = False
_pg_unavailable = False

_CASE_COLS = "id, name, tags, birth_time, gender, bio, analysis, keypoints, domains, chart_data, created_at, updated_at"
_INSERT_CASE_SQL = (
    "INSERT INTO cases (id, name, tags, birth_time, gender, chart_data, bio, analysis, keypoints, domains) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def _get_pool():
    """复用 postgres_memory 模块级连接池（懒创建）。"""
    from app.memory.postgres_memory import _get_pool as _pg_get_pool
    return _pg_get_pool()


def ensure_table():
    """确保 cases 表存在（幂等，进程内只执行一次）；不可用返回 False 以回退本地存储。

    cases 表结构由 app.db.user_data._ensure_tables 统一创建，此处直接复用。
    """
    global _table_ready, _pg_unavailable
    if _table_ready:
        return True
    if _pg_unavailable:
        return False
    try:
        from app.db import user_data
        user_data._ensure_tables()
        _table_ready = True
        log.info("命例表（cases）已就绪")
        return True
    except Exception as e:
        _pg_unavailable = True
        log.warning("命例表不可用，切换到本地 JSON 存储: {}", e)
        return False


def _load_file_cases() -> list[dict[str, Any]]:
    if not _fallback_file.exists():
        return []
    try:
        data = json.loads(_fallback_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("cases", []) or []
        if isinstance(data, list):
            return data
    except Exception as e:
        log.warning("读取本地命例失败: {}", e)
    return []


def _save_file_cases(cases: list[dict[str, Any]]) -> None:
    _fallback_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updatedAt": datetime.now().isoformat(),
        "cases": cases,
    }
    _fallback_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_file_case(name: str, birth_time: str, gender: str, tags: list, chart_data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "tags": tags,
        "birthTime": birth_time,
        "gender": gender,
        "chartData": chart_data,
        "createdAt": now,
        "updatedAt": now,
    }


def _build_chart_data(birth_time: str, gender: str) -> dict[str, Any]:
    """调用结构化排盘引擎生成命例数据。"""
    from app.domain.bazi_engine import (
        build_bazi_chart,
        chart_to_api_dict,
        format_analysis_text,
        format_chart_text,
        format_dayun_text,
        format_liunian_text,
    )

    chart = build_bazi_chart(birth_time, gender, dayun_count=8, liunian_years=5)
    payload = chart_to_api_dict(chart)
    payload.update({
        "chartText": format_chart_text(chart),
        "analysisText": format_analysis_text(chart, "整体命盘"),
        "dayunText": format_dayun_text(chart),
        "liunianText": format_liunian_text(chart),
    })
    return payload


def _parse_chart(value) -> dict:
    return value if isinstance(value, dict) else json.loads(value) if value else {}


def _row_to_case(row, with_chart: bool = False) -> dict:
    """将 cases 行（_CASE_COLS 列序）映射为 API 结构。"""
    case = {
        "id": str(row[0]),
        "name": row[1],
        "tags": row[2] or [],
        "birthTime": row[3],
        "gender": row[4],
        "bio": row[5] or "",
        "analysis": row[6] or "",
        "keypoints": row[7] or "",
        "domains": row[8] or [],
        "createdAt": str(row[10]) if row[10] else "",
        "updatedAt": str(row[11]) if row[11] else "",
    }
    if with_chart:
        case["chartData"] = _parse_chart(row[9])
    return case


def _db_list_cases() -> list[dict[str, Any]]:
    """同步查询命例列表（handler 中经 asyncio.to_thread 调用）。"""
    with _get_pool().connection() as conn:
        cur = conn.execute(f"SELECT {_CASE_COLS} FROM cases ORDER BY updated_at DESC")
        return [
            {**_row_to_case(row), "bazi": extract_bazi_brief(_parse_chart(row[9]))}
            for row in cur
        ]


@router.get("", dependencies=[Depends(require_admin)])
async def list_cases():
    """获取所有命例列表（cases 表，Bazi 结构）。"""
    if not await asyncio.to_thread(ensure_table):
        cases = _load_file_cases()
        return [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "tags": c.get("tags") or [],
                "birthTime": c.get("birthTime") or c.get("birth_time", ""),
                "gender": c.get("gender", ""),
                "createdAt": c.get("createdAt", ""),
                "updatedAt": c.get("updatedAt", ""),
                "bazi": extract_bazi_brief(c.get("chartData") or c.get("chart_data")),
            }
            for c in sorted(cases, key=lambda x: x.get("updatedAt", ""), reverse=True)
        ]
    try:
        return await asyncio.to_thread(_db_list_cases)
    except Exception as e:
        log.exception("获取命例列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _db_create_case(name, tags, birth_time, gender, chart_data, bio, analysis, keypoints, domains) -> str:
    """同步写入新命例，返回新 id。"""
    with _get_pool().connection() as conn:
        cur = conn.execute(
            _INSERT_CASE_SQL,
            (str(uuid.uuid4()), name, tags, birth_time, gender, json.dumps(chart_data),
             bio, analysis, keypoints, domains),
        )
        row = cur.fetchone()
    return str(row[0])


@router.post("", dependencies=[Depends(require_admin)])
async def create_case(payload: dict):
    """保存新命例（写入 cases 表）；未提供 chart_data 时后端自动排盘生成。"""
    name = (payload.get("name") or "").strip()
    birth_time = (payload.get("birth_time") or "").strip()
    gender = (payload.get("gender") or "").strip()
    if not name or not birth_time or not gender:
        raise HTTPException(status_code=400, detail="name、birth_time、gender 必填")

    tags = payload.get("tags") or []
    bio = (payload.get("bio") or "").strip()
    analysis = (payload.get("analysis") or "").strip()
    keypoints = (payload.get("keypoints") or "").strip()
    domains = payload.get("domains") or []
    chart_data = payload.get("chart_data") or await asyncio.to_thread(_build_chart_data, birth_time, gender)

    if not await asyncio.to_thread(ensure_table):
        case = _new_file_case(name, birth_time, gender, tags, chart_data)
        cases = _load_file_cases()
        cases.append(case)
        _save_file_cases(cases)
        return {"id": case["id"], "status": "ok", "storage": "file"}

    try:
        cid = await asyncio.to_thread(
            _db_create_case, name, tags, birth_time, gender, chart_data,
            bio, analysis, keypoints, domains,
        )
        return {"id": cid, "status": "ok"}
    except Exception as e:
        log.exception("保存命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _db_get_case(case_id: str) -> dict[str, Any] | None:
    """同步查询单个命例；不存在返回 None。"""
    with _get_pool().connection() as conn:
        cur = conn.execute(f"SELECT {_CASE_COLS} FROM cases WHERE id = %s", (case_id,))
        row = cur.fetchone()
    return _row_to_case(row, with_chart=True) if row else None


@router.get("/{case_id}", dependencies=[Depends(require_admin)])
async def get_case(case_id: str):
    """获取单个命例详情（cases 表）。"""
    if not await asyncio.to_thread(ensure_table):
        for c in _load_file_cases():
            if c.get("id") == case_id:
                return c
        raise HTTPException(status_code=404, detail="命例不存在")
    try:
        item = await asyncio.to_thread(_db_get_case, case_id)
        if not item:
            raise HTTPException(status_code=404, detail="命例不存在")
        return item
    except HTTPException:
        raise
    except Exception as e:
        log.exception("获取命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _db_update_case(case_id, payload):
    """同步执行命例更新 SQL；无更新字段时抛 ValueError。"""
    with _get_pool().connection() as conn:
        updates = []
        params = []
        if "name" in payload:
            updates.append("name = %s")
            params.append(payload["name"])
        if "tags" in payload:
            updates.append("tags = %s")
            params.append(payload["tags"])
        for field in ("bio", "analysis", "keypoints"):
            if field in payload:
                updates.append(f"{field} = %s")
                params.append((payload[field] or "").strip())
        if "domains" in payload:
            updates.append("domains = %s")
            params.append(payload["domains"] or [])
        if "birth_time" in payload and "gender" in payload:
            birth_time = payload["birth_time"]
            gender = payload["gender"]
            updates.extend(["birth_time = %s", "gender = %s"])
            params.extend([birth_time, gender])
            if payload.get("regenerate_chart_data", True):
                updates.append("chart_data = %s")
                params.append(json.dumps(_build_chart_data(birth_time, gender)))
        if not updates:
            raise ValueError("无更新字段")
        updates.append("updated_at = NOW()")
        params.append(case_id)
        conn.execute(
            f"UPDATE cases SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )


@router.put("/{case_id}", dependencies=[Depends(require_admin)])
async def update_case(case_id: str, payload: dict):
    """更新命例（名称、标签、出生信息）。"""
    if not await asyncio.to_thread(ensure_table):
        cases = _load_file_cases()
        for c in cases:
            if c.get("id") != case_id:
                continue
            if "name" in payload:
                c["name"] = payload["name"]
            if "tags" in payload:
                c["tags"] = payload["tags"]
            if "birth_time" in payload and "gender" in payload:
                c["birthTime"] = payload["birth_time"]
                c["gender"] = payload["gender"]
                if payload.get("regenerate_chart_data", True):
                    c["chartData"] = await asyncio.to_thread(_build_chart_data, payload["birth_time"], payload["gender"])
            c["updatedAt"] = datetime.now().isoformat()
            _save_file_cases(cases)
            return {"status": "ok", "storage": "file"}
        raise HTTPException(status_code=404, detail="命例不存在")
    try:
        await asyncio.to_thread(_db_update_case, case_id, payload)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("更新命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _db_delete_case(case_id: str) -> None:
    with _get_pool().connection() as conn:
        conn.execute("DELETE FROM cases WHERE id = %s", (case_id,))


@router.delete("/{case_id}", dependencies=[Depends(require_admin)])
async def delete_case(case_id: str):
    """删除命例（cases 表）。"""
    if not await asyncio.to_thread(ensure_table):
        cases = _load_file_cases()
        _save_file_cases([c for c in cases if c.get("id") != case_id])
        return {"status": "ok", "storage": "file"}
    try:
        await asyncio.to_thread(_db_delete_case, case_id)
        return {"status": "ok"}
    except Exception as e:
        log.exception("删除命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


def _db_export_cases() -> list[dict[str, Any]]:
    """同步导出全部命例。"""
    with _get_pool().connection() as conn:
        cur = conn.execute(f"SELECT {_CASE_COLS} FROM cases ORDER BY updated_at DESC")
        return [_row_to_case(row, with_chart=True) for row in cur]


@router.get("/export/json", dependencies=[Depends(require_admin)])
async def export_cases_json():
    """导出所有命例为 JSON 文件（attachment）。"""
    if not await asyncio.to_thread(ensure_table):
        cases = _load_file_cases()
    else:
        try:
            cases = await asyncio.to_thread(_db_export_cases)
        except Exception as e:
            log.exception("导出命例失败")
            raise HTTPException(status_code=500, detail=client_error(e))
    content = json.dumps({"version": 1, "exportedAt": datetime.now().isoformat(), "cases": cases}, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="xianzhi_cases.json"'},
    )


def _db_import_cases(cases) -> tuple[int, int]:
    """同步批量导入命例，返回 (inserted, skipped)。"""
    inserted = 0
    skipped = 0
    with _get_pool().connection() as conn:
        for c in cases:
            cid = c.get("id")
            if cid:
                cur = conn.execute("SELECT 1 FROM cases WHERE id = %s", (cid,))
                if cur.fetchone():
                    skipped += 1
                    continue
            birth_time = (c.get("birthTime") or c.get("birth_time") or "").strip()
            gender = (c.get("gender") or "").strip()
            if not birth_time or not gender:
                continue
            chart_data = c.get("chartData") or c.get("chart_data")
            if not chart_data:
                chart_data = _build_chart_data(birth_time, gender)
            conn.execute(
                _INSERT_CASE_SQL,
                (
                    str(uuid.uuid4()),
                    (c.get("name") or "未命名命例").strip(),
                    c.get("tags") or [],
                    birth_time,
                    gender,
                    json.dumps(chart_data),
                    (c.get("bio") or "").strip(),
                    (c.get("analysis") or "").strip(),
                    (c.get("keypoints") or "").strip(),
                    c.get("domains") or [],
                ),
            )
            inserted += 1
    return inserted, skipped


@router.post("/import/json", dependencies=[Depends(require_admin)])
async def import_cases_json(payload: dict):
    """从 JSON 导入命例（相同 id 跳过，新增命例生成新 id）。"""
    cases = payload.get("cases") or []
    if not isinstance(cases, list):
        raise HTTPException(status_code=400, detail="cases 必须是数组")

    if not await asyncio.to_thread(ensure_table):
        existing = _load_file_cases()
        existing_ids = {c.get("id") for c in existing}
        inserted = 0
        skipped = 0
        for c in cases:
            cid = c.get("id")
            if cid and cid in existing_ids:
                skipped += 1
                continue
            birth_time = (c.get("birthTime") or c.get("birth_time") or "").strip()
            gender = (c.get("gender") or "").strip()
            if not birth_time or not gender:
                continue
            chart_data = c.get("chartData") or c.get("chart_data") or await asyncio.to_thread(_build_chart_data, birth_time, gender)
            existing.append(_new_file_case((c.get("name") or "未命名命例").strip(), birth_time, gender, c.get("tags") or [], chart_data))
            inserted += 1
        _save_file_cases(existing)
        return {"inserted": inserted, "skipped": skipped, "storage": "file"}

    try:
        inserted, skipped = await asyncio.to_thread(_db_import_cases, cases)
        return {"inserted": inserted, "skipped": skipped}
    except Exception as e:
        log.exception("导入命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))
