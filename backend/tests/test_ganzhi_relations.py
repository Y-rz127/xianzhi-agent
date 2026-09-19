"""干支关系单一事实源的契约测试。

口径依据：`knowledge_docs/12_合冲刑害规则卡.md`
- §一 合局力量排序：三会 ＞ 三合 ＞ 六合 ＞ 半合 ＞ 拱合（半合/拱合是正式关系类）
- §三.3 辰/午/酉/亥 自刑
- §三.4 三刑采用「两支半刑」口径（并注明部分流派坚持三支齐全）
- 古籍05 十二节：六破
另：三刑名称（寅巳申=无恩 / 丑未戌=恃势）曾写反，本文件把方向钉死。

这层测试与黄金快照分工不同：快照保证"和上次一样"，
本文件保证"口径与知识库一致" —— 前者对代码改动敏感，后者对口径错误敏感。
"""

from __future__ import annotations

from app.domain.ganzhi_relations import (
    branch_relations,
    gan_pair_relation,
    stem_relations,
    zhi_pair_relations,
)


def _br(*zhis):
    return branch_relations(list(zhis))


def _labels(rel) -> dict[str, tuple]:
    return {
        "hui": rel.hui,
        "san_he": rel.san_he,
        "ban_he": rel.ban_he,
        "gong_he": rel.gong_he,
        "liu_he": rel.liu_he,
        "chong": rel.chong,
        "hai": rel.hai,
        "po": rel.po,
        "san_xing": rel.san_xing,
        "ban_xing": rel.ban_xing,
        "zi_xing": rel.zi_xing,
    }


# ---------------- 三合体系（三合 / 半合 / 拱合） ----------------


def test_full_san_he():
    assert _labels(_br("申", "子", "辰"))["san_he"] == ("申子辰合水局",)


def test_ban_he_contains_middle_branch():
    """半合 = 三合中**含中神**的两支（生半合与旺半合）。"""
    assert "申子半合水" in _labels(_br("申", "子", "未"))["ban_he"]     # 生半合
    assert "子辰半合水" in _labels(_br("子", "辰", "午"))["ban_he"]     # 旺半合
    assert "亥卯半合木" in _labels(_br("亥", "卯", "丑"))["ban_he"]
    assert "午戌半合火" in _labels(_br("亥", "午", "戌"))["ban_he"]
    assert "巳酉半合金" in _labels(_br("巳", "酉", "辰"))["ban_he"]


def test_gong_he_when_middle_branch_missing():
    """拱合 = 首尾两支、中神虚一（如 申辰拱子）。"""
    assert "申辰拱合子" in _labels(_br("申", "辰", "未"))["gong_he"]
    assert "寅戌拱合午" in _labels(_br("寅", "戌", "卯"))["gong_he"]


def test_three_branches_are_san_he_not_ban_he():
    """三支齐全时只报三合局，不再叠加半合/拱合。"""
    rel = _br("申", "子", "辰")
    labels = _labels(rel)
    assert labels["san_he"] and not labels["ban_he"] and not labels["gong_he"]


def test_san_he_order_preserved_from_table():
    """三合产物顺序须与 `SAN_HE_TRIPLE` 表序一致（申子辰/亥卯未/寅午戌/巳酉丑）。"""
    assert _labels(_br("子", "申", "辰"))["san_he"] == ("申子辰合水局",)


# ---------------- 三会 ----------------


def test_san_hui():
    assert _labels(_br("寅", "卯", "辰"))["hui"] == ("寅卯辰会东方木",)


# ---------------- 成对关系 ----------------


def test_pair_relations_all_four_classes():
    """巳申 同时是 六合/六刑? 否 —— 巳申为六合、相刑(半刑)、六破 三类同见。"""
    rel = _br("巳", "申", "午", "子")
    labels = _labels(rel)
    assert "巳申合水" in labels["liu_he"]
    assert "巳申破" in labels["po"]
    assert labels["hai"] == ()          # 巳申不在六害


def test_liu_chong_and_hai():
    rel = _br("子", "午", "未", "丑")
    labels = _labels(rel)
    assert "子午冲" in labels["chong"]
    assert "子未害" in labels["hai"]
    assert "丑未冲" in labels["chong"]


# ---------------- 三刑 / 半刑 / 自刑 ----------------


def test_san_xing_labels_are_not_swapped():
    """寅巳申=无恩之刑、丑未戌=恃势之刑 —— 原表曾把两者写反（字典抄错类故障）。"""
    labels = _labels(_br("寅", "巳", "申"))
    assert "寅巳申无恩之刑三刑" in labels["san_xing"]
    assert "持势" not in "".join(labels["san_xing"]), "寅巳申不应标为恃势"

    labels2 = _labels(_br("丑", "未", "戌"))
    assert "丑未戌恃势之刑三刑" in labels2["san_xing"]
    assert "无恩" not in "".join(labels2["san_xing"]), "丑未戌不应标为无恩"


def test_ban_xing_when_only_two_branches():
    """两支见为半刑（知识库 §三.4 采用「两支半刑」口径），并带刑名。"""
    labels = _labels(_br("寅", "巳", "午", "子"))
    assert "寅巳半刑（无恩之刑）" in labels["ban_xing"]
    assert not labels["san_xing"], "三支不齐不应报真刑"

    labels2 = _labels(_br("丑", "戌", "卯", "子"))
    assert "丑戌半刑（恃势之刑）" in labels2["ban_xing"]


def test_ban_xing_only_reported_once_per_pair():
    """同一对半刑不得重复输出（寅巳 与 巳申 之外的申寅 仅当申也在场才有）。"""
    labels = _labels(_br("寅", "巳", "卯", "午"))
    assert labels["ban_xing"] == ("寅巳半刑（无恩之刑）",)


def test_zi_mao_pair_is_full_xing():
    """子卯 无礼刑是天然两支，成对即成刑，不走半刑。"""
    labels = _labels(_br("子", "卯", "酉", "酉"))
    assert "子卯无礼刑" in labels["san_xing"]
    assert not labels["ban_xing"], "子卯不应被当成半刑"


def test_zi_xing_named_zixing_not_xiangxing():
    """自刑名称统一为「辰辰自刑」等（xipan 曾用「辰辰相刑」）。"""
    labels = _labels(_br("辰", "辰", "午", "午"))
    assert "辰辰自刑" in labels["zi_xing"]
    assert "午午自刑" in labels["zi_xing"]
    assert not any("相刑" in x for x in labels["zi_xing"]), "不得再出现「相刑」写法"


def test_zi_xing_needs_duplicate_branch():
    labels = _labels(_br("辰", "午", "酉", "亥"))    # 四支各一 → 无自刑
    assert labels["zi_xing"] == ()


# ---------------- 天干 ----------------


def test_stem_he_and_chong_naming():
    """命名依知识库：甲己合土（表内不含「化」字，因合≠合化成功）、甲庚冲。"""
    he, chong = stem_relations(["甲", "己", "乙", "庚", "辛"])
    assert "甲己合土" in he
    assert "乙庚合金" in he
    assert "甲庚冲" in chong
    assert "乙辛冲" in chong


def test_gan_pair_relation_prefers_he_over_chong():
    assert gan_pair_relation("甲", "己") == "甲己合土"
    assert gan_pair_relation("甲", "庚") == "甲庚冲"
    assert gan_pair_relation("丁", "庚") == ""      # 非冲的天干相克不列
    assert gan_pair_relation("甲", "甲") == ""


def test_zhi_pair_relations_covers_four_classes():
    assert zhi_pair_relations("巳", "申") == ["巳申合水", "巳申破"]
    assert zhi_pair_relations("子", "午") == ["子午冲"]
    assert zhi_pair_relations("子", "未") == ["子未害"]
    assert zhi_pair_relations("子", "子") == []


# ---------------- 不去重（与原 analysis_calc 行为一致） ----------------


def test_repeated_branch_keeps_repeated_relation():
    """原实现按 i<j 遍历且不去重：子×2 + 丑 会对「子丑合土」出现两次。

    这是有意保留的行为差异声明：本模块不做去重，视图侧自行处理
    （xipan 已有 `_dedup`；analysis_calc 的字段是给 LLM 的列表）。
    """
    rel = _br("子", "子", "丑")
    labels = _labels(rel)
    assert labels["liu_he"] == ("子丑合土", "子丑合土"), "重复支应产生重复的六合条目"

    # 三合重复：申子辰 中 子 出现两次，三合局仍只报一次（集合判定）
    rel2 = _br("申", "子", "子", "辰")
    assert _labels(rel2)["san_he"] == ("申子辰合水局",)


# ---------------- require_from：只保留"参与支里有该集合成员"的局/刑类 ----------------


def test_require_from_drops_groups_no_member_comes_from_the_set():
    """岁运细盘口径：局/刑类必须"有岁运支参与"。

    并集判定下 子辰 是半合水（原局自成一局），但岁运只有 寅午 ⇒ 参与支一个都不来自岁运，
    这类条目不该出现在岁运栏（否则会变成一个与流年无关的固定项）。
    """
    zhis = ["子", "辰", "寅", "午"]
    assert "子辰半合水" in _labels(_br(*zhis))["ban_he"], "并集判定：原局自成一局"

    rel = branch_relations(zhis, require_from=["寅", "午"])
    assert "子辰半合水" not in rel.ban_he, "参与支都不来自 require_from ⇒ 不收"
    assert "寅午半合火" in rel.ban_he, "寅午 含 require_from 成员 ⇒ 收"


def test_require_from_keeps_groups_the_set_takes_part_in():
    """**原局已有、岁运再来属于岁运引动，必须保留**（口径是"岁运有没有参与"，不是"原局有没有"）。

    巳酉 在原局已成立；流月再来一个酉 ⇒ 参与支含酉 ⇒ 仍要报。
    """
    rel = branch_relations(["酉", "巳", "酉"], require_from=["酉"])
    assert "巳酉半合金" in rel.ban_he, "岁运支参与 ⇒ 保留（不去重）"
    assert "酉酉自刑" in rel.zi_xing, "自刑同理：酉 在 require_from 里 ⇒ 保留"


def test_require_from_never_touches_pair_relations():
    """成对关系（六合/六冲/六害/六破）按"谁与谁"成对计算，不受 require_from 影响。"""
    zhis = ["子", "午", "丑", "未", "寅", "巳"]
    full, restricted = branch_relations(zhis), branch_relations(zhis, require_from=["寅"])
    for field in ("liu_he", "chong", "hai", "po"):
        assert getattr(full, field) == getattr(restricted, field), f"{field} 不该被 require_from 影响"


def test_require_from_bounds_xing_and_hui_too():
    """三会/三刑/半刑同样按参与支过滤（不只是三合体系）。"""
    # 原局 寅巳 半刑成立；岁运 子 ⇒ 与 寅巳 无关
    rel = branch_relations(["寅", "巳", "子"], require_from=["子"])
    assert not rel.ban_xing, "寅巳半刑 与岁运子无关 ⇒ 不收"
    assert rel.hui == () and rel.san_xing == ()

    # 岁运 寅 参与 ⇒ 寅巳半刑 保留
    rel2 = branch_relations(["寅", "巳", "子"], require_from=["寅"])
    assert any("寅巳半刑" in x for x in rel2.ban_xing)

    # 三会：原局 寅卯辰 会东方木，岁运 子 ⇒ 不报；岁运 卯 ⇒ 报
    assert branch_relations(["寅", "卯", "辰", "子"], require_from=["子"]).hui == ()
    assert branch_relations(["寅", "卯", "辰", "子"], require_from=["卯"]).hui == ("寅卯辰会东方木",)
