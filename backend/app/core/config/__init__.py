"""应用配置包。

- `settings`：pydantic-settings 实例（从 .env / 环境变量加载）
- `kv`：运行时 KV 配置访问（零业务依赖，具体存储由 infra 层注册）

注意：本包对外暴露的 `settings` 是 **Settings 实例**（同名子模块 `settings` 被有意遮蔽），
调用方一律 `from app.core.config import settings`。
"""

from __future__ import annotations

from app.core.config.settings import (
    BACKEND_ROOT,
    Settings,
    ensure_dirs,
    settings,
)

__all__ = ["BACKEND_ROOT", "Settings", "ensure_dirs", "settings"]
