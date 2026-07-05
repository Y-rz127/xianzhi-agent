# 核心功能：演示通过 MultiQueryRetriever（多查询检索器）优化向量检索效果，通过LLM自动生成多个不同角度的查询语句，
# 扩大检索范围并融合结果，从而提升检索的召回率和准确率（目标提升约30%）
import logging

# 导入多查询检索器（核心组件，用于生成多视角查询提升检索效果）
from langchain.retrievers import MultiQueryRetriever
# 导入文档加载器：TextLoader加载本地文本文件，RecursiveUrlLoader加载网页内容（此处仅用TextLoader）
from langchain_community.document_loaders import TextLoader, RecursiveUrlLoader
# 导入阿里云百炼嵌入模型，用于文本向量化
from langchain_community.embeddings import DashScopeEmbeddings
# 导入Milvus向量数据库集成，用于存储和检索向量
from langchain_milvus import Milvus
# 导入ChatOpenAI大模型，用于生成多视角查询语句
from langchain_openai import ChatOpenAI
# 导入递归字符文本分割器，用于将长文档切分为小片段
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 导入SecretStr，用于安全存储API密钥（避免明文泄露）
from pydantic import SecretStr

# ======================== 日志配置 ========================
# 设置日志系统的基础配置（默认输出到控制台）
logging.basicConfig()
# 将MultiQueryRetriever的日志级别设置为INFO，便于查看其生成的多查询语句等关键信息
logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)

# ======================== 文档加载与预处理 ========================
# 初始化文本加载器，加载本地UTF-8编码的qa.txt文件（存储待检索的问答数据）
loader = TextLoader("data/qa.txt", encoding="utf-8")
# 加载文件内容为LangChain的Document对象
data = loader.load()

# 初始化递归字符文本分割器（适合中文文本分割）
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=100,  # 每个文本片段的最大字符数（小片段提升检索精准度）
    chunk_overlap=10  # 片段间重叠字符数（避免分割导致上下文丢失）
)
# 将加载的长文档切分为多个小文本片段
splits = text_splitter.split_documents(data)

# ======================== 嵌入模型初始化 ========================
# 初始化阿里云百炼文本嵌入模型，将文本转换为向量表示
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定第二代通用文本嵌入模型（兼顾效果和效率）
    max_retries=3,  # API调用失败时的最大重试次数（提升稳定性）
    dashscope_api_key="",  # 阿里云百炼API密钥（建议通过环境变量配置）
)

# ======================== 向量数据库入库 ========================
# 将切分后的文本片段转换为向量，并批量存入Milvus向量数据库
vector_storage = Milvus.from_documents(
    documents=splits,  # 待入库的文本片段列表
    embedding=embeddings,  # 用于生成向量的嵌入模型
    collection_name="multi_query_tesr",  # Milvus中的集合名称（注意：原代码拼写错误，应为multi_query_test）
    connection_args={"uri": "http://192.168.64.137:19530"}  # Milvus服务的连接地址和端口
)

# ======================== 检索配置 ========================
# 待检索的目标问题（核心查询）
question = "老王不知道为什么抽筋了？"

# 初始化大语言模型（用于生成多视角查询语句）
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用通义千问plus模型（效果较好）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云百炼兼容OpenAI接口的地址
    api_key=SecretStr(""),  # 安全存储API密钥（SecretStr避免明文打印）
    temperature=0.7  # 生成文本的随机性（0-1，0.7兼顾多样性和准确性）
)

# 初始化多查询检索器（核心优化组件）
# 原理：基于原始问题，通过LLM自动生成多个语义相似但表述不同的查询语句，分别检索后融合结果
retriever_from_llm = MultiQueryRetriever.from_llm(
    retriever=vector_storage.as_retriever(),  # 基础向量检索器（Milvus）
    llm=model  # 用于生成多查询语句的大模型
)

# ======================== 执行检索并输出结果 ========================
# 执行多查询检索，获取与问题相关的文档结果
results = retriever_from_llm.invoke(question)
# 打印检索到的文档数量（便于评估召回率）
print(f"检索到的文档数量：{len(results)}")

# 遍历并打印每个检索结果的内容和元数据
for result in results:
    print(f"内容:{result.page_content},元数据:{result.metadata}"
