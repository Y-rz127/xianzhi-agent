# 【大模型接入LangSmith实战】：配置LangSmith实现大模型调用的链路追踪、运行监控和异常告警
import os          # 用于设置系统环境变量
import logging     # 用于日志输出（辅助调试LangSmith接入过程）
# 导入OpenAI兼容的大模型客户端（支持通义千问等模型）
from langchain_openai import ChatOpenAI
# 导入SecretStr用于安全存储API密钥（避免明文泄露）
from pydantic import SecretStr

# ====================== 基础日志配置（可选） ======================
# 设置日志级别为DEBUG，便于调试LangSmith的接入和调用过程
# 可看到LangSmith的请求/响应日志，排查接入失败等问题
logging.basicConfig(level=logging.DEBUG)

# ====================== LangSmith核心配置（关键） ======================
# 1. 启用LangChain V2版本的追踪功能（必须设为true才会开启链路追踪）
os.environ["LANGCHAIN_TRACING_V2"] = "true"
# 2. LangSmith的API端点（固定值，无需修改）
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# 3. LangSmith的API密钥（核心，替换为自己的密钥，在LangSmith平台获取）
#    作用：鉴权，确认当前调用归属的账号/项目
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
# 4. LangSmith的项目名称（自定义）
#    作用：在LangSmith平台按项目分类查看追踪数据，便于多项目管理
os.environ["LANGCHAIN_PROJECT"] = "agent_v1"

# ====================== 初始化大模型 ======================
# 创建ChatOpenAI实例（兼容通义千问等OpenAI格式的模型）
model = ChatOpenAI(
    model="qwen-plus",  # 模型名称（这里使用通义千问增强版）
    # 阿里云通义千问的OpenAI兼容接口地址（固定值）
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    # 通义千问的API密钥（安全存储为SecretStr，避免明文暴露）
    api_key=SecretStr(""),
    temperature=0.7  # 温度系数：控制回答的随机性，0.7为适中值
)

# ====================== 执行模型调用（触发LangSmith追踪） ======================
# 调用模型并传入问题：该调用会被LangSmith完整追踪
resp = model.invoke("什么是智能体?")
# 打印模型返回的回答内容
print("模型回答：", resp.content)

# 【关键提示】：执行后可访问 https://smith.langchain.com/ 登录查看：
# 1. 调用链路：模型的输入/输出、耗时、Token用量
# 2. 监控数据：调用成功率、响应时间分布
# 3. 告警配置：可在LangSmith平台设置超时、失败率等告警规则
