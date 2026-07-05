"""工具调用白名单与权限控制示例。

模型提出工具调用不等于一定可以执行。高风险工具需要按用户、角色、动作做权限判断。
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import tool


@dataclass
class RuntimeContext:
    user_id: str
    role: str


def require_role(context: RuntimeContext, allowed_roles: set[str]) -> None:
    if context.role not in allowed_roles:
        raise PermissionError(f"用户 {context.user_id} 无权执行该工具。")


@tool
def read_report(report_id: str) -> str:
    """Read a public report by id."""
    return f"报告 {report_id} 的摘要内容。"


@tool
def delete_report(report_id: str, role: str = "viewer") -> str:
    """Delete a report. Only admin role should call this."""
    require_role(RuntimeContext(user_id="demo", role=role), {"admin"})
    return f"报告 {report_id} 已删除。"


agent = create_agent(
    model="openai:gpt-4.1-mini",
    tools=[read_report, delete_report],
    system_prompt=(
        "你只能在明确需要时调用工具。删除类操作必须确认用户拥有 admin 权限。"
    ),
)


if __name__ == "__main__":
    print("示例重点是权限模式；真实项目应从登录态注入 user_id 和 role。")

