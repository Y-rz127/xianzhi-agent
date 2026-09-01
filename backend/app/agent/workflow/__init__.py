"""先知工作流子包。

收口原 app/agent/ 下散落的 workflow 家族模块：
- workflow_models：领域 Worker / 意图 / 命盘上下文等数据模型
- workflow_support：容错 JSON、命理信号正则、意图分类、命盘上下文构建
- workflow_workers：领域 Worker 注册表与 Reviewer 审核 Agent
- workflow_retrieval：RAG 知识检索 / 查询构造 / 合婚对方盘解析（纯函数）
- workflow_messages：消息拼装 / 事实校验（纯函数）
- xianzhi_workflow：XianzhiWorkflow 编排核心（LangGraph 节点委托其方法）

包内模块互相引用统一使用绝对路径 app.agent.workflow.<module>。
"""
