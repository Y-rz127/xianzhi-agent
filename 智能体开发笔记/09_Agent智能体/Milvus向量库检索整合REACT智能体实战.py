# LangChain综合实战：搭建具备「Milvus向量库检索」和「网页实时搜索」能力的REACT智能体，解决Milvus相关专业查询任务
import os

# 导入阿里通义千问嵌入模型，用于将文本转换为向量（适配Milvus向量存储）
from langchain_community.embeddings import DashScopeEmbeddings
# 导入创建检索器工具的方法，将Milvus检索器封装为LangChain智能体可调用工具
from langchain_core.tools import create_retriever_tool
# 导入Milvus向量存储模块，用于构建向量数据库、存储和检索文本向量
from langchain_milvus import Milvus
# 导入ChatOpenAI，用于实例化大语言模型（对接阿里通义千问，兼容OpenAI接口）
from langchain_openai import ChatOpenAI
# 导入tool装饰器，用于定义自定义工具（网页搜索）
from langchain.tools import tool
# 导入SearchApiAPIWrapper，用于对接网页搜索API获取实时信息（如Milvus最新版本、GitHub教程）
from langchain_community.utilities import SearchApiAPIWrapper
# 导入提示词模板类，用于构建REACT智能体的运行格式模板
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
# 导入REACT智能体和工具调用智能体的创建方法、智能体执行器
from langchain.agents import create_react_agent, AgentExecutor, create_tool_calling_agent
# 导入LangChain hub，用于对接官方提示词仓库（虽未直接使用，保留用于后续优化）
from langchain import hub
# 导入SecretStr，用于安全存储和传递API密钥（避免明文泄露风险）
from pydantic import SecretStr

# 配置LangChain Smith环境变量，用于追踪智能体的完整运行轨迹、日志和性能指标
# 启用v2版本追踪功能，支持更详细的运行数据采集和后台可视化查看
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# LangChain Smith的官方API端点地址，用于上传智能体运行数据
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# LangChain Smith的API密钥，用于身份验证（确保只有授权用户能上传/查看运行数据）
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
# 定义当前项目名称，方便在LangChain Smith后台分类管理、查询和对比不同版本智能体
os.environ["LANGCHAIN_PROJECT"] = "llm_agent_v1"

# 配置SearchApi的API密钥，用于调用网页搜索接口获取实时数据（如Milvus最新版本、GitHub教程链接）
os.environ["SEARCHAPI_API_KEY"] = ""

# 实例化SearchApiWrapper对象，封装了SearchApi的调用逻辑，提供便捷的results()搜索方法
# 后续web_search工具将通过该对象执行实际的网页实时搜索请求
search = SearchApiAPIWrapper()

# 实例化阿里通义千问嵌入模型（DashScopeEmbeddings），用于文本向量化处理
# 嵌入模型的核心作用：将自然语言文本转换为计算机可识别的向量数据，供Milvus向量库存储和检索
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定使用通义千问第二代通用文本嵌入模型，具备更好的语义表征能力
    max_retries=3,  # 设置请求重试次数，提升接口调用的稳定性（网络波动时自动重试）
    dashscope_api_key="",  # 通义千问API密钥，用于嵌入模型接口调用
)

# 实例化Milvus向量存储对象，构建本地/远程向量数据库，用于存储和检索文本向量数据
vector_storage = Milvus(
    embedding_function=embeddings,  # 绑定嵌入模型，用于自动将文本转换为向量
    collection_name="doc_qa_db",  # 定义Milvus中的集合名称（相当于数据库中的表名）
    connection_args={"uri": "http://192.168.64.137:19530"},  # Milvus服务连接参数，指定服务地址和端口
    drop_old=True  # 设置为True：如果集合已存在，先删除旧集合再创建新集合（方便测试和重置）
)

# 将Milvus向量存储转换为检索器（Retriever），具备相似性查询能力
# 检索器的核心作用：接收查询文本，返回Milvus中语义最相似的文本结果
retriever = vector_storage.as_retriever()

# 将Milvus检索器封装为LangChain智能体可直接调用的工具
# 使智能体能够通过工具调用的方式，查询Milvus向量库中的相关信息
tool_retriever = create_retriever_tool(
    retriever,  # 绑定Milvus检索器，作为工具的核心执行逻辑
    "milvs_retriever",  # 工具名称（供REACT智能体识别和调用，注意：此处拼写为milvs_retriever，与Milvus一致）
    "搜索有关Milvus的信息。对于任何有关Milvus的问题，你必须使用这个工具"  # 工具功能描述（供智能体判断是否需要调用）
)

# 实例化大语言模型（LLM），对接阿里通义千问qwen-plus（兼容OpenAI接口格式）
# 模型作为智能体的"大脑"，负责逻辑推理、工具调用决策和最终结果整合
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问增强版，具备较强的专业逻辑推理和工具调用能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 通义千问兼容OpenAI接口的端点地址
    api_key=SecretStr(""),  # 通义千问API密钥，使用SecretStr安全存储（避免明文泄露）
    temperature=0.7  # 模型生成内容的随机性（0~1），0.7兼顾逻辑性和一定的灵活度，适合专业查询任务
)

# 定义网页实时搜索工具，指定工具名称"web_search"，设置return_direct=True直接返回搜索结果
@tool("web_search", return_direct=True)
def web_search(query: str) -> str:
    """
    工具功能描述（供REACT智能体判断是否需要调用）：
    当需要获取实时信息、最新版本、官方教程、对比数据等动态更新内容时使用，输入应为搜索关键词
    （例如：Milvus最新版本、Milvus LangChain 整合教程、Milvus vs Faiss 优缺点）
    """
    try:
        # 调用SearchApiWrapper的results方法执行网页搜索，num=3指定返回前3条核心结果
        results = search.results(query, num=3)
        # 解析搜索结果中的有机结果（organic_results），提取标题和摘要并格式化拼接
        # 最终返回结构化、易读的搜索结果，方便智能体整合和输出
        return "\n\n".join([
            f"来源: {res['title']}\n内容: {res['snippet']}"
            for res in results['organic_results'][:3]
        ])
    except Exception as e:
        # 捕获搜索过程中的异常（如API密钥失效、网络错误、无搜索结果等），返回友好错误提示
        return f"搜索失败: {str(e)}"

# 整合所有工具形成工具列表，供REACT智能体初始化时调用
# 智能体将基于每个工具的功能描述，决策何时调用哪个工具（Milvus检索/网页搜索）
tools = [web_search, tool_retriever]

# 注释：保留工具调用型智能体的提示词模板（备用），当前实战使用REACT智能体模板
# prompt = ChatPromptTemplate.from_messages([
#     ("system", "你是一个 个人AI助手，必要时可以调用工具函数帮助用户解决问题"),
#     ("human", "我叫老王，经常出差，喜欢性价比的按摩，身份证号是4444144444"),
#     ("human", "{input}"),
#     ("placeholder", "{agent_scratchpad}"),
# ])

# 构建REACT智能体的提示词模板，严格遵循REACT的「思考-行动-观察」循环格式
# 该模板是智能体运行的核心指引，规定了智能体的行为逻辑和输出格式要求
prompt = PromptTemplate.from_template('''Answer the following questions as best you can. You have access to this topic
    {tools}  # 占位符：自动填充所有工具的名称和详细功能描述

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do  # 思考：判断是否需要调用工具、调用哪个工具
Action: the action to take, should be one of {tool_names}  # 行动：指定要调用的工具名称（必须在工具列表中）
Action Input: the input to the action  # 行动输入：传递给工具的查询关键词/参数
Observation: the result of the action  # 观察：接收工具执行后的返回结果
... (this Thought/Action/Action Input/Observation can repeat N times)  # 可循环多次，完成复杂多步骤任务
Thought: I now know the final answer  # 最终思考：确认已获取足够信息，可整合形成最终答案
Final Answer: the final answer to the original input question  # 最终答案：返回给用户的完整、结构化回复

Begin!  # 启动指令，提示智能体开始执行任务

Question: {input}  # 占位符：接收用户传入的查询输入
Thought:{agent_scratchpad}  # 占位符：智能体的「草稿区」，存储思考过程、行动记录和中间结果（不可删除）''')

# 注释：保留工具调用型智能体的创建代码（备用），当前实战使用REACT智能体
# agent = create_tool_calling_agent(
#     llm=model,
#     tools=tools,
#     prompt=prompt
# )

# 创建REACT智能体，整合大语言模型、工具列表和提示词模板，具备复杂任务的分步决策能力
agent = create_react_agent(
    llm=model,  # 传入实例化的大语言模型（负责逻辑推理、工具调用决策）
    tools=tools,  # 传入智能体可调用的工具列表（Milvus检索+网页搜索）
    prompt=prompt  # 传入自定义的REACT提示词模板，规定智能体的运行格式和逻辑
)

# 创建智能体执行器，负责调度智能体运行、处理工具调用流程、返回最终结果和中间步骤
agent_executor = AgentExecutor(
    agent=agent,  # 传入已创建的REACT智能体
    tools=tools,  # 传入工具列表（与创建智能体时保持一致）
    verbose=True,  # 启用详细日志输出，可在控制台查看智能体的完整运行流程
    return_intermediate_steps=True,  # 启用中间步骤返回，方便追溯工具调用记录和调试
    handle_parsing_errors="log_and_continue"  # 优化：设置解析错误处理策略，出错时记录日志并继续执行，提升鲁棒性
)

def run_agent(question: str):
    """
    封装智能体运行函数，简化调用流程，格式化输出结果和中间步骤
    参数：question - 用户需要查询的问题（字符串格式）
    """
    print(f"\n问题:{question}")
    # 调用智能体执行器，传入用户问题，获取执行结果
    result = agent_executor.invoke({"input": question})
    # 打印完整返回结果（含最终回复+中间步骤，便于调试）
    print(f"\n llm-result:{result}")
    # 打印格式化的最终答案（便于用户查看核心结果）
    print(f"\n 答案:{result['output']}\n{'='*50}")
    # 遍历并打印所有中间步骤，详细展示智能体的「思考-行动-输入-观察」过程
    for step in result["intermediate_steps"]:
        print(f"\n Thought:{step[0].log}")  # 打印智能体的思考过程
        print(f"\n Action:{step[0].tool}")  # 打印智能体调用的工具名称
        print(f"\n Action Input:{step[0].tool_input}")  # 打印工具的输入参数
        print(f"\n Observation:{step[1]}")  # 打印工具的返回结果

# 调用封装的智能体运行函数，传入复杂多子任务查询问题，执行综合实战任务
# 用户问题包含5个子任务：1. 什么是Milvus 2. Milvus最新版本 3. Milvus整合LangChain 4. Milvus与Faiss对比 5. Milvus GitHub最新教程链接
run_agent("中文回答下面3个问题：第一个，什么是Milvus，最新的版本是多少？如何整合langchain框架，与Faiss对比优缺点，最后给出GitHub最新教程链接")
