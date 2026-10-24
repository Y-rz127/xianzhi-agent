"""先知智能体 - 应用入口。"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_openai import ChatOpenAI

from app.agent.checkpoint import close_checkpointer, init_checkpointer
from app.agent.context import AppContext, set_app_context
from app.api.health import readiness
from app.api.routes import router
from app.core.config import ensure_dirs, settings
from app.core.llm_failover import FailoverModel
from app.core.llm_health import SubModelSpec, probe_sub_models
from app.core.llm_params import temperature_for
from app.core.llm_throttle import ThrottledModel, llm_tag
from app.core.logger import log
from app.core.observability import init_observability, record_error, record_request
from app.core.request_context import RequestIdMiddleware, get_request_id
from app.core.security import ApiKeyAuthMiddleware, RateLimitMiddleware
from app.core.thinking_router import ThinkingRouter
from app.memory import create_chat_memory
from app.rag.vector_store import get_knowledge_base
from app.sub_app.tarot.tarot_app import TarotApp
from app.tools.bazi import bazi_analysis, bazi_chart, bazi_dayun, bazi_tools
from app.tools.huangli import huangli_tools
from app.tools.mcp_client import mcp_manager
from app.tools.rag_search import rag_tools
from app.tools.terminate import terminate_tools
from app.tools.web_search import search_tools
from app.tools.ziwei import ziwei_tools


def _close_quietly(client) -> None:
    """关闭 httpx 客户端，忽略异常。"""
    if client is None:
        return
    try:
        client.close()
    except Exception:
        pass


def _make_model(
    model_name: str,
    temperature: float,
    timeout: float,
    http_client,
    *,
    enable_thinking: bool,
) -> ChatOpenAI:
    """构造 DashScope ChatOpenAI 实例（轻量子模型：意图拆解 / Reviewer 审核）。

    `enable_thinking` 由调用方按**模型真实能力**显式给出，不再写死：qwen3.8 / glm-5 系
    只接受 True，传 False 会被 400 拒绝（`InvalidParameter ... restricted to True`）。
    曾写死 False，导致 Reviewer 的 LLM 深审每轮 400 后被兜底吞成"正则通过"——
    答案照常输出，审核层其实从未运行（2026-09-19 现场）。
    配置写错时由启动探活 `app/core/llm_health.py::probe_sub_models` 自动纠正并提示。
    """
    resolved_model = model_name or settings.dashscope_model
    return ChatOpenAI(
        model=resolved_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        temperature=temperature_for(resolved_model, temperature),
        timeout=timeout,
        max_retries=settings.llm_max_retries,
        # 思考型模型思考期无 chunk 流出，默认 120s 会误判"内容静默"（2026-10-06 实测
        # glm-5.3 思考 183s ⇒ 每轮 AI 简批都 ReadError）。与上面的 timeout 是两件事。
        stream_chunk_timeout=settings.llm_stream_chunk_timeout,
        extra_body={"enable_thinking": enable_thinking},
        http_client=http_client,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 后台初始化 task 需强引用（asyncio 只持弱引用，防被 GC 中断）
    _bg_init_tasks: list[asyncio.Task] = []
    retention_stop = asyncio.Event()
    ensure_dirs()

    # 专用线程池替换 asyncio 默认池（默认仅 min(32, cpu+4) 个线程）：
    # 同步 workflow/LLM 调用经 asyncio.to_thread 落此池，数十秒级长会话会占满默认小池拖垮全站
    thread_pool = ThreadPoolExecutor(
        max_workers=max(8, settings.thread_pool_size), thread_name_prefix="xianzhi-worker"
    )
    asyncio.get_running_loop().set_default_executor(thread_pool)

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
    if settings.memory_store_type.lower() != "postgres":
        log.warning("MEMORY_STORE_TYPE 非 postgres：多副本部署会话历史不一致，生产必须设为 postgres")
    if settings.vector_store_type.lower() != "postgres":
        log.warning("VECTOR_STORE_TYPE 非 postgres：多副本将各自维护本地向量索引，生产必须设为 postgres")

    # LangSmith 可观测性（最早初始化，确保后续 LangChain 调用均被追踪）
    init_observability()

    # LLM 终审（阶段三）：tools 层禁依赖 agent（架构守卫），bazi_full 的终审
    # 经依赖倒置注入；排盘/K线/聊天挂载在各自层内直连 agent.verdict
    from app.agent.verdict import chart_with_verdict_sync
    from app.tools.bazi import register_chart_verdict_hook

    register_chart_verdict_hook(chart_with_verdict_sync)

    # 答案生成主模型（直连 DashScope，不经系统代理）
    http = httpx.Client(trust_env=False)
    raw_chat_model = ChatOpenAI(
        model=settings.dashscope_model,
        base_url=settings.dashscope_url,
        api_key=settings.dashscope_api_key,
        temperature=temperature_for(settings.dashscope_model, settings.llm_temperature),
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        # 思考期无 chunk 流出的长静默预算，同 _make_model 内的说明
        stream_chunk_timeout=settings.llm_stream_chunk_timeout,
        extra_body={"enable_thinking": settings.llm_enable_thinking},
        http_client=http,
    )
    # 思考模式中间件：闲聊由调用方用 use_thinking(False) 关闭，其他路径默认开启。
    # 底层在构造期派生 ON/OFF 两份副本，运行时按 contextvar 透明切换。
    # ThrottledModel 提供并发信号量+按模型隔离的熔断；最外层 FailoverModel 按降级链切换模型。
    chat_model = ThrottledModel(ThinkingRouter(raw_chat_model, default_thinking=settings.llm_enable_thinking))

    def _make_failover_model(name: str) -> ThrottledModel:
        """降级链备选模型实例工厂（共用主 http 连接池；max_retries=1 快速失败换链）。"""
        llm = ChatOpenAI(
            model=name,
            base_url=settings.dashscope_url,
            api_key=settings.dashscope_api_key,
            timeout=settings.llm_timeout,
            max_retries=1,
            extra_body={"enable_thinking": settings.llm_enable_thinking},
            http_client=http,
        )
        return ThrottledModel(ThinkingRouter(llm, default_thinking=settings.llm_enable_thinking))

    # 降级链配置存 PG（Web 管理端热改），未配置时等效单主模型
    chat_model = FailoverModel(chat_model, _make_failover_model)

    # 意图拆解 / Reviewer 审核模型（独立实例，留空则复用主模型）。
    # 思考开关按角色显式给（DECOMPOSE_ENABLE_THINKING / REVIEWER_ENABLE_THINKING），
    # 不再写死：只接受思考模式的模型会在**每一轮**请求上 400（现场见 _make_model 注释）。
    # 子模型各自的 httpx 连接池：trust_env=False 直连 DashScope（不经系统代理）。
    # 为什么集中记一份：探活纠正时 `rebuild` 会再造一个实例（旧实例可能已被会话 Agent 持有，
    # 不能立刻 close），关停时统一收口，避免连接池泄漏。
    sub_model_http: list[httpx.Client] = []

    def _make_sub_model(
        model_name: str, temperature: float, timeout: float, enable_thinking: bool
    ) -> ThrottledModel:
        client = httpx.Client(trust_env=False)
        sub_model_http.append(client)
        return ThrottledModel(
            _make_model(model_name, temperature, timeout, client, enable_thinking=enable_thinking)
        )

    decompose_model = (
        _make_sub_model(settings.decompose_model, 0.1, 30.0, settings.decompose_enable_thinking)
        if settings.decompose_model
        else chat_model
    )
    reviewer_model = (
        _make_sub_model(settings.reviewer_model, 0.1, 60.0, settings.reviewer_enable_thinking)
        if settings.reviewer_model
        else chat_model
    )
    # 子应用（塔罗/紫微/六爻/合婚）解读模型：与问答主模型分开配，留空则复用主模型。
    # temperature/timeout 跟主模型一致（解读与问答同为"生成一段话"，不另立口径）。
    sub_app_model = (
        _make_sub_model(
            settings.sub_app_model,
            settings.llm_temperature,
            settings.llm_timeout,
            settings.sub_app_enable_thinking,
        )
        if settings.sub_app_model
        else chat_model
    )

    # 记忆（数据库不可达时降级，不阻断端口监听）
    memory = create_chat_memory()
    # LangGraph 断点恢复：checkpointer 初始化失败时无断点运行，不阻断启动
    init_checkpointer()

    local_tools = bazi_tools + search_tools + terminate_tools + rag_tools + huangli_tools + ziwei_tools
    tarot_app = TarotApp()  # 不注入模型：divine_stream 按请求取子应用解读模型（见 TarotApp docstring）

    # Xianzhi 按会话池化，首次请求时按需创建实例；HTTP handler 经依赖注入获取，WS 经模块级 get_app_context()
    app_ctx = AppContext(
        chat_model=chat_model,
        local_tools=local_tools,
        memory=memory,
        tarot_app=tarot_app,
        decompose_model=decompose_model,
        reviewer_model=reviewer_model,
        sub_app_model=sub_app_model,
    )
    app.state.app_context = app_ctx
    set_app_context(app_ctx)

    # 子模型启动探活规格：模型名非空的角色各探一次。
    # 目的不是"测通不通"，而是把**配置类错误**（如 enable_thinking 与模型能力不匹配）
    # 从"每轮请求里被兜底吞掉"提前到启动时可见/可自愈（见 app/core/llm_health.py）。
    sub_model_specs = [
        SubModelSpec(
            label="意图拆解",
            attr="decompose_model",
            env_key="DECOMPOSE_ENABLE_THINKING",
            model_name=settings.decompose_model,
            enable_thinking=settings.decompose_enable_thinking,
            rebuild=lambda flag: _make_sub_model(settings.decompose_model, 0.1, 30.0, flag),
            model=decompose_model,
        ),
        SubModelSpec(
            label="Reviewer 审核",
            attr="reviewer_model",
            env_key="REVIEWER_ENABLE_THINKING",
            model_name=settings.reviewer_model,
            enable_thinking=settings.reviewer_enable_thinking,
            rebuild=lambda flag: _make_sub_model(settings.reviewer_model, 0.1, 60.0, flag),
            model=reviewer_model,
        ),
        SubModelSpec(
            label="子应用解读",
            attr="sub_app_model",
            env_key="SUB_APP_ENABLE_THINKING",
            model_name=settings.sub_app_model,
            enable_thinking=settings.sub_app_enable_thinking,
            rebuild=lambda flag: _make_sub_model(
                settings.sub_app_model, settings.llm_temperature, settings.llm_timeout, flag
            ),
            model=sub_app_model,
        ),
    ]
    sub_model_specs = [s for s in sub_model_specs if s.model_name]

    # 报告任务后台 worker（Redis 队列消费；多副本各自消费，任务单飞）
    # 启动前先把上次进程崩溃遗留的 running 标失败，并把仍 pending 的任务重新入队
    try:
        from app.db import report_tasks as report_task_db

        await asyncio.to_thread(report_task_db.reconcile_after_restart)
    except Exception as e:
        log.warning("报告任务悬挂修复失败（数据库不可达，跳过）: {}", e)
    # 管理员账号存 PG：表为空时播种旧 JSON/环境变量默认账号；失败不阻断启动，但登录将 fail-closed
    try:
        from app.api.admin_accounts import init_admin_accounts

        await asyncio.to_thread(init_admin_accounts)
    except Exception as e:
        log.warning("管理员账号初始化失败（账号库不可用，管理员登录将被拒绝）: {}", e)
    from app.tasks.worker import requeue_pending, worker_loop

    try:
        requeued = await requeue_pending()
        if requeued:
            log.info("[report-worker] 启动重新入队 pending 任务 {} 个", requeued)
    except Exception as e:
        log.warning("报告任务重新入队失败（Redis 不可达，任务保持 pending）: {}", e)

    report_stop = asyncio.Event()
    report_workers = [
        # 传 None：报告属"子应用解读"，由 worker 按任务解析 SUB_APP_MODEL（未配置则回落主模型）。
        # 不在这里注入实例——模型可能被启动探活整体替换，抓死引用会让纠正失效。
        asyncio.create_task(worker_loop(None, report_stop))
        for _ in range(max(1, settings.report_task_workers))
    ]

    # 重/可失败的初始化放后台执行，避免阻塞端口监听导致存活探针失败
    async def _bg_init():
        if settings.rag_init_enabled:
            try:
                await asyncio.to_thread(get_knowledge_base().init)
            except Exception as e:
                log.warning("RAG 知识库初始化失败（可稍后重试）: {}", e)
        else:
            log.info("RAG 启动初始化已关闭（RAG_INIT_ENABLED=false）")
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

    # 子模型探活同样放后台：一次真实请求可能几秒，不能挡端口监听。
    # 探活会不会与首个请求抢跑？会，但纠正只影响**之后**创建的会话 Agent，
    # 且写错的配置本来就已经在每轮失败——不存在"比原来更差"的时间窗。
    async def _bg_probe_sub_models():
        if not sub_model_specs:
            return
        try:
            await asyncio.to_thread(probe_sub_models, sub_model_specs, app_ctx)
        except Exception as e:
            log.warning("[探活] 子模型探活整体失败（不影响服务）: {}", e)

    _bg_init_tasks.append(asyncio.create_task(_bg_probe_sub_models()))

    async def _bg_probe_chain():
        if not settings.llm_chain_probe_enabled:
            return
        try:
            with llm_tag("probe"):
                results = await asyncio.to_thread(chat_model.probe_chain)
        except Exception as e:
            log.warning("[chain-probe] 降级链探活整体失败: {}", e)
            return
        for item in results:
            if item.get("ok"):
                log.info("[chain-probe] {} 可用", item.get("model"))
            else:
                log.warning("[chain-probe] {} 不可用: {}", item.get("model"), item.get("error"))
                record_error("llm_chain_probe_failed")

    _bg_init_tasks.append(asyncio.create_task(_bg_probe_chain()))

    async def _bg_retention_cleanup():
        """用户数据保留期清理：启动先跑一次，之后每 24h 一次。"""
        from app.agent.checkpoint import purge_stale_checkpoints
        from app.db.retention import purge_expired_safely

        while not retention_stop.is_set():
            if settings.message_retention_days > 0:
                stats = await asyncio.to_thread(
                    purge_expired_safely, settings.message_retention_days
                )
                if any(stats.values()):
                    log.info("[retention] 清理过期数据: {}", stats)
            if settings.checkpoint_retention_hours > 0:
                removed = await asyncio.to_thread(
                    purge_stale_checkpoints, settings.checkpoint_retention_hours
                )
                if removed:
                    log.info("[retention] 清理残留 checkpoint thread: {}", removed)
            try:
                await asyncio.wait_for(retention_stop.wait(), timeout=86400)
            except asyncio.TimeoutError:
                pass

    retention_task = asyncio.create_task(_bg_retention_cleanup())
    _bg_init_tasks.append(retention_task)

    log.info(
        "先知智能体启动完成 | 版本 {} | 端口 {} | 本地工具 {} 个",
        settings.app_version,
        settings.app_port,
        len(local_tools),
    )

    yield

    retention_stop.set()
    try:
        await asyncio.wait_for(retention_task, timeout=2)
    except Exception:
        retention_task.cancel()

    # 清理 AppContext 注册（避免关停后旧实例被访问）
    try:
        set_app_context(None)
    except Exception:
        pass

    # 停止报告任务 worker：给 3s 让循环自然退出，未退出的强取消
    # （正在执行的长任务落在线程池里随进程终止，其 PG 状态由下次启动的 reconcile 修复）
    report_stop.set()
    try:
        await asyncio.wait_for(asyncio.gather(*report_workers), timeout=3)
    except Exception:
        for w in report_workers:
            w.cancel()

    close_checkpointer()

    # 关闭 PostgreSQL 连接池（db / memory / RAG 指纹共用同一模块级池，关一次即可）
    try:
        from app.db.pool import close_pool

        close_pool()
    except Exception as e:
        log.warning("关闭 PG 连接池失败: {}", e)

    # 关闭 LLM 客户端 httpx 连接池（仅独立子模型实例有各自的池；复用主模型的没有）
    for client in (*sub_model_http, http):
        _close_quietly(client)

    # 关闭专用线程池（取消排队任务，等待中的执行不再接收；已在执行的不强杀）
    try:
        thread_pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass

    # 关闭 Redis 全局连接
    try:
        from app.core.redis_client import close_redis

        await close_redis()
    except Exception:
        pass

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
    allow_credentials=True,  # 允许跨域请求携带认证信息（如 JWT）（仅限开发环境）（生产环境需鉴权）
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全中间件（后添加的先执行：限流在最外层，鉴权其次）
app.add_middleware(ApiKeyAuthMiddleware)
app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """安全响应头中间件：为所有响应自动注入安全相关的 HTTP 头"""
    response = await call_next(request)
    # 禁止浏览器 MIME 嗅探：强制使用服务端声明的 Content-Type，
    # 防止攻击者上传恶意文件后浏览器按错误类型解析执行
    response.headers["X-Content-Type-Options"] = "nosniff"
    # 禁止页面被 iframe 嵌入：防止点击劫持（Clickjacking）攻击
    response.headers["X-Frame-Options"] = "DENY"
    # 纯 JSON/SSE 无需加载资源，加严格 CSP；Swagger 页需加载 CDN 资源，不加以免白屏
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # 静态资源（/assets/）内容不变可长期缓存：max-age=1年 + immutable
    # 表示资源永不变化，浏览器无需发条件请求验证，直接用本地缓存
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """记录 API 请求指标，跳过静态资源与健康检查路径。"""
    raw_path = request.url.path
    if (
        raw_path.startswith("/assets/")
        or raw_path.startswith("/static/")
        or raw_path.startswith("/api/health")
        or raw_path.startswith("/api/ai/health")
    ):
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    # 指标 key 用路由模板而非原始 URL：带路径参数的路由（sessions/{id} 等 27 处）
    # 若按原始 path 记账，每个不同 id 都会在 _metrics["endpoints"] 常驻一个 key，
    # 只增不减，用户量上来后缓慢涨内存且拖慢 get_metrics 全量遍历。
    # 做法：路由匹配后 scope 带 path_params，把原始 path 中等于参数值的段替换为 {参数名}，
    # 保留完整前缀（route.path 只是相对路径，会丢 /api/ai/xianzhi 等前缀，不上）；
    # 参数值含 "/"（:path 转换器）时逐段替换失效，退回 route.path 保底有界；
    # 未匹配到路由（404）统一归并 "(unmatched)"，原始路径仍可从 recent_errors 观测。
    route = request.scope.get("route")
    if route is None:
        path = "(unmatched)"
    else:
        path_params = request.scope.get("path_params") or {}
        if any("/" in str(v) for v in path_params.values()):
            path = route.path
        else:
            name_by_value = {str(v): name for name, v in path_params.items()}
            path = "/".join(
                "{" + name_by_value[seg] + "}" if seg in name_by_value else seg
                for seg in raw_path.split("/")
            )
    record_request(
        request.method,
        path,
        response.status_code,
        time.perf_counter() - start,
        request_id=get_request_id(),
    )
    return response


# 请求 ID 中间件必须最后添加（add_middleware 插到栈顶），
# 这样限流/鉴权/业务日志都能带上 rid；SSE 的流式 body 也在其上下文内。
app.add_middleware(RequestIdMiddleware)


app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["Health"])
async def health():
    """健康检查（直接挂载，不经过 /ai 前缀，供 CloudBase 探针与外部监控使用）。"""
    ctx = getattr(app.state, "app_context", None)
    return {
        "status": "ok",
        "version": settings.app_version,
        "rag_ready": get_knowledge_base().ready,
        "workflow_backend": AppContext.workflow_backend(),
        "agent_pool": ctx.agent_pool_stats() if ctx else {"pool_size": 0, "max_agents": 0},
    }


@app.get("/api/health/live", tags=["Health"])
async def health_live():
    """liveness：只证明进程还活着，不查任何依赖，永远 200。"""
    return {"status": "ok", "version": settings.app_version}


@app.get("/api/health/ready", tags=["Health"])
async def health_ready():
    """readiness：PG / Redis / RAG 任一关键依赖不可用返回 503，供网关摘流量。"""
    result = await readiness()
    return JSONResponse(status_code=200 if result["ok"] else 503, content=result)


if __name__ == "__main__":
    # 端口：容器内（未显式设 PORT）强制 80，否则存活探针会因端口不匹配失败；本地开发以 settings.app_port 为准。
    # 必须读 settings.app_port 而非 os.environ——pydantic-settings 不会把 .env 写回环境变量，
    # 否则 APP_PORT=8123 会被无视、回退到 80；仍可用 PORT / APP_PORT 进程环境变量覆盖。
    in_container = os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST") is not None
    port = int(
        os.environ.get("PORT") or os.environ.get("APP_PORT") or (80 if in_container else settings.app_port)
    )
    # WORKERS 控制多进程（默认 1）；进程级状态的影响已在 lifespan 启动告警中显式提示
    workers = max(1, int(os.environ.get("WORKERS") or 1))
    # RELOAD=true 开启代码热重载（仅本地开发，.env 或进程环境变量均可）：改 .py 保存即生效。
    # 与多 worker 互斥（热重载强制单进程）；每次重载都会重跑 lifespan 的 RAG/MCP
    # 后台初始化与排盘缓存预热，保存频繁时启动日志会刷屏。
    if settings.reload:
        workers = 1
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=settings.reload, workers=workers)
