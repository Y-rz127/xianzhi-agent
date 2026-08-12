"""八字命盘结构化引擎（基于 lunar-python 纯算法）。

对外暴露 build_bazi_chart / parse_birth / parse_gender / chart_to_api_dict /
format_* 等函数，产出 BaziChart 这一「命盘事实来源」，供 API、图表案例与
Agent 上下文共用。公共工具函数仍返回可读文本，但结构化数据以本模块为准。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field
from typing import Any

from lunar_python import Lunar, Solar


GAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

ZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
    "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
    "戌": "土", "亥": "水",
}

GZ_WUXING = {**GAN_WUXING, **ZHI_WUXING}

HIDDEN_STEMS = {
    "子": (("癸", 1.0),),
    "丑": (("己", 0.6), ("癸", 0.3), ("辛", 0.1)),
    "寅": (("甲", 0.6), ("丙", 0.3), ("戊", 0.1)),
    "卯": (("乙", 1.0),),
    "辰": (("戊", 0.6), ("乙", 0.3), ("癸", 0.1)),
    "巳": (("丙", 0.6), ("戊", 0.3), ("庚", 0.1)),
    "午": (("丁", 0.7), ("己", 0.3)),
    "未": (("己", 0.6), ("丁", 0.3), ("乙", 0.1)),
    "申": (("庚", 0.6), ("壬", 0.3), ("戊", 0.1)),
    "酉": (("辛", 1.0),),
    "戌": (("戊", 0.6), ("辛", 0.3), ("丁", 0.1)),
    "亥": (("壬", 0.7), ("甲", 0.3)),
}

GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   #相生
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}    #相克
WUXING_ORDER = ("金", "木", "水", "火", "土")      # 五行

# 十二长生（星运/自坐共用顺序）
CHANG_SHENG = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")
# 各天干长生所在地支（阳干顺行、阴干逆行）
_GAN_CHANGSHENG_ZHI = {
    "甲": "亥", "丙": "寅", "戊": "寅", "庚": "巳", "壬": "申",
    "乙": "午", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯",
}
_YANG_GAN = {"甲", "丙", "戊", "庚", "壬"}
_ZHI_SEQ = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

LIU_HE = {
    frozenset(("子", "丑")): "子丑合土",
    frozenset(("寅", "亥")): "寅亥合木",
    frozenset(("卯", "戌")): "卯戌合火",
    frozenset(("辰", "酉")): "辰酉合金",
    frozenset(("巳", "申")): "巳申合水",
    frozenset(("午", "未")): "午未合土",
}
# 天干五合（合化后的五行）
GAN_HE = {
    frozenset(("甲", "己")): "甲己合土",
    frozenset(("乙", "庚")): "乙庚合金",
    frozenset(("丙", "辛")): "丙辛合水",
    frozenset(("丁", "壬")): "丁壬合木",
    frozenset(("戊", "癸")): "戊癸合火",
}
# 天干相冲（方位对冲）
GAN_CHONG = {
    frozenset(("甲", "庚")): "甲庚冲",
    frozenset(("乙", "辛")): "乙辛冲",
    frozenset(("丙", "壬")): "丙壬冲",
    frozenset(("丁", "癸")): "丁癸冲",
}
LIU_CHONG = {
    frozenset(("子", "午")): "子午冲",
    frozenset(("丑", "未")): "丑未冲",
    frozenset(("寅", "申")): "寅申冲",
    frozenset(("卯", "酉")): "卯酉冲",
    frozenset(("辰", "戌")): "辰戌冲",
    frozenset(("巳", "亥")): "巳亥冲",
}
# 地支六冲（支 → 对冲支），供元辰 / 飞刃等按支取对冲
CHONG_ZHI = {
    "子": "午", "午": "子", "丑": "未", "未": "丑",
    "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
}
LIU_HAI = {
    frozenset(("子", "未")): "子未害",
    frozenset(("丑", "午")): "丑午害",
    frozenset(("寅", "巳")): "寅巳害",
    frozenset(("卯", "辰")): "卯辰害",
    frozenset(("申", "亥")): "申亥害",
    frozenset(("酉", "戌")): "酉戌害",
}
SAN_XING = {
    frozenset(("寅", "巳", "申")): "寅巳申持势三刑",
    frozenset(("丑", "未", "戌")): "丑未戌无恩三刑",
    frozenset(("子","卯")):"子卯无礼刑"
}
SELF_XING = {"辰": "辰辰自刑", "午": "午午自刑", "酉": "酉酉自刑", "亥": "亥亥自刑"}
# 地支三合局（长生-帝旺-墓库，三支全会则成局）
SAN_HE = {
    frozenset(("申", "子", "辰")): "申子辰合水局",
    frozenset(("亥", "卯", "未")): "亥卯未合木局",
    frozenset(("寅", "午", "戌")): "寅午戌合火局",
    frozenset(("巳", "酉", "丑")): "巳酉丑合金局",
}
# 地支三会（三方会聚一方旺气）
SAN_HUI = {
    frozenset(("寅", "卯", "辰")): "寅卯辰会东方木",
    frozenset(("巳", "午", "未")): "巳午未会南方火",
    frozenset(("申", "酉", "戌")): "申酉戌会西方金",
    frozenset(("亥", "子", "丑")): "亥子丑会北方水",
}
# 地支六破（相破，破中取损）
LIU_PO = {
    frozenset(("子", "酉")): "子酉破",
    frozenset(("卯", "午")): "卯午破",
    frozenset(("辰", "丑")): "辰丑破",
    frozenset(("巳", "申")): "巳申破",
    frozenset(("寅", "亥")): "寅亥破",
    frozenset(("未", "戌")): "未戌破",
}

# ===== 神煞查表 =====
# 天乙贵人（以日干查）
TIAN_YI = {
    "甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
    "乙": ("子", "申"), "己": ("子", "申"),
    "丙": ("亥", "酉"), "丁": ("亥", "酉"),
    "壬": ("卯", "巳"), "癸": ("卯", "巳"),
    "辛": ("午", "寅"),
}
# 太极贵人（以日干查）
TAI_JI = {
    "甲": ("子", "午"), "乙": ("子", "午"),
    "丙": ("酉", "卯"), "丁": ("酉", "卯"),
    "戊": ("辰", "戌", "丑", "未"), "己": ("辰", "戌", "丑", "未"),
    "庚": ("寅", "亥"), "辛": ("寅", "亥"),
    "壬": ("巳", "申"), "癸": ("巳", "申"),
}
# 文昌贵人（以日干查）
WEN_CHANG = {
    "甲": "巳", "乙": "午", "丙": "申", "丁": "酉",
    "戊": "申", "己": "酉", "庚": "亥", "辛": "子",
    "壬": "寅", "癸": "卯",
}
# 羊刃（以日干查，帝旺地支）
YANG_REN = {
    "甲": "卯", "乙": "寅",  # 乙羊刃有争议，多数取寅
    "丙": "午", "丁": "巳",
    "戊": "午", "己": "巳",
    "庚": "酉", "辛": "申",
    "壬": "子", "癸": "亥",
}
# 华盖（以年支/日支查，三合局墓库）
HUA_GAI = {
    "寅": "戌", "午": "戌", "戌": "戌",
    "巳": "丑", "酉": "丑", "丑": "丑",
    "申": "辰", "子": "辰", "辰": "辰",
    "亥": "未", "卯": "未", "未": "未",
}
# 桃花（以年支/日支查，四正地支，又名咸池）
TAO_HUA = {
    "寅": "卯", "午": "卯", "戌": "卯",
    "巳": "午", "酉": "午", "丑": "午",
    "申": "酉", "子": "酉", "辰": "酉",
    "亥": "子", "卯": "子", "未": "子",
}
# 驿马（以年支/日支查，三合局长生对冲）
YI_MA = {
    "寅": "申", "午": "申", "戌": "申",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "申": "寅", "子": "寅", "辰": "寅",
    "亥": "巳", "卯": "巳", "未": "巳",
}
# 将星（以年支/日支查，三合局帝旺）
JIANG_XING = {
    "寅": "午", "午": "午", "戌": "午",
    "巳": "酉", "酉": "酉", "丑": "酉",
    "申": "子", "子": "子", "辰": "子",
    "亥": "卯", "卯": "卯", "未": "卯",
}
# 禄神（以日干查，临官地支）
LU_SHEN = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午",
    "戊": "巳", "己": "午", "庚": "申", "辛": "酉",
    "壬": "亥", "癸": "子",
}
# 天德贵人（以月支查，歌诀：正丁二申三壬，四辛五亥六甲，
#         七癸八寅九丙，十乙十一己十二庚）
# 注意：天德可能是天干也可能是地支，需分别检测
TIAN_DE_MONTH = {
    1: ("丁",),     # 正月(寅月)：见丁
    2: ("申",),     # 二月(卯月)：见申（地支！）
    3: ("壬",),     # 三月(辰月)：见壬
    4: ("辛",),     # 四月(巳月)：见辛
    5: ("亥",),     # 五月(午月)：见亥（地支！）
    6: ("甲",),     # 六月(未月)：见甲
    7: ("癸",),     # 七月(申月)：见癸
    8: ("寅",),     # 八月(酉月)：见寅（地支！）
    9: ("丙",),     # 九月(戌月)：见丙
    10: ("乙",),    # 十月(亥月)：见乙
    11: ("巳",),    # 十一月(子月)：见巳（地支！）
    12: ("庚",),    # 十二月(丑月)：见庚
}
TIAN_DE_IS_BRANCH = {2, 5, 8, 11}  # 这几个月的天德是地支而非天干
# 月德贵人（以月支查，歌诀：寅午戌月丙上辉，亥卯未月甲干栖，
#         申子辰月壬干是，巳酉丑月庚干奇）
YUE_DE_MONTH = {
    1: ("丙",),   2: ("甲",),   3: ("壬",),   4: ("庚",),
    5: ("丙",),   6: ("甲",),   7: ("壬",),   8: ("庚",),
    9: ("丙",),   10: ("甲",), 11: ("壬",), 12: ("庚",),
}
# 十恶大败（日柱干支组合，共10组）
# 来源：华易网《四柱神煞查法对照表》
SHI_E_DA_BAI = (
    "甲辰",
    "乙巳",   # ← 原：乙亥（错）
    "丙申",
    "丁亥",
    "戊戌",   # ← 原：戊午（错）
    "己丑",   # ← 原：己巳（错）
    "庚辰",   # ← 原：庚午（错）
    "辛巳",
    "壬申",
    "癸亥",
)
# 学堂（以年柱纳音五行查，禄命法长生位；对齐 07_神煞初探.md）
XUE_TANG = {"金": "巳", "木": "亥", "水": "申", "土": "申", "火": "寅"}
# 词馆（以年柱纳音五行查，禄命法临官位；对齐 07_神煞初探.md）
CI_GUAN = {"金": "申", "木": "寅", "水": "亥", "土": "亥", "火": "巳"}
# 正学堂 / 正词馆（年柱纳音 + 干支完全匹配）
ZHENG_XUE_TANG = {"金": "辛巳", "木": "己亥", "水": "甲申", "土": "戊申", "火": "丙寅"}
ZHENG_CI_GUAN = {"金": "壬申", "木": "庚寅", "水": "癸亥", "土": "丁亥", "火": "乙巳"}
# 金舆（以日干查，禄神顺推一位）
JIN_YU = {
    "甲": "辰", "乙": "巳", "丙": "未", "丁": "申",
    "戊": "未", "己": "申", "庚": "戌", "辛": "亥",
    "壬": "丑", "癸": "寅",
}
# 福星贵人（以年/日干查地支，古诀：凡甲、丙两干见寅或子，
# 乙、癸两干见卯或丑，戊干见申，己干见未，丁干见亥，庚干见午，
# 辛干见巳，壬干见辰是也）
FU_XING = {
    "甲": ("寅", "子"), "丙": ("寅", "子"),
    "乙": ("卯", "丑"), "癸": ("卯", "丑"),
    "戊": ("申",),
    "己": ("未",),
    "丁": ("亥",),
    "庚": ("午",),
    "辛": ("巳",),
    "壬": ("辰",),
}
# 劫煞（三合局绝位，以年支/日支查）
# 歌诀：申子辰见巳，寅午戌见亥，亥卯未见申，巳酉丑见寅
# 来源：算卦吧《八字入门之四柱神煞》
JIE_SHA = {
    # 水局(申子辰)：木绝于巳
    "申": "巳", "子": "巳", "辰": "巳",
    # 火局(寅午戌)：火绝于亥
    "寅": "亥", "午": "亥", "戌": "亥",
    # 木局(亥卯未)：水绝于申
    "亥": "申", "卯": "申", "未": "申",
    # 金局(巳酉丑)：土绝于寅
    "巳": "寅", "酉": "寅", "丑": "寅",
}
# 灾煞（将星受冲位，以年支查）
# 将星=三合局中支(四正)，灾煞=将星之冲
ZAI_SHA = {
    # 水(申子辰)→将星子→冲午
    "申": "午", "子": "午", "辰": "午",
    # 火(寅午戌)→将星午→冲子
    "寅": "子", "午": "子", "戌": "子",
    # 木(亥卯未)→将星卯→冲酉
    "亥": "酉", "卯": "酉", "未": "酉",
    # 金(巳酉丑)→将星酉→冲卯
    "巳": "卯", "酉": "卯", "丑": "卯",
}
# 亡神（三合局临官位，以年支/日支查）
# 歌诀：寅午戌见巳，亥卯未见寅，巳酉丑见申，申子辰见亥
WANG_SHEN = {
    # 火局(寅午戌)：火临官在巳
    "寅": "巳", "午": "巳", "戌": "巳",
    # 木局(亥卯未)：木临官在寅
    "亥": "寅", "卯": "寅", "未": "寅",
    # 金局(巳酉丑)：金临官在申
    "巳": "申", "酉": "申", "丑": "申",
    # 水局(申子辰)：水临官在亥
    "申": "亥", "子": "亥", "辰": "亥",
}
# 吊客（以年支查，岁后二辰 / 丧门岁前二辰的对称位，二者非对宫关系）
DIAO_KE = {
    "子": "戌", "丑": "亥", "寅": "子", "卯": "丑",
    "辰": "寅", "巳": "卯", "午": "辰", "未": "巳",
    "申": "午", "酉": "未", "戌": "申", "亥": "酉",
}
# 丧门（以年支查，岁前二辰 / 与吊客相差四辰为对称关系，非对宫）
SANG_MEN = {
    "子": "寅", "丑": "卯", "寅": "辰", "卯": "巳",
    "辰": "午", "巳": "未", "午": "申", "未": "酉",
    "申": "戌", "酉": "亥", "戌": "子", "亥": "丑",
}
# 病符（岁后一辰，以年支查）
BING_FU = {
    "子": "亥", "丑": "子", "寅": "丑", "卯": "寅",
    "辰": "卯", "巳": "辰", "午": "巳", "未": "午",
    "申": "未", "酉": "申", "戌": "酉", "亥": "戌",
}
# 天医（以月支查，对齐 07_神煞初探.md：正月丑、二月寅…十二月子）
TIAN_YI_MED = {
    "寅": "丑", "卯": "寅", "辰": "卯", "巳": "辰", "午": "巳",
    "未": "午", "申": "未", "酉": "申", "戌": "酉", "亥": "戌",
    "子": "亥", "丑": "子",
}
# 红鸾（以年支查，年支逆推：从卯起子逆数）
# 标准表：子→卯,丑→寅,寅→丑,卯→子,辰→亥,巳→戌,午→酉,未→申,申→未,酉→午,戌→巳,亥→辰
# 注意：红鸾与桃花（咸池）是不同神煞，不可混用同一张表。
HONG_LUAN = {
    "亥": "辰", "卯": "子", "未": "申",           # 亥卯未
    "寅": "丑", "午": "酉", "戌": "巳",           # 寅午戌
    "申": "未", "子": "卯", "辰": "亥",           # 申子辰
    "巳": "戌", "酉": "午", "丑": "寅",           # 巳酉丑
}
# 天喜（红鸾对冲位，以年支查）
TIAN_XI = {
    "亥": "戌", "卯": "午", "未": "寅",           # 亥卯未（红鸾对宫）
    "寅": "未", "午": "卯", "戌": "亥",           # 寅午戌
    "申": "丑", "子": "酉", "辰": "巳",           # 申子辰
    "巳": "辰", "酉": "子", "丑": "申",           # 巳酉丑
}
# 孤辰寡宿（以年支查余三支）
# 古诀：亥子丑人见寅为孤，见戌为寡；寅卯辰人见巳为孤，见丑为寡；
#       巳午未人见申为孤，见辰为寡；申酉戌人见亥为孤，见未为寡。
GU_CHEN = {
    "寅": "巳", "卯": "巳", "辰": "巳",           # 寅卯辰年 → 巳
    "巳": "申", "午": "申", "未": "申",            # 巳午未年 → 申
    "申": "亥", "酉": "亥", "戌": "亥",            # 申酉戌年 → 亥
    "亥": "寅", "子": "寅", "丑": "寅",            # 亥子丑年 → 寅
}
GUA_SU = {
    "寅": "丑", "卯": "丑", "辰": "丑",           # 寅卯辰年 → 丑
    "巳": "辰", "午": "辰", "未": "辰",            # 巳午未年 → 辰
    "申": "未", "酉": "未", "戌": "未",            # 申酉戌年 → 未
    "亥": "戌", "子": "戌", "丑": "戌",            # 亥子丑年 → 戌
}
# 地支顺序（用于顺推/逆推、对冲等）
BRANCH_ORDER = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
SEASON_OF_BRANCH = {  # 月支对应季节
    "寅": "春", "卯": "春", "辰": "春",
    "巳": "夏", "午": "夏", "未": "夏",
    "申": "秋", "酉": "秋", "戌": "秋",
    "亥": "冬", "子": "冬", "丑": "冬",
}
# 国印贵人（以年/日干查四支）
GUO_YIN = {
    "甲": "戌", "乙": "亥", "丙": "丑", "丁": "寅",
    "戊": "丑", "己": "寅", "庚": "辰", "辛": "巳",
    "壬": "未", "癸": "申",
}
# 德秀贵人（以月令查天干）：德干集合 / 秀干集合
DE_XIU = {
    "寅": ({"丙", "丁"}, {"戊", "癸"}), "午": ({"丙", "丁"}, {"戊", "癸"}), "戌": ({"丙", "丁"}, {"戊", "癸"}),
    "申": ({"壬", "癸", "戊", "己"}, {"丙", "辛", "甲", "己"}), "子": ({"壬", "癸", "戊", "己"}, {"丙", "辛", "甲", "己"}), "辰": ({"壬", "癸", "戊", "己"}, {"丙", "辛", "甲", "己"}),
    "巳": ({"庚", "辛"}, {"乙", "庚"}), "酉": ({"庚", "辛"}, {"乙", "庚"}), "丑": ({"庚", "辛"}, {"乙", "庚"}),
    "亥": ({"甲", "乙"}, {"丁", "壬"}), "卯": ({"甲", "乙"}, {"丁", "壬"}), "未": ({"甲", "乙"}, {"丁", "壬"}),
}
# 月德合（以月支查天干，月德之合干）
YUE_DE_HE = {
    "寅": "辛", "午": "辛", "戌": "辛",
    "申": "丁", "子": "丁", "辰": "丁",
    "巳": "乙", "酉": "乙", "丑": "乙",
    "亥": "己", "卯": "己", "未": "己",
}
# 天德合（以月支查天干，天德之五合/六合干）
TIAN_DE_HE = {
    "寅": "壬", "卯": "巳", "辰": "丁", "巳": "丙", "午": "寅", "未": "己",
    "申": "戊", "酉": "亥", "戌": "辛", "亥": "庚", "子": "申", "丑": "乙",
}
# 三奇贵人（天干相连且须含日干）
SAN_QI = (("甲", "戊", "庚"), ("乙", "丙", "丁"), ("壬", "癸", "辛"))
# 天赦日（按出生月支所属季节查日柱）
TIAN_SHE = {"春": "戊寅", "夏": "甲午", "秋": "戊申", "冬": "甲子"}
# 六秀日（专查日柱）
LIU_XIU = {"丙午", "丁未", "戊子", "戊午", "己丑", "己未"}
# 天厨贵人（以年/日干查四支；= 食神建禄：X 干食神是 Y，则 Y 禄地支即 X 之天厨）
# 古诀"甲巳乙午丙巳丁午，戊申己酉庚亥辛子，壬寅癸卯"
TIAN_CHU = {
    "甲": "巳", "乙": "午", "丙": "巳", "丁": "午",
    "戊": "申", "己": "酉", "庚": "亥", "辛": "子",
    "壬": "寅", "癸": "卯",
}
# 拱禄（日时柱配合：日支、时支拱夹日干禄位）
GONG_LU = (
    ("亥", "丑", "子"), ("丑", "亥", "子"),
    ("巳", "未", "午"), ("未", "巳", "午"),
    ("辰", "午", "巳"),
)
# 十灵日（专查日柱）
SHI_LING = {"甲辰", "乙亥", "丙辰", "丁酉", "戊午", "庚戌", "庚寅", "辛亥", "壬寅", "癸未"}
# 天转日/地转日（以月支查日柱，二者同表）
TIAN_DI_ZHUAN = {
    "春": ("乙卯", "辛卯"), "夏": ("丙午", "戊午"),
    "秋": ("辛酉", "癸酉"), "冬": ("壬子", "丙子"),
}
# 魁罡（专查日柱）
KUI_GANG = {"庚辰", "壬辰", "戊戌", "庚戌"}
# 金神（专查日/时柱）
JIN_SHEN = {"乙丑", "己巳", "癸酉"}
# 八专日（专查日柱）
BA_ZHUAN = {"甲寅", "乙卯", "丁未", "戊戌", "己未", "庚申", "辛酉", "癸丑"}
# 血刃（以月支查四柱地支）
XUE_REN = {
    "寅": "丑", "卯": "未", "辰": "寅", "巳": "申", "午": "卯",
    "未": "酉", "申": "辰", "酉": "戌", "戌": "巳", "亥": "亥",
    "子": "午", "丑": "子",
}
# 披麻（以年支查其余三支）
PI_MA = {
    "子": "酉", "丑": "戌", "寅": "亥", "卯": "子", "辰": "丑",
    "巳": "寅", "午": "卯", "未": "辰", "申": "巳", "酉": "午",
    "戌": "未", "亥": "申",
}
# 天罗地网（戌亥为天罗，辰巳为地网）
TIAN_LUO = ("戌", "亥")
DI_WANG = ("辰", "巳")
# 九丑日（专查日柱）
JIU_CHOU = {"丁酉", "戊子", "戊午", "己卯", "己酉", "辛卯", "辛酉", "壬子", "壬午"}
# 四废日（按出生季节查日柱）
SI_FEI = {
    "春": ("庚申", "辛酉"), "夏": ("壬子", "癸亥"),
    "秋": ("甲寅", "乙卯"), "冬": ("丙午", "丁巳"),
}
# 阴差阳错（专查日柱）
YIN_CHA_YANG_CUO = {"丙子", "丙午", "丁丑", "丁未", "戊寅", "戊申",
                     "辛卯", "辛酉", "壬辰", "壬戌", "癸巳", "癸亥"}
# 孤鸾煞（专查日柱）
GU_LUAN = {"甲寅", "乙巳", "丙午", "丁巳", "戊午", "戊申", "辛亥", "壬子"}
# 流霞（以日干查四支）
LIU_XIA = {
    "甲": "酉", "乙": "戌", "丙": "未", "丁": "申", "戊": "巳",
    "己": "午", "庚": "辰", "辛": "卯", "壬": "亥", "癸": "寅",
}
# 红艳煞（以日干查四支）
HONG_YAN = {
    "甲": "午", "乙": "午", "丙": "寅", "丁": "未", "戊": "辰",
    "己": "辰", "庚": "戌", "辛": "酉", "壬": "子", "癸": "申",
}

SEASON_NOTES = {
    "寅": "春初木旺，重在疏土培木，兼看火来通明。",
    "卯": "仲春木旺，木气纯粹，宜看金土是否成器。",
    "辰": "季春湿土，木余水藏，需分清湿土与木气。",
    "巳": "初夏火旺，燥热渐起，喜水调候、金水相济。",
    "午": "仲夏火极，最怕燥烈失衡，调候优先看水。",
    "未": "季夏燥土，火土偏重时需金水润局。",
    "申": "初秋金旺，金气肃杀，宜看火炼与水润。",
    "酉": "仲秋金旺，金清则贵，过寒则需火暖。",
    "戌": "季秋燥土，火库土燥，喜水润燥。",
    "亥": "初冬水旺，寒气渐重，喜火暖局、土来制水。",
    "子": "仲冬水极，寒湿明显，调候首看火。",
    "丑": "季冬寒土，湿寒并见，喜火温土。",
}


@dataclass(frozen=True)
class BirthInfo:
    """排盘基础信息（公历/农历/生肖/性别/流派）。"""
    solar: str
    lunar: str
    gender: str
    shengxiao: str
    sect: int
    yun_sect: int


@dataclass(frozen=True)
class Pillar:
    """单柱（年/月/日/时）的结构化数据：干支、五行、纳音、空亡、藏干、十神、星运、自坐。"""
    name: str
    ganzhi: str
    gan: str
    zhi: str
    gan_wuxing: str
    zhi_wuxing: str
    nayin: str
    xunkong: str
    hidden_stems: list[str]
    shishen_gan: str = ""
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""          # 星运：日干在四柱地支的十二长生
    zizuo: str = ""               # 自坐：本柱天干在本柱地支的十二长生


@dataclass(frozen=True)
class DayunItem:
    """大运单项：干支、起止年份/年龄、空亡、详情（主星/藏干/副星/星运/神煞）。"""
    index: int
    ganzhi: str
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    xunkong: str
    shishen_gan: str = ""
    gan: str = ""
    zhi: str = ""
    hidden_stems: list[str] = field(default_factory=list)
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""
    shensha: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class LiunianItem:
    """流年单项：年份、干支、虚岁、所在大运区间、详情（主星/藏干/副星/星运/神煞）。"""
    year: int
    ganzhi: str
    age: int
    dayun_ganzhi: str
    dayun_start_year: int | None
    dayun_end_year: int | None
    xunkong: str
    shishen_gan: str = ""
    gan: str = ""
    zhi: str = ""
    hidden_stems: list[str] = field(default_factory=list)
    shishen_zhi: list[str] = field(default_factory=list)
    changsheng: str = ""
    shensha: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class WuxingAnalysis:
    """五行分析结果：含权重统计、日主强弱、用神提示与口径说明。"""
    counts: dict[str, float]
    visible_counts: dict[str, int]
    strongest: str
    weakest: str
    day_master: str
    day_master_wuxing: str
    strength: str
    strength_score: float
    useful_hint: str
    notes: list[str]
    special_pattern: str = ""   # 方案B：特殊格局类型，"专旺" / "从格" / 空串


@dataclass(frozen=True)
class DomainAnalysis:
    """十神/合冲刑害/调候/格局等命局结构分析。"""
    ten_gods: dict[str, int]
    exposed_stems: list[str]
    rooted_stems: list[str]
    combinations: list[str]
    clashes: list[str]
    harms: list[str]
    punishments: list[str]
    three_assemblies: list[str]
    season: str
    adjustment: str
    pattern_hint: str
    confidence: float


@dataclass(frozen=True)
class BaziChart:
    """八字命盘完整结构化数据（事实来源），供 API/图表/代理上下文共用。"""
    birth: BirthInfo
    pillars: list[Pillar]
    wuxing: WuxingAnalysis
    analysis: DomainAnalysis
    dayun: list[DayunItem]
    liunian: list[LiunianItem]
    ming_gong: str
    ming_gong_nayin: str
    shen_gong: str
    shen_gong_nayin: str
    start_yun: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_birth(birth_time: str) -> tuple[int, int, int, int, int]:
    """将多种格式的出生时间字符串解析为 (年, 月, 日, 时, 分)。

    兼容中文年月日时、点/号、T、多种分隔符；不足 3 段或时辰非法则抛 ValueError。
    """
    import re as _re
    s = birth_time.strip()
    # 兼容多种分隔符：中文冒号、中文年月日时分、点号、T、汉字等
    s = s.replace("：", ":").replace("．", ".").replace("。", ".")
    s = s.replace("年", "-").replace("月", "-").replace("日", " ").replace("号", " ")
    s = s.replace("时", ":").replace("点", ":").replace("分", "").replace("T", " ")
    # 移除多余空格，统一分隔符
    s = s.replace("/", "-").replace(".", "-")
    s = _re.sub(r"\s+", " ", s).strip()
    parts = s.replace(":", " ").replace("-", " ").split()
    if len(parts) < 3:
        raise ValueError("请提供完整的出生时间，格式: YYYY-MM-DD HH:MM")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    hour = int(parts[3]) if len(parts) > 3 else 0
    minute = int(parts[4]) if len(parts) > 4 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("出生时辰必须在 00:00-23:59 之间")
    return year, month, day, hour, minute


def parse_gender(gender: str) -> int:
    """解析性别为内部编码：男=1，女=0；支持 男/女/male/female/m/f/1/0/公/母。"""
    g = (gender or "").strip().lower()
    if g in ("男", "male", "m", "1", "公"):
        return 1
    if g in ("女", "female", "f", "0", "母"):
        return 0
    raise ValueError("gender 必须是 男 或 女")


def _gender_label(gender_int: int) -> str:
    return "男" if gender_int == 1 else "女"


def _producer_of(element: str) -> str:
    for src, dst in GENERATES.items():
        if dst == element:
            return src
    return ""


def _controller_of(element: str) -> str:
    for src, dst in CONTROLS.items():
        if dst == element:
            return src
    return ""


def _round_counts(counts: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 2) for k, v in counts.items()}


def _compute_shensha(pillars: list[Pillar], gender_int: int | None = None) -> list[dict[str, str]]:
    """根据四柱干支计算传统神煞。

    以日干、年支、日支、月支为查表主键，遍历四柱地支判断是否带神煞。
    返回 [{"name": "天乙贵人", "description": "日干甲见丑，逢凶化吉"}, ...]
    """
    if not pillars:
        return []

    day_gan = pillars[2].gan  # 日柱天干
    year_gan = pillars[0].gan  # 年干
    year_zhi = pillars[0].zhi  # 年支
    month_zhi = pillars[1].zhi  # 月支
    day_zhi = pillars[2].zhi  # 日支

    result: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str, desc: str, pillar_name: str = ""):
        key = f"{name}-{pillar_name}"
        if key in seen:
            return
        seen.add(key)
        result.append({"name": name, "description": desc, "pillar": pillar_name})

    # ================================================================
    # 一、以日干 / 年干查的神煞（口径对齐 07_神煞初探.md / FateMaster）
    # ================================================================
    year_nayin_wx = pillars[0].nayin[-1] if pillars[0].nayin else ""
    month_gan = pillars[1].gan

    def _adv(zhi: str, step: int) -> str:
        i = BRANCH_ORDER.index(zhi)
        return BRANCH_ORDER[(i + step) % 12]

    # 天乙贵人（日干或年干）
    for g in (day_gan, year_gan):
        for z in TIAN_YI.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    add("天乙贵人", "遇事有人帮、临难有人解，逢凶化吉", p.name)

    # 太极贵人（日干或年干）
    for g in (day_gan, year_gan):
        for z in TAI_JI.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    add("太极贵人", "聪明好学，喜文史哲宗教，做事有始有终", p.name)

    # 文昌贵人（日干或年干）
    for g in (day_gan, year_gan):
        w = WEN_CHANG.get(g)
        if w:
            for p in pillars:
                if p.zhi == w:
                    add("文昌贵人", "聪明雅秀、有上进心，利考试功名", p.name)

    # 禄神（日干）
    lu = LU_SHEN.get(day_gan)
    if lu:
        for p in pillars:
            if p.zhi == lu:
                add("禄神", "身体健康、勤劳致富，一生少闲", p.name)

    # 羊刃（日干，取帝旺位；丁己在巳）
    yangren = YANG_REN.get(day_gan)
    if yangren:
        for p in pillars:
            if p.zhi == yangren:
                add("羊刃", "刚烈勇猛、有勇有谋；得制化为武贵，失制化易招灾", p.name)

    # 学堂 / 词馆（年柱纳音五行查月日时支的长生/临官位；禄命法）
    # 注意：只查月日时三柱（pillars[1:]），不包含年柱自身（古诀"见其他三支"）
    # 正学堂 / 正词馆 是 学堂 / 词馆 的精确位（干支完全匹配 ⊃ 仅地支匹配）。
    # 同柱同时命中"正X"和"X"时仅保留"正X"，避免重复标记。
    _other_three = pillars[1:]
    xt = XUE_TANG.get(year_nayin_wx)
    zxt = ZHENG_XUE_TANG.get(year_nayin_wx)
    cg = CI_GUAN.get(year_nayin_wx)
    zcg = ZHENG_CI_GUAN.get(year_nayin_wx)

    # 先标"正X"：记录命中柱，避免同一柱重复报"X"
    zheng_xt_pillars: set[str] = set()
    if zxt:
        for p in _other_three:
            if p.ganzhi == zxt:
                zheng_xt_pillars.add(p.name)
                add("正学堂", "纳音长生正位，学问正统、贵气十足", p.name)
    zheng_cg_pillars: set[str] = set()
    if zcg:
        for p in _other_three:
            if p.ganzhi == zcg:
                zheng_cg_pillars.add(p.name)
                add("正词馆", "纳音临官正位，文章锦绣、文采斐然", p.name)

    # 再标"X"：跳过已被"正X"标记的柱
    if xt:
        for p in _other_three:
            if p.zhi == xt and p.name not in zheng_xt_pillars:
                add("学堂", "纳音长生，聪明好学、文才出众、功名显达", p.name)
    if cg:
        for p in _other_three:
            if p.zhi == cg and p.name not in zheng_cg_pillars:
                add("词馆", "纳音临官，文章出类、学业精专", p.name)

    # 金舆（日干或年干）
    for g in (day_gan, year_gan):
        y = JIN_YU.get(g)
        if y:
            for p in pillars:
                if p.zhi == y:
                    add("金舆", "贵气显赫、得权贵相助，具领导气质", p.name)

    # 福星贵人（年干或日干）
    for g in (year_gan, day_gan):
        for z in FU_XING.get(g, ()):
            for p in pillars:
                if p.zhi == z:
                    add("福星贵人", "福德深厚、一生多得贵人，福寿双全", p.name)

    # 天厨贵人（年干或日干）
    for g in (year_gan, day_gan):
        t = TIAN_CHU.get(g)
        if t:
            for p in pillars:
                if p.zhi == t:
                    add("天厨贵人", "食神建禄，衣食无忧、财帛丰足，善理财", p.name)

    # 国印贵人（年干或日干）
    for g in (year_gan, day_gan):
        y = GUO_YIN.get(g)
        if y:
            for p in pillars:
                if p.zhi == y:
                    add("国印贵人", "权威正直、有责任感，宜公职权力岗", p.name)

    # 流霞（日干）
    lx = LIU_XIA.get(day_gan)
    if lx:
        for p in pillars:
            if p.zhi == lx:
                add("流霞", "主血光之灾、外伤疾病，需防意外", p.name)

    # 红艳煞（日干）
    hy = HONG_YAN.get(day_gan)
    if hy:
        for p in pillars:
            if p.zhi == hy:
                add("红艳煞", "异性缘过旺、易陷复杂感情纠葛，女命尤忌", p.name)

    # ================================================================
    # 二、以月支查的神煞（天德、月德 — 需四柱天干见对应字）
    # ================================================================
    month_idx = _zhi_to_month_index(month_zhi)  # 寅=1, 卯=2, ..., 丑=12

    tiande_chars = TIAN_DE_MONTH.get(month_idx)
    if tiande_chars:
        for c in tiande_chars:
            is_branch_target = month_idx in TIAN_DE_IS_BRANCH
            for p in pillars:
                if is_branch_target:
                    # 天德是地支（2月申、5月亥、8月寅），查地支
                    if p.zhi == c:
                        add("天德贵人", "逢凶化吉", p.name)
                else:
                    # 天德是天干，查天干（透出，力显）和藏干（暗藏，力弱需引动）
                    if p.gan == c:
                        add("天德贵人", "逢凶化吉", p.name)
                    elif any(hs == c for hs in p.hidden_stems):
                        add("天德贵人", "逢凶化吉", p.name)

    yuede_chars = YUE_DE_MONTH.get(month_idx)
    if yuede_chars:
        # 月德贵人查四柱天干（口诀"亥卯未月甲干栖"中的"干"即天干），
        # 不查藏干——否则亥/卯/未三合木局的藏干甲会被全部误报。
        # 对齐 07_神煞初探.md §3 月德贵人。
        for c in yuede_chars:
            for p in pillars:
                if p.gan == c:
                    add("月德贵人", "化煞解厄", p.name)

    # 天德合（按月支查。卯/午/酉/子四个月支对应的天德是地支，
    # 其天德合也走"地支六合"——对应值本身是地支，须查 p.zhi；
    # 其余八个月支天德是天干，其天德合是"天干五合"——对应值是天干，查 p.gan）。
    tian_de_he = TIAN_DE_HE.get(month_zhi)
    if tian_de_he:
        is_branch_target = month_idx in TIAN_DE_IS_BRANCH
        for p in pillars:
            if is_branch_target:
                if p.zhi == tian_de_he:
                    add("天德合", "与天德相配、逢凶化吉", p.name)
            else:
                if p.gan == tian_de_he:
                    add("天德合", "与天德相配、逢凶化吉", p.name)
    yue_de_he = YUE_DE_HE.get(month_zhi)
    if yue_de_he:
        for p in pillars:
            if p.gan == yue_de_he:
                add("月德合", "化解灾难、福禄双全", p.name)

    # 德秀贵人（月令查天干：德干 / 秀干）
    de_xiu = DE_XIU.get(month_zhi)
    if de_xiu:
        de_set, xiu_set = de_xiu
        for p in pillars:
            if p.gan in de_set:
                add("德秀贵人", "温厚聪慧、才华横溢", p.name)
                break
        else:
            for p in pillars:
                if p.gan in xiu_set:
                    add("德秀贵人", "清秀之气、多才多艺", p.name)
                    break

    # 天医（月支查，对齐 07_神煞初探.md）
    tianyi_med = TIAN_YI_MED.get(month_zhi)
    if tianyi_med:
        for p in pillars:
            if p.zhi == tianyi_med:
                add("天医", "医药有缘、善疗病痛，宜医护保健", p.name)

    # ================================================================
    # 三、以年支/日支查的神煞
    # 注：文档明确「查余支/余三支」，即排除自身柱位
    #   以年支查时排除年柱(index=0)，以日支查时排除日柱(index=2)
    # ================================================================
    for key_zhi, label, skip_idx in ((year_zhi, "年", 0), (day_zhi, "日", 2)):

        huagai = HUA_GAI.get(key_zhi)
        if huagai:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == huagai:
                    add("华盖", "聪明孤僻，近艺术宗教", p.name)

        taohua = TAO_HUA.get(key_zhi)
        if taohua:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == taohua:
                    add("桃花", "人缘感情，异性缘佳", p.name)

        yima = YI_MA.get(key_zhi)
        if yima:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == yima:
                    add("驿马", "迁动出行，奔波变化", p.name)

        jiang = JIANG_XING.get(key_zhi)
        if jiang:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == jiang:
                    add("将星", "掌权威望，领导力强", p.name)

        # 劫煞
        jiesha = JIE_SHA.get(key_zhi)
        if jiesha:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == jiesha:
                    add("劫煞", "破财伤身之兆", p.name)

        # 亡神
        wangshen = WANG_SHEN.get(key_zhi)
        if wangshen:
            for i, p in enumerate(pillars):
                if i == skip_idx:
                    continue
                if p.zhi == wangshen:
                    add("亡神", "心思深沉，暗耗多端", p.name)

    # ================================================================
    # 四、以年支查的专属神煞（灾煞、红鸾、天喜、孤辰寡宿、吊客、病符、天医）
    # 注：吊客/病符/天医传统只以年支查，故不放入上面的年/日双查循环
    # ================================================================
    # 灾煞（将星冲位，以年支查余三支）
    zaisha = ZAI_SHA.get(year_zhi)
    if zaisha:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == zaisha:
                add("灾煞", "灾厄不顺，需防意外", p.name)

    # 吊客（岁后二辰，以年支查余三支）
    diaoke = DIAO_KE.get(year_zhi)
    if diaoke:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == diaoke:
                add("吊客", "孝服丧事之兆", p.name)

    # 病符（岁后一辰，以年支查余三支）
    bingfu = BING_FU.get(year_zhi)
    if bingfu:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == bingfu:
                add("病符", "身体小恙，注意健康", p.name)

    hongluan = HONG_LUAN.get(year_zhi)
    if hongluan:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == hongluan:
                add("红鸾", "喜庆婚恋之事", p.name)

    tianxi = TIAN_XI.get(year_zhi)
    if tianxi:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == tianxi:
                add("天喜", "喜事临门，感情顺遂", p.name)

    guchen = GU_CHEN.get(year_zhi)
    if guchen:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == guchen:
                add("孤辰", "性格孤独，亲情淡薄", p.name)

    guasu = GUA_SU.get(year_zhi)
    if guasu:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == guasu:
                add("寡宿", "内心寂寞，晚景清冷", p.name)

    # 丧门（以年支查余三支）
    sangmen = SANG_MEN.get(year_zhi)
    if sangmen:
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == sangmen:
                add("丧门", "孝服丧事之应，主忧郁悲伤", p.name)

    # 披麻（年支查余三支）
    for z in PI_MA.get(year_zhi, ()):
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == z:
                add("披麻", "孝服六亲有损，大运流年遇之主意外伤病", p.name)

    # 血刃（以月支查四柱地支，含月柱自身）
    # 口径对齐 07_神煞初探.md §38 ——「以月支查四柱干支」。
    # 注：XUE_REN 表中"亥月→亥"是自映射，月柱本身就是命中点，
    #     不能像"将星冲位/年支前后辰"那种余三支模式一样 skip 月柱。
    xr = XUE_REN.get(month_zhi)
    if xr:
        for p in pillars:
            if p.zhi == xr:
                add("血刃", "血光之灾、外伤手术，岁运冲激尤忌", p.name)

    # 勾绞煞（年支查余三支，依年干阴阳+性别：阳男阴女勾前绞后，阴男阳女勾后绞前）
    yang_gan = {"甲", "丙", "戊", "庚", "壬"}
    is_yang = year_gan in yang_gan
    is_male = gender_int == 1
    if (is_yang and is_male) or (not is_yang and not is_male):
        gou = _adv(year_zhi, 3); jiao = _adv(year_zhi, -3)
    else:
        gou = _adv(year_zhi, -3); jiao = _adv(year_zhi, 3)
    for i, p in enumerate(pillars):
        if i == 0:
            continue
        if p.zhi == gou:
            add("勾绞煞", "牵连羁绊、易有官非纠纷", p.name)
    for i, p in enumerate(pillars):
        if i == 0:
            continue
        if p.zhi == jiao:
            add("勾绞煞", "牵连羁绊、易有官非纠纷", p.name)

    # 元辰（年支查对冲前/后一位，依年干阴阳+性别）
    chong = CHONG_ZHI.get(year_zhi)
    if chong:
        if (is_yang and is_male) or (not is_yang and not is_male):
            yuan = _adv(chong, 1)
        else:
            yuan = _adv(chong, -1)
        for i, p in enumerate(pillars):
            if i == 0:
                continue
            if p.zhi == yuan:
                add("元辰", "别而不合、诸事不顺", p.name)

    # 天罗地网（戌亥为天罗、辰巳为地网；需戌亥互见 / 辰巳互见）
    # 标注到具体柱：天罗标含"戌"的柱，地网标含"辰"的柱
    all_zhi = [p.zhi for p in pillars]
    if "戌" in all_zhi and "亥" in all_zhi:
        p_xu = next((p for p in pillars if p.zhi == "戌"), None)
        add("天罗", "困顿羁绊、难挣脱", p_xu.name if p_xu else "")
    if "辰" in all_zhi and "巳" in all_zhi:
        p_chen = next((p for p in pillars if p.zhi == "辰"), None)
        add("地网", "困顿羁绊、事业受阻", p_chen.name if p_chen else "")

    # ================================================================
    # 五、特殊组合类神煞（日柱特定组合 / 日柱纳音等）
    # ================================================================

    # ===== 五、特殊组合类神煞（日柱组合 / 日柱纳音 / 日时配合等） =====
    day_gz = pillars[2].ganzhi
    season_now = SEASON_OF_BRANCH.get(month_zhi)

    # 魁罡（日柱）
    if day_gz in KUI_GANG:
        add("魁罡", "刚强果断、文章振发，运行身旺发福百端", "日柱")

    # 十恶大败（日柱）
    if day_gz in SHI_E_DA_BAI:
        add("十恶大败", "祖业难守、不善理财，财运波折", "日柱")

    # 十灵日（日柱）
    if day_gz in SHI_LING:
        add("十灵日", "通灵异常、灵感丰富，宜玄学文学艺术", "日柱")

    # 八专日（日柱）
    if day_gz in BA_ZHUAN:
        add("八专日", "专业专精、禄旺，聪明专一但易固执", "日柱")

    # 九丑日（日柱）
    if day_gz in JIU_CHOU:
        add("九丑日", "容貌有魅力、感情易惹纠纷损名；女命主产厄", "日柱")

    # 阴差阳错（日柱）
    if day_gz in YIN_CHA_YANG_CUO:
        add("阴差阳错", "婚姻波折、夫妻不和，需包容理解", "日柱")

    # 孤鸾煞（日柱）
    if day_gz in GU_LUAN:
        add("孤鸾煞", "婚姻不顺、感情孤独，易晚婚或婚后不和", "日柱")

    # 六秀日（日柱）
    if day_gz in LIU_XIU:
        add("六秀日", "聪明俊秀、多才多艺，文雅秀丽", "日柱")

    # 天赦日（按出生季节查日柱）
    if day_gz == TIAN_SHE.get(season_now, ""):
        add("天赦日", "天恩浩荡、逢凶化吉，一生多得天佑", "日柱")

    # 金神（日柱或时柱，六甲日见乙丑/己巳/癸酉）
    if day_gz in JIN_SHEN:
        add("金神", "刚烈果断、具开拓改革精神，危机能当重任", "日柱")
    elif len(pillars) > 3 and pillars[3].ganzhi in JIN_SHEN:
        add("金神", "刚烈果断、具开拓改革精神，危机能当重任", "时柱")

    # 天转日 / 地转日（以月支查日柱，二者同表）
    td_zhuan = TIAN_DI_ZHUAN.get(season_now, ())
    if day_gz in td_zhuan:
        add("天转日", "干支纳音俱专、旺于四时，时来运转亦防过旺", "日柱")
        add("地转日", "干支纳音俱专、旺于四时，转运改命亦防过旺", "日柱")

    # 四废日（以出生季节查日柱）
    if day_gz in SI_FEI.get(season_now, ()):
        add("四废日", "有始无终、费力少功，需防虎头蛇尾", "日柱")

    # 拱禄（日时柱配合：日支与时支拱夹日干禄位）
    if len(pillars) > 3:
        for d, t, lu_zhi in GONG_LU:
            if pillars[2].zhi == d and pillars[3].zhi == t:
                add("拱禄", f"日时拱夹禄位{lu_zhi}，财禄拱护、富贵双全", "日柱")

    # 三奇贵人（对齐 07_神煞初探.md §10 + 《渊海子平》卷一·论三奇贵人）：
    #   硬性基础条件「天干顺次连续，不可颠倒、不可间隔其它天干」：
    #   - 天上三奇 甲→戊→庚：仅 年甲·月戊·日庚  或  月甲·日戊·时庚
    #   - 地下三奇 乙→丙→丁：仅 年乙·月丙·日丁  或  月乙·日丙·时丁
    #   - 人中三奇 壬→癸→辛：仅 年壬·月癸·日辛  或  月壬·日癸·时辛
    #   逆序、乱序、或在三干之间插入别的天干 → 直接不成立。
    #   两个连续窗口（年-月-日 / 月-日-时）任一「精确顺序」匹配即命中（均天然含日柱）。
    _SAN_QI_KIND = {
        ("甲", "戊", "庚"): "天上三奇",
        ("乙", "丙", "丁"): "地下三奇",
        ("壬", "癸", "辛"): "人中三奇",
    }
    _sanqi_windows: list[tuple[str, str, str]] = []
    if len(pillars) > 2:  # 年-月-日
        _sanqi_windows.append((pillars[0].gan, pillars[1].gan, pillars[2].gan))
    if len(pillars) > 3:  # 月-日-时
        _sanqi_windows.append((pillars[1].gan, pillars[2].gan, pillars[3].gan))
    _sanqi_hit = False
    for triple in SAN_QI:
        for window in _sanqi_windows:
            if window == triple:  # 精确顺序 + 连续窗口，逆序/乱序/隔柱一律不中
                kind = _SAN_QI_KIND[triple]
                add("三奇贵人", f"{kind}（{' '.join(triple)}），襟怀卓越、博学多能", "日柱")
                _sanqi_hit = True
                break
        if _sanqi_hit:
            break

    # 童子煞（月令 + 年柱纳音 + 日/时支分别判断，对齐 07_神煞初探.md）
    # 「春秋寅子贵，冬夏卯未辰；金木马卯合，水火鸡犬多；土命逢辰巳」
    def _check_tongzi(zhi: str, pillar_label: str) -> bool:
        if season_now in ("春", "秋") and zhi in ("寅", "子"):
            return True
        if season_now in ("夏", "冬") and zhi in ("卯", "未", "辰"):
            return True
        if year_nayin_wx in ("金", "木") and zhi in ("午", "卯"):
            return True
        if year_nayin_wx in ("水", "火") and zhi in ("酉", "戌"):
            return True
        if year_nayin_wx == "土" and zhi in ("辰", "巳"):
            return True
        return False

    if _check_tongzi(day_zhi, "日柱"):
        add("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "日柱")
    if len(pillars) > 3 and _check_tongzi(pillars[3].zhi, "时柱"):
        add("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "时柱")

    # 飞刃（羊刃对冲位）
    if yangren:
        feiren_zhi = CHONG_ZHI.get(yangren, "")
        if feiren_zhi:
            for p in pillars:
                if p.zhi == feiren_zhi:
                    add("飞刃", f"羊刃{yangren}对冲{feiren_zhi}，刚烈更甚、主突发伤害", p.name)

    # ================================================================
    # 六、空亡（以年柱+日柱旬空双查，标注实际落住四柱的旬空位）
    # ================================================================
    # 传统子平法以日柱旬空为主，年柱旬空为辅；本实现双查，任一落空即标记
    xunkong_set: set[str] = set()
    for idx in (0, 2):  # 年柱=0, 日柱=2
        if pillars[idx].xunkong:
            for xk_char in pillars[idx].xunkong:
                xunkong_set.add(xk_char)
    if xunkong_set:
        for p in pillars:
            if p.zhi in xunkong_set:
                add("空亡", f"旬空{p.zhi}，力减半", p.name)

    return result


def _zhi_to_month_index(zhi: str) -> int:
    """地支 → 农历月份索引。寅=1, 卯=2, ..., 子=11, 丑=12"""
    m = {"寅": 1, "卯": 2, "辰": 3, "巳": 4, "午": 5, "未": 6,
         "申": 7, "酉": 8, "戌": 9, "亥": 10, "子": 11, "丑": 12}
    return m.get(zhi, 0)


# —— 特殊格局（方案B）：专旺格 / 从格 检测 ——————————————————————
# 阈值（可调，后续用典型八字回测校准）：
_ZHUANWANG_DOM_RATIO = 0.60       # 主导五行占全局加权比例下限
_ZHUANWANG_PRESSURE_MAX = 2.0     # 克泄耗三行合计加权上限（超过则视为有破局，不算真专旺）
_CONG_ROOT_MIN_HIDDEN = 0.30      # 藏干中日主五行达此权重视为有"根"
_CONG_RESOURCE_MIN_HIDDEN = 0.30  # 藏干中印星五行达此权重视为有"印根"
_CONG_SELF_WX_MAX = 0.50          # 日主自身五行加权超过此值，不从（仍有本气根气）
_CONG_SECOND_RATIO = 0.60         # 从势判定：次旺/最旺 ≥ 此比例视为两行相当 → 从势

# 禄 / 羊刃 / 库（日主 → 其根气地支）
_LU = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午",
       "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
_REN = {"甲": "卯", "乙": "辰", "丙": "午", "丁": "未", "戊": "午", "己": "未",
        "庚": "酉", "辛": "戌", "壬": "子", "癸": "丑"}
_KU = {"木": "未", "火": "戌", "金": "丑", "水": "辰"}  # 土库寄四季，单独处理


def _root_branches_for_master(day_master: str) -> set[str]:
    wx = GAN_WUXING.get(day_master, "")
    s = {_LU.get(day_master, ""), _REN.get(day_master, "")}
    s.discard("")
    if wx == "土":
        s.update(["辰", "戌", "丑", "未"])
    else:
        ku = _KU.get(wx)
        if ku:
            s.add(ku)
    return s


# 专旺五格命名（按主导五行）
_ZHUANWANG_NAME = {"水": "润下格", "火": "炎上格", "木": "曲直格", "金": "从革格", "土": "稼穑格"}


def _has_root(pillars, day_master: str, day_wx: str, resource: str) -> bool:
    """真假从根气判定：日主在地支有禄/刃/库根，或藏干有中气以上本气根，
    或印星透干/有印根，或（除日干外）有比劫透干 → 视为有依，不从。
    注：日干本身即日主，不计入"比劫透干"，否则任何八字都会被判有比劫。
    """
    roots = _root_branches_for_master(day_master)
    hidden_day = 0.0
    hidden_resource = 0.0
    same_stem = False
    resource_stem = False
    for i, p in enumerate(pillars):
        zhi = p[1]
        if zhi in roots:
            return True
        for h, ratio in HIDDEN_STEMS.get(zhi, ()):
            hw = GAN_WUXING.get(h)
            if hw == day_wx:
                hidden_day += ratio
            elif hw == resource:
                hidden_resource += ratio
        if i == 2:  # 日柱天干就是日主，跳过比劫/印透干判定
            continue
        gw = GAN_WUXING.get(p[0])
        if gw == day_wx:
            same_stem = True
        elif gw == resource:
            resource_stem = True
    if same_stem:
        return True
    if hidden_day >= _CONG_ROOT_MIN_HIDDEN:
        return True
    if resource_stem or hidden_resource >= _CONG_RESOURCE_MIN_HIDDEN:
        return True
    return False


def _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output):
    """极旺候选 → 专旺格判定。返回 (label, hint) 或 None。
    要求主导五行就是日主自身五行（比劫一行得局），且一行独旺、克泄耗无破局。
    """
    total = sum(weighted.values())
    if total <= 0:
        return None
    strongest = max(weighted, key=weighted.get)
    if strongest != day_wx:
        return None
    dom_ratio = weighted[strongest] / total
    pressure = weighted.get(officer, 0.0) + weighted.get(wealth, 0.0) + weighted.get(output, 0.0)
    if dom_ratio < _ZHUANWANG_DOM_RATIO:
        return None
    if pressure > _ZHUANWANG_PRESSURE_MAX:
        return None
    name = _ZHUANWANG_NAME.get(strongest)
    if not name:
        return None
    hint = (
        f"日主入{name}（一行独旺，候选专旺），宜顺其旺势，喜{resource or '印星'}、{day_wx}比劫相扶；"
        f"切忌{wealth or '财星'}、{officer or '官杀'}逆克激怒旺神。"
    )
    return name, hint


def _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output):
    """极弱候选 → 从格判定（真假从 + 从杀/从财/从儿/从势）。返回 (label, hint) 或 None。"""
    if _has_root(pillars, day_master, day_wx, resource):
        return None  # 有根/有印/有比劫 → 假从或不从，不判从格
    if weighted.get(day_wx, 0.0) > _CONG_SELF_WX_MAX:
        return None  # 日主自身五行仍有可观权重（藏干本气），不从
    # 比较 官杀(克我) / 财(我克) / 食伤(我生) 三行权重
    contenders = {
        "官杀": weighted.get(officer, 0.0),
        "财": weighted.get(wealth, 0.0),
        "食伤": weighted.get(output, 0.0),
    }
    best_name = max(contenders, key=contenders.get)
    if contenders[best_name] < 0.5:
        return None  # 没有一行明显独旺，不从
    # 从势：次旺行与最旺行相当（差距不大）→ 从势格
    vals = sorted(contenders.values(), reverse=True)
    if vals[1] >= vals[0] * _CONG_SECOND_RATIO and vals[1] > 0:
        hint = (
            f"日主极弱无依，官杀/财/食伤两三相混、势均力敌，入从势格；"
            f"宜顺势相从，随旺气流转，喜多而从者、忌{resource or '印星'}{day_wx}比劫扶身。"
        )
        return "从势格", hint
    name_map = {
        "官杀": ("从杀格", f"日主极弱从杀，喜{wealth or '财星'}生{officer or '官杀'}、顺势御杀；切忌{resource or '印星'}、{day_wx}比劫抗杀。"),
        "财": ("从财格", f"日主极弱从财，喜{output or '食伤'}生{wealth or '财星'}、{officer or '官杀'}护财；切忌{resource or '印星'}、{day_wx}比劫分财。"),
        "食伤": ("从儿格", f"日主极弱从儿（食伤），喜{wealth or '财星'}流通秀气；切忌{resource or '印星'}制儿、{officer or '官杀'}犯怒。"),
    }
    return name_map[best_name]


def _detect_special_pattern(pillars, weighted, day_wx, day_master, score,
                            resource, output, wealth, officer):
    """方案B 编排：在 A 的 ±7 极端候选区上做结构化特殊格局识别。
    返回 dict: {is_special, kind, label, useful_hint}。
    - score ≥ 7：尝试判专旺五格（润下/炎上/曲直/从革/稼穑）。
    - score ≤ -7：尝试判从格（真假从 + 从杀/从财/从儿/从势）。
    - 不落入极端区或判定不自信时返回 is_special=False，沿用 A 的基础档。
    """
    if score >= 7:
        zw = _detect_zhuanwang(weighted, day_wx, resource, officer, wealth, output)
        if zw:
            label, hint = zw
            return {"is_special": True, "kind": "专旺", "label": label, "useful_hint": hint}
    elif score <= -7:
        cg = _detect_conging(weighted, pillars, day_wx, day_master, resource, officer, wealth, output)
        if cg:
            label, hint = cg
            return {"is_special": True, "kind": "从格", "label": label, "useful_hint": hint}
    return {"is_special": False, "kind": "", "label": "", "useful_hint": ""}


def _classify_strength(
    score: float,
    day_wx: str,
    resource: str,
    same: str,
    output: str,
    wealth: str,
    officer: str,
) -> tuple[str, str]:
    """日主强弱五档分档（方案A）。返回 (strength, useful_hint)。

    阈值约定（与 07_神煞初探.md / 滴天髓「中和」注解对齐思路）：
      - |score| ≥ 7 视为极端，候选特殊格局：极旺（专旺）/ 极弱（从格）；
      - score ≥ 2.2 为偏旺；score ≤ -1.2 为偏弱；中间为中和。
    极旺/极弱 的用神方向走「顺势」，与偏旺/偏弱 的制衡/扶助方向相反，
    避免 癸亥×4 这类极端局被笼统标成偏强却给出泄耗用神（方向折损）。
    """
    if score >= 7:
        strength = "极旺"
        useful_hint = (
            f"日主极旺（候选专旺格），宜顺其旺势，喜{resource or '印星'}、{same or '比劫'}相扶；"
            f"若有{output or '食伤'}亦可泄秀，切忌{wealth or '财星'}、{officer or '官杀'}逆克激怒旺神。"
        )
    elif score >= 2.2:
        strength = "偏旺"
        useful_hint = f"日主偏旺，宜取泄耗制衡之气，优先关注{output or '食伤'}、{wealth or '财星'}、{officer or '官杀'}的配合。"
    elif score <= -7:
        strength = "极弱"
        useful_hint = (
            f"日主极弱（候选从格），宜顺势相从，不喜{resource or '印星'}、{same or '比劫'}扶身反成羁绊；"
            f"具体用神需结合所从五行（从{wealth or '财'} / 从{officer or '官'} / 从{output or '儿'} 等）判定。"
        )
    elif score <= -1.2:
        strength = "偏弱"
        useful_hint = f"日主偏弱，宜先扶助日主，重点看{resource or '印星'}与{same or '比劫'}是否得地。"
    else:
        strength = "中和"
        useful_hint = "格局接近平衡，喜忌需要结合大运流年触发点细看。"
    return strength, useful_hint


def _build_wuxing_analysis(ec) -> WuxingAnalysis:
    pillars = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    visible_counts = {k: 0 for k in WUXING_ORDER}
    weighted = {k: 0.0 for k in WUXING_ORDER}

    for index, pillar in enumerate(pillars):
        gan, zhi = pillar[0], pillar[1]
        gan_wx = GAN_WUXING.get(gan)
        zhi_wx = ZHI_WUXING.get(zhi)
        stem_weight = 1.2 if index == 1 else 1.0
        branch_weight = 1.6 if index == 1 else 1.0
        if gan_wx:
            visible_counts[gan_wx] += 1
            weighted[gan_wx] += stem_weight
        if zhi_wx:
            visible_counts[zhi_wx] += 1
            weighted[zhi_wx] += branch_weight
        for hidden, ratio in HIDDEN_STEMS.get(zhi, ()):
            wx = GAN_WUXING.get(hidden)
            if wx:
                weighted[wx] += ratio * branch_weight

    day_master = ec.getDayGan()
    day_wx = GAN_WUXING.get(day_master, "未知")
    same = day_wx
    resource = _producer_of(day_wx)
    output = GENERATES.get(day_wx, "")
    wealth = CONTROLS.get(day_wx, "")
    officer = _controller_of(day_wx)

    support = weighted.get(same, 0.0) + weighted.get(resource, 0.0) * 0.85
    pressure = (
        weighted.get(output, 0.0) * 0.55
        + weighted.get(wealth, 0.0) * 0.7
        + weighted.get(officer, 0.0) * 0.8
    )
    strength_score = round(support - pressure, 2)
    strength, useful_hint = _classify_strength(
        strength_score, day_wx, resource, same, output, wealth, officer
    )
    # 方案B：仅在 A 的 ±7 极端候选区上做结构化特殊格局识别（专旺/从格）。
    special_pattern = ""
    if abs(strength_score) >= 7:
        sp = _detect_special_pattern(
            pillars, weighted, day_wx, day_master, strength_score,
            resource, output, wealth, officer,
        )
        if sp["is_special"]:
            strength = sp["label"]
            useful_hint = sp["useful_hint"]
            special_pattern = sp["kind"]

    strongest = max(weighted, key=weighted.get)
    weakest = min(weighted, key=weighted.get)
    notes = [
        "五行权重已纳入天干、地支、藏干，并对月令加权；比单纯统计八个字更稳。",
        "强弱为工程化初判，最终用神仍需结合格局、调候、合冲刑害与大运流年校验。",
    ]
    return WuxingAnalysis(
        counts=_round_counts(weighted),
        visible_counts=visible_counts,
        strongest=strongest,
        weakest=weakest,
        day_master=day_master,
        day_master_wuxing=day_wx,
        strength=strength,
        strength_score=strength_score,
        useful_hint=useful_hint,
        special_pattern=special_pattern,
        notes=notes,
    )


def _count_ten_gods(pillars: list[Pillar]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pillar in pillars:
        if pillar.shishen_gan and pillar.shishen_gan != "日主":
            counts[pillar.shishen_gan] = counts.get(pillar.shishen_gan, 0) + 1
        for item in pillar.shishen_zhi:
            if item:
                counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _branch_relations(zhis: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    combinations: list[str] = []
    clashes: list[str] = []
    harms: list[str] = []
    punishments: list[str] = []
    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            pair = frozenset((zhis[i], zhis[j]))
            if pair in LIU_HE:
                combinations.append(LIU_HE[pair])
            if pair in LIU_CHONG:
                clashes.append(LIU_CHONG[pair])
            if pair in LIU_HAI:
                harms.append(LIU_HAI[pair])
    zhi_set = set(zhis)
    for group, label in SAN_XING.items():
        if group.issubset(zhi_set):
            punishments.append(label)
    for zhi in zhi_set:
        if zhis.count(zhi) >= 2 and zhi in SELF_XING:
            punishments.append(SELF_XING[zhi])
    return combinations, clashes, harms, punishments


def _branch_combinations(zhis: list[str]) -> list[str]:
    """识别地支三合局、三会方、六破（与六合/六冲/六害并列的宏观合会关系）。

    只报「三支全会」的完整三合局/三会方；缺支的半合、拱合等暂不识别。
    三会方与三合局可能同时成立（如 申酉戌 既会西方金、又含 申子辰? 不会同局），
    各自独立判断，命中即报。六破与六合可同支并存（如 巳申 既六合又相破），均报。
    """
    result: list[str] = []
    zhi_set = set(zhis)
    for group, label in SAN_HE.items():
        if group.issubset(zhi_set):
            result.append(label)
    for group, label in SAN_HUI.items():
        if group.issubset(zhi_set):
            result.append(label)
    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            pair = frozenset((zhis[i], zhis[j]))
            if pair in LIU_PO:
                result.append(LIU_PO[pair])
    return result


def _stem_relations(gans: list[str]) -> tuple[list[str], list[str]]:
    """天干五合与相冲。返回 (合, 冲)。"""
    combos: list[str] = []
    clashes: list[str] = []
    for i in range(len(gans)):
        for j in range(i + 1, len(gans)):
            pair = frozenset((gans[i], gans[j]))
            if pair in GAN_HE:
                combos.append(GAN_HE[pair])
            if pair in GAN_CHONG:
                clashes.append(GAN_CHONG[pair])
    return combos, clashes


def _build_domain_analysis(pillars: list[Pillar], wuxing: WuxingAnalysis) -> DomainAnalysis:
    day_master = wuxing.day_master
    visible_gans = [p.gan for p in pillars if p.gan]
    hidden_stems = [stem for p in pillars for stem in p.hidden_stems]
    exposed = [gan for gan in visible_gans if gan != day_master]
    rooted = sorted({day_master for stem in hidden_stems if stem == day_master})
    zhis = [p.zhi for p in pillars if p.zhi]
    combinations, clashes, harms, punishments = _branch_relations(zhis)
    three_assemblies = _branch_combinations(zhis)
    # 天干五合与相冲，合并到合/冲列表（前缀标注“干”以便区分）
    gan_he, gan_chong = _stem_relations(visible_gans)
    combinations = [f"{g}(干合)" for g in gan_he] + combinations
    clashes = [f"{c}(干冲)" for c in gan_chong] + clashes
    month_zhi = pillars[1].zhi if len(pillars) > 1 else ""
    adjustment = SEASON_NOTES.get(month_zhi, "调候需结合月令、寒暖燥湿与全局五行再定。")

    ten_gods = _count_ten_gods(pillars)
    # 原 root_hint / top_gods / relation_bits / pattern_hint 拼接被移除——
    # "癸日主偏强，日主根气不显；十神以…"这类拼接句观感太笼统，
    # 且"根气不显"措辞生硬。根气、关系等结构化信息已由 analysis 其它
    # 字段分别承载（rooted_stems / combinations / clashes / harms / punishments），
    # 这里不再拼成一句；pattern_hint 字段保留空串以保持 dataclass 契约。
    pattern_hint = ""
    confidence = 0.72
    if month_zhi:
        confidence += 0.08
    if combinations or clashes or harms or punishments:
        confidence += 0.05

    return DomainAnalysis(
        ten_gods=ten_gods,
        exposed_stems=exposed,
        rooted_stems=rooted,
        combinations=combinations,
        clashes=clashes,
        harms=harms,
        punishments=punishments,
        three_assemblies=three_assemblies,
        season=month_zhi,
        adjustment=adjustment,
        pattern_hint=pattern_hint,
        confidence=round(min(confidence, 0.9), 2),
    )


def _zizuo(gan: str, zhi: str) -> str:
    """天干在其本柱地支的十二长生状态（自坐）。阳干顺行、阴干逆行。"""
    if not gan or not zhi:
        return ""
    base = _GAN_CHANGSHENG_ZHI.get(gan)
    if not base or base not in _ZHI_SEQ or zhi not in _ZHI_SEQ:
        return ""
    i_base = _ZHI_SEQ.index(base)
    i_zhi = _ZHI_SEQ.index(zhi)
    offset = (i_zhi - i_base) % 12 if gan in _YANG_GAN else (i_base - i_zhi) % 12
    return CHANG_SHENG[offset]


def _ten_god(day_master: str, target_gan: str) -> str:
    """计算 target_gan 相对于 day_master 的十神（主星）。"""
    if not day_master or not target_gan:
        return ""
    dm_wx = GAN_WUXING.get(day_master, "")
    tg_wx = GAN_WUXING.get(target_gan, "")
    if not dm_wx or not tg_wx:
        return ""
    same_polarity = (day_master in _YANG_GAN) == (target_gan in _YANG_GAN)
    if dm_wx == tg_wx:
        return "比肩" if same_polarity else "劫财"
    if GENERATES[dm_wx] == tg_wx:
        return "食神" if same_polarity else "伤官"
    if CONTROLS[dm_wx] == tg_wx:
        return "偏财" if same_polarity else "正财"
    if GENERATES[tg_wx] == dm_wx:
        return "偏印" if same_polarity else "正印"
    if CONTROLS[tg_wx] == dm_wx:
        return "七杀" if same_polarity else "正官"
    return ""


def _ganzhi_detail(ganzhi: str, day_master_gan: str, pillars: list[Pillar], gender_int: int) -> dict[str, Any]:
    """为大运/流年干支计算详细字段：主星、天干、地支、藏干、副星、星运、神煞。

    Args:
        ganzhi: 大运/流年干支（如 "辛未"）
        day_master_gan: 日主天干（如 "丙"）
        pillars: 原局四柱（用于神煞查表）
        gender_int: 性别（1=男 0=女）
    Returns:
        dict 含 shishen_gan/gan/zhi/hidden_stems/shishen_zhi/changsheng/shensha
    """
    if not ganzhi or len(ganzhi) < 2:
        return {}
    gan = ganzhi[0]
    zhi = ganzhi[1]
    # 主星：大运/流年天干相对日主的十神
    shishen_gan = _ten_god(day_master_gan, gan)
    # 藏干
    hidden = [s for s, _ in HIDDEN_STEMS.get(zhi, ())]
    # 副星：藏干天干相对日主的十神
    shishen_zhi = [_ten_god(day_master_gan, s) for s in hidden]
    # 星运：日主在大运/流年地支的十二长生
    changsheng = _zizuo(day_master_gan, zhi)
    # 神煞：创建临时 Pillar 加入四柱列表，调用 _compute_shensha 后筛出该柱神煞
    temp_name = "运柱"
    temp_pillar = Pillar(
        name=temp_name, ganzhi=ganzhi, gan=gan, zhi=zhi,
        gan_wuxing=GAN_WUXING.get(gan, ""), zhi_wuxing=ZHI_WUXING.get(zhi, ""),
        nayin="", xunkong="", hidden_stems=hidden,
        shishen_gan=shishen_gan, shishen_zhi=shishen_zhi,
        changsheng=changsheng, zizuo="",
    )
    all_pillars = pillars + [temp_pillar]
    all_shensha = _compute_shensha(all_pillars, gender_int)
    shensha = [{"name": s["name"], "description": s["description"]} for s in all_shensha if s.get("pillar") == temp_name]
    return {
        "shishen_gan": shishen_gan,
        "gan": gan,
        "zhi": zhi,
        "hidden_stems": hidden,
        "shishen_zhi": shishen_zhi,
        "changsheng": changsheng,
        "shensha": shensha,
    }


def _pillar(name: str, ganzhi: str, nayin: str, xunkong: str, hidden: str, shishen_gan: str, shishen_zhi: Any,
            changsheng: str = "", zizuo: str = "") -> Pillar:
    gan = ganzhi[0] if ganzhi else ""
    zhi = ganzhi[1] if len(ganzhi) > 1 else ""
    if isinstance(shishen_zhi, str):
        zhi_shishen = [s for s in shishen_zhi.replace("[", "").replace("]", "").replace("'", "").split(",") if s.strip()]
    else:
        zhi_shishen = list(shishen_zhi or [])
    return Pillar(
        name=name,
        ganzhi=ganzhi,
        gan=gan,
        zhi=zhi,
        gan_wuxing=GAN_WUXING.get(gan, ""),
        zhi_wuxing=ZHI_WUXING.get(zhi, ""),
        nayin=nayin,
        xunkong=xunkong,
        hidden_stems=[s.strip() for s in str(hidden).replace("[", "").replace("]", "").replace("'", "").split(",") if s.strip()],
        shishen_gan=shishen_gan,
        shishen_zhi=[s.strip() for s in zhi_shishen],
        changsheng=changsheng,
        zizuo=zizuo,
    )


def _build_dayun(yun, count: int, day_master_gan: str = "", pillars: list[Pillar] | None = None, gender_int: int = 1) -> list[DayunItem]:
    items: list[DayunItem] = []
    for d_yun in yun.getDaYun(count + 1):
        gz = d_yun.getGanZhi()
        if not gz:
            continue
        detail = _ganzhi_detail(gz, day_master_gan, pillars or [], gender_int) if day_master_gan else {}
        items.append(DayunItem(
            index=d_yun.getIndex(),
            ganzhi=gz,
            start_year=d_yun.getStartYear(),
            end_year=d_yun.getEndYear(),
            start_age=d_yun.getStartAge(),
            end_age=d_yun.getEndAge(),
            xunkong=d_yun.getXunKong(),
            shishen_gan=detail.get("shishen_gan", ""),
            gan=detail.get("gan", ""),
            zhi=detail.get("zhi", ""),
            hidden_stems=detail.get("hidden_stems", []),
            shishen_zhi=detail.get("shishen_zhi", []),
            changsheng=detail.get("changsheng", ""),
            shensha=detail.get("shensha", []),
        ))
        if len(items) >= count:
            break
    return items


def _find_dayun_for_year(dayun: list[DayunItem], year: int) -> DayunItem | None:
    for item in dayun:
        if item.start_year <= year <= item.end_year:
            return item
    return None


def _build_liunian(yun, dayun: list[DayunItem], start_year: int, years: int,
                   day_master_gan: str = "", pillars: list[Pillar] | None = None, gender_int: int = 1) -> list[LiunianItem]:
    lookup: dict[int, Any] = {}
    for d_yun in yun.getDaYun(14):
        for liu_nian in d_yun.getLiuNian(10):
            lookup[liu_nian.getYear()] = liu_nian

    result: list[LiunianItem] = []
    for offset in range(years):
        year = start_year + offset
        liu_nian = lookup.get(year)
        active_dayun = _find_dayun_for_year(dayun, year)
        if liu_nian is not None:
            ganzhi = liu_nian.getGanZhi()
            age = liu_nian.getAge()
            xunkong = liu_nian.getXunKong()
        else:
            lunar = Solar.fromYmdHms(year, 2, 4, 12, 0, 0).getLunar()
            ganzhi = lunar.getYearInGanZhiByLiChun()
            birth_year = yun.getLunar().getSolar().getYear()
            age = year - birth_year + 1
            xunkong = lunar.getYearXunKongByLiChun()
        detail = _ganzhi_detail(ganzhi, day_master_gan, pillars or [], gender_int) if day_master_gan else {}
        result.append(LiunianItem(
            year=year,
            ganzhi=ganzhi,
            age=age,
            dayun_ganzhi=active_dayun.ganzhi if active_dayun else "",
            dayun_start_year=active_dayun.start_year if active_dayun else None,
            dayun_end_year=active_dayun.end_year if active_dayun else None,
            xunkong=xunkong,
            shishen_gan=detail.get("shishen_gan", ""),
            gan=detail.get("gan", ""),
            zhi=detail.get("zhi", ""),
            hidden_stems=detail.get("hidden_stems", []),
            shishen_zhi=detail.get("shishen_zhi", []),
            changsheng=detail.get("changsheng", ""),
            shensha=detail.get("shensha", []),
        ))
    return result


def build_bazi_chart(
    birth_time: str,
    gender: str,
    sect: int = 2,
    yun_sect: int = 1,
    dayun_count: int = 8,
    liunian_years: int = 5,
    liunian_start_year: int | None = None,
    longitude: float | None = None,
) -> BaziChart:
    """构建完整八字命盘（BaziChart）。

    Args:
        birth_time: 出生时间（公历/农历/时辰/节日格式）
        gender: 性别（男/女）
        sect: 日柱计算流派（默认 2）
        yun_sect: 大运计算流派（默认 1）
        dayun_count: 推算多少柱大运（默认 8）
        liunian_years: 推算多少年流年（默认 5）
        liunian_start_year: 流年起始年（默认当前年）
        longitude: 出生地经度，用于真太阳时校正（基准 120°E，每度差 4 分钟）
    Returns:
        结构化 BaziChart（四柱/五行/十神/大运/流年/命宫/身宫/起运）
    """
    from datetime import timedelta

    y, m, d, h, mi = parse_birth(birth_time)
    gender_int = parse_gender(gender)

    # 真太阳时校正：根据出生地经度修正时钟时间
    solar_correction_min = 0
    if longitude and 60 <= longitude <= 140:
        solar_correction_min = round((120 - longitude) * 4)
    if solar_correction_min != 0:
        corrected = _dt.datetime(y, m, d, h, mi) + _dt.timedelta(minutes=solar_correction_min)
        h, mi = corrected.hour, corrected.minute
        # 跨日处理
        if corrected.date() != _dt.date(y, m, d):
            y, m, d = corrected.year, corrected.month, corrected.day

    solar = Solar.fromYmdHms(y, m, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    if sect != 2:
        ec.setSect(sect)

    # 大运顺逆以年干阴阳+性别判定（传统《渊海子平》古法）
    # 规则：阳年(甲丙戊庚壬)男/阴年女 → 顺排；阴年男/阳年女 → 逆排
    # lunar-python 内部用年干阴阳+性别判定，与古法一致，直接传真实性别
    yang_gan = {"甲", "丙", "戊", "庚", "壬"}
    year_gan = ec.getYearGan()
    year_is_yang = year_gan in yang_gan
    yun = ec.getYun(gender_int, yun_sect)
    start_solar = yun.getStartSolar()
    dayun_direction = "顺排" if (year_is_yang == (gender_int == 1)) else "逆排"

    pillars = [
        _pillar("年柱", ec.getYear(), ec.getYearNaYin(), ec.getYearXunKong(), ec.getYearHideGan(), ec.getYearShiShenGan(), ec.getYearShiShenZhi(),
                changsheng=ec.getYearDiShi(), zizuo=_zizuo(ec.getYearGan(), ec.getYearZhi())),
        _pillar("月柱", ec.getMonth(), ec.getMonthNaYin(), ec.getMonthXunKong(), ec.getMonthHideGan(), ec.getMonthShiShenGan(), ec.getMonthShiShenZhi(),
                changsheng=ec.getMonthDiShi(), zizuo=_zizuo(ec.getMonthGan(), ec.getMonthZhi())),
        _pillar("日柱", ec.getDay(), ec.getDayNaYin(), ec.getDayXunKong(), ec.getDayHideGan(), "日主", ec.getDayShiShenZhi(),
                changsheng=ec.getDayDiShi(), zizuo=_zizuo(ec.getDayGan(), ec.getDayZhi())),
        _pillar("时柱", ec.getTime(), ec.getTimeNaYin(), ec.getTimeXunKong(), ec.getTimeHideGan(), ec.getTimeShiShenGan(), ec.getTimeShiShenZhi(),
                changsheng=ec.getTimeDiShi(), zizuo=_zizuo(ec.getTimeGan(), ec.getTimeZhi())),
    ]
    wuxing = _build_wuxing_analysis(ec)
    analysis = _build_domain_analysis(pillars, wuxing)
    day_master_gan = ec.getDayGan()
    dayun = _build_dayun(yun, dayun_count, day_master_gan, pillars, gender_int)
    start_year = liunian_start_year or _dt.date.today().year
    liunian = _build_liunian(yun, dayun, start_year, liunian_years, day_master_gan, pillars, gender_int)

    warnings = [
        "流年干支采用立春口径；具体到立春前后的事件判断，应结合准确日期时刻。",
    ]
    if solar_correction_min != 0:
        sign = '+' if solar_correction_min > 0 else ''
        warnings.append(f"已根据出生地经度（{longitude}°E）校正真太阳时：{sign}{solar_correction_min}分钟。")
    if h == 23 or h == 0:
        warnings.append("出生时间接近子时，日柱可能受 sect 流派影响，建议保留早晚子时口径。")

    return BaziChart(
        birth=BirthInfo(
            solar=f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mi:02d}",
            lunar=lunar.toString(),
            gender=_gender_label(gender_int),
            shengxiao=lunar.getYearShengXiao(),
            sect=sect,
            yun_sect=yun_sect,
        ),
        pillars=pillars,
        wuxing=wuxing,
        analysis=analysis,
        dayun=dayun,
        liunian=liunian,
        ming_gong=ec.getMingGong(),
        ming_gong_nayin=ec.getMingGongNaYin(),
        shen_gong=ec.getShenGong(),
        shen_gong_nayin=ec.getShenGongNaYin(),
        start_yun={
            "startYear": yun.getStartYear(),
            "startSolarYear": start_solar.getYear(),
            "startMonth": yun.getStartMonth(),
            "startDay": yun.getStartDay(),
            "startHour": yun.getStartHour(),
            "startDate": f"{start_solar.getYear():04d}-{start_solar.getMonth():02d}-{start_solar.getDay():02d}",
            "forward": year_is_yang == (gender_int == 1),
            "direction": dayun_direction,
        },
        warnings=warnings,
    )


def chart_to_api_dict(chart: BaziChart) -> dict[str, Any]:
    """将 BaziChart 转为前端友好的 dict（含五行配色、柱/五行/大运/流年结构）。"""
    colors = {"金": "#d4af37", "木": "#4a7c3a", "水": "#3a6ea5", "火": "#c0392b", "土": "#8b6f47"}
    return {
        "birth": asdict(chart.birth),
        "pillars": [
            {
                "name": p.name,
                "ganzhi": p.ganzhi,
                "nayin": p.nayin,
                "gan": p.gan,
                "zhi": p.zhi,
                "ganWuxing": p.gan_wuxing,
                "zhiWuxing": p.zhi_wuxing,
                "xunkong": p.xunkong,
                "hiddenStems": p.hidden_stems,
                "shishenGan": p.shishen_gan,
                "shishenZhi": p.shishen_zhi,
                "changsheng": p.changsheng,
                "zizuo": p.zizuo,
            }
            for p in chart.pillars
        ],
        "wuxing": [
            {"name": name, "count": chart.wuxing.counts.get(name, 0), "color": colors[name]}
            for name in WUXING_ORDER
        ],
        "analysis": {
            **asdict(chart.wuxing),
            "tenGods": chart.analysis.ten_gods,
            "exposedStems": chart.analysis.exposed_stems,
            "rootedStems": chart.analysis.rooted_stems,
            "combinations": chart.analysis.combinations,
            "clashes": chart.analysis.clashes,
            "harms": chart.analysis.harms,
            "punishments": chart.analysis.punishments,
            "threeAssemblies": chart.analysis.three_assemblies,
            "season": chart.analysis.season,
            "adjustment": chart.analysis.adjustment,
            "patternHint": chart.analysis.pattern_hint,
            "confidence": chart.analysis.confidence,
        },
        "dayun": [
            {
                "year": item.ganzhi,
                "ganzhi": item.ganzhi,
                "startYear": item.start_year,
                "endYear": item.end_year,
                "startAge": item.start_age,
                "endAge": item.end_age,
                "xunkong": item.xunkong,
                "shishenGan": item.shishen_gan,
                "gan": item.gan,
                "zhi": item.zhi,
                "hiddenStems": item.hidden_stems,
                "shishenZhi": item.shishen_zhi,
                "changsheng": item.changsheng,
                "shensha": item.shensha,
            }
            for item in chart.dayun
        ],
        "liunian": [
            {
                "year": str(item.year),
                "ganzhi": item.ganzhi,
                "age": item.age,
                "dayun": item.dayun_ganzhi,
                "dayunStartYear": item.dayun_start_year,
                "dayunEndYear": item.dayun_end_year,
                "xunkong": item.xunkong,
                "shishenGan": item.shishen_gan,
                "gan": item.gan,
                "zhi": item.zhi,
                "hiddenStems": item.hidden_stems,
                "shishenZhi": item.shishen_zhi,
                "changsheng": item.changsheng,
                "shensha": item.shensha,
            }
            for item in chart.liunian
        ],
        "shensha": _compute_shensha(chart.pillars, parse_gender(chart.birth.gender)),
        "mingGong": f"{chart.ming_gong}（{chart.ming_gong_nayin}）",
        "shenGong": f"{chart.shen_gong}（{chart.shen_gong_nayin}）",
        "startYun": chart.start_yun,
        "warnings": chart.warnings,
    }


def format_chart_text(chart: BaziChart) -> str:
    """格式化四柱排盘文本（基本信息/四柱/空亡/命宫身宫/神煞/校验提示）。"""
    lines = [
        "【基本信息】",
        f"出生(公历): {chart.birth.solar}",
        f"出生(农历): {chart.birth.lunar}",
        f"生肖: {chart.birth.shengxiao}",
        f"性别: {chart.birth.gender}",
        "",
        "【四柱】",
    ]
    for p in chart.pillars:
        mark = "  ← 日主" if p.name == "日柱" else ""
        lines.append(f"  {p.name}: {p.ganzhi} ({p.nayin}){mark}")
        lines.append(
            f"    藏干: {', '.join(p.hidden_stems) or '-'} | "
            f"副星: {', '.join(p.shishen_zhi) or '-'} | "
            f"星运: {p.changsheng or '-'} | 自坐: {p.zizuo or '-'} | 空亡: {p.xunkong or '-'}"
        )
    lines += [
        "",
        "【空亡】",
    ]
    for p in chart.pillars:
        lines.append(f"  {p.name[0]}空: {p.xunkong}")
    lines += [
        "",
        "【命宫/身宫】",
        f"  命宫: {chart.ming_gong} ({chart.ming_gong_nayin})",
        f"  身宫: {chart.shen_gong} ({chart.shen_gong_nayin})",
    ]
    shensha_all = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    if shensha_all:
        shensha_by_pillar: dict[str, list[str]] = {}
        for _s in shensha_all:
            shensha_by_pillar.setdefault(_s.get("pillar") or "全局", []).append(_s["name"])
        lines += ["", "【神煞（按柱）】"]
        for p in chart.pillars:
            names = shensha_by_pillar.get(p.name, [])
            lines.append(f"  {p.name}: {'、'.join(names) if names else '—'}")
    if chart.warnings:
        lines += ["", "【校验提示】"] + [f"  - {w}" for w in chart.warnings]
    return "\n".join(lines)


def format_analysis_text(chart: BaziChart, question: str = "整体运势") -> str:
    """格式化五行十神分析文本（四柱/日主强弱/用神/十神/藏干/结构判断）。"""
    wx = chart.wuxing
    lines = [
        f"【四柱】 {' '.join(p.ganzhi for p in chart.pillars)}",
        f"【日主】 {wx.day_master}({wx.day_master_wuxing})",
        f"【五行权重】 {wx.counts}",
        f"【显性五行】 {wx.visible_counts}",
        f"【最旺/最弱】 {wx.strongest}({wx.counts[wx.strongest]}) / {wx.weakest}({wx.counts[wx.weakest]})",
        f"【日主强弱】 {wx.strength} (score={wx.strength_score})",
        f"【特殊格局】 {wx.special_pattern or '无（普通正格/未达极端候选）'}",
        f"【用神提示】 {wx.useful_hint}",
        "",
        "【十神（天干对日主）】",
    ]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.gan}: {p.shishen_gan}")
    lines += ["", "【藏干】"]
    for p in chart.pillars:
        lines.append(f"  {p.name}{p.zhi}: {', '.join(p.hidden_stems) or '-'}")
    lines += [
        "",
        "【结构判断】",
        f"  十神分布: {chart.analysis.ten_gods}",
        f"  透干: {', '.join(chart.analysis.exposed_stems) or '-'}",
        f"  通根: {', '.join(chart.analysis.rooted_stems) or '-'}",
        f"  合: {', '.join(chart.analysis.combinations) or '-'}",
        f"  冲: {', '.join(chart.analysis.clashes) or '-'}",
        f"  害: {', '.join(chart.analysis.harms) or '-'}",
        f"  刑: {', '.join(chart.analysis.punishments) or '-'}",
        f"  调候: {chart.analysis.adjustment}",
        f"  判断置信度: {chart.analysis.confidence}",
        "",
        f"【分析方向】 {question}",
        "【口径说明】",
    ]
    lines += [f"  - {note}" for note in wx.notes]
    # 神煞（按柱分组，与 _fact_block / format_chart_text 一致）
    _ss = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    _ss_by_p: dict[str, list[str]] = {}
    for _s in _ss:
        _ss_by_p.setdefault(_s.get("pillar") or "全局", []).append(_s["name"])
    lines += ["", "【神煞（按柱）】"]
    for p in chart.pillars:
        _names = _ss_by_p.get(p.name, [])
        lines.append(f"  {p.name}: {'、'.join(_names) if _names else '—'}")
    return "\n".join(lines)


def format_dayun_text(chart: BaziChart) -> str:
    """格式化大运文本（起运信息 + 每柱大运的干支/年份区间/年龄）。"""
    lines = [
        "【起运信息】",
        f"起运年龄: {chart.start_yun['startYear']}年 {chart.start_yun['startMonth']}月 {chart.start_yun['startDay']}日 {chart.start_yun['startHour']}时",
        f"起运日期: {chart.start_yun['startDate']}",
        f"起运公历年: {chart.start_yun['startSolarYear']} 年",
        f"大运方向: {chart.start_yun['direction']}",
        "",
        f"【大运列表】(共 {len(chart.dayun)} 柱)",
    ]
    for item in chart.dayun:
        lines.append(
            f"  {item.ganzhi}({item.shishen_gan}) | {item.start_year}-{item.end_year} | {item.start_age}-{item.end_age}岁 "
            f"藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}] "
            f"星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        )
    lines += ["", "注: 大运由 lunar-python 起运算法生成，顺逆与起运时间已结构化保存。"]
    return "\n".join(lines)


def format_liunian_text(chart: BaziChart) -> str:
    """格式化流年文本（逐年干支/虚岁，并绑定所在大运）。"""
    if chart.liunian:
        start_year = chart.liunian[0].year
    else:
        start_year = _dt.date.today().year
    lines = [f"【流年推算】从 {start_year} 年起往后 {len(chart.liunian)} 年", ""]
    for item in chart.liunian:
        dy = f" | 所在大运: {item.dayun_ganzhi}" if item.dayun_ganzhi else ""
        lines.append(
            f"  {item.year}年: {item.ganzhi}({item.shishen_gan}) | {item.age}虚岁{dy} "
            f"藏干[{'、'.join(item.hidden_stems) or '—'}] 副星[{'、'.join(item.shishen_zhi) or '—'}] "
            f"星运[{item.changsheng or '—'}] 神煞[{'、'.join(s['name'] for s in item.shensha) or '—'}]"
        )
    lines += ["", "注: 流年干支采用立春口径，并逐年绑定所在大运。"]
    return "\n".join(lines)


# 反推候选出生日期：四柱 -> 少量可能日期，由用户确认其一
_GAN_SEQ = "甲乙丙丁戊己庚辛壬癸"
_ZHI_SEQ2 = "子丑寅卯辰巳午未申酉戌亥"
# 各时辰中点小时（用于反推时取代表时刻，整时辰干支相同）
_ZHI_MID_HOUR = {
    "子": 0, "丑": 2, "寅": 4, "卯": 6, "辰": 8, "巳": 10,
    "午": 12, "未": 14, "申": 16, "酉": 18, "戌": 20, "亥": 22,
}


def _parse_pillars(pillars: str) -> tuple[str, str, str, str]:
    """把 '甲申庚午壬申甲辰' / '甲申 庚午 壬申 甲辰' / '甲申年庚午月...' 统一拆成四柱。"""
    import re as _re
    s = (pillars or "").strip()
    s = _re.sub(r"[\s/、，,年日月时\-]", "", s)
    chars = [c for c in s if c in _GAN_SEQ or c in _ZHI_SEQ2]
    seq = "".join(chars)
    if len(seq) < 8:
        raise ValueError("八字应为 4 个干支共 8 字，如 甲申庚午壬申甲辰")
    seq = seq[:8]
    out = []
    for i in range(4):
        gz = seq[i * 2: i * 2 + 2]
        if gz[0] not in _GAN_SEQ or gz[1] not in _ZHI_SEQ2:
            raise ValueError(f"非法干支: {gz}")
        out.append(gz)
    return tuple(out)


def _jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def _day_gz_from_jdn(j: int) -> str:
    """日柱快速公式（与 lunar 标定一致）。"""
    return _GAN_SEQ[(j + _DAY_OFF_G) % 10] + _ZHI_SEQ2[(j + _DAY_OFF_Z) % 12]


# 用 lunar 标定日柱相对 JDN 的偏移（模块加载时执行一次）
_REF = _jdn(2000, 1, 1)
_REF_EC = Lunar.fromSolar(Solar.fromYmd(2000, 1, 1)).getEightChar().getDay()
_DAY_OFF_G = (_GAN_SEQ.index(_REF_EC[0]) - _REF) % 10
_DAY_OFF_Z = (_ZHI_SEQ2.index(_REF_EC[1]) - _REF) % 12


def find_birth_dates_from_pillars(
    pillars: str,
    gender: str = "男",
    max_years_back: int = 120,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """根据四柱反推候选出生日期。

    用户只知道八字（如「甲申庚午壬申甲辰」）、不知道精确出生时间时，
    用日柱 60 天周期 + 年/月/时柱逐层过滤，反推出少量候选出生日期，
    由用户确认其一即可获得精确 birth_time 以排大运/流年/命宫。

    Returns: [{"birth_time", "ganzhi", "shi_chen"}, ...] 按日期倒序，最多 top_n 个。
    """
    y_gz, m_gz, d_gz, t_gz = _parse_pillars(pillars)
    today = _dt.date.today()
    today_jdn = _jdn(*today.timetuple()[:3])
    min_jdn = _jdn(today.year - max_years_back, 1, 1)

    t_zhi = t_gz[1]
    results: list[dict[str, Any]] = []
    seen_dates: set[str] = set()

    j = today_jdn
    while j >= min_jdn:
        if _day_gz_from_jdn(j) == d_gz:
            y, mo, d = _date_from_jdn(j)
            key = f"{y}-{mo:02d}-{d:02d}"
            if key not in seen_dates:
                hour = _ZHI_MID_HOUR[t_zhi]
                solar = Solar.fromYmdHms(y, mo, d, hour, 0, 0)
                ec = solar.getLunar().getEightChar()
                if ec.getYear() == y_gz and ec.getMonth() == m_gz and ec.getTime() == t_gz:
                    seen_dates.add(key)
                    results.append({
                        "birth_time": f"{y}-{mo:02d}-{d:02d} {hour:02d}:00",
                        "ganzhi": f"{ec.getYear()} {ec.getMonth()} {ec.getDay()} {t_gz}",
                        "shi_chen": f"{t_zhi}时",
                    })
        j -= 1

    results.sort(key=lambda r: r["birth_time"], reverse=True)
    return results[:top_n]


def _date_from_jdn(j: int) -> tuple[int, int, int]:
    a = j + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def format_fact_context(chart: BaziChart) -> str:
    """汇总格式化命盘事实（排盘+分析+大运+流年），用于事实校验锚点。"""
    return "\n\n".join([
        format_chart_text(chart),
        format_analysis_text(chart),
        format_dayun_text(chart),
        format_liunian_text(chart),
    ])