"""用户态数据访问层（账号 + 用户私有数据）。

导入本包即完成运行时 KV 存储的注册（副作用在 ``kv_store`` 模块内），
保证 core 层的 ``get_config`` / ``set_config`` 在业务代码调用前已可用。
"""

from __future__ import annotations

from app.db import kv_store as _kv_store  # noqa: F401 - 导入即注册 KV 存储

__all__: list[str] = []
