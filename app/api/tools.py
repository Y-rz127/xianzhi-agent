"""命理工具接口（合婚）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.api.common import client_error
from app.logger import log
from app.tools.text_clean import clean_think_tags

router = APIRouter(prefix="/xianzhi", tags=["Tools"])


HEHUN_SYSTEM_PROMPT = """你是一位有几十年实战经验的八字合婚师傅，性格像一位见多识广的老朋友。

身份与能力：
- 精通四柱八字、五行生克、十神配婚、大运流年
- 熟悉传统合婚理论：年命纳音、日柱关系、五行互补、配偶星、桃花、刑冲合害
- 说话不绕弯子，有传统文化底蕴

说话风格（重要）：
- 像真人聊天，不要用表格、不要分太多层级标题、不要用 emoji 结尾
- 先一句话给总评（缘分深浅、合婚吉凶），再分2-4个关键点讲依据，最后给一条实在的建议
- 长度控制：3-6段，简洁有重点，不长篇大论
- 该幽默时幽默（比如调侃桃花旺、欢喜冤家），该严肃时严肃（比如刑冲、配偶星受损）
- 用"你"而不是"您"，自然口语化
- 不确定的事直说"这个要看具体大运流年"，不装懂、不绝对化
- 避免 AI 味重的表达：不要"总结一下""需要注意的是""好消息/需要注意"这种模板腔

回答原则：
- 基于系统提供的双方命盘事实进行分析，不要自行编造四柱
- 客观中立，引导理性看待，姻缘天定一半，人为一半
- 既指出缘分优势，也提醒潜在问题，不给绝对结论
- 最后给一句实在的建议，比如如何经营、何时结婚更合适等
"""


@router.get("/hehun")
async def hehun(birth_time_a: str, gender_a: str, birth_time_b: str, gender_b: str):
    """合婚分析。先调规则工具拿基础数据，再调 LLM 做综合解读。"""
    from fastapi import HTTPException
    from app.tools.bazi import bazi_hehun
    try:
        # 1. 规则层：排盘 + 五行互补评分（同步阻塞计算，放线程池避免卡住事件循环）
        base_result = await asyncio.to_thread(bazi_hehun.invoke, {
            "birth_time_a": birth_time_a, "gender_a": gender_a,
            "birth_time_b": birth_time_b, "gender_b": gender_b,
        })
        if base_result and base_result.startswith("合婚失败"):
            raise HTTPException(status_code=400, detail=base_result)

        # 2. LLM 层：基于规则结果做综合解读
        from app.api import state
        llm = state.get_chat_model()
        if llm is None:
            # 兜底：LLM 不可用时只返回规则结果
            return {"result": base_result}

        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=HEHUN_SYSTEM_PROMPT),
            HumanMessage(content=(
                "以下是系统根据双方出生时间自动排盘生成的合婚基础数据，"
                "请基于这些事实进行综合解读，给出缘分分析和合婚建议：\n\n"
                f"{base_result}"
            )),
        ]
        try:
            resp = await asyncio.to_thread(llm.invoke, messages)
            content = (getattr(resp, "content", "") or "").strip()
            # 过滤推理模型的 think 块
            content = clean_think_tags(content)
            if content:
                return {"result": content}
            return {"result": base_result}
        except Exception as e:
            log.warning("合婚 LLM 解读失败，返回规则结果: {}", e)
            return {"result": base_result}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("合婚分析失败")
        raise HTTPException(status_code=500, detail=client_error(e))


