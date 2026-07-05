# 导入 LangChain 核心的 Runnable 相关模块
# Runnable 是 LangChain 中用于构建可组合、可运行的链的基础接口
# RunnableParallel 用于并行执行多个 Runnable 链
# RunnableLambda 用于将普通函数/匿名函数包装成 Runnable
from langchain_core.runnables import Runnable, RunnableParallel, RunnableLambda

# ==================== Runnable 核心概念实战示例 ====================
# 1. 多维度数据分析场景
# 说明：通过 RunnableParallel 并行执行三个不同的分析任务
# 注：以下 sentiment_analyzer/keyword_extractor/ner_recognizer 为示意函数，需自行实现
analysis_chain = RunnableParallel({
    "sentiment": sentiment_analyzer,  # 情感分析任务
    "keyword": keyword_extractor,  # 关键词提取任务
    "entities": ner_recognizer  # 命名实体识别任务（如人名、地名、机构名）
})

# 2. 多模型对比系统场景
# 说明：并行调用多个大模型，方便对比不同模型的输出结果
# 注：以下 gpt-3.5-turbo/gpt-4/claude-2 为示意的模型调用链，需自行实现
model_comparison = RunnableParallel({
    "gpt-3.5-turbo": gpt_35_turbo,  # GPT-3.5 模型调用链
    "gpt-4": gpt_4,  # GPT-4 模型调用链
    "claude-2": claude_2  # Claude-2 模型调用链
})

# 3. 智能文档处理系统场景
# 说明：并行处理文档的摘要生成、目录提取、基础统计信息计算
document_analyzer = RunnableParallel({
    "summary": summary_generator,  # 文档摘要生成（示意函数，需自行实现）
    "toc": toc_generator,  # 文档目录提取（示意函数，需自行实现）
    # 使用 RunnableLambda 包装匿名函数，计算文档的基础统计信息
    "status": RunnableLambda(
        lambda doc: {
            "char_count": len(doc),  # 计算文档字符数
            "page_count": doc.count("PAGE_BREAK") + 1  # 按 PAGE_BREAK 标记计算页数
        }
    )
})

# 4. 处理200页PDF文本（仅示意，需结合实际PDF解析逻辑）
# 实际使用时需先将PDF转为文本，再传入上述 chain 执行
# 示例：
# pdf_text = extract_text_from_pdf("200_pages.pdf")  # 自定义PDF文本提取函数
# analysis_result = document_analyzer.invoke(pdf_text)


# ==================== Runnable 完整实战案例（景点+书籍推荐） ====================
# 导入必要的 LangChain 模块
# ChatPromptTemplate：用于构建聊天型提示词模板
# ChatOpenAI：OpenAI 兼容的聊天模型调用接口（可对接第三方兼容OpenAI接口的模型）
# JsonOutputParser：用于将模型输出解析为 JSON 格式
from langchain_core.runnables import RunnableParallel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

# 1. 初始化大模型（这里使用阿里云通义千问的兼容OpenAI接口）
model = ChatOpenAI(
    model_name="qwen-plus",  # 指定模型名称（通义千问Plus）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的兼容接口地址
    api_key="",  # 阿里云API密钥（注意：实际生产环境需从环境变量读取，避免硬编码）
    temperature=0.7  # 模型生成温度（0-1，值越高输出越随机，越低越固定）
)

# 2. 初始化 JSON 输出解析器
# 作用：确保模型输出的文本能被正确解析为 Python 字典/JSON 格式
parser = JsonOutputParser()

# 3. 构建景点推荐的提示词模板
# from_template 方法从字符串模板创建提示词，支持变量替换（{city}/{num}）
prompt_attractions = ChatPromptTemplate.from_template(
    """列出{city}的{num}个著名景点，返回JSON格式：
    {{
    "num": "编号",
    "city": "城市",
    "introduce": "景点介绍"
    }}"""
)

# 4. 构建书籍推荐的提示词模板
prompt_books = ChatPromptTemplate.from_template(
    """列出与{city}相关的{num}本书籍，返回JSON格式：
    {{
    "num": "编号",
    "city": "城市",
    "introduce": "书籍介绍"
    }}"""
)

# 5. 构建独立的处理链（使用 | 运算符组合组件）
# 链执行流程：提示词模板（填充变量）→ 模型调用 → JSON解析
chain1 = prompt_attractions | model | parser  # 景点推荐链
chain2 = prompt_books | model | parser  # 书籍推荐链

# 6. 并行执行两条链
# RunnableParallel 将多个链包装为并行执行的链，返回字典格式的结果（key为指定名称，value为对应链的结果）
chain = RunnableParallel(
    attractions=chain1,  # 景点推荐结果的key
    books=chain2  # 书籍推荐结果的key
)

# 7. 主函数：测试并行链的执行
if __name__ == "__main__":
    # 定义输入数据（填充提示词模板的变量）
    input_data = {
        "city": "北京",
        "num": 3
    }

    # 调用并行链（invoke 方法为同步调用，返回最终结果）
    result = chain.invoke(input_data)

    # 打印结果
    print("景点推荐:", result["attractions"])
    print("书籍推荐:", result["books"])
