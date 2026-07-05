# ====================== 第一部分：基础演示 - 逗号分隔列表解析器 + 提示词格式指令注入 ======================
# 从 langchain_core.output_parsers 模块导入 CommaSeparatedListOutputParser 类
# 该解析器的核心作用：将大模型返回的逗号分隔字符串，解析为 Python 列表（list）对象
from langchain_core.output_parsers import CommaSeparatedListOutputParser
# 从 langchain_core.prompts 模块导入 ChatPromptTemplate 类，用于构建聊天类型提示词模板
from langchain_core.prompts import ChatPromptTemplate

# 1. 实例化逗号分隔列表解析器
# 注释：JsonOutputParser() 是另一种解析器，用于将模型返回结果解析为 JSON 格式对象（此处展示逗号解析器）
# parser = JsonOutputParser() 创建json解析器 解析成json
parser = CommaSeparatedListOutputParser()

# 2. 获取解析器对应的格式指令（核心本质：生成一段「格式要求提示词」，用于约束大模型输出格式）
# 该方法会自动生成大模型可识别的自然语言提示词（例如："请将你的回答用逗号分隔，不要包含其他额外符号或文本"）
# 这段提示词最终会被添加到我们的自定义模板中，让大模型按格式返回，确保后续解析器能正常工作
format_instructions = parser.get_format_instructions()

# 3. 定义聊天提示词模板
# 模板中包含两个动态变量：{review} 接收商品评论内容，{format_instructions} 接收解析器的格式要求
prompt = ChatPromptTemplate.from_template("""
    分析以下商品评论，按指定格式返回结果：
    评论内容：{review}
    格式要求:{format_instructions}
""")

# 4. 注入格式指令（使用 partial 方法进行部分变量填充）
# partial 方法：预先填充模板中的部分固定变量（此处为 format_instructions），后续只需填充剩余变量（review）
# 好处：避免重复传入固定不变的参数，提升代码复用性
final_prompt = prompt.partial(format_instructions=format_instructions)

# 5. 填充所有剩余变量，生成完整提示词
# format_prompt 方法：填充模板中未被 partial 预先填充的变量（此处为 review），返回标准化提示词对象
# 打印完整提示词，可查看包含格式要求的最终提问内容
print(final_prompt.format_prompt(review="这个手机很棒"))

# ====================== 第二部分：实战演示 - 逗号分隔列表解析器 + LCEL 链式流式输出 ======================
# 从 langchain_core.prompts 模块导入 PromptTemplate 类，用于构建基础提示词模板
from langchain_core.prompts import PromptTemplate
# 从 langchain_openai 模块导入 ChatOpenAI 类，用于调用兼容 OpenAI 接口的大模型（对接通义千问）
from langchain_openai import ChatOpenAI
# 从 pydantic 模块导入 SecretStr 类，用于安全封装 API 密钥，避免明文泄露
from pydantic import SecretStr
# 从 langchain_core.output_parsers 模块导入逗号分隔列表解析器（实战使用）
from langchain_core.output_parsers import CommaSeparatedListOutputParser

# 1. 实例化 ChatOpenAI 大模型对象，配置相关参数
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的大模型名称（通义千问 qwen-plus）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 大模型服务接口地址（阿里云通义千问兼容 OpenAI 格式）
    api_key=SecretStr(""),  # 安全封装 API 密钥，防止明文暴露
    streaming=True,  # 关键参数：设置为 True 开启流式输出功能，模型分段返回生成结果
    temperature=0.7)  # 生成温度（0-2），0.7 兼顾生成内容的创造性和稳定性

# 2. 实例化逗号分隔列表解析器（用于将模型返回的逗号分隔字符串转为 Python 列表）
out_parser = CommaSeparatedListOutputParser()

# 3. 获取解析器的格式指令
# 自动生成格式要求，告诉大模型需要以“逗号分隔”的形式返回结果，确保解析器能正常解析
format_instructions = out_parser.get_format_instructions()

# 4. 创建基础提示词模板
prompt = PromptTemplate(
    template="""
    列举多个常见的{topic}场景。{format_instructions}
    """,  # 模板字符串：{topic} 接收主题变量，{format_instructions} 接收解析器格式指令
    input_variables=["topic"],  # 声明需要动态传入的变量（仅 topic，format_instructions 为固定参数）
    partial_variables={"format_instructions": format_instructions}  # 预先填充固定变量 format_instructions
)

# 5. 使用 LCEL 管道符（|）串联组件，构建完整链式流程
# 执行流程：prompt（填充 topic 生成完整提示词）→ model（流式调用大模型返回片段）→ out_parser（解析片段为列表元素）
chain = prompt | model | out_parser

# 6. 调用链的 stream 方法，实现流式输出
# 传入动态变量 topic = "电影"，遍历流式返回的解析结果（每个 token 是列表中的单个元素）
for token in chain.stream({"topic": "电影"}):
    # 实时打印每个解析后的列表元素
    print(token)
