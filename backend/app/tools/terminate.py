"""终止工具（对应 Java TerminateTool）。"""
from langchain_core.tools import tool


@tool
def do_terminate() -> str:
    """任务完成时调用此工具结束交互。"""
    return "TERMINATE"


terminate_tools = [do_terminate]
