"""领域命盘投影层（纯函数，无 IO 无 LLM）。

把命盘的静态要素（骨架/十神落点/宫位/神煞）按领域抽取出关注子集，供工作流
消息装配注入，让 LLM 的推演有据可依，避免在全盘事实里自行翻找。

只筛要素、不下断语；岁运关系（动态）统一交给 yun_relations，本模块不重复计算。
"""

from __future__ import annotations

from app.domain.chart_builder import parse_gender
from app.domain.models import BaziChart, Pillar
from app.domain.shensha_calc import _compute_shensha
from app.domain.xipan import ten_god

_ALL_GODS = ("正官", "七杀", "正印", "偏印", "食神", "伤官", "正财", "偏财", "比肩", "劫财")

# 柱位 → 标准宫位（命理通用口径，所有领域一致）
_PALACE_LABEL = {
    "年柱": "祖上父母宫",
    "月柱": "父母兄弟宫",
    "日柱": "配偶宫",
    "时柱": "子女宫",
}

# 领域 → 关注要素。gods/palaces/shensha 为常规投影；
# gender_gods=(男配偶星, 女配偶星) 按命主性别取星；缺省领域走骨架-only。
_DOMAIN_PROJECTION: dict[str, dict] = {
    "career": {
        "gods": ("正官", "七杀", "正印", "偏印", "食神", "伤官"),
        "palaces": ("月柱", "日柱"),
        "shensha": ("将星", "国印贵人", "天乙贵人", "文昌贵人", "学堂",
                    "正学堂", "词馆", "正词馆", "金神", "魁罡"),
    },
    "wealth": {
        "gods": ("正财", "偏财", "食神", "伤官", "比肩", "劫财"),
        "palaces": ("月柱", "日柱", "时柱"),
        "shensha": ("金舆", "天厨贵人", "禄神", "拱禄", "十恶大败", "劫煞", "亡神"),
    },
    "love": {
        "gods": ("比肩", "劫财"),
        "gender_gods": ("正财、偏财", "正官、七杀"),
        "palaces": ("日柱",),
        "shensha": ("桃花", "红艳煞", "红鸾", "天喜", "孤辰", "寡宿", "阴差阳错", "孤鸾煞"),
    },
    "marriage": {
        "gods": ("食神", "伤官"),
        "gender_gods": ("正财、偏财", "正官、七杀"),
        "palaces": ("日柱", "月柱"),
        "shensha": ("桃花", "红艳煞", "红鸾", "天喜", "孤辰", "寡宿", "阴差阳错", "孤鸾煞", "童子煞"),
    },
    "health": {
        "gods": (),
        "palaces": ("年柱", "月柱", "日柱", "时柱"),
        "shensha": ("羊刃", "飞刃", "血刃", "病符", "天医", "流霞", "劫煞", "灾煞", "天罗", "地网"),
    },
    "study": {
        "gods": ("正印", "偏印", "食神", "伤官", "正官", "七杀"),
        "palaces": ("年柱", "月柱", "时柱"),
        "shensha": ("文昌贵人", "学堂", "正学堂", "词馆", "正词馆", "华盖", "德秀贵人", "六秀日", "十灵日"),
    },
    "social": {
        "gods": ("比肩", "劫财", "正官", "七杀"),
        "palaces": ("月柱",),
        "shensha": ("天乙贵人", "天德贵人", "月德贵人", "太极贵人", "勾绞煞", "元辰"),
    },
    "family": {
        "gods": _ALL_GODS,
        "palaces": ("年柱", "月柱", "日柱", "时柱"),
        "shensha": ("天乙贵人", "丧门", "吊客", "披麻", "孤辰", "寡宿"),
    },
    "personality": {
        "gods": (),
        "palaces": ("日柱",),
        "shensha": ("魁罡", "华盖", "十灵日", "八专日", "九丑日", "六秀日", "德秀贵人", "天赦日", "四废日"),
    },
    "appearance": {
        "gods": ("食神", "伤官", "正印", "偏印", "劫财", "比肩"),
        "palaces": ("日柱", "时柱"),
        "shensha": ("桃花", "红艳煞", "天乙贵人", "六秀日", "九丑日", "八专日", "魁罡", "羊刃"),
    },
    "migration": {
        "gods": ("比肩", "劫财", "正官", "七杀", "正印", "偏印"),
        "palaces": ("日柱", "月柱"),
        "shensha": ("驿马", "天乙贵人", "天罗", "地网"),
    },
    "children": {
        "gods": (),
        "gender_gods": ("正官、七杀", "食神、伤官"),
        "palaces": ("时柱",),
        "shensha": ("天乙贵人", "华盖", "孤辰", "寡宿"),
    },
    "liunian": {
        "gods": (),
        "palaces": ("年柱", "月柱", "日柱", "时柱"),
        "shensha": ("驿马", "桃花", "红鸾", "天喜", "羊刃"),
    },
    "match": {
        "gods": (),
        "gender_gods": ("正财、偏财", "正官、七杀"),
        "palaces": ("日柱",),
        "shensha": ("桃花", "红艳煞", "红鸾", "天喜", "孤辰", "寡宿"),
    },
    "general": {
        "gods": (),
        "palaces": ("年柱", "月柱", "日柱", "时柱"),
        "shensha": ("天乙贵人", "天德贵人", "月德贵人", "文昌贵人", "学堂", "禄神"),
    },
    # 无需投影的领域：返回空串，零开销
    "naming": {}, "auspicious": {}, "theory": {}, "chitchat": {},
}

def _god_placement(pillars: list[Pillar], god: str) -> str:
    """某十神在四柱的落点：天干透出 / 地支藏干。"""
    parts: list[str] = []
    for p in pillars:
        if p.shishen_gan == god:
            parts.append(f"{p.name}天干透出")
    for p in pillars:
        for stem, sg in zip(p.hidden_stems, p.shishen_zhi):
            if sg == god:
                parts.append(f"{p.name}支藏{stem}")
    return "、".join(parts) if parts else "无"


def _top_gods(ten_gods: dict[str, int], n: int = 3) -> list[str]:
    return [g for g, c in sorted(ten_gods.items(), key=lambda kv: -kv[1])[:n] if g != "日主" and c > 0]


def _skeleton_lines(chart: BaziChart) -> list[str]:
    w = chart.wuxing
    special = w.special_pattern or "无"
    return [
        f"一、骨架：日主 {w.day_master}({w.day_master_wuxing})（{w.strength}，分数 {w.strength_score}）",
        f"   特殊格局 {special}；用神提示 {w.useful_hint}",
        f"   月令 {chart.analysis.season or '-'}（{chart.analysis.adjustment}）",
    ]


def _shensha_lines(chart: BaziChart, wanted: tuple[str, ...]) -> list[str]:
    shensha_list = _compute_shensha(chart.pillars, parse_gender(chart.birth.gender))
    found: dict[str, list[str]] = {}
    for s in shensha_list:
        name = s.get("name", "")
        if name in wanted:
            found.setdefault(name, []).append(s.get("pillar") or "全局")
    return [f"  {name}：{'、'.join(pillars)}" for name, pillars in found.items()]


def _palace_lines(chart: BaziChart, palaces: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for p in chart.pillars:
        if p.name not in palaces:
            continue
        lines.append(
            f"  {p.name}（{_PALACE_LABEL.get(p.name, '')}）：{p.ganzhi} 主星[{p.shishen_gan or '—'}] "
            f"藏干[{'、'.join(p.hidden_stems) or '—'}] 星运[{p.changsheng or '—'}]"
        )
    return lines


def build_domain_brief(chart: BaziChart, domain: str) -> str:
    """领域命盘要素投影；未映射领域返回空串（naming/auspicious/theory/chitchat）。"""
    spec = _DOMAIN_PROJECTION.get(domain)
    if spec is None or domain in ("naming", "auspicious", "theory", "chitchat"):
        return ""

    lines = _skeleton_lines(chart)
    day_master = chart.wuxing.day_master
    gender = chart.birth.gender
    gods = spec.get("gods", ())

    # 十神落点：gender_gods 场景额外给配偶星
    lines.append(f"二、{_domain_god_section(domain)}相关十神落点")
    if domain == "health":
        w = chart.wuxing
        lines.append(f"   日主 {w.day_master}({w.day_master_wuxing})；五行权重 {w.counts}")
        lines.append(f"   最旺 {w.strongest}；最弱 {w.weakest}")
    elif domain in ("personality", "general"):
        top = _top_gods(chart.analysis.ten_gods)
        for god in top:
            lines.append(f"  {god}：{_god_placement(chart.pillars, god)}")
        if domain == "general":
            lines.append(f"  日主 {day_master}；格局/用神见【骨架】")
    elif domain == "liunian":
        for key, label in (("dayun", "大运"), ("liunian", "流年"), ("liuyue", "流月")):
            gz = (chart.xipan or {}).get("current", {}).get(key, "")
            if len(gz) == 2:
                lines.append(f"  {label}：{gz}（{ten_god(day_master, gz[0])}）")
        lines.append("  岁运与原局的关系详见【岁运关系】段")
    else:
        if "gender_gods" in spec:
            male_gods, female_gods = spec["gender_gods"]
            label = "子女星" if domain == "children" else "配偶星"
            picked = male_gods if gender == "男" else female_gods
            lines.append(f"  {label}（{'男命' if gender == '男' else '女命'}取 {picked}）")
            for g in picked.split("、"):
                if g:
                    lines.append(f"    {g}：{_god_placement(chart.pillars, g)}")
        for god in gods:
            lines.append(f"  {god}：{_god_placement(chart.pillars, god)}")

    # 宫位
    palaces = spec.get("palaces", ())
    if palaces:
        lines.append("三、相关宫位")
        lines.extend(_palace_lines(chart, palaces))

    # 神煞
    shensha = spec.get("shensha", ())
    if shensha:
        ss_lines = _shensha_lines(chart, shensha)
        lines.append("四、相关神煞")
        lines.extend(ss_lines if ss_lines else ["  无"])

    return "\n".join(lines)


def _domain_god_section(domain: str) -> str:
    """十神落点段的领域标题（保持与 DOMAIN_LABELS 一致的口语化）。"""
    label = {
        "career": "事业", "wealth": "财运", "love": "感情", "marriage": "婚姻",
        "health": "健康", "study": "学业", "social": "社交", "family": "六亲",
        "personality": "性格", "appearance": "形貌", "migration": "迁移",
        "children": "子女", "liunian": "岁运", "match": "合婚", "general": "综合",
    }
    return label.get(domain, domain)
