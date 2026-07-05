# ------------------------ 核心功能：Milvus向量数据库DML实战（插入/删除/更新） ------------------------
# DML（Data Manipulation Language）：数据操作语言，对应Milvus的插入、删除、更新（Milvus无原生更新，需删插）
# 导入Milvus核心模块
from pymilvus import connections, db, MilvusClient, FieldSchema, DataType, CollectionSchema, Collection
# 导入警告处理模块，忽略无关的deprecated警告
import warnings
# 过滤"pkg_resources is deprecated"警告（Milvus客户端依赖库的冗余警告，不影响功能）
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

# ------------------------ 步骤1：初始化Milvus客户端（连接远程Milvus服务） ------------------------
# MilvusClient：简化版客户端API，更适合DML操作（插入/删除/查询）
# uri：Milvus服务的访问地址（IP+端口，需替换为实际部署地址）
client = MilvusClient(uri="http://192.168.64.137:19530")

# ------------------------ 【注释段】前置操作：创建集合+索引（DML的前提） ------------------------
# # 1. 创建集合Schema（表结构）
# schema = MilvusClient.create_schema(
#     auto_id = False,                # 关闭自动生成ID（需手动指定id字段值）
#     enable_dynamic_field = True,    # 开启动态字段（允许插入Schema未定义的字段，如示例中的text）
# )
# # 2. 添加主键字段（id）
# schema.add_field(
#     field_name = "id",              # 字段名
#     datatype = DataType.INT64,      # 数据类型：64位整数
#     is_primary = True,              # 设为主键（唯一标识每条数据）
# )
# # 3. 添加向量字段（vector）
# schema.add_field(
#     field_name = "vector",          # 向量字段名
#     datatype = DataType.FLOAT_VECTOR, # 数据类型：浮点型向量
#     dim = 5                         # 向量维度（示例为5维，实际需匹配嵌入模型维度）
# )
#
# # 4. 配置向量字段索引（提升检索效率，DML后检索需依赖索引）
# index_params = MilvusClient.prepare_index_params()
# index_params.add_index(
#     field_name = "vector",          # 要创建索引的向量字段名
#     metric_type = "COSINE",         # 距离度量方式：余弦相似度（适合文本嵌入向量）
#     index_type="IVF_FLAT",          # 索引类型：IVF_FLAT（基础稳定，中小数据量首选）
#     index_name = "vector_index",    # 索引名称（自定义）
#     params = {
#         "nlist": 1024              # IVF_FLAT核心参数：聚类中心数（建议sqrt(数据量)）
#     }
# )
#
# # 5. 创建集合（表）并绑定索引
# client.create_collection(
#     collection_name = "my_collection", # 集合名（表名）
#     schema = schema,                  # 绑定表结构
#     index_params = index_params,      # 绑定索引配置（创建集合时自动创建索引）
# )

# ------------------------ 【注释段】DML操作1：插入数据（核心写操作） ------------------------
# # 模拟待插入的数据（包含主键、向量字段、动态字段text）
# data = [
#     {
#         "id": 1,                          # 主键ID（必须唯一）
#         "vector": [0.1, 0.2, 0.3, 0.4, 0.5], # 5维向量（维度需与Schema定义一致）
#         "text": "hello world"              # 动态字段（Schema未定义，因enable_dynamic_field=True才支持）
#     },
#     {
#         "id": 2,
#         "vector": [0.2, 0.3, 0.4, 0.5, 0.6],
#         "text": "hello milvus"
#     },
#     {
#         "id": 3,
#         "vector": [0.3, 0.4, 0.5, 0.6, 0.7],
#         "text": "hello python"
#     }
# ]
#
# # 打印待插入数据（验证数据格式）
# print(data)
#
# # 执行插入操作
# result = client.insert(
#     collection_name = "my_collection", # 目标集合名
#     data = data,                      # 待插入的数据列表
# )
# # 打印插入结果（包含插入成功的条数、ID列表等）
# print(result)

# ------------------------ DML操作2：删除数据（核心删操作） ------------------------
# client.delete：删除指定集合中的数据，支持两种方式：
# 1. ids：指定主键ID列表（精准删除，推荐）；
# 2. filter：过滤条件（如"id == 1"或"text like 'hello%'"，批量删除）
client.delete(
    collection_name = "my_collection",  # 目标集合名
    ids = [1, 2],                       # 要删除的数据主键ID列表（删除ID=1和ID=2的两条数据）
    # filter="id == 1"                  # 备选删除方式：通过过滤条件删除（注释掉，二选一）
)

# ------------------------ DML操作3：更新数据（Milvus无原生UPDATE，需先删后插） ------------------------
# 重要说明：Milvus不支持直接UPDATE操作，更新数据的核心逻辑是：
# 1. 删除原数据（通过ID/filter）；
# 2. 插入新数据（使用相同ID，覆盖原数据）；
# 示例伪代码：
# # 1. 删除要更新的ID=3的数据
# client.delete(collection_name="my_collection", ids=[3])
# # 2. 插入新的ID=3的数据（覆盖原数据）
# client.insert(
#     collection_name="my_collection",
#     data=[{"id": 3, "vector": [0.4, 0.5, 0.6, 0.7, 0.8], "text": "hello milvus update"}]
# )
