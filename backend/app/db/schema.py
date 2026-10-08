"""用户私有数据共享工具：惰性建表 / 错误埋点 / JSON 容错。"""

from __future__ import annotations

import json

from app.core.logger import log
from app.core.observability import record_error as _record_error  # 统一实现，消除跨模块重复定义
from app.db.pool import get_pool

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
        # 建表失败会拖垮后续 CRUD，必须错误级可见；_READY 保持 False 下次重试
        log.error("用户私有数据表创建失败: {}", e)
        _record_error("schema.ensure_tables")


def _do_ensure_tables():
    with get_pool().connection() as conn:
        _ensure_profile_tables(conn)
        _ensure_interaction_tables(conn)
        _ensure_case_tables(conn)
        _ensure_kline_tables(conn)
        _ensure_kline_event_tables(conn)


def _ensure_profile_tables(conn) -> None:
    """八字档案 / 命盘画像 / 画像事实三表（chart_facts 外键依赖 chart_profiles）。"""
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON bazi_profiles(user_id)")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_profiles_user ON chart_profiles(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_profiles_hash ON chart_profiles(chart_hash)")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_facts_profile ON chart_facts(chart_profile_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_facts_user ON chart_facts(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_facts_confidence ON chart_facts(confidence)")


def _ensure_interaction_tables(conn) -> None:
    """收藏 / 解读记录 / 反馈 / 回答反馈四表。"""
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fav_user ON chart_favorites(user_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_interpretation_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            source TEXT NOT NULL,
            question TEXT DEFAULT '',
            payload JSONB,
            interpretation TEXT DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_interpretation_user ON ai_interpretation_records(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_interpretation_source ON ai_interpretation_records(source)"
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_answer_feedback_rating ON answer_feedback(rating)")
    conn.execute("ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed BOOLEAN DEFAULT FALSE")
    conn.execute("ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS reviewed_by TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_answer_feedback_reviewed ON answer_feedback(reviewed)")
    conn.execute("ALTER TABLE answer_feedback ADD COLUMN IF NOT EXISTS case_id TEXT DEFAULT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_answer_feedback_case ON answer_feedback(case_id)")


def _ensure_case_tables(conn) -> None:
    """命理库八字命例两表：cases（解读文案库）+ chart_cases（结构化命例）。"""
    # cases：bio/analysis/keypoints/domains 承载解读文案，替代已废弃的 markdown 种子文档
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
    # 对旧库中已存在的 cases 表做在线迁移（新增列不破坏旧数据），须在建索引前完成
    for col, col_type in [
        ("bio", "TEXT DEFAULT ''"),
        ("analysis", "TEXT DEFAULT ''"),
        ("keypoints", "TEXT DEFAULT ''"),
        ("domains", "TEXT[] DEFAULT '{}'"),
    ]:
        conn.execute(f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col} {col_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_tags ON cases USING GIN (tags)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_domains ON cases USING GIN (domains)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at DESC)")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_cases_domains ON chart_cases USING GIN (domains)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chart_cases_rating ON chart_cases(rating DESC)")


def _ensure_kline_tables(conn) -> None:
    """命理 K 线的用户反馈表（校准闭环的数据面）。

    为什么要单独一张表而不是复用 `answer_feedback`：K 线反馈的锚点是
    **(命盘, 维度, 年份)** 三元组，而不是"某次对话的某个回答"。
    混进 answer_feedback 会让"这条反馈针对哪一年的哪条线"无处安放。

    `chart_hash` 存的是 birth_time+gender 的指纹（与 `chart_store` 同一算法），
    而不是外键 —— K 线可以在没建过命盘画像的情况下用，硬挂外键会丢反馈。

    `anchor_year` 必须存：批注文案里含"当前大运"这类**随当下时间变化**的措辞，
    没有它，一年后再看这条反馈就对不上当时批的到底是哪一段。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kline_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chart_hash TEXT NOT NULL,
            birth_time TEXT DEFAULT '',
            gender TEXT DEFAULT '',
            dimension TEXT NOT NULL,
            scope TEXT NOT NULL,
            year INT,
            anchor_year INT,
            rating INT NOT NULL,
            accurate BOOLEAN,
            comment TEXT DEFAULT '',
            snapshot JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kline_feedback_chart ON kline_feedback(chart_hash, dimension)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_feedback_rating ON kline_feedback(rating DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_feedback_created ON kline_feedback(created_at DESC)")


def _ensure_kline_event_tables(conn) -> None:
    """真实事件标注表：回测的 ground truth（真相面）。

    与 `kline_feedback` 的分工
    -------------------------
    `kline_feedback` 是「用户觉得这条解读准不准」，是**主观评价**；
    `kline_events` 是「这一年实际发生了什么」，是**客观事实**。
    回测只能吃后者 —— 用主观评价回测等于让模型给自己打分。

    锚点是 **(命盘, 命理年, 领域)**：同一年可以既升职（事业吉）又生病（健康凶），
    故**不设** (chart_hash, ganzhi_year) 唯一约束，那是把两件独立的事挤成一件。
    重复录入由回测层的 `duplicateAnchors` 报警，而不是由数据库硬拦。

    `ganzhi_year` 存**命理年**（立春换岁），不是公历年：1-2 月的事件若按公历年存会
    整体错位一年。原始公历日期留在 `event_date` 里，便于人工复核与重算。
    纵使 `event_date` 缺失也可录（很多传记只记年），故允许它为空，但两者必须至少有一个。

    `birth_time` / `gender` / `sect` / `yun_sect` / `longitude` 全部落库（而非只存指纹）：
    回测必须**原样重建**预测时的那张盘，少一个参数就可能预测出另一条曲线。
    `chart_hash` 仍冗余存一份，用于按盘分组与计数（与 `chart_store._chart_hash` 同算法）。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kline_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chart_hash TEXT NOT NULL,
            birth_time TEXT NOT NULL,
            gender TEXT NOT NULL,
            sect INT DEFAULT 2,
            yun_sect INT DEFAULT 1,
            longitude DOUBLE PRECISION,
            ganzhi_year INT NOT NULL,
            event_date DATE,
            polarity INT NOT NULL,
            domain TEXT NOT NULL DEFAULT 'general',
            source TEXT DEFAULT '',
            note TEXT DEFAULT '',
            case_id TEXT DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kline_events_chart ON kline_events(chart_hash, ganzhi_year)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_events_year ON kline_events(ganzhi_year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_events_domain ON kline_events(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_events_created ON kline_events(created_at DESC)")
    _ensure_kline_pair_event_tables(conn)


def _ensure_kline_pair_event_tables(conn) -> None:
    """合盘关系事件表：**共振线**的 ground truth（"这两人某年如何"）。

    为什么单开一张表而不是给 `kline_events` 加两列
    ----------------------------------------------
    两件事的主键不同：单盘事件挂在一张盘上（一年可以既升职又生病，故锚点是盘+年+领域），
    关系事件挂在**一对人**上（同一年只有一种"我们俩顺不顺"，没有领域可切）。
    硬塞进一张表会让"哪些列该为空"变成隐性契约，回测读的时候还得按来源分叉。

    `pair_key` 是两侧 chart_hash **排序后**拼接的：关系是对称的（共振分交换甲乙逐字相同，
    `test_kline_resonance.py` 有这条不变量），排序后同一对只有一种键，
    不至于因为录入时谁在甲谁在乙而分成两组。

    `relation`（夫妻/亲子/同事…）只用于分组复盘，**不参与预测** —— 引擎对任何一对都算同一套
    四项，人伦关系是"这个分该怎么读"的解释框架，不是打分依据。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kline_pair_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pair_key TEXT NOT NULL,
            birth_time_a TEXT NOT NULL,
            gender_a TEXT NOT NULL,
            birth_time_b TEXT NOT NULL,
            gender_b TEXT NOT NULL,
            sect INT DEFAULT 2,
            yun_sect INT DEFAULT 1,
            longitude_a DOUBLE PRECISION,
            longitude_b DOUBLE PRECISION,
            ganzhi_year INT NOT NULL,
            event_date DATE,
            polarity INT NOT NULL,
            relation TEXT DEFAULT '',
            source TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kline_pair_events_pair "
        "ON kline_pair_events(pair_key, ganzhi_year)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_pair_events_year ON kline_pair_events(ganzhi_year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_pair_events_created ON kline_pair_events(created_at DESC)")


def _safe_json(s: str):
    """安全解析 JSON 字符串，解析失败时返回空字典。"""
    try:
        return json.loads(s)
    except Exception:
        return {}
