# ====================== 大模型输出修复机制：OutputFixingParser 核心使用（项目级应用） ======================
# OutputFixingParser 核心价值：大模型返回结果可能不符合格式要求，该工具可自动修复格式错误并重新解析
# 支持设置重试次数，基于原始解析器约束，让大模型修正输出后再进行解析，提升结构化提取的成功率
# 若多次重试仍失败，常见原因：1.模型能力不足 2.网络异常导致输出不完整 3.提示词描述不具体、约束不明确
from langchain.output_parsers import OutputFixingParser  # 导入输出修复解析器
from langchain_core.output_parsers import PydanticOutputParser  # 原始结构化解析器
from langchain_openai import ChatOpenAI  # 大模型调用客户端
from pydantic import BaseModel, SecretStr  # 数据模型定义与密钥安全封装

# 1. 初始化项目所需的大模型实例（对接公司指定大模型服务）
model = ChatOpenAI(
    model="qwen-plus",  # 项目指定使用的大模型名称
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 项目对接的大模型服务接口地址
    api_key=SecretStr(""),  # 安全存储项目大模型API密钥（避免明文泄露）
    temperature=0.7)  # 控制大模型生成创造性，项目中可按需调整

# 2. 定义项目所需的结构化数据模型（约束演员信息的输出格式）
class Actor(BaseModel):
    name: str  # 演员名称（字符串类型，对应业务所需核心字段）
    film_names : list[str]  # 参演电视剧列表（字符串列表类型，约束输出结构）

# 3. 创建原始结构化解析器（关联Actor模型，定义基础解析规则）
parser = PydanticOutputParser(pydantic_object=Actor)
# 4. 用OutputFixingParser包装原始解析器（赋予错误修复能力，项目中用于提升解析成功率）
# 传入原始解析器和大模型实例，自动实现“错误检测-指令引导-模型重生成-重新解析”流程
fixing_parser = OutputFixingParser.from_llm(parser = parser, llm = model,max_retries=3) # 重试三次

# 5. 模拟项目中可能出现的大模型错误格式输出（如单引号、格式不规范等问题）
misformatted_output = """ {'name':'','film_names':['A计划','B计划']} """

# 注释：原始解析器直接解析错误格式会抛出异常（项目中未做容错时的问题场景）
# try:
#     parser.parse(misformatted_output) # 原始解析器无法识别单引号格式，解析失败报错 也可以作为兜底
# except Exception as e:
#  兜底数据
#     print(e)
#	  return Actor(name="未知演员", film_names=[])


# 6. 使用OutputFixingParser自动修复并解析（项目中核心容错逻辑，提升鲁棒性）
# 自动检测输出格式错误，引导大模型修正后，再用原始解析器完成结构化解析
fixed_data = fixing_parser.parse(misformatted_output)
# 解析结果转为字典（项目中便于后续数据存储、接口传输等业务操作）
print(fixed_data.model_dump())
