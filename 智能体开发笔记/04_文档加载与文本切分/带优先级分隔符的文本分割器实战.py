# 从LangChain库中导入RecursiveCharacterTextSplitter类
# 这是递归字符文本分割器，相比普通CharacterTextSplitter更智能：
# 会按分隔符优先级递归拆分文本，直到每个片段满足chunk_size要求，更适合复杂格式文本
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ------------------------ 定义待拆分的示例文本 ------------------------
# 待切割的文本内容（一段写作要点描述，包含多个段落分隔）
text = """
    时间地点：冬日早晨、上学路上

    事件经过：发现小狗→送医→收养

    情感升华：从帮助他人到自我成长

    语言简洁：用短句和细节描写增强画面感（如“瑟瑟发抖”“摇着尾巴”）
"""

# ------------------------ 初始化递归字符文本分割器 ------------------------
splitter = RecursiveCharacterTextSplitter(
    chunk_size=20,        # 核心参数：每个文本片段（chunk）的最大字符长度（此处设为20个字符）
    chunk_overlap=4,      # 核心参数：相邻两个文本片段的重叠字符数（此处设为4个字符）
                          # 作用：保留上下文连贯性，避免关键信息被割裂
    separators = ["\n\n", "\n", " ", ""],  # 关键参数：分隔符优先级列表（从高到低）
                          # 1. "\n\n"：优先按空行（段落分隔）拆分
                          # 2. "\n"：段落拆分不满足长度要求时，按换行符拆分
                          # 3. " "：换行拆分仍不满足时，按空格拆分
                          # 4. ""：最后按单个字符拆分（确保片段长度符合要求）
    length_function=len,  # 计算文本长度的函数，使用Python内置len()（按字符数统计）
    keep_separator=True   # 是否保留分隔符本身（True=保留，False=丢弃）
                          # 保留分隔符可更好地维持文本原有格式
)

# ------------------------ 执行文本拆分并查看结果 ------------------------
# 调用split_text方法，传入待拆分文本，执行递归拆分操作
# 返回拆分后的文本片段列表
chunk = splitter.split_text(text)

# 打印拆分后得到的文本片段总数（即列表长度）
print(len(chunk))

# 遍历所有拆分后的文本片段，逐个打印信息
for i in chunk:
    # 打印当前文本片段的字符长度，验证是否符合chunk_size要求
    print(len(i))
    # 打印当前文本片段的具体内容
    print(i)
