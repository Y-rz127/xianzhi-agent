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
| 健康检查路径 | `/api/health`（代码已提供） |
| 环境变量 | 见 `.env.example` 全部项；重点：`POSTGRES_CONNECTION_STRING`、`DASHSCOPE_API_KEY`、`VECTOR_STORE_TYPE=postgres`、`MEMORY_STORE_TYPE=postgres`、`CORS_ORIGINS`、`REDIS_URL`、`TRUST_PROXY_HEADERS=true`、`LLM_MAX_CONCURRENCY` |
| 内存 / 超时 | 建议内存 ≥ 1GB、请求超时 ≥ 60s（LLM 调用较慢） |

> 改动点：`main.py` 的 `uvicorn` 启动已改为优先读 `PORT`；`Dockerfile` 的 `EXPOSE 80`；
> 新增 `.dockerignore` 防止密钥/前端代码进入镜像。本地与云端双兼容。

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

## 8. 容器访问数据库的网络连通性（必看）

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
