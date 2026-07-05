# 从LangChain库中导入文本分割相关工具类
# RecursiveCharacterTextSplitter：递归字符分割器（智能按分隔符优先级拆分）
# CharacterTextSplitter：基础字符分割器（按指定分隔符拆分）
# Language：语言枚举类，用于指定编程语言类型（适配语言专属分割规则）
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter, Language

# ------------------------ 场景1：文本长度不足chunk_size，chunk_overlap不生效 ------------------------
# 定义一段极短的测试文本，长度小于后续设置的chunk_size=20
# 由于文本整体长度未超过单个片段的最大长度，不会进行拆分，仅生成一个文本块
text = """
    这是一段非常短的文本
"""

# 初始化递归字符文本分割器
splitter = RecursiveCharacterTextSplitter(
    chunk_size=20,        # 每个文本片段的最大字符长度为20
    chunk_overlap=4,      # 相邻片段的重叠字符数为4（此场景下不生效，因为仅生成一个片段）
    separators = ["\n\n", "\n", " ", ""],  # 分隔符优先级：空行>换行>空格>单个字符
    length_function=len,  # 用Python内置len()函数统计字符长度
    keep_separator=True   # 保留分隔符，维持文本原有格式
)
# 执行文本拆分操作
chunk = splitter.split_text(text)
# 打印拆分后的文本片段列表（仅包含1个元素，无重叠可言）
print(chunk)


# ------------------------ 场景2：无有效分隔符，按字符硬分割，chunk_overlap生效 ------------------------
# 定义一段无有效分隔符（无空行、换行、空格）的超长纯字母文本
# 无法通过高优先级分隔符拆分，最终会按单个字符硬分割，并触发重叠逻辑
text = """
    aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""

# 初始化递归字符文本分割器（配置同场景1）
splitter = RecursiveCharacterTextSplitter(
    chunk_size=20,        # 每个片段最大20个字符
    chunk_overlap=4,      # 相邻片段重叠4个字符（此场景下生效）
    separators = ["\n\n", "\n", " ", ""],  # 分隔符优先级列表
    length_function=len,  # 按字符数统计长度
    keep_separator=True   # 保留分隔符（此场景无有效分隔符，该参数无实际影响）
)
# 执行文本拆分
chunk = splitter.split_text(text)
# 遍历拆分后的片段（使用enumerate同时获取索引和片段内容）
for i in enumerate(chunk):  # enumerate：遍历可迭代对象时，返回（索引，元素值）的元组
    print(len(i))  # 打印当前元组（索引+片段）的长度（固定为2，包含索引和片段两个元素）
    print(i)       # 打印索引和对应的文本片段，查看硬分割及重叠效果

# 补充演示enumerate的基础用法（帮助理解上述遍历逻辑）
fruits = ["apple", "banana", "cherry", "date", "elderberry"]
for index, fruit in enumerate(fruits):
    # index：遍历的索引（从0开始），fruit：遍历到的列表元素值
    print(index, fruit)


# ------------------------ 场景3：分隔符完美切割，片段长度合规，chunk_overlap不生效 ------------------------
# 定义一段以"."为分隔符的文本，每个分隔后的片段长度（7个a）远小于chunk_size=20
# 按分隔符拆分后，所有片段长度均符合要求，无需进一步拆分，也不会触发重叠逻辑
text = """
    aaaaaaa.aaaaaaa.aaaaaaa.aaaaaaa
"""

# 初始化基础字符文本分割器
splitter = CharacterTextSplitter(
    chunk_size=20,        # 每个片段最大20个字符
    chunk_overlap=4,      # 相邻片段重叠4个字符（此场景下不生效，因片段长度合规且独立）
    separators = ".",     # 仅指定"."作为分隔符
)
# 执行文本拆分
chunk = splitter.split_text(text)
# 遍历拆分后的片段，用enumerate获取索引和片段内容
for i in enumerate(chunk):  # enumerate：同时获取索引和片段值
    print(len(i))  # 打印（索引+片段）元组的长度
    print(i)       # 打印索引和对应的文本片段，查看完美分割效果

# ------------------------ 最佳实践 & 语言专属分割器 ------------------------
# 温馨提示：文本分割参数最佳配置
# 1. chunk_size 建议设置为500-1000个字符（兼顾语义完整和检索效率）
# 2. chunk_overlap 建议设置为chunk_size的10%-20%（既能保留上下文，又不会冗余过多）

# 初始化Python语言专属的递归字符分割器
# from_language：通过指定编程语言，自动适配该语言的专属分隔符（如Python的缩进、函数定义等）
python_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON,  # 指定语言为Python
    chunk_size=200,            # 每个Python代码片段最大200个字符
    chunk_overlap=50           # 相邻Python代码片段重叠50个字符（约为chunk_size的25%，接近最佳实践）
)
