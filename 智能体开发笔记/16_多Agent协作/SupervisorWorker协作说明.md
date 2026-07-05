# Supervisor + Worker 协作说明

Supervisor 负责决策、分派、验收；Worker 负责单一能力执行。

## 典型角色

| 角色 | 职责 |
| --- | --- |
| Supervisor | 判断任务类型、选择 Worker、合并结果 |
| Research Worker | 搜索资料、整理来源 |
| Coding Worker | 编写或修改代码 |
| RAG Worker | 检索知识库并回答 |
| Review Worker | 检查遗漏、风险和测试 |

## 适用场景

- 任务复杂，单 Agent 容易上下文过长。
- 需要并行处理多个子任务。
- 不同子任务需要不同工具权限。
- 希望把高风险工具限制在少数 Worker 中。

## 状态边界

Supervisor 不应把所有 Worker 的完整中间过程都塞进主上下文。Worker 返回结构化摘要即可：

```python
{
    "status": "done",
    "summary": "...",
    "artifacts": ["path/to/file.py"],
    "risks": ["..."],
}
```

