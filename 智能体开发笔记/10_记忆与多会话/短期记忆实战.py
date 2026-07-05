# 短期记忆实战：基于 LangChain 实现带对话摘要记忆的多轮智能问答，支持上下文关联回复
# 从 LangChain 记忆模块导入对话摘要记忆类，用于自动生成和管理对话历史摘要
from langchain.memory import ConversationSummaryMemory
# 从 LangChain 核心输出解析模块导入字符串输出解析器，用于格式化模型返回结果（转为纯字符串）
from langchain_core.output_parsers import StrOutputParser
# 从 LangChain 核心提示词模块导入聊天提示词模板，用于构建结构化的多角色对话提示词
from langchain_core.prompts import ChatPromptTemplate
# 从 LangChain 核心可运行模块导入透传工具，用于动态扩展链的输入字段、加载记忆数据
from langchain_core.runnables import RunnablePassthrough
# 从 LangChain OpenAI 模块导入 ChatOpenAI 类，用于实例化兼容 OpenAI 格式的大语言模型客户端
from langchain_openai import ChatOpenAI
# 从 pydantic 导入 SecretStr，用于安全存储和处理敏感信息（如 API 密钥），避免明文泄露
from pydantic import SecretStr

# ---------------------- 大语言模型实例化 ----------------------
# 创建 ChatOpenAI 模型实例，作为对话生成和摘要生成的核心引擎
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的模型名称（通义千问 plus 版本，具备较强的理解和生成能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的 OpenAI 兼容 API 地址
    api_key=SecretStr(""),  # 安全存储 API 密钥（敏感信息），SecretStr 会隐藏明文展示
    temperature=0.7)  # 模型生成内容的随机性参数（0-1区间），0.7 兼顾逻辑性和一定的创造性（注：原注释"亲密度"不准确，应为"随机性/创造性"）

# ---------------------- 对话摘要记忆初始化 ----------------------
# 初始化对话摘要记忆对象，用于自动整合多轮对话为摘要，实现长期上下文记忆
memory = ConversationSummaryMemory(
    llm=model,  # 传入已实例化的模型，用于自动生成对话摘要（增量更新）
    return_messages=True,  # 设置返回格式为 Message 对象列表（而非纯字符串），适配 ChatPromptTemplate 格式要求
    memory_key="chat_history",  # 定义记忆数据的键名，后续在提示词和链中通过该键获取对话摘要
)

# ---------------------- 聊天提示词模板构建 ----------------------
# 构建结构化的聊天提示词模板，包含系统角色和用户角色，实现上下文关联问答
prompt = ChatPromptTemplate.from_messages([
    # 系统角色：定义 AI 助手的身份、行为准则，同时注入对话历史摘要（{chat_history} 为记忆键对应的占位符）
    ("system", "你是一个AI智能助手，你的名字是AI助手，需要基于历史对话回答问题，当前摘要信息:{chat_history}"),
    # 用户角色：接收用户的实时输入（{input} 为用户输入的占位符，运行时会被真实提问替换）
    ("user", "{input}")
])

# ---------------------- 构建 LangChain 运行链（LCEL 表达式） ----------------------
# 定义 LCEL（LangChain Expression Language）表达式，构建端到端的问答运行链
# 链式结构按从左到右顺序执行，通过 | 符号串联各个组件
chain = (
    # 第一步：RunnablePassthrough.assign() - 动态扩展输入字段，为后续链补充额外数据（此处为对话记忆）
        RunnablePassthrough.assign(
            # 定义要扩展的字段：chat_history（与记忆对象的 memory_key 对应）
            # 匿名函数 lambda _: 接收输入（此处无需使用输入，用 _ 占位），加载记忆中的对话摘要数据
            chat_history=lambda _: memory.load_memory_variables({})["chat_history"]
        ) |  # 管道符：将上一步的输出（扩展后的字段字典）作为下一步的输入
        # 第二步：prompt - 接收扩展后的字段字典，填充占位符，生成完整的结构化提示词
        prompt |
        # 第三步：model - 接收完整提示词，调用大语言模型生成回复内容
        model |
        # 第四步：StrOutputParser() - 解析模型返回结果，将复杂的 Message 对象转为纯字符串格式，方便后续使用和存储
        StrOutputParser()
)

# ---------------------- 定义模拟用户输入列表 ----------------------
# 准备多轮模拟用户提问，包含个人信息、知识点查询、上下文回溯查询（验证记忆功能）
user_input = [
    "我叫老王，现在是计算机专业大学生",
    "人工智能的定义",
    "",
    "人工智能在医疗领域有什么应用",
    "我是谁?读什么专业的？",  # 用于验证：AI 是否能通过对话记忆回答个人信息（上下文回溯）
]

# ---------------------- 循环调用问答链，执行多轮对话 ----------------------
# 遍历用户输入列表，逐轮执行问答流程，验证记忆功能
for query in user_input:
    # 调用链式结构，传入用户当前输入（字典格式，key 与 prompt 中的 {input} 对应），获取 AI 回复
    resp = chain.invoke({"input": query})

    # 打印当前轮次的用户提问和 AI 回复，方便查看对话过程
    print(f"User提问:{query}")
    print(f"AI回复:{resp}", end="\n\n")

    # 手动保存当前轮次的对话到记忆对象中（关键步骤）
    # 将用户输入（input）和 AI 回复（output）存入记忆，记忆对象会自动调用模型生成/更新摘要
    memory.save_context({"input": query}, {"output": resp})

    # 打印当前最新的对话摘要，查看记忆对象的增量更新结果，验证摘要生成功能
    print(f"打印当前摘要：{memory.load_memory_variables({})['chat_history']}")
    print("-" * 80)  # 分隔线，优化打印结果的可读性（可选补充）
