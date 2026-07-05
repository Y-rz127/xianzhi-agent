# 导入 LangChain 核心工具相关的模块和异常类
from langchain_core.tools import StructuredTool, ToolException


# 定义搜索工具的核心函数
def search(query: str) -> str:
    """
    执行搜索查询的核心函数（模拟实现）

    参数:
        query (str): 需要搜索的查询字符串

    返回:
        str: 搜索结果（本示例中会抛出异常，不会正常返回）

    异常:
        ToolException: 模拟搜索过程中出现的业务异常
    """
    # 模拟搜索过程中发生异常
    # 使用 LangChain 提供的 ToolException 而非原生 Exception，便于工具层统一处理
    raise ToolException(f"搜索失败: {query}")


# 自定义异常处理函数（核心：统一处理工具执行过程中抛出的异常）
def _handel_tool_error(e: Exception) -> str:
    """
    工具异常的自定义处理函数

    参数:
        e (Exception): 工具执行过程中捕获到的异常对象

    返回:
        str: 格式化后的异常提示信息（友好返回给调用方）
    """
    # 可以在这里扩展更复杂的异常处理逻辑：
    # 1. 区分不同异常类型（如网络异常、参数异常）
    # 2. 记录异常日志
    # 3. 返回不同的提示语
    return f"搜索结果失败，请重试。具体错误信息：{str(e)}"


# 构建结构化工具（LangChain 标准方式）
search_tool = StructuredTool.from_function(
    name="search",  # 工具名称（唯一标识，用于 Agent 调用）
    func=search,  # 绑定工具的核心执行函数
    description="用于执行搜索查询，输入查询字符串即可获取相关结果",  # 工具描述（Agent 用于判断是否调用该工具）
    handle_tool_error=_handel_tool_error  # 绑定自定义异常处理函数
)

# 调用工具（模拟实际业务场景中的工具调用）
if __name__ == "__main__":
    # 调用工具并传入参数（参数需与 search 函数的入参匹配）
    resp = search_tool.invoke({"query": "如何使用langchain进行搜索"})
    # 打印处理后的结果（即使异常也会返回友好提示，而非直接崩溃）
    print("工具调用结果：", resp)
