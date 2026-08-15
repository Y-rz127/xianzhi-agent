"""用户私有数据：建表与共享工具（惰性建表 / 错误埋点 / JSON 容错）。

R9 拆分自 user_data.py；user_data 门面重导出全部符号。"""
from __future__ import annotations

import json

from app.core.logger import log
from app.core.observability import record_error as _record_error  # 统一实现，消除跨模块重复定义
from app.memory.postgres_memory import _get_pool

_READY = False


def _ensure_tables():
    """惰性建表：首次调用时创建八字档案/命例收藏/塔罗记录/反馈四张表及索引，之后直接返回。"""
    global _READY
    if _READY:
        return
    try:
        _do_ensure_tables()
        _READY = True
        log.info("用户私有数据表已就绪")
    except Exception as e:
        # 建表失败 → 后续 CRUD 全部不可用，必须错误级可见；_READY 保持 False 下次重试
        log.error("用户私有数据表创建失败: {}", e)
        _record_error("user_data.ensure_tables")


def _do_ensure_tables():
    with _get_pool().connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bazi_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                relation TEXT DEFAULT '',
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                sect INT DEFAULT 2,
                yun_sect INT DEFAULT 1,
                chart_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_user ON bazi_profiles(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_favorites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, case_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fav_user ON chart_favorites(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tarot_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                spread TEXT NOT NULL,
                question TEXT DEFAULT '',
                cards JSONB,
                interpretation TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tarot_user ON tarot_records(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT,
                content TEXT NOT NULL,
                contact TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT,
                conversation_id TEXT DEFAULT '',
                question TEXT DEFAULT '',
                answer TEXT NOT NULL,
                rating TEXT NOT NULL,
                reason TEXT DEFAULT '',
                chart_snapshot JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_created ON answer_feedback(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_rating ON answer_feedback(rating)"
        )
        conn.execute(
            "ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE"
        )
        conn.execute(
            "ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed_by TEXT DEFAULT ''"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_answer_feedback_reviewed ON answer_feedback(reviewed)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL,
                chart_hash TEXT NOT NULL,
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                chart_data JSONB,
                common_topics TEXT[] DEFAULT '{}',
                style_preference TEXT DEFAULT '',
                feedback_stats JSONB DEFAULT '{}',
                interaction_count INT DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, chart_hash)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_profiles_user ON chart_profiles(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_profiles_hash ON chart_profiles(chart_hash)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_facts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chart_profile_id UUID REFERENCES chart_profiles(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                conversation_id TEXT DEFAULT '',
                question TEXT DEFAULT '',
                answer_snippet TEXT DEFAULT '',
                fact_type TEXT DEFAULT 'general',
                fact_summary TEXT DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'verified',
                reason TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_profile ON chart_facts(chart_profile_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_user ON chart_facts(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_facts_confidence ON chart_facts(confidence)"
        )
        # 命理库八字信息（Web 端新建命例）：cases 表（Bazi 结构）
        # 新增 bio/analysis/keypoints/domains 用于承载命例解读文案（替代已废弃的 markdown 种子文档）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                tags TEXT[] DEFAULT '{}',
                birth_time TEXT NOT NULL,
                gender TEXT NOT NULL,
                chart_data JSONB,
                bio TEXT DEFAULT '',
                analysis TEXT DEFAULT '',
                keypoints TEXT DEFAULT '',
                domains TEXT[] DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        # 对已经存在的 cases 表做在线迁移（新列不会破坏旧数据），必须在建索引前完成
        for col, col_type in [
            ("bio", "TEXT DEFAULT ''"),
            ("analysis", "TEXT DEFAULT ''"),
            ("keypoints", "TEXT DEFAULT ''"),
            ("domains", "TEXT[] DEFAULT '{}'"),
        ]:
            conn.execute(
                f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col} {col_type}"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_tags ON cases USING GIN (tags)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_domains ON cases USING GIN (domains)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at DESC)"
        )
        # 用户反馈转换的结构化案例库：chart_cases 表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_cases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT DEFAULT '',
                source TEXT DEFAULT '',
                question TEXT DEFAULT '',
                analysis TEXT NOT NULL,
                domains TEXT[] DEFAULT '{}',
                features JSONB DEFAULT '{}',
                rating INT DEFAULT 4,
                verified BOOLEAN DEFAULT TRUE,
                keywords TEXT[] DEFAULT '{}',
                promoted_by TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                reason TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_cases_domains ON chart_cases USING GIN (domains)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chart_cases_rating ON chart_cases(rating DESC)"
        )


def _safe_json(s: str):
    """安全解析 JSON 字符串，解析失败时返回空字典。"""
    try:
        return json.loads(s)
    except Exception:
        return {}


