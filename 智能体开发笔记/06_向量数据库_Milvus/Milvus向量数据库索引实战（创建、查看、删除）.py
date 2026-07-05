# ------------------------ 核心功能：Milvus向量数据库索引实战（创建/查看/删除） ------------------------
# 索引是Milvus提升向量检索效率的核心，类似MySQL的索引（无索引时向量检索是全量扫描，效率极低）
# 导入Milvus核心模块
from pymilvus import connections, db, MilvusClient, FieldSchema, DataType, CollectionSchema, Collection
# 导入警告处理模块，忽略无关的deprecated警告（提升代码运行体验）
import warnings
# 过滤"pkg_resources is deprecated"警告（Milvus客户端依赖的第三方库警告，不影响功能）
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

# ------------------------ 步骤1：初始化Milvus客户端（HTTP方式连接远程服务） ------------------------
# MilvusClient：更简洁的客户端API，适合快速操作索引/集合
# uri：Milvus服务的访问地址（IP+端口，需替换为实际部署地址）
client = MilvusClient(uri="http://192.168.64.137:19530")

# ------------------------ 【注释段】前置操作：创建集合（表）+ 定义字段 ------------------------
# # 1. 创建集合Schema（表结构）
# schema = MilvusClient.create_schema(
#     auto_id = False,        # 关闭自动生成ID（手动指定id字段值）
#     enable_dynamic_field = True, # 开启动态字段（允许插入未定义的标量字段）
# )
# # 2. 向Schema添加主键字段（id）
# schema.add_field(
#     field_name = "id",      # 字段名
#     datatype = DataType.INT64, # 数据类型：64位整数
#     is_primary = True,      # 设为主键（唯一标识每条数据）
# )
# # 3. 向Schema添加向量字段（vector）
# schema.add_field(
#     field_name = "vector",  # 向量字段名
#     datatype = DataType.FLOAT_VECTOR, # 数据类型：浮点型向量
#     dim = 5                 # 向量维度（示例为5维，实际需与嵌入模型维度匹配，如768/1024）
# )
# # 4. 创建集合（表）
# client.create_collection(
#     collection_name = "customized_setup", # 集合名
#     schema = schema,                      # 绑定上面定义的表结构
# )

# ------------------------ 【注释段】核心操作：为向量字段创建索引 ------------------------
# # 1. 初始化索引参数对象（用于配置索引的各项参数）
# index_params = MilvusClient.prepare_index_params()
# # 2. 配置向量字段的索引参数（核心步骤）
# index_params.add_index(
#     field_name = "vector",          # 要创建索引的字段名（必须是向量字段）
#     metric_type = "COSINE",         # 距离度量方式：COSINE（余弦相似度，适合文本嵌入向量）
#                                     # 可选值：L2（欧式距离）、IP（内积）、COSINE（余弦）
#     index_type="IVF_FLAT",          # 索引类型：IVF_FLAT（基础且稳定的索引，适合中小数据量）
#                                     # 其他常用类型：HNSW（高并发/大数据量）、DISKANN（海量数据）
#     index_name = "vector_index",    # 索引名称（自定义，用于后续查看/删除索引）
#     params = {
#         "nlist": 1024              # IVF_FLAT索引核心参数：聚类中心数
#                                     # 建议值：sqrt(总数据量)，如10万条数据设为300-1000
#     }
# )
# # 3. 执行索引创建
# client.create_index(
#     collection_name = "customized_setup", # 集合名（要创建索引的表）
#     index_params = index_params,          # 绑定上面配置的索引参数
#     sync = False                          # 是否同步等待索引创建完成：False（异步，立即返回）
#                                           # 大数据量时建议异步，避免阻塞；小数据量可设为True
# )

# ------------------------ 实战操作1：查看索引详情（类似MySQL的DESC/ SHOW INDEX） ------------------------
# describe_index：查询指定集合中指定索引的详细信息（字段、类型、参数等）
res = client.describe_index(
    collection_name = "customized_setup",  # 集合名称（要查询的表）
    index_name = "vector_index"            # 索引名称（要查询的索引）
)
# 打印索引详情（包含索引类型、度量方式、参数、创建时间等）
print(res)

# ------------------------ 实战操作2：删除索引 ------------------------
# drop_index：删除指定集合中的指定索引（删除后检索会变回全量扫描，效率降低）
res = client.drop_index(
    collection_name = "customized_setup",  # 集合名称
    index_name = "vector_index"            # 要删除的索引名称
)
# 打印删除结果（成功返回None或True，失败抛出异常）
print(res)
