# ------------------------ 核心功能：LangChain + Milvus 向量检索进阶（MMR检索） ------------------------
# 演示场景：基于通义千问嵌入模型生成文本向量，将文档存入Milvus后，实现普通相似性检索、带分数的相似性检索，以及MMR（最大边际相关性）检索
# MMR核心价值：在保证相似度的同时，提升检索结果的多样性，避免结果高度重复
from langchain_community.embeddings import DashScopeEmbeddings  # 导入通义千问文本嵌入模型
from langchain_core.documents import Document                   # 导入LangChain标准文档结构
from langchain_milvus import Milvus                             # 导入LangChain对接Milvus的向量库类

# ------------------------ 步骤1：初始化通义千问嵌入模型 ------------------------
# 作用：将自然语言文本转换为数值向量（用于Milvus的向量相似性计算）
embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",        # 指定嵌入模型版本：第二代通用文本嵌入模型（效果更优）
    max_retries=3,                    # API请求失败后的重试次数：提升请求稳定性
    dashscope_api_key="", # 阿里云通义千问API密钥（需替换为自己的有效密钥）
)

# ------------------------ 步骤2：构造测试文档集 ------------------------
# Document是LangChain的标准化文档对象，包含两个核心部分：
# - page_content：文档的核心文本内容（会被嵌入模型转为向量）
# - metadata：文档的元数据（标量信息，如来源、分类等，用于过滤/溯源）
document_1 = Document(
    page_content="I had chocalate chip pancakes and scrambled eggs for breakfast this morning.",
    metadata={"source": "tweet"},  # 元数据：文档来源为推特
)

document_2 = Document(
    page_content="The weather forecast for tomorrow is cloudy and overcast, with a high of 62 degrees.",
    metadata={"source": "news"},   # 元数据：文档来源为新闻
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

# 将所有文档整合为列表，方便批量操作
documents = [
    document_1,
    document_2,
    document_3,
    document_4,
    document_5
]

# ------------------------ 步骤3：生成自定义文档ID ------------------------
# 为每个文档生成唯一ID（1~5），格式为字符串（Milvus主键常用字符串类型）
# 作用：方便后续精准删除、检索溯源，若不指定则Milvus会自动生成ID
ids = [str(i + 1) for i in range(len(documents))]
print(ids)  # 打印ID列表：输出 ['1', '2', '3', '4', '5']

# ------------------------ 【注释段】方式1：快速初始化Milvus并插入文档（一键式） ------------------------
# # from_documents是Milvus类的快捷方法：自动完成「文档嵌入→创建集合→插入数据」全流程
# # 无需手动初始化Milvus再调用add_documents，适合快速开发
# vector_storage = Milvus.from_documents(
#     documents = documents,          # 待插入的文档列表
#     embedding=embeddings,           # 绑定的嵌入模型
#     collection_name="mmr_test",     # Milvus集合名（表名）
#     connection_args={"uri": "http://192.168.64.137:19530"}) # Milvus连接地址

# ------------------------ 步骤4：手动初始化Milvus向量库（更灵活） ------------------------
# 手动初始化方式：可自定义更多参数（如索引、分片等），适合精细化控制
vector_store = Milvus(
    embedding_function=embeddings,  # 绑定嵌入模型（检索时会自动将查询文本转为向量）
    connection_args={"uri": "http://192.168.64.137:19530"}, # Milvus服务连接地址
    collection_name="langchain_example", # 指定操作的集合名（需确保该集合已存在/已插入数据）
)

# ------------------------ 【注释段】检索1：基础相似性检索（仅返回文档） ------------------------
# # 相似性检索：根据查询文本的向量，返回最相似的k个文档（默认按相似度降序）
# query = "I had chocalate chip pancakes and scrambled eggs for breakfast this morning."
# result = vector_store.similarity_search(query,k=2)  # k=2：返回前2个最相似的文档
# for i in result:
#     print(f"内容：{i.page_content},元数据:{i.metadata}")  # 打印文档内容和元数据

# ------------------------ 【注释段】检索2：带相似度分数的相似性检索 ------------------------
# # similarity_search_with_score：返回文档+相似度分数（分数越小，相似度越高）
# # 相比基础检索，可直观判断匹配程度，适合需要量化相似度的场景
# query = "I had chocalate chip pancakes and scrambled eggs for breakfast this morning."
# result = vector_store.similarity_search_with_score(query,k=2)
# for i in result:
#     # i[0]是Document对象（内容+元数据），i[1]是相似度分数
#     print(f"内容：{i[0].page_content},元数据:{i[0].metadata},分数:{i[1]}")

# ------------------------ 核心检索：MMR（最大边际相关性）检索 ------------------------
# MMR检索：在保证相似度的前提下，最大化结果的多样性，避免检索结果高度重复
# 适用场景：推荐系统、问答系统（需要覆盖更多相关维度，而非仅最相似）
query = "I had chocalate chip pancakes and scrambled eggs for breakfast this morning."
result = vector_store.max_marginal_relevance_search(
    query=query,          # 检索查询文本
    k=3,                  # 最终返回的文档数量
    fetch_k=10,           # 先检索出最相似的10个文档（候选集），再从中选k个多样性最高的
    lambda_mult=0.4       # 平衡参数：0~1，越接近1越侧重相似度，越接近0越侧重多样性
)
# 遍历并打印MMR检索结果
for i in result:
    print(f"内容：{i.page_content},元数据:{i.metadata}")
