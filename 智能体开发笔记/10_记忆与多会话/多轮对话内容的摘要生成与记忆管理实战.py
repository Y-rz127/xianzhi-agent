# 从 LangChain 记忆模块导入对话摘要记忆类，用于实现对话内容的自动摘要存储
from langchain.memory import ConversationSummaryMemory
# 从 LangChain OpenAI 模块导入 ChatOpenAI 类，用于实例化大语言模型客户端
from langchain_openai import ChatOpenAI
# 从 pydantic 导入 SecretStr，用于安全存储和处理敏感信息（如 API 密钥）
from pydantic import SecretStr

# ---------------------- 大语言模型实例化 ----------------------
# 创建 ChatOpenAI 模型实例，用于后续对话摘要的生成
model = ChatOpenAI(
    model="qwen-plus",  # 指定要使用的模型名称（此处为通义千问 plus 版本）
    base_url= "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 阿里云通义千问的兼容 OpenAI 格式的 API 地址
    api_key=SecretStr(""),  # 安全存储 API 密钥（敏感信息），避免明文泄露风险
    temperature=0.7)  # 模型生成内容的随机性/创造性参数（0-1之间），0.7 表示兼顾逻辑性和一定创造性

# ---------------------- 对话摘要提示词模板 ----------------------
# 定义渐进式对话摘要的提示词模板，指导模型如何生成连贯的对话摘要
# 核心逻辑：基于历史摘要（{summary}）和新增对话内容（{new_lines}），生成更新后的完整摘要
prompt = """Progressively summarize the lines of conversation provided, adding onto the previous summary returning a new summary.

EXAMPLE
Current summary:
The human asks what the AI thinks of artificial intelligence. The AI thinks artificial intelligence is a force for good.

New lines of conversation:
Human: Why do you think artificial intelligence is a force for good?
AI: Because artificial intelligence will help humans reach their full potential.

New summary:
The human asks what the AI thinks of artificial intelligence. The AI thinks artificial intelligence is a force for good because it will help humans reach their full potential.
END OF EXAMPLE

Current summary:
{summary}

New lines of conversation:
{new_lines}

New summary:"""

# ---------------------- 对话摘要记忆初始化与使用 ----------------------
# 初始化对话摘要记忆对象，传入已实例化的大语言模型（用于自动生成摘要）
# 该对象会自动管理对话历史，将新对话内容整合到历史摘要中，无需手动处理
memory = ConversationSummaryMemory(llm=model)

# 模拟第一轮对话，将用户输入和 AI 回复保存到摘要记忆中
# input：用户输入内容；output：AI 回复内容
memory.save_context({"input": "Hi"}, {"output": "What's up?"})

# 模拟第二轮对话，继续将新的对话内容保存到摘要记忆中
# 此时记忆对象会自动调用模型，将本轮对话整合到上一轮的摘要中
memory.save_context({"input": "Not much you?"}, {"output": "Not much."})

# 从摘要记忆中加载当前的对话摘要（以字典格式返回）
# 返回结果中包含 "history" 键，对应的值为完整的对话摘要内容
summary = memory.load_memory_variables({})

# 打印最终的对话摘要结果
print(summary)
