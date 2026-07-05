# ------------------------ 核心业务场景说明 ------------------------
# 本代码演示嵌入模型缓存的差异化使用策略：
# 1. 用户实时查询请求（embed_query）：不走缓存，保证结果实时性；
# 2. 大量文本构建向量库（embed_documents）：走缓存，避免重复计算，节省成本/时间；
import time  # 导入时间模块，用于统计嵌入调用耗时

# 导入LangChain缓存嵌入核心类、阿里云通义嵌入模型类
from langchain.embeddings import CacheBackedEmbeddings, DashScopeEmbeddings
# 导入本地文件存储类，用于缓存嵌入向量
from langchain.storage import LocalFileStore
# 以下两个导入为冗余导入（未实际使用），保留原代码结构仅作注释说明
from openai import max_retries
from openai.types import embedding_model

# ------------------------ 初始化阿里云通义嵌入模型 ------------------------
# 实例化阿里云第二代通用文本嵌入模型
ali_embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定使用阿里云text-embedding-v2嵌入模型
    max_retries=3,              # 设置API调用失败后的最大重试次数为3次
    dashscope_api_key="",  # 阿里云通义千问API密钥（需替换为有效密钥）
)

# ------------------------ 初始化本地文件缓存存储 ------------------------
# 创建本地文件缓存对象，缓存文件存储路径为"./cache.json"（实际是文件夹，非单个文件）
storage = LocalFileStore("./cache.json")
# 组合阿里云嵌入模型与本地缓存（装饰器模式）
cache = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings=ali_embeddings,  # 底层实际执行嵌入计算的模型（阿里云模型）
    document_embedding_cache=storage,      # 文档嵌入的缓存存储介质（本地文件）
    namespace="my_namespace",              # 缓存命名空间：隔离不同项目/模型的缓存，避免冲突
)

# 定义测试文本列表（包含两条文本，故意设计无重复，用于测试缓存策略）
text = [""]

# ------------------------ 【注释段】演示：批量文本嵌入（embed_documents）走缓存 ------------------------
# # 记录首次调用开始时间
# start1 = time.time()
# # 第一次调用embed_documents（批量文本嵌入）：无缓存，调用阿里云API计算向量并写入本地缓存
# vector1 = cache.embed_documents(text)
# # 打印第一条文本嵌入向量的维度（如768/1024，取决于模型）
# print(f"首次调用嵌入维度:{len(vector1[0])}")
# # 记录首次调用结束时间
# end1 = time.time()
# # 打印首次调用耗时（包含API调用+缓存写入时间，耗时较长）
# print(f"首次调用耗时:{end1-start1}")
#
# # 第二次调用embed_documents：命中缓存，直接从本地文件读取向量，不调用API
# vector2 = cache.embed_documents(text)
# # 验证两次调用结果一致性（缓存命中则结果相等）
# print(f"二次调用结果相等: {vector1 == vector2}")
# end2 = time.time()
# # 打印二次调用耗时（仅缓存读取时间，耗时极短）
# print(f"二次调用耗时:{end2-end1}")

# ------------------------ 【执行段】演示：用户查询嵌入（embed_query）不走缓存 ------------------------
# 记录首次调用开始时间
start1 = time.time()
# 第一次调用embed_query（单文本嵌入，注：原代码传入列表，实际应传入单个字符串，此处保留原逻辑）：
# embed_query默认不走document_embedding_cache缓存，每次都调用阿里云API计算向量
r1 = cache.embed_query(text)
# 打印用户查询文本嵌入向量的维度
print(f"首次调用嵌入维度:{len(r1)}")
# 记录首次调用结束时间
end1 = time.time()
# 打印首次调用耗时（每次都包含API调用时间，耗时较长）
print(f"首次调用耗时:{end1-start1}")

# 第二次调用embed_query：同样不走缓存，重新调用阿里云API计算向量
r2 = cache.embed_query(text)
# 验证两次调用结果一致性（向量计算结果理论上相等，但均为实时计算）
print(f"二次调用结果相等: {r1 == r2}")
end2 = time.time()
# 打印二次调用耗时（仍为API调用时间，无缓存提速效果）
print(f"二次调用耗时:{end2-end1}")
