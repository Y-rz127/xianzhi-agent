# Agent 架构简介

建议内容：

- Agent 层次：`Interface (tools/memory)` -> `Planner` -> `Executor` -> `Observation`。
- 设计原则：最小可测、可替换、依赖注入。
- 集成注意：外部服务（Milvus/Redis/模型服务）应通过适配器统一封装。
