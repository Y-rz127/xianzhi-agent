"""PostgreSQL 模块级连接池（懒创建、线程安全），全库数据访问共用。

psycopg.Connection 非线程安全，全局单连接在并发下会互相干扰，连接池按需检出/归还。
原定义位于 app.memory.postgres_memory，因业务数据访问（app.db.*）也在使用，
抽为本基础设施模块，db 与 memory 平级引用。
"""

from __future__ import annotations

import threading

from app.core.config import settings
from app.core.logger import log

pg_pool = None
pool_lock = threading.Lock()


def check_connection(conn) -> bool:
    """借出连接前探活：失败则丢弃重建（服务端超时断开的死连接不可外借）。"""
    try:
        conn.execute("SELECT 1")
        return True
    except Exception as e:  # noqa: BLE001 - 任何异常都视为连接不可用
        log.warning("连接池健康检查失败，丢弃该连接: {}", e)
        return False


def get_pool():
    """获取模块级连接池，懒创建（双重检查，避免并发重复建池）。"""
    global pg_pool
    with pool_lock:
        if pg_pool is None:
            from psycopg_pool import ConnectionPool

            pg_pool = ConnectionPool(
                settings.pg_dsn(),
                min_size=settings.pg_pool_min_size,
                max_size=settings.pg_pool_max_size,
                # 并发超池时最多等待这么久，避免请求无限悬挂
                timeout=settings.pg_pool_timeout,
                kwargs={"autocommit": True},
                check=check_connection,  # 借出前探活，避免借到被服务端断开的死连接
                max_lifetime=1800,  # 空闲连接 30 分钟主动回收，降低踩到 PG 空闲超时的概率
                open=True,
            )
        return pg_pool


def close_pool() -> None:
    """关闭模块级连接池（应用退出时调用）。"""
    global pg_pool
    with pool_lock:
        if pg_pool is not None:
            try:
                pg_pool.close()
            except Exception as e:
                log.warning("关闭 PG 连接池失败: {}", e)
            finally:
                pg_pool = None


# LangGraph checkpointer 专用池：psycopg 需要 dict_row 行工厂；
# 不能复用业务池（业务代码大量按 tuple 取值，改全局 row_factory 会破坏现有查询）。
checkpoint_pool = None
checkpoint_pool_lock = threading.Lock()


def get_checkpoint_pool():
    """懒创建 checkpointer 专用连接池（dict_row + autocommit）。"""
    global checkpoint_pool
    with checkpoint_pool_lock:
        if checkpoint_pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            checkpoint_pool = ConnectionPool(
                settings.pg_dsn(),
                min_size=1,
                max_size=2,
                timeout=settings.pg_pool_timeout,
                kwargs={"autocommit": True, "row_factory": dict_row},
                check=check_connection,
                max_lifetime=1800,
                open=True,
            )
        return checkpoint_pool


def close_checkpoint_pool() -> None:
    global checkpoint_pool
    with checkpoint_pool_lock:
        pool = checkpoint_pool
        checkpoint_pool = None
    if pool is not None:
        try:
            pool.close()
        except Exception as e:
            log.warning("关闭 checkpointer 连接池失败: {}", e)
