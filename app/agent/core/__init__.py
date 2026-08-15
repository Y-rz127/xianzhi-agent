"""Agent 框架层：基础 Agent 与两种具体实现（ReAct / Tool-Call）。

历史：原散落在 app/agent/ 顶层，与业务编排（xianzhi.py）、LangGraph 图
（xianzhi_langgraph.py）混在一起；2026-08-15 收拢到本子包以明确分层。
"""
