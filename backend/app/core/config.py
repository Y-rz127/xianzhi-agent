"""应用配置：基于 pydantic-settings 从 .env / 环境变量加载。"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置模型，字段均通过 alias 支持环境变量覆盖，便于容器化部署。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 大模型
    dashscope_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="DASHSCOPE_BASE_URL",
    )
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_model: str = Field(default="qwen3.8-flash", alias="DASHSCOPE_MODEL")
    asr_model: str = Field(default="qwen-audio-3.0-asr-flash", alias="ASR_MODEL")
    # 意图拆解/Reviewer 审核模型（轻量独立实例，留空则复用主模型）
    decompose_model: str = Field(default="", alias="DECOMPOSE_MODEL")
    reviewer_model: str = Field(default="", alias="REVIEWER_MODEL")
    # LLM 生成参数；temperature 默认不传（None）：
    # kimi-k3 等模型不接受 temperature 参数，显式设置会被 400 拒绝；
    # 使用 qwen 等支持采样温度的模型时可设 LLM_TEMPERATURE=0.7
    llm_temperature: Optional[float] = Field(default=None, alias="LLM_TEMPERATURE")
    llm_enable_thinking: bool = Field(default=False, alias="LLM_ENABLE_THINKING")
    llm_timeout: float = Field(default=60.0, alias="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")

    # LLM 背压与熔断（DashScope 配额保护）
    # 全模型共享的并发上限：队列满时按 llm_queue_timeout 等待，超时抛 LLMBusyError
    llm_max_concurrency: int = Field(default=20, alias="LLM_MAX_CONCURRENCY")
    llm_queue_timeout: float = Field(default=120.0, alias="LLM_QUEUE_TIMEOUT")
    # 连续失败达阈值触发熔断（快速失败，避免上游故障时每个请求空等重试）
    llm_circuit_failure_threshold: int = Field(default=8, alias="LLM_CIRCUIT_FAILURE_THRESHOLD")
    llm_circuit_open_seconds: float = Field(default=30.0, alias="LLM_CIRCUIT_OPEN_SECONDS")
    # LLM 成本换算表（可选，JSON）：key 为模型名前缀（最长匹配），
    # value 为 {"input": 输入单价, "output": 输出单价}，单位 元/百万 token。
    # 留空则 /metrics 只统计 token 不折算金额。例（单价请按实际填写）：
    # LLM_PRICE_MAP={"kimi-k3": {"input": 4, "output": 16}, "qwen3.8": {"input": 1, "output": 4}}
    llm_price_map: str = Field(default="", alias="LLM_PRICE_MAP")

    # 服务
    app_port: int = Field(default=8123, alias="APP_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    # 代码热重载（仅本地开发）：改 .py 保存即重启，强制单进程，勿用于生产
    reload: bool = Field(default=False, alias="RELOAD")
    # API 鉴权：逗号分隔的 API Key 列表，为空表示关闭鉴权（本地开发默认）
    api_keys: str = Field(default="", alias="API_KEYS")
    # 限流：单 IP 每分钟最大请求数（0=不限流）
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    # 经可信代理（CDN/CLB）部署时开启：从 X-Forwarded-For 取真实客户端 IP
    # 前提是容器仅能经网关访问（CloudBase 默认如此），否则该头可被客户端伪造
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")
    # Redis（限流等共享状态；多副本部署必须，未配置时限流降级为进程内存）
    redis_url: str = Field(default="", alias="REDIS_URL")
    # 单条用户消息最大长度（字符），超出直接拒绝，防止 token 账单被打爆
    max_message_length: int = Field(default=4000, alias="MAX_MESSAGE_LENGTH")
    # CORS 允许的前端源（逗号分隔，支持通配符 *）
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
        alias="CORS_ORIGINS",
    )

    # Agent
    agent_max_steps: int = Field(default=8, alias="AGENT_MAX_STEPS")

    # 并发与连接池
    # 专用线程池（替换 asyncio 默认池，默认仅 min(32, cpu+4)）：
    # 同步 workflow/LLM 调用经 asyncio.to_thread 落此池，长会话会长时间占用线程
    thread_pool_size: int = Field(default=128, alias="THREAD_POOL_SIZE")
    pg_pool_min_size: int = Field(default=2, alias="PG_POOL_MIN_SIZE")
    pg_pool_max_size: int = Field(default=20, alias="PG_POOL_MAX_SIZE")
    # 连接池借出超时（秒）：并发超池时最多等待这么久，避免请求无限悬挂
    pg_pool_timeout: float = Field(default=10.0, alias="PG_POOL_TIMEOUT")
    # 报告任务后台 worker 数量（PDF 渲染 CPU 密集；LLM 报告受全局背压约束）
    report_task_workers: int = Field(default=2, alias="REPORT_TASK_WORKERS")

    # 搜索 API
    search_api_key: str = Field(default="", alias="SEARCH_API_KEY")

    # 记忆
    memory_dir: Path = Field(default=Path("./data/memory"), alias="MEMORY_DIR")
    # 记忆存储类型：file | postgres
    memory_store_type: str = Field(default="file", alias="MEMORY_STORE_TYPE")
    # PG 记忆表名（memory_store_type=postgres 时使用）
    memory_table_name: str = Field(default="message_store", alias="MEMORY_TABLE_NAME")

    # MCP 服务
    amap_maps_api_key: str = Field(default="", alias="AMAP_MAPS_API_KEY")
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")

    # RAG 知识库
    embedding_local_model: str = Field(
        default="./models/Xorbits/bge-small-zh-v1.5", alias="EMBEDDING_LOCAL_MODEL"
    )
    embedding_model: str = Field(default="text-embedding-v2", alias="EMBEDDING_MODEL")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    # 向量数据库类型：chroma | postgres
    vector_store_type: str = Field(default="chroma", alias="VECTOR_STORE_TYPE")
    # 向量数据库目录（VECTOR_STORE_TYPE=chroma 时使用）
    vector_db_dir: Path = Field(default=Path("./data/vector_db"), alias="VECTOR_DB_DIR")
    rag_k: int = Field(default=1, alias="RAG_K")
    # 检索排序相关度权重（0~1），仅在后端不支持 score 检索、回退 MMR retriever 时生效
    rag_mmr_lambda: float = Field(default=0.7, alias="RAG_MMR_LAMBDA")
    # 检索距离阈值（仅对支持 score 的后端有效，如 Chroma L2 距离）；None 表示不过滤
    rag_distance_threshold: Optional[float] = Field(default=None, alias="RAG_DISTANCE_THRESHOLD")
    # PostgreSQL + pgvector 连接串（VECTOR_STORE_TYPE=postgres 时使用）
    postgres_connection_string: str = Field(
        default="postgresql://postgres:postgres@localhost:5433/xianzhi",
        alias="POSTGRES_CONNECTION_STRING",
    )
    # PG 向量表名
    postgres_collection: str = Field(default="xianzhi_knowledge", alias="POSTGRES_COLLECTION")
    # DashScope embedding 不可用时回退本地 HuggingFace 模型（避免欠费导致服务崩溃）
    embedding_local_fallback: bool = Field(default=True, alias="EMBEDDING_LOCAL_FALLBACK")
    # 检索结果缓存 TTL（秒），0=不缓存；避免多轮对话重复调用 embedding
    rag_search_cache_ttl: int = Field(default=60, alias="RAG_SEARCH_CACHE_TTL")
    # Embedding 批量参数：单次请求最大条数与总字符上限。
    # DashScope 部分文本嵌入模型（如 qwen 系 flash）在长输入/大批量下会"挂死不返回"而非报错，
    # 收敛到安全的条数与总字符数可避免这类模型把全量重建拖到超时（详见 embeddings.py）。
    embedding_batch_size: int = Field(default=10, alias="EMBEDDING_BATCH_SIZE")
    embedding_max_chars_per_batch: int = Field(default=6000, alias="EMBEDDING_MAX_CHARS_PER_BATCH")

    # LangSmith 可观测性
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="xianzhi-agent", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")

    # 微信小程序登录
    wechat_appid: str = Field(default="", alias="WECHAT_APPID")
    wechat_secret: str = Field(default="", alias="WECHAT_SECRET")

    def pg_dsn(self, timeout: int = 5) -> str:
        """容器与数据库不在同一网络平面时连接会长时间挂起、拖垮启动，统一兜底追加 connect_timeout。"""
        dsn = self.postgres_connection_string
        if "connect_timeout" in dsn:
            return dsn
        sep = "&" if "?" in dsn else "?"
        return f"{dsn}{sep}connect_timeout={timeout}"


def ensure_dirs() -> None:
    """创建运行时目录。由启动方（lifespan）显式调用，避免导入 config 产生文件系统副作用。"""
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    settings.vector_db_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
