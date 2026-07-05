# ==================== LangChain 内置工具包实战：联网搜索 ====================
# 核心目标：使用 LangChain 内置的 SearchApiAPIWrapper 工具调用联网搜索API，获取实时网络信息
import os  # 导入操作系统模块，用于设置环境变量（存储敏感的API密钥）

# 导入LangChain社区工具：SearchApiAPIWrapper是对接SearchApi搜索引擎的封装工具
from langchain_community.utilities import SearchApiAPIWrapper
# 导入SecretStr（可选）：用于安全存储敏感信息（本示例用环境变量，仅展示导入）
from pydantic import SecretStr

# -------------------- 第一步：配置搜索API密钥（核心） --------------------
# 1. SearchApi需要API密钥才能调用，这里通过环境变量设置（避免硬编码泄露）
# 2. 实际使用时，建议将密钥放在.env文件中，通过python-dotenv加载，而非直接写在代码里
os.environ["SEARCHAPI_API_KEY"] = ""

# -------------------- 第二步：实例化搜索工具对象 --------------------
# SearchApiAPIWrapper：LangChain内置的SearchApi封装工具，提供简洁的搜索接口
# 实例化后可调用run()/results()方法执行搜索
search = SearchApiAPIWrapper()

# -------------------- 第三步：执行联网搜索 --------------------
# 方式1（简化版）：run()方法 → 返回格式化的搜索结果字符串（适合直接给大模型输入）
# result = search.run("langchain框架核心模块")

# 方式2（详细版）：results()方法 → 返回原始的搜索结果字典列表（适合自定义解析）
# 参数：搜索关键词（字符串），可额外指定num_results（返回结果数量，默认10）等参数
result = search.results("langchain框架核心模块")

# -------------------- 第四步：输出搜索结果 --------------------
# 输出结果：results()返回的是包含多个搜索结果的列表，每个元素是字典（含标题、链接、内容等）
print("搜索结果（原始字典列表）：")
print(result)

# 【可选】解析搜索结果示例（提取关键信息）
# for item in result:
#     print(f"标题：{item['title']}")
#     print(f"链接：{item['link']}")
#     print(f"摘要：{item['snippet']}\n")
