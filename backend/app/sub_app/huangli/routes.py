"""每日黄历相关接口（只读，鉴权/限流由全局中间件处理）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.common import client_error
from app.core.logger import log
from app.domain.huangli_calc import YI_JI_ITEMS
from app.sub_app.huangli import huangli_app

router = APIRouter(prefix="/huangli", tags=["HuangLi"])


@router.get("/day")
async def huangli_day(date: str = ""):
    """当日完整黄历，date 省略取今天，支持 1900-2100 年任意日期。"""
    try:
        return huangli_app.huangli_day(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("黄历查询失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/range")
async def huangli_range(start: str, end: str):
    """月视图轻量简报，区间上限 31 天。"""
    try:
        return {"days": huangli_app.build_range_briefs(start, end)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("黄历区间查询失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/zeji")
async def huangli_zeji(yi: str, start: str, end: str, avoid_chong: str = ""):
    """择吉：筛选宜含目标事项的日子，吉神加星排序，可避冲生肖。"""
    try:
        return {"yi": yi, "days": huangli_app.zeji(yi, start, end, avoid_chong)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("择吉查询失败")
        raise HTTPException(status_code=500, detail=client_error(e))


@router.get("/items")
async def huangli_items():
    """宜忌事项词表，供择吉下拉。"""
    return {"items": list(YI_JI_ITEMS)}
