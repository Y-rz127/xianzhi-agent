"""管理员账号

Revision ID: c4e8a9f1b2d6
Revises: b7e4c2a1d9f0
Create Date: 2026-10-24 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4e8a9f1b2d6"
down_revision: Union[str, None] = "b7e4c2a1d9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column("id", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("username", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("password_hash", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("nickname", sa.TEXT(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("enabled", sa.BOOLEAN(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_super", sa.BOOLEAN(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="admin_accounts_pkey"),
        sa.UniqueConstraint("username", name="admin_accounts_username_key"),
    )


def downgrade() -> None:
    op.drop_table("admin_accounts")
