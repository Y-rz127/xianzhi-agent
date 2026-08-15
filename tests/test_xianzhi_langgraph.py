"""R3 编排收敛专项测试：LangGraph 为唯一编排后端。

验证点：
- langgraph 为硬依赖：create_xianzhi_graph 必须返回可执行图（不再允许返回 None）
- XianzhiWorkflow.backend 恒为 langgraph，构建失败即抛错（不再降级 builtin）
- 图 state 支持 summary 字段透传（修复双后端漂移）
"""

from app.agent.workflow.xianzhi_workflow import XianzhiWorkflow
from app.agent.xianzhi_langgraph import XianzhiGraphState, create_xianzhi_graph


def test_create_xianzhi_graph_is_mandatory():
    """langgraph 为硬依赖，图必须构建成功且可执行。"""
    workflow = XianzhiWorkflow(chat_model=None)
    graph = create_xianzhi_graph(workflow)
    assert graph is not None
    assert hasattr(graph, "invoke")


def test_workflow_backend_is_langgraph_only():
    """backend 恒为 langgraph，不再存在 builtin 降级路径。"""
    workflow = XianzhiWorkflow(chat_model=None)
    assert workflow.backend == "langgraph"


def test_graph_state_supports_summary():
    """图状态字典包含 summary 字段（生成节点透传给 _build_messages）。"""
    assert "summary" in XianzhiGraphState.__annotations__
