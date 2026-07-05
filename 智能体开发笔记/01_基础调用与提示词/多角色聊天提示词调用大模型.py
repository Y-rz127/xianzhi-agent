# ====================== 第一部分：基础消息列表调用大模型（固定角色+固定问题） ======================
# 从langchain_core.messages模块导入系统消息和人类消息类，用于构建多轮对话消息
from langchain_core.messages import SystemMessage, HumanMessage
# 从langchain_openai模块导入ChatOpenAI类，用于调用兼容OpenAI接口的大模型（此处对接通义千问）
from langchain_openai import ChatOpenAI
# 从pydantic模块导入SecretStr类，用于安全存储和管理敏感信息（API密钥）
from pydantic import SecretStr
# 从langchain_core.prompts模块导入聊天提示词相关类，用于构建灵活的聊天模板
from langchain_core.prompts import ChatPromptTemplate,SystemMessagePromptTemplate,HumanMessagePromptTemplate

# 构建固定的消息列表，用于传递给大模型（系统消息定义角色，人类消息传递具体问题）
messages = [
    # 系统消息：定义大模型的角色和核心任务（翻译小助手，负责将文本翻译成英文）
    SystemMessage("你是一个翻译小助手，你需要将文本翻译成英文"),
    # 人类消息：传递具体的用户查询内容（需要翻译的中文句子）
    HumanMessage("你好，如何成为一个高级程序员?"),
]

# 实例化ChatOpenAI对象，配置大模型连接参数，用于后续调用模型
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（通义千问qwen-plus）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容OpenAI格式）
    api_key=SecretStr(""),  # 配置模型调用密钥，使用SecretStr安全封装避免明文泄露
    temperature=0.7)  # 设置模型生成温度（0-2），0.7兼顾创造性和回答稳定性

# 调用大模型的invoke方法，传入构建好的消息列表，获取模型响应结果
responses = model.invoke(messages)
# 打印模型响应的核心文本内容（翻译后的英文结果）
print(responses.content)

# ====================== 第二部分：灵活构建聊天提示词模板（动态变量+消息组合） ======================
# 构建系统消息模板：通过SystemMessagePromptTemplate.from_template方法，支持动态变量
system_template = SystemMessagePromptTemplate.from_template(
        """
        你是一个专业的{domain}专家，回答需满足:{style_guide}
        """
# {domain}（领域）和{style_guide}（回答规范）为动态变量，后续可灵活填充

)

# 构建人类消息模板：通过HumanMessagePromptTemplate.from_template方法，支持动态变量
human_template = HumanMessagePromptTemplate.from_template(
        """
        请解释:{concept}
        """  # {concept}（需要解释的概念）为动态变量，后续可灵活填充
)

# 将系统消息模板和人类消息模板组合，构建完整的聊天提示词模板
chat_prompt = ChatPromptTemplate.from_messages(
    [system_template, human_template]  # 按对话顺序组合单个消息模板
)

# 注释：格式化模板生成消息列表（此处注释备用，可取消注释使用）
# messages = chat_prompt.format(domain="机器学习", style_guide="简洁", concept="机器学习是什么?")
# 调用大模型获取响应
# responses = model.invoke(messages)
# 打印响应结果
# print(responses.content)

# ====================== 第三部分：快速构建客服场景聊天模板（直接使用消息元组） ======================
# 快速构建合规客服场景的聊天提示词模板，直接使用（消息类型, 模板字符串）的元组形式
compliance_template = ChatPromptTemplate.from_messages([
    # 系统消息：定义客服助手角色和三条合规规则，包含{company}和{transfer_cond}两个动态变量
    ("system",""" 您是{company}客服助手，遵守
     1.不透露内部系统名称
     2.不提供医疗/金融建议
     3.遇到{transfer_cond} 转人工
     """),
    # 人类消息：定义用户消息格式，包含{user_level}（用户等级）和{query}（用户查询）两个动态变量
    ("human","[{user_level}用户]:{query}")]
)

# 调用format方法填充所有动态变量，生成完整的提示词字符串（可直接传给大模型）
messages = compliance_template.format(
    company="百度",  # 填充系统消息中的{company}变量
    transfer_cond="用户反馈问题无法解决或者支付的问题",  # 填充系统消息中的{transfer_cond}变量
    user_level="普通",  # 填充人类消息中的{user_level}变量
    query="你们内部系统叫什么?"  # 填充人类消息中的{query}变量（测试合规规则1：不透露内部系统名称）
)

# 调用大模型，传入格式化后的提示词，获取客服合规响应
responses = model.invoke(messages)
# 打印模型的合规回答结果（预期会拒绝透露内部系统名称）
print(responses.content)
