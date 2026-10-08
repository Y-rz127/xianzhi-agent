"""report tasks

Revision ID: 9f2b3c0a91d5
Revises: fb0266ad5aaa
Create Date: 2026-09-01 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9f2b3c0a91d5'
down_revision: Union[str, None] = 'fb0266ad5aaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('report_tasks',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('kind', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('status', sa.TEXT(), server_default=sa.text("'pending'::text"), autoincrement=False, nullable=False),
    sa.Column('payload', postgresql.BYTEA(), autoincrement=False, nullable=True),
    sa.Column('error', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='report_tasks_pkey')
    )
    op.create_index('idx_report_tasks_status_created', 'report_tasks', [sa.literal_column('status'), sa.literal_column('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('idx_report_tasks_status_created', table_name='report_tasks')
    op.drop_table('report_tasks')