# 导入操作系统相关模块，用于设置系统环境变量
import os
# ------------------------ 关键配置：设置User-Agent（避免网页访问被拦截） ------------------------
# 注意：该配置必须放在WebBaseLoader导入之前，否则会报错
# 设置USER_AGENT环境变量，模拟Chrome浏览器的请求头，防止被目标网站反爬拦截
os.environ['USER_AGENT'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'

# 从LangChain库中导入WebBaseLoader类，用于加载和解析静态网页内容
# （导入放在User-Agent设置之后，避免配置不生效报错）
from langchain.document_loaders import WebBaseLoader

# ------------------------ 单个/单个批次网页加载实战 ------------------------
# 定义需要加载的网页URL列表（此处仅包含一个博客园首页URL）
urls = ["https://www.cnblogs.com"]
# 初始化WebBaseLoader加载器实例，传入待加载的URL列表
loader = WebBaseLoader(urls)
# 加载网页内容，返回文档对象列表（每个URL对应一个文档对象）
docs = loader.load()

# 查看加载结果：打印完整的文档对象列表
print(docs)
# 查看第一个网页（索引0）的内容，仅截取前100个字符，避免输出过长
print(docs[0].page_content[:100])
# 查看第一个网页文档的元数据（包含URL来源、加载时间等信息）
print(docs[0].metadata)



# ------------------------ 批量读取多个静态网页实战 ------------------------
# 定义需要批量加载的静态网页URL列表（百度新闻+百度贴吧）
urls = ["https://www.news.baidu.com","https://tieba.baidu.com/index.html"]
# 初始化WebBaseLoader加载器实例，传入批量URL列表
loader = WebBaseLoader(urls)
# 加载所有指定网页的内容，返回包含多个文档对象的列表
docs = loader.load()

# 遍历所有加载后的文档对象，逐个打印关键信息
for doc in docs:
    # 打印当前网页的内容，仅截取前100个字符
    print(doc.page_content[:100])
    # 打印当前网页的来源URL（从元数据中提取source字段）
    print(doc.metadata['source'])
    # 打印分隔线，方便区分不同网页的输出结果
    print("-"*50)
