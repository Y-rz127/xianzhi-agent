# ====================== PydanticOutputParser 基本使用（大模型结构化信息提取） ======================
# 导入项目所需核心依赖
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate  # 提示词模板构建工具
from langchain_openai import ChatOpenAI  # 大模型调用客户端
from pydantic import SecretStr, BaseModel, Field  # 数据模型定义与密钥安全封装
from langchain_core.output_parsers import PydanticOutputParser  # 结构化输出解析器

# 1. 初始化大模型实例（项目中用于调用大模型能力）
model = ChatOpenAI(
    model="qwen-plus",  # 指定项目使用的大模型名称
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 项目对接的大模型服务接口地址
    api_key=SecretStr(""),  # 安全存储项目的大模型API密钥
    temperature=0.7)  # 控制大模型生成内容的创造性（项目中可按需调整）

# 2. 定义Pydantic数据模型（项目中约束用户信息的结构化输出格式）
class UserInfo(BaseModel):
    name: str = Field(..., title="Name of the user")  # 用户名（必填字段）
    age: int = Field(..., title="Age of the user", ge=18)  # 年龄（必填，且大于等于18岁）
    hobby : str = Field(..., title="Hobby of the user")  # 爱好（必填字段）

# 3. 创建Pydantic输出解析器（项目中用于将大模型输出转为结构化数据）
parse = PydanticOutputParser(pydantic_object=UserInfo)
# 构建聊天提示词模板（项目中引导大模型提取用户信息并遵守指定格式）
prompt = ChatPromptTemplate.from_template(
    "你是一个文本助手，提取用户信息:{input}，必须遵守格式{format_instructions}")

# 预先注入格式指令（项目中避免重复传递，提升链式调用效率）
prompt = prompt.partial(format_instructions = parse.get_format_instructions())

# 4. 构建LCEL链式调用（项目中标准化流程：提示词→大模型→结构化解析）
chain = prompt | model | parse
# 传入用户文本，执行信息提取（项目中实际使用时可替换为业务输入数据）
response = chain.invoke({"input": "我的名称是老王，今年18岁，喜欢看电影，打篮球和写代码。我下午要去看我大学老师!"})
print(response)  # 打印结构化提取结果
print(type(response))  # 打印结果类型（UserInfo模型实例）
# 模型实例转为字典（项目中便于后续数据存储、接口传输等业务操作）
print(response.model_dump())


# ---------------------- 项目实战：大模型情感分析系统（结构化输出） ----------------------
# 定义情感分析结果的数据模型（项目中约束情感分析的输出结构）
class SentimentResult(BaseModel):
    sentiment : str  # 情感倾向（如正面/负面/中性，项目中用于业务判断）
    confidence : float  # 情感判断置信度（0-1，项目中用于评估结果可靠性）
    keyword : list[str]  # 情感相关关键词（项目中用于文本特征提取）

# 创建情感分析专用解析器（关联情感分析数据模型）
parse = PydanticOutputParser(pydantic_object=SentimentResult)
# 构建情感分析提示词模板并预先注入格式指令（项目中标准化情感分析引导语）
prompt = (ChatPromptTemplate.from_template(
    "请对下面这句话进行情感分析：{input}，并给出关键词，必须遵守格式{format_instructions}")
          .partial(format_instructions = parse.get_format_instructions()))
# 构建情感分析链式调用流程
chain = prompt | model | parse
# 传入待分析文本（项目中可替换为业务中的评论、反馈等文本数据）
response = chain.invoke({"input": "商品很好!"})
print(response)  # 打印情感分析结构化结果
print(response.model_dump())  # 转为字典，用于项目内数据处理
print(response.model_dump_json())  # 转为JSON字符串，用于项目接口返回或文件存储
