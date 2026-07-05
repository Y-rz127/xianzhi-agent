"""MCP 客户端封装（对应 Java 项目的 ToolCallbackProvider + mcp-servers.json）。

将 MCP 服务端工具动态包装成 LangChain BaseTool，供 Agent 统一调用。
当前接入高德地图 MCP（地理/天气/导航），与 Java 项目 mcp-servers.json 配置一致。

设计：MCPManager 单例在应用启动时建立 stdio 长连接，维持 session 活跃，
工具调用复用同一 session；应用关闭时清理连接。
"""
from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.config import settings
from app.logger import log


class _MCPToolSchema(BaseModel):
    """MCP 工具动态参数 schema 占位。"""
    args: dict = Field(default_factory=dict, description="工具参数 JSON 对象")


class MCPToolWrapper(BaseTool):
    """把单个 MCP 工具包装成 LangChain BaseTool。调用复用 manager 持有的 session。"""
    name: str
    description: str
    args_schema: type = _MCPToolSchema
    _manager: Any
    _tool_name: str

    def __init__(self, manager, tool_name, tool_description):
        super().__init__(name=tool_name, description=tool_description or tool_name)
        object.__setattr__(self, "_manager", manager)
        object.__setattr__(self, "_tool_name", tool_name)

    def _run(self, args: dict | None = None, **kwargs):
        if args is None:
            args = kwargs
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._call_mcp(args))
            finally:
                loop.close()
        except Exception as e:
            return "MCP 工具 {} 调用失败: {}".format(self._tool_name, e)

    async def _arun(self, args: dict | None = None, **kwargs):
        if args is None:
            args = kwargs
        return await self._call_mcp(args)

    async def _call_mcp(self, arguments: dict) -> str:
        session = self._manager.session
        if session is None:
            return "MCP 会话未就绪"
        try:
            result = await asyncio.wait_for(
                session.call_tool(self._tool_name, arguments),
                timeout=30,
            )
            if hasattr(result, "content") and result.content:
                parts = []
                for item in result.content:
                    text = getattr(item, "text", None) or str(item)
                    parts.append(text)
                return "\n".join(parts)
            return str(result)
        except Exception as e:
            log.exception("MCP 工具 {} 调用失败", self._tool_name)
            return "MCP 工具 {} 调用失败: {}".format(self._tool_name, e)


class MCPManager:
    """管理 MCP stdio 长连接，在后台 task 中维持 session。"""

    def __init__(self):
        self.session = None
        self._task = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._tools: list[BaseTool] = []
        self._available = False

    async def start(self) -> None:
        """启动 MCP server 并建立长连接。失败不抛异常，仅标记不可用。"""
        if not settings.amap_maps_api_key:
            log.warning("未配置 AMAP_MAPS_API_KEY，跳过 MCP")
            return
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
        except ImportError:
            log.warning("未安装 mcp 库，跳过 MCP")
            return

        server_params = StdioServerParameters(
            command="npx.cmd",
            args=["-y", "@amap/amap-maps-mcp-server"],
            env={"AMAP_MAPS_API_KEY": settings.amap_maps_api_key},
        )

        async def _run():
            try:
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self.session = session
                        tool_resp = await session.list_tools()
                        for t in tool_resp.tools:
                            self._tools.append(MCPToolWrapper(
                                manager=self,
                                tool_name=t.name,
                                tool_description=t.description or t.name,
                            ))
                        self._available = True
                        self._ready.set()
                        log.info("MCP 就绪，加载 {} 个工具: {}",
                                 len(self._tools), [t.name for t in self._tools])
                        # 维持连接直到 stop
                        await self._stop.wait()
            except Exception as e:
                log.warning("MCP 启动失败（高德地图，需 Node.js/npx）: {}", e)
                self._ready.set()

        self._task = asyncio.create_task(_run())
        # 等待就绪或失败，最多 30 秒
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            log.warning("MCP 启动超时（30s），跳过")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self._available

    def get_tools(self) -> list[BaseTool]:
        return list(self._tools)


# 全局单例
mcp_manager = MCPManager()