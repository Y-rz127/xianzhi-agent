"""Planner + Executor 任务分解示例。

Planner 负责拆步骤，Executor 负责逐步执行。这里用规则模拟，便于先理解结构。
"""

from __future__ import annotations


def planner(task: str) -> list[str]:
    return [
        f"明确目标：{task}",
        "收集必要资料",
        "执行核心步骤",
        "检查结果并总结",
    ]


def executor(step: str) -> str:
    return f"已完成 - {step}"


def run_task(task: str) -> dict[str, list[str] | str]:
    plan = planner(task)
    results = [executor(step) for step in plan]
    return {
        "task": task,
        "plan": plan,
        "results": results,
        "final": "任务已按计划执行完成。",
    }


if __name__ == "__main__":
    output = run_task("搭建一个个人知识库 Agent")
    for item in output["results"]:
        print(item)

