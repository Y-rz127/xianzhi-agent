# initialize_agent 到 create_agent 迁移说明

现有资料里有 `initialize_agent`、`AgentType.ZERO_SHOT_REACT_DESCRIPTION`、`LLMChain` 等旧式写法。学习 ReAct 原理时可以继续读，但新项目建议优先使用 `create_agent`。

## 旧写法

```python
from langchain.agents import AgentType, initialize_agent

agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)
result = agent.invoke({"input": "问题"})
```

## 新写法

```python
from langchain.agents import create_agent

agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=tools,
    system_prompt="你是一个严谨的助手。",
)
result = agent.invoke({
    "messages": [{"role": "user", "content": "问题"}]
})
```

## 关键变化

| 旧版概念 | 新版对应 |
| --- | --- |
| `llm=` | `model=` |
| `AgentType.ZERO_SHOT_REACT_DESCRIPTION` | `create_agent` 默认工具循环 |
| `{"input": "..."}` | `{"messages": [...]}` |
| 手动管理历史 | 配置 `checkpointer` + `thread_id` |
| 手动解析最终结果 | `response_format=` 结构化输出 |
| 复杂状态流 | 升级为 LangGraph |

## 迁移建议

1. 先把工具函数保留不动，只替换 Agent 创建方式。
2. 把字符串输入改成 messages 输入。
3. 如果需要多轮对话，给 `create_agent` 加 `checkpointer`，调用时传 `thread_id`。
4. 如果 Agent 需要复杂分支、人工审批、长任务恢复，直接改用 LangGraph。

