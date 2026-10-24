"""会话命盘快照（保存接口先落计算版，终审完成后覆盖）

Revision ID: d9a1c7e5b4f2
Revises: c4e8a9f1b2d6
Create Date: 2026-10-24 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d9a1c7e5b4f2"
down_revision: Union[str, None] = "c4e8a9f1b2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_birth_info",
        sa.Column("chart_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "session_birth_info",
        sa.Column("chart_engine_version", sa.TEXT(), nullable=True),
    )
    op.add_column(
        "session_birth_info",
        sa.Column("verdict_status", sa.TEXT(), server_default=sa.text("'none'"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_birth_info", "verdict_status")
    op.drop_column("session_birth_info", "chart_engine_version")
    op.drop_column("session_birth_info", "chart_json")
