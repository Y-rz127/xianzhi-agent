"""八字命盘结构化引擎（兼容门面）。

统一重导出各子域模块的公共符号，既有 import 无需改动；
新代码建议直接从子域模块导入。
"""
from app.domain.analysis_calc import (  # noqa: F401
    _branch_combinations,
    _branch_relations,
    _build_domain_analysis,
    _build_wuxing_analysis,
    _classify_strength,
    _controller_of,
    _count_ten_gods,
    _detect_conging,
    _detect_special_pattern,
    _detect_zhuanwang,
    _producer_of,
    _round_counts,
    _stem_relations,
)
from app.domain.chart_builder import (  # noqa: F401
    _build_dayun,
    _build_liunian,
    _find_dayun_for_year,
    _ganzhi_detail,
    _gender_label,
    _pillar,
    _ten_god,
    _zizuo,
    build_bazi_chart,
    chart_to_api_dict,
    parse_birth,
    parse_gender,
)
from app.domain.chart_format import (  # noqa: F401
    extract_bazi_brief,
    find_birth_dates_from_pillars,
    format_analysis_text,
    format_chart_text,
    format_dayun_text,
    format_fact_context,
    format_liunian_text,
)
from app.domain.models import (  # noqa: F401
    BaziChart,
    BirthInfo,
    DayunItem,
    DomainAnalysis,
    LiunianItem,
    Pillar,
    WuxingAnalysis,
)
from app.domain.shensha_calc import _compute_shensha, _zhi_to_month_index  # noqa: F401
from app.domain.tables import *  # noqa: F401,F403
from app.domain.tables import (  # noqa: F401  (私有表显式重导出，* 不覆盖下划线开头)
    _GAN_CHANGSHENG_ZHI,
    _YANG_GAN,
    _ZHI_SEQ,
)
