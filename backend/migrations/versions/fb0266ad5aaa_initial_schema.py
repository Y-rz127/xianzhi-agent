"""initial schema

Revision ID: fb0266ad5aaa
Revises:
Create Date: 2026-09-01 13:49:23.067260

基线迁移：冻结 2026-09 时的全部应用业务表结构（自启动建表逻辑的历史快照）。
langchain_pg_*（PGVector / ChatMessageHistory）由其运行时库自建，不在迁移内。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fb0266ad5aaa'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector 扩展：langchain_postgres 需要；应用层也要求（DEPLOY.md 已注明）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('answer_feedback',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('conversation_id', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('question', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('answer', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('rating', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('reason', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('chart_snapshot', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('reviewed', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=True),
    sa.Column('reviewed_by', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('case_id', sa.TEXT(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='answer_feedback_pkey')
    )
    op.create_index('idx_answer_feedback_reviewed', 'answer_feedback', ['reviewed'], unique=False)
    op.create_index('idx_answer_feedback_rating', 'answer_feedback', ['rating'], unique=False)
    op.create_index('idx_answer_feedback_created', 'answer_feedback', [sa.literal_column('created_at DESC')], unique=False)
    op.create_index('idx_answer_feedback_case', 'answer_feedback', ['case_id'], unique=False)

    op.create_table('chart_favorites',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('case_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='chart_favorites_pkey'),
    sa.UniqueConstraint('user_id', 'case_id', name='chart_favorites_user_id_case_id_key')
    )
    op.create_index('idx_fav_user', 'chart_favorites', ['user_id'], unique=False)

    op.create_table('chart_profiles',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('chart_hash', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('birth_time', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('gender', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('chart_data', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('common_topics', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("'{}'::text[]"), autoincrement=False, nullable=True),
    sa.Column('style_preference', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('feedback_stats', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), autoincrement=False, nullable=True),
    sa.Column('interaction_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='chart_profiles_pkey'),
    sa.UniqueConstraint('user_id', 'chart_hash', name='chart_profiles_user_id_chart_hash_key')
    )
    op.create_index('idx_chart_profiles_user', 'chart_profiles', ['user_id'], unique=False)
    op.create_index('idx_chart_profiles_hash', 'chart_profiles', ['chart_hash'], unique=False)

    op.create_table('message_store',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('message', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='message_store_pkey')
    )
    op.create_index('idx_message_store_session_id', 'message_store', ['session_id'], unique=False)
    op.create_index('idx_message_store_session_created', 'message_store', ['session_id', sa.literal_column('created_at DESC')], unique=False)

    op.create_table('rag_fingerprint',
    sa.Column('id', sa.SMALLINT(), server_default=sa.text('1'), autoincrement=False, nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='rag_fingerprint_pkey')
    )

    op.create_table('cases',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('tags', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("'{}'::text[]"), autoincrement=False, nullable=True),
    sa.Column('birth_time', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('gender', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('chart_data', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('bio', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('analysis', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('keypoints', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('domains', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("'{}'::text[]"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='cases_pkey')
    )
    op.create_index('idx_cases_updated', 'cases', [sa.literal_column('updated_at DESC')], unique=False)
    op.create_index('idx_cases_tags', 'cases', ['tags'], unique=False, postgresql_using='gin')
    op.create_index('idx_cases_domains', 'cases', ['domains'], unique=False, postgresql_using='gin')

    op.create_table('bazi_profiles',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('name', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('relation', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('birth_time', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('gender', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('sect', sa.INTEGER(), server_default=sa.text('2'), autoincrement=False, nullable=True),
    sa.Column('yun_sect', sa.INTEGER(), server_default=sa.text('1'), autoincrement=False, nullable=True),
    sa.Column('chart_data', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='bazi_profiles_pkey')
    )
    op.create_index('idx_profiles_user', 'bazi_profiles', ['user_id'], unique=False)

    op.create_table('tarot_records',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('spread', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('question', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('cards', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('interpretation', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='tarot_records_pkey')
    )
    op.create_index('idx_tarot_user', 'tarot_records', ['user_id'], unique=False)

    op.create_table('chart_cases',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('title', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('source', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('question', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('analysis', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('domains', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("'{}'::text[]"), autoincrement=False, nullable=True),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), autoincrement=False, nullable=True),
    sa.Column('rating', sa.INTEGER(), server_default=sa.text('4'), autoincrement=False, nullable=True),
    sa.Column('verified', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=True),
    sa.Column('keywords', postgresql.ARRAY(sa.TEXT()), server_default=sa.text("'{}'::text[]"), autoincrement=False, nullable=True),
    sa.Column('promoted_by', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('reason', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='chart_cases_pkey')
    )
    op.create_index('idx_chart_cases_rating', 'chart_cases', [sa.literal_column('rating DESC')], unique=False)
    op.create_index('idx_chart_cases_domains', 'chart_cases', ['domains'], unique=False, postgresql_using='gin')

    op.create_table('feedback',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('content', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('contact', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='feedback_pkey')
    )

    op.create_table('session_metadata',
    sa.Column('session_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('conversation_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('module', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), autoincrement=False, nullable=True),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), autoincrement=False, nullable=True),
    sa.Column('summary', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('last_summary_msg_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('session_id', name='session_metadata_pkey')
    )

    op.create_table('chart_facts',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('chart_profile_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('conversation_id', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('question', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('answer_snippet', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('fact_type', sa.TEXT(), server_default=sa.text("'general'::text"), autoincrement=False, nullable=True),
    sa.Column('fact_summary', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('confidence', sa.TEXT(), server_default=sa.text("'verified'::text"), autoincrement=False, nullable=False),
    sa.Column('reason', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['chart_profile_id'], ['chart_profiles.id'], name='chart_facts_chart_profile_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='chart_facts_pkey')
    )
    op.create_index('idx_chart_facts_user', 'chart_facts', ['user_id'], unique=False)
    op.create_index('idx_chart_facts_profile', 'chart_facts', ['chart_profile_id'], unique=False)
    op.create_index('idx_chart_facts_confidence', 'chart_facts', ['confidence'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False),
    sa.Column('nickname', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('password_hash', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('password_salt', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('avatar', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=True),
    sa.Column('wx_openid', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('token', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('token_created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('last_active_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='users_pkey'),
    sa.UniqueConstraint('nickname', name='users_nickname_key'),
    sa.UniqueConstraint('wx_openid', name='users_wx_openid_key')
    )
    op.create_index('idx_users_wx_openid', 'users', ['wx_openid'], unique=False)
    op.create_index('idx_users_token', 'users', ['token'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_users_token', table_name='users')
    op.drop_index('idx_users_wx_openid', table_name='users')
    op.drop_table('users')
    op.drop_index('idx_chart_facts_confidence', table_name='chart_facts')
    op.drop_index('idx_chart_facts_profile', table_name='chart_facts')
    op.drop_index('idx_chart_facts_user', table_name='chart_facts')
    op.drop_table('chart_facts')
    op.drop_table('session_metadata')
    op.drop_table('feedback')
    op.drop_index('idx_chart_cases_domains', table_name='chart_cases', postgresql_using='gin')
    op.drop_index('idx_chart_cases_rating', table_name='chart_cases')
    op.drop_table('chart_cases')
    op.drop_index('idx_tarot_user', table_name='tarot_records')
    op.drop_table('tarot_records')
    op.drop_index('idx_profiles_user', table_name='bazi_profiles')
    op.drop_table('bazi_profiles')
    op.drop_index('idx_cases_domains', table_name='cases', postgresql_using='gin')
    op.drop_index('idx_cases_tags', table_name='cases', postgresql_using='gin')
    op.drop_index('idx_cases_updated', table_name='cases')
    op.drop_table('cases')
    op.drop_table('rag_fingerprint')
    op.drop_index('idx_message_store_session_created', table_name='message_store')
    op.drop_index('idx_message_store_session_id', table_name='message_store')
    op.drop_table('message_store')
    op.drop_index('idx_chart_profiles_hash', table_name='chart_profiles')
    op.drop_index('idx_chart_profiles_user', table_name='chart_profiles')
    op.drop_table('chart_profiles')
    op.drop_index('idx_fav_user', table_name='chart_favorites')
    op.drop_table('chart_favorites')
    op.drop_index('idx_answer_feedback_case', table_name='answer_feedback')
    op.drop_index('idx_answer_feedback_created', table_name='answer_feedback')
    op.drop_index('idx_answer_feedback_rating', table_name='answer_feedback')
    op.drop_index('idx_answer_feedback_reviewed', table_name='answer_feedback')
    op.drop_table('answer_feedback')