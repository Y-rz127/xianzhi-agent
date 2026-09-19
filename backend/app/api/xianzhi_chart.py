"""先知排盘相关接口：缓存统计 / 岁运关系现算 / 直接排盘 / 八字反推。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
"""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Xianzhi"])

# 四柱缓存：关系判定只用到干支，点一次大运/流年/流月就全量重排太浪费
_PILLAR_CACHE: "OrderedDict[str, list]" = OrderedDict()
_PILLAR_CACHE_MAX = 64
_PILLAR_CACHE_LOCK = threading.Lock()

# /bazi/infer-dates 用的天干地支字集
_GAN = "甲乙丙丁戊己庚辛壬癸"
_ZHI = "子丑寅卯辰巳午未申酉戌亥"
# 干支合法性校验集合（/relations 校验岁运输入用）
_GAN_SET = set(_GAN)
_ZHI_SET = set(_ZHI)


@router.get("/cache_stats")
async def cache_stats():
    """获取排盘缓存统计。"""
    from app.tools.cache import bazi_cache

    return bazi_cache.stats()


def _pillars_cached(
    birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None
) -> list:
    """按出生信息缓存四柱（不含大运/流年等重活），供 /relations 反复调用。"""
    from app.domain.chart_builder import build_bazi_chart

    key = "|".join([birth_time, gender, str(sect), str(yun_sect), str(longitude)])
    with _PILLAR_CACHE_LOCK:
        hit = _PILLAR_CACHE.get(key)
        if hit is not None:
            _PILLAR_CACHE.move_to_end(key)
            return hit
    chart = build_bazi_chart(
        birth_time, gender, sect=sect, yun_sect=yun_sect, dayun_count=1, liunian_years=1, longitude=longitude
    )
    with _PILLAR_CACHE_LOCK:
        _PILLAR_CACHE[key] = chart.pillars
        while len(_PILLAR_CACHE) > _PILLAR_CACHE_MAX:
            _PILLAR_CACHE.popitem(last=False)
    return chart.pillars


@router.get("/relations")
async def get_relations(
    birth_time: str,
    gender: str,
    sect: int = 2,
    yun_sect: int = 1,
    longitude: float | None = None,
    dayun: str = "",
    xiaoyun: str = "",
    liunian: str = "",
    liuyue: str = "",
):
    """按指定的 大运/小运/流年/流月 计算「岁运分析 / 原局分析」。

    细盘页点选大运/流年/流月时调用：页面初次加载的 relations 只对应"今天"那一组，
    点别的年份不会变（旧行为）。这里按传入干支现算，缺省项自动跳过。

    入参：dayun/xiaoyun/liunian/liuyue 为干支（如 "壬申"），按 运柱→流年→流月 顺序叠加在原局上。
    **大运与小运互斥**：童限（未起运）没有大运，该段以当年小运论，前端传 xiaoyun 而不是 dayun；
    两个都传无法判断谁是运柱，直接 400。
    """
    if not any((dayun, xiaoyun, liunian, liuyue)):
        raise HTTPException(status_code=400, detail="至少需要 dayun / xiaoyun / liunian / liuyue 之一")
    if dayun and xiaoyun:
        raise HTTPException(
            status_code=400, detail="dayun 与 xiaoyun 互斥：童限没有大运，该段以当年小运论"
        )

    from app.domain.chart_builder import (
        parse_birth,
        parse_gender,
    )
    from app.domain.time_parse import _normalize_birth_time
    from app.domain.xipan import _build_relations

    try:
        # _normalize_birth_time 内部也会解析（农历/时辰/节日），失败同样抛 ValueError
        birth_time = _normalize_birth_time(birth_time)
        parse_birth(birth_time)
        parse_gender(gender)
    except ValueError as e:  # 与 /chart 一致：输入非法返回 400，不能 500
        raise HTTPException(status_code=400, detail=str(e))

    sui: list[str] = []
    # 顺序即语义（运柱 → 流年 → 流月）：_build_relations 按位置叠加，label 也按此拼接
    for label, value in (("dayun", dayun), ("xiaoyun", xiaoyun), ("liunian", liunian), ("liuyue", liuyue)):
        value = (value or "").strip()
        if not value:
            continue
        if len(value) != 2 or value[0] not in _GAN_SET or value[1] not in _ZHI_SET:
            raise HTTPException(status_code=400, detail=f"{label} 不是合法干支：{value}")
        sui.append(value)

    pillars = await asyncio.to_thread(_pillars_cached, birth_time, gender, sect, yun_sect, longitude)
    rel = await asyncio.to_thread(_build_relations, pillars, sui)
    return {"suiyun": rel["suiyun"], "yuanju": rel["yuanju"]}


def _compute_chart_payload(
    birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None
) -> dict:
    """同步排盘流水线（标准化 → 校验 → 排盘 → 格式化），输入非法抛 ValueError。"""
    from app.domain.chart_builder import (
        build_bazi_chart,
        chart_to_api_dict,
        parse_birth,
        parse_gender,
    )
    from app.domain.chart_format import (
        format_analysis_text,
        format_chart_text,
        format_dayun_text,
        format_liunian_text,
    )
    from app.domain.time_parse import _normalize_birth_time

    # 标准化出生时间（支持公历+时辰、农历、节日等格式，与 bazi_chart 工具入口一致）
    birth_time = _normalize_birth_time(birth_time)
    parse_birth(birth_time)
    parse_gender(gender)
    chart = build_bazi_chart(
        birth_time,
        gender,
        sect=sect,
        yun_sect=yun_sect,
        dayun_count=12,
        liunian_years=5,
        longitude=longitude,
        liunian_cover_dayun=True,
    )
    payload = chart_to_api_dict(chart)
    payload.update(
        {
            "chartText": format_chart_text(chart),
            "analysisText": format_analysis_text(chart, "整体命盘"),
            "dayunText": format_dayun_text(chart),
            "liunianText": format_liunian_text(chart),
        }
    )
    return payload


@router.get("/chart")
async def get_chart(
    birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, longitude: float | None = None
):
    """直接排盘，返回四柱/五行/大运/流年等结构化数据。

    Args:
        longitude: 出生地经度（用于真太阳时校正，可选）
    """
    from app.tools.cache import bazi_cache

    # 复用与聊天工具同一套 LRU：/chart 是全量重算的 CPU 密集路径，高频请求会抢 GIL 拖垮事件循环
    # key 追加经度（真太阳时校正会改变四柱）；None 与 0 是不同 key，语义正确
    cache_tool = f"chart_api:{longitude}"
    payload = bazi_cache.get(birth_time, gender, sect, yun_sect, cache_tool)
    if payload is not None:
        return payload
    try:
        # 排盘为同步重计算，放到线程池避免阻塞事件循环
        payload = await asyncio.to_thread(
            _compute_chart_payload, birth_time, gender, sect, yun_sect, longitude
        )
        bazi_cache.set(birth_time, gender, payload, sect, yun_sect, cache_tool)
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bazi/infer-dates")
async def infer_bazi_dates(payload: dict):
    """根据八字反推候选出生日期：用户只知八字、不知精确时间时调用。

    请求体: {"pillars": "甲申庚午壬申甲辰", "gender": "男", "top_n": 3}
    返回: {"pillars": "...", "candidates": [{"birth_time", "ganzhi", "shi_chen"}, ...]}
    """
    from app.domain.chart_format import find_birth_dates_from_pillars

    pillars = (payload.get("pillars") or "").strip()
    gender = (payload.get("gender") or "男").strip() or "男"
    top_n = int(payload.get("top_n") or 3)
    seq = [c for c in pillars if c in _GAN or c in _ZHI]
    if len(seq) < 8:
        raise HTTPException(status_code=400, detail="八字应为 4 个干支共 8 字，如 甲申庚午壬申甲辰")
    try:
        candidates = await asyncio.to_thread(find_birth_dates_from_pillars, pillars, gender, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pillars": pillars, "gender": gender, "candidates": candidates}
