# 项目长期备忘 (xianzhi-agent)

## 备案合规约束（写代码/注释必守）
- 用户明确要求代码"不要成屎山、降低 AI 味"，后续需备案/合规审查。
- 注释原则：只补必要 docstring，不堆废话套话；私有 helper 不补注释；保持结构紧凑、可审查。

## Git / 出网环境
- 沙箱 git 配置 http.proxy=http://127.0.0.1:7890(用户本机代理)。**代理开启时沙箱可直推**；代理关闭则不可达/超时。
- 已验证：用户开代理后 `git push origin main` 成功(推送 a26623d)。无需用户另跑终端。

## 功能决策（已否决/暂缓）
- **四柱直接排盘（八字录入模式）**：用户曾提议「命例录入支持直接填四柱 + 对话中'我的八字是XXX我是男命'自动排盘」。经评估否决：lunar_python 的 `EightChar` 只能从 `Lunar` 日期构造，无法从四柱反推；同一四柱可对应多个出生日期，无精确生日则大运起运/流年/命宫身宫都会排错，误导用户。**结论：命例录入仍强制出生时间，四柱直排盘需求暂缓不做**。

## 临时变更（待恢复）
- **小程序强制登录守卫已临时关闭**（commit 5f0524b，已推送 main）：`uniapp/src/App.vue` 全局 onShow 拦截 + `uniapp/src/utils/authGuard.ts` 的 `requireLogin()` 均改为不拦截（直接 return true / 空 onShow）。目的：排查朋友真机调试"进不去"（已确认朋友成功进入）。**合规审查 / 正式发布前必须恢复登录拦截**——恢复内容见该 commit 的 diff。

## 技术约束
- 沙箱无外网：`pip install` 会超时，静态分析改用纯标准库 AST 脚本，不依赖 pyflakes/ruff。
- 写文件后用 Write 工具可能带入 UTF-8 BOM，必要时用脚本检测并剥离 `b'\xef\xbb\xbf'`。
- bash 路径用正斜杠 `/c/CodeProjects/...`，反斜杠会被转义报错。
- 服务 `reload=False`，改代码后必须 `taskkill` 旧进程并重启才生效。
- 前端源码量很小（frontend/src≈29、uniapp/src≈31 文件），项目总文件数的大头是 node_modules/dist。BOM 可能是**多重叠加**（最多见 11 层连续 EF BB BF），剥离要循环去首 3 字节直到无 BOM；前端无 eslint，可用各自 node_modules 里已装的 typescript 做离线 AST 分析。
- 部署（CloudBase 云托管+腾讯云 PG）：main.py 已读 `PORT` 环境变量、Dockerfile EXPOSE 80；腾讯云 PostgreSQL 默认不带 pgvector 需手动 `CREATE EXTENSION vector;`，连接串必须 `?sslmode=require`；小程序自用时开发版+真机调试勾「不校验合法域名」即免备案（体验版/正式版/自有域名 H5 才需备案）。详见仓库 `DEPLOY.md`。
