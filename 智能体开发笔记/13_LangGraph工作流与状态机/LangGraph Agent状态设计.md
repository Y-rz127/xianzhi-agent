# LangGraph Agent 状态设计

LangGraph 适合把 Agent 从“黑盒循环”拆成可检查、可恢复、可测试的状态机。状态设计越清晰，后续的路由、记忆、人工审批和错误恢复越简单。

## 常见状态字段

| 字段 | 用途 |
| --- | --- |
| `messages` | 对话消息，通常配合 reducer 追加 |
| `user_id` | 用户标识，用于权限、偏好、长期记忆 |
| `task` | 当前任务描述 |
| `plan` | 计划步骤 |
| `retrieved_docs` | RAG 检索结果 |
| `tool_results` | 工具调用结果 |
| `needs_approval` | 是否需要人工审批 |
| `final_answer` | 最终输出 |

## 设计原则

1. 状态只保存必要信息，不把所有中间文本都塞进去。
2. 节点返回“增量更新”，不要在节点里直接修改原状态对象。
3. 会增长的字段使用 reducer，例如 messages 追加。
4. 对高风险工具调用保留 `approval_reason`、`proposed_action`、`approved_by`。
5. 可恢复任务必须配置 checkpointer，并在调用时传 `thread_id`。

## 什么时候不用 LangGraph

- 只是 `prompt | model | parser` 的简单链。
- 没有分支、循环、人工审批、恢复需求。
- 没有复杂多 Agent 协作。

## 什么时候应该用 LangGraph

- Agent 需要多个工具循环。
- 中途要暂停等待人工确认。
- 要支持任务失败后恢复。
- 要明确记录每一步状态。
- 要实现多 Agent、Planner/Executor、Supervisor/Worker。

