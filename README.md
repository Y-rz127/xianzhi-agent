# 先知 · 八字命理分析预测智能体

> 基于多 Agent 协作架构的八字命理分析平台，融合传统命理学与现代 AI 智能体技术。

## 项目简介

先知是一个集八字排盘、命理分析、合婚分析、塔罗占卜、命主档案管理于一体的智能体平台。核心采用 **Supervisor + 专业 Worker + Reviewer** 三层架构，让命理分析具备专业深度与严谨性。

### 核心能力

- **八字排盘**：四柱、大运、流年、五行、十神、格局、用神、调候、神煞，全套排盘
- **命理问答**：基于 RAG 知识库的术语解释、古籍引用、专项断事
- **合婚分析**：双方八字合婚，五行匹配度评分
- **塔罗占卜**：78 张完整塔罗牌，单张/三张/关系牌阵，AI 流式解读
- **命主档案**：注册用户可保存多个命主档案，便捷复用排盘
- **命例收藏**：跨会话收藏命例，支持命例库浏览
- **PDF 报告**：命盘详情 PDF 下载、完整命理报告导出
- **用户反馈**：意见反馈通道 + 管理员后台

### 技术栈

| 层级 | 技术 |
|------|------|
| **大模型** | 阿里云百炼 DashScope（Qwen3，OpenAI 兼容模式） |
| **Agent 框架** | LangChain + LangGraph（可选） |
| **Web 框架** | FastAPI + WebSocket（小程序兼容） |
| **RAG** | PostgreSQL pgvector（可切 Chroma / Milvus）+ DashScope Embedding |
| **记忆持久化** | PostgreSQL（生产）/ File（本地兜底） |
| **数据库** | PostgreSQL（用户/档案/收藏/反馈） |
| **MCP** | 高德地图 MCP |
| **可观测性** | LangSmith + Prometheus |
| **前端** | Vue3 + UniApp（小程序） / Vite（Web） |
| **排盘引擎** | lunar-python |

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      前端（小程序 / Web）                      │
│  先知聊天 │ 合婚 │ 塔罗占卜 │ 命例库 │ 命主档案 │ 命盘详情    │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket / REST
┌──────────────────────────┴──────────────────────────────────┐
│                        FastAPI 服务层                         │
│  /api/ai/xianzhi │ /api/ai/tarot │ /api/ai/rag │ /api/auth  │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   ┌─────────┐      ┌─────────────┐    ┌───────────┐
   │  ReAct   │      │  workflow   │    │  独立 App │
   │ (无命盘) │      │ (有命盘)    │    │           │
   │          │      │ Supervisor  │    │ TarotApp  │
   │ LLM 自主 │      │ + Worker    │    │ RagChain  │
   │ 调工具   │      │ + Reviewer  │    │           │
   └─────────┘      └─────────────┘    └───────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
   ┌──────────────────────────────────────────────────────┐
   │  本地工具（11 个）│ MCP 工具（高德）│ RAG 知识库       │
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
- **断事**：事业/财运/婚恋/健康/学业/官非/六亲/性格
- **合婚**：双方八字匹配度评分
- **命例库**：历史命例展示与学习
- **PDF 报告**：命盘详情导出、完整命理报告

### 2. 塔罗占卜（紫金神秘主题）

- 78 张完整塔罗牌（22 大阿卡纳 + 56 小阿卡纳）
- 三种牌阵：每日一牌 / 过去现在未来 / 关系牌阵
- Fisher-Yates 洗牌算法，随机正逆位
- 翻牌动画（正反面分离设计）
- AI 流式解读（mystical tarot reader 人设）

### 3. 用户系统与档案

- **登录认证**：JWT Token，支持微信小程序登录与匿名访问
- **命主档案**：注册用户可保存多个命主档案（姓名、生辰、性别）
- **命例收藏**：跨会话收藏命例，便捷复用排盘
- **塔罗历史**：保存抽牌记录与解读结果
- **用户反馈**：意见反馈通道 + 管理员后台审核

### 4. RAG 命理知识库

知识库收录 34 份命理文档：

- **基础理论**：天干地支、五行生克、十神、用神、大运流年、纳音、神煞、排盘基础
- **断法体系**：事业财运、婚恋关系、合冲刑害、大运流年、格局、六亲、健康、学业、官非、性格、子女、贫富层次、男女命差异、流月流日
- **标准流程**：标准分析流程、术语白话对照、问答模板库
- **古籍**：渊海子平、子平真诠、穷通宝鉴、滴天髓、三命通会、神峰通考、盲派口诀
- **命例案例库**：历史命例

## 神煞排盘规则

神煞是八字命盘的重要辅助指标。本项目以主流《渊海子平》《三命通会》为查表依据，并对齐问真八字等主流排盘软件的输出。

### 查法（以日干或年干）

以下神煞同时查日干和年干（"以日、年干查四地支"）：

| 神煞 | 查表依据 |
|------|---------|
| **太极贵人** | 甲乙子午 / 丙丁卯酉 / 戊己辰戌丑未 / 庚辛寅亥 / 壬癸巳申 |
| **福星贵人** | 古诀"凡甲丙见寅子，乙癸见卯丑，戊申己未丁亥庚午辛巳壬辰" |
| **金舆** | 禄后二位：甲辰乙巳丙未丁申戊未己申庚戌辛亥壬丑癸寅 |
| **天乙贵人** | 日干查（甲戊庚丑未 / 乙己子申 / 丙丁亥酉 / 壬癸卯巳 / 辛午寅） |
| **文昌** | 日干查（甲巳乙午丙申丁酉戊申己酉庚亥辛子壬寅癸卯） |
| **禄神 / 羊刃** | 日干查临官位 / 帝旺位 |
| **学堂 / 词馆** | 日干查日支，仅落日柱 |

### 查法（以年支或日支）

以下神煞以年支或日支双向查表（三合局衍生）：

- **华盖**：三合局墓库（寅午戌→戌，巳酉丑→丑，申子辰→辰，亥卯未→未）
- **桃花**：三合局帝旺（寅午戌→卯，巳酉丑→午，申子辰→酉，亥卯未→子）
- **驿马**：三合局长生对冲
- **将星**：三合局帝旺
- **劫煞 / 灾煞 / 亡神**：三合局绝位 / 将星对冲 / 临官位
- **吊客 / 丧门 / 病符 / 天医**：岁后二辰 / 岁前二辰 / 岁后一辰 / 三合前库
- **红鸾 / 天喜**：桃花位 / 桃花对冲
- **孤辰 / 寡宿**：年支三合前位

### 日柱专属神煞

- **魁罡**：日柱为庚辰/壬辰/庚戌/戊戌
- **十恶大败**：日柱干支在十恶大败表（甲辰、乙巳、丙申、丁亥、戊戌、己丑、庚辰、辛巳、壬申、癸亥）
- **童子煞**：以时柱干支查表（民间主流查时柱）
- **飞刃**：羊刃对冲位出现在四柱（如壬日子为羊刃，午为飞刃）

### 空亡

以 lunar-python 计算的旬空为准，只标注实际落住四柱的旬空位。

### 前端展示

- **每柱内独立显示**：神煞按所属柱位垂直排列，柱内同名神煞去重
- **命宫 / 身宫**：独立字段，显示在"四柱命盘"标题右侧
- **点击查看寓意**：点击神煞标签弹出寓意说明
  - Web：浮层卡片，点击遮罩或"关闭"按钮关闭
  - 小程序：调用 `uni.showModal` 原生弹窗

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
│   │   ├── xianzhi.py            # 先知聊天 WS / SSE / REST
│   │   ├── tarot.py              # 塔罗 WS
│   │   ├── rag.py                # 问答 WS
│   │   ├── chart_cases.py        # 命例库 REST
│   │   ├── auth.py               # 用户登录认证（JWT）
│   │   ├── me.py                 # 当前用户信息
│   │   ├── profiles.py           # 命主档案 REST
│   │   ├── favorites.py          # 命例收藏 REST
│   │   ├── feedback.py           # 用户反馈 REST
│   │   ├── tarot_records.py      # 塔罗历史记录 REST
│   │   ├── admin_users.py        # 管理员用户管理 REST
│   │   ├── deps.py               # 依赖注入（用户认证等）
│   │   ├── common.py             # 通用工具
│   │   ├── observability.py      # 可观测性
│   │   ├── tools.py              # 工具接口
│   │   └── routes.py             # 路由聚合
│   ├── domain/                  # 领域逻辑
│   │   └── bazi_engine.py        # 八字排盘引擎（神煞查表）
│   ├── tools/                   # 工具集
│   │   ├── bazi.py               # 八字工具（8个）
│   │   ├── rag_search.py         # 知识库检索工具
│   │   ├── web_search.py         # 联网搜索（Serper.dev）
│   │   ├── terminate.py          # 终止工具
│   │   ├── mcp_client.py         # MCP 客户端（高德）
│   │   ├── pdf_report.py         # PDF 报告生成
│   │   ├── report_generator.py   # 报告生成器
│   │   └── cache.py              # 排盘缓存
│   ├── rag/                     # RAG 知识库
│   │   ├── vector_store.py       # 向量库封装
│   │   ├── rag_chain.py          # RAG 链
│   │   ├── retrieval.py          # 检索器
│   │   └── knowledge_docs/       # 命理文档（34份）
│   ├── memory/                  # 记忆系统
│   │   ├── chat_memory.py        # 对话记忆
│   │   └── postgres_memory.py    # PostgreSQL 持久化
│   ├── db/                      # PostgreSQL 数据访问层
│   ├── evaluation/              # 离线评估
│   │   └── xianzhi_eval.py       # 答案质量检查
│   ├── tarot_app.py             # 塔罗 App
│   ├── observability.py         # LangSmith 可观测性
│   ├── security.py              # 安全中间件
│   ├── utils/                   # 通用工具
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

可选：Serper.dev（联网搜索）、高德地图 MCP、LangSmith 可观测性、JWT 密钥。

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
| `/api/ai/tarot/ws` | 塔罗占卜解读 |
| `/api/ai/rag/ws` | 命理理论问答 |

### REST

| 端点 | 用途 |
|------|------|
| `GET /api/ai/xianzhi/chart` | 结构化命盘数据 |
| `POST /api/ai/xianzhi/hehun` | 合婚分析 |
| `GET /api/ai/xianzhi/chart_cases` | 命例库列表 |
| `GET /api/ai/tarot/spreads` | 塔罗牌阵列表 |
| `POST /api/auth/login` | 用户登录 |
| `GET /api/me` | 当前用户信息 |
| `GET/POST /api/profiles` | 命主档案 |
| `GET/POST /api/favorites` | 命例收藏 |
| `POST /api/feedback` | 用户反馈 |
| `GET /api/ai/admin/users` | 用户管理（管理员） |
| `GET /api/ai/health` | 健康检查 |

所有 WebSocket 使用 `_safe_ws_send` 包装，妥善处理客户端断连。

## 工具集

### 本地工具（11 个）

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

### 18 个专业 Worker

事业 / 财运 / 恋爱 / 婚姻 / 健康 / 学业 / 社交 / 六亲 / 大运流年 / 术语理论 / 闲聊 / 性格 / 迁移 / 起名 / 择吉 / 合婚 / 子女 / 综合

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
| `MEMORY_STORE_TYPE` | 记忆存储 | `postgres`（本地兜底 `file`） |
| `VECTOR_STORE_TYPE` | 向量库类型 | `postgres`（pgvector；本地兜底 `chroma`） |
| `JWT_SECRET` | JWT 签名密钥 | 随机生成 |
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

### 测试神煞排盘

```powershell
.venv\Scripts\python.exe -c "
from app.domain.bazi_engine import build_bazi_chart, _compute_shensha
chart = build_bazi_chart('2004-06-22 08:00', '男', sect=2, yun_sect=1)
for p in chart.pillars:
    print(f'{p.name}: {p.ganzhi}')
for s in _compute_shensha(chart.pillars):
    print(f'  {s[\"name\"]}: {s[\"description\"]}')
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
5. **数据准确**：关键 UI 元素（神煞查表、空亡、命宫身宫）从后端计算填充，不依赖 LLM 生成
6. **每柱独立显示**：神煞按柱位垂直排列，柱内同名去重，命宫身宫独立显示在标题右侧

## 许可

私有项目，未授权不得商用。
