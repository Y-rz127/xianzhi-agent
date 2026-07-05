# ====================== 核心功能：使用 LangChain LCEL 管道符（|）快速串联组件，实现「提示词→模型→解析」一站式流程 ======================
# 从 langchain_core.prompts 模块导入 PromptTemplate 类，用于构建提示词模板
from langchain_core.prompts import PromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（此处对接阿里云通义千问）
from langchain_openai import ChatOpenAI
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露敏感信息
from pydantic import SecretStr
# 从 langchain_core.output_parsers 模块导入 StrOutputParser 类，用于将大模型返回的复杂对象解析为纯字符串
from langchain_core.output_parsers import StrOutputParser

# 1. 使用 PromptTemplate 类方法 from_template 快速创建提示词模板
# 传入带动态变量的模板字符串，自动推断 input_variables（此处推断出变量为 question）
prompt = PromptTemplate.from_template("回答你是一个IT助手，回答下面这个问题{question}")

# 2. 实例化 ChatOpenAI 对象，配置大模型的连接参数和生成属性
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（通义千问 qwen-plus 模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式的接口）
    api_key=SecretStr(""),  # 配置模型调用密钥，用 SecretStr 安全封装，防止明文暴露
    temperature=0.7)  # 设置模型生成温度（取值范围 0-2），0.7 表示生成内容兼具创造性和稳定性（值越高创造性越强，越低越严谨）

# 3. 实例化 StrOutputParser 字符串解析器
# 核心作用：屏蔽大模型返回对象的底层格式差异，自动提取核心文本内容，转换为纯 Python 字符串
parse = StrOutputParser()

# 4. 使用 LCEL 管道符（|）创建链式流程（核心特性：极简串联，按顺序执行）
# 执行流程：prompt（填充变量生成完整提示词）→ model（接收提示词调用大模型）→ parse（解析模型返回结果为纯字符串）
chain = prompt | model | parse

# 5.调用链的 invoke 方法，传入动态变量参数，执行完整流程
# 传入字典格式参数，key 对应提示词模板中的变量名 question，value 为具体的用户问题
result = chain.invoke({"question": "如何学习java"})

# 6. 打印最终解析后的纯字符串结果
print(result)
