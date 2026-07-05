# ------------------------ 阿里云通义嵌入模型实战 ------------------------
# 从LangChain社区库中导入DashScopeEmbeddings，用于调用阿里云通义千问的文本嵌入模型
from langchain_community.embeddings import DashScopeEmbeddings
# 从pydantic库导入SecretStr，用于安全存储和处理敏感信息（如API密钥，此处保留原代码结构）
from pydantic import SecretStr

# 初始化阿里云通义嵌入模型实例
ali_embeddings = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定使用阿里云第二代通用文本嵌入模型
    max_retries=3,              # 设置接口调用失败后的最大重试次数为3次
    dashscope_api_key="",  # 配置阿里云通义千问的API密钥（需替换为自己的有效密钥）
)

# 定义待处理的商品评论列表（用于后续通过嵌入向量进行情感分析等任务）
comments = [
    "这个手机太差了，没有使用价值",
    "这个手机很棒，非常值得使用",
    "这个手机没有问题，非常满意",
    "这个手机很差，非常不满意",
    "这个手机没有问题，非常"
]

# 调用嵌入模型的embed_query方法，将商品评论列表转换为文本嵌入向量
# 注：embed_query通常用于单文本嵌入，多文本也可直接传入列表进行批量转换
ali_embeddings_vec = ali_embeddings.embed_query(comments)
# 打印转换后的所有嵌入向量（每个评论对应一个高维向量）
print(ali_embeddings_vec)
# 打印嵌入向量的总数（对应评论列表的长度，即5个向量）
print(len(ali_embeddings_vec))
# 打印第一个评论对应的嵌入向量（查看单个向量的具体数值）
print(ali_embeddings_vec[0])


# ------------------------ Ollama本地嵌入模型实战（通过API调用） ------------------------
# 导入requests库，用于发送HTTP请求调用Ollama本地API
import requests
# 定义Ollama默认的本地API地址，用于获取文本嵌入向量
OLLAMA_URL = "http://localhost:11434/api/embeddings"

# 准备发送给Ollama API的请求数据（JSON格式）
data = {
    "model": "mofanke/acge_text_embedding",  # 指定使用的Ollama本地模型名称
    "prompt": "需要转换为向量的文本"          # 待转换为嵌入向量的输入文本
}

# 发送POST请求到Ollama API地址，传入JSON格式的请求数据
response = requests.post(OLLAMA_URL, json=data)
# 解析响应结果的JSON数据，提取其中的"embedding"字段，即文本对应的嵌入向量
embedding = response.json()["embedding"]

# 打印该嵌入向量的维度（即向量长度，常见值如768、1024等，取决于模型配置）
print(f"向量维度: {len(embedding)}")
