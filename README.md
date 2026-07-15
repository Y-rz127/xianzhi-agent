# 先知 · 八字命理分析预测智能体

> 基于多 Agent 协作架构的八字命理分析平台，融合传统命理学与现代 AI 智能体技术。

## 项目简介

先知是一个集八字排盘、命理分析、塔罗占卜、恋爱咨询于一体的智能体平台。核心采用 **Supervisor + 专业 Worker + Reviewer** 三层架构，让命理分析具备专业深度与严谨性。

### 核心能力

- **八字排盘**：四柱、大运、流年、五行、十神、格局、用神、调候，全套排盘
- **命理问答**：基于 RAG 知识库的术语解释、古籍引用、专项断事
- **合婚分析**：双方八字合婚，五行匹配度评分
- **塔罗占卜**：78 张完整塔罗牌，单张/三张/关系牌阵，AI 流式解读
- **恋爱咨询**：独立 dark night 主题的恋爱分支
- **PDF 报告**：命盘详情 PDF 下载

### 技术栈

| 层级 | 技术 |
|------|------|
| **大模型** | 阿里云百炼 DashScope（Qwen3，OpenAI 兼容模式） |
| **Agent 框架** | LangChain + LangGraph（可选） |
| **Web 框架** | FastAPI + WebSocket（小程序兼容） |
| **RAG** | Chroma 向量库 + DashScope Embedding |
| **记忆持久化** | File（默认） / PostgreSQL |
| **MCP** | 高德地图 MCP |
| **可观测性** | LangSmith + Prometheus |
| **前端** | Vue3 + UniApp（小程序） / Vite（Web） |
| **排盘引擎** | lunar-python |

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      前端（小程序 / Web）                      │
│  先知聊天 │ 恋爱咨询 │ 塔罗占卜 │ 命例库 │ 合婚 │ 命盘详情    │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket / REST
┌──────────────────────────┴──────────────────────────────────┐
│                        FastAPI 服务层                         │
│  /api/ai/xianzhi │ /api/ai/love │ /api/ai/tarot │ /api/ai/rag│
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   ┌─────────┐      ┌─────────────┐    ┌───────────┐
   │  ReAct   │      │  workflow   │    │  独立 App │
   │ (无命盘) │      │ (有命盘)    │    │           │
   │          │      │ Supervisor  │    │ LoveApp   │
   │ LLM 自主 │      │ + Worker    │    │ TarotApp  │
   │ 调工具   │      │ + Reviewer  │    │ RagChain  │
   └─────────┘      └─────────────┘    └───────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
   ┌──────────────────────────────────────────────────────┐
   │  本地工具（12 个）│ MCP 工具（高德）│ RAG 知识库       │
   │  bazi_*  │ search_knowledge │ search_web │ terminate  │
   └──────────────────────────────────────────────────────┘
```

## 双路径智能体

先知智能体根据命盘上下文自动切换执行路径：

### ReAct 路径（无命盘）

LLM 自主规划、自主调工具，适合首次对话、用户主动提供生辰、纯术语问答。

```
用户："04年端午节辰时男，帮我排盘"
→ LLM 调 search_web 查端午真实公历（避免农历换算错误）
→ LLM 调 bazi_full 排盘
→ LLM 调 search_knowledge 查佐证
→ LLM 生成回答
→ 挂载命盘上下文（后续对话切 workflow）
```

### workflow 路径（有命盘，多 Agent 协作）

**Supervisor + 专业 Worker + Reviewer** 三层架构：

```
1. classify_question          → 意图分类（事业/财运/婚姻/健康/…）
2. WORKERS.get(domain)         → Supervisor 分派专业 Worker
3. _retrieve_rules(worker)     → Worker 专属检索（叠加 extra_queries）
4. _build_messages(worker)     → Worker 专属断法 prompt
5. _invoke                    → Worker 生成回答
6. _reviewer.review()         → Reviewer 三重校验
   ├─ 事实校验：四柱/大运/流年是否与排盘一致
   ├─ 古籍真实性：引用的古籍是否在检索结果中（防杜撰）
   └─ 合规校验：扫描生死/赌博/符咒/堕胎红线关键词
7. 通过 → 返回 / 未通过 → Reflextion 回退修复
```

详细架构见 [docs/multi_agent_architecture.md](docs/multi_agent_architecture.md)。

### 闲聊双重短路

避免"你好"也触发工具调用：

- **ReAct 路径**：`_is_chitchat()` 判定 → 直接调 LLM 闲聊回复，0 工具调用
- **workflow 路径**：chitchat Worker 跳过检索 + 跳过命盘事实注入

## 功能模块

### 1. 先知智能体（核心）

- **排盘**：四柱八字、大运流年、五行十神、格局用神、纳音神煞
- **断事**：事业/财运/婚姻/健康/学业/官非/六亲/性格
- **合婚**：双方八字匹配度评分
- **命例库**：历史命例展示与学习
- **PDF 报告**：命盘详情导出

### 2. 塔罗占卜（紫金神秘主题）

- 78 张完整塔罗牌（22 大阿卡纳 + 56 小阿卡纳）
- 三种牌阵：每日一牌 / 过去现在未来 / 关系牌阵
- Fisher-Yates 洗牌算法，随机正逆位
- 翻牌动画（正反面分离设计）
- AI 流式解读（mystical tarot reader 人设）

### 3. 恋爱咨询（dark night 主题）

- 独立 dark night 暗色主题
- 恋爱关系专项咨询

### 4. RAG 命理知识库

知识库收录 34 份命理文档：

- **基础理论**：天干地支、五行生克、十神、用神、大运流年、纳音、神煞、排盘基础
- **断法体系**：事业财运、婚恋关系、合冲刑害、大运流年、格局、六亲、健康、学业、官非、性格、子女、贫富层次、男女命差异、流月流日
- **标准流程**：标准分析流程、术语白话对照、问答模板库
- **古籍**：渊海子平、子平真诠、穷通宝鉴、滴天髓、三命通会、神峰通考、盲派口诀
- **命例案例库**：历史命例

## 项目结构

```
xianzhi-agent/
├── main.py                      # 应用入口（FastAPI + lifespan）
├── app/
│   ├── agent/                   # 智能体核心
│   │   ├── xianzhi.py            # 先知主类（ReAct + workflow 分流 + 闲聊短路）
│   │   ├── xianzhi_workflow.py   # Supervisor + Worker + Reviewer 核心
│   │   ├── xianzhi_langgraph.py  # LangGraph 可选封装
│   │   ├── base_agent.py         # Agent 基类
│   │   ├── tool_call_agent.py    # 工具调用 Agent
│   │   └── react_agent.py        # ReAct Agent
│   ├── api/                     # REST/WebSocket 接口
│   │   ├── xianzhi.py            # 先知聊天 WS
│   │   ├── love.py               # 恋爱 WS
│   │   ├── tarot.py              # 塔罗 WS
│   │   ├── rag.py                # 问答 WS
│   │   ├── chart_cases.py        # 命例库 REST
│   │   ├── observability.py      # 可观测性
│   │   ├── tools.py              # 工具接口
│   │   └── routes.py             # 路由聚合
│   ├── domain/                  # 领域逻辑
│   │   └── bazi_engine.py        # 八字排盘引擎
│   ├── tools/                   # 工具集
│   │   ├── bazi.py               # 八字工具（7个）
│   │   ├── rag_search.py         # 知识库检索工具
│   │   ├── web_search.py         # 联网搜索（Serper.dev）
│   │   ├── terminate.py          # 终止工具
│   │   ├── mcp_client.py        # MCP 客户端（高德）
│   │   ├── pdf_report.py        # PDF 报告生成
│   │   ├── report_generator.py  # 报告生成器
│   │   └── cache.py              # 排盘缓存
│   ├── rag/                     # RAG 知识库
│   │   ├── vector_store.py       # 向量库封装
│   │   ├── rag_chain.py          # RAG 链
│   │   └── knowledge_docs/       # 命理文档（34份）
│   ├── memory/                  # 记忆系统
│   │   ├── chat_memory.py        # 对话记忆
│   │   └── postgres_memory.py    # PostgreSQL 持久化
│   ├── evaluation/              # 离线评估
│   │   └── xianzhi_eval.py       # 答案质量检查
│   ├── love_app.py              # 恋爱大师 App
│   ├── tarot_app.py             # 塔罗 App
│   ├── observability.py         # LangSmith 可观测性
│   ├── config.py                # 配置
│   └── logger.py                # 日志（loguru）
├── frontend/                    # Web 前端（Vue3 + Vite）
├── uniapp/                      # 小程序前端（UniApp）
├── docs/
│   └── multi_agent_architecture.md  # 多 Agent 协作架构文档
├── 学习资料/
│   └── 智能体开发笔记/          # 智能体开发学习笔记
├── .env.example                 # 环境变量示例
├── requirements.txt             # Python 依赖
├── Dockerfile                   # 后端容器
├── docker-compose.yml           # 容器编排
├── start.ps1 / stop.ps1         # Windows 启停脚本
└── pyproject.toml
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（前端）
- 阿里云百炼 API Key

### 1. 配置环境变量

```powershell
cp .env.example .env
```

编辑 `.env`，至少配置：

```env
DASHSCOPE_API_KEY=your-api-key
DASHSCOPE_MODEL=qwen3.7-max-2026-06-08
APP_PORT=8123
```

可选：Serper.dev（联网搜索）、高德地图 MCP、LangSmith 可观测性。

### 2. 安装依赖

```powershell
# 后端
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 前端（Web）
cd frontend
npm install

# 前端（小程序）
cd uniapp
npm install
```

### 3. 启动服务

```powershell
# 后端
.venv\Scripts\python.exe main.py
# 或用启动脚本
.\start.ps1

# 前端（Web）
cd frontend
npm run dev

# 前端（小程序）
cd uniapp
npm run dev:mp-weixin
```

访问 `http://localhost:8123`（后端 API）或 `http://localhost:5173`（前端 dev）。

### 4. Docker 部署

```powershell
docker-compose up -d
```

## API 接口

### WebSocket（小程序兼容）

| 端点 | 用途 |
|------|------|
| `/api/ai/xianzhi/ws` | 先知聊天（排盘 + 命理分析） |
| `/api/ai/love/ws` | 恋爱咨询 |
| `/api/ai/tarot/ws` | 塔罗占卜解读 |
| `/api/ai/rag/ws` | 命理理论问答 |

### REST

| 端点 | 用途 |
|------|------|
| `GET /api/ai/xianzhi/chart` | 结构化命盘数据 |
| `POST /api/ai/xianzhi/hehun` | 合婚分析 |
| `GET /api/ai/xianzhi/cases` | 命例库列表 |
| `GET /api/ai/tarot/spreads` | 塔罗牌阵列表 |
| `GET /api/ai/health` | 健康检查 |

所有 WebSocket 使用 `_safe_ws_send` 包装，妥善处理客户端断连。

## 工具集

### 本地工具（12 个）

| 工具 | 用途 |
|------|------|
| `bazi_full` | 完整排盘（信息最全） |
| `bazi_chart` | 基础排盘 |
| `bazi_analysis` | 命局分析 |
| `bazi_dayun` | 大运查询 |
| `bazi_liunian` | 流年查询 |
| `bazi_liuyue` | 流月查询 |
| `bazi_liuri` | 流日查询 |
| `bazi_hehun` | 合婚分析 |
| `search_knowledge` | RAG 知识库检索 |
| `search_web` | 联网搜索（Serper.dev） |
| `do_terminate` | 任务终止 |

### MCP 工具

- 高德地图 MCP（地理编码、POI 搜索等）

## 多 Agent 协作架构

详见 [docs/multi_agent_architecture.md](docs/multi_agent_architecture.md)。

### 核心：Supervisor + Worker + Reviewer

```
Supervisor (XianzhiWorkflow)
    ├─ classify_question → 分派 Worker
    ├─ Worker 执行（专属断法 + 专属检索）
    ├─ Reviewer 三重校验（事实 + 古籍 + 合规）
    └─ Reflextion 回退修复
```

### 10 个专业 Worker

事业 / 财运 / 恋爱 / 婚姻 / 健康 / 学业 / 大运流年 / 术语理论 / 闲聊 / 综合

每个 Worker 带专属断法 prompt 和检索 query，专注单一领域。

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | 百炼 API Key | 必填 |
| `DASHSCOPE_MODEL` | 模型名 | `qwen-plus` |
| `DASHSCOPE_URL` | OpenAI 兼容端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `APP_PORT` | 服务端口 | `8123` |
| `CORS_ORIGINS` | CORS 允许源 | `http://localhost:5173,...` |
| `AGENT_MAX_STEPS` | ReAct 最大步数 | `5` |
| `MEMORY_STORE_TYPE` | 记忆存储 | `file` |
| `VECTOR_STORE_TYPE` | 向量库类型 | `chroma` |
| `SEARCH_API_KEY` | Serper.dev Key | 空 |
| `AMAP_MAPS_API_KEY` | 高德 MCP Key | 空 |
| `LANGSMITH_TRACING` | LangSmith 追踪 | `false` |

完整配置见 [.env.example](.env.example)。

## 可观测性

- **日志**：loguru，分级别输出（DEBUG/INFO/WARNING/ERROR）
- **链路追踪**：LangSmith（可选）
- **指标监控**：Prometheus（请求量、耗时、状态码）
- **架构日志**：`[Supervisor]` / `[workflow检索]` / `[Reviewer]` / `[Reflextion]` 完整链路

## 合规与安全

### 红线

- 不推断生死
- 不指导赌博投机
- 不宣扬符咒改运
- 不提供堕胎择时
- 涉及重病、牢狱等凶险信息，优先劝导寻求医院、律师等现实专业帮助

### Reviewer 合规校验

扫描死期/赌博/符咒/堕胎等红线关键词，命中即提示需人工审核。

### 安全中间件

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- CORS 白名单（生产环境应配置实际域名）

## 开发

### 测试多 Agent 架构

```powershell
.venv\Scripts\python.exe -c "
from app.agent.xianzhi_workflow import WORKERS, ReviewerWorker
print(f'Workers: {len(WORKERS)}')
reviewer = ReviewerWorker()
print(f'Compliance risks: {len(reviewer.COMPLIANCE_RISKS)}')
"
```

### 添加新 Worker

在 `app/agent/xianzhi_workflow.py` 的 `WORKERS` 注册表添加配置，并在 `DOMAIN_KEYWORDS` 和 `DOMAIN_RULE_QUERIES` 添加对应配置。详见 [docs/multi_agent_architecture.md](docs/multi_agent_architecture.md#扩展-worker)。

### 命理知识库扩展

在 `app/rag/knowledge_docs/` 添加 `.md` 文档，重启服务自动重新索引。

## 设计原则

1. **确定性优先**：命理事实是客观的（排盘结果确定），workflow 路径用 Python 代码直接检索而非 LLM 调工具
2. **专业深度 + 交叉校验**：单领域 Worker 更短更专业，Reviewer 用不同视角审视避免盲区
3. **小程序兼容**：所有聊天用 WebSocket（SSE 不支持），HTTPS + 备案域名
4. **用户体验**：不展示 ReAct 中间步骤，只输出最终回答；闲聊双重短路避免无谓工具调用
5. **数据准确**：关键 UI 元素（五鬼/生门/死门/星宿/胎神）从后端计算填充，不依赖 LLM 生成

## 许可

私有项目，未授权不得商用。
