"""命盘快照（命例）管理。

提供命例的增删改查、JSON 导入导出接口。
命例数据库存储四柱、五行、大运、神煞等结构化排盘结果。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.api.common import client_error
from app.logger import log

router = APIRouter(prefix="/chart_cases", tags=["Chart Cases"])


_table_ready = False
_pg_unavailable = False
_fallback_file = Path("./data/chart_cases.json")


def _get_pool():
    """复用 postgres_memory 模块级连接池（线程安全，懒创建）。"""
    from app.memory.postgres_memory import _get_pool as _pg_get_pool
    return _pg_get_pool()


def ensure_table():
    """确保命例表存在（幂等，进程内只执行一次）。

    Returns:
        True 表示 PostgreSQL 命例表可用；False 表示应使用本地 JSON fallback。
    """
    global _table_ready, _pg_unavailable
    if _table_ready:
        return True
    if _pg_unavailable:
        return False
    try:
        with _get_pool().connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chart_cases (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name TEXT NOT NULL,
                    tags TEXT[] DEFAULT '{}',
                    birth_time TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    chart_data JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        _table_ready = True
        log.info("命例表已就绪")
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


def _extract_bazi_brief(chart_data: Any) -> str | None:
    """从 chart_data JSON 中提取四柱干支摘要，如 '辛卯 丁酉 庚午 丙子'。"""
    try:
        pillars = chart_data.get("pillars")
        if isinstance(pillars, list) and len(pillars) >= 4:
            parts = []
            for p in pillars:
                gz = p.get("ganzhi") if isinstance(p, dict) else None
                if isinstance(gz, list) and len(gz) >= 2:
                    parts.append(f"{gz[0]}{gz[1]}")
                elif isinstance(gz, str):
                    parts.append(gz)
            if len(parts) >= 4:
                return " ".join(parts[:4])
    except Exception:
        pass
    return None


@router.get("")
async def list_chart_cases():
    """获取所有命例列表。"""
    if not ensure_table():
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
                "bazi": _extract_bazi_brief(c.get("chartData") or c.get("chart_data")),
            }
            for c in sorted(cases, key=lambda x: x.get("updatedAt", ""), reverse=True)
        ]
    try:
        with _get_pool().connection() as conn:
            cur = conn.execute(
                """
                SELECT id, name, tags, birth_time, gender, created_at, updated_at, chart_data
                FROM chart_cases ORDER BY updated_at DESC
                """
            )
            result = []
            for row in cur:
                cd = row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
                result.append({
                    "id": str(row[0]),
                    "name": row[1],
                    "tags": row[2] or [],
                    "birthTime": row[3],
                    "gender": row[4],
                    "createdAt": str(row[5]) if row[5] else "",
                    "updatedAt": str(row[6]) if row[6] else "",
                    "bazi": _extract_bazi_brief(cd),
                })
        return result
    except Exception as e:
        log.exception("获取命例列表失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("")
async def create_chart_case(payload: dict):
    """保存新命例。

    payload: { name, birth_time, gender, tags?, chart_data? }
    若未提供 chart_data，后端自动排盘生成。
    """
    name = (payload.get("name") or "").strip()
    birth_time = (payload.get("birth_time") or "").strip()
    gender = (payload.get("gender") or "").strip()
    if not name or not birth_time or not gender:
        raise HTTPException(status_code=400, detail="name、birth_time、gender 必填")

    tags = payload.get("tags") or []
    chart_data = payload.get("chart_data") or _build_chart_data(birth_time, gender)

    if not ensure_table():
        cases = _load_file_cases()
        case = _new_file_case(name, birth_time, gender, tags, chart_data)
        cases.append(case)
        _save_file_cases(cases)
        return {"id": case["id"], "status": "ok", "storage": "file"}

    try:
        with _get_pool().connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO chart_cases (id, name, tags, birth_time, gender, chart_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (str(uuid.uuid4()), name, tags, birth_time, gender, json.dumps(chart_data)),
            )
            row = cur.fetchone()
        return {"id": str(row[0]), "status": "ok"}
    except Exception as e:
        log.exception("保存命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/{case_id}")
async def get_chart_case(case_id: str):
    """获取单个命例详情。"""
    if not ensure_table():
        for c in _load_file_cases():
            if c.get("id") == case_id:
                return c
        raise HTTPException(status_code=404, detail="命例不存在")
    try:
        with _get_pool().connection() as conn:
            cur = conn.execute(
                "SELECT id, name, tags, birth_time, gender, chart_data, created_at, updated_at FROM chart_cases WHERE id = %s",
                (case_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="命例不存在")
        return {
            "id": str(row[0]),
            "name": row[1],
            "tags": row[2] or [],
            "birthTime": row[3],
            "gender": row[4],
            "chartData": row[5] if isinstance(row[5], dict) else json.loads(row[5]),
            "createdAt": str(row[6]) if row[6] else "",
            "updatedAt": str(row[7]) if row[7] else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("获取命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.put("/{case_id}")
async def update_chart_case(case_id: str, payload: dict):
    """更新命例（名称、标签、出生信息）。"""
    if not ensure_table():
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
                    c["chartData"] = _build_chart_data(payload["birth_time"], payload["gender"])
            c["updatedAt"] = datetime.now().isoformat()
            _save_file_cases(cases)
            return {"status": "ok", "storage": "file"}
        raise HTTPException(status_code=404, detail="命例不存在")
    try:
        with _get_pool().connection() as conn:
            updates = []
            params = []
            if "name" in payload:
                updates.append("name = %s")
                params.append(payload["name"])
            if "tags" in payload:
                updates.append("tags = %s")
                params.append(payload["tags"])
            if "birth_time" in payload and "gender" in payload:
                birth_time = payload["birth_time"]
                gender = payload["gender"]
                updates.extend(["birth_time = %s", "gender = %s"])
                params.extend([birth_time, gender])
                if payload.get("regenerate_chart_data", True):
                    updates.append("chart_data = %s")
                    params.append(json.dumps(_build_chart_data(birth_time, gender)))
            if not updates:
                raise HTTPException(status_code=400, detail="无更新字段")
            updates.append("updated_at = NOW()")
            params.append(case_id)
            conn.execute(
                "UPDATE chart_cases SET {} WHERE id = %s".format(", ".join(updates)),
                tuple(params),
            )
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("更新命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.delete("/{case_id}")
async def delete_chart_case(case_id: str):
    """删除命例。"""
    if not ensure_table():
        cases = _load_file_cases()
        kept = [c for c in cases if c.get("id") != case_id]
        _save_file_cases(kept)
        return {"status": "ok", "storage": "file"}
    try:
        with _get_pool().connection() as conn:
            conn.execute("DELETE FROM chart_cases WHERE id = %s", (case_id,))
        return {"status": "ok"}
    except Exception as e:
        log.exception("删除命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/export/json")
async def export_chart_cases_json():
    """导出所有命例为 JSON 文件。"""
    if not ensure_table():
        cases = _load_file_cases()
        content = json.dumps({"version": 1, "exportedAt": datetime.now().isoformat(), "cases": cases}, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="xianzhi_chart_cases.json"'},
        )
    try:
        with _get_pool().connection() as conn:
            cur = conn.execute(
                "SELECT id, name, tags, birth_time, gender, chart_data, created_at, updated_at FROM chart_cases ORDER BY updated_at DESC"
            )
            cases = []
            for row in cur:
                chart_data = row[5] if isinstance(row[5], dict) else json.loads(row[5])
                cases.append({
                    "id": str(row[0]),
                    "name": row[1],
                    "tags": row[2] or [],
                    "birthTime": row[3],
                    "gender": row[4],
                    "chartData": chart_data,
                    "createdAt": str(row[6]) if row[6] else "",
                    "updatedAt": str(row[7]) if row[7] else "",
                })
        content = json.dumps({"version": 1, "exportedAt": datetime.now().isoformat(), "cases": cases}, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="xianzhi_chart_cases.json"'},
        )
    except Exception as e:
        log.exception("导出命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.post("/import/json")
async def import_chart_cases_json(payload: dict):
    """从 JSON 导入命例。

    payload: { cases: [...] }
    已存在相同 id 的命例会跳过，新增命例生成新 id。
    """
    cases = payload.get("cases") or []
    if not isinstance(cases, list):
        raise HTTPException(status_code=400, detail="cases 必须是数组")

    inserted = 0
    skipped = 0
    if not ensure_table():
        existing = _load_file_cases()
        existing_ids = {c.get("id") for c in existing}
        for c in cases:
            cid = c.get("id")
            if cid and cid in existing_ids:
                skipped += 1
                continue
            birth_time = (c.get("birthTime") or c.get("birth_time") or "").strip()
            gender = (c.get("gender") or "").strip()
            if not birth_time or not gender:
                continue
            name = (c.get("name") or "未命名命例").strip()
            tags = c.get("tags") or []
            chart_data = c.get("chartData") or c.get("chart_data") or _build_chart_data(birth_time, gender)
            existing.append(_new_file_case(name, birth_time, gender, tags, chart_data))
            inserted += 1
        _save_file_cases(existing)
        return {"inserted": inserted, "skipped": skipped, "storage": "file"}

    try:
        with _get_pool().connection() as conn:
            for c in cases:
                cid = c.get("id")
                if cid:
                    cur = conn.execute("SELECT 1 FROM chart_cases WHERE id = %s", (cid,))
                    if cur.fetchone():
                        skipped += 1
                        continue
                name = (c.get("name") or "未命名命例").strip()
                birth_time = (c.get("birthTime") or c.get("birth_time") or "").strip()
                gender = (c.get("gender") or "").strip()
                tags = c.get("tags") or []
                chart_data = c.get("chartData") or c.get("chart_data")
                if not birth_time or not gender:
                    continue
                if not chart_data:
                    chart_data = _build_chart_data(birth_time, gender)
                conn.execute(
                    """
                    INSERT INTO chart_cases (id, name, tags, birth_time, gender, chart_data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), name, tags, birth_time, gender, json.dumps(chart_data)),
                )
                inserted += 1
        return {"inserted": inserted, "skipped": skipped}
    except Exception as e:
        log.exception("导入命例失败")
        raise HTTPException(status_code=500, detail=client_error(e))
