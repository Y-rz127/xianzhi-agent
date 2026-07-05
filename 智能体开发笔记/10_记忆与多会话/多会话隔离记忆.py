# 从LangChain核心消息模块导入系统消息和人类消息类，用于构建结构化对话消息
from langchain_core.messages import SystemMessage, HumanMessage
# 从LangChain核心提示词模块导入：
# ChatPromptTemplate：构建结构化聊天提示词模板
# MessagesPlaceholder：对话历史占位符，用于动态嵌入会话历史消息列表
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# 从LangChain核心可运行模块导入RunnableWithMessageHistory，用于为链式结构添加会话历史管理和隔离能力
from langchain_core.runnables import RunnableWithMessageHistory
# 从LangChain OpenAI模块导入ChatOpenAI，实例化兼容OpenAI格式的大语言模型客户端
from langchain_openai import ChatOpenAI
# 从pydantic导入SecretStr，用于安全存储敏感信息（API密钥），避免明文泄露风险
from pydantic import SecretStr
# 从LangChain记忆模块导入ChatMessageHistory，用于存储单个会话的完整消息历史（会话级记忆载体）
from langchain.memory import ChatMessageHistory

# ---------------------- 全局会话存储初始化 ----------------------
# 定义全局字典store，用于存储所有用户/会话的历史记录，实现多会话隔离
# 键（key）：会话唯一标识（session_id），值（value）：对应会话的ChatMessageHistory实例（存储该会话的完整对话）
store = {}


# ---------------------- 会话历史获取函数（核心：实现会话隔离与创建） ----------------------
def get_session_history(session_id: str):
    """
    根据会话唯一标识（session_id）获取对应的会话历史，实现多会话隔离
    :param session_id: 会话唯一标识（如用户ID、会话ID），用于区分不同会话
    :return: 对应session_id的ChatMessageHistory实例（会话历史载体）
    """
    # 从全局字典store中，根据session_id获取对应的会话历史对象
    history = store.get(session_id)

    # 判空逻辑：如果该session_id对应的会话历史不存在（首次访问该会话）
    if history is None:  # 修复点：使用 is None 准确判断对象是否为空，而非 in None
        # 创建一个新的ChatMessageHistory实例，用于存储该会话的后续对话消息
        history = ChatMessageHistory()
        # 将新创建的会话历史存入全局字典，绑定对应的session_id，方便后续获取
        store[session_id] = history

    # 返回该session_id对应的会话历史对象（存在则返回已有，不存在则返回新建并存储后的）
    return history  # 修复点：确保函数返回会话历史对象，供后续链式结构使用


# ---------------------- 构建带会话历史占位符的聊天提示词模板 ----------------------
# 构建结构化聊天提示词模板，包含系统消息、历史消息占位符、人类输入，支持会话上下文关联
prompt = ChatPromptTemplate.from_messages([
    # 系统消息：定义AI助手的能力边界和回答要求，{ability}为动态传入的能力参数
    SystemMessage(content="你是一个AI助手，擅长能力{ability}。用30个字以内回答"),
    # 会话历史占位符：动态嵌入对应session_id的对话历史消息列表，key为"history"
    MessagesPlaceholder(variable_name="history"),
    # 人类消息：接收用户的实时输入，{input}为动态传入的用户提问参数
    HumanMessage(content="{input}")
])

# ---------------------- 大语言模型实例化 ----------------------
# 创建ChatOpenAI模型实例，作为会话问答的核心生成引擎
llm = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问plus版本，具备优秀的文本理解与生成能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的OpenAI兼容API地址
    api_key=SecretStr(""),  # 安全存储API密钥（敏感信息），SecretStr会隐藏明文展示
    temperature=0.7)  # 模型生成内容的随机性/创造性参数（0-1区间），0.7兼顾逻辑性和表达流畅性（注：原注释"亲密度"不准确）

# ---------------------- 构建基础运行链 ----------------------
# 用管道符|串联提示词模板和模型，构建端到端的基础问答链（无会话记忆能力）
chain = prompt | llm

# ---------------------- 为基础链添加会话历史管理与隔离能力 ----------------------
# 封装RunnableWithMessageHistory，为基础链赋予「会话历史记忆+多会话隔离」的核心能力
with_message_history = RunnableWithMessageHistory(
    chain,  # 传入基础运行链，为其添加会话历史功能
    get_session_history=get_session_history,  # 传入会话历史获取函数，用于获取/创建对应session_id的会话历史
    input_messages_key="input",  # 指定用户输入对应的键名，与prompt中的{input}和invoke传入的参数对应
    history_messages_key="history"  # 指定会话历史对应的键名，与MessagesPlaceholder的variable_name对应
)

# ---------------------- 第一次调用：会话user_123 首次提问 ----------------------
# 调用带会话历史的链式结构，向session_id=user_123的会话发送首次提问
resp1 = with_message_history.invoke(
    # 传入提示词模板所需的动态参数：能力类型和用户输入
    {
        "ability": "Java开发",
        "input": "什么是JVM"
    },
    # 配置会话唯一标识，指定本次调用归属的会话（实现会话隔离的关键配置）
    config={"configurable": {"session_id": "user_123"}}
)

# 打印全局存储字典store，查看session_id=user_123的会话历史是否已创建并存储
print(f"store1：{store}")
# 打印第一次调用的AI回复内容（提取Message对象的content属性，获取纯文本回复）
print(f"resp1:{resp1.content}", end="\n\n")

# ---------------------- 第二次调用：会话user_123 后续追问 ----------------------
# 继续调用带会话历史的链式结构，向同一个session_id=user_123的会话发送追问
resp2 = with_message_history.invoke(
    # 传入提示词模板所需的动态参数，本次要求重新回答JVM相关问题
    {
        "ability": "Java开发",
        "input": "重新回答一次"
    },
    # 配置相同的session_id=user_123，确保归属同一个会话，可关联上一轮对话上下文
    config={"configurable": {"session_id": "user_123"}}
)

# 打印全局存储字典store，查看session_id=user_123的会话历史是否已追加本轮对话
print(f"store2：{store}")
# 打印第二次调用的AI回复内容
print(f"resp2:{resp2.content}", end="\n\n")
