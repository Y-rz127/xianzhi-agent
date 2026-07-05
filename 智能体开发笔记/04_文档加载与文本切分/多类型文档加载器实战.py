# ====================== LangChain 各类文档加载器实战（项目级数据加载场景） ======================
# 从langchain社区导入多种文档加载器，适配项目中不同格式文件/网页的数据读取需求
from langchain_community.document_loaders import (
    TextLoader,        # 加载纯文本文件（.txt），项目中用于读取普通文本数据
    UnstructuredURLLoader,# 加载静态网页数据，项目中用于爬取无动态渲染的网页内容
    UnstructuredFileLoader,# 通用文件加载器，适配多种非结构化文件
    PyPDFLoader,       # 加载PDF文件，项目中用于读取PDF格式的文档/报告
    Docx2txtLoader,    # 加载Word文档（.docx），项目中用于读取办公文档数据
    CSVLoader,         # 加载CSV文件，项目中用于读取表格类数据（如销售数据、用户数据）
    UnstructuredHTMLLoader,# 加载HTML文件，项目中用于读取本地/远程HTML格式数据
    SeleniumURLLoader, # 加载动态渲染网页（JS渲染），项目中用于爬取需要动态加载的网页
    WebBaseLoader,     # 通用网页加载器，简化网页数据读取流程
    JSONLoader,        # 加载JSON文件，项目中用于读取结构化JSON数据并按需提取
)

# ---------------------- 实战1：纯文本文件加载（项目中最基础的文本数据读取） ----------------------
# 初始化TextLoader：指定待加载的txt文件路径，设置编码格式为utf-8（避免中文乱码）
loader = TextLoader("data/test.txt", encoding="utf-8")
# 执行加载：返回Document对象列表，每个Document包含核心内容（page_content）和元数据（metadata）
document = loader.load()
print(document)  # 打印完整的Document列表
print(len(document))  # 打印加载的文档数量（txt文件默认返回1个Document）
print(document[0].page_content[:100])  # 打印第一个文档的前100个字符（预览核心内容）
print(document[0].metadata)  # 打印第一个文档的元数据（包含文件路径、修改时间等信息）

# ---------------------- 实战2：CSV文件加载（项目中表格数据读取与数据分析场景） ----------------------
# 初始化CSVLoader：指定csv文件路径，配置编码格式，自定义字段名
# csv_args={"fieldnames":...}：指定CSV文件的列名，用于规范数据结构，方便后续数据分析
# 每行CSV数据会自动转换为1个Document对象，元数据中包含对应行号
loader = CSVLoader("data/test.csv",csv_args={"fieldnames":["产品名称","销售数量","客户名称"]},encoding = "utf-8")
document = loader.load()
print(document)  # 打印加载后的Document列表（每行对应一个Document）
print(len(document))  # 打印加载的文档数量（等于CSV文件的行数）
print(document[0].page_content)  # 打印第一行数据的核心内容（格式化后的表格字段与值）

# ---------------------- 实战3：JSON文件加载（项目中结构化JSON数据提取场景） ----------------------
# 初始化JSONLoader：指定json文件路径，配置数据提取规则
# jq_schema=".articles[]"：使用jq语法，提取JSON中articles数组的每一个元素
# content_key="content"：指定将每个数组元素的"content"字段作为Document的核心内容
loader = JSONLoader("data/test.json",jq_schema=".articles[]",content_key="content")
print(f"json loader:{loader}")  # 打印JSONLoader实例信息
docs = loader.load()  # 执行加载，提取符合规则的结构化数据
print(docs)  # 打印加载后的Document列表（articles数组元素数量对应Document数量）
print(len(docs))  # 打印提取的文档数量（等于articles数组的长度）
