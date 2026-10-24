# 先知对话 WS：单连接多路复用（多会话并行）

> 一句话：**一条 WebSocket 上同时跑多个会话的生成**，每轮带一个 `request_id`，
> 服务端推送的每一帧原样带回，前端据此把帧路由回各自的会话。

## 为什么不能"多开连接"

小程序里同一页面只可能有一条 socket，且有两个硬约束（细节见
`frontend/uniapp/src/api/chat.ts` 文件头的踩坑记录）：

1. 收包只能靠全局 `wx.onSocketMessage` —— 帧进来时**没有 socket 身份**，
   无法区分"这是哪条连接的"；
2. 真机上 `uni.connectSocket` 返回的 `SocketTask` 是个空对象，`onMessage/send` 全没有；
3. `wx.closeSocket()` 关的是"那条"全局 socket，再叠加小程序 5 条连接上限。

所以旧实现的做法是"发新消息先掐掉旧连接"。代价是：
**上一个会话还在生成时新建会话提问，等于把它的推送通道掐了**，
更糟的是旧连接的回调仍会落到被原地清空的消息数组上
（`newSession` 用 `splice` 清空同一个数组），按下标写就写出 `undefined` 空洞，
`v-for` 渲染时读 `msg.role` 直接抛
`TypeError: Cannot read properties of undefined (reading 'role')`（线上崩过的那个）。

多开连接这条路走不通，那就只能让**一条连接跑多轮**。

## 协议

客户端 → 服务端（原有字段不变，新增 `request_id`）：

```json
{
  "message": "帮我看看今年",
  "conversation_id": "mp-xianzhi-<uuid>",
  "request_id": "<本轮唯一 id>",
  "client_msg_id": "<同 request_id，用于防重放>",
  "birth_time": "...", "gender": "男", "birth_place": "杭州", "longitude": 120.15,
  "sect": 2, "yun_sect": 1, "token": "...", "verbose": false
}
```

服务端 → 客户端：**每一帧都带 `request_id`**。

| type | 载荷 | 说明 |
|---|---|---|
| `message` | `data: string` | 回答正文的一个 chunk |
| `progress` | `data: string` | 阶段进度（"正在检索命理知识…"） |
| `chart_context` | `data: {birth_time, gender, birth_place?, longitude?}` | 挂盘成功，**挂盘那一刻就发**，不等整轮 |
| `done` | — | 本轮结束（后端早已落库） |
| `error` | `data: string` | 本轮失败/被拒（含并发上限、会话忙、无权限） |
| `ping` | — | 连接级保活，**不带 `request_id`** |

- 没有 `request_id` 的老客户端照常可用：服务端回显空串，老客户端忽略未知字段。
- 同一 `request_id` 重复发（客户端重发）→ 直接回错误，避免前端路由错乱。
- 没有 `request_id` 的帧只可能是连接级错误 → 前端广播给所有在跑的轮次。

## 服务端实现（`backend/app/api/xianzhi_chat.py`）

- `ws_chat_with_xianzhi` 只做**收包与派发**：校验 → `conn.spawn()` 起一个 task，立刻回去收下一条；
- 每轮独立 task，各自 `get_xianzhi(conversation_id)` + `SessionLock`：
  **同会话串行、跨会话并行**（锁是 `lock:session:{conversation_id}`，进程内 + Redis 双层）；
- `_WsConnection.send_json` 用一把 `asyncio.Lock` 串行化发送 —— 并发 `send_json`
  会把字节互相插入，帧就废了（`tests/test_ws_multiplex.py` 断言 `max_in_flight == 1`）；
- `_TurnSender` 与 WebSocket **同形**（只有 `send_json`），所以 `_relay_chunks` /
  `_safe_ws_send` / 挂盘通知器 / 进度通知器全部原样复用，只是帧多了一个 `request_id`；
- 并发上限 `WS_MAX_PARALLEL_SESSIONS`（默认 3）：**超了直接回错误，不排队** ——
  在这条连接上排队只会变成"用户以为发出去了，其实在等"；
- 保活 `ws_keepalive_loop` 按**连接**起一个（不是按轮次，否则 N 个会话各发各的 ping）；
- **断线不中止生成**（策略没变）：客户端走了，轮次继续跑完并落库，
  只是 `_safe_ws_send` 返回 False 后不再推送。task 用模块级 `_BACKGROUND_TURNS`
  留强引用，避免 handler 返回后被 GC 掉。

## 前端实现（`frontend/uniapp/src/api/chat.ts`）

- `sendXianzhiTurn(message, opts, handlers)`：登记 `turnId → handlers`，
  连接没建就先建（`wx.onSocket*` 全局回调只认自己那条连接的序号），
  握手完成前发的轮次进队列，连上后按序发出（各轮在服务端并发）；
- 收帧只按 `request_id` 找 handlers，**找不到就静默丢弃** —— 少了这一句就会串台；
- `closeXianzhiSocket()` / 连接断开 → 在跑的轮次收到 `onDisconnect`，
  页面转成"去会话记录里取回"（后端不中止生成，答案一定在）；
- 别的页面（塔罗/六爻/紫微）会 `wx.closeSocket` 把连接换走：`sendXianzhiTurn`
  里用序号比对发现"连接已不是我的"，当断线处理并重连。

## 页面状态（`frontend/uniapp/src/pages/xianzhi/index.vue`）

- `turns: Record<convId, TurnState>`：**按会话**记在跑的轮次（`turnId/question/text/progress/idx`）；
- 推送先写缓冲，只有"该会话正停在前台"才同步到 `messages`（`writeTurn`）；
- 切回某会话时 `attachTurnToView()` 把缓冲铺回列表并继续实时刷新；
  服务端历史里已有这轮答案（`done` 帧丢了）时直接认领那一条，不重复插；
- `thinking` 是 `computed`：只看**当前会话**有没有在跑，所以 A 会话生成时可以去 B 会话提问；
- `onShow` 的 `recoverStaleTurns()`：连接被系统回收/被别的页面换走时 close 事件
  不一定回到我们手上，这里把"SDK 还在等、连接却没了"的轮次统一转成取回流程。

## 验证

```bash
# 后端：多路复用行为（并发帧带各自 rid、发送不交错、同会话串行、并发上限、断线续跑）
PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests/test_ws_multiplex.py -q

# 前端类型门
cd frontend/uniapp && npx vue-tsc --noEmit
```

手工验：会话 A 提一个长问题 → 不等回答，点「新会话」→ 会话 B 提问 →
两边各自流式输出；切回 A 能看到 A 的回答继续在长；把同时生成的会话数开到
`WS_MAX_PARALLEL_SESSIONS + 1`，第 N+1 个应立刻收到
"最多同时 N 个会话在生成，请等其中一个完成再发"。
