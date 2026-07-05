# 导入操作系统相关功能模块，用于后续可能的文件路径处理等操作
import os
# 导入filename方法（保留原导入结构，此处代码暂未实际使用该方法）
from fileinput import filename
# 从LangChain库中导入PyPDFLoader类，用于加载和解析PDF文件（支持图片提取功能）
from langchain.document_loaders import PyPDFLoader

# ------------------------ PDF文件加载（开启图片提取功能） ------------------------
# 初始化PyPDFLoader实例，传入待加载的PDF文件路径
# 参数extract_images=True：开启PDF内部图片提取功能（默认值为False，不提取图片）
loader = PyPDFLoader("data/test.pdf", extract_images=True)

# 加载PDF文件，并按原始页面进行分割，返回包含所有页面信息的文档对象列表
# 加载后的页面对象中，会包含提取到的图片相关信息（结合页面文本内容）
pages = loader.load()

# 打印第一个页面（索引为0，对应PDF实际第1页）的文本内容
# 若该页面包含图片，图片相关信息会同步在页面内容中体现
print(pages[0].page_content)
