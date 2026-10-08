"""Alembic 迁移环境。

- 连接串复用应用配置（POSTGRES_CONNECTION_STRING / backend/.env），迁移与业务用同一数据库
- langchain_pg_* / pgvector 的表由对应库运行时自建（幂等 CREATE IF NOT EXISTS），
  排除在迁移管理之外，避免两边 DDL 互相干扰
- 应用启动仍保留建表自愈逻辑；空库部署流程：先 alembic upgrade head，再启动应用
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.postgres_connection_string)

# 空元数据：本项目不用 ORM 模型，autogenerate 以「库内现状」为唯一事实来源
target_metadata = MetaData()


def _include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name.startswith("langchain_pg_"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        target_metadata=target_metadata,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # NullPool：迁移是短命进程，不做跨调用连接复用
    engine = create_engine(config.get_main_option("sqlalchemy.url"), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()