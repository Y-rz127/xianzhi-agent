# ------------------------ 普通文本切割实战 ------------------------
# 从LangChain库中导入CharacterTextSplitter类
# 该类是基于字符分隔的文本分割器，适用于大多数普通文本的分片处理
from langchain.text_splitter import CharacterTextSplitter

# 定义待切割的普通文本内容（一段关于写作要点的描述）
text = """
    时间地点：冬日早晨、上学路上

    事件经过：发现小狗→送医→收养


    情感升华：从帮助他人到自我成长

    语言简洁：用短句和细节描写增强画面感（如“瑟瑟发抖”“摇着尾巴”）
"""

# 初始化CharacterTextSplitter文本分割器实例，并配置核心参数
split = CharacterTextSplitter(
    separator=" ",  # 文本分割的分隔符，此处设置为空格（按空格拆分文本）
    chunk_size=1000,  # 每个文本片段（chunk）的最大长度（单位：字符数）
    chunk_overlap=10,  # 相邻两个文本片段之间的重叠字符数，用于保留上下文连贯性
    length_function=len  # 用于计算文本长度的函数，此处使用Python内置的len()函数（按字符数统计长度）
)

# 调用split_text方法，传入待切割文本，执行分割操作，返回切割后的文本片段列表
chunk = split.split_text(text)

# 打印切割后得到的文本片段总数（列表长度）
print(len(chunk))

# 遍历切割后的所有文本片段，逐个打印输出，查看分割结果
for i in chunk:
    print(i)


# ------------------------ 日志文本切割实战（针对性配置分隔符） ------------------------
# 定义待切割的日志文本内容（一段应用运行日志，每行对应一条日志记录）
log = """
2023-12-15 10:23:45 [INFO] App started. Loading config...
2023-12-15 10:23:46 [DEBUG] Database connected: jdbc:mysq
2023-12-15 10:23:47 [WARN] Cache size exceeds 80% (cur
2023-12-15 10:23:49 [INFO] User login: id=1024, role=ad
2023-12-15 10:23:50 [ERROR] File not found: /tmp/data.x
2023-12-15 10:23:51 [INFO] Processing 15 requests in 
2023-12-15 10:23:53 [DEBUG] Response time: 248ms | GET
2023-12-15 10:23:55 [INFO] Shutdown hook triggered. 
"""

# 初始化CharacterTextSplitter文本分割器实例，针对日志格式配置参数
split = CharacterTextSplitter(
    separator="\n",  # 分隔符设置为换行符（\n），适配日志“一行一条记录”的格式，按行分割
    chunk_size=60,   # 每个日志文本片段的最大字符长度（60个字符）
    chunk_overlap=20,# 相邻日志片段的重叠字符数（20个字符），防止日志信息被割裂
)

# 调用split_text方法，传入日志文本，执行分割操作
chunk = split.split_text(log)

# 打印日志文本切割后的片段总数
print(len(chunk))

# 遍历所有切割后的日志片段，逐个打印输出，查看日志分割结果
for i in chunk:
    print(i)
