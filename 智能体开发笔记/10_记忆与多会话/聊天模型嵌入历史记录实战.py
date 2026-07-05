# 从LangChain链模块导入LLMChain，用于构建基于大语言模型的端到端运行链
from langchain.chains.llm import LLMChain
# 从LangChain记忆模块导入两种对话记忆类（本演示使用ConversationBufferMemory，前者为备用/对比）
from langchain.memory import ConversationSummaryMemory, ConversationBufferMemory
# 从LangChain核心提示词模块导入：
# ChatPromptTemplate：构建结构化聊天提示词模板
# MessagesPlaceholder：对话历史占位符，用于动态嵌入完整对话消息列表
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# 从LangChain OpenAI模块导入ChatOpenAI，实例化兼容OpenAI格式的大语言模型客户端
from langchain_openai import ChatOpenAI
# 从pydantic导入SecretStr，用于安全存储敏感信息（API密钥），避免明文泄露风险
from pydantic import SecretStr

# ---------------------- 大语言模型实例化 ----------------------
# 创建ChatOpenAI模型实例，作为翻译任务和对话记忆管理的核心引擎
llm = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问plus版本，具备优秀的文本理解与翻译能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的OpenAI兼容API地址
    api_key=SecretStr(""),  # 安全存储API密钥（敏感信息），SecretStr会隐藏明文展示
    temperature=0.7)  # 模型生成内容的随机性/创造性参数（0-1区间），0.7兼顾翻译准确性和表达流畅性（注：原注释"亲密度"不准确）

# ---------------------- 对话记忆初始化（使用ConversationBufferMemory） ----------------------
# 初始化对话缓冲记忆对象，用于完整存储多轮对话的原始消息（不做摘要压缩，保留完整上下文）
memory = ConversationBufferMemory(
    llm=llm,  # 传入已实例化的模型（虽缓冲记忆默认无需模型生成摘要，仍可用于后续扩展）
    return_messages=True,  # 设置返回格式为Message对象列表（而非纯字符串），适配MessagesPlaceholder要求
    memory_key="chat_history",  # 定义记忆数据的键名，**必须与MessagesPlaceholder的variable_name一致**，否则无法正常嵌入
)

# ---------------------- 构建包含对话历史占位符的提示词模板 ----------------------
# 构建结构化聊天提示词模板，核心特点是嵌入对话历史占位符，实现上下文关联翻译
prompt = ChatPromptTemplate.from_messages([
    # 系统角色：定义AI的身份为翻译助手，明确核心任务目标
    ("system", "你是一个翻译助手"),
    # 对话历史占位符：动态嵌入由memory管理的完整对话消息列表（key为chat_history）
    # 作用：将历史对话上下文传入模型，支持关联式翻译（如需基于前文语境优化翻译结果）
    MessagesPlaceholder(variable_name="chat_history"),
    # 用户角色：接收用户实时输入的待翻译文本（{input}为用户输入占位符）
    ("user", "{input}")
])

# ---------------------- 构建LLMChain运行链（集成模型、提示词、记忆） ----------------------
# 实例化LLMChain链，将模型、提示词模板、对话记忆三者集成，实现端到端的带记忆翻译
chain = LLMChain(
    llm=llm,  # 传入核心大语言模型
    prompt=prompt,  # 传入已构建的带历史占位符的提示词模板
    memory=memory,  # 传入已初始化的对话缓冲记忆，链会自动管理对话的存储与加载（无需手动调用save_context）
)

# ---------------------- 定义模拟用户输入列表（待翻译的英文句子） ----------------------
# 准备3句待翻译的英文文本，用于验证多轮对话记忆和翻译功能
user_input = [
    "The symphony of raindrops on the rooftop played a gentle, rhythmic lullaby.",
    "A solitary dandelion seed drifted on the breeze, carrying its promise of new life to unknown soil",
    "He found that the oldest maps often led not to treasure, but to the most profound silence"
]

# ---------------------- 循环调用LLMChain，执行多轮带记忆翻译 ----------------------
# 遍历用户输入列表，逐轮执行翻译任务，验证对话记忆的自动管理功能
for query in user_input:
    # 调用LLMChain链，传入用户当前输入（字典格式，key与prompt中的{input}对应），获取翻译结果
    # 注：因链中集成了memory，会自动加载历史对话并嵌入提示词，执行后也会自动保存本轮对话到记忆中
    resp = chain.invoke({"input": query})

    # 打印当前轮次的用户提问（待翻译英文）和AI回复（翻译结果）
    print(f"User提问:{query}")
    print(f"AI回复:{resp}", end="\n\n")

    # 打印当前最新的完整对话历史，验证记忆对象的自动更新功能
    # 从记忆中加载以"chat_history"为键的对话消息列表，查看所有历史对话记录
    print(f"打印当前历史：{memory.load_memory_variables({})['chat_history']}")
    print("-" * 100)  # 分隔线，优化打印结果的可读性（可选补充）
