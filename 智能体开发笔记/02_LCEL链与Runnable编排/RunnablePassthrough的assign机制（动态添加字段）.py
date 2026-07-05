# 核心功能：演示LangChain中RunnablePassthrough的assign机制（动态添加字段），并结合Milvus向量库构建完整RAG系统
# 核心逻辑：在链式执行中动态生成/补充字段（如检索上下文、透传用户问题），为LLM提供完整的输入信息
from langchain_community.embeddings import DashScopeEmbeddings  # 阿里云百炼嵌入模型，文本转向量
from langchain_core.documents import Document  # LangChain文档对象，封装文本和元数据
from langchain_core.prompts import ChatPromptTemplate  # 提示词模板，构建LLM输入
from langchain_core.runnables import RunnablePassthrough  # 透传/动态字段组件，核心实现assign功能
from langchain_milvus import Milvus  # Milvus向量数据库集成，存储/检索向量
from langchain_openai import ChatOpenAI  # OpenAI兼容接口，调用通义千问模型
from pydantic import SecretStr  # 安全存储API密钥
import os

# ======================== LangSmith配置（可选，链路追踪） ========================
# 开启LangChain链路追踪，用于调试/监控RAG流程的执行过程
os.environ["LANGCHAIN_TRACING_V2"]="true"
os.environ["LANGCHAIN_ENDPOINT"]="https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"]="agent_v1"

# ======================== assign机制基础示例（注释说明核心用法） ========================
# RunnablePassthrough().assign() 核心作用：在输入数据基础上，动态添加新字段（由自定义函数生成）
# 示例1：动态添加processed字段，值为num字段的2倍
# chain = RunnablePassthrough().assign(processed=lambda x: x["num"] * 2)
# output = chain.invoke({"num": 5})  # 执行后输出：{"num":5, "processed":10}
# print(output)


# 示例2：RAG场景中动态添加context字段（检索文档）
# chain = RunnablePassthrough().assign(
#     context=lambda x : retrieve_documents({x["question"]})  # 动态生成context字段（检索结果）
# ) | prompt | llm  # 拼接提示词+LLM生成回答

# 自定义检索函数（模拟从本地读PDF/查数据库/查本地文件找答案）
def retrieve_documents(question):
    # 模拟检索：比如用户问“张三是谁”，返回相关文档内容
    if "张三" in question:
        return "张三是XX公司的产品经理，负责LangChain项目落地"
    else:
        return "未找到相关文档"

# 示例2输入：{"question":"langchain是什么?"}
# 执行后输入会自动补充context字段，最终传给prompt的是：{"question":"langchain是什么?", "context":"检索到的文档"}
# input_data = {"question":"langchain是什么?"}
# response = chain.invoke(input_data)

# ======================== 初始化嵌入模型 ========================
# 创建阿里云百炼嵌入模型实例，用于将文本转换为向量
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 第二代通用文本嵌入模型
    max_retries=3,  # API调用失败重试次数，提升稳定性
    dashscope_api_key="",  # 阿里云百炼API密钥（建议环境变量配置）
)

# ======================== 构建示例文档 ========================
# 创建Document对象，每个对象包含文本内容（page_content）和元数据（metadata）
document_1 = Document(
    page_content="I had chocalate chip pancakes and scrambled eggs for breakfast this morning.",
    metadata={"source": "tweet"},  # 标记文档来源为推特
)

document_2 = Document(
    page_content="The weather forecast for tomorrow is cloudy and overcast, with a high of 62 degrees.",
    metadata={"source": "news"},  # 标记文档来源为新闻
)

# 整合文档列表，用于批量入库
documents = [document_1, document_2]

# ======================== 向量数据库入库 ========================
# 将文档转换为向量，并批量存入Milvus向量数据库
vector_storage = Milvus.from_documents(
    documents=documents,  # 待入库的文档列表
    embedding=embeddings,  # 用于生成向量的嵌入模型
    collection_name="runnable_test1",  # Milvus集合名称（表名）
    connection_args={"uri": "http://192.168.64.137:19530"}  # Milvus服务连接地址
)

# ======================== 构建检索器 ========================
# 将Milvus存储转换为检索器（Retriever），支持链式调用
# search_kwargs={"k":3}：检索时返回最相似的3个文档（此处示例只有2个文档，实际返回2个）
retriever = vector_storage.as_retriever(search_kwargs={"k": 3})

# ======================== 构建提示词模板 ========================
# 定义RAG提示词模板，包含两个占位符：content（检索上下文）、question（用户问题）
prompt = ChatPromptTemplate.from_template(
    " 基于上下文回答：{content}\t问题:{question}"
)

# ======================== 初始化大语言模型 ========================
model = ChatOpenAI(
    model="qwen-plus",  # 指定通义千问plus模型
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云百炼兼容OpenAI的接口地址
    api_key=SecretStr(""),  # 安全存储API密钥
    temperature=0.7  # 生成文本的随机性，0.7兼顾灵活性和准确性
)

# ======================== 构建完整RAG链（核心体现assign/透传逻辑） ========================
# 核心逻辑拆解：
# 1. {"content":retriever, "question": RunnablePassthrough()}：
#    - content字段：由retriever检索生成（相当于动态添加检索上下文）
#    - question字段：由RunnablePassthrough()透传用户输入的问题（不做修改）
#    这是assign机制的简化写法，等价于 RunnablePassthrough().assign(content=retriever)
# 2. | prompt：将content和question填充到提示词模板中
# 3. | model：将填充后的提示词输入给LLM，生成最终回答
chain = {"content":retriever, "question": RunnablePassthrough()} | prompt |  model

# ======================== 执行RAG链并输出结果 ========================
# 传入用户问题，执行完整RAG流程
result = chain.invoke("LangChain支持java吗？")
# 打印LLM生成的回答
print(result)
