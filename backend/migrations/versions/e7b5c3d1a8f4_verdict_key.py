"""chart_verdicts 增加裁决指纹 verdict_key（四柱 + 性别）

Revision ID: e7b5c3d1a8f4
Revises: d9a1c7e5b4f2
Create Date: 2026-10-24 21:30:00.000000

裁决身份从"出生时刻"改成"四柱 + 性别"：同一张嘴的盘（不同出生时刻/经度/写法）跨人复用
同一份裁决，命中即回放、不再重复调 LLM。chart_hash 是早期口径的身份，保留做审计与老行兜底。

**为什么用裸 SQL + IF EXISTS**：本仓库的建表是运行时 `_ensure_tables()` 负责的，
alembic 只补增量列（`chart_verdicts` 本身没有任何 create_table 迁移，`d9a1c7e5b4f2`
改的 `session_birth_info` 亦然）。裸 SQL 让这条迁移在两种库上都安全：表已被运行时
建好 → 加列加索引；表还不存在 → 跳过，等 `_ensure_tables()` 带着新列一起建。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e7b5c3d1a8f4"
down_revision: Union[str, None] = "d9a1c7e5b4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE IF EXISTS chart_verdicts ADD COLUMN IF NOT EXISTS verdict_key TEXT"
    )
    conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_chart_verdicts_vkey"
        " ON chart_verdicts(verdict_key, engine_version, prompt_version)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DROP INDEX IF EXISTS idx_chart_verdicts_vkey")
    conn.exec_driver_sql("ALTER TABLE IF EXISTS chart_verdicts DROP COLUMN IF EXISTS verdict_key")
