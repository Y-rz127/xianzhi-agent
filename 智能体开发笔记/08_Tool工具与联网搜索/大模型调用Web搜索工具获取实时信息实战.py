# 【LLM联网搜索功能实战】：演示基于LangChain框架实现大模型调用Web搜索工具获取实时信息（如股价），并通过工具调用流程完成问答
import os
# 导入SearchApi相关的API封装（用于调用联网搜索接口）
from langchain_community.utilities import SearchApiAPIWrapper
# 导入工具调用相关的消息类（用于封装工具返回结果）
from langchain_core.messages import ToolMessage
# 导入提示词模板（用于构建大模型的输入提示）
from langchain_core.prompts import ChatPromptTemplate
# 导入RunnablePassthrough（用于链式调用中透传输入参数）
from langchain_core.runnables import RunnablePassthrough
# 导入工具装饰器（用于定义LangChain标准工具）
from langchain_core.tools import tool
# 导入OpenAI兼容的大模型客户端（用于调用通义千问等模型）
from langchain_openai import ChatOpenAI
# 导入SecretStr（用于安全存储API密钥）
from pydantic import SecretStr

# ====================== LangSmith 配置（可选，用于追踪链的执行过程） ======================
# 启用LangChain的追踪功能，便于调试和查看链的执行流程
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# LangSmith的API端点
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# LangSmith的API密钥（替换为自己的）
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
# 项目名称（用于在LangSmith中区分不同项目）
os.environ["LANGCHAIN_PROJECT"] = "agent_v1"

# ====================== 搜索工具配置 ======================
# 设置SearchApi的API密钥（替换为自己的有效密钥）
os.environ["SEARCHAPI_API_KEY"] = ""
# 实例化SearchApiWrapper对象，封装了搜索API的调用逻辑
search = SearchApiAPIWrapper()


# ====================== 定义工具函数 ======================
# 定义联网搜索工具：使用@tool装饰器标记为LangChain工具，name指定工具名，return_direct=True表示直接返回结果
@tool(name_or_callable="web_search", return_direct=True)
def web_search(search_query: str) -> str:
    """
    联网搜索工具：适用于获取实时信息、最新事件或未知领域知识的场景
    参数:
        search_query (str): 搜索关键字，如"寒武纪今天最新的股价"
    返回:
        str: 格式化后的搜索结果（包含来源标题和内容摘要）
    """
    try:
        # 调用SearchApi获取搜索结果（默认返回前几条结果）
        result = search.results(search_query)
        # 格式化搜索结果：提取organic_results（自然搜索结果），拼接标题和内容
        return "\n\n".join([f"来源:{res['title']}\n内容:{res['snippet']}" for res in result['organic_results']])
    except Exception as e:
        # 异常处理：搜索失败时返回友好提示
        return f"搜索失败：{str(e)}"


# 定义加法工具：演示非联网工具的定义方式，用于对比
@tool
def add(a: int, b: int) -> int:
    """
    加法计算工具：用于执行简单的整数加法运算
    参数:
        a (int): 加数1
        b (int): 加数2
    返回:
        int: a + b的计算结果
    """
    return a + b


# ====================== 初始化大模型 ======================
# 创建ChatOpenAI实例（兼容通义千问等OpenAI格式的模型）
model = ChatOpenAI(
    model="qwen-plus",  # 模型名称（通义千问增强版）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的兼容接口
    api_key=SecretStr(""),  # 通义千问的API密钥（安全存储为SecretStr）
    temperature=0.7  # 温度系数：控制回答的随机性，0.7为适中值
)

# ====================== 构建提示词模板 ======================
# 创建聊天提示词模板：包含系统提示和用户输入
prompt = ChatPromptTemplate.from_messages([
    # 系统提示：告诉大模型的角色和工具调用规则
    ("system", "你是一个AI助手，名字叫HideOnBoss，请根据用户输入的查询问题，必要时可以调用工具帮用户解答"),
    # 用户输入：{query}为占位符，运行时会替换为实际的用户查询
    ("human", "{query}"),
])

# ====================== 工具绑定与链构建 ======================
# 构建工具字典：将工具名和工具函数映射，便于后续调用
tool_dict = {"add": add, "web_search": web_search}
# 提取工具列表：从字典中获取所有工具函数，用于绑定给大模型
tools = [tool_dict[tool_name] for tool_name in tool_dict]

# 将大模型绑定工具：让模型具备调用指定工具的能力
llm_with_tool = model.bind_tools(tools)

# 构建运行链：
# 1. RunnablePassthrough() 透传用户输入的query参数
# 2. prompt 接收query并生成完整的提示词
# 3. llm_with_tool 接收提示词，判断是否调用工具并返回结果
chain = {"query": RunnablePassthrough()} | prompt | llm_with_tool

# ====================== 执行示例：查询寒武纪最新股价 ======================
# 用户查询：需要实时信息，模型会判断调用web_search工具
query = "寒武纪今天最新的股价是多少?"
# 调用链，获取模型的初始响应（可能包含工具调用指令）
resp = chain.invoke(query)
print(f"AI初始回复:{resp}\n")

# ====================== 处理工具调用逻辑 ======================
# 提取模型返回的工具调用指令（tool_calls为空则无需调用工具）
tool_calls = resp.tool_calls
# 构建历史消息：包含初始的提示词和模型的初始响应，用于后续上下文传递
history_message = prompt.invoke(query).to_messages()
history_message.append(resp)

# 判断是否需要调用工具
if len(tool_calls) <= 0:
    print(f"不需要调用工具，直接回答：{resp.content}")
else:
    print(f"需要调用工具，工具调用指令：{tool_calls}\n")
    print(f"当前历史消息：{history_message}\n")

    # 循环处理每个工具调用指令
    for tool_call in tool_calls:
        # 提取工具名称和调用参数
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args")
        print(f"开始调用工具：{tool_name}，参数：{tool_args}")

        # 调用对应的工具函数，获取工具输出
        tool_output = tool_dict[tool_name].invoke(tool_args)

        # 封装工具返回结果为ToolMessage（包含tool_call_id，用于关联调用）
        tool_response_message = ToolMessage(
            tool_call_id=tool_call.get("id"),  # 关联对应的工具调用ID
            content=tool_output,  # 工具返回的内容
            name=tool_name  # 工具名称
        )
        print(f"工具调用结果：{tool_output}\n")

        # 将工具返回结果添加到历史消息中，供模型后续回答使用
        history_message.append(tool_response_message)
        print(f"更新后的历史消息：{history_message}\n")

        # 再次调用模型，传入包含工具结果的历史消息，获取最终回答
        result = llm_with_tool.invoke(history_message)
        print(f"模型结合工具结果的最终回复：{result}")
        print(f"最终答案：{result.content}\n")
