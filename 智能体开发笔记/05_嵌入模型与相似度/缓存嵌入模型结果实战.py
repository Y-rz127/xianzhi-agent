# ------------------------ 核心说明：CacheBackedEmbeddings 作用 ------------------------
# CacheBackedEmbedding 是LangChain提供的嵌入向量缓存工具类
# 核心价值：缓存文本的嵌入向量计算结果，避免重复计算相同文本，提升效率+减少API调用成本（尤其付费模型）
from langchain.embeddings import CacheBackedEmbeddings  # 导入缓存嵌入核心类
from langchain.storage import LocalFileStore           # 导入本地文件存储类（用于文件缓存）
from openai.types import embedding_model               # 导入嵌入模型（示例，需替换为实际使用的模型，如Ollama/阿里云嵌入）

# ------------------------ 方式1：基础初始化示例（注释版，展示核心参数） ------------------------
# 初始化CacheBackedEmbeddings（基础写法，仅作参数说明参考）
# cache = CacheBackedEmbeddings(
#     embedding_function=embedding_model,  # 核心参数：指定实际使用的嵌入模型（如OllamaEmbeddings/阿里云嵌入）
#     cache_store="./cache.json",          # 缓存存储位置：支持文件、数据库、Redis等（此处示例为本地JSON文件）
#     namespace = "my_namespace"           # 缓存命名空间：用于隔离不同项目/模型的缓存，避免冲突
# )


# ------------------------ 方式2：本地文件缓存（常用，适合单机/小项目） ------------------------
# 1. 创建本地文件缓存存储对象，指定缓存文件存储目录为"./embedding_cache"
# LocalFileStore：将缓存的嵌入向量以文件形式存储在指定目录，自动管理缓存的读写
fs = LocalFileStore("./embedding_cache")

# 2. 组合嵌入模型与文件缓存（采用装饰器模式，类似Java的装饰器，不修改原模型逻辑，新增缓存能力）
# from_bytes_store：通过字节存储方式初始化缓存嵌入对象（推荐写法，适配多种存储类型）
cache = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings=embedding_model,  # 底层嵌入模型：实际执行文本转向量的模型（如自定义的OllamaEmbeddings）
    document_embedding_cache=fs,            # 文档嵌入缓存：指定使用上面创建的本地文件存储对象
    namespace="my_namespace"                # 缓存命名空间：区分不同模型版本/项目，避免缓存混淆
)

# 3. 测试缓存效果
# 首次调用：文本"如何重置密码?"无缓存，会调用底层模型计算向量，并将结果存入本地文件缓存
vector1 = cache.embed_documents(["如何重置密码?"])  # 注：原代码少中括号，embed_documents需传入列表，此处修正
# 二次调用：文本"如何重置密码?"已有缓存，直接从本地文件读取向量，不调用底层模型
vector2 = cache.embed_documents(["如何重置密码?"])
# 验证结果一致性：两次调用结果完全相同，且第二次无模型计算开销
print(vector1 == vector2)  # 输出True


# ------------------------ 方式3：带TTL的Redis缓存（适合分布式/生产环境） ------------------------
from langchain.storage import RedisStore  # 导入Redis存储类（用于Redis缓存）
from redis import Redis                   # 导入Redis客户端，用于连接Redis服务

# 1. 创建Redis客户端，连接本地Redis服务（host=localhost，端口=6379，默认无密码）
redis_client = Redis(host="localhost", port=6379)

# 2. 创建Redis缓存存储对象，设置TTL（过期时间）为86400秒（24小时）
# RedisStore：将缓存的嵌入向量存储在Redis中，支持分布式部署，TTL自动清理过期缓存
redis_storage = RedisStore(redis_client, ttl = 86400)  # ttl=86400 表示缓存24小时后自动过期

# 3. 组合嵌入模型与Redis缓存（适配分布式场景）
cache = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings=embedding_model,    # 底层嵌入模型（同上）
    document_embedding_store= redis_storage,  # 文档嵌入缓存：指定使用Redis存储对象
    namespace="my_namespace"                  # 缓存命名空间：隔离不同项目的Redis缓存
)
