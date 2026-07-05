# 导入所需的库和模块
# DashScopeEmbeddings：阿里云百炼提供的文本嵌入模型，用于将文本转换为向量
from langchain_community.embeddings import DashScopeEmbeddings
# Document：LangChain 中的文档对象，用于封装文本内容和元数据
from langchain_core.documents import Document
# Milvus：向量数据库 Milvus 的 LangChain 集成，用于存储和检索向量
from langchain_milvus import Milvus

# ======================== 初始化嵌入模型 ========================
# 创建 DashScopeEmbeddings 实例，用于生成文本的向量表示
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定使用的嵌入模型版本：第二代通用文本嵌入模型
    max_retries=3,  # API 调用失败时的最大重试次数，增强鲁棒性
    dashscope_api_key="",  # 阿里云百炼的 API 密钥（注意：实际使用时建议通过环境变量配置，避免硬编码）
)

# ======================== 构建示例文档数据 ========================
# 创建 Document 对象，每个对象包含文本内容（page_content）和元数据（metadata）
# 元数据可以用于标识文档来源、类型等附加信息
document_1 = Document(
    page_content="I had chocalate chip pancakes and scrambled eggs for breakfast this morning.",
    metadata={"source": "tweet"},  # 标记文档来源为推特
)

document_2 = Document(
    page_content="The weather forecast for tomorrow is cloudy and overcast, with a high of 62 degrees.",
    metadata={"source": "news"},  # 标记文档来源为新闻
)

document_3 = Document(
    page_content="Building an exciting new project with LangChain - come check it out!",
    metadata={"source": "tweet"},
)

document_4 = Document(
    page_content="Robbers broke into the city bank and stole $1 million in cash.",
    metadata={"source": "news"},
)

document_5 = Document(
    page_content="Wow! That was an amazing movie. I can't wait to see it again.",
    metadata={"source": "tweet"},
)

# 将所有 Document 对象整合为一个列表，方便批量处理
documents = [
    document_1,
    document_2,
    document_3,
    document_4,
    document_5
]

# 为每个文档生成唯一的 ID（字符串类型），ID 从 1 开始递增
ids = [str(i + 1) for i in range(len(documents))]
print(f"生成的文档 ID 列表：{ids}")  # 打印 ID 列表，用于调试验证

# ======================== 将文档存入 Milvus 向量数据库 ========================
# 调用 Milvus.from_documents 方法，将文档转换为向量并批量插入 Milvus
# 该方法会自动完成：文本 -> 向量（通过 embeddings 模型）-> 存入 Milvus
vector_storage = Milvus.from_documents(
    documents = documents,  # 待插入的文档列表
    embedding=embeddings,   # 用于生成向量的嵌入模型
    collection_name="retriever_test",  # Milvus 中的集合名称（相当于数据库中的表名）
    connection_args={"uri": "http://192.168.64.137:19530"}  # Milvus 服务的连接地址和端口
)

# ======================== 基于向量的相似性检索 ========================
# 将 Milvus 存储转换为检索器（Retriever），支持两种检索方式：
# 1. 相似性检索（默认）：返回最相似的 k 个结果
# 2. MMR（Maximum Marginal Relevance）：最大边际相关性检索，在相似性基础上保证结果的多样性

# 方式1：普通相似性检索（注释掉，备用）
# retriever = vector_storage.as_retriever(search_kwargs={"k": 3})

# 方式2：MMR 多样性检索（启用）
retriever = vector_storage.as_retriever(
    search_kwargs={"k": 3},  # 检索参数：返回 Top 3 个结果
    search_type="mmr"        # 检索类型：MMR（平衡相似性和多样性）
)

# 执行检索：传入查询语句，检索与 "What is LangChain?" 最相关的文档
result = retriever.invoke("What is LangChain?")

# 遍历并打印检索结果
for r in result:
    print(f"文档内容:{r.page_content}, 元数据:{r.metadata}")
