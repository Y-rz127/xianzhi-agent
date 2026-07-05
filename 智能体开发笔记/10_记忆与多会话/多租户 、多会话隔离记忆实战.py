# 从LangChain核心消息模块导入系统消息和人类消息类，用于构建结构化对话消息
from langchain_core.messages import SystemMessage, HumanMessage
# 从LangChain核心提示词模块导入：
# ChatPromptTemplate：构建结构化聊天提示词模板
# MessagesPlaceholder：对话历史占位符，用于动态嵌入会话历史消息列表
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# 从LangChain核心可运行模块导入：
# RunnableWithMessageHistory：为链式结构添加会话历史管理和隔离能力
# ConfigurableFieldSpec：定义自定义可配置字段，支持多参数（用户+会话）的会话隔离
from langchain_core.runnables import RunnableWithMessageHistory, ConfigurableFieldSpec
# 从LangChain OpenAI模块导入ChatOpenAI，实例化兼容OpenAI格式的大语言模型客户端
from langchain_openai import ChatOpenAI
# 从pydantic导入SecretStr，用于安全存储敏感信息（API密钥），避免明文泄露风险
from pydantic import SecretStr
# 从LangChain记忆模块导入ChatMessageHistory，用于存储单个（用户+会话）的完整消息历史
from langchain.memory import ChatMessageHistory

# ---------------------- 全局多租户会话存储初始化 ----------------------
# 定义全局字典store，用于存储「多租户+多会话」的双层历史记录，实现双层隔离
# 键（key）：元组 (user_id, session_id)，对应「用户唯一标识+会话唯一标识」
# 值（value）：对应 该（用户+会话）的ChatMessageHistory实例（存储该组合的完整对话）
store = {}

# ---------------------- 双层会话历史获取函数（核心：多租户+多会话隔离） ----------------------
def get_session_history(user_id: str, session_id: str):
    """
    根据「用户唯一标识（user_id）+ 会话唯一标识（session_id）」获取对应的会话历史，实现双层隔离
    :param user_id: 租户/用户唯一标识，用于区分不同用户（多租户核心）
    :param session_id: 会话唯一标识，用于区分同一用户的不同会话
    :return: 对应 (user_id, session_id) 的ChatMessageHistory实例（会话历史载体）
    """
    # 判空逻辑：如果该（用户+会话）组合对应的会话历史不存在（首次访问该组合）
    if (user_id, session_id) not in store:
        # 创建一个新的ChatMessageHistory实例，用于存储该（用户+会话）的后续对话消息
        store[(user_id, session_id)] = ChatMessageHistory()
    # 返回该（用户+会话）组合对应的会话历史对象（存在则返回已有，不存在则返回新建并存储后的）
    return store[(user_id, session_id)]

# ---------------------- 构建带会话历史占位符的聊天提示词模板 ----------------------
# 构建结构化聊天提示词模板，包含系统消息、历史消息占位符、人类输入，支持上下文关联
prompt = ChatPromptTemplate.from_messages([
    # 系统消息：定义AI助手的能力边界和回答要求，{ability}为动态传入的能力参数
    SystemMessage(content="你是一个AI助手，擅长能力{ability}。用30个字以内回答"),
    # 会话历史占位符：动态嵌入对应（用户+会话）的对话历史消息列表，key为"history"
    MessagesPlaceholder(variable_name="history"),
    # 人类消息：接收用户的实时输入，{input}为动态传入的用户提问参数
    HumanMessage(content="{input}")
])

# ---------------------- 大语言模型实例化 ----------------------
# 创建ChatOpenAI模型实例，作为多租户会话问答的核心生成引擎
llm = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问plus版本，具备优秀的文本理解与生成能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的OpenAI兼容API地址
    api_key=SecretStr(""),  # 安全存储API密钥（敏感信息），SecretStr会隐藏明文展示
    temperature=0.7)  # 模型生成内容的随机性/创造性参数（0-1区间），0.7兼顾逻辑性和表达流畅性（注：原注释"亲密度"不准确）

# ---------------------- 构建基础运行链 ----------------------
# 用管道符|串联提示词模板和模型，构建端到端的基础问答链（无会话记忆能力）
chain = prompt | llm

# ---------------------- 为基础链添加「多租户+多会话」双层隔离记忆能力 ----------------------
# 封装RunnableWithMessageHistory，为基础链赋予「多租户+多会话」双层隔离的会话历史管理能力
with_message_history = RunnableWithMessageHistory(
    chain,  # 传入基础运行链，为其添加会话历史功能
    get_session_history=get_session_history,  # 传入双层会话历史获取函数，支持用户+会话双参数
    input_messages_key="input",  # 指定用户输入对应的键名，与prompt中的{input}和invoke传入的参数对应
    history_messages_key="history",  # 指定会话历史对应的键名，与MessagesPlaceholder的variable_name对应
    # 定义自定义可配置字段（核心：为get_session_history传递多参数）
    history_factory_config=[
        # 定义第一个自定义字段：user_id（用户唯一标识）
        ConfigurableFieldSpec(
            id = "user_id",  # 字段唯一标识，与get_session_history的参数名、config中的键名一致
            annotation=str,  # 字段数据类型，指定为字符串类型
            name="用户id",  # 字段名称（可读性描述）
            description="用户唯一标识符",  # 字段详细描述（说明用途）
            default="",  # 字段默认值
            is_shared=True  # 标记字段为共享配置，可在config中传递
        ),
        # 定义第二个自定义字段：session_id（对话唯一标识）
        ConfigurableFieldSpec(
            id = "session_id",  # 字段唯一标识，与get_session_history的参数名、config中的键名一致
            annotation=str,  # 字段数据类型，指定为字符串类型
            name="对话id",  # 字段名称（可读性描述）
            description="对话唯一标识符",  # 字段详细描述（说明用途）
            default="",  # 字段默认值
            is_shared=True  # 标记字段为共享配置，可在config中传递
        )
    ]
)

# ---------------------- 第一次调用：用户1 + 会话1 首次提问 ----------------------
# 调用带双层隔离记忆的链式结构，向（user_id=1, session_id=1）的组合发送首次提问
resp1 = with_message_history.invoke(
    # 传入提示词模板所需的动态参数：能力类型和用户输入（封装为HumanMessage对象）
    {
        "ability": "Java开发",
        "input": HumanMessage("什么是JVM")
    },
    # 配置双层唯一标识，指定本次调用归属的「用户+会话」（实现双层隔离的关键配置）
    config={'configurable':{"user_id":"1", 'session_id':"1"}}
)

# 打印全局存储字典store，查看（1,1）组合的会话历史是否已创建并存储
print(f"store1：{store}")
# 打印第一次调用的AI回复内容（提取Message对象的content属性，获取纯文本回复）
print(f"resp1:{resp1.content}",end="\n\n")

# ---------------------- 第二次调用：用户1 + 会话1 后续追问 ----------------------
# 继续调用带双层隔离记忆的链式结构，向同一个（user_id=1, session_id=1）组合发送追问
resp2 = with_message_history.invoke(
    # 传入提示词模板所需的动态参数，本次要求重新回答JVM相关问题
    {
        "ability": "Java开发",
        "input": HumanMessage("重新回答一次")
    },
    # 配置相同的「用户+会话」组合，确保归属同一上下文，可关联上一轮对话
    config={'configurable':{"user_id":"1", 'session_id':"1"}}
)

# 打印全局存储字典store，查看（1,1）组合的会话历史是否已追加本轮对话
print(f"store2：{store}")
# 打印第二次调用的AI回复内容
print(f"resp2:{resp2.content}",end="\n\n")
