# 该代码功能：基于指定产品名称，调用大模型生成面向年轻人的3条吸引人广告语
# 核心技术栈：LangChain（大模型应用框架） + 通义千问模型 + Pydantic（密钥安全管理） + 输出解析

# 从langchain_openai模块导入ChatOpenAI类（用于调用兼容OpenAI接口的大模型，此处对接通义千问）
from langchain_openai import ChatOpenAI
# 从langchain_core.prompts模块导入PromptTemplate类（用于构建标准化提示词模板）
from langchain_core.prompts import PromptTemplate
# 从pydantic模块导入SecretStr类（用于安全存储和管理敏感信息，如API密钥，避免明文泄露）
from pydantic import SecretStr
# 从langchain_core.output_parsers模块导入StrOutputParser类（用于将大模型返回结果解析为纯字符串格式）
from langchain_core.output_parsers import StrOutputParser

# 实例化ChatOpenAI对象，配置大模型连接参数，用于后续调用大模型
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的大模型名称（此处为通义千问qwen-plus模型）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 指定大模型服务的接口地址（阿里云通义千问兼容OpenAI格式的接口）
    api_key=SecretStr(""),  # 配置大模型调用密钥，使用SecretStr安全封装，避免明文暴露
    temperature=0.7  # 设置模型生成温度（取值0-2），0.7表示生成内容兼具创造性和稳定性（值越高创造性越强，越低越严谨）
)

# 创建提示词模板对象，用于标准化生成大模型的输入提示词
prompt_template = PromptTemplate(
    input_variables=["product"],  # 声明模板中需要动态传入的变量名称（此处仅需传入产品名称product）
    template="为{product}写三个吸引人的广告语，需要面向年青人",  # 固定提示词模板，{product}为变量占位符，后续将被实际产品名称替换
)

# 调用prompt_template的invoke方法，传入变量参数，生成完整的提示词对象
# 此处将product变量赋值为"HideOnBoss"，填充到模板占位符中，得到可直接传给大模型的提示词
prompt = prompt_template.invoke({"product":"HideOnBoss"})

# 调用大模型对象的invoke方法，传入完整提示词，发起模型调用，获取模型返回结果
# 该方法为同步调用，会等待模型返回结果后再执行后续代码
response = model.invoke(prompt)

# 注释：直接打印模型返回结果的content属性，也可获取广告语内容（与后续解析效果一致，此处注释备用）
# print(response.content)

# 实例化StrOutputParser字符串输出解析器，用于统一解析大模型返回结果为纯字符串
# 作用：屏蔽不同模型返回结果的格式差异，只提取核心文本内容
output_parser = StrOutputParser()

# 调用输出解析器的invoke方法，传入大模型返回的原始响应，解析得到纯字符串格式的广告语结果
answer = output_parser.invoke(response)

# 打印最终解析后的广告语结果
print(answer)
