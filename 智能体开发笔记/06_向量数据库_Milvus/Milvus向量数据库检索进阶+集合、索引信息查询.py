# ------------------------ 核心功能：Milvus向量数据库检索进阶+集合/索引信息查询 ------------------------
# 演示场景：图书向量检索（带过滤/分页）、批量向量查询、查询集合结构/索引详情
from pymilvus import connections, db, MilvusClient, FieldSchema, DataType, CollectionSchema, Collection
import random  # 用于生成随机查询向量

# ------------------------ 步骤1：初始化Milvus客户端（连接远程Milvus服务） ------------------------
# uri：Milvus服务的IP+端口（需替换为实际部署地址）
client = MilvusClient(uri="http://192.168.64.137:19530")

# ------------------------ 步骤2：生成随机查询向量（模拟用户检索的图书简介向量） ------------------------
# 生成4维随机向量（需与book集合中book_intro字段的dim=4一致）
# _ 是占位符，表示循环4次但不使用循环变量
query_vector = [random.random() for _ in range(4)]

# ------------------------ 核心检索：带标量过滤的向量相似性搜索 ------------------------
result = client.search(
    collection_name = "book",          # 目标集合名（图书库）
    data = [query_vector],             # 查询向量（列表格式，支持批量查询）
    filter = "category == 'Python'",   # 标量过滤条件：仅检索Python分类的图书
    limit = 3,                         # 返回相似度最高的3条结果
    search_params= {"nprobe": 10},     # 检索参数：IVF_FLAT索引的nprobe（遍历10个聚类中心，平衡精度/速度）
    output_fields= ["title", "price","category"] # 指定返回的标量字段（避免返回冗余数据）
)

# ------------------------ 【注释段】检索进阶1：基础分页检索（无过滤） ------------------------
# # 仅返回相似度最高的3条结果（基础检索，无过滤）
# response = client.search(
#     collection_name = "book",
#     data = [query_vector], # 单个查询向量
#     limit=3                # 返回Top3结果
# )
# print(response)

# ------------------------ 【注释段】检索进阶2：带偏移量的分页检索 ------------------------
# # 分页检索：跳过前2条结果，返回接下来的3条（实现“第2页，每页3条”效果）
# response = client.search(
#     collection_name = "book",
#     data = [query_vector],
#     offset=2,  # 偏移量：跳过前2条结果
#     limit=3    # 每页条数：返回3条
# )
# print(response)

# ------------------------ 【注释段】检索进阶3：批量向量查询 ------------------------
# # 同时传入2个查询向量，每个向量都返回“跳过2条+取3条”的结果
# # [0.5] * 4 表示生成[0.5, 0.5, 0.5, 0.5]的4维向量
# response = client.search(
#     collection_name = "book",
#     data = [query_vector,[0.5] * 4], # 批量查询：2个查询向量
#     offset = 2 ,                     # 每个向量的结果都跳过前2条
#     limit=3                          # 每个向量返回3条结果
# )
# print(response)

# ------------------------ 元数据查询1：查看集合（表）的详细信息 ------------------------
# describe_collection：查询集合的Schema、字段、动态字段、分片等元数据（类似MySQL的DESC TABLE）
print("===== 集合（book）详情 =====")
print(client.describe_collection("book"))

# ------------------------ 元数据查询2：查看索引的详细信息 ------------------------
# describe_index：查询集合中向量字段的索引配置（类型、度量方式、参数等）
print("\n===== 索引（book）详情 =====")
print(client.describe_index("book"))
