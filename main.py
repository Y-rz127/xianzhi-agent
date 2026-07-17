"""先知智能体 - 应用入口（对应 Java AiAgentApplication）。"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI

from app.api.routes import router
from app.api.state import set_instances
from app.config import settings
from app.memory import create_chat_memory
from app.observability import init_observability, record_request
from app.logger import log
from app.rag.vector_store import knowledge_base
from app.rag.rag_chain import RagChatChain
from app.tarot_app import TarotApp
from app.tools.mcp_client import mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. LangSmith 可观测性（最早初始化）
    init_observability()

    # 1. LLM - 使用 OpenAI 兼容模式调用千问（langchain-dashscope 不支持 bind_tools）
    # extra_body: 禁用 Qwen3 推理模型的 thinking 模式，避免 <think> 标签导致内容重复
    chat_model = ChatOpenAI(
        model=settings.dashscope_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        extra_body={"enable_thinking": settings.llm_enable_thinking},
    )

    # 2. 记忆
    memory = create_chat_memory()

    # 3. RAG 知识库初始化（失败不阻断主流程；内部根据文档指纹决定是否复用已有索引）
    knowledge_base.init()
    rag_chain = RagChatChain(chat_model=chat_model)

    # 4. 本地工具（含 RAG 检索）
    from app.tools.bazi import bazi_tools
    from app.tools.web_search import search_tools
    from app.tools.terminate import terminate_tools
    from app.tools.rag_search import rag_tools
    local_tools = bazi_tools + search_tools + terminate_tools + rag_tools

    # 5. 启动 MCP（高德地图，异步加载，失败不阻断）
    log.info("正在启动 MCP 服务...")
    await mcp_manager.start()

    # 6. 塔罗占卜
    tarot_app = TarotApp(chat_model=chat_model)

    # 7. 注册共享依赖：Xianzhi 按会话池化，首次请求时按需创建实例
    set_instances(chat_model, local_tools, memory, rag_chain, tarot_app)

    # 暖启动：预热排盘缓存（后台线程执行，不阻塞服务就绪）
    def _warm_cache():
        from app.tools.bazi import bazi_chart, bazi_analysis, bazi_dayun
        warm_dates = ["1990-01-01 12:00", "2000-01-01 12:00", "1985-01-01 12:00", "1995-01-01 12:00"]
        warm_genders = ["男", "女"]
        warm_count = 0
        for dt in warm_dates:
            for g in warm_genders:
                try:
                    bazi_chart.invoke({"birth_time": dt, "gender": g})
                    bazi_analysis.invoke({"birth_time": dt, "gender": g, "question": "整体命盘"})
                    bazi_dayun.invoke({"birth_time": dt, "gender": g, "count": 8})
                    warm_count += 1
                except Exception:
                    pass
        log.info("缓存预热完成: {} 条", warm_count)

    import threading
    threading.Thread(target=_warm_cache, daemon=True, name="bazi-cache-warmup").start()

    # 8. 初始化命例表
    try:
        from app.api.chart_cases import ensure_table
        ensure_table()
    except Exception as e:
        log.warning("命例表初始化失败（可能已存在）: {}", e)

    log.info("先知智能体启动完成 | 端口 {} | 本地工具 {} 个 | MCP 工具 {} 个 | RAG {}",
             settings.app_port, len(local_tools), len(mcp_manager.get_tools()),
             "就绪" if knowledge_base.ready else "未就绪")

    yield

    # 清理资源：关闭 PG 连接池（chart_cases 已复用 postgres_memory 的连接池）
    try:
        from app.memory.postgres_memory import close_global_conn
        close_global_conn()
    except Exception as e:
        log.warning("关闭 PG 连接池失败: {}", e)

    await mcp_manager.stop()
    log.info("先知智能体已关闭")


app = FastAPI(
    title="先知 - 八字命理分析预测智能体",
    version="0.1.0",
    lifespan=lifespan,
)
# CORS 跨域配置（通过环境变量 CORS_ORIGINS 配置，逗号分隔；支持通配符 *）
# 生产环境应配置实际域名，如 https://your-domain.com
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全中间件（后添加的先执行：限流在最外层，鉴权其次）
from app.security import ApiKeyAuthMiddleware, RateLimitMiddleware
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # API 响应设置严格 CSP（纯 JSON/SSE 无需加载任何资源）；
    # /docs、/redoc 等 Swagger 页面需加载 CDN 资源，不加 CSP 以免白屏
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # 静态资源增加缓存破坏
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """记录 API 请求指标，跳过静态资源与健康检查路径。"""
    path = request.url.path
    if path.startswith("/assets/") or path.startswith("/static/") or path == "/health" or path == "/api/ai/health":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    record_request(request.method, path, response.status_code, duration)
    return response


app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=False)