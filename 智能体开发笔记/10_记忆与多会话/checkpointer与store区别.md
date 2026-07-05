# checkpointer 与 store 区别

| 对比项 | checkpointer | store |
| --- | --- | --- |
| 保存内容 | 图状态快照 | 应用自定义键值数据 |
| 作用范围 | 单个 thread | 跨 thread |
| 典型用途 | 会话连续性、人工中断恢复、失败恢复 | 用户偏好、长期事实、共享知识 |
| 访问方式 | 调用 graph/agent 时传 `thread_id` | 在节点或业务代码中读写 namespace/key |
| 生命周期 | 跟随对话线程 | 跟随应用数据 |

## 简单判断

- “用户上一轮说了什么？”用 checkpointer。
- “这个用户长期偏好中文回答？”用 store。
- “任务暂停后继续执行？”用 checkpointer。
- “跨多个会话都要记住的事实？”用 store。

多数真实 Agent 会同时使用两者：checkpointer 管当前线程，store 管长期用户数据。

