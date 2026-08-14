"""命盘 JSON（chart_data）摘要提取，DB 层与 API 层共用。"""
from __future__ import annotations

from typing import Any


def extract_bazi_brief(chart_data: Any) -> str | None:
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
