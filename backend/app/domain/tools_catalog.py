"""领域层·排盘工具能力目录（单一事实源）。

带 birth_time/gender 参数的排盘工具名单：agent 会话内出生信息提取
（app.agent.xianzhi）与会话历史回溯（app.memory.postgres_memory）共用，
下沉到 domain 使 memory / db / rag / tools / agent 均可直连，消除 memory→tools 倒置。

bazi_hehun 参数为 *_a/*_b，不在此列。
"""

from __future__ import annotations

BAZI_BIRTH_TOOLS = frozenset({
    "bazi_chart",
    "bazi_full",
    "bazi_analysis",
    "bazi_dayun",
    "bazi_liunian",
    "bazi_liuyue",
    "bazi_liuri",
})
