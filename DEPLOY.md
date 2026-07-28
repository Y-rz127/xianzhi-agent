# 部署指南：CloudBase 云托管 + 腾讯云 PostgreSQL

> 适用场景：把后端 FastAPI 跑在腾讯云 CloudBase 云托管（容器），数据库用腾讯云 PostgreSQL，
> 微信小程序 / H5 在任意网络下连接。**自己开发调试、不上体验版/正式版时无需 ICP 备案**。

---

## 1. 架构概览

| 组件 | 部署位置 | 说明 |
|------|----------|------|
| 后端 FastAPI | CloudBase 云托管（容器，跑现有 `Dockerfile`） | 平台注入 `PORT`，代码已自动读取 |
| 数据库 | 腾讯云 PostgreSQL（需支持 pgvector） | 存对话记忆 + RAG 向量 |
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

仓库已含 `Dockerfile` 与 `.dockerignore`（已排除 `frontend/`、`uniapp/`、`.env`、`data/`、
`.workbuddy/` 等，**镜像不会泄露密钥、也不会把前端代码打进去**）。

CloudBase 云托管支持两种方式：
- **关联代码仓库**（推荐）：控制台新建服务 → 关联 GitHub 仓库 → 指定分支 → 自动检测 `Dockerfile` 构建。
- **上传本地代码**：在项目根目录打包（排除 `.env`、`node_modules`）后上传。

### 4.2 服务关键配置

| 配置项 | 值 / 说明 |
|--------|-----------|
| 监听端口 | 平台注入 `PORT`（默认 80），`main.py` 已优先读取，无需改代码 |
| 健康检查路径 | `/api/health`（代码已提供） |
| 环境变量 | 见 `.env.example` 全部项；重点：`POSTGRES_CONNECTION_STRING`、`DASHSCOPE_API_KEY`、`VECTOR_STORE_TYPE=postgres`、`MEMORY_STORE_TYPE=postgres`、`CORS_ORIGINS` |
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

- 构建：`VITE_API_BASE=https://你的云托管域名/api npm run build`（`frontend` 目录）。
- 产物 `frontend/dist` 托管到 CloudBase 静态网站 / 任意静态服务器。
- 若用自有域名，需 ICP 备案并把域名加入 `CORS_ORIGINS`。

---

## 6. 验证

- 浏览器/终端访问 `https://你的云托管域名/api/health` 应返回健康状态。
- 小程序设置正确后，发一条消息验证端到端连通。

---

## 7. 注意事项

- **pgvector**：腾讯云 PG 需手动 `CREATE EXTENSION vector`，否则启动报错。
- **SSL**：腾讯云 PG 强制 `sslmode=require`，连接串务必带该参数。
- **鉴权**：`API_KEYS` 为空时后端不校验 Key（本地默认）；云端自己用也建议设一个 Key，避免被扫。
- **CORS**：`CORS_ORIGINS` 需包含前端域名，否则浏览器请求被拦；小程序 `wx.request` 不受 CORS 限制。
- **备案**：仅「自己开发调试 / 真机调试」使用时，微信小程序勾选不校验合法域名即可，**无需备案**；
  若要发布体验版/正式版或使用自有域名 H5，则需 ICP 备案。
- **密钥**：`.env` 已在 `.gitignore` 中，切勿提交真实密钥；云端请在平台环境变量面板配置。
