# ==================== 大模型绑定工具（Tool）核心实战 ====================
# 核心目标：让大模型根据用户问题自动判断是否调用工具、调用哪个工具，并基于工具结果生成最终回答

# 导入核心模块：
# HumanMessage：构造用户消息（符合LangChain消息格式）
# tool：装饰器，将普通函数转为大模型可调用的工具
# ChatOpenAI：调用兼容OpenAI接口的大模型（这里对接阿里云通义千问）
# SecretStr：安全存储敏感信息（如API密钥），避免明文泄露
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


# -------------------- 第一步：定义大模型可调用的工具 --------------------
# @tool装饰器：将普通Python函数转为LangChain标准工具（无需手动定义参数Schema，自动解析）
# 工具1：加法工具，实现两数相加
@tool
def add(a:int, b: int) -> int:
    """
    工具功能描述（给大模型看）：计算两个整数的加法（a + b）
    :param a: 第一个整数参数
    :param b: 第二个整数参数
    :return: 两数相加的结果
    """
    return a + b

# 工具2：乘法工具，实现两数相乘
@tool
def multiply(a:int, b: int) -> int:
    """
    工具功能描述（给大模型看）：计算两个整数的乘法（a * b）
    :param a: 第一个整数参数
    :param b: 第二个整数参数
    :return: 两数相乘的结果
    """
    return a * b

# -------------------- 第二步：初始化大模型（对接阿里云通义千问） --------------------
model = ChatOpenAI(
    model="qwen-plus",  # 指定模型名称（通义千问Plus）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问兼容OpenAI的接口地址
    api_key=SecretStr(""),  # 安全存储API密钥（SecretStr避免明文打印/泄露）
    temperature=0.7)  # 模型生成温度（0-1，值越高输出越随机，越低越精准）

# -------------------- 第三步：将工具绑定到大模型 --------------------
# bind_tools：将工具列表绑定到模型，让模型具备“工具调用能力”
# 绑定后，模型会分析用户问题，判断是否需要调用工具、调用哪个工具、传什么参数
llm_with_tool = model.bind_tools(tools)

# -------------------- 第四步：构造用户问题并触发模型推理 --------------------
# 用户问题（需要模型调用乘法工具解决）
query = "请计算2*3是多少？"

# 构造消息列表（LangChain标准格式，HumanMessage表示用户消息）
message = [
    HumanMessage(content=query)
]

# 调用绑定工具的模型：模型会先分析问题，生成“工具调用指令”（而非直接回答）
ai_message = llm_with_tool.invoke(message)
# print(ai_message.tool_calls)  # 可打印查看工具调用详情（包含工具名称、参数等）

# 将模型的工具调用消息加入消息列表（用于后续上下文传递）
message.append(ai_message)

# -------------------- 第五步：执行模型指定的工具调用 --------------------
# 遍历模型生成的工具调用指令（可能调用多个工具）
for tool_call in ai_message.tool_calls:
    # 根据工具名称匹配对应的工具函数（统一转为小写避免大小写问题）
    selected_tool = {"add": add, "multiply": multiply}[tool_call['name'].lower()]
    # 调用工具：传入工具调用指令中的参数，执行工具并获取结果
    tool_msg = selected_tool.invoke(tool_call)
    print(f"工具执行结果:{tool_msg}")  # 输出：6（2*3的结果）
    # 将工具执行结果加入消息列表（作为上下文，供模型生成最终回答）
    message.append(tool_msg)

# 打印完整消息列表（查看上下文流转：用户消息 → 模型工具调用 → 工具结果）
print("完整消息上下文:", message)

# -------------------- 第六步：模型基于工具结果生成最终回答 --------------------
# 模型结合用户问题、工具调用指令、工具执行结果，生成自然语言回答
result = llm_with_tool.invoke(message)
print(f"AI最终回复:{result.content}")  # 输出类似：2乘以3的结果是6。
