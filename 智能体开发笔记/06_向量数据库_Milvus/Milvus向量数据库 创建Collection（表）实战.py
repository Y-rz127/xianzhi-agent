# ------------------------ 核心功能：Milvus向量数据库创建Collection（表） ------------------------
# Milvus是开源的向量数据库，Collection等价于传统数据库的"表"，用于存储向量+标量数据
# 导入Milvus核心模块：字段定义、集合schema、数据类型、集合操作
from pymilvus import FieldSchema, CollectionSchema, DataType, Collection

# ------------------------ 步骤1：定义Collection的字段结构（等价于数据库表的列） ------------------------
# 定义字段列表，包含主键、向量字段、标量字段（分类）
field1 = [
    # 字段1：主键字段（必选）
    # name="id"：字段名（对应列名）
    # dtype=DataType.INT64：数据类型为64位整数
    # is_primary=True：设为主键（唯一标识每条数据，类似MySQL的主键）
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),

    # 字段2：向量字段（Milvus核心字段，用于存储嵌入向量）
    # name="vector"：向量字段名
    # dtype=DataType.FLOAT_VECTOR：数据类型为浮点型向量（嵌入向量的标准类型）
    # dim=768：向量维度（需与嵌入模型输出维度一致，如text-embedding-v2默认768维）
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=768),

    # 字段3：标量字段（普通属性字段，用于过滤/检索）
    # name="category"：分类字段名（如商品分类：手机、电脑、家电）
    # dtype=DataType.VARCHAR：字符串类型（可变长度）
    # max_length = 50：字符串最大长度（VARCHAR类型必须指定）
    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=50)
]

# ------------------------ 步骤2：创建Collection的Schema（等价于数据库表结构） ------------------------
# CollectionSchema：定义集合的整体结构，包含字段列表+描述
# 参数1：field1 - 上面定义的字段列表
# 参数2：description - 集合描述（备注信息，便于管理）
schema = CollectionSchema(field1, description="商品向量库")

# ------------------------ 步骤3：创建Collection（等价于创建数据库表） ------------------------
# Collection：实例化集合对象，完成表的创建（需先连接Milvus客户端，此处省略连接代码）
# 参数1：name="product" - 集合名（表名）
# 参数2：schema=schema - 绑定上面定义的表结构
collection = Collection(name="product", schema=schema)
