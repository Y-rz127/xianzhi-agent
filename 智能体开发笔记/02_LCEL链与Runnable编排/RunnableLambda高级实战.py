# 包装链式函数实战
# 将任意python函数转换为符合Runnable协议的对象 实现自定义逻辑与langchain生态的无缝集成

# 导入LangChain核心的RunnableLambda类，用于将普通函数包装为可链式调用的对象
from langchain_core.runnables import RunnableLambda
# 导入OpenAI兼容的Chat模型类，用于调用大语言模型
from langchain_openai import ChatOpenAI

# ===================== 示例1：基础文本处理链（数据清洗ETL） =====================
# 构建文本清洗链，使用 | 运算符实现链式调用（类似Linux管道）
# 链式调用的执行顺序：从左到右，前一个函数的输出作为后一个函数的输入
text_clean_chain = (
    # 第一个处理步骤：去除字符串首尾的空白字符（空格、换行、制表符等）
        RunnableLambda(lambda doc: doc.strip())
        # 管道符：将前一步的输出作为后一步的输入
        |
        # 第二个处理步骤：将字符串全部转换为小写字母
        RunnableLambda(lambda doc: doc.lower())
)

# 调用清洗链，处理测试文本
result = text_clean_chain.invoke("  Hello, World!  ")
# 打印结果，预期输出：hello, world!
print(result)


# ===================== 示例2：带内容过滤的LLM调用链 =====================
# 打印中间结果并且过滤敏感词（在链中插入自定义处理逻辑）

# 自定义文本清洗函数：过滤敏感词
def filter_content(text: str) -> str:
    """
    敏感词过滤函数：将文本中的"暴力"替换为★★★

    Args:
        text (str): 需要过滤的原始文本

    Returns:
        str: 过滤后的文本
    """
    return text.replace("暴力", "★★★")


# 初始化大语言模型实例（这里使用通义千问，兼容OpenAI接口）
model = ChatOpenAI(
    model_name="qwen-plus",  # 指定模型名称（通义千问增强版）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问兼容接口地址
    api_key="",  # 注意：实际使用时应从环境变量获取，避免硬编码
    temperature=0.7  # 模型生成温度，值越高输出越随机，0.7为中等随机性
)

# 构建完整的处理链：数据提取 → 内容过滤 → 模型调用
chain = (
    # 第一步：从输入字典中提取"user_input"字段的值
        RunnableLambda(lambda x: x["user_input"])
        # 管道符：传递数据
        |
        # 第二步：调用自定义过滤函数处理文本
        RunnableLambda(filter_content)
        # 管道符：传递过滤后的文本给模型
        |
        # 第三步：调用大语言模型处理文本
        model
)

# 测试内容过滤链，传入包含敏感词的用户输入
result = chain.invoke({"user_input": "暴力内容"})
# 打印最终结果，预期模型会接收到"★★★内容"并生成响应
print("过滤后结果:", result)
