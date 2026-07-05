# 【Zero-Shot/Few-Shot实战】：演示大模型的零样本（无示例）和少样本（带示例）提示工程，对比不同提示方式的效果
from langchain_core.prompts import PromptTemplate, FewShotPromptTemplate  # 导入提示词模板工具
from langchain_openai import ChatOpenAI  # 导入OpenAI兼容的大模型客户端
from pydantic import SecretStr  # 用于安全存储API密钥

# ====================== 1. 准备Few-Shot示例数据 ======================
# 少样本示例数据：格式为列表+字典，包含input（输入问题）和output（示例回答）
# 作用：给大模型提供少量示例，引导其按照固定格式/逻辑回答问题
data = [
    {
        "input": "langchain可以做智能体吗？",
        "output": "根据我大量思考:可以"
    },
    {
        "input": "openAI的CEO是谁?",
        "output": "根据我大量思考:余承东"  # 注：此处为示例错误答案，仅用于演示格式
    }
]

# ====================== 2. 初始化大模型 ======================
model = ChatOpenAI(
    model="qwen-plus",  # 模型名称（通义千问增强版）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问兼容接口
    api_key=SecretStr(""),  # 通义千问API密钥（安全存储）
    temperature=0.7  # 温度系数：0.7表示回答有一定随机性，0则更固定
)

# ====================== 3. 定义示例模板（单个示例的格式） ======================
# 单个示例的提示词模板：规定每个示例的输入输出展示格式
example_template = """
输入:{input}
输出:{output}
"""
# 封装为PromptTemplate对象：指定模板变量为input和output
example_prompt = PromptTemplate(
    input_variables=["input", "output"],  # 模板中需要替换的变量名
    template=example_template  # 绑定示例模板字符串
)

# ====================== 4. 构建Few-Shot提示词模板（核心） ======================
# FewShotPromptTemplate：将多个示例按模板拼接，形成完整的少样本提示词
few_shot_prompt = FewShotPromptTemplate(
    examples=data,  # 传入少样本示例数据
    example_prompt=example_prompt,  # 单个示例的格式模板
    prefix="请按照以下示例的格式回答问题：",  # 前缀：告诉模型示例的作用（可选但建议加）
    suffix="输入:{question}\n输出:",  # 后缀：指定用户问题的输入位置和回答格式
    input_variables=["question"],  # 最终需要传入的变量（用户问题）
    example_separator="\n\n"  # 示例之间的分隔符，增强可读性
)

# ====================== 5. 测试Few-Shot提示词格式 ======================
# 格式化提示词：传入用户问题，生成包含示例的完整提示词
formatted_prompt = few_shot_prompt.format(question="苹果公司的总部在哪?")
print("=== 生成的Few-Shot提示词 ===")
print(formatted_prompt)
print("\n")

# ====================== 6. 构建少样本调用链并执行 ======================
# 构建链式调用：提示词模板 → 大模型
few_shot_chain = few_shot_prompt | model
# 调用链：传入用户问题，模型会参考示例格式回答
resp = few_shot_chain.invoke({"question": "langchain是什么?"})

# ====================== 7. 输出结果 ======================
print("=== 模型少样本回答结果 ===")
print("完整响应对象：", resp)
print("回答内容：", resp.content)

# ====================== 8. 补充Zero-Shot对比（无示例） ======================
# 零样本提示：无任何示例，直接让模型回答
zero_shot_prompt = PromptTemplate(
    input_variables=["question"],
    template="输入:{question}\n输出:"
)
zero_shot_chain = zero_shot_prompt | model
zero_shot_resp = zero_shot_chain.invoke({"question": "langchain是什么?"})

print("\n=== 模型零样本回答结果 ===")
print("回答内容：", zero_shot_resp.content)
