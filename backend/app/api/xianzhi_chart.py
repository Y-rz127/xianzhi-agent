"""先知排盘相关接口：缓存统计 / 岁运关系现算 / 直接排盘 / 八字反推。

路由挂在 /xianzhi 前缀下（由 app.api.xianzhi 聚合），本模块自持 router。
"""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


def _build_chart_only(
    birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None
):
    """同步排盘（标准化 → 校验 → 排盘），输入非法抛 ValueError。终审应用前段。"""
    from app.domain.chart_builder import build_bazi_chart, parse_birth, parse_gender
    from app.domain.time_parse import _normalize_birth_time

    # 标准化出生时间（支持公历+时辰、农历、节日等格式，与 bazi_chart 工具入口一致）
    birth_time = _normalize_birth_time(birth_time)
    parse_birth(birth_time)
    parse_gender(gender)
    return build_bazi_chart(
        birth_time,
        gender,
        sect=sect,
        yun_sect=yun_sect,
        dayun_count=12,
        liunian_years=5,
        longitude=longitude,
        liunian_cover_dayun=True,
    )


def _format_chart_payload(chart) -> dict:
    """chart → API 载荷（结构化 + 四段文本）。终审应用后段：文本与 wuxing 同源。"""
    from app.agent.verdict import verdict_applied, verdict_five_gods, verdict_is_stale
    from app.domain.chart_builder import chart_to_api_dict
    from app.domain.chart_format import (
        format_analysis_text,
        format_chart_text,
        format_dayun_text,
        format_liunian_text,
    )

    payload = chart_to_api_dict(chart)
    payload.update(
        {
            "chartText": format_chart_text(chart),
            "analysisText": format_analysis_text(chart, "整体命盘"),
            "dayunText": format_dayun_text(chart),
            "liunianText": format_liunian_text(chart),
            # 供前端提示"终审版生成中，下拉刷新"：载荷里嵌着终审结论，
            # 前端必须能分辨手上这份是计算版还是终审版
            "verdict_applied": verdict_applied(chart),
            # 旧版终审顶替（版本已 bump、新版仍在后台判）：前端据此提示"旧版"，
            # 不能再报"已是最新终审版"（2026-10-22 用户实测到该误报）
            "verdict_stale": verdict_is_stale(chart),
            # 终审五神（用/喜/忌/仇/平）：命盘详情页在"喜忌用神"处逐条显示，
            # 只含判得出来的类别（缺项整键缺席，前端不显示空标签）；计算版为空对象
            "gods": verdict_five_gods(chart),
        }
    )
    return payload


def _compute_chart_payload(
    birth_time: str, gender: str, sect: int, yun_sect: int, longitude: float | None
) -> dict:
    """兼容入口：一次完成 build+format（不插终审）。

    线上 get_chart 已拆成 build → 终审 → format 三段；本函数保留给
    xianzhi.py 别名与测试（纯计算版，快照可重现，不依赖 LLM）。
    """
    return _format_chart_payload(_build_chart_only(birth_time, gender, sect, yun_sect, longitude))


@router.get("/chart")
async def get_chart(
    birth_time: str, gender: str, sect: int = 2, yun_sect: int = 1, longitude: float | None = None
):
    """直接排盘，返回四柱/五行/大运/流年等结构化数据。

    Args:
        longitude: 出生地经度（用于真太阳时校正，可选）
    """
    from app.agent.verdict import (
        ENGINE_VERSION,
        PROMPT_VERSION,
        chart_hash_for_input,
        chart_with_verdict_for_api,
        verdict_applied,
        verdict_cache_namespace,
        verdict_is_stale,
    )
    from app.tools.cache import bazi_cache

    # 复用与聊天工具同一套 LRU：/chart 是全量重算的 CPU 密集路径，高频请求会抢 GIL 拖垮事件循环。
    # key 追加经度（真太阳时校正会改变四柱）与引擎/提示词版本（终审口径变了旧载荷自然失效），
    # 以及终审命名空间 v/p —— payload 里嵌着终审结论，状态不参与 key 的话，一张盘先按
    # 计算版缓存过，后台补判落库后详情页也永远吐旧载荷（2026-10-11 用户实测到的问题）。
    try:
        # 指纹必须按**排盘口径**（校正后的出生时间）算，见 chart_hash_for_input 的注释：
        # 拿原始查询串算会与写侧（chart.birth.solar）错位，导致永远查不到裁决。
        chash = await asyncio.to_thread(chart_hash_for_input, birth_time, gender, longitude)
    except Exception:
        chash = ""
    # DB 查询放线程池：与排盘同理，别让一次连接等待卡住事件循环
    ns = await asyncio.to_thread(verdict_cache_namespace, chash)
    cache_tool = f"chart_api:{ns}:{longitude}:{ENGINE_VERSION}:{PROMPT_VERSION}"
    payload = bazi_cache.get(birth_time, gender, sect, yun_sect, cache_tool)
    if payload is not None:
        return payload
    try:
        # 排盘为同步重计算，放到线程池避免阻塞事件循环
        chart = await asyncio.to_thread(
            _build_chart_only, birth_time, gender, sect, yun_sect, longitude
        )
        # 终审：已有后台补判在跑就跳过 —— 不让用户再等一轮，也不重复烧 token
        chart = await chart_with_verdict_for_api(chart)
        payload = await asyncio.to_thread(_format_chart_payload, chart)
        # 按**实际生效状态**落缓存：v=同版本终审 / s=旧版终审顶替 / p=计算版。
        # s 必须单独占一个命名空间 —— 若把旧版当 v，新裁决落库后 key 不变，
        # 详情页下拉刷新也永远吐旧载荷（版本升级场景）。
        if verdict_is_stale(chart):
            applied = "s"
        else:
            applied = "v" if verdict_applied(chart) else "p"
        bazi_cache.set(
            birth_time,
            gender,
            payload,
            sect,
            yun_sect,
            f"chart_api:{applied}:{longitude}:{ENGINE_VERSION}:{PROMPT_VERSION}",
        )
        return payload
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ChartSaveRequest(BaseModel):
    """出生信息保存（小程序面板「保存并排盘」）入参。

    面板改动在点保存前只是草稿：只有本接口才会**按会话落库**并触发排盘/终审，
    这是"一次填写只算一份盘"的落点（此前面板 watch / 选城市都会各算一次）。
    """

    session_id: str = Field(..., description="会话 ID：出生信息与命盘快照都按会话落库")
    birth_time: str = Field(..., description="出生时间（公历/农历/时辰/节日格式均可，与 /chart 同一入口）")
    gender: str
    place: str = Field("", description="出生地；填了才做真太阳时校正，不填不校正")
    longitude: float | None = Field(None, description="出生地经度；与 place 同时给时以它为准")
    sect: int = 2
    yun_sect: int = 1
    token: str | None = Field(None, description="登录 token：有归属的会话需本人才能写")


def _resolve_save_longitude(body: "ChartSaveRequest") -> float:
    """出生地 → 经度：显式经度优先，其次地名匹配；都拿不到返回 0（不做真太阳时校正）。"""
    from app.agent.birth_parse import birth_place_to_longitude

    if body.longitude:
        return float(body.longitude)
    place = (body.place or "").strip()
    if place:
        return float(birth_place_to_longitude(place) or 0.0)
    return 0.0


def _chart_snapshot(chart, birth_time: str = "") -> dict:
    """会话命盘快照（`session_birth_info.chart_json`）。

    只存"重进会话要回显/审计的结论"，不存整份 payload（后者几十 KB 且可重算）：
    四柱 + 强弱/格局 + 喜忌 + 五神 + 终审状态。

    `birth_time` 传**用户输入侧**的（未做真太阳时校正的）标准写法：它是下次挂盘的入参，
    而 `chart.birth.solar` 在带经度时已被校正过（如 14:30→13:47），拿它当入参会二次校正。
    """
    from app.agent.verdict import (
        PROMPT_VERSION,
        verdict_applied,
        verdict_five_gods,
        verdict_is_stale,
    )
    from app.domain.analysis_calc import ENGINE_VERSION

    w = chart.wuxing
    return {
        "birth_time": birth_time or chart.birth.solar,
        "solar_corrected": chart.birth.solar,
        "gender": chart.birth.gender,
        "pillars": " ".join(p.ganzhi for p in chart.pillars),
        "day_master": w.day_master,
        "day_master_wuxing": w.day_master_wuxing,
        "strength": w.strength,
        "special_pattern": w.special_pattern,
        "useful_hint": w.useful_hint,
        "gods": verdict_five_gods(chart),
        "verdict_applied": verdict_applied(chart),
        "verdict_stale": verdict_is_stale(chart),
        "engine_version": ENGINE_VERSION,
        "prompt_version": PROMPT_VERSION,
    }


def _cache_chart_payload(
    payload: dict, chart, birth_time: str, gender: str, sect: int, yun_sect: int, longitude
) -> None:
    """把 payload 预热进 /chart 的缓存（key 与 `get_chart` 逐字同构，否则永远不命中）。"""
    from app.agent.verdict import PROMPT_VERSION, verdict_applied, verdict_is_stale
    from app.domain.analysis_calc import ENGINE_VERSION
    from app.tools.cache import bazi_cache

    if verdict_is_stale(chart):
        ns = "s"
    elif verdict_applied(chart):
        ns = "v"
    else:
        ns = "p"
    bazi_cache.set(
        birth_time,
        gender,
        payload,
        sect,
        yun_sect,
        f"chart_api:{ns}:{longitude}:{ENGINE_VERSION}:{PROMPT_VERSION}",
    )


@router.post("/chart/save")
async def save_chart(body: ChartSaveRequest):
    """保存出生信息并排盘（小程序面板「保存并排盘」）。

    与 `GET /chart` 只差两件事：**按会话落库**、**先落计算版再回写终审版**。
    - 出生地填了 → 按经度做真太阳时校正；没填 → 不校正（不沿用上一张盘的地点）；
    - 点了保存就落库（`session_birth_info` + 命盘快照），重进会话/换端都能恢复；
    - 终审在后台补判，跑完用回调**覆盖写入**快照并把终审版 payload 预热进缓存，
      前端下次下拉/重进拿到的就是终审版，不必干等。
    """
    from app.agent.verdict import (
        chart_with_cached_verdict,
        submit_verdict_background,
        verdict_applied,
        verdict_is_stale,
    )
    from app.api import data_access as repo
    from app.api._xianzhi_common import check_session_access
    from app.core.logger import log
    from app.domain.analysis_calc import ENGINE_VERSION
    from app.domain.time_parse import _normalize_birth_time
    from app.memory import postgres_memory as memory

    await check_session_access(body.session_id, body.token)

    longitude = _resolve_save_longitude(body)
    lon_param = longitude or None  # 与 /chart 的入参写法对齐：没经度就是 None
    try:
        # 入参口径：**未校正**的标准写法（农历/时辰在这里换算）。
        # 带经度时 chart.birth.solar 会被校正成真太阳时（如 14:30→13:47），
        # 那是排盘结果、不是入参 —— 拿它入库/做缓存键，下次挂盘会二次校正。
        birth_time = _normalize_birth_time(body.birth_time)
        chart = await asyncio.to_thread(
            _build_chart_only, birth_time, body.gender, body.sect, body.yun_sect, lon_param
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    gender = chart.birth.gender
    place = (body.place or "").strip()
    user_id = ""
    if body.token:
        user = await repo.get_by_token(body.token)
        if user:
            user_id = user["id"]

    # 1) 出生信息落库：会话级权威来源（get birth-info / 聊天挂盘都读它）
    # 这一步失败要明确告诉用户：没落库的话重进会话就查不到了，不能假装保存成功
    try:
        await asyncio.to_thread(
            memory.upsert_session_birth_info,
            body.session_id,
            birth_time,
            gender,
            place,
            longitude,
            user_id,
        )
    except Exception:
        log.exception("[chart/save] 出生信息落库失败 session={}", body.session_id)
        raise HTTPException(status_code=503, detail="出生信息保存失败，请稍后再试")

    # 2) 已有同版本裁决就直接应用（命中毫秒级）：省掉"先计算版再跳终审版"的闪动
    chart = await asyncio.to_thread(chart_with_cached_verdict, chart)
    if verdict_is_stale(chart):
        status = "stale"  # 旧版结论先顶上，下面照常派后台重判
    elif verdict_applied(chart):
        status = "verdict"
    else:
        status = "pending"
    payload = await asyncio.to_thread(_format_chart_payload, chart)

    # 3) 快照先落"当前拿得到的版本"，并预热缓存（前端立刻能拿到同一份）
    # 快照是"回显/审计"用的副本，写失败不影响本次排盘结果，只留日志
    try:
        await asyncio.to_thread(
            memory.set_session_chart,
            body.session_id,
            _chart_snapshot(chart, birth_time),
            ENGINE_VERSION,
            status,
        )
    except Exception as e:
        log.warning("[chart/save] 命盘快照落库失败（不影响本次排盘）: {}", e)
    _cache_chart_payload(payload, chart, birth_time, gender, body.sect, body.yun_sect, lon_param)

    # 4) 还没终审 → 后台补判；跑完覆盖写入快照 + 预热终审版 payload
    if status != "verdict":

        def _backfill(applied_chart) -> None:
            """回调跑在补判线程里（同步上下文）：DB 与缓存都用同步入口，别回主循环。"""
            try:
                final_status = "verdict" if verdict_applied(applied_chart) else "failed"
                memory.set_session_chart(
                    body.session_id,
                    _chart_snapshot(applied_chart, birth_time),
                    ENGINE_VERSION,
                    final_status,
                )
                if verdict_applied(applied_chart):
                    fresh = _format_chart_payload(applied_chart)
                    _cache_chart_payload(
                        fresh, applied_chart, birth_time, gender, body.sect, body.yun_sect, lon_param
                    )
                log.info(
                    "[chart/save] 终审回写 {} {} → {}", birth_time, gender, final_status
                )
            except Exception as e:  # 回写失败不能影响已返回的计算版
                log.warning("[chart/save] 终审回写失败: {}", e)

        submit_verdict_background(chart, on_done=_backfill)

    return {
        "birth_info": {"time": birth_time, "gender": gender, "place": place, "longitude": longitude},
        "chart": payload,
        "verdict_status": status,
        "verdict_applied": verdict_applied(chart),
    }


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
