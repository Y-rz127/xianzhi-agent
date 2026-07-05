# 导入类型注解相关模块，用于定义函数参数/返回值的类型（提升代码可读性和规范性）
from typing import List, Optional
# 从LangChain的嵌入模型基类中导入Embeddings抽象类，自定义嵌入模型需继承该类
from langchain.embeddings.base import Embeddings
# 导入requests库，用于发送HTTP请求调用Ollama本地API
import requests


# ------------------------ 自定义Ollama嵌入模型类（遵循LangChain规范） ------------------------
# 继承LangChain的Embeddings抽象类，确保自定义模型能无缝接入LangChain生态（如与文本分割器、向量库配合）
class OllamaEmbeddings(Embeddings):
    """
    自定义Ollama嵌入模型类，遵循LangChain Embeddings抽象类规范
    核心功能：调用本地Ollama API，将文本转换为嵌入向量
    """
    # 类的初始化方法，定义模型关键参数
    def __init__(self, model: str = "mofanke/acge_text_embedding", base_url: str = "http://localhost:11434"):
        # 初始化Ollama模型名称（默认使用mofanke/acge_text_embedding）
        self.model = model
        # 初始化Ollama本地服务的基础URL（默认本地地址：http://localhost:11434）
        self.base_url = base_url

    # 私有方法：核心嵌入逻辑（单文本转向量），供外部方法调用
    def _embed(self, text: str) -> List[float]:
        """
        私有核心方法：将单条文本转换为嵌入向量
        :param text: 待转换的单条文本字符串
        :return: 文本对应的嵌入向量（浮点数列表）
        """
        try:
            # 发送POST请求调用Ollama的嵌入API
            response = requests.post(
                # 拼接完整的API地址：基础URL + 嵌入接口端点
                f"{self.base_url}/api/embeddings",
                # 传入JSON格式的请求参数
                json={
                    "model": self.model,  # 指定使用的Ollama模型名称
                    "prompt": text        # 待转换的文本内容（部分模型需改为"text"/"input"，视模型而定）
                }
            )
            # 检查请求是否成功（状态码非2xx则抛出异常）
            response.raise_for_status()
            # 解析响应JSON，提取"embedding"字段（即文本向量），无则返回空列表
            return response.json().get("embedding", [])
        # 捕获所有异常，封装为自定义ValueError并抛出，便于排查问题
        except Exception as e:
            raise ValueError(f"Ollama embedding error: {str(e)}")

    # 实现Embeddings抽象类的必选方法：单文本嵌入（适配LangChain标准调用方式）
    def embed_query(self, text: str) -> List[float]:
        """
        公开方法：单文本嵌入（用于查询文本的向量转换，如用户提问）
        :param text: 单条查询文本
        :return: 单个嵌入向量（浮点数列表）
        """
        return self._embed(text)

    # 实现Embeddings抽象类的必选方法：多文本批量嵌入（适配LangChain批量处理场景）
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        公开方法：多文本批量嵌入（用于文档库的批量向量转换，如商品评论、PDF文本等）
        :param texts: 待转换的文本列表（多条文本）
        :return: 嵌入向量列表（每个元素是单文本对应的向量，即二维浮点数列表）
        """
        # 遍历文本列表，调用_embed方法逐个转换，返回批量向量结果
        return [self._embed(text) for text in texts]


# ------------------------ 自定义Ollama嵌入模型实战 ------------------------
# 初始化自定义的Ollama嵌入模型实例
ali_embeddings = OllamaEmbeddings(
    model="mofanke/acge_text_embedding",  # 指定使用的Ollama模型名称
    base_url = "http://localhost:11434"    # 指定Ollama本地服务地址
)

# 定义待转换的商品评论列表（用于情感分析的文本数据）
comments = [
    "这个手机太差了，没有使用价值",
    "这个手机很棒，非常值得使用",
    "这个手机没有问题，非常满意",
    "这个手机很差，非常不满意",
    "这个手机没有问题，非常"]

# 调用批量嵌入方法，将5条商品评论转换为对应的嵌入向量列表
ali_embeddings = ali_embeddings.embed_documents(comments)

# 打印批量转换后的所有嵌入向量（5个向量，每个向量为浮点数列表）
print(ali_embeddings)
# 打印向量列表的长度（即评论数量，输出结果为5）
print(len(ali_embeddings))
# 打印第一条评论对应的嵌入向量（查看单个向量的具体数值）
print(ali_embeddings[0])
