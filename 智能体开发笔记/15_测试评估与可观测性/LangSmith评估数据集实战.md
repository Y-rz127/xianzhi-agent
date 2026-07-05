# LangSmith 评估数据集实战

LangSmith 适合记录 Agent trace、沉淀测试数据集、对比不同 prompt/model/tool 配置。

## 建议流程

1. 打开 tracing。
2. 运行一批真实问题。
3. 从 trace 中挑选成功和失败样本加入 dataset。
4. 定义 evaluator，例如准确性、是否调用正确工具、是否引用来源。
5. 修改 Agent 后重新跑 experiment，对比指标。

## 环境变量

```txt
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=你的 LangSmith key
LANGCHAIN_PROJECT=agent-learning
```

## 适合评估的样本

- RAG 问答：答案是否来自上下文。
- 工具调用：工具名和参数是否正确。
- 多轮记忆：是否记住同一 thread 内的信息。
- 安全策略：敏感输入是否被阻断或脱敏。

