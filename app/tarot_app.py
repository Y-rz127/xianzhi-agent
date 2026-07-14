"""塔罗占卜应用。

- 78 张完整牌组（22 大阿卡纳 + 56 小阿卡纳）
- 抽牌在后端完成（Fisher-Yates 洗牌，不可预测）
- LLM 流式解读：根据问题 + 牌阵 + 正逆位组合给出深度解读
"""
from __future__ import annotations

import random
from typing import AsyncIterator, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.logger import log


# ============ 牌组数据 ============

class TarotCard:
    __slots__ = ("name", "name_en", "emblem", "arcana", "suit", "meaning", "reversed_meaning")

    def __init__(self, name: str, name_en: str, emblem: str, arcana: str,
                 suit: str, meaning: str, reversed_meaning: str):
        self.name = name
        self.name_en = name_en
        self.emblem = emblem
        self.arcana = arcana  # "major" | "minor"
        self.suit = suit       # "major" | "wands" | "cups" | "swords" | "pentacles"
        self.meaning = meaning
        self.reversed_meaning = reversed_meaning

    def to_dict(self, is_reversed: bool) -> dict:
        return {
            "name": self.name,
            "nameEn": self.name_en,
            "emblem": self.emblem,
            "arcana": self.arcana,
            "suit": self.suit,
            "isReversed": is_reversed,
            "meaning": self.reversed_meaning if is_reversed else self.meaning,
        }


# 22 张大阿卡纳
_MAJOR_ARCANA: list[TarotCard] = [
    TarotCard("愚者", "The Fool", "☆", "major", "major",
              "新的开始、冒险、天真无邪。是时候勇敢迈出第一步，相信宇宙的指引。",
              "鲁莽、犹豫不决。你需要停下来重新审视当前的处境，不要盲目行动。"),
    TarotCard("魔术师", "The Magician", "✦", "major", "major",
              "创造力、技能、意志力。你拥有实现目标所需的一切资源，现在是行动的时候。",
              "欺骗、能力不足。你可能在浪费自己的才华，或被表象迷惑。"),
    TarotCard("女祭司", "The High Priestess", "☽", "major", "major",
              "直觉、潜意识、神秘。静下心来倾听内心的声音，答案就在你心中。",
              "忽视直觉、情绪封闭。你与内心的连接被切断，需要重新建立信任。"),
    TarotCard("女皇", "The Empress", "♔", "major", "major",
              "丰饶、母性、感官享受。创造力与滋养的能量充沛，享受生活的美好。",
              "依赖、停滞。过度依赖他人或物质享受，忽视了内在成长。"),
    TarotCard("皇帝", "The Emperor", "⚔", "major", "major",
              "权威、秩序、掌控。建立规则和结构，用理性与纪律引导自己。",
              "专制、失控。你可能过于强势，或缺乏自律导致混乱。"),
    TarotCard("教皇", "The Hierophant", "✠", "major", "major",
              "传统、导师、精神指引。遵循传统智慧，寻求导师或制度的帮助。",
              "叛逆、盲目追随。你可能被困在陈规中，或盲目追随权威。"),
    TarotCard("恋人", "The Lovers", "♥", "major", "major",
              "爱情、选择、和谐。面临重要抉择，跟随内心做出真诚的决定。",
              "分离、错误选择。关系中可能出现裂痕，需要真诚沟通。"),
    TarotCard("战车", "The Chariot", "⚡", "major", "major",
              "胜利、意志力、前进。克服困难，通过坚定的意志力取得胜利。",
              "失控、失败。你可能失去了方向，需要重新掌控局面。"),
    TarotCard("力量", "Strength", "♌", "major", "major",
              "勇气、耐心、内在力量。以柔克刚，用爱与耐心驯服内心的野兽。",
              "软弱、恐惧。你被恐惧支配，需要找回内在的力量。"),
    TarotCard("隐士", "The Hermit", "✶", "major", "major",
              "内省、孤独、智慧。退一步反思，寻找内心的光明与真理。",
              "孤立、逃避。过度的孤独变成了逃避，需要重新连接外界。"),
    TarotCard("命运之轮", "Wheel of Fortune", "☸", "major", "major",
              "命运、转折、机遇。命运的齿轮转动，好运即将到来，抓住机会。",
              "厄运、停滞。你可能处于低谷，但变化是必然的，保持信念。"),
    TarotCard("正义", "Justice", "⚖", "major", "major",
              "公正、真相、因果。种瓜得瓜，真理必将显现，做出公正的决定。",
              "不公、逃避责任。你可能在逃避应承担的责任或真相。"),
    TarotCard("倒吊人", "The Hanged Man", "〰", "major", "major",
              "牺牲、换个视角、等待。暂停行动，换个角度看问题，会有新的领悟。",
              "固执、无谓牺牲。你不愿改变视角，导致停滞不前。"),
    TarotCard("死神", "Death", "☠", "major", "major",
              "结束、转变、重生。旧的不去新的不来，接受改变，迎接新生。",
              "抗拒改变、停滞。你拒绝放手，导致无法获得新的成长。"),
    TarotCard("节制", "Temperance", "≈", "major", "major",
              "平衡、调和、耐心。寻找中庸之道，调和内在的矛盾，保持平衡。",
              "失衡、过度。你可能在某个方面走极端，需要回归平衡。"),
    TarotCard("恶魔", "The Devil", "♄", "major", "major",
              "束缚、欲望、阴影。直面内心的欲望和恐惧，认识自己的阴暗面。",
              "解脱、觉醒。你正在摆脱束缚，看清真相，获得自由。"),
    TarotCard("高塔", "The Tower", "▲", "major", "major",
              "突变、崩塌、觉醒。突如其来的改变打破旧有结构，虽然痛苦但是必要的。",
              "抗拒改变、危机延迟。你在逃避不可避免的改变，但终究要面对。"),
    TarotCard("星星", "The Star", "★", "major", "major",
              "希望、灵感、治愈。黑暗中看到了光芒，保持信念，未来充满希望。",
              "绝望、失去信心。你可能感到迷茫，但希望从未真正离开。"),
    TarotCard("月亮", "The Moon", "☾", "major", "major",
              "幻觉、恐惧、潜意识。面对内心的恐惧，穿越迷雾方能看清真相。",
              "恐惧消散、真相显现。迷雾正在散去，真相即将揭晓。"),
    TarotCard("太阳", "The Sun", "☀", "major", "major",
              "快乐、成功、活力。阳光普照，一切顺利，享受生命的美好时刻。",
              "暂时的阴霾、热情减退。快乐被暂时遮蔽，但太阳终会再次升起。"),
    TarotCard("审判", "Judgement", "♫", "major", "major",
              "觉醒、重生、召唤。听到内心的召唤，做出改变，迎接新生。",
              "拒绝觉醒、自我怀疑。你忽视了内心的召唤，需要重新审视。"),
    TarotCard("世界", "The World", "⬡", "major", "major",
              "完成、圆满、成就。一个周期的圆满结束，你已经达成了目标。",
              "未完成、拖延。你接近完成但尚未达成，需要最后一步努力。"),
]


def _minor(suit: str, suit_cn: str, emblem: str, theme: str, rev_theme: str,
           numbers: list[tuple[str, str, str]]) -> list[TarotCard]:
    """批量生成小阿卡纳某花色的 14 张牌。

    numbers: [(牌名, 正位含义, 逆位含义), ...] 共 14 项
    """
    out: list[TarotCard] = []
    for cn_name, pos, rev in numbers:
        en_name = f"{cn_name} of {suit_cn}"
        out.append(TarotCard(cn_name, en_name, emblem, "minor", suit, pos, rev))
    return out


# 权杖 Wands 🔥 - 行动、激情、创造
_WANDS = _minor(
    "wands", "Wands", "🜂", "行动与激情", "冲动与耗竭",
    [
        ("权杖王牌", "新行动的萌芽，灵感火花点燃，充满动力与热情。", "拖延、缺乏方向。热情被熄灭，需要重新点燃内在火焰。"),
        ("权杖二", "规划与抉择，站在十字路口展望未来。", "犹豫不决、恐惧未知。不敢迈出舒适区，错失良机。"),
        ("权杖三", "远见与扩展，计划开始展现成果，眺望远方。", "目光短浅、阻碍。计划受阻，需要调整方向。"),
        ("权杖四", "庆祝、稳定、归属感。收获阶段性成果，值得欢庆。", "动荡、缺乏归属。过渡期不稳，需要重建根基。"),
        ("权杖五", "竞争、冲突、思想碰撞。良性竞争激发潜能。", "内耗、无谓争斗。冲突失去建设性，需要停止。"),
        ("权杖六", "胜利、认可、荣耀。努力获得回报，受到赞誉。", "失败、失去认可。寻求外界认同而忽视内在价值。"),
        ("权杖七", "捍卫、坚守立场。守护已得的成果，迎接挑战。", "压力过大、孤军奋战。感到力不从心，需要支援。"),
        ("权杖八", "快速变化、消息来临。事情加速推进，保持敏捷。", "混乱、方向不明。变化太快失去掌控，需要聚焦。"),
        ("权杖九", "坚韧、最后防线。坚持到最后，胜利在望。", "疲惫、防御过当。过度紧张消耗精力，需要放松。"),
        ("权杖十", "重担、责任。承担过多，接近极限。", "放下重担、转嫁责任。学会拒绝，释放压力。"),
        ("权杖侍从", "探索、学习新事物。充满好奇与热情的初学者。", "半途而废、注意力分散。缺乏专注，需要深耕。"),
        ("权杖骑士", "冒险、进取、冲劲十足。追寻梦想的行动派。", "鲁莽、三分钟热度。行动前缺乏思考，容易燃尽。"),
        ("权杖皇后", "热情、自信、魅力四射。用温暖感染他人。", "嫉妒、控制欲。热情变成占有，需要给彼此空间。"),
        ("权杖国王", "领导力、远见、魄力。天生的领袖与开拓者。", "专横、自负。权力使人盲目，需要谦逊。"),
    ],
)

# 圣杯 Cups 💧 - 情感、关系、直觉
_CUPS = _minor(
    "cups", "Cups", "🜄", "情感与关系", "情绪失衡",
    [
        ("圣杯王牌", "新情感萌芽，爱意涌动，心灵打开。", "情感封闭、压抑。感受被堵塞，需要释放。"),
        ("圣杯二", "相互吸引、 partnership、心灵契合。", "关系破裂、误解。双方渐行渐远，需要重新连接。"),
        ("圣杯三", "欢庆、友谊、分享喜悦。社交与聚会。", "社交疲劳、流言蜚语。关系表面化，需要深度。"),
        ("圣杯四", "沉思、冷漠、忽略眼前的机会。", "倦怠、逃避现实。对一切提不起兴趣，需要重新振作。"),
        ("圣杯五", "失落、悲伤、专注于失去。", "释怀、向前看。从悲伤中走出，看到希望。"),
        ("圣杯六", "怀旧、童年回忆、纯真的情感。", "沉溺过去、不愿长大。过度美化回忆，错过当下。"),
        ("圣杯七", "幻想、诱惑、选择迷茫。", "迷雾散去、看清真相。从幻觉中清醒，做出选择。"),
        ("圣杯八", "离开、寻找更深意义。主动转身。", "逃避、害怕孤独。不敢离开舒适却又不满的现状。"),
        ("圣杯九", "满足、愿望成真。心想事成的喜悦。", "自满、表面满足。物质丰盈但内心空虚。"),
        ("圣杯十", "家庭、圆满、长久幸福。情感归宿。", "家庭矛盾、失和。表面和谐下暗藏裂痕。"),
        ("圣杯侍从", "直觉、情感敏锐。善于倾听的小天使。", "情绪化、幼稚。情感不成熟，需要成长。"),
        ("圣杯骑士", "浪漫、追求、理想主义。追梦的骑士。", "幻想破灭、不切实际。浪漫变成空想。"),
        ("圣杯皇后", "同理心、温柔、滋养他人。情感的守护者。", "情绪失控、过度依赖。为他人牺牲自己。"),
        ("圣杯国王", "情感成熟、平衡、智慧。以柔克刚。", "情感操控、阴郁。压抑情绪变成冷暴力。"),
    ],
)

# 宝剑 Swords 💨 - 思维、真相、冲突
_SWORDS = _minor(
    "swords", "Swords", "🜁", "思维与真相", "冲突与混乱",
    [
        ("宝剑王牌", "清晰、决断、真相显现。突破性的洞察。", "混乱、错误判断。思绪不清，需要冷静。"),
        ("宝剑二", "僵局、平衡、回避选择。蒙眼站在十字路口。", "打破僵局、做出决定。不再逃避，直面真相。"),
        ("宝剑三", "心碎、悲伤、痛苦。必要的切割带来疗愈。", "释怀、走出阴影。痛苦过后迎来新生。"),
        ("宝剑四", "休息、恢复、静养。暂停以积蓄力量。", "倦怠、被迫停滞。休息变成逃避，需要行动。"),
        ("宝剑五", "冲突、损失、空洞的胜利。赢了却失去人心。", "和解、释怀。放下胜负，寻求双赢。"),
        ("宝剑六", "过渡、远离困境。在水面上平稳前行。", "停滞、无法放下。过去的阴影仍在拖累。"),
        ("宝剑七", "策略、暗中行动、谨慎。", "欺骗、背信。小心不诚实的诱惑。"),
        ("宝剑八", "束缚、自我设限。被恐惧困住。", "解放、看清束缚来自自己。重获自由。"),
        ("宝剑九", "焦虑、失眠、深夜的恐惧。", "走出焦虑、看见希望。恐惧被夸大，真相没那么糟。"),
        ("宝剑十", "终结、谷底、彻底的结束。黎明前最黑暗。", "重生、复苏。触底反弹，新的开始。"),
        ("宝剑侍从", "好奇、敏锐、求知欲强。善于观察。", "多疑、八卦。言辞伤人，需要谨慎。"),
        ("宝剑骑士", "果断、直言、行动迅速。", "鲁莽、好斗。锋芒伤人，需要收敛。"),
        ("宝剑皇后", "清醒、理性、洞察真相。用智慧守护。", "冷漠、苛刻。理性过度变成绝情。"),
        ("宝剑国王", "公正、权威、判断分明。以理服人。", "冷酷、独断。权力使人疏离。"),
    ],
)

# 星币 Pentacles 🌍 - 物质、财富、现实
_PENTACLES = _minor(
    "pentacles", "Pentacles", "🜃", "物质与现实", "匮乏与停滞",
    [
        ("星币王牌", "新机会、物质丰盛、机遇降临。", "错失机会、匮乏。需要把握眼前的良机。"),
        ("星币二", "平衡、灵活、多任务处理。", "失衡、应接不暇。需要专注，减少分散。"),
        ("星币三", "协作、技艺、团队配合。", "不协调、各自为政。需要重新磨合。"),
        ("星币四", "稳固、占有、守成。", "吝啬、过度控制。抓得太紧反而失去。"),
        ("星币五", "困难、匮乏、寒夜。物质或精神上的困境。", "走出困境、获得援助。难关将过。"),
        ("星币六", "慷慨、给予、平衡的交换。", "施舍失衡、有条件的给予。需要真诚。"),
        ("星币七", "等待、评估成果、耐心。", "焦虑、急功近利。急于求成反而破坏。"),
        ("星币八", "精进、专注、工匠精神。", "粗心、缺乏耐心。需要打磨技艺。"),
        ("星币九", "丰盛、独立、自给自足。享受自己创造的成果。", "空虚、物质依赖。拥有却仍不满足。"),
        ("星币十", "家族传承、长久积累、富裕。", "家族纷争、遗产纠纷。财富成为负担。"),
        ("星币侍从", "学习、务实、脚踏实地。", "好高骛远、不肯吃苦。需要从基础做起。"),
        ("星币骑士", "勤勉、可靠、稳步前行。", "固执、保守。缺乏变通，错失新机。"),
        ("星币皇后", "滋养、丰盛、与自然连接。享受生活的丰盛。", "依赖、物质焦虑。安全感外求。"),
        ("星币国王", "富有、成就、掌控现实。物质世界的王者。", "贪婪、守财奴。被物质奴役。"),
    ],
)


# 完整 78 张牌组
DECK: list[TarotCard] = _MAJOR_ARCANA + _WANDS + _CUPS + _SWORDS + _PENTACLES
assert len(DECK) == 78, f"牌组数量错误: {len(DECK)}"


# ============ 牌阵定义 ============

SpreadKey = Literal["daily", "three_card", "relationship"]

SPREADS: dict[str, dict] = {
    "daily": {
        "name": "每日一牌",
        "desc": "一张牌，看今日运势指引",
        "count": 1,
        "positions": ["今日指引"],
    },
    "three_card": {
        "name": "过去现在未来",
        "desc": "三张牌，梳理时间脉络",
        "count": 3,
        "positions": ["过去", "现在", "未来"],
    },
    "relationship": {
        "name": "关系牌阵",
        "desc": "三张牌，解读人际缘分",
        "count": 3,
        "positions": ["你自己", "对方", "关系"],
    },
}


# ============ 系统提示词 ============

SYSTEM_PROMPT = """你是"塔罗师"，一位神秘的塔罗牌占卜师，从事占卜数十年，对牌面象征学有深刻理解。

身份与能力：
- 精通 78 张塔罗牌的象征意义，包括大阿卡纳的原型力量与小阿卡纳的日常映射
- 能从牌阵组合中读出连贯的叙事，而非孤立解读单张牌
- 尊重塔罗传统，但解读有现代洞察力

解读结构（严格遵守）：
1. 先一句话点出本次牌阵的整体基调
2. 逐张解读每张牌在对应位置的含义（结合正逆位）
3. 综合三张牌的关联，给出整体叙事
4. 最后给一条具体可执行的建议

说话风格（重要）：
- 神秘但有洞察力，不说空话套话
- 用"你"称呼问卜者，像面对面占卜
- 不用 emoji 结尾，不用表格，不用太多小标题
- 适当使用塔罗术语但不要堆砌，让普通人能懂
- 该直白时直白，塔罗不是回避真相的工具
- 长度控制：单张牌 2-3 句话，整体解读不超过 4-5 段
- 避免"总结一下""需要注意的是"这类 AI 模板腔

解读原则：
- 基于牌面客观解读，不刻意说好话也不制造恐惧
- 逆位牌不是"坏牌"，它提示能量阻塞或需要觉察的部分
- 牌义要落到问卜者的具体问题上，不要泛泛而谈
- 不预测绝对未来，塔罗是镜子不是水晶球
"""


# ============ 业务类 ============

class TarotApp:
    def __init__(self, chat_model: BaseChatModel):
        self.chat_model = chat_model

    def draw_cards(self, spread: SpreadKey) -> list[dict]:
        """根据牌阵抽牌（后端洗牌，不可预测）。

        Returns:
            list[dict]: 每张牌的字典表示（含 isReversed 和 meaning）
        """
        spread_info = SPREADS.get(spread, SPREADS["daily"])
        count = spread_info["count"]

        # Fisher-Yates 洗牌
        deck = list(DECK)
        random.shuffle(deck)

        drawn: list[dict] = []
        for i in range(count):
            card = deck[i]
            is_reversed = random.random() < 0.5
            drawn.append(card.to_dict(is_reversed))
        return drawn

    async def divine_stream(
        self,
        question: str,
        spread: SpreadKey,
        cards: list[dict],
    ) -> AsyncIterator[str]:
        """LLM 流式解读（带 fallback）。

        Args:
            question: 用户的问题（可为空，空则用"今日运势指引"）
            spread: 牌阵 key
            cards: draw_cards 返回的牌组数据
        """
        spread_info = SPREADS.get(spread, SPREADS["daily"])
        positions = spread_info["positions"]
        spread_name = spread_info["name"]

        # 构造牌阵描述
        card_lines: list[str] = []
        for i, c in enumerate(cards):
            pos = positions[i] if i < len(positions) else f"位置{i + 1}"
            orientation = "逆位" if c["isReversed"] else "正位"
            card_lines.append(
                f"位置「{pos}」：{orientation} {c['name']}（{c['nameEn']}）\n"
                f"  牌义：{c['meaning']}"
            )
        cards_text = "\n".join(card_lines)

        q = question.strip() if question and question.strip() else "今日运势指引"

        user_prompt = f"""请为以下塔罗占卜做深度解读：

问卜者的问题：{q}
牌阵：{spread_name}

抽到的牌：
{cards_text}

请按照系统提示中的结构解读：整体基调 → 逐张牌解读 → 综合叙事 → 具体建议。
解读要落到问卜者的具体问题上。"""

        msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
        try:
            has_any_chunk = False
            async for chunk in self.chat_model.astream(msgs):
                text = chunk.content
                if text:
                    has_any_chunk = True
                    yield text
            if not has_any_chunk:
                # LLM 返回空，fallback
                log.warning("塔罗 LLM 返回空片段，使用 fallback 解读")
                for piece in self._fallback_reading(question, spread, cards):
                    yield piece
        except Exception as e:
            log.exception("塔罗 LLM 解读失败，使用 fallback")
            # 先发送错误提示，再 fallback
            yield f"\n\n[AI 解读暂不可用：{type(e).__name__}]\n\n"
            for piece in self._fallback_reading(question, spread, cards):
                yield piece

    def _fallback_reading(
        self, question: str, spread: SpreadKey, cards: list[dict]
    ) -> list[str]:
        """当 LLM 不可用时，返回基于牌面基础信息的解读。"""
        spread_info = SPREADS.get(spread, SPREADS["daily"])
        positions = spread_info["positions"]
        spread_name = spread_info["name"]
        q = question.strip() if question and question.strip() else "今日运势指引"

        lines: list[str] = []
        lines.append(f"你问的是：{q}。牌阵选择：{spread_name}。\n\n")
        for i, c in enumerate(cards):
            pos = positions[i] if i < len(positions) else f"位置{i + 1}"
            orientation = "逆位" if c["isReversed"] else "正位"
            lines.append(
                f"位置「{pos}」抽到{orientation}「{c['name']}」：{c['meaning']}\n\n"
            )
        # 简单综合
        names = "、".join(c["name"] for c in cards)
        lines.append(
            f"\n三张牌「{names}」组合在一起，呈现出一个由过去经由现在通往未来的完整脉络。"
            f"建议结合你的具体处境综合考量，倾听内心的声音。\n"
            f"\n（本次占卜为牌面基础解读，深度 AI 解读暂不可用，请稍后再试。）"
        )
        return lines
