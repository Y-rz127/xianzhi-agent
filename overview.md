# 架构深度分析 · 概览

对 `xianzhi-agent`（八字命理智能体，FastAPI + LangChain/LangGraph + pgvector）做了静态结构与关键路径精读分析，产出完整报告：`docs/architecture_review.md`（含 3 张内联架构图）。

## 关键发现
- **冗余**：两套编排后端（`builtin` + `LangGraph` 镜像同 6 节点）、两套 RAG 检索路径（`search_deduped` vs `_retrieve_rules`）口径分叉。
- **耦合**：`app.api.state` 全局服务定位器 + `postgres_memory → tools.bazi` 分层倒置 + `main.py:17` 导入期构造 `knowledge_base`。
- **性能**：`async` handler 内同步 psycopg 调用阻塞事件循环（40+ 处）；单进程单事件循环部署。
- **稳定**：DB/记忆层广泛静默 `except Exception` 吞错；`API_KEYS` 默认空（鉴权关闭）；`requirements.lock` 由 Python 3.10 生成却约束 `>=3.11`。

## 核心建议（含优先级/收益/ADR）
- P0：异步化 DB 访问（R1）、收紧异常（R2）、收敛编排后端（R3）。
- P1：统一 RAG 检索入口（R4）、解耦 state→AppContext 注入（R5）、纠正分层倒置（R6）、依赖治理对齐（R7）。
- P2：启动去副作用（R8）、拆分超大模块（R9）、部署加固+多副本（R10）、前端共享 API 层（R11）。

目标：不删减任何功能，关键路径延迟↓、并发↑、可观测性↑、可维护性↑。
