# 导入操作系统相关功能模块，用于文件路径处理和文件夹遍历
import os
# 导入filename方法（注：此处实际批量处理中未使用该方法，保留原导入结构）
from fileinput import filename
# 从LangChain库中导入PyPDFLoader类，专门用于加载和解析PDF文件
from langchain.document_loaders import PyPDFLoader

# ------------------------ 单个PDF文件加载实战 ------------------------
# 初始化PyPDFLoader实例，传入待加载的PDF文件路径
loader = PyPDFLoader("data/test.pdf")
# 加载PDF文件，并按默认方式（按页面）分割文档，返回文档对象列表
docs = loader.load()

# 注释：以下是可选的加载并分割方式（当前未启用）
# 一个文档片段为一个单位
# 加载PDF并自定义分割规则：split_overlap=1（相邻文档片段重叠1个单位）
# split_length=2（每个文档片段长度为2个单位），页码从0开始计数
# docs = loader.load_and_split(split_overlap=1, split_length=2)

# 打印加载得到的文档总页数（即文档对象列表的长度）
print(len(docs))
# 打印完整的文档对象列表，查看每个页面的完整信息
print(docs)
# 访问并打印第一页（索引0）的文档内容，只截取前200个字符，避免输出过长
print(docs[0].page_content[:200])
# 访问并打印第一页文档的元数据（包含文件路径、页码等信息）
print(docs[0].metadata)

# 遍历所有文档页面，拼接每个页面的内容，得到PDF全文内容
full_text = "".join([doc.page_content for doc in docs])
# 打印拼接后的全文总长度（字符数）
print(len(full_text))


# ------------------------ 批量处理文件夹中的所有PDF文件 ------------------------
# 定义存放PDF文件的文件夹路径
pdf_folder  = "docs/"
# 初始化一个空列表，用于存储所有PDF文件的所有页面文档对象
all_pages = []

# 遍历指定文件夹下的所有文件
for file in os.listdir(pdf_folder):
    # 判断当前文件是否以.pdf后缀结尾（筛选出PDF文件）
    if file.endswith(".pdf"):
        # 拼接完整的PDF文件路径：文件夹路径 + 文件名
        # 修复原代码bug：原filename()改为file（filename()是fileinput的方法，此处应使用遍历得到的文件名file）
        pdf_file_path = os.path.join(pdf_folder, file)
        # 初始化PyPDFLoader实例，传入当前PDF文件的完整路径
        loader = PyPDFLoader(pdf_file_path)
        # 加载当前PDF的所有页面，并将页面文档对象添加到all_pages列表中
        all_pages.extend(loader.load())
