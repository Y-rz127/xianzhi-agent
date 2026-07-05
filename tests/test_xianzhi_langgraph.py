from app.agent.xianzhi_langgraph import create_xianzhi_graph
from app.agent.xianzhi_workflow import XianzhiWorkflow


def test_create_xianzhi_graph_is_optional():
    workflow = XianzhiWorkflow(chat_model=None)
    graph = create_xianzhi_graph(workflow)

    # In minimal environments langgraph may be absent; production installs it
    # through requirements.txt. Either way this call must not raise.
    assert graph is None or hasattr(graph, "invoke")
