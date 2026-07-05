# BaseAgent 示例智能体设计

`templates/base_agent.py` 是一个不依赖任何大模型框架的基础智能体模板。它的目标不是替代 LangChain 或 LangGraph，而是帮助理解 Agent 的核心结构。

## 核心对象

| 对象 | 作用 |
| --- | --- |
| `BaseAgent` | 智能体基类，负责运行流程、工具调用、记忆和轨迹 |
| `AgentAction` | 计划中的动作，例如 think、tool、remember、respond |
| `AgentStep` | 实际执行后的轨迹记录 |
| `ToolSpec` | 工具名称、描述、函数和是否直接返回 |
| `AgentMemory` | 简单 key-value 记忆和消息历史 |

## 执行流程

1. `run(user_input)` 接收用户输入。
2. 写入 memory messages。
3. 调用 `plan(user_input)` 得到动作列表。
4. 逐步执行动作。
5. 遇到 tool 动作时调用注册工具。
6. 记录每一步 trace。
7. 调用 `compose_answer(...)` 生成最终回答。
8. 把助手回答写入 memory messages。

## 扩展点

- 重写 `plan()`：把规则规划替换成 LLM 规划、ReAct 或 LangGraph。
- 重写 `compose_answer()`：把观察结果组织成更适合业务的回答。
- 新增工具：使用 `add_tool(...)` 或注册 `ToolSpec`。
- 替换记忆：实现自己的持久化 memory，例如 Redis、SQLite 或向量记忆。

## 运行示例

从 `PythonProject` 目录运行：

```powershell
python -m AI.examples.base_agent_demo
```

这个示例会演示：

- 根据用户输入生成动作计划。
- 调用 `calculator` 工具。
- 调用 `knowledge_search` 工具。
- 把最后一次用户输入写入记忆。
- 输出完整执行轨迹。

