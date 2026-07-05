# ====================== 核心功能：使用 StrOutputParser 字符串解析器，将大模型返回结果统一转为纯字符串格式 ======================
# 导入idlelib.undo模块的CommandSequence（注：该导入在当前代码中未实际使用，保留原始代码结构）
from idlelib.undo import CommandSequence

# 从 langchain_core.prompts 模块导入 PromptTemplate 类，用于快速构建基础提示词模板
from langchain_core.prompts import PromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（此处对接阿里云通义千问）
from langchain_openai import ChatOpenAI
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露敏感信息
from pydantic import SecretStr
# 从 langchain_core.output_parsers 模块导入多种解析器
# StrOutputParser：字符串解析器（核心使用），CommaSeparatedListOutputParser：逗号分隔列表解析器，JsonOutputParser：JSON格式解析器
from langchain_core.output_parsers import StrOutputParser,CommaSeparatedListOutputParser,JsonOutputParser

# 1. 使用 PromptTemplate 类方法 from_template 快速创建提示词模板
# 模板字符串中 {topic} 为动态变量，用于接收需要写诗的主题内容
prompt = PromptTemplate.from_template("写一首关于{topic}的诗")

# 2. 实例化 ChatOpenAI 大模型对象，配置连接参数与生成属性
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（通义千问 qwen-plus 模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式的接口）
    api_key=SecretStr(""),  # 配置模型调用密钥，使用 SecretStr 安全封装，防止明文暴露
    temperature=0.7)  # 设置模型生成温度（取值范围 0-2），0.7 兼顾诗歌的创造性和可读性（值越高创造性越强，越低越严谨）

# 3. 实例化 StrOutputParser 字符串解析器
# 核心本质：屏蔽不同大模型返回对象的底层格式差异，自动提取核心文本内容并转换为纯 Python 字符串
# 无需手动调用 response.content，解析器内部已自动完成核心文本提取
parse = StrOutputParser()

# 4. 使用 LCEL 管道符（|）串联组件，构建完整链式流程
# 执行流程：prompt（填充 topic 变量生成完整提示词）→ model（接收提示词调用大模型返回响应对象）→ parse（解析响应对象为纯字符串）
chain = prompt | model | parse

# 5. 调用链的 invoke 方法，传入动态变量参数执行完整流程
# 传入字典格式参数，key 对应提示词模板中的 {topic} 变量，value 为具体的写诗主题（此处为“如何学习java”）
result = chain.invoke({"topic": "如何学习java"})

# 6. 打印最终解析后的纯字符串结果
print(result)
