# ------------------------ 核心功能：LangChain + Milvus 向量库实战（嵌入+增删数据） ------------------------
# 演示场景：使用阿里云通义千问嵌入模型生成文本向量，将文档存入Milvus向量库，并实现数据删除
# 核心依赖：langchain-milvus（LangChain对接Milvus的适配器）、DashScopeEmbeddings（通义千问嵌入模型）
from langchain_community.embeddings import DashScopeEmbeddings  # 导入通义千问嵌入模型
from langchain_core.documents import Document                   # 导入LangChain的文档数据结构
from langchain_milvus import Milvus                             # 导入LangChain对接Milvus的向量库类

# ------------------------ 步骤1：初始化通义千问嵌入模型（生成文本向量） ------------------------
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",        # 指定嵌入模型版本：第二代通用文本嵌入模型（生成高质量向量）
    max_retries=3,                    # 请求失败时的重试次数：最多重试3次，提升稳定性
    dashscope_api_key="", # 通义千问API密钥（需替换为自己的有效密钥）
)

# ------------------------ 步骤2：初始化Milvus向量库（对接远程Milvus服务） ------------------------
vector_store = Milvus(
    embedding_function = embeddings,  # 绑定嵌入模型：文档会自动通过该模型生成向量
    connection_args= {"uri":"http://192.168.64.137:19530"}, # Milvus服务连接地址（IP+端口）
    collection_name="langchain_example", # Milvus集合名（相当于数据库表名）
)

# ------------------------ 步骤3：构造测试文档（LangChain标准Document格式） ------------------------
# Document是LangChain的标准文档结构，包含2个核心字段：
# - page_content：文档的文本内容（会被嵌入模型转为向量）
# - metadata：文档的元数据（标量信息，用于过滤检索，如来源、分类等）
document_1 = Document(
    page_content="I had chocalate chip pancakes and scrambled eggs for breakfast this morning.",
    metadata={"source": "tweet"},  # 元数据：文档来源是推特
)

document_2 = Document(
    page_content="The weather forecast for tomorrow is cloudy and overcast, with a high of 62 degrees.",
    metadata={"source": "news"},   # 元数据：文档来源是新闻
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

document_6 = Document(
    page_content="Is the new iPhone worth the price? Read this review to find out.",
    metadata={"source": "website"}, # 元数据：文档来源是网站
)

document_7 = Document(
    page_content="The top 10 soccer players in the world right now.",
    metadata={"source": "website"},
)

document_8 = Document(
    page_content="LangGraph is the best framework for building stateful, agentic applications!",
    metadata={"source": "tweet"},
)

document_9 = Document(
    page_content="The stock market is down 500 points today due to fears of a recession.",
    metadata={"source": "news"},
)

document_10 = Document(
    page_content="I have a bad feeling I am going to get deleted :(",
    metadata={"source": "tweet"},
)

# 将所有文档整合为列表，方便批量操作
documents = [
    document_1,
    document_2,
    document_3,
    document_4,
    document_5,
    document_6,
    document_7,
    document_8,
    document_9,
    document_10,
]

# ------------------------ 【注释段】步骤4：批量插入文档到Milvus向量库 ------------------------
# # 生成自定义文档ID：为每个文档分配唯一ID（1~10），方便后续删除/检索
# ids = [str(i+1) for i in range(len(documents))]
# print(ids)  # 打印ID列表：['1','2','3',...,'10']
#
# # 批量插入文档：LangChain会自动将page_content转为向量，metadata存入标量字段
# result = vector_store.add_documents(documents = documents,ids = ids)
# print(result)  # 打印插入结果：返回成功插入的文档ID列表

# ------------------------ 步骤5：删除Milvus中的指定文档 ------------------------
# delete方法：根据文档ID精准删除Milvus中的数据（需与插入时的ID对应）
result = vector_store.delete(ids = ["1"])  # 删除ID为"1"的文档（即document_1）
print(result)  # 打印删除结果：成功返回None/True，失败抛出异常
