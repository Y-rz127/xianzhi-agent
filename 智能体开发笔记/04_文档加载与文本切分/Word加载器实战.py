# 导入操作系统相关模块，用于文件路径拼接和文件夹遍历操作
import os

# 从LangChain库中导入Docx2txtLoader类，专门用于加载和解析.docx格式的Word文档
from langchain.document_loaders import Docx2txtLoader

# ------------------------ 单个Word文档加载实战 ------------------------
# 初始化Docx2txtLoader加载器实例，传入单个Word文档的相对路径
# 注意：该加载器仅支持.docx格式，不支持旧版.doc格式
loader = Docx2txtLoader("./word.docx")

# 加载该Word文档内容，返回文档对象列表（单个Word文档默认返回长度为1的列表）
docs = loader.load()

# 打印第一个（也是唯一的）文档对象的内容，仅截取前100个字符，避免输出过长
print(docs[0].page_content[:100])

# 打印该Word文档的元数据（包含文件路径等信息）
print(docs[0].metadata)

# 打印完整的文档对象列表，查看详细信息
print(docs)


# ------------------------ 批量加载文件夹中的Word文档实战 ------------------------
# 定义存放Word文档的文件夹路径
folder_path = "data/test.word"

# 初始化一个空列表，用于存储所有Word文档的文档对象列表
all_pages = []

# 遍历指定文件夹下的所有文件/文件夹
for file_name in os.listdir(folder_path):
    # 判断当前文件是否以.docx后缀结尾，筛选出Word文档（排除非.docx文件）
    if file_name.endswith(".docx"):
        # 拼接当前Word文档的完整路径：文件夹路径 + 文件名，避免路径错误
        file_path = os.path.join(folder_path, file_name)
        # 初始化Docx2txtLoader实例，传入当前Word文档的完整路径
        loader = Docx2txtLoader(file_path)
        # 加载当前Word文档，并将返回的文档对象列表添加到all_pages中
        all_pages.append(loader.load())
        # 打印提示信息，确认当前文件已成功加载
        print("加载文件!")

# 打印存储了所有Word文档信息的列表，查看批量加载结果
print(all_pages)
