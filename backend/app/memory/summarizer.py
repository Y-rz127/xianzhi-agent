"""会话增量摘要：聊天消息达到阈值后异步生成 ≤600 字摘要并落库。

从 app.agent.xianzhi 抽离：摘要只依赖 memory 接口（计数/读旧摘要/写新摘要）与
chat_model，与智能体实例状态解耦，避免 agent 类膨胀。
"""

from __future__ import annotations

import threading

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_throttle import llm_tag
from app.core.logger import log

# 每 6 轮对话（一问一答=1轮，约12条消息）触发一次增量摘要
_SUMMARY_TRIGGER_MESSAGES = 12
_SUMMARY_MAX_CHARS = 600

_SUMMARY_PROMPT = (
    "你是一个会话摘要助手。请根据【旧摘要】和【最近对话】，生成不超过 600 字的增量摘要。\n"
    "只保留以下事实，忽略闲聊、问候、天气、发牢骚、流水账、长文本等非命理内容：\n"
    "- 用户身份/人生事件：年龄、职业、婚姻、健康、已确认的断事结论；\n"
    '- 用户对之前分析的修正或反馈（如"上次说我身弱不对"）——必须保留，避免重复旧错；\n'
    '- 待确认事项（如"用户给了八字但未确认出生日期"）。\n'
    "合并同类项，丢弃过时或冗余信息，保持简洁。\n\n"
    "【旧摘要】\n{old_summary}\n\n"
    "【最近对话】\n{recent_text}\n\n"
    "请输出新摘要（不超过 600 字）："
)


def maybe_summarize(memory, chat_model, conversation_id: str, recent_messages: list) -> None:
    """消息增量达到阈值时，后台线程异步生成并落库摘要（失败不阻断主流程）。

    - 阈值判断与数据快照在主线程完成（线程安全）
    - LLM 调用与落库放 daemon 线程，避免拖慢用户响应
    - 增量累积：旧摘要 + 最近 12 条消息 → 新摘要
    """
    try:
        msg_count = memory.get_message_count(conversation_id)
        last_summary_count = memory.get_last_summary_count(conversation_id)
        if msg_count - last_summary_count < _SUMMARY_TRIGGER_MESSAGES:
            return

        # 主线程先取快照（避免线程内读共享状态）
        try:
            old_summary = memory.get_summary(conversation_id)
        except Exception as e:
            log.warning("获取会话摘要失败: {}", e)
            old_summary = ""
        recent_text = "\n".join(
            f"{m.__class__.__name__.replace('Message', '')}: {str(getattr(m, 'content', ''))[:300]}"
            for m in recent_messages[-_SUMMARY_TRIGGER_MESSAGES:]
            if str(getattr(m, "content", "")).strip()
        )

        def _run():
            """调用摘要模型，基于旧摘要与最近对话生成增量摘要。"""
            try:
                log.info("[摘要] 会话 {} 开始生成摘要...", conversation_id)
                prompt = _SUMMARY_PROMPT.format(old_summary=old_summary or "（无）", recent_text=recent_text)
                with llm_tag("summary"):
                    resp = chat_model.invoke(
                        [
                            SystemMessage(content="你是会话摘要助手，只输出摘要文本，不输出任何解释。"),
                            HumanMessage(content=prompt),
                        ]
                    )
                new_summary = (getattr(resp, "content", "") or "").strip()
                if new_summary and len(new_summary) > 10:
                    if len(new_summary) > _SUMMARY_MAX_CHARS:
                        new_summary = new_summary[:_SUMMARY_MAX_CHARS]
                    memory.save_summary(conversation_id, new_summary, msg_count)
                    log.info(
                        "[摘要] 会话 {} 已生成摘要 ({}字, 消息数={})",
                        conversation_id,
                        len(new_summary),
                        msg_count,
                    )
            except Exception as e:
                log.warning("会话摘要生成失败（后台线程）: {}", e)

        threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        log.warning("会话摘要触发失败: {}", e)