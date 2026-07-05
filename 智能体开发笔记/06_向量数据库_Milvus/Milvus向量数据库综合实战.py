# ------------------------ 核心功能：Milvus向量数据库综合实战（图书向量检索系统） ------------------------
# 完整演示：创建集合→生成测试数据→插入数据→创建索引→带过滤条件的向量相似性检索
# 模拟场景：图书检索 - 根据图书简介的向量相似度，筛选指定分类（如Python）的图书
from pymilvus import connections, db, MilvusClient, FieldSchema, DataType, CollectionSchema, Collection
import random  # 用于生成随机测试数据

# 冗余导入（原代码误导入，保留仅作注释说明）
# from sympy.integrals.meijerint_doc import category

# ------------------------ 步骤1：初始化Milvus客户端（连接远程Milvus服务） ------------------------
# MilvusClient：简化版客户端API，一站式完成集合创建、数据插入、索引、检索
# uri：Milvus服务的访问地址（IP+端口，需替换为实际部署地址）
client = MilvusClient(uri="http://192.168.64.137:19530")

# ------------------------ 【注释段】步骤2：创建图书集合（表）+ 定义字段结构 ------------------------
# # 定义集合的字段列表（包含主键、标量字段、向量字段）
# field1 = [
#     # 主键字段：图书ID（自动生成）
#     FieldSchema(name="book_id", dtype=DataType.INT64, is_primary=True, auto_id=True),
#     # 标量字段：图书标题（字符串类型，最大长度200）
#     FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=200),
#     # 标量字段：图书分类（如Python/Java，字符串类型）
#     FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=50),
#     # 标量字段：图书价格（浮点型，保留2位小数）
#     FieldSchema(name="price", dtype=DataType.DOUBLE),
#     # 向量字段：图书简介的嵌入向量（4维，实际场景需匹配嵌入模型维度如768）
#     FieldSchema(name="book_intro", dtype=DataType.FLOAT_VECTOR, dim=4)
# ]
#
# # 创建集合Schema（表结构）
# schema = CollectionSchema(
#     field1,
#     description="book search collection",  # 集合描述：图书检索库
#     enable_dynamic_field=True              # 开启动态字段（允许插入未定义的字段）
# )
#
# # 执行集合创建（等价于创建数据库表）
# collection = client.create_collection(collection_name="book", schema=schema)

# ------------------------ 【注释段】步骤3：生成并插入批量测试数据 ------------------------
# # 定义测试数据规模：生成1000本图书数据
# num_books = 1000
# # 图书分类列表（用于随机生成）
# category = ["Python", "Java", "C++", "C#", "Ruby", "Go", "PHP", "JavaScript", "Swift", "Kotlin"]
# # 图书标题前缀（用于随机生成）
# titles = ["Java基础", "Python基础", "C++基础", "C#基础", "Ruby基础", "Go基础", "PHP基础", "JavaScript基础", "Swift基础", "Kotlin基础"]
# # 初始化数据列表
# data = []
# for i in range(num_books):
#     data.append(
#         {
#             "title": f"{random.choice(titles)}_{i}",  # 随机标题+序号（如Python基础_123）
#             "category": random.choice(category),      # 随机分类
#             "price": round(random.uniform(10, 100), 2), # 随机价格（10~100元，保留2位小数）
#             "book_intro": [random.random() for _ in range(4)] # 随机生成4维向量（模拟图书简介嵌入）
#         }
#     )
#
# # 批量插入数据到book集合
# insert_result = client.insert(
#     collection_name = "book",  # 目标集合名
#     data = data                # 待插入的图书数据列表
# )
# # 打印插入结果：输出成功插入的图书ID数量
# print(f"数据插入:{len(insert_result['ids'])}")

# ------------------------ 【注释段】步骤4：为向量字段创建索引（提升检索效率） ------------------------
# # 初始化索引参数对象
# index_params = MilvusClient.prepare_index_params()
# # 配置向量字段的索引参数
# index_params.add_index(
#     field_name = "book_intro",          # 要创建索引的向量字段：图书简介向量
#     metric_type = "L2",                 # 距离度量方式：L2欧式距离（适合数值型向量）
#     index_type="IVF_FLAT",              # 索引类型：IVF_FLAT（中小数据量首选）
#     index_name = "vector_index",        # 索引名称：自定义标识
#     params = {
#         "nlist": 128                   # IVF_FLAT核心参数：聚类中心数（sqrt(1000)≈32，此处设128）
#     }
# )
#
# # 执行索引创建（异步创建，不阻塞）
# client.create_index(
#     collection_name = "book",
#     index_params = index_params,
#     sync = False  # 异步创建：立即返回，后台创建索引（大数据量建议异步）
# )

# ------------------------ 步骤5：执行带过滤条件的向量相似性检索（核心实战） ------------------------
# 加载集合到内存（检索前必须执行，索引和数据需加载到内存才能生效）
client.load_collection(collection_name = "book")

# 生成查询向量：随机生成4维向量（模拟用户输入的"图书简介"转换后的向量）
query_vector = [random.random() for _ in range(4)]

# 执行向量检索（结合标量过滤）
result = client.search(
    collection_name = "book",          # 目标集合名
    data = [query_vector],             # 查询向量（支持批量查询，列表格式）
    filter = "category == 'Python'",   # 标量过滤条件：只检索Python分类的图书
    limit = 3,                         # 返回相似度最高的3条结果
    search_params= {"nprobe": 10},     # 检索参数：nprobe=10（IVF_FLAT检索时遍历的聚类中心数，越大越精准但越慢）
    output_fields= ["title", "price","category"] # 指定返回的标量字段（不指定则只返回ID和距离）
)

# ------------------------ 步骤6：解析并格式化输出检索结果 ------------------------
# 打印原始检索结果（便于调试）
print(result)

# 格式化输出Python分类的检索结果
print("\nPython相关的结果")
for item in result[0]: # result是二维列表，result[0]对应第一个查询向量的结果
    print(f"id: {item['id']}")                  # 图书ID（主键）
    print(f"距离: {item['distance']:.4f}")      # 向量距离（越小相似度越高）
    print(f"标题: {item['entity']['title']}")   # 图书标题
    print(f"价格: {item['entity']['price']:.2f}") # 图书价格
    print("_" * 30 )                            # 分隔线，提升可读性
