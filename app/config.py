"""应用配置加载（对应 Java 项目的 application.yml）。"""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 大模型
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    dashscope_model: str = Field(default="qwen-plus", alias="DASHSCOPE_MODEL")

    # 服务
    app_port: int = Field(default=8123, alias="APP_PORT")
    debug: bool = Field(default=False, alias="DEBUG")
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
    embedding_model: str = Field(default="text-embedding-v2", alias="EMBEDDING_MODEL")
    vector_store_type: str = Field(default="chroma", alias="VECTOR_STORE_TYPE")
    milvus_uri: str = Field(default="", alias="MILVUS_URI")
    vector_db_dir: Path = Field(default=Path("./data/vector_db"), alias="VECTOR_DB_DIR")
    rag_k: int = Field(default=3, alias="RAG_K")
    # PostgreSQL + pgvector 连接串（VECTOR_STORE_TYPE=postgres 时使用）
    postgres_connection_string: str = Field(
        default="postgresql://postgres:postgres@localhost:5433/xianzhi",
        alias="POSTGRES_CONNECTION_STRING",
    )
    # PG 向量表名
    postgres_collection: str = Field(default="xianzhi_knowledge", alias="POSTGRES_COLLECTION")

    # LangSmith 可观测性
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="xianzhi-agent", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")


settings = Settings()
settings.memory_dir.mkdir(parents=True, exist_ok=True)
settings.vector_db_dir.mkdir(parents=True, exist_ok=True)