# 部署指南：CloudBase 云托管 + 腾讯云 PostgreSQL

> 适用场景：把后端 FastAPI 跑在腾讯云 CloudBase 云托管（容器），数据库用腾讯云 PostgreSQL，
> 微信小程序 / H5 在任意网络下连接。**自己开发调试、不上体验版/正式版时无需 ICP 备案**。

---

## 1. 架构概览

| 组件 | 部署位置 | 说明 |
|------|----------|------|
| 后端 FastAPI | CloudBase 云托管（容器，跑现有 `Dockerfile`） | 平台注入 `PORT`，代码已自动读取 |
| 数据库 | 腾讯云 PostgreSQL（需支持 pgvector） | 存对话记忆 + RAG 向量 |
| Redis | 腾讯云 Redis（或自建，需与云托管同 VPC） | 跨副本限流等共享状态；未配置时降级为进程内存（单副本可用） |
| 前端 | 微信小程序（开发版 + 真机调试）或 H5 网页 | 运行时填云托管域名即可 |

---

## 2. 前置准备

- 腾讯云账号 + 开通 **CloudBase（云开发）**
- 腾讯云 **PostgreSQL** 实例（选支持 `pgvector` 扩展的版本；以控制台实际为准）
- 微信公众平台账号（仅小程序需要）
- （H5 公网访问需要）一个已 ICP 备案的域名；**开发调试可免**

---

## 3. 数据库准备（腾讯云 PostgreSQL）

1. 创建实例，记下 **地址、端口、用户名、密码、数据库名**（如 `xianzhi`）。
2. 连接后执行（腾讯云默认**未装** pgvector，必须手动开启）：
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. 连接串模板（**腾讯云 PG 强制 SSL，必须带 `sslmode=require`**）：
   ```
   postgresql://用户名:密码@地址:5432/xianzhi?sslmode=require
   ```
   填到环境变量 `POSTGRES_CONNECTION_STRING`。
4. 同时设 `VECTOR_STORE_TYPE=postgres` 与 `MEMORY_STORE_TYPE=postgres`（见 `.env.example`）。

### 3.5 表结构迁移（alembic，首次部署必做一次性标记）

表结构变更统一走 `backend/migrations/`（alembic），应用内建表逻辑只作兜底。

- **全新空库**：部署前在 backend 目录执行
  `alembic upgrade head`（自动建全部业务表 + CREATE EXTENSION vector）
- **已有的存量库**（表已是当前结构）：执行一次 `alembic stamp head` 打版本标记，
  后续发布时 `alembic upgrade head` 增量升级；不 stamp 会导致下次 upgrade 报“表已存在”
- 连接串复用 `POSTGRES_CONNECTION_STRING`，运行前先设好该环境变量；
  `langchain_pg_*`（向量/记忆库表）不在迁移内，由对应库运行时自建

---

## 4. 后端部署到 CloudBase 云托管

### 4.1 准备构建产物

仓库已含 `backend/Dockerfile` 与 `backend/.dockerignore`（已排除 `tests/`、`data/`、`logs/`、`.env`、
`scripts/node_modules/` 等，**镜像不会泄露密钥、也不会把多余代码打进去**）。

CloudBase 云托管支持两种方式：
- **关联代码仓库**（推荐）：控制台新建服务 → 关联 GitHub 仓库 → 指定分支 → 自动检测 `Dockerfile` 构建。
  注意 Dockerfile 位于 `backend/` 子目录，需把云托管的**构建根目录/工作目录设为 `backend`**（或选择该目录触发构建）。
- **上传本地代码**：在 `backend/` 目录打包（排除 `.env`、`node_modules`）后上传。

### 4.2 服务关键配置

| 配置项 | 值 / 说明 |
|--------|-----------|
| 监听端口 | 平台注入 `PORT`（默认 80），`main.py` 已优先读取，无需改代码 |
| 健康检查路径 | 存活 `/api/health/live`；就绪 `/api/health/ready`（兼容旧 `/api/health`） |
| 环境变量 | 见 `.env.example` 全部项；重点：`POSTGRES_CONNECTION_STRING`、`DASHSCOPE_API_KEY`、`VECTOR_STORE_TYPE=postgres`、`MEMORY_STORE_TYPE=postgres`、`CORS_ORIGINS`、`REDIS_URL`、`TRUST_PROXY_HEADERS=true`、`LLM_MAX_CONCURRENCY`、`ADMIN_SESSION_SECRET`（管理后台令牌签名密钥，多副本必须一致） |
| 内存 / 超时 | 建议内存 ≥ 1GB、请求超时 ≥ 60s（LLM 调用较慢） |

> 改动点：`main.py` 的 `uvicorn` 启动已改为优先读 `PORT`；`Dockerfile` 的 `EXPOSE 80`；
> 新增 `.dockerignore` 防止密钥/前端代码进入镜像。本地与云端双兼容。

### 4.3 生产容量：副本模型与关键约束

| 项 | 说明 |
|----|------|
| 运行形态 | **单容器单进程（WORKERS=1）+ 水平副本**。不要在同一容器开多 worker：限流/会话锁已 Redis 化没问题，但八字缓存等进程内状态按 worker 数放大、不如副本隔离干净 |
| 副本数起步 | 2 副本（滚动发布不断流）；聊天链路单副本承载约 5~7 请求/分钟（40~70s/请求，压测基线数据），扩缩触发建议看 CPU + 在飞请求数 |
| LLM 背压 | `LLM_MAX_CONCURRENCY` 是全副本共享配额按**每副本**生效，若上游 DashScope 配额是全局的，多副本时要按 配额/副本数 调小该值 |
| 报告任务 | 后台队列模型：提交落 PG（`report_tasks` 表）→ Redis 队列 → 各副本 worker 消费。**Redis 是必配项**（未配 Redis 提交直接 503）；`REPORT_TASK_WORKERS` 控制每副本消费并发，PDF 渲染 CPU 密集不要调太大 |
| 长连接 | 聊天 SSE/WS 单请求可达 2~5 分钟：网关/CDN 的回源与读超时必须 ≥ 300s，且关闭对 /api/ai/xianzhi 路径的响应缓冲；健康检查与长连接路径要分开限流 |
| 探针 | 存活/就绪统一用 `GET /api/health`（返回 DB/RAG/agent 池状态，启动期间后台初始化不阻塞端口监听）；扩缩容前先确认 `rag_ready=true` |

### 4.4 数据库连接治理（PgBouncer）

应用内 PG 连接池上限 `PG_POOL_MAX_SIZE`（默认 20）。多副本时总连接 = 副本数 × 池上限，
会顶到腾讯云 PG 的 `max_connections`（默认几百）。两个选择：

1. **（推荐）前置 PgBouncer**：应用 `POSTGRES_CONNECTION_STRING` 指向 PgBouncer（默认 5432 换成
   PgBouncer 端口，如 6432），PgBouncer 与 PG 之间用少量连接复用；应用端 `PG_POOL_MAX_SIZE`
   可保持 20 不变。
2. **直连调参**：算好 副本数 × `PG_POOL_MAX_SIZE` ≤ 实例 `max_connections` - 预留（RAG/migrations/后台任务占用），
   按需调小 `PG_POOL_MAX_SIZE`；连接借出超时由 `PG_POOL_TIMEOUT`（默认 10s）兜底。

> 报告任务的产物（PDF 字节）持久化在 PG `report_tasks.payload`，单条几百 KB 量级，
> 低频写入无压力；7 天后随任务清理。

---

## 5. 前端连接

### 5.1 微信小程序（免备案，开发版 + 真机调试）

1. 微信开发者工具 → 详情 → 本地设置 → 勾选 **「不校验合法域名、web-view、TLS 版本以及 HTTPS 证书」**。
2. 小程序内「设置」页把 API 地址改为：
   ```
   https://你的云托管默认域名/api
   ```
   （云托管会分配 `*.apigw.tencentcs.com` 之类的 HTTPS 域名，直接用即可）
3. 用「真机调试」或「预览」扫码，即可在任意网络下使用，**无需 ICP 备案**。

### 5.2 H5 网页

- 构建：`VITE_API_BASE=https://你的云托管域名/api npm run build`（`frontend/web` 目录）。
- 产物 `frontend/web/dist` 托管到 CloudBase 静态网站 / 任意静态服务器。
- 若用自有域名，需 ICP 备案并把域名加入 `CORS_ORIGINS`。

---

## 6. 验证

- 浏览器/终端访问 `https://你的云托管域名/api/health` 应返回健康状态。
- 小程序设置正确后，发一条消息验证端到端连通。

---

## 7. 注意事项

- **pgvector**：腾讯云 PG 需手动 `CREATE EXTENSION vector`，否则启动报错。
- **SSL**：腾讯云 PG 强制 `sslmode=require`，连接串务必带该参数。
- **Redis（多副本部署必配）**：单副本可不配（限流自动降级为进程内存）。多副本时必须配
  `REDIS_URL`（腾讯云 Redis 需与云托管同 VPC），否则限流上限按副本数线性放宽、形同虚设。
- **TRUST_PROXY_HEADERS**：经云托管网关/CDN 访问时设为 `true`，限流才按真实客户端 IP 统计
  （云托管容器默认仅能经平台网关访问，不存在头部伪造风险）。
- **LLM 背压**：`LLM_MAX_CONCURRENCY` 是全模型共享的并发上限，按 DashScope 配额 ≤80% 取值；
  排队超时或上游持续故障时接口返回「繁忙」提示而不是堆积重试。
- **鉴权**：`API_KEYS` 为空时后端不校验 Key（本地默认）；云端自己用也建议设一个 Key，避免被扫。
- **CORS**：`CORS_ORIGINS` 需包含前端域名，否则浏览器请求被拦；小程序 `wx.request` 不受 CORS 限制。
- **备案**：仅「自己开发调试 / 真机调试」使用时，微信小程序勾选不校验合法域名即可，**无需备案**；
  若要发布体验版/正式版或使用自有域名 H5，则需 ICP 备案。
- **密钥**：`.env` 已在 `.gitignore` 中，切勿提交真实密钥；云端请在平台环境变量面板配置。

## 8. 灰度发布与回滚 Runbook

> 目标：新版本先承接少量流量，指标不劣化再放量；异常时切回上一版本即可恢复，不改库、不重建镜像。
> 版本标识：部署时设置 `APP_VERSION=<git sha 或 tag>`，`GET /api/health/live` 直接返回该版本。

### 8.1 发布前闸门（Release Gate）

| 检查 | 通过标准 |
|------|----------|
| CI | unit job（Ruff + 单测/安全/混沌）全绿；改到集成链路的发布手动跑一次 integration job |
| 版本 | `APP_VERSION` 已设为本次 git sha/tag；上一版本的镜像/版本仍可部署 |
| 数据库迁移 | 只做向后兼容的增量变更；发布前做 PG 快照，并在新版本部署前执行 `alembic upgrade head`（旧代码必须能在新表结构上运行一个发布窗口） |
| 环境变量 | 与 `.env.example` 做差集，新增项已在平台配置；`ADMIN_SESSION_SECRET` 多副本必须一致 |
| 容量 | Redis 已配置；`副本数 × PG_POOL_MAX_SIZE` 不超过实例上限；`LLM_MAX_CONCURRENCY` 按全局配额/副本数调整 |
| 基线 | 记录 `/api/health/ready`（version / rag_ready / 队列深度）与 `/api/ai/metrics`（管理员令牌）当前值 |
| 回滚预案 | 明确触发阈值、执行人、沟通群；确认平台回滚只切流量、不需要动数据库 |

### 8.2 灰度步骤（0% → 5% → 25% → 50% → 100%）

1. **空跑部署**：部署新版本并保持 0% 流量（或独立灰度服务）。确认 `/api/health/live` 返回 200 且 `version` 是新版本，`/api/health/ready` 三个依赖均 ok。
2. **冒烟（直连灰度实例/域名）**：
   - `GET /api/health/live`、`GET /api/health/ready`
   - `GET /api/ai/xianzhi/chart?birth_time=1990-05-20%2014:30&gender=男` 返回 200 且有四柱
   - 发一轮 SSE 聊天（带 `client_msg_id`）：收到 `chart_context` / `progress`，最后 `[DONE]`，无 `event: error`
   - 提交一份报告任务并轮询到 done（付费接口需管理员或用户 token）
   - 管理后台登录成功，`/api/ai/metrics` 可读
3. **按阶梯放量**，每档观察后再进入下一档：

| 档位 | 最短观察 | 通过条件 |
|------|----------|----------|
| 5% | 10 分钟 | 5xx ≤ 1%，聊天成功率 ≥ 99%，无新增 ERROR 堆栈 |
| 25% | 10 分钟 | p95 总耗时相对基线偏差 ≤ 20%，Reviewer 降级比例不上升 |
| 50% | 15 分钟 | 报告队列深度不持续增长；PG 连接数 < 80% 上限 |
| 100% | 24 小时 | 指标持平；旧版本保留到观察期结束再下线 |

4. **观察项**（至少）：`/api/ai/metrics` 的 status_codes、recent_errors（含 request_id）、LLM 失败/降级计数、Reviewer 指标；`/api/health/ready` 的 `checks.report_queue.depth`；平台 CPU/内存/实例重启次数。
5. **双版本并行是预期行为**：新旧版本共享 PG/Redis，报告队列 worker、数据保留清理可能同时在两个版本运行；任务抢占（`mark_running`）与清理逻辑均幂等，不会重复执行。

> 单机 docker-compose 无法按比例分流：可用新容器独立端口 + 网关/NGINX 权重；回滚时保留旧容器即可切回。

### 8.3 回滚

**触发条件（任一满足立即回滚，不再观察）**
- 5xx 比例 > 2% 持续 5 分钟，或连续 3 次健康检查失败
- 聊天超时（180s 预算耗尽）比例 > 5%，或 p95 总耗时 > 240s
- LLM 降级链耗尽、Reviewer 全链不可用等关键指标出现并持续
- 报告队列深度持续增长 > 10 分钟且无下降趋势
- 出现冒烟阶段未覆盖的新 ERROR 堆栈

**执行**
1. 在平台版本管理/流量策略把新版本流量切到 0%（或直接切回上一版本），不重新构建镜像。
2. 等一个健康检查周期，确认 `/api/health/live` 的 `version` 已回到上一版本、`/ready` 正常。
3. 复跑冒烟：健康检查 + 命盘接口 + 一轮聊天。
4. 保留故障实例日志（用响应头 `X-Request-ID` 定位单请求），记录回滚时间线，24 小时内完成复盘。

**数据侧红线**
- 只做增量迁移时，旧版本可直接跑在新表结构上；**禁止同一次发布包含破坏性迁移**（删列/改类型），否则无法仅靠切流量回滚。
- 回滚不清库：新版本已写入的会话、报告任务、checkpoint 保留；若怀疑数据被写坏，先停止写入并恢复发布前 PG 快照。
- Redis 队列可能残留新版本入队的任务：任务 kind/params 必须能被旧版本识别，否则应等队列清空后再回滚。
- 管理员令牌格式变更（如签名密钥轮换）会让旧令牌失效，需在低峰期执行并提前通知。

### 8.4 发布后收尾

- 100% 流量稳定 24 小时后下线旧版本。
- 检查残留：异常中断的 checkpoint 由每日清理任务回收；报告任务按 7 天保留清理。
- 更新发布记录：`APP_VERSION`、变更摘要、灰度时间线、关键指标截图。

## 9. 容器访问数据库的网络连通性（必看）

云托管容器与云数据库 PostgreSQL **默认不在同一网络平面**，容器直接用 `172.17.0.x`、
`10.x` 等内网地址通常**连不通**，表现为：

- 构建成功，但部署阶段 `Liveness probe failed: dial tcp ...:80: connect: connection refused`；
- 启动日志停在「对话记忆存储: PostgreSQL」后无进展。

代码已做容错：数据库不可达时**不再阻断启动**（连接最多等 5s 后降级，端口照常监听，
存活探针通过），但记忆 / RAG 功能仍需数据库可达才可用。要让功能真正可用，二选一：

1. **（推荐，内网）把云托管服务放入数据库所在 VPC**
   控制台 → 云托管 → 服务 → 服务设置 → 网络 → 选择私有网络(VPC) 与子网 =
   该 PostgreSQL 实例所在的 VPC/子网。容器获得同 VPC IP 后即可直连内网地址。
2. **（最简，公网）开启 PostgreSQL 外网地址**
   云数据库 PostgreSQL 控制台 → 实例 → 数据库连接 → 开启外网地址，
   拿到 `*.rds.tencentdb.com:5432`，把 `POSTGRES_CONNECTION_STRING` 改为该地址
   （仍带 `?sslmode=require`）。云托管容器默认有出公网能力，可直接访问；
   安全组需放行（自用可临时放通 `0.0.0.0/0`）。

> 注意：连接串里的 `172.17.0.9` 这类地址疑似本地 Docker 桥接网段，
> 请务必从**云数据库 PostgreSQL 控制台「数据库连接」页**复制真实地址，
> 不要用本地 docker-compose 的地址。
