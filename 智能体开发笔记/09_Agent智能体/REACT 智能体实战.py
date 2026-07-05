# 基于LangChain搭建具备「城市天气查询、天气适配活动推荐、网页实时股票搜索」能力的REACT智能体
import os
from langchain_openai import ChatOpenAI
from langchain.tools import tool  # 导入tool装饰器，用于定义智能体可调用工具
from langchain_community.utilities import SearchApiAPIWrapper  # 导入SearchApi封装类，实现网页搜索
from langchain_core.prompts import PromptTemplate  # 导入PromptTemplate，用于自定义REACT提示词模板
from langchain.agents import create_react_agent, AgentExecutor  # 导入REACT智能体创建与执行器类
from langchain import hub  # 导入hub（虽未直接使用，保留用于后续对接官方提示词仓库）
from pydantic import SecretStr  # 导入SecretStr，用于安全存储API密钥

# 配置LangChain Smith环境变量，用于追踪智能体运行轨迹、日志和性能指标
# 启用v2版本追踪功能，支持更详细的运行数据采集
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# LangChain Smith的官方API端点地址，用于上传运行数据
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# LangChain Smith的API密钥，用于身份验证（确保只有授权用户能上传/查看数据）
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
# 定义当前项目名称，方便在LangChain Smith后台分类管理和查询
os.environ["LANGCHAIN_PROJECT"] = "agent_v1"

# 配置SearchApi的API密钥，用于调用网页搜索接口获取实时数据（如腾讯股票价格）
os.environ["SEARCHAPI_API_KEY"] = ""

# 实例化SearchApiWrapper对象，封装了SearchApi的调用逻辑，提供便捷的results()搜索方法
# 后续web_search工具将通过该对象执行实际的网页搜索请求
search = SearchApiAPIWrapper()

# 定义天气查询工具，使用@tool装饰器标记为LangChain智能体可调用工具
# 入参：city（城市名称），返回值：格式化的天气信息
@tool
def get_weather(city: str) -> str:
    """
    工具功能描述（供REACT智能体判断是否调用）：获取指定城市的当前天气信息（模拟固定数据）
    参数说明：city - 城市名称（如"北京"、"上海"，仅支持预设城市列表）
    """
    # 模拟天气数据集，实际生产环境可对接气象API（如中国天气网、和风天气等）
    weather_data = {
        "北京": "晴, 25℃",
        "上海": "雨, 20℃",
        "广州": "多云, 28℃",
        "深圳": "晴, 27℃",
        "杭州": "多云, 23℃",
        "成都": "雨, 18℃"
    }
    # 从模拟数据中获取指定城市天气，无匹配城市时返回友好提示
    return weather_data.get(city, "暂不支持该城市的天气查询")

# 定义活动推荐工具，使用@tool装饰器标记为LangChain智能体可调用工具
# 入参：weather（天气信息），返回值：对应的活动推荐内容
@tool
def recommend_activity(weather: str) -> str:
    """
    工具功能描述（供REACT智能体判断是否调用）：根据输入的天气信息推荐合适的出行活动
    参数说明：weather - 天气描述字符串（如"晴, 25℃"、"雨, 20℃"）
    """
    # 根据天气关键词进行分支判断，推荐对应场景的活动
    if "雨" in weather:
        return "推荐室内活动: 博物馆参观、美术馆观展、咖啡厅阅读、商场购物。"
    elif "晴" in weather:
        return "推荐户外活动: 公园骑行、郊游野餐、登山徒步、户外运动。"
    else:  # 多云、阴等其他天气
        return "推荐一般活动: 城市观光、美食探索、文化体验。"

# 定义网页搜索工具，指定工具名称"web_search"，设置return_direct=True直接返回结果
@tool("web_search", return_direct=True)
def web_search(query: str) -> str:
    """
    工具功能描述（供REACT智能体判断是否调用）：
    当需要获取实时信息、最新事件或未知领域知识时使用（如股票价格、实时新闻等），输入应为搜索关键词
    """
    try:
        # 调用SearchApiWrapper的results方法执行搜索，num=3指定返回3条结果
        results = search.results(query, num=3)
        # 解析搜索结果中的有机结果（organic_results），提取前3条的标题和摘要
        # 格式化拼接后返回，提升结果的可读性和结构化
        return "\n\n".join([
            f"来源: {res['title']}\n内容: {res['snippet']}"
            for res in results['organic_results'][:3]
        ])
    except Exception as e:
        # 捕获搜索过程中的异常（如API密钥失效、网络错误、无搜索结果等）
        return f"搜索失败: {str(e)}"

# 整合所有工具形成工具列表，供智能体初始化时调用
# 智能体将基于每个工具的功能描述，决策何时调用哪个工具
tools = [get_weather, recommend_activity, web_search]

# 实例化大语言模型（LLM），对接阿里通义千问qwen-plus（兼容OpenAI接口格式）
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问增强版，具备较强的逻辑推理和工具调用能力）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 通义千问兼容OpenAI接口的端点地址
    api_key=SecretStr(""),  # 通义千问API密钥，使用SecretStr安全存储（避免明文泄露）
    temperature=0.7)  # 模型生成内容的随机性（0~1），0.7兼顾逻辑性和一定的灵活度

# 定义REACT智能体的提示词模板，严格遵循REACT的「思考-行动-观察」循环格式
# 该模板是REACT智能体运行的核心指引，规定了智能体的行为逻辑和输出格式
template = """
Answer the following questions as best you can. You have access to the following tools:
{tools}  # 占位符：将自动填充所有工具的名称和功能描述
Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do  # 思考：判断是否需要调用工具、调用哪个工具
Action: the action to take, should be one of [{tool_names}]  # 行动：指定要调用的工具名称（必须在工具列表中）
Action Input: the input to the action  # 行动输入：传递给工具的入参
Observation: the result of the action  # 观察：接收工具执行后的返回结果
... (this Thought/Action/Action Input/Observation can repeat N times)  # 可循环多次，完成复杂任务
Thought: I now know the final answer  # 最终思考：确认已获取足够信息，可得出最终答案
Final Answer: the final answer to the original input question  # 最终答案：返回给用户的完整结果

Begin!  # 启动指令，提示智能体开始执行任务
Question: {input}  # 占位符：接收用户传入的查询输入
Thought:{agent_scratchpad}  # 占位符：存储智能体的思考过程、行动记录和中间结果（不可删除）
"""

# 基于自定义模板创建PromptTemplate对象，自动识别并绑定模板中的占位符变量
prompt = PromptTemplate.from_template(template)

# 创建REACT智能体，整合模型、工具和提示词模板，具备「思考-行动-观察」的循环决策能力
agent = create_react_agent(
    llm=model,  # 传入实例化的大语言模型（作为智能体的"大脑"，负责逻辑推理和工具决策）
    tools=tools,  # 传入智能体可调用的工具列表
    prompt=prompt  # 传入自定义的REACT提示词模板，规定智能体的运行格式和逻辑
)

# 创建智能体执行器，负责调度智能体运行、处理工具调用流程、返回最终结果
agent_executor = AgentExecutor(
    agent=agent,  # 传入已创建的REACT智能体
    tools=tools,  # 传入工具列表（与创建智能体时保持一致）
    verbose=True,  # 启用详细日志输出，可在控制台查看智能体的完整运行流程（思考、行动、输入、观察等）
    return_intermediate_steps=True,  # 启用中间步骤返回，最终结果中包含所有工具调用记录和中间数据（方便调试和追溯）
    handle_parsing_errors="log_and_continue"  # 优化：添加解析错误处理策略，出错时记录日志并继续执行，提升鲁棒性
)

# 调用智能体执行器，传入用户复合任务请求，执行多步骤任务处理
# 用户请求包含2个子任务：1. 基于北京天气推荐三天出行活动 2. 查询腾讯最新股票价格
resp = agent_executor.invoke({"input":"我在北京玩三天，根据天气推荐活动，顺便查询腾讯的股票价格是多少?"})

# 打印完整返回结果，包含最终回复和中间执行步骤
print("=" * 100)
print("完整返回结果（含最终回复+中间步骤）：")
print("=" * 100)
print(resp)
