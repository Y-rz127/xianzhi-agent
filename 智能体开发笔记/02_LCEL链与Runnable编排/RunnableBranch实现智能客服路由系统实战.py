# 核心功能：基于LangChain的RunnableBranch实现智能客服路由系统，模拟if-else逻辑
# 根据用户输入的问题类型（技术问题/财务问题/通用问题），自动路由到对应的专业处理子链，
# 实现不同类型请求的差异化应答，提升客服回复的精准度
from langchain_core.prompts import ChatPromptTemplate  # 聊天提示词模板，构建不同场景的Prompt
from langchain_core.runnables import RunnableBranch, RunnableLambda  # 路由分支/自定义函数执行组件
from langchain_openai import ChatOpenAI  # OpenAI兼容的大模型调用接口（适配通义千问）
from langchain_core.output_parsers import StrOutputParser  # 输出解析器，将LLM响应转为字符串
from pydantic import SecretStr  # 安全存储API密钥，避免明文泄露

# ======================== 初始化大语言模型 ========================
# 创建通义千问大模型实例，作为所有子链的回答生成核心
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用通义千问plus模型（具备更好的理解和生成能力）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云百炼兼容OpenAI的接口地址
    api_key=SecretStr(""),  # 安全存储API密钥（SecretStr避免明文打印）
    temperature=0.7  # 生成文本的随机性（0-1，0.7兼顾灵活性和专业性）
)

# ======================== 构建不同场景的专业子链 ========================
# 1. 技术支持子链：专门处理技术类问题，使用技术专家的Prompt模板
tech_prompt = ChatPromptTemplate.from_template(
    "你是一名技术支持专家，请回答以下技术问题：{input}"
)
# 技术链流程：Prompt模板填充 → LLM生成回答 → 输出转为字符串
tech_chain = tech_prompt | model | StrOutputParser()

# 2. 财务问题子链：专门处理账单/支付类问题，使用财务专员的Prompt模板
billing_prompt = ChatPromptTemplate.from_template(
    "你是一名财务专员，请处理以下账单问题：{input}"
)
# 财务链流程：Prompt模板填充 → LLM生成回答 → 输出转为字符串
billing_chain = billing_prompt | model | StrOutputParser()

# 3. 默认通用子链：处理非技术/非财务的通用问题，使用通用客服Prompt模板
default_prompt = ChatPromptTemplate.from_template(
    "你是一名客服专员，请回答以下问题：{input}"
)
# 通用链流程：Prompt模板填充 → LLM生成回答 → 输出转为字符串
default_chain = default_prompt | model | StrOutputParser()

# ======================== 定义路由判断函数（核心逻辑） ========================
from typing import Dict  # 导入类型注解，规范函数输入输出类型

def is_tech_question(input: dict) -> bool:
    """判断用户输入是否为技术问题（路由判断函数1）
    Args:
        input: 包含用户输入的字典，格式为 {"input": "用户问题文本"}
    Returns:
        bool: 包含技术关键词返回True，否则返回False
    """
    # 提取用户输入的文本内容（默认空字符串，避免KeyError）
    input_value = input.get("input", "")
    # 技术问题关键词列表（可根据实际业务扩展）
    tech_keywords = ["技术", "故障", "安装", "错误", "bug", "无法运行"]
    # 检查输入是否包含任意技术关键词（原代码仅判断2个，此处优化为通用逻辑）
    return any(keyword in input_value for keyword in tech_keywords)

def is_billing_question(input: dict) -> bool:
    """判断用户输入是否为财务问题（路由判断函数2）
    Args:
        input: 包含用户输入的字典，格式为 {"input": "用户问题文本"}
    Returns:
        bool: 包含财务关键词返回True，否则返回False
    """
    # 提取用户输入的文本内容
    input_value = input.get("input", "")
    # 财务问题关键词列表（原代码注释错误，已修正）
    billing_keywords = ["账单", "支付", "费用", "发票", "退款"]
    # 检查输入是否包含任意财务关键词
    return any(keyword in input_value for keyword in billing_keywords)

# ======================== 构建路由分支（模拟if-else） ========================
# RunnableBranch：按顺序执行判断，匹配第一个为True的条件则执行对应子链，否则执行默认链
# 逻辑等价于：if is_tech_question → tech_chain; elif is_billing_question → billing_chain; else → default_chain
branch = RunnableBranch(
    (is_tech_question, tech_chain),    # 条件1：技术问题 → 技术链
    (is_billing_question, billing_chain),  # 条件2：财务问题 → 财务链
    default_chain                      # 默认分支：通用问题 → 通用链
)

# ======================== 可选：构建带日志的路由链（调试/监控用） ========================
def log_decision(input_data):
    """日志函数：打印路由判断的输入数据，便于调试和监控"""
    print(f"路由检查输入：{input_data}")
    return input_data  # 透传输入数据，不影响后续流程

# 带日志的路由链：先打印日志 → 再执行路由分支
log_chain_branch = RunnableLambda(log_decision) | branch

# ======================== 构建完整的客服链路 ========================
# 完整链流程：
# 1. RunnableLambda(lambda x: {"input": x})：将原始字符串输入转为字典（适配路由函数的输入格式）
# 2. | branch：执行路由分支，匹配对应子链
full_chain = RunnableLambda(lambda x: {"input": x}) | branch

# ======================== 测试不同类型的用户问题 ========================
# 测试1：技术问题 → 路由到技术支持链
tech_response = full_chain.invoke("如何处理系统安装故障？")
print("【技术问题回复】：", tech_response)

# 测试2：财务问题 → 路由到财务链
billing_response = full_chain.invoke("如何查询本月的消费账单？")
print("【财务问题回复】：", billing_response)

# 测试3：通用问题 → 路由到默认通用链
common_response = full_chain.invoke("请问你们的工作时间是什么？")
print("【通用问题回复】：", common_response)
