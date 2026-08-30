"""黄历子应用核心：组装领域计算，供 REST 路由与 Agent 工具共用。"""
from __future__ import annotations

import datetime

from app.domain.huangli_calc import (
    YI_JI_ITEMS,
    build_huangli_day,
    build_range_briefs,
    filter_zeji,
)

# build_range_briefs 等为有意再导出：routes 通过 huangli_app.* 统一访问，工具层同源复用
__all__ = ["YI_JI_ITEMS", "build_huangli_day", "build_range_briefs", "filter_zeji", "huangli_day", "zeji"]


def huangli_day(date: str = "") -> dict:
    """当日完整黄历，date 为空取今天。"""
    return build_huangli_day(date.strip() or datetime.date.today().isoformat())


def zeji(yi: str, start: str, end: str, avoid_chong: str = "") -> list[dict]:
    """择吉筛选，事项必须命中宜忌词表。"""
    item = (yi or "").strip()
    if item not in YI_JI_ITEMS:
        raise ValueError("不支持的择吉事项「{}」，请从词表中选择".format(item))
    return filter_zeji(item, start, end, avoid_chong=(avoid_chong or "").strip())
