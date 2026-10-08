"""命理报告生成提示（tools 层随使用者归位）。

报告提示词仅被 app.tools.report_generator 消费，故不放在 agent 人设提示里，
下沉本模块消除 report_generator → agent.prompts 的倒置依赖。
COMPLIANCE_REDLINES 为 ReAct / Workflow 全局共享的合规红线，由
app.agent.prompts 从这个单一事实源 re-export，并在本报告 system 提示内嵌。
"""

from __future__ import annotations

COMPLIANCE_REDLINES = """【合规红线 · 硬性，违反即作废】
- 不指导赌博、投机、荐股、"必赢"类话术；
- 不提供堕胎择时；
- 涉及重病、牢狱等凶险信息，优先劝导就医 / 找律师，不放大恐慌。"""

# 薄 system 扩充为人设基座 + 合规
REPORT_SYSTEM_PROMPT = f"""你是先知，一位精通八字命理的预测师。请基于下方【四柱排盘】【五行十神分析】【大运信息】给出的确定数据客观分析，
不夸大、不恐吓、不绝对化，末尾提醒用户理性看待命理。
{COMPLIANCE_REDLINES}"""

# 命理报告 human prompt 模板（占位符：birth_time/gender/chart_text/analysis_text/dayun_text/sections_text）
REPORT_PROMPT_TEMPLATE = """请根据以下命盘信息，为用户生成一份结构化八字命理报告。

用户出生时间：{birth_time}
性别：{gender}

【四柱排盘】
{chart_text}

【五行十神分析】
{analysis_text}

【大运信息】
{dayun_text}

请生成以下章节，每个章节用 ## 标题 分隔：
{sections_text}

要求：
- 严格基于上面三段给定数据，不得自行推算、补充或改写任何干支/大运事实。
- 客观分析、用语平和、不绝对化、不制造焦虑；重大健康/官非提示优先建议现实求助。
- 每章言之有物、紧贴该章主题（命盘总览/事业/财运/感情/健康/大运），避免空话堆字数。
- 使用 Markdown 格式（列表、加粗、适当小标题均可）。
- 报告末尾用一段简短文字提醒：命理为趋势参考，决策仍需结合自身努力与现实情况。

直接输出报告正文，不要包含额外的开场白。"""
