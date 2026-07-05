# ====================== 核心功能：使用 LangChain LCEL 实现大模型流式输出，实时返回内容片段 ======================
# 从 langchain_core.prompts 模块导入提示词模板类，支持构建基础模板和聊天模板
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（此处对接阿里云通义千问）
from langchain_openai import ChatOpenAI
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露敏感信息
from pydantic import SecretStr
# 从 langchain_core.output_parsers 模块导入 StrOutputParser 类，用于将模型返回的复杂对象解析为纯字符串
from langchain_core.output_parsers import StrOutputParser

# 1. 使用 ChatPromptTemplate 类方法 from_template 快速创建聊天提示词模板
# 注意：原始代码中变量名与类名重复（ChatPromptTemplate = ChatPromptTemplate.from_template），保留原始写法，实际开发中建议改为 prompt = ChatPromptTemplate.from_template(...)
# 模板字符串中 {concept} 为动态变量，用于接收需要解释/介绍的知识点名称
prompt = ChatPromptTemplate = ChatPromptTemplate.from_template("用100个字解释下面的知识点或者介绍:{concept}")

# 2. 实例化 ChatOpenAI 对象，配置大模型参数（重点开启流式输出）
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（通义千问 qwen-plus 模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式接口）
    api_key=SecretStr(""),  # 配置模型调用密钥，用 SecretStr 安全封装，防止明文暴露
    streaming=True,  # 关键参数：设置为 True 开启大模型流式输出功能，模型会分段返回生成结果
    temperature=0.7)  # 设置模型生成温度（取值 0-2），0.7 兼顾生成内容的创造性和稳定性

# 注释：直接调用模型的 stream 方法实现流式输出（此处注释备用，展示单独使用模型流式输出的写法）
# 遍历模型流式返回的内容片段（chunk 为模型返回的单个片段对象）
# for chunk in model.stream("讲一个隔壁老王的故事"):
#     # 打印每个片段的核心文本内容
#     print(chunk.content)

# 3. 使用 LCEL 管道符（|）串联组件，构建完整的流式处理链
# 执行流程：prompt（填充变量生成完整提示词）→ model（流式调用大模型返回片段）→ StrOutputParser()（解析每个片段为纯字符串）
chain = prompt | model | StrOutputParser()

# 4. 调用链的 stream 方法，传入动态变量，实现链式流式输出
# 传入字典格式参数，key 对应模板中的 {concept} 变量，value 为要解释的知识点（此处为“多线程”）
# 遍历链流式返回的纯字符串片段（chunk 为解析后的单个字符串片段）
for chunk in chain.stream({"concept":"多线程"}):
    # 实时打印每个字符串片段，实现类似“打字机”的实时输出效果
    print(chunk, end="", flush=True)  # end="" 取消默认换行，flush=True 强制刷新输出缓冲区，确保实时显示
