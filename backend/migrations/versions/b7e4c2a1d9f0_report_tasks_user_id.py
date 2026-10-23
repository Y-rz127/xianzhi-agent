"""report tasks user ownership

Revision ID: b7e4c2a1d9f0
Revises: 3c1d8f5e92b0
Create Date: 2026-10-23 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e4c2a1d9f0"
down_revision: Union[str, None] = "3c1d8f5e92b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("report_tasks", sa.Column("user_id", sa.TEXT(), nullable=True))
    op.create_index("idx_report_tasks_user_created", "report_tasks", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_report_tasks_user_created", table_name="report_tasks")
    op.drop_column("report_tasks", "user_id")
