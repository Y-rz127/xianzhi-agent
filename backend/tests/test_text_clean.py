"""验证 LLM 输出后处理：用户输入边界标记剥离（strip_user_input_boundary）。

回归背景：闲聊短路路径(_chitchat_reply)此前未剥离模型回显的
`--- USER INPUT BEGIN/END ---` 边界块，导致用户看到内部标记（如截图"hello"被回显成
`--- USER INPUT BEGIN ---\nhello\n请正面回应，简短直接。\n--- USER INPUT END ---`）。
Workflow 路径早已在 invoke() 里剥离，本次将同一防护统一到 text_clean.strip_user_input_boundary，
并在聊短路路径一并调用。
"""
import sys

sys.path.insert(0, r"c:\MyProjects\xianzhi-agent")

from unittest.mock import MagicMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent.xianzhi import Xianzhi
from app.tools.text_clean import strip_user_input_boundary


def test_strip_removes_whole_echoed_block():
    content = "--- USER INPUT BEGIN ---\nhello\n请正面回应，简短直接。\n--- USER INPUT END ---"
    assert strip_user_input_boundary(content) == ""


def test_strip_keeps_real_reply_before_echo():
    content = "你好呀，我在的。\n--- USER INPUT BEGIN ---\nhello\n--- USER INPUT END ---"
    assert strip_user_input_boundary(content) == "你好呀，我在的。"


def test_strip_keeps_real_reply_after_echo():
    content = "--- USER INPUT BEGIN ---\nhello\n--- USER INPUT END ---\n\n你好呀，我在的。"
    assert strip_user_input_boundary(content) == "你好呀，我在的。"


def test_strip_empty_and_plain_content_noop():
    assert strip_user_input_boundary("") == ""
    assert strip_user_input_boundary("你好") == "你好"


def test_chitchat_path_hides_boundary_markers():
    """闲聊短路路径必须把模型回显的边界标记剥干净，不泄漏给用户。"""
    echo = "--- USER INPUT BEGIN ---\nhello\n请正面回应，简短直接。\n--- USER INPUT END ---"
    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=FakeListChatModel(responses=[echo]), local_tools=[])
        agent._bazi_pending = None
        reply = agent._chitchat_reply("hello")
        assert "USER INPUT" not in reply, f"内部标记泄漏: {reply!r}"


def test_chitchat_path_keeps_real_reply():
    """存在真实回答时，只剥边界块，保留正文。"""
    echo = "--- USER INPUT BEGIN ---\nhello\n--- USER INPUT END ---\n你好呀，我在的。"
    with patch("app.agent.xianzhi.create_chat_memory") as m1, \
         patch("app.agent.xianzhi.XianzhiWorkflow") as m2:
        m1.return_value = MagicMock()
        m2.return_value = MagicMock()
        agent = Xianzhi(chat_model=FakeListChatModel(responses=[echo]), local_tools=[])
        agent._bazi_pending = None
        reply = agent._chitchat_reply("hello")
        assert reply == "你好呀，我在的。", repr(reply)


if __name__ == "__main__":
    test_strip_removes_whole_echoed_block()
    test_strip_keeps_real_reply_before_echo()
    test_strip_keeps_real_reply_after_echo()
    test_strip_empty_and_plain_content_noop()
    test_chitchat_path_hides_boundary_markers()
    test_chitchat_path_keeps_real_reply()
    print("ALL text_clean tests passed")
