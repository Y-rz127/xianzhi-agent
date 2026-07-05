# ====================== 核心功能：使用 JsonOutputParser 解析器，将大模型返回结果转为标准 JSON 格式并可直接按键取值 ======================
# 从 langchain_core.prompts 模块导入 PromptTemplate 类，用于构建基础提示词模板
from langchain_core.prompts import PromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（此处对接阿里云通义千问）
from langchain_openai import ChatOpenAI
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露敏感信息
from pydantic import SecretStr
# 从 langchain_core.output_parsers 模块导入多种解析器
# StrOutputParser：纯字符串解析器，CommaSeparatedListOutputParser：逗号分隔列表解析器，JsonOutputParser：JSON格式解析器（核心使用）
from langchain_core.output_parsers import StrOutputParser,CommaSeparatedListOutputParser,JsonOutputParser

# 注释：原始备用提示词模板（手动指定JSON结构，此处保留原始代码结构，未实际使用）
# prompt = PromptTemplate.from_template("返回JSON:{{'name':'姓名','age':'年龄'}},输入:{input}")
# 说明：模板中使用 {{ }} 是转义写法，最终会渲染为单个 { }，用于指定JSON格式中的大括号

# 1. 实例化 ChatOpenAI 大模型对象，配置连接参数与生成属性
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（通义千问 qwen-plus 模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式的接口）
    api_key=SecretStr(""),  # 配置模型调用密钥，使用 SecretStr 安全封装，防止明文暴露
    temperature=0.7)  # 设置模型生成温度（取值范围 0-2），0.7 兼顾回答的准确性和灵活性（值越低回答越严谨，更易生成标准JSON）

# 2. 实例化 JsonOutputParser JSON 解析器
# 核心本质：1. 自动识别大模型返回的 JSON 格式字符串，将其转换为 Python 可直接操作的字典（dict）对象
#          2. 若大模型返回非标准 JSON，会尝试容错解析；若完全不符合 JSON 格式，会抛出解析异常
parse = JsonOutputParser()

# 注释：原始备用链式调用（此处保留原始代码结构，未实际使用）
# chain = prompt | model | parse
# print(chain.invoke({"input":"我叫小王，今年18岁"}))

# 3. 构建提示词模板（核心：明确要求大模型返回指定结构的 JSON 格式，确保 JsonOutputParser 能正常解析）
# 模板中通过清晰的 JSON 示例结构，约束大模型返回包含 "answer"（答案文本）和 "confidence"（0-1区间置信度）的 JSON
# 问题:{question} 为动态变量，用于接收用户的具体问题
prompt = PromptTemplate.from_template("""
    回答以下问题，返回json格式:
    {{
        "answer":"答案文本",
        "confidence": 置信度(0-1)
    }}
    问题:{question}
""")

# 4. 使用 LCEL 管道符（|）串联组件，构建完整链式流程
# 执行流程：prompt（填充 question 变量生成含 JSON 格式要求的完整提示词）→ model（调用大模型返回 JSON 格式字符串响应）→ parse（将 JSON 字符串解析为 Python 字典）
chain = prompt | model | parse

# 5. 调用链的 invoke 方法，传入具体问题执行流程，获取解析后的 Python 字典结果
# 传入字典格式参数，key 对应模板中的 {question} 变量，value 为具体问题（此处为“地球的半径是多少?”）
result = chain.invoke({"question": "地球的半径是多少?"})

# 6. 打印解析后的完整字典结果（可直观看到 JSON 解析后的键值对结构）
print(result)

# 7. 按键取值，分别获取答案文本和置信度，实现精准数据提取与使用
# 由于 result 是 Python 字典对象，可直接通过 ["key"] 的方式获取对应值，方便后续业务逻辑处理
print(f"答案:{result['answer']},置信度:{result['confidence']}")
