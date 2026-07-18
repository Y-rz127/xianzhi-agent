"""应用配置加载（对应 Java 项目的 application.yml）。"""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置模型（基于 pydantic-settings 从 .env / 环境变量加载，对应 Java 的 application.yml）。

    所有字段均通过 alias 支持环境变量覆盖，便于容器化部署。
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 大模型
    dashscope_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="DASHSCOPE_BASE_URL",
    )
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_model: str = Field(default="qwen-plus", alias="DASHSCOPE_MODEL")
    # LLM 生成参数
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    # Qwen3 推理模型 thinking 模式开关（默认关闭，避免 <think> 标签泄漏）
    llm_enable_thinking: bool = Field(default=False, alias="LLM_ENABLE_THINKING")
    llm_timeout: float = Field(default=60.0, alias="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")

    # 服务
    app_port: int = Field(default=8123, alias="APP_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
    # API 鉴权：逗号分隔的 API Key 列表；为空表示关闭鉴权（本地开发默认）
    api_keys: str = Field(default="", alias="API_KEYS")
    # 限流：单 IP 每分钟最大请求数（0=不限流；仅统计非静态/健康检查路径）
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    # 单条用户消息最大长度（字符），超出直接拒绝，防止 token 账单被打爆
    max_message_length: int = Field(default=4000, alias="MAX_MESSAGE_LENGTH")
    # CORS 允许的前端源（逗号分隔，支持通配符 *）
    # 生产环境应配置实际域名，如 https://your-domain.com,https://www.your-domain.com
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
        alias="CORS_ORIGINS",
    )

    # Agent
    agent_max_steps: int = Field(default=8, alias="AGENT_MAX_STEPS")

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
    embedding_local_model: str = Field(default="sentence-transformers", alias="EMBEDDING_LOCAL_MODEL")
    embedding_model: str = Field(default="text-embedding-v2", alias="EMBEDDING_MODEL")
    vector_store_type: str = Field(default="chroma", alias="VECTOR_STORE_TYPE")
    milvus_uri: str = Field(default="", alias="MILVUS_URI")
    vector_db_dir: Path = Field(default=Path("./data/vector_db"), alias="VECTOR_DB_DIR")
    rag_k: int = Field(default=2, alias="RAG_K")
    # 检索排序相关度权重（0~1）：越高越重视相关性、越低越重视多样性。
    # 主路径（KnowledgeBase._search_reranked）按关键词重叠重排，不依赖本值；
    # 本值仅在后端不支持 score 检索、回退 MMR retriever 时生效。
    rag_mmr_lambda: float = Field(default=0.7, alias="RAG_MMR_LAMBDA")
    # 检索距离阈值（仅对支持 score 的后端有效，如 Chroma L2 距离）。
    # None 表示不过滤；需按 embedding 模型距离分布实验标定，避免误伤召回。
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
    # 检索结果缓存 TTL（秒），0 表示不缓存；避免多轮对话重复调用 embedding
    rag_search_cache_ttl: int = Field(default=60, alias="RAG_SEARCH_CACHE_TTL")

    # LangSmith 可观测性
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="xianzhi-agent", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")

    # 微信小程序登录
    wechat_appid: str = Field(default="", alias="WECHAT_APPID")
    wechat_secret: str = Field(default="", alias="WECHAT_SECRET")


settings = Settings()
settings.memory_dir.mkdir(parents=True, exist_ok=True)
settings.vector_db_dir.mkdir(parents=True, exist_ok=True)