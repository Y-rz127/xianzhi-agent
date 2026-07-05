# ------------------------ 核心功能：Milvus向量数据库连接+创建带动态字段/分片的Collection ------------------------
# 导入Milvus核心模块：连接管理、数据库操作、客户端、字段定义、数据类型、集合结构、集合操作
from pymilvus import connections, db, MilvusClient, FieldSchema, DataType, CollectionSchema, Collection

# ------------------------ 【注释段】MilvusClient方式连接（备选连接方式，与connections二选一） ------------------------
# # 初始化Milvus客户端（HTTP方式连接远程Milvus服务）
# # 参数为Milvus服务的地址+端口（此处为示例地址，需替换为实际部署地址）
# client = MilvusClient("http://192.168.64.137:19530")

# ------------------------ 步骤1：连接Milvus服务（官方推荐的connections方式） ------------------------
# connections.connect：建立与Milvus服务的连接（默认使用"default"连接别名）
# host：Milvus服务部署的IP地址（示例为192.168.64.137，需替换为实际IP）
# port：Milvus服务的端口（默认19530，若修改过需对应调整）
conn = connections.connect(host="192.168.64.137", port="19530")

# ------------------------ 【注释段】Milvus数据库级操作（可选，类似MySQL的数据库创建/切换） ------------------------
# # 创建自定义数据库（Milvus支持多数据库隔离，默认使用"default"数据库）
# db.create_database("my_database")
# # 切换到指定数据库（后续操作均在该数据库下执行）
# db.using_database("my_database")
# # 列出当前Milvus服务下的所有数据库
# dbs = db.list_database()
# print(dbs)
# # 删除指定数据库（谨慎操作，会删除库内所有Collection）
# db.drop_database("my_database")

# ------------------------ 步骤2：定义Collection的字段结构（表列定义） ------------------------
# 定义字段列表，包含主键、向量字段、标量字段
field1 = [
    # 主键字段：唯一标识每条数据（必选）
    # name="id"：字段名（列名）
    # dtype=DataType.INT64：64位整数类型
    # is_primary=True：设为主键（不可重复、非空）
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),

    # 向量字段：存储文本/商品转换后的嵌入向量（Milvus核心字段）
    # dtype=DataType.FLOAT_VECTOR：浮点型向量（嵌入模型输出的标准类型）
    # dim=768：向量维度（需与嵌入模型（如text-embedding-v2）输出维度一致）
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=768),

    # 标量字段：存储商品分类（如"手机"、"电脑"），用于过滤检索
    # dtype=DataType.VARCHAR：可变长度字符串类型
    # max_length=50：字符串最大长度（VARCHAR类型必须指定）
    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=50)
]

# ------------------------ 步骤3：创建Collection的Schema（表结构） ------------------------
# CollectionSchema：定义集合的整体结构
# 参数1：field1 - 字段列表
# 参数2：description - 集合描述（备注信息）
# 参数3：enable_dynamic_field=True - 开启动态字段功能（允许插入Schema未定义的字段，灵活扩展）
schema = CollectionSchema(field1, description="商品向量库", enable_dynamic_field=True)

# ------------------------ 步骤4：创建Collection（表）并配置分片 ------------------------
# 实例化Collection对象，完成表的创建
collection = Collection(
    name="product",  # 集合名（表名）
    schema=schema,  # 绑定上面定义的表结构
    using="default",  # 指定使用的数据库（默认"default"，若创建了自定义库需对应修改）
    num_shards=2  # 分片数（分布式部署时生效，将数据拆分到2个分片，提升并发/存储能力）
)
