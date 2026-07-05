# 从LangChain核心输出解析模块导入字符串输出解析器，将模型返回的复杂Message对象转为纯字符串
from langchain_core.output_parsers import StrOutputParser
# 从LangChain核心提示词模块导入聊天提示词模板，用于构建结构化的RAG问答提示词
from langchain_core.prompts import ChatPromptTemplate
# 从LangChain核心可运行模块导入透传工具，用于直接传递用户提问到RAG链中
from langchain_core.runnables import RunnablePassthrough
# 从LangChain社区文档加载模块导入：
# TextLoader：用于加载本地文本文件（.txt），实现本地文档的RAG问答
from langchain_community.document_loaders import WebBaseLoader, TextLoader
# 从LangChain社区向量存储模块导入Chroma，用于构建本地向量数据库，存储文档嵌入向量
from langchain_community.vectorstores import Chroma
# 从LangChain OpenAI模块导入ChatOpenAI，实例化兼容OpenAI格式的大语言模型客户端
from langchain_openai import ChatOpenAI
# 从LangChain文本分割模块导入递归字符文本分割器，用于将长文档分割为小片段（适配嵌入模型限制）
from langchain_text_splitters import RecursiveCharacterTextSplitter
# 从LangChain社区嵌入模块导入通义千问嵌入模型，用于将文档片段转换为向量表示（嵌入）
from langchain_community.embeddings import DashScopeEmbeddings
# 从pydantic导入SecretStr，用于安全存储敏感信息（API密钥），避免明文泄露风险
from pydantic import SecretStr

# ---------------------- 步骤1：加载本地文档（RAG的数据源准备） ----------------------
# 注释：网页文档加载器（备用），用于加载在线网页内容，需确保网络通畅
# loader = WebBaseLoader("")  # 示例网页
# docs = loader.load()

# 初始化本地文本文件加载器，指定要加载的本地文本文件路径和编码格式（utf-8避免中文乱码）
# 需提前创建data目录，并在其中放入qa.txt文件（存储待问答的文档内容）
loader = TextLoader("data/qa.txt", encoding="utf-8")
# 执行文档加载，返回文档对象列表（docs），每个元素对应一个文档（此处仅加载单个txt文件）
docs = loader.load()

# ---------------------- 步骤2：分割长文档（适配嵌入模型的长度限制，提升检索精度） ----------------------
# 初始化递归字符文本分割器，这是RAG场景中最常用的文档分割工具
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,  # 每个文档片段（chunk）的最大字符数，根据嵌入模型能力调整
    chunk_overlap=200  # 相邻文档片段之间的重叠字符数，避免分割导致上下文丢失，提升片段连贯性
)
# 执行文档分割，将加载的完整文档（docs）分割为多个小片段（splits），返回片段列表
splits = text_splitter.split_documents(docs)

# ---------------------- 步骤3：初始化嵌入模型（文档→向量的转换工具） ----------------------
# 初始化通义千问DashScopeEmbeddings嵌入模型，用于将文档片段转换为高维向量（嵌入表示）
embedding_model = DashScopeEmbeddings(
    model="text-embedding-v2",  # 指定使用的嵌入模型版本（第二代通用嵌入模型，效果更优）
    max_retries=3,  # 嵌入请求失败时的最大重试次数，提升稳定性
    dashscope_api_key=""  # 通义千问API密钥，用于调用嵌入接口
)

# ---------------------- 步骤4：创建Chroma向量数据库并构建检索器（存储向量+实现精准检索） ----------------------
# 基于分割后的文档片段，创建Chroma本地向量数据库
vectorstore = Chroma.from_documents(
    documents=splits,  # 传入分割后的文档片段列表，作为向量数据库的数据源
    embedding=embedding_model,  # 传入已初始化的嵌入模型，用于将文档片段转为向量
    persist_directory="./rag_chroma_db"  # 指定向量数据库的本地持久化目录，重启程序后无需重新生成向量
)
# 将向量数据库转换为检索器（retriever），用于后续根据用户提问检索相关文档片段
# search_kwargs={"k": 3}：指定每次检索返回最相关的3个文档片段，平衡检索精度和上下文长度
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# ---------------------- 步骤5：初始化大语言模型（RAG的核心生成引擎，用于基于检索结果回答问题） ----------------------
# 创建ChatOpenAI模型实例，作为RAG问答的最终生成引擎
model = ChatOpenAI(
    model="qwen-plus",  # 指定使用的大语言模型（通义千问plus版本，具备优秀的文本理解和生成能力）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的OpenAI兼容API地址
    api_key=SecretStr(""),  # 安全存储API密钥（敏感信息），SecretStr隐藏明文展示
    streaming=True,  # 开启流式输出（本代码直接invoke获取结果，未体现流式效果，需结合回调函数使用）
    temperature=0.7)  # 模型生成内容的随机性/创造性参数（0-1区间），0.7兼顾回答准确性和表达流畅性（注：原注释"亲密度"不准确）

# ---------------------- 步骤6：创建RAG专用提示词模板（引导模型基于检索上下文回答问题） ----------------------
# 定义RAG提示词模板，核心是注入检索到的上下文（{context}）和用户问题（{question}）
template = """[INST]<<SYS>>
你是一个有用的AI助手，请根据以下上下文回答问题：
{context}
<</SYS>>
问题：{question} [/INST]"""
# 基于模板字符串创建ChatPromptTemplate对象，用于后续填充上下文和问题，生成完整提示词
rag_prompt = ChatPromptTemplate.from_template(template)

# ---------------------- 步骤7：构建完整RAG链（串联所有组件，实现端到端的检索增强生成） ----------------------
# 构建LCEL表达式的RAG链，按从左到右顺序串联各组件，实现「检索→填充提示词→模型生成→结果解析」
rag_chain = (
    # 第一步：构建输入字典，为后续链提供两个核心参数：
    # - context：通过retriever检索用户问题相关的文档片段（自动将用户提问传入retriever进行检索）
    # - question：通过RunnablePassthrough()直接透传用户的原始提问，不做任何修改
    {"context": retriever, "question": RunnablePassthrough()}
    |  # 管道符：将上一步的输出（字典）作为下一步的输入
    # 第二步：将输入字典填充到rag_prompt模板中，生成完整的结构化提示词
    rag_prompt
    |  # 管道符：将完整提示词作为下一步的输入
    # 第三步：将完整提示词传入大语言模型，生成问答结果（Message对象）
    model
    |  # 管道符：将模型生成的Message对象作为下一步的输入
    # 第四步：将复杂的Message对象转为纯字符串格式，方便查看和使用
    StrOutputParser()
)

# ---------------------- 示例：调用RAG链，执行问答任务 ----------------------
# 调用RAG链，传入用户问题「头疼怎么办?」，获取基于本地qa.txt文档的增强回答结果
result = rag_chain.invoke("头疼怎么办?")
# 打印最终的问答结果
print(result)
