# 该代码演示了基于LangChain框架搭建一个具备「网页实时搜索」和「数学计算」能力的智能体（Agent），可响应实时股票查询等需要外部数据或计算的需求
import os

# 从LangChain框架导入智能体相关核心模块
from langchain.agents import AgentType, initialize_agent
# 导入SearchApiAPIWrapper，用于对接SearchApi实现网页搜索功能
from langchain_community.utilities import SearchApiAPIWrapper
# 导入tool装饰器，用于定义智能体可调用的工具函数
from langchain_core.tools import tool
# 导入ChatOpenAI，用于实例化大语言模型（此处对接阿里通义千问）
from langchain_openai import ChatOpenAI
# 导入SecretStr，用于安全存储和传递API密钥（避免明文泄露风险）
from pydantic import SecretStr

# 配置LangChain Smith相关环境变量，用于追踪智能体的运行过程、日志和性能
# 启用LangChain v2版本追踪功能
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# LangChain Smith的API端点地址
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# LangChain Smith的API密钥（用于身份验证）
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
# 定义当前项目名称，方便在LangChain Smith后台分类查看
os.environ["LANGCHAIN_PROJECT"] = "agent_v1"

# 配置SearchApi的API密钥，用于调用网页搜索接口获取实时数据
os.environ["SEARCHAPI_API_KEY"] = ""
# 实例化SearchApiWrapper对象，封装了SearchApi的调用逻辑，提供便捷的搜索方法
search = SearchApiAPIWrapper()

# 定义网页搜索工具，使用@tool装饰器标记为LangChain智能体可调用的工具
# 参数1：工具名称"web_search"，供智能体识别；参数2：return_direct=True，表示直接返回工具执行结果给用户
@tool("web_search", return_direct=True)
def web_search(search_query: str) -> str:
    """
    工具功能描述（供智能体判断是否需要调用该工具）：
    当需要获取实时信息、最新事件或未知领域知识时使用，输入应为搜索关键字
    """
    try:
        # 调用SearchApiWrapper的results方法执行搜索，传入搜索关键字
        result = search.results(search_query)
        # 解析搜索结果中的有机结果（organic_results），提取标题和摘要并格式化拼接
        # 最终返回易读的结构化搜索结果
        return "\n\n".join([f"来源:{res['title']}\n内容:{res['snippet']}" for res in result['organic_results']])
    except Exception as e:
        # 捕获搜索过程中的异常（如网络错误、API密钥失效、无结果等），返回友好的错误提示
        return f"搜索失败：{e}"

# 定义数学计算工具，使用@tool装饰器标记为LangChain智能体可调用的工具
# 参数1：工具名称"math_calculator"，供智能体识别；参数2：return_direct=True，表示直接返回计算结果给用户
@tool("math_calculator", return_direct=True)
def math_calculator(expression: str) -> str:
    """
    工具功能描述（供智能体判断是否需要调用该工具）：
    用于计算数学公式，输入应为合法的数学表达式（如"1+2*3"、"sqrt(16)"等）
    """
    try:
        # 使用eval函数执行数学表达式计算（注意：生产环境中eval存在安全风险，需做输入校验）
        result = eval(expression)
        # 返回格式化的计算结果
        return f"计算结果为：{result}"
    except Exception as e:
        # 捕获计算过程中的异常（如表达式不合法、除零错误等），返回友好的错误提示
        return f"计算失败：{e}"

# 实例化大语言模型（LLM），此处对接阿里通义千问（qwen-plus），兼容OpenAI接口格式
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问plus版本）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里通义千问的兼容OpenAI接口地址
    api_key=SecretStr(""),  # 通义千问的API密钥，使用SecretStr安全存储
    temperature=0.7  # 模型生成内容的随机性（0~1），0.7表示兼顾逻辑性和一定的创造性
)

# 整理智能体可调用的工具列表，将定义好的两个工具放入列表供后续初始化智能体使用
tool_dict = [math_calculator, web_search]

# 初始化LangChain智能体，将模型、工具列表进行整合，构建具备决策能力的智能体链
agent_chain = initialize_agent(
    tools=tool_dict,  # 传入智能体可调用的工具列表
    llm=model,  # 传入实例化的大语言模型（作为智能体的"大脑"，负责决策和逻辑推理）
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,  # 指定智能体类型：零样本REACT描述型
    # 零样本：无需训练样本即可工作；REACT：通过"思考-行动-观察"循环完成任务
    verbose=True,  # 启用详细日志输出，可在控制台查看智能体的运行过程（思考、调用工具、结果等）
    handle_parsing_errors=True  # 启用解析错误处理，当工具返回结果解析失败时，自动进行容错处理
)

# 打印智能体的核心组件信息，用于清晰理解底层结构和调试
# 1. 打印智能体的LLM链（包含模型、提示词等核心组件）
print(f"agent_chain.agent.llm_chain：{agent_chain.agent.llm_chain}")
# 2. 打印LLM链中的提示词模板（智能体执行任务时的核心指令模板）
print(f"agent_chain.agent.llm_chain.prompt.template:{agent_chain.agent.llm_chain.prompt.template}")
# 3. 打印提示词模板中的输入变量（需要传入的参数，如任务输入、工具描述等）
print(f"agent_chain.agent.llm_chain.prompt.input_variables:{agent_chain.agent.llm_chain.prompt.input_variables}")

# 调用智能体的invoke方法，传入用户输入（查询比亚迪当日股票价格），执行任务并获取响应结果
# 由于查询的是实时股票数据，智能体会自动决策调用web_search工具获取最新信息
resp = agent_chain.invoke({"input": "比亚迪今天股票多少？"})

# 打印智能体的最终运算结果，供用户查看
print(f"运算结果:{resp}")
