"""app config kv

Revision ID: 3c1d8f5e92b0
Revises: 9f2b3c0a91d5
Create Date: 2026-09-01 14:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c1d8f5e92b0'
down_revision: Union[str, None] = '9f2b3c0a91d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('app_config',
    sa.Column('key', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('key', name='app_config_pkey')
    )


def downgrade() -> None:
    op.drop_table('app_config')