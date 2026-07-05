# ====================== 第一部分：LangChain 聊天提示词模板实战 ======================
# 从langchain的map_reduce问答链模块中导入系统提示词模板（此处虽导入未实际使用，仅保留原始代码结构）
from langchain.chains.question_answering.map_reduce_prompt import system_template
# 从langchain_core.prompts模块导入聊天提示词相关核心类
# ChatPromptTemplate：用于构建多轮对话式提示词模板
# SystemMessagePromptTemplate：用于构建系统角色消息模板
# HumanMessagePromptTemplate：用于构建人类用户消息模板
# PromptTemplate：基础提示词模板类
from langchain_core.prompts import ChatPromptTemplate,SystemMessagePromptTemplate,HumanMessagePromptTemplate,PromptTemplate

# 方式1：直接通过ChatPromptTemplate.from_messages快速创建聊天提示词模板
# 传入一个消息列表，每个元素代表一轮消息，格式支持（消息类型, 消息内容）
# 消息类型支持：system（系统指令）、human（人类输入）、ai（AI回复）
chat_template = ChatPromptTemplate.from_messages([
    ("system","你是一个助手AI，名字是{name}"),  # 系统消息：定义AI角色，{name}为动态变量
    ("human","你好，最近怎么样?"),                 # 人类消息：固定用户问候语（无变量）
    ("ai","我很好谢谢"),                           # AI消息：固定AI回复（无变量）
    ("human","{user_input}"),                     # 人类消息：动态用户输入，{user_input}为变量
])

# 填充模板（注释掉的方式：format方法，此处使用format_messages更适配聊天场景）
# message = chat_template.format(text="你好",language="英文")
# 调用format_messages方法填充模板中的动态变量，生成标准化的聊天消息列表
# 传入name和user_input两个变量，对应模板中的占位符
message = chat_template.format_messages(name="HideOnBoss",user_input="你最喜欢的编程语言是什么?")
# 打印填充后的完整聊天消息列表
print(message)

# ====================== 方式2：先构建单条消息模板，再组合成聊天模板 ======================
# 结合from_template和from_messages实现更灵活的聊天模板构建
# 1. 创建系统消息模板：通过SystemMessagePromptTemplate.from_template方法
# 传入带动态变量的模板字符串，构建专属系统角色的消息模板
system_template = SystemMessagePromptTemplate.from_template(
    "你是一个{role}，请用{language}回答"  # {role}（角色）和{language}（回答语言）为动态变量
)

# 2. 创建人类用户消息模板：通过HumanMessagePromptTemplate.from_template方法
# 传入带动态变量的模板字符串，构建专属人类用户的消息模板
user_template = HumanMessagePromptTemplate.from_template(
    "{question}"  # {question}（用户问题）为动态变量
)

# 3. 将单个消息模板组合成完整的多轮对话模板
# ChatPromptTemplate.from_messages接收单个消息模板对象组成的列表
chat_template = ChatPromptTemplate.from_messages([
    system_template,  # 先传入系统消息模板
    user_template,    # 再传入人类用户消息模板
])

# 调用format_messages方法填充所有动态变量，生成标准化聊天消息
message = chat_template.format_messages(
    role="助手",     # 填充system_template中的{role}变量
    language="中文", # 填充system_template中的{language}变量
    question="你最喜欢什么?"  # 填充user_template中的{question}变量
)
# 打印组合模板填充后的结果
print(message)
