# AI Agent 学习资料总览

这个目录按能力模块组织，目标是从模型调用、提示词、LCEL、RAG、工具调用，逐步过渡到 Agent 设计、记忆、多 Agent、测试评估和工程化模板。

## 快速入口

- `00_学习路线与总览/学习路线.md`：完整学习顺序。
- `templates/base_agent.py`：不依赖大模型框架的 `BaseAgent` 基类模板。
- `examples/base_agent_demo.py`：可直接运行的 BaseAgent 示例智能体。
- `docs/base_agent_design.md`：BaseAgent 设计说明。
- `tests/test_agent_basic.py`：BaseAgent 基础测试。

## BaseAgent 示例运行

从 `PythonProject` 目录运行：

```powershell
python -m AI.examples.base_agent_demo
```

也可以直接运行文件：

```powershell
python AI/examples/base_agent_demo.py
```

这个示例会展示：

- 工具注册：`calculator`、`knowledge_search`
- 动作计划：`think`、`remember`、`tool`、`respond`
- 简单记忆：记录最后一次用户输入
- 执行轨迹：每一步动作、工具结果和错误信息

## 目录说明

| 目录 | 内容定位 |
| --- | --- |
| `00_学习路线与总览` | 学习路线、运行环境提示 |
| `01_基础调用与提示词` | ChatModel、PromptTemplate、流式输出、LangSmith 入门 |
| `02_LCEL链与Runnable编排` | RunnablePassthrough、RunnableLambda、RunnableParallel、RunnableBranch |
| `03_输出解析与结构化输出` | 字符串、JSON、Pydantic 结构化输出、输出修复 |
| `04_文档加载与文本切分` | PDF、Word、网页、多类型文档加载与文本切分 |
| `05_嵌入模型与相似度` | Embeddings、自定义嵌入、缓存、余弦相似度 |
| `06_向量数据库_Milvus` | Milvus collection、索引、DML、检索、LangChain 集成 |
| `07_RAG检索与文档问答` | Retriever、MultiQueryRetriever、文档助手、医疗问答 RAG |
| `08_Tool工具与联网搜索` | 自定义 Tool、工具异常处理、联网搜索、模型绑定工具 |
| `09_Agent智能体` | Agent、ReAct、个人助手、新版 `create_agent`、旧版迁移 |
| `10_记忆与多会话` | 短期记忆、多会话隔离、Redis、LangGraph checkpointer/store |
| `11_MCP协议` | MCP 服务端与客户端 |
| `12_Python工程基础` | 类型注解等 Python 工程基础 |
| `13_LangGraph工作流与状态机` | StateGraph、条件路由、人工中断、状态设计 |
| `14_Agent安全与Guardrails` | 工具权限、PII 脱敏、Prompt Injection、高风险审批 |
| `15_测试评估与可观测性` | Tool 测试、Agent 集成测试、轨迹评估、LangSmith 评估 |
| `16_多Agent协作` | Router、Planner/Executor、Supervisor/Worker、状态边界 |
| `templates` | 可复用模板：`BaseAgent`、工具、记忆等基础结构 |
| `examples` | 可直接运行的最小示例 |
| `docs` | 架构、安全、BaseAgent 设计说明 |
| `tests` | 基础测试 |
| `scripts` | 外部服务启动和检查说明 |

## 推荐学习顺序

1. 先看基础模型调用：`01_基础调用与提示词`。
2. 学链式编排：`02_LCEL链与Runnable编排`。
3. 学输出稳定性：`03_输出解析与结构化输出`。
4. 学 RAG 全链路：`04` 到 `07`。
5. 学工具调用：`08_Tool工具与联网搜索`。
6. 先读 `templates/base_agent.py` 和 `examples/base_agent_demo.py`，理解 Agent 骨架。
7. 再进入 `09_Agent智能体`、`10_记忆与多会话`。
8. 复杂状态和长任务再学 `13_LangGraph工作流与状态机`。
9. 最后补安全、测试和多 Agent：`14`、`15`、`16`。

## 工程化文件

- `.env.example`：环境变量模板。
- `config.py`：统一读取 `.env` 和环境变量。
- `requirements.txt`：常见依赖清单。
- `scripts/服务启动说明.md`：Redis、Milvus、Ollama、MCP 的运行前检查。

## 运行提醒

- 很多 LangChain 示例需要 API Key、Milvus、Redis、Ollama 或联网搜索服务。
- `BaseAgent` 示例不需要真实大模型，也不需要第三方依赖，适合先理解 Agent 架构。
- 不建议一次性批量运行全部脚本；这些文件更适合作为分主题学习样例。

