# 基于LangChain搭建具备「日期获取、航班查询/预订、股价查询」能力的个人AI助手智能体
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool, Tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# 定义获取当前日期的工具函数，使用@tool装饰器标记为LangChain可调用工具
# 无入参，返回格式化的当前日期字符串
@tool
def get_current_date() -> str:
    """ 获取当前日期（格式：年-月-日），用于需要日期上下文的任务（如航班查询、预订等） """
    import datetime  # 内部导入datetime模块，仅在该工具调用时加载
    # 将当前时间格式化为"YYYY-MM-DD"的标准格式，提升结果可读性和后续工具兼容性
    formatted_date = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"当前日期为：{formatted_date}"

# 定义搜索航班的工具函数，带入参校验，满足指定城市和日期的航班查询需求
@tool
def search_flight(from_city: str, to_city: str, date: str) -> str:
    """
    搜索指定出发地、目的地和日期的可用航班
    参数说明：
    - from_city: 出发城市（如"广州"、"上海"）
    - to_city: 目的城市（如"北京"、"深圳"）
    - date: 出行日期（格式：YYYY-MM-DD）
    """
    # 模拟航班搜索结果，实际场景可对接航空公司API或第三方旅游平台接口
    return f"搜索结果：从{from_city}到{to_city}的航班在{date}有可用航班,价格：￥1200，推荐航班号：CA1324"

# 定义预定航班的工具函数，支持指定航班号和用户信息完成预订
@tool
def book_flight(flight_id: str, user: str) -> str:
    """
    预定指定航班号的机票，需提供有效航班号和用户名
    参数说明：
    - flight_id: 航班号（如"CA1324"，需从search_flight工具的结果中获取）
    - user: 预订用户姓名（用于机票出票和身份核验）
    """
    # 模拟航班预订成功结果，实际场景需对接航班预订系统，包含订单创建、支付回调等逻辑
    return f"用户:{user}预定成功，航班号：{flight_id}，订单状态：待支付"

# 定义获取股价的普通函数（未使用@tool装饰器，后续将封装为Tool对象）
def get_stock_price(symbol: str) -> str:
    """
    查询指定股票代码对应的股价（模拟返回固定结果）
    参数说明：
    - symbol: 股票代码/标的符号（如苹果公司"AAPL"、比亚迪"002594"）
    """
    # 模拟美股股价查询结果，实际场景可对接金融数据API（如Yahoo Finance、Tushare等）
    return f"The price of {symbol} is $100. (实时更新时间：{datetime.datetime.now().strftime('%H:%M:%S')})"

# 修复：导入datetime模块（解决get_stock_price中调用datetime未导入的问题）
import datetime

# 创建工具列表，整合两种方式定义的工具（@tool装饰器直接生成 + 普通函数封装为Tool对象）
tools = [
    get_current_date,  # 直接加入@tool装饰器定义的工具
    search_flight,     # 直接加入@tool装饰器定义的工具
    book_flight,       # 直接加入@tool装饰器定义的工具
    # 将普通函数get_stock_price封装为LangChain标准Tool对象，使其可被Agent调用
    Tool(
        name="Get Stock Price",  # 工具名称（供Agent识别和调用）
        func=get_stock_price,    # 绑定工具执行的核心函数
        description="查询指定股票代码的当前股价，输入为股票标的符号（如苹果公司输入AAPL）",  # 工具功能描述（关键：供Agent判断是否需要调用该工具）
    ),
]

# 实例化大语言模型（对接阿里通义千问qwen-plus，兼容OpenAI接口格式）
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问增强版，具备更强的工具调用和逻辑推理能力）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 通义千问兼容OpenAI接口的端点地址
    api_key=SecretStr(""),  # 通义千问API密钥，使用SecretStr安全存储（避免明文泄露）
    temperature=0.7,    # 模型生成随机性（0~1），0.7兼顾逻辑性和灵活度，适合工具调用类任务
)

# 创建聊天提示词模板，定义Agent的系统角色、上下文信息和交互格式
prompt = ChatPromptTemplate.from_messages([
    # 系统消息：定义Agent的身份和核心行为准则，为Agent提供全局指令
    ("system", "你是一个专业的个人AI助手，擅长处理出行预订、金融信息查询等任务，必要时可以调用工具函数帮助用户解决问题，优先使用工具返回的准确数据进行回复"),
    # 历史上下文消息：预置用户的个人信息，供Agent在后续任务中直接使用（无需用户重复提供）
    ("human", "我叫老王，经常出差，喜欢性价比的按摩，身份证号是4444144444"),
    # 用户输入占位符：接收用户实时提交的任务指令，变量名{input}需与后续invoke传入的参数对应
    ("human", "{input}"),
    # Agent思考/行动占位符：用于存储Agent的思考过程、工具调用记录和中间结果，不可删除
    ("placeholder", "{agent_scratchpad}"),
])

# 创建工具调用型Agent（基于最新的Tool Calling能力，比传统REACT更高效、更稳定）
agent = create_tool_calling_agent(
    llm=model,    # 传入实例化的大语言模型（作为Agent的"大脑"，负责决策是否调用工具、调用哪个工具）
    tools=tools,  # 传入Agent可调用的工具列表，Agent会基于工具描述进行选择
    prompt=prompt # 传入自定义的提示词模板，定义Agent的行为边界和交互格式
)

# 创建Agent执行器，负责调度Agent运行、处理工具调用流程、返回最终结果
agent_executor = AgentExecutor(
    agent=agent,  # 传入已创建的工具调用型Agent
    tools=tools,  # 传入工具列表（与创建Agent时的工具列表保持一致）
    verbose=True,  # 启用详细日志输出，可在控制台查看Agent的思考过程、工具调用参数、工具返回结果等
    return_intermediate_steps=True,  # 启用中间步骤返回，最终结果中会包含Agent的每一步操作记录（方便调试和追溯）
    handle_parsing_errors="log_and_continue"  # 优化：设置解析错误处理策略，出错时记录日志并继续执行，提升鲁棒性
)

# 调用Agent执行器，传入用户复合任务请求，执行多任务并行处理
# 用户请求包含3个子任务：1. 查询自身身份证号 2. 查询苹果公司最新股价 3. 查询并预订广州→北京明天的航班
resp = agent_executor.invoke({
    "input": "我的身份证是多少?苹果公司最新的股票价格是多少? 根据我的行程帮我查询明天的航班，从广州到北京，并且定个机票"
})

# 打印最终结果，包含Agent的最终回复和中间执行步骤
print("=" * 80)
print(f"最终结果（核心回复）:\n{resp['output']}")
print("=" * 80)
print(f"完整返回结果（含中间步骤）:\n{resp}")
