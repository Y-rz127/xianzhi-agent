# 多 Agent 状态边界

多 Agent 系统最容易失控的地方是状态共享过度。每个 Agent 应该只看到完成自己任务所需的上下文。

## 推荐边界

1. 主 Agent 保存任务目标、计划、子任务状态。
2. 子 Agent 只接收自己的子任务、必要资料和允许工具。
3. 子 Agent 返回结构化结果，不返回完整对话历史。
4. 高风险工具只暴露给需要它的 Agent。
5. 共享长期记忆时按 namespace 区分用户、项目和 Agent 类型。

## 不推荐

- 所有 Agent 共用一整份 messages。
- 子 Agent 可以调用所有工具。
- 子 Agent 可以随意写入全局长期记忆。
- Supervisor 不验证 Worker 结果就直接输出。

## 最小结果协议

```python
class WorkerResult(BaseModel):
    status: Literal["done", "blocked", "failed"]
    summary: str
    evidence: list[str] = []
    next_actions: list[str] = []
```

