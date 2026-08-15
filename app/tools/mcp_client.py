"""MCP 客户端封装（对应 Java 项目的 ToolCallbackProvider + mcp-servers.json）。

将 MCP 服务端工具动态包装成 LangChain BaseTool，供 Agent 统一调用。
当前接入高德地图 MCP（地理/天气/导航），与 Java 项目 mcp-servers.json 配置一致。

设计：MCPManager 单例在应用启动时建立 stdio 长连接，维持 session 活跃，
工具调用复用同一 session；应用关闭时清理连接。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import traceback
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logger import log


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
            # MCP session 绑定在启动时的主事件循环上（stdio 流跨 loop 调用会报错），
            # 同步路径必须把协程调度回主 loop 执行，而不是新建 loop。
            loop = self._manager.loop
            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self._call_mcp(args), loop)
                return future.result(timeout=35)
            # 主 loop 不可用（未启动/已关闭）：session 大概率也不可用，走本地 loop 兜底
            local = asyncio.new_event_loop()
            try:
                return local.run_until_complete(self._call_mcp(args))
            finally:
                local.close()
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
        self._loop = None  # 启动时所在的主事件循环（同步工具调用调度回此 loop）

    @property
    def loop(self):
        return self._loop

    async def start(self) -> None:
        """启动 MCP server 并建立长连接。失败不抛异常，仅标记不可用。"""
        if not settings.amap_maps_api_key:
            log.warning("未配置 AMAP_MAPS_API_KEY，跳过 MCP")
            return
        self._loop = asyncio.get_running_loop()
        try:
            from mcp import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError:
            log.warning("未安装 mcp 库，跳过 MCP")
            return

        # 解析 npx 可执行文件路径（优先 PATH，其次常见安装位置）
        npx_cmd = shutil.which("npx.cmd") or shutil.which("npx")
        nodejs_dir = None
        if not npx_cmd:
            for fallback in (
                r"C:\Program Files\nodejs\npx.cmd",
                r"C:\Program Files (x86)\nodejs\npx.cmd",
            ):
                if os.path.isfile(fallback):
                    npx_cmd = fallback
                    nodejs_dir = os.path.dirname(fallback)
                    break
        else:
            nodejs_dir = os.path.dirname(npx_cmd)
        if not npx_cmd:
            log.warning("未找到 npx，跳过 MCP（请确认已安装 Node.js 并重启终端）")
            return

        # 继承当前环境变量，追加 API Key
        child_env = {**os.environ, "AMAP_MAPS_API_KEY": settings.amap_maps_api_key}
        # 确保 Node.js 目录在子进程 PATH 中（npx 运行时需要找到 node.exe）
        if nodejs_dir:
            current_path = child_env.get("PATH", child_env.get("Path", ""))
            if nodejs_dir not in current_path:
                child_env["PATH"] = nodejs_dir + os.pathsep + current_path

        server_params = StdioServerParameters(
            command=npx_cmd,
            args=["-y", "@amap/amap-maps-mcp-server"],
            env=child_env,
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
                log.warning("MCP 异常详情:\n{}", traceback.format_exc())
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
