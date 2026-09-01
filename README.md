# 先知 · 八字命理分析预测智能体

> 基于多 Agent 协作架构的八字命理分析平台，融合传统命理学与现代 AI 智能体技术。

## 项目简介

先知是一个集八字排盘、命理分析、合婚分析、塔罗占卜、六爻起卦、每日黄历、命主档案管理于一体的智能体平台。核心采用 **Supervisor + 专业 Worker + Reviewer** 三层架构，让命理分析具备专业深度与严谨性。

### 核心能力

- **八字排盘**：四柱、大运、流年、五行、十神、格局、用神、调候、神煞，全套排盘
- **命理问答**：基于 RAG 知识库的术语解释、古籍引用、专项断事
- **合婚分析**：双方八字合婚，五行匹配度评分
- **塔罗占卜**：78 张完整塔罗牌，单张/三张/关系牌阵，AI 流式解读
- **六爻起卦**：铜钱/数字/时间三式起卦，本卦变卦动爻，AI 深度解读
- **每日黄历**：宜忌/八方位/时辰吉凶/择吉/月视图，纯算法确定性计算，对齐主流老黄历（Web + 小程序双端）
- **紫微斗数**：Python 自研排盘引擎（iztro 黄金快照逐宫逐曜钉死），十二宫 4×4 命盘 + 点宫详情 + AI 简批，接入仙芝对话（小程序）
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
   │  本地工具（16 个）│ MCP 工具（高德）│ RAG 知识库       │
   │  bazi_* │ huangli_* │ search_knowledge │ search_web   │
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

知识库收录 40 份命理文档：

- **基础理论**：天干地支、五行生克、十神、用神、大运流年、纳音、神煞、排盘基础
- **断法体系**：事业工作、财运收入、婚恋关系、合冲刑害、大运流年、格局、六亲、健康、学业、官非、性格、子女、贫富层次、男女命差异、流月流日、社交人际、方位迁移、择吉择日、合婚配对、起名改名
- **标准流程**：标准分析流程、术语白话对照、问答模板库
- **古籍**：渊海子平、子平真诠、穷通宝鉴、滴天髓、三命通会、神峰通考、盲派口诀
- **命例案例库**：历史命例

### 检索分层说明

知识检索为「Layer 1 相似度召回 + 关键词重叠重排 + Layer 2 多 query 编排」结构；两条路径共用统一检索入口 `app.rag.retrieval.retrieve_for_context`（top-1 chunk + 跨 query 去重，去重键 `(source, content[:120])`，单 chunk 截断与条数上限由参数控制），差异仅在 query 构造：

- **ReAct 工具路径**（`search_knowledge`）：`expand_knowledge_queries` 把每条问题扩展为最多 4 条 query（原文 + 理论术语精准 query + 领域规则 query），检索后最多取 4 条文档。
- **workflow 路径**（`_retrieve_rules`）：query 来自 LLM 拆解 / 理论路径 / 断事路径（理论 / 专项 query 均注入用户原句以提升个性化召回），单 chunk 受 `_MAX_TEXT_PER_QUERY` 截断。

Layer 1（`KnowledgeBase.search` → `_search_reranked`）为后端无关的两段式检索：

1. 向量召回 `similarity_search_with_score` 取 `fetch_k = rag_k * 3` 候选；
2. （仅 Chroma）按 `rag_distance_threshold` 距离阈值过滤低相关片段；
3. 关键词字符 2-gram（Jaccard）重叠度降序**重排**，取 `rag_k` 条。

用关键词重叠度而非后端 score 重排，规避 Chroma（L2 距离越小越相关）与 pgvector / Milvus（余弦相似度越大越相关）的 score 方向不一致；不支持 score 检索的后端自动回退 MMR（`rag_mmr_lambda`）。完整对比见 [docs/multi_agent_architecture.md](docs/multi_agent_architecture.md)。

### 5. 每日黄历（Web / 小程序）

基于 lunar-python 纯算法的确定性黄历（`app/domain/huangli_calc.py` 领域层 + `app/sub_app/huangli/` 子应用），不依赖 LLM 与数据库：

- **当日黄历**：宜忌、冲煞、彭祖百忌、胎神占方、纳音五行、吉神宜趋/凶煞宜忌、八吉神方位（财神/喜神/福神/阳贵/阴贵/五鬼/生门/死门）、值神黄黑道、十二建星、九星、二十八宿、节日节气（含中元/上巳等 24 民俗节）。方位流派对齐主流老黄历 App（17 日 × 8 字段回测 134/136，唯一分歧壬申生门死门已被手机自身庚午/辛未数据证伪为 App 错组）：财神按日干民历派（`_CAI_MINLI`）、五鬼按日干（`_WUGUI_GAN`，十干全实测）、阳贵/阴贵/生门/死门按六十甲子逐日表（`_DAY_GOD_POS`，渊海子平系，三处源表讹字按"对冲宫+三日组"双不变式校正，丙日阳贵覆写正南可回退）
- **十二时辰吉凶**：每时辰值神/吉凶/宜忌（子时合并为一条，取当日早子段，主流黄历口径）
- **择吉**：按宜忌事项词表（139 项）筛选区间吉日，天德/月德/天赦/四相加星排序，可避冲生肖
- **月视图概览**：整月简报（农历、宜忌摘要、节日/节气/天赦角标）
- **Agent 工具**：`huangli_today` / `huangli_zeji` 挂载 ReAct 路径，可回答"今天适合开业吗""帮我挑个下月搬家吉日"
- **双端页面**：Web `/huangli`（侧栏导航）；小程序 `pages/huangli`（聊天抽屉快捷入口「黄历」）

### 6. 六爻起卦

- 铜钱 / 数字 / 时间三种起卦方式，纯算法可复现（`app/sub_app/liuyao/`）
- 本卦 / 变卦 / 动爻完整排布，六十四卦 + 八卦上下卦标注
- AI 深度解读（`POST /api/ai/liuyao/interpret`）
- Web `/liuyao` 页面（摇卦动画 + 逐爻揭示），小程序同步支持

### 7. 紫微斗数排盘

基于 Python 自研排盘引擎的确定性命盘（`app/domain/ziwei/` 领域层 + `app/sub_app/ziwei/` 子应用），零运行时依赖、不碰数据库与 RAG：

- **引擎正确性**：安星法（《紫微斗数全书》通行派）、十四主星庙旺利陷、六吉六煞、三十余杂曜、生年四化、大限/小限、身宫、五行局全部纯函数实现；以开源 iztro 2.6.0（MIT）为黄金 oracle，`scripts/gen_ziwei_oracle.js` 一次性生成 45 组生辰快照（五行局 5 种 × 十二时辰 × 男女 × 闰月 × 晚子时 × 年分界全覆盖），`tests/test_ziwei.py` 逐宫逐曜断言钉死流派与规则。
- **流派与规则**：四化取三合通用表（`MUTAGEN_BY_STEM` 可替换常量）；年分界取正月初一（`getYearInGanZhi`）；闰月上半归本月、下半归下月；晚子时（23:00–24:00）起紫微归次日。
- **接口**：`GET /api/ai/ziwei/chart`（排盘，阳历/农历 + 闰月）、`POST /api/ai/ziwei/interpret`（AI 简批，后端重排盘不信任前端传盘）。
- **Agent 工具**：`app/tools/ziwei.py` 的 `ziwei_chart` 已接入仙芝对话，可直接排盘并衔接解读。
- **小程序**：`pages/ziwei`（黛蓝紫 accent `#5B6FC8`，暗夜星空 + 流星），经典 4×4 宫格命盘（`grid repeat(4,1fr)`）+ 中央信息区 + 四化角标 + 点宫详情弹层 + AI 简批；聊天抽屉快捷入口「紫微」。
- 定位为传统民俗文化参考，文案带免责口径。

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
├── backend/                     # 后端（Python FastAPI）
│   ├── main.py                  # 应用入口（FastAPI + lifespan：模型/思考路由/后台初始化/缓存预热）
│   ├── app/
│   │   ├── agent/               # 智能体核心
│   │   │   ├── xianzhi.py       # 先知主类（ReAct + workflow 分流 + 闲聊短路）
│   │   │   ├── xianzhi_langgraph.py # LangGraph 可选封装
│   │   │   ├── birth_parse.py   # 出生信息提取
│   │   │   ├── prompts.py       # Prompt 中枢（断法/六爻解读等）
│   │   │   ├── core/            # base_agent / react_agent / tool_call_agent
│   │   │   └── workflow/        # Supervisor + Worker + Reviewer
│   │   │                        #   （xianzhi_workflow + models/retrieval/workers/messages/support）
│   │   ├── api/                 # REST/WebSocket 接口
│   │   │   ├── xianzhi.py       # 先知聊天 WS / SSE / REST
│   │   │   ├── rag.py           # 问答 WS
│   │   │   ├── auth.py / me.py  # 登录认证（JWT）/ 当前用户
│   │   │   ├── cases.py / profiles.py / favorites.py      # 命例库 / 命主档案 / 收藏
│   │   │   ├── tarot_records.py / feedback.py             # 塔罗记录 / 反馈
│   │   │   ├── admin_users.py / admin_accounts.py         # 管理员
│   │   │   ├── asr.py           # 语音转写
│   │   │   └── routes.py / deps.py / common.py / context.py  # 聚合 / 依赖注入 / 通用 / 应用上下文
│   │   ├── core/                # config / logger（loguru）/ security（鉴权限流）
│   │   │                        #   observability（LangSmith）/ thinking_router（思考模式路由）
│   │   ├── domain/              # 领域纯计算（不依赖 LLM 与数据库）
│   │   │   ├── bazi_engine.py   # 八字排盘引擎（lunar-python + 神煞查表）
│   │   │   ├── chart_builder / chart_format / analysis_calc / shensha_calc / tables
│   │   │   ├── time_parse.py    # 农历/节日/时辰智能解析
│   │   │   ├── huangli_calc.py  # 黄历领域层（宜忌/八方位/时辰/择吉/月简报，对齐主流老黄历）
│   │   │   └── ziwei/           # 紫微斗数领域层（tables/engine/models，纯函数排盘，iztro 黄金快照钉死）
│   │   ├── sub_app/             # 玩法子应用（App 核心 + routes）
│   │   │   ├── tarot/           # 塔罗（TarotApp，WS 流式解读）
│   │   │   ├── hehun/           # 合婚
│   │   │   ├── liuyao/          # 六爻（纯算法起卦 + AI 解读）
│   │   │   ├── huangli/         # 黄历（day/range/zeji/items 四接口）
│   │   │   └── ziwei/           # 紫微斗数（chart 排盘 + interpret AI 简批）
│   │   ├── tools/               # 16 个本地工具（bazi/huangli/rag_search/web_search/terminate）
│   │   │   ├── mcp_client.py    # MCP 客户端（高德）
│   │   │   ├── pdf_report.py / report_generator.py        # PDF 报告
│   │   │   └── cache.py / text_clean.py / fonts/          # 排盘缓存 / 文本清洗 / 字体
│   │   ├── rag/                 # RAG 知识库（vector_store/retrieval/relevance/embeddings/fingerprint/case_store）
│   │   │   └── knowledge_docs/  # 命理文档（40 份）
│   │   ├── memory/              # 对话记忆（chat_memory / postgres_memory / summarizer）
│   │   ├── db/                  # PostgreSQL 数据访问层（pool/repository/users/profiles/chart_store…）
│   │   └── evaluation/          # 离线评估（xianzhi_eval）
│   ├── tests/                   # pytest 套件（黄历含 17 日老黄历 App 回测 + 表结构不变式）
│   ├── scripts/                 # 工具脚本（locust 压测 / iztro oracle 快照生成）
│   ├── data/ / logs/            # 运行时数据与日志（不入库）
│   ├── Dockerfile / .dockerignore / .env.example
│   ├── start.ps1 / stop.ps1     # 一键启停（复用仓库根 .venv，工作目录在 backend/）
│   └── pyproject.toml / requirements.txt / requirements.lock / .coveragerc
├── frontend/                    # 前端
│   ├── web/                     # Web 前端（Vue3 + Vite）
│   │   └── src/views/           # 先知/合婚/塔罗/六爻/黄历/命例库/管理后台等
│   └── uniapp/                  # 小程序前端（UniApp，聊天抽屉含合婚/塔罗/六爻/黄历/紫微入口）
├── shared/                      # Web 与小程序共享 API 层（数据模型/端点常量/解析器）
├── docs/                        # 多 Agent 架构 / code review / 持续学习路线图
├── 学习资料/                     # 智能体开发学习笔记
└── docker-compose.yml           # 编排（api=backend/ 镜像，frontend=frontend/web/ 镜像）
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（前端）
- 阿里云百炼 API Key

### 1. 配置环境变量

```powershell
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，至少配置：

```env
DASHSCOPE_API_KEY=your-api-key
DASHSCOPE_MODEL=qwen3.7-max-2026-06-08
APP_PORT=8123
```

可选：Serper.dev（联网搜索）、高德地图 MCP、LangSmith 可观测性、JWT 密钥。

### 2. 安装依赖

```powershell
# 后端（venv 建在仓库根）
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt

# 前端（Web）
cd frontend\web
npm install

# 前端（小程序）
cd frontend\uniapp
npm install
```

### 3. 启动服务

```powershell
# 后端（工作目录须在 backend/，data/logs 相对路径基于它）
cd backend
..\.venv\Scripts\python.exe main.py
# 或用启动脚本（自动处理工作目录与端口清理）
.\start.ps1

# 前端（Web）
cd frontend\web
npm run dev

# 前端（小程序）
cd frontend\uniapp
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
| `GET /api/ai/xianzhi/cases` | 命例库列表（Web 端新建八字命例） |
| `GET /api/ai/tarot/spreads` | 塔罗牌阵列表 |
| `POST /api/ai/liuyao/cast` | 六爻起卦（coins/numbers/time） |
| `POST /api/ai/liuyao/interpret` | 六爻 AI 解读 |
| `GET /api/ai/huangli/day` | 当日完整黄历（date 可选，1900-2100） |
| `GET /api/ai/huangli/range` | 月视图简报（区间上限 31 天） |
| `GET /api/ai/huangli/zeji` | 择吉筛选（区间上限 60 天，可避冲生肖） |
| `GET /api/ai/huangli/items` | 宜忌事项词表 |
| `POST /api/auth/login` | 用户登录 |
| `GET /api/me` | 当前用户信息 |
| `GET/POST /api/profiles` | 命主档案 |
| `GET/POST /api/favorites` | 命例收藏 |
| `POST /api/feedback` | 用户反馈 |
| `GET /api/ai/admin/users` | 用户管理（管理员） |
| `GET /api/ai/health` | 健康检查 |

所有 WebSocket 使用 `_safe_ws_send` 包装，妥善处理客户端断连。

## 工具集

### 本地工具（16 个）

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
| `bazi_infer_dates` | 出生日期反推（多候选） |
| `lunar_to_solar` | 农历/节日/时辰转公历 |
| `huangli_today` | 每日黄历查询（含八方位/时辰吉凶） |
| `huangli_zeji` | 择吉吉日筛选 |
| `search_knowledge` | RAG 知识库检索 |
| `search_web` | 联网搜索（Serper.dev） |
| `scrape_web_page` | 网页正文抓取 |
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
| `RELOAD` | 代码热重载（仅本地开发，改 .py 即重启，强制单进程） | `false` |
| `CORS_ORIGINS` | CORS 允许源 | `http://localhost:5173,...` |
| `AGENT_MAX_STEPS` | ReAct 最大步数 | `8` |
| `MEMORY_STORE_TYPE` | 记忆存储 | `postgres`（本地兜底 `file`） |
| `VECTOR_STORE_TYPE` | 向量库类型 | `postgres`（pgvector；不可用时自动回退 `chroma` 并记录实际类型，避免每次启动重试 / 重建） |
| `RAG_K` | 每 query 最终召回条数 | `2` |
| `RAG_MMR_LAMBDA` | 回退 MMR 相关性权重（0~1） | `0.7`（仅后端不支持 score 检索时生效；主路径按关键词重叠重排，不依赖此值） |
| `RAG_DISTANCE_THRESHOLD` | 检索距离阈值（仅 Chroma） | `None`（不过滤；需按 embedding 距离分布实验标定） |
| `RAG_SEARCH_CACHE_TTL` | 检索结果缓存 TTL（秒） | `60`（0 表示不缓存） |
| `JWT_SECRET` | JWT 签名密钥 | 随机生成 |
| `SEARCH_API_KEY` | Serper.dev Key | 空 |
| `AMAP_MAPS_API_KEY` | 高德 MCP Key | 空 |
| `LANGSMITH_TRACING` | LangSmith 追踪 | `false` |

完整配置见 [backend/.env.example](backend/.env.example)。

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
# 在 backend/ 目录下执行（导入 app.* 需以 backend 为工作目录）
cd backend
..\.venv\Scripts\python.exe -c "
from app.agent.workflow.xianzhi_workflow import WORKERS, ReviewerWorker
print(f'Workers: {len(WORKERS)}')
reviewer = ReviewerWorker()
print(f'Compliance risks: {len(reviewer.COMPLIANCE_RISKS)}')
"
```

### 测试神煞排盘

```powershell
# 在 backend/ 目录下执行
cd backend
..\.venv\Scripts\python.exe -c "
from app.domain.bazi_engine import build_bazi_chart, _compute_shensha
chart = build_bazi_chart('2004-06-22 08:00', '男', sect=2, yun_sect=1)
for p in chart.pillars:
    print(f'{p.name}: {p.ganzhi}')
for s in _compute_shensha(chart.pillars):
    print(f'  {s[\"name\"]}: {s[\"description\"]}')
"
```

### 添加新 Worker

在 `app/agent/workflow/xianzhi_workflow.py` 的 `WORKERS` 注册表添加配置，并在 `DOMAIN_KEYWORDS` 和 `DOMAIN_RULE_QUERIES` 添加对应配置。详见 [docs/multi_agent_architecture.md](docs/multi_agent_architecture.md#扩展-worker)。

### 命理知识库扩展

在 `app/rag/knowledge_docs/` 添加 `.md` 文档，重启服务自动重新索引。文档指纹 = 源文件内容哈希 + embedding 模型 + 向量库类型 + 切分参数（`CHUNK_SIZE=350` / `CHUNK_OVERLAP=70`），任一项变化即触发全量重建，确保新旧 chunk 不混用。

## 设计原则

1. **确定性优先**：命理事实是客观的（排盘结果确定），workflow 路径用 Python 代码直接检索而非 LLM 调工具
2. **专业深度 + 交叉校验**：单领域 Worker 更短更专业，Reviewer 用不同视角审视避免盲区
3. **小程序兼容**：所有聊天用 WebSocket（SSE 不支持），HTTPS + 备案域名
4. **用户体验**：不展示 ReAct 中间步骤，只输出最终回答；闲聊双重短路避免无谓工具调用
5. **数据准确**：关键 UI 元素（神煞查表、空亡、命宫身宫、黄历八方位）从后端计算填充，不依赖 LLM 生成
6. **每柱独立显示**：神煞按柱位垂直排列，柱内同名去重，命宫身宫独立显示在标题右侧

## 许可

私有项目，未授权不得商用。