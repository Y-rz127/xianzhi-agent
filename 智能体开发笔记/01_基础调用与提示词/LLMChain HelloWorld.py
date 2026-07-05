# ====================== 核心功能：使用 LLMChain 串联提示词模板与大模型，生成产品卖点文案 ======================
# 从 langchain_core.prompts 模块导入 PromptTemplate 类，用于构建标准化的提示词模板
from langchain_core.prompts import PromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（此处对接通义千问）
from langchain_openai import ChatOpenAI
# 从 langchain.chains 模块导入 LLMChain 类，用于串联「提示词模板」和「大模型」形成基础工作链
from langchain.chains import LLMChain
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露敏感信息
from pydantic import SecretStr

# 导入 main 模块中的 responses 变量（注：此处若 main 模块无对应定义，会报导入错误，保留原始代码结构）
from main import responses

# 1. 实例化 PromptTemplate 对象，创建自定义提示词模板
# 注意：变量名建议避免与类名重复（此处保留原始代码写法，实际开发中可改为 prompt_template）
PromptTemplate = PromptTemplate(
    input_variables=["name"],  # 声明模板中需要动态传入的变量名称，仅需传入产品名称 name
    template="""
    你是一个文案高手，专门为{name}设计文案，列举三个卖点
    """,  # 提示词模板字符串，{name} 为变量占位符，后续将被实际产品名称替换
)

# 2. 实例化 ChatOpenAI 对象，配置大模型连接参数与生成属性
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（此处为通义千问 qwen-plus 模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式的接口）
    api_key=SecretStr(""),  # 配置模型调用密钥，使用 SecretStr 安全封装
    temperature=0.7)  # 设置模型生成温度（取值 0-2），0.7 兼顾文案的创造性和合理性

# 3. 实例化 LLMChain 对象，串联提示词模板与大模型
# LLMChain 是 LangChain 基础链，核心作用是自动完成「模板填充 → 模型调用」的流程，无需手动分步执行
chain = LLMChain(llm=model, prompt=PromptTemplate)  # llm 参数指定大模型实例，prompt 参数指定提示词模板实例

# 4. 调用链的 invoke 方法，传入变量参数执行流程，获取结果
# 传入字典格式的参数，key 对应 prompt 模板中的 input_variables，value 为具体的产品名称
response = chain.invoke({"name": "智能手机"})

# 5. 打印最终结果
# LLMChain 执行后返回的结果是字典格式，默认以 "text" 为 key 存储大模型生成的核心文本内容
print(response["text"])
