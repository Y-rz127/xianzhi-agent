"""验证 ReAct 路径修复：不依赖真实 LLM，直接构造 Xianzhi Agent 状态。"""
import sys
import os
sys.path.insert(0, r'c:\MyProjects\xianzhi-agent')

from unittest.mock import patch, MagicMock
from app.agent.xianzhi import Xianzhi


def test_bazi_pending_blocks_chitchat():
    """场景1：用户给了八字+性别（无完整出生时间），_bazi_pending 应阻止闲聊短路。"""
    print("=== 测试 1: 八字+性别 → 不应走闲聊短路 ===")

    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])

        # 模拟 mount_chart_context 设置 _bazi_pending
        agent._bazi_pending = {
            "pillars": "戊戌辛酉壬寅甲辰",
            "gender": "男",
            "candidates": [
                {"birth_time": "1992-09-22 08:00", "ganzhi": "壬申 戊申 壬午 壬寅", "shi_chen": "辰时"},
                {"birth_time": "1958-09-22 08:00", "ganzhi": "戊戌 辛酉 壬寅 甲辰", "shi_chen": "辰时"},
            ],
        }

        result = agent._is_chitchat("我的八字是戊戌辛酉壬寅甲辰，男命，能给我看看盘吗？")
        assert result is False, f"期望 _is_chitchat 返回 False（走 ReAct），实际 {result}"
        print("  ✓ _is_chitchat 在 _bazi_pending 时返回 False（不会走闲聊短路）")


def test_bazi_pending_survives_reset():
    """场景2：reset() 不应清空 _bazi_pending，候选必须能跨 turn 解析。"""
    print("=== 测试 2: reset() 保留 _bazi_pending ===")

    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])

        pending = {
            "pillars": "戊戌辛酉壬寅甲辰",
            "gender": "男",
            "candidates": [{"birth_time": "1992-09-22 08:00", "ganzhi": "...", "shi_chen": "辰时"}],
        }
        agent._bazi_pending = pending

        # 模拟 turn 2 开始
        agent.reset()

        assert agent._bazi_pending is not None, "reset() 不应清空 _bazi_pending"
        assert agent._bazi_pending == pending, "_bazi_pending 应原样保留"
        print("  ✓ reset() 后 _bazi_pending 仍保留，下一轮可正常解析选择")

        # 验证 _resolve_bazi_selection 仍能工作
        bt = agent._resolve_bazi_selection("第一个", pending)
        assert bt == "1992-09-22 08:00", f"期望解析出 1992-09-22 08:00，实际 {bt}"
        print("  ✓ _resolve_bazi_selection('第一个') 仍能命中候选")

        bt2 = agent._resolve_bazi_selection("1992年", pending)
        assert bt2 == "1992-09-22 08:00", f"期望解析出 1992-09-22 08:00，实际 {bt2}"
        print("  ✓ _resolve_bazi_selection('1992年') 仍能命中候选")


def test_normal_chitchat_still_works():
    """场景3：纯闲聊（无八字、无出生信息、无_bazi_pending）仍走闲聊短路。"""
    print("=== 测试 3: 纯闲聊仍走闲聊短路 ===")

    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])

        agent._bazi_pending = None  # 无候选

        result = agent._is_chitchat("哈哈，你好")
        assert result is True, f"期望 _is_chitchat 返回 True，实际 {result}"
        print("  ✓ '哈哈，你好' 仍被识别为闲聊，走短路逻辑")


def test_conversation_switch_clears_pending():
    """场景4：切换会话时 _bazi_pending 必须清空，避免跨会话污染。"""
    print("=== 测试 4: 切换会话清空 _bazi_pending ===")

    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=MagicMock(), local_tools=[])

        agent._bazi_pending = {"pillars": "...", "gender": "男", "candidates": []}
        agent._conversation_id = "conv-1"
        agent.set_conversation_id("conv-2")

        assert agent._bazi_pending is None, "切换会话应清空 _bazi_pending"
        print("  ✓ 切换会话后 _bazi_pending 被清空")


if __name__ == "__main__":
    test_bazi_pending_blocks_chitchat()
    test_bazi_pending_survives_reset()
    test_normal_chitchat_still_works()
    test_conversation_switch_clears_pending()
    print("\n✅ 全部测试通过")
