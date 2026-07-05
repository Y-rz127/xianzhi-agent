# AI文档助手综合实战：基于LangChain+Milvus+通义千问构建完整的RAG（检索增强生成）系统，
# 实现从网页加载Milvus官方文档、文本切分、向量入库、语义检索到智能回答的全流程，
# 最终为用户提供精准的Milvus文档问答服务
from langchain_community.document_loaders import WebBaseLoader  # 网页文档加载器，用于加载在线网页内容
from langchain_community.embeddings import DashScopeEmbeddings  # 阿里云百炼嵌入模型，将文本转为向量
from langchain_core.prompts import PromptTemplate  # 提示词模板，用于构建LLM的输入提示
from langchain_core.runnables import RunnablePassthrough  # 链式执行工具，透传用户问题到后续环节
from langchain_milvus import Milvus  # Milvus向量数据库集成，存储/检索向量
from langchain_openai import ChatOpenAI  # OpenAI兼容的大模型调用接口（适配通义千问）
from langchain_text_splitters import CharacterTextSplitter  # 文本分割器，将长文档切分为小片段
from pydantic import SecretStr  # 安全存储敏感信息（如API密钥），避免明文泄露

# ======================== 全局配置 ========================
# 定义Milvus向量数据库中的集合名称（相当于数据库表名），统一管理存储的文档向量
COLLECTION_NAME = "doc_qa_db"

# ======================== 步骤1：加载在线文档 ========================
# 初始化网页加载器，加载Milvus官方中文文档的多个核心页面
loader = WebBaseLoader(
    # 待加载的网页URL列表（Milvus概述、发布说明、快速开始）
    ["https://milvus.io/docs/zh/overview.md",
     "https://milvus.io/docs/zh/release_notes_md",
     "https://milvus.io/docs/zh/quickstart.md"],
    # 请求头配置：强制要求返回中文内容，避免加载到英文文档
    requests_kwargs={"headers": {"Accept-Language": "zh-CN"}}
)
# 执行加载，将网页内容转换为LangChain的Document对象（包含文本内容和元数据）
data = loader.load()

# ======================== 步骤2：文本分割（核心预处理） ========================
# 初始化字符文本分割器，解决长文本向量化效果差的问题
text_splitter = CharacterTextSplitter(
    chunk_size=1024,  # 每个文本片段的最大字符数（适配嵌入模型的输入限制）
    chunk_overlap=20  # 片段间重叠字符数（避免分割导致上下文断裂）
)
# 将加载的网页文档切分为多个小文本片段，提升后续检索的精准度
all_split = text_splitter.split_documents(data)

# ======================== 步骤3：初始化嵌入模型 ========================
# 初始化阿里云百炼文本嵌入模型，负责将文本片段转换为数值向量（Embedding）
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定第二代通用文本嵌入模型（兼顾效果和效率）
    max_retries=3,  # API调用失败时的最大重试次数（提升稳定性）
    dashscope_api_key="",  # 阿里云百炼API密钥（建议通过环境变量配置）
)

# ======================== 步骤4：向量数据库入库 ========================
# 方式1：简化版入库（注释备用）
# vector_storage = Milvus.from_documents(
#     documents = all_split,
#     embedding=embeddings,
#     collection_name=COLLECTION_NAME,
#     connection_args={"uri": "http://192.168.64.137:19530"})

# 方式2：自定义Milvus配置后入库（当前使用）
vector_storage = Milvus(
    embedding_function=embeddings,  # 指定向量生成的嵌入模型
    collection_name=COLLECTION_NAME,  # 指定存储的集合名称
    connection_args={"uri": "http://192.168.64.137:19530"},  # Milvus服务连接地址（IP+端口）
    drop_old=True  # 入库前删除同名旧集合（避免数据冗余，适合测试/迭代场景）
).from_documents(
    documents=all_split,  # 待入库的文本片段列表
    embedding=embeddings,  # 嵌入模型（与上方保持一致）
    collection_name=COLLECTION_NAME,  # 集合名称（与上方保持一致）
    connection_args={"uri": "http://192.168.64.137:19530"}  # 连接信息（与上方保持一致）
)

# 方式3：仅初始化Milvus连接（注释备用，适用于已入库场景）
# vector_storage = Milvus(
#     embedding_function=embeddings,
#     collection_name=COLLECTION_NAME,
#     connection_args={"uri": "http://192.168.64.137:19530"})

# ======================== 步骤5：测试基础相似性检索（注释备用） ========================
# 定义用户查询问题：获取Milvus的Docker安装命令
query = "docker怎么安装milvus，只告诉我命令就可以了"
# 执行基础相似性检索，返回Top3最相关的文档片段
# docs = vector_storage.similarity_search(query, k=3)
# 打印检索结果（注释备用，用于调试）
# print(docs)
# for doc in docs:
#     print(doc.page_content)

# ======================== 步骤6：初始化大语言模型（LLM） ========================
# 初始化通义千问大模型（通过OpenAI兼容接口调用），负责基于检索结果生成回答
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用通义千问plus模型（效果优于基础版）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云百炼兼容OpenAI的接口地址
    api_key=SecretStr(""),  # 安全存储API密钥（SecretStr避免明文打印）
    temperature=0.7  # 生成文本的随机性（0-1，0.7兼顾灵活性和准确性）
)

# ======================== 步骤7：构建RAG链式问答系统 ========================
# 将Milvus向量存储转换为检索器（Retriever），支持链式调用
retriever = vector_storage.as_retriever()

# 定义提示词模板（Prompt Template），规范LLM的回答逻辑和格式
prompt_template = """
        你是AI文档助手，使用如下上下文来回答最后的问题
        如果你不知道答案，就说你不知道，不要试图编造答案。
        最多使用10句话，并尽可能简洁的回答。总是在答案末尾说"谢谢你的提问!"
        {content}  # 占位符：填充检索到的相关文档内容
        问题:{question}  # 占位符：填充用户的查询问题
"""
# 将字符串模板转换为LangChain的PromptTemplate对象，便于后续链式调用
rag_prompt = PromptTemplate.from_template(
    template=prompt_template
)

# 构建完整的RAG链式流程：
# 1. {"content": retriever, "question": RunnablePassthrough()}：并行执行，retriever检索相关内容，RunnablePassthrough透传用户问题
# 2. | rag_prompt：将检索内容和问题填充到提示词模板中
# 3. | model：将填充后的提示词输入给LLM，生成最终回答
rag_chain = ({"content": retriever, "question": RunnablePassthrough()} | rag_prompt | model)

# 执行RAG链式调用，传入用户查询问题，获取最终回答
result = rag_chain.invoke(query)
# 打印AI生成的回答结果
print(result)
