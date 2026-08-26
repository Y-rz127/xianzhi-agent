"""先知智能体 - 应用入口。"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI

from app.api.context import AppContext, set_app_context
from app.api.routes import router
from app.core.config import ensure_dirs, settings
from app.core.logger import log
from app.core.observability import init_observability, record_request
from app.core.security import ApiKeyAuthMiddleware, RateLimitMiddleware
from app.core.thinking_router import ThinkingRouter
from app.memory import create_chat_memory
from app.rag.vector_store import get_knowledge_base
from app.tarot.tarot_app import TarotApp
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_tools
from app.tools.mcp_client import mcp_manager
from app.tools.rag_search import rag_tools
from app.tools.terminate import terminate_tools
from app.tools.web_search import search_tools


def _close_quietly(client) -> None:
    """关闭 httpx 客户端，忽略异常。"""
    if client is None:
        return
    try:
        client.close()
    except Exception:
        pass


def _make_model(model_name: str, temperature: float, timeout: float, http_client) -> ChatOpenAI:
    """构造 DashScope ChatOpenAI 实例（thinking 始终关闭，用于轻量子模型）。"""
    return ChatOpenAI(
        model=model_name or settings.dashscope_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        temperature=temperature,
        timeout=timeout,
        max_retries=settings.llm_max_retries,
        extra_body={"enable_thinking": False},
        http_client=http_client,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 后台初始化 task 需强引用（asyncio 只持弱引用，防被 GC 中断）
    _bg_init_tasks: list[asyncio.Task] = []
    ensure_dirs()

    # API_KEYS 未配置时管理端点无鉴权，仅限开发环境；多 worker 时进程级状态彼此独立
    if not settings.api_keys.strip():
        log.warning(
            "API_KEYS 未配置：管理类端点（admin/rag/observability/cases）无鉴权，仅限开发环境，生产必须配置"
        )
    workers = int(os.environ.get("WORKERS") or 1)
    if workers > 1:
        log.warning(
            "多 worker 模式（WORKERS={}）：内存限流/会话 Agent 池/八字缓存为进程级状态，进程间相互独立（限流上限按 worker 数线性放宽）；横向扩容/跨副本限流需外置 Redis",
            workers,
        )

    # LangSmith 可观测性（最早初始化，确保后续 LangChain 调用均被追踪）
    init_observability()

    # 答案生成主模型（直连 DashScope，不经系统代理）
    http = httpx.Client(trust_env=False)
    raw_chat_model = ChatOpenAI(
        model=settings.dashscope_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        extra_body={"enable_thinking": settings.llm_enable_thinking},
        http_client=http,
    )
    # 思考模式中间件：闲聊由调用方用 use_thinking(False) 关闭，其他路径默认开启。
    # 底层在构造期派生 ON/OFF 两份副本，运行时按 contextvar 透明切换。
    chat_model = ThinkingRouter(raw_chat_model, default_thinking=settings.llm_enable_thinking)

    # 意图拆解 / Reviewer 审核模型（独立实例，留空则复用主模型）
    decompose_http = httpx.Client(trust_env=False) if settings.decompose_model else None
    decompose_model = _make_model(settings.decompose_model, 0.1, 30.0, decompose_http) if decompose_http else chat_model
    reviewer_http = httpx.Client(trust_env=False) if settings.reviewer_model else None
    reviewer_model = _make_model(settings.reviewer_model, 0.1, 60.0, reviewer_http) if reviewer_http else chat_model

    # 记忆（数据库不可达时降级，不阻断端口监听）
    memory = create_chat_memory()

    local_tools = bazi_tools + search_tools + terminate_tools + rag_tools
    tarot_app = TarotApp(chat_model=chat_model)

    # Xianzhi 按会话池化，首次请求时按需创建实例；HTTP handler 经依赖注入获取，WS 经模块级 get_app_context()
    app_ctx = AppContext(
        chat_model=chat_model,
        local_tools=local_tools,
        memory=memory,
        tarot_app=tarot_app,
        decompose_model=decompose_model,
        reviewer_model=reviewer_model,
    )
    app.state.app_context = app_ctx
    set_app_context(app_ctx)

    # 重/可失败的初始化放后台执行，避免阻塞端口监听导致存活探针失败
    async def _bg_init():
        try:
            await asyncio.to_thread(get_knowledge_base().init)
        except Exception as e:
            log.warning("RAG 知识库初始化失败（可稍后重试）: {}", e)
        try:
            log.info("正在启动 MCP 服务...")
            await mcp_manager.start()
        except Exception as e:
            log.warning("MCP 启动失败: {}", e)

        def _warm_cache():
            warm_dates = ["1990-01-01 12:00", "2000-01-01 12:00", "1985-01-01 12:00", "1995-01-01 12:00"]
            warm_count = 0
            warm_failed = 0
            for dt in warm_dates:
                for g in ("男", "女"):
                    try:
                        bazi_chart.invoke({"birth_time": dt, "gender": g})
                        bazi_analysis.invoke({"birth_time": dt, "gender": g, "question": "整体命盘"})
                        bazi_dayun.invoke({"birth_time": dt, "gender": g, "count": 8})
                        warm_count += 1
                    except Exception as e:
                        # 预热失败不阻断启动，但必须可见（可能暴露引擎/依赖问题）
                        warm_failed += 1
                        log.warning("缓存预热失败 {} {}: {}", dt, g, e)
            if warm_failed:
                log.warning("缓存预热完成: 成功 {} 条, 失败 {} 条", warm_count, warm_failed)
            else:
                log.info("缓存预热完成: {} 条", warm_count)

        try:
            threading.Thread(target=_warm_cache, daemon=True, name="bazi-cache-warmup").start()
        except Exception as e:
            log.warning("缓存预热线程启动失败（跳过预热）: {}", e)
        try:
            from app.api.cases import ensure_table

            ensure_table()
        except Exception as e:
            log.warning("命例表初始化失败（可能已存在）: {}", e)

    _bg_init_tasks.append(asyncio.create_task(_bg_init()))

    log.info("先知智能体启动完成 | 端口 {} | 本地工具 {} 个", settings.app_port, len(local_tools))

    yield

    # 清理 AppContext 注册（避免关停后旧实例被访问）
    try:
        set_app_context(None)
    except Exception:
        pass

    # 关闭 PG 连接池与 RAG 指纹持久化连接池（cases 已复用 postgres_memory 的连接池）
    try:
        from app.memory.postgres_memory import close_global_conn

        close_global_conn()
    except Exception as e:
        log.warning("关闭 PG 连接池失败: {}", e)
    try:
        from app.rag.vector_store import close_fp_pool

        close_fp_pool()
    except Exception as e:
        log.warning("关闭 RAG 指纹连接池失败: {}", e)

    # 关闭 LLM 客户端 httpx 连接池（仅独立实例，复用主模型的无需关闭）
    for client in (decompose_http, reviewer_http, http):
        _close_quietly(client)

    try:
        await mcp_manager.stop()
    except Exception:
        pass
    log.info("先知智能体已关闭")


app = FastAPI(
    title="先知 - 八字命理分析预测智能体",
    version="0.1.0",
    lifespan=lifespan,
)
# CORS：环境变量 CORS_ORIGINS 逗号分隔配置（支持通配符 *）
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全中间件（后添加的先执行：限流在最外层，鉴权其次）
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # 纯 JSON/SSE 无需加载资源，加严格 CSP；Swagger 页需加载 CDN 资源，不加以免白屏
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """记录 API 请求指标，跳过静态资源与健康检查路径。"""
    path = request.url.path
    if (
        path.startswith("/assets/")
        or path.startswith("/static/")
        or path in ("/health", "/api/health", "/api/ai/health")
    ):
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    record_request(request.method, path, response.status_code, time.perf_counter() - start)
    return response


app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["Health"])
async def health():
    """健康检查（直接挂载，不经过 /ai 前缀，供 CloudBase 探针与外部监控使用）。"""
    ctx = getattr(app.state, "app_context", None)
    return {
        "status": "ok",
        "rag_ready": get_knowledge_base().ready,
        "workflow_backend": AppContext.workflow_backend(),
        "agent_pool": ctx.agent_pool_stats() if ctx else {"pool_size": 0, "max_agents": 0},
    }


if __name__ == "__main__":
    # 端口：容器内（未显式设 PORT）强制 80，否则存活探针会因端口不匹配失败；本地开发以 settings.app_port 为准。
    # 必须读 settings.app_port 而非 os.environ——pydantic-settings 不会把 .env 写回环境变量，
    # 否则 APP_PORT=8123 会被无视、回退到 80；仍可用 PORT / APP_PORT 进程环境变量覆盖。
    in_container = os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST") is not None
    port = int(os.environ.get("PORT") or os.environ.get("APP_PORT") or (80 if in_container else settings.app_port))
    # WORKERS 控制多进程（默认 1）；进程级状态的影响已在 lifespan 启动告警中显式提示
    workers = max(1, int(os.environ.get("WORKERS") or 1))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=workers)
