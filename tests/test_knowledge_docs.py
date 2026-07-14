from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).parents[1] / "app" / "rag" / "knowledge_docs"


def test_rule_cards_exist_with_retrieval_keywords():
    """原有规则卡核心关键词校验（保留向后兼容）。"""
    expected = {
        "10_事业财运规则卡.md": ["事业", "财运", "跳槽", "食伤生财"],
        "11_婚恋关系规则卡.md": ["感情", "配偶宫", "复合", "结婚"],
        "12_合冲刑害规则卡.md": ["六合", "六冲", "三刑", "自刑"],
        "13_大运流年咨询规则卡.md": ["大运", "流年", "立春", "回答模板"],
    }
    for filename, keywords in expected.items():
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        for keyword in keywords:
            assert keyword in text


def test_all_knowledge_docs_present():
    """第一阶段扩容后的 13 份文档均存在且非空。"""
    expected_files = [
        "01_天干地支基础.md",
        "02_五行生克关系.md",
        "03_十神详解.md",
        "04_用神喜忌.md",
        "05_大运流年.md",
        "06_纳音五行.md",
        "07_神煞初探.md",
        "08_八字排盘基础.md",
        "09_玄学史古籍.md",
        "10_事业财运规则卡.md",
        "11_婚恋关系规则卡.md",
        "12_合冲刑害规则卡.md",
        "13_大运流年咨询规则卡.md",
    ]
    for filename in expected_files:
        path = KNOWLEDGE_DIR / filename
        assert path.exists(), f"文档缺失: {filename}"
        assert path.stat().st_size > 0, f"文档为空: {filename}"


def test_doc01_stem_branch_expanded():
    """01_天干地支基础：校验地支藏干、三合三会、十二长生、纳音全表等新增内容。"""
    text = (KNOWLEDGE_DIR / "01_天干地支基础.md").read_text(encoding="utf-8")
    for keyword in [
        "天干五合",
        "天干相冲",
        "十干性情",
        "地支藏干",
        "寅宫甲丙戊",
        "巳中丙戊庚",
        "本气",
        "余气",
        "杂气",
        "三合",
        "三会",
        "半合",
        "拱合",
        "十二长生",
        "禄",
        "刃",
        "库",
        "墓",
        "旺相休囚死",
        "纳音",
        "海中金",
        "大海水",
        "透干",
        "通根",
        "根气",
    ]:
        assert keyword in text, f"01 缺失关键词: {keyword}"


def test_doc02_five_elements_expanded():
    """02_五行生克关系：校验反生反克、通关、五行意象、真假旺衰。"""
    text = (KNOWLEDGE_DIR / "02_五行生克关系.md").read_text(encoding="utf-8")
    for keyword in [
        "反生",
        "反克",
        "火多木焚",
        "水多金沉",
        "通关",
        "五脏",
        "六腑",
        "五官",
        "行业",
        "职业",
        "病症",
        "真旺",
        "假旺",
        "真弱",
        "假弱",
        "虚旺",
    ]:
        assert keyword in text, f"02 缺失关键词: {keyword}"


def test_doc03_ten_gods_expanded():
    """03_十神详解：校验宫位分断、十神组合、男女命六亲、真假清浊。"""
    text = (KNOWLEDGE_DIR / "03_十神详解.md").read_text(encoding="utf-8")
    for keyword in [
        "年柱",
        "月柱",
        "日柱",
        "时柱",
        "官印相生",
        "伤官见官",
        "财官双美",
        "比劫夺财",
        "六亲",
        "偏财为父",
        "正财为正妻",
        "正官为夫",
        "七杀为偏夫",
        "偏印为母",
        "继母",
        "清浊",
        "混杂",
        "去杂留清",
    ]:
        assert keyword in text, f"03 缺失关键词: {keyword}"


def test_doc04_yongshen_expanded():
    """04_用神喜忌：校验三大用神体系、病药论、用神层次、四季土干湿。"""
    text = (KNOWLEDGE_DIR / "04_用神喜忌.md").read_text(encoding="utf-8")
    for keyword in [
        "扶抑用神",
        "调候用神",
        "通关用神",
        "病药论",
        "病之种类",
        "药之种类",
        "用神层次",
        "通根有力",
        "透干虚浮",
        "藏干暗用",
        "远隔无力",
        "真假用神",
        "用神被合",
        "用神被冲",
        "用神有救",
        "用神无救",
        "辰戌丑未",
        "干湿区分",
        "寒暖燥湿",
    ]:
        assert keyword in text, f"04 缺失关键词: {keyword}"


def test_doc05_dayun_expanded():
    """05_大运流年：校验起运、流月、伏吟反吟、岁运并临、流月推演。"""
    text = (KNOWLEDGE_DIR / "05_大运流年.md").read_text(encoding="utf-8")
    for keyword in [
        "起运",
        "三折一",
        "小运",
        "胎元",
        "命宫",
        "伏吟",
        "反吟",
        "岁运并临",
        "天克地冲",
        "天合地合",
        "流月",
        "流年应期",
        "换运关口",
    ]:
        assert keyword in text, f"05 缺失关键词: {keyword}"


def test_doc06_nayin_expanded():
    """06_纳音五行：校验纳音合婚、纳音格局、纳音与正五行边界。"""
    text = (KNOWLEDGE_DIR / "06_纳音五行.md").read_text(encoding="utf-8")
    for keyword in [
        "纳音合婚",
        "相生为吉",
        "相克为忌",
        "纳音格局",
        "纳音强弱",
        "正五行",
        "主次",
        "辅助",
    ]:
        assert keyword in text, f"06 缺失关键词: {keyword}"


def test_doc07_shensha_expanded():
    """07_神煞初探：校验吉神凶煞全套查法。"""
    text = (KNOWLEDGE_DIR / "07_神煞初探.md").read_text(encoding="utf-8")
    for keyword in [
        "天乙贵人",
        "禄神",
        "文昌",
        "学堂",
        "词馆",
        "红鸾",
        "天喜",
        "天月德",
        "魁罡",
        "羊刃",
        "驿马",
        "桃花",
        "孤辰",
        "寡宿",
        "亡神",
        "劫煞",
        "空亡",
        "天罗地网",
        "十恶大败",
        "华盖",
        "三奇贵人",
    ]:
        assert keyword in text, f"07 缺失关键词: {keyword}"


def test_doc08_paipan_expanded():
    """08_八字排盘基础：校验节气、早子夜子、五虎遁五鼠遁、排盘易错点。"""
    text = (KNOWLEDGE_DIR / "08_八字排盘基础.md").read_text(encoding="utf-8")
    for keyword in [
        "立春",
        "二十四节气",
        "十二节",
        "中气",
        "早子时",
        "夜子时",
        "五虎遁",
        "五鼠遁",
        "夏令时",
        "真太阳时",
        "排盘易错点",
    ]:
        assert keyword in text, f"08 缺失关键词: {keyword}"


def test_doc09_classics_index_expanded():
    """09_玄学史古籍：校验五大核心典籍索引、引经据典格式、多流派融合。"""
    text = (KNOWLEDGE_DIR / "09_玄学史古籍.md").read_text(encoding="utf-8")
    for keyword in [
        "渊海子平",
        "子平真诠",
        "穷通宝鉴",
        "滴天髓",
        "三命通会",
        "神峰通考",
        "李虚中命书",
        "千里命稿",
        "命理约言",
        "引经据典",
        "多流派融合",
        "格局法",
        "旺衰扶抑",
        "调候优先",
        "主次区分",
    ]:
        assert keyword in text, f"09 缺失关键词: {keyword}"


def test_doc10_career_expanded():
    """10_事业财运规则卡：校验八格事业适配、细分断法、财运分层、求财应期。"""
    text = (KNOWLEDGE_DIR / "10_事业财运规则卡.md").read_text(encoding="utf-8")
    for keyword in [
        "八格事业适配",
        "正官格",
        "七杀格",
        "正财格",
        "偏财格",
        "正印格",
        "偏印格",
        "食神格",
        "伤官格",
        "跳槽",
        "裸辞",
        "合伙创业",
        "投资",
        "开店",
        "副业",
        "正财稳定",
        "偏财投资",
        "比劫夺财",
        "食伤生财",
        "印旺无财",
        "求财应期",
        "回款风险",
        "负债",
        "官非破财",
    ]:
        assert keyword in text, f"10 缺失关键词: {keyword}"


def test_doc11_marriage_expanded():
    """11_婚恋关系规则卡：校验财官混杂、桃花正缘、复合分手异地晚婚二婚、结婚应期。"""
    text = (KNOWLEDGE_DIR / "11_婚恋关系规则卡.md").read_text(encoding="utf-8")
    for keyword in [
        "财星混杂",
        "官杀混杂",
        "墙内桃花",
        "墙外桃花",
        "真桃花",
        "滚浪桃花",
        "暧昧",
        "正缘",
        "复合",
        "分手",
        "异地婚姻",
        "晚婚",
        "二婚",
        "结婚应期",
        "红鸾",
        "天喜",
        "配偶宫",
        "配偶星",
        "比劫夺财",
        "伤官见官",
    ]:
        assert keyword in text, f"11 缺失关键词: {keyword}"


def test_doc12_hechong_expanded():
    """12_合冲刑害规则卡：校验力量排序、六冲轻重、三刑细分、六害、贪合忘冲。"""
    text = (KNOWLEDGE_DIR / "12_合冲刑害规则卡.md").read_text(encoding="utf-8")
    for keyword in [
        "三会局",
        "三合局",
        "六合",
        "半合",
        "拱合",
        "近冲",
        "远冲",
        "冲喜神",
        "冲忌神",
        "寅巳申",
        "无恩之刑",
        "丑未戌",
        "恃势之刑",
        "辰午酉亥",
        "自刑",
        "子未害",
        "丑午害",
        "寅巳害",
        "卯辰害",
        "申亥害",
        "酉戌害",
        "贪合忘冲",
        "贪冲忘合",
    ]:
        assert keyword in text, f"12 缺失关键词: {keyword}"


def test_doc13_dayun_consult_expanded():
    """13_大运流年咨询规则卡：校验流月断事、立春切换、岁运并临、人群差异化模板。"""
    text = (KNOWLEDGE_DIR / "13_大运流年咨询规则卡.md").read_text(encoding="utf-8")
    for keyword in [
        "立春",
        "月令切换",
        "交年过渡期",
        "流月",
        "十二地支",
        "天干上半年",
        "地支下半年",
        "岁运并临",
        "伏吟",
        "反吟",
        "天克地冲",
        "天合地合",
        "天罗地网",
        "换运关口",
        "学生问事",
        "职场人问事",
        "已婚者问事",
        "创业者问事",
        "中老年人问事",
    ]:
        assert keyword in text, f"13 缺失关键词: {keyword}"


def test_all_docs_have_classic_citations():
    """所有扩容后的规则卡均含引用典籍小节，确保引经据典可追溯。"""
    citation_files = [
        "10_事业财运规则卡.md",
        "11_婚恋关系规则卡.md",
        "12_合冲刑害规则卡.md",
        "13_大运流年咨询规则卡.md",
    ]
    for filename in citation_files:
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        assert "引用典籍" in text or "渊海子平" in text, f"{filename} 缺少典籍引用"


def test_core_classic_quotations_present():
    """校验核心典籍名句已录入知识库，确保引经据典素材可用。"""
    all_text = ""
    for md_file in KNOWLEDGE_DIR.glob("*.md"):
        all_text += md_file.read_text(encoding="utf-8")
    for quotation in [
        "有病方为贵",
        "无伤不是奇",
        "伤官见官",
        "为祸百端",
        "财为养命之源",
        "官为荣身之本",
        "甲木参天",
        "脱胎要火",
        "善神顺用",
        "恶神逆用",
    ]:
        assert quotation in all_text, f"知识库缺失典籍名句: {quotation}"


# ==================== 第二阶段新增文档校验（14-23） ====================


def test_phase2_docs_present():
    """第二阶段新增的 10 份文档均存在且非空。"""
    expected_files = [
        "14_格局完整体系.md",
        "15_六亲完整断法.md",
        "16_健康伤病断法.md",
        "17_学业功名断法.md",
        "18_官非口舌出行.md",
        "19_性格心性详断.md",
        "20_子女子嗣断法.md",
        "21_贫富层次判断.md",
        "22_男女命差异化论命.md",
        "23_流月流日断事细则.md",
    ]
    for filename in expected_files:
        path = KNOWLEDGE_DIR / filename
        assert path.exists(), f"文档缺失: {filename}"
        assert path.stat().st_size > 0, f"文档为空: {filename}"


def test_doc14_geju_expanded():
    """14_格局完整体系：校验八正格、外格、顺逆用神、格局清浊真假。"""
    text = (KNOWLEDGE_DIR / "14_格局完整体系.md").read_text(encoding="utf-8")
    for keyword in [
        "正官格",
        "七杀格",
        "正财格",
        "偏财格",
        "正印格",
        "偏印格",
        "食神格",
        "伤官格",
        "顺用",
        "逆用",
        "善神",
        "恶神",
        "从强格",
        "从弱格",
        "曲直格",
        "炎上格",
        "稼穑格",
        "从革格",
        "润下格",
        "化气格",
        "清浊",
        "真假",
        "杂气取格",
        "破格",
        "救应",
        "当顺而顺",
        "当逆而逆",
    ]:
        assert keyword in text, f"14 缺失关键词: {keyword}"


def test_doc15_liuqin_expanded():
    """15_六亲完整断法：校验父母、兄弟、配偶、子女、祖辈断法。"""
    text = (KNOWLEDGE_DIR / "15_六亲完整断法.md").read_text(encoding="utf-8")
    for keyword in [
        "父亲",
        "母亲",
        "兄弟",
        "姐妹",
        "妻子",
        "丈夫",
        "子女",
        "祖辈",
        "配偶",
        "偏财为父",
        "正印为母",
        "正财为妻",
        "正官为夫",
        "食伤为子女",
        "时柱",
        "子女宫",
        "月柱",
        "父母宫",
        "日支",
        "配偶宫",
        "缘薄",
        "得力",
        "拖累",
    ]:
        assert keyword in text, f"15 缺失关键词: {keyword}"


def test_doc16_health_expanded():
    """16_健康伤病断法：校验五行对应脏腑、羊刃七杀三刑灾病、应期。"""
    text = (KNOWLEDGE_DIR / "16_健康伤病断法.md").read_text(encoding="utf-8")
    for keyword in [
        "肝",
        "心",
        "脾",
        "肺",
        "肾",
        "胆",
        "小肠",
        "胃",
        "大肠",
        "膀胱",
        "羊刃",
        "七杀",
        "三刑",
        "血光",
        "手术",
        "车祸",
        "慢性病",
        "意外",
        "寿元",
        "用神受克",
        "调候",
    ]:
        assert keyword in text, f"16 缺失关键词: {keyword}"


def test_doc17_xueye_expanded():
    """17_学业功名断法：校验文昌、印星、伤官利学业、考公考研证书。"""
    text = (KNOWLEDGE_DIR / "17_学业功名断法.md").read_text(encoding="utf-8")
    for keyword in [
        "印星",
        "文昌",
        "伤官",
        "食神",
        "考公",
        "考研",
        "证书",
        "学历",
        "升学",
        "考试",
        "官印相生",
        "伤官佩印",
        "伤官见官",
    ]:
        assert keyword in text, f"17 缺失关键词: {keyword}"


def test_doc18_guanfei_expanded():
    """18_官非口舌出行：校验官非、牢狱、驿马、异地、搬迁。"""
    text = (KNOWLEDGE_DIR / "18_官非口舌出行.md").read_text(encoding="utf-8")
    for keyword in [
        "官非",
        "牢狱",
        "口舌",
        "小人",
        "驿马",
        "出行",
        "异地",
        "搬迁",
        "官杀混杂",
        "伤官见官",
        "三刑",
        "天罗地网",
        "辰戌冲",
    ]:
        assert keyword in text, f"18 缺失关键词: {keyword}"


def test_doc19_xingge_expanded():
    """19_性格心性详断：校验十神性格、干支性格、焦虑、人际关系。"""
    text = (KNOWLEDGE_DIR / "19_性格心性详断.md").read_text(encoding="utf-8")
    for keyword in [
        "正官",
        "七杀",
        "正印",
        "偏印",
        "比肩",
        "劫财",
        "食神",
        "伤官",
        "正财",
        "偏财",
        "甲木",
        "乙木",
        "丙火",
        "丁火",
        "焦虑",
        "人际关系",
        "上级",
        "同事",
        "朋友",
        "家人",
    ]:
        assert keyword in text, f"19 缺失关键词: {keyword}"


def test_doc20_zinv_expanded():
    """20_子女子嗣断法：校验子女数量、性别、出息、亲子、生育年份。"""
    text = (KNOWLEDGE_DIR / "20_子女子嗣断法.md").read_text(encoding="utf-8")
    for keyword in [
        "子女",
        "子女星",
        "时柱",
        "子女宫",
        "数量",
        "性别",
        "出息",
        "亲子",
        "生育",
        "添丁",
        "食神",
        "伤官",
        "枭神夺食",
    ]:
        assert keyword in text, f"20 缺失关键词: {keyword}"


def test_doc21_pinfu_expanded():
    """21_贫富层次判断：校验富贵、中产、普通、劳碌、贫贱判定。"""
    text = (KNOWLEDGE_DIR / "21_贫富层次判断.md").read_text(encoding="utf-8")
    for keyword in [
        "大富大贵",
        "中富中贵",
        "小富小贵",
        "普通",
        "劳碌",
        "贫贱",
        "巨富",
        "富",
        "中产",
        "温饱",
        "贫困",
        "格局",
        "用神",
        "财官",
        "身旺任财",
    ]:
        assert keyword in text, f"21 缺失关键词: {keyword}"


def test_doc22_nannv_expanded():
    """22_男女命差异化论命：校验男女十神取用、婚姻事业节奏差异。"""
    text = (KNOWLEDGE_DIR / "22_男女命差异化论命.md").read_text(encoding="utf-8")
    for keyword in [
        "男命",
        "女命",
        "财星为妻",
        "官星为夫",
        "财官",
        "夫子",
        "大运",
        "顺行",
        "逆行",
        "阳男",
        "阴女",
        "事业",
        "婚姻",
        "人生节奏",
        "伤官见官",
        "官杀混杂",
        "比劫夺财",
    ]:
        assert keyword in text, f"22 缺失关键词: {keyword}"


def test_doc23_liuyue_expanded():
    """23_流月流日断事细则：校验流月、流日、当月机会风险、变动应期。"""
    text = (KNOWLEDGE_DIR / "23_流月流日断事细则.md").read_text(encoding="utf-8")
    for keyword in [
        "流月",
        "流日",
        "五虎遁",
        "立春",
        "惊蛰",
        "清明",
        "立夏",
        "芒种",
        "小暑",
        "立秋",
        "白露",
        "寒露",
        "立冬",
        "大雪",
        "小寒",
        "当月",
        "机会",
        "风险",
        "变动",
        "应期",
    ]:
        assert keyword in text, f"23 缺失关键词: {keyword}"


def test_phase2_docs_have_classic_citations():
    """第二阶段新增文档均含引用典籍小节。"""
    citation_files = [
        "14_格局完整体系.md",
        "15_六亲完整断法.md",
        "16_健康伤病断法.md",
        "17_学业功名断法.md",
        "18_官非口舌出行.md",
        "19_性格心性详断.md",
        "20_子女子嗣断法.md",
        "21_贫富层次判断.md",
        "22_男女命差异化论命.md",
        "23_流月流日断事细则.md",
    ]
    for filename in citation_files:
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        assert "引用典籍" in text, f"{filename} 缺少典籍引用"


def test_phase2_zi_ping_quotation_present():
    """校验《子平真诠》核心原文已录入知识库。"""
    all_text = ""
    for md_file in KNOWLEDGE_DIR.glob("*.md"):
        all_text += md_file.read_text(encoding="utf-8")
    for quotation in [
        "八字用神",
        "专求月令",
        "财官印食",
        "煞伤劫刃",
        "配合得宜",
        "皆贵格",
    ]:
        assert quotation in all_text, f"知识库缺失《子平真诠》原文: {quotation}"


# ==================== 第三阶段古籍原文库校验（古籍01-07） ====================


def test_phase3_ancient_books_present():
    """第三阶段新增的 7 份古籍文档均存在且非空。"""
    expected_files = [
        "古籍01_渊海子平核心赋诀.md",
        "古籍02_子平真诠全文摘录.md",
        "古籍03_穷通宝鉴十天干十二月喜忌.md",
        "古籍04_滴天髓注解核心.md",
        "古籍05_三命通会精选条文.md",
        "古籍06_神峰通考精选.md",
        "古籍07_盲派实用口诀.md",
    ]
    for filename in expected_files:
        path = KNOWLEDGE_DIR / filename
        assert path.exists(), f"古籍文档缺失: {filename}"
        assert path.stat().st_size > 0, f"古籍文档为空: {filename}"


def test_guji01_yuanhaiziping():
    """古籍01《渊海子平》：校验继善篇、五言独步、四言独步、寸金搜髓论原文。"""
    text = (KNOWLEDGE_DIR / "古籍01_渊海子平核心赋诀.md").read_text(encoding="utf-8")
    for keyword in [
        "继善篇",
        "五言独步",
        "四言独步",
        "寸金搜髓论",
        "人禀天地",
        "欲知贵贱",
        "先观月令",
        "用神不可损伤",
        "取用凭于生月",
        "有病方为贵",
        "无伤不是奇",
        "木盛逢金",
        "造作栋梁之器",
        "先天何处",
        "以日为主",
        "建禄生提月",
        "造化先须看日主",
        "身旺财官多富贵",
    ]:
        assert keyword in text, f"古籍01 缺失关键词: {keyword}"


def test_guji02_zipingzhenyuan():
    """古籍02《子平真诠》：校验论用神、顺逆用神、格局高低、格局救应原文。"""
    text = (KNOWLEDGE_DIR / "古籍02_子平真诠全文摘录.md").read_text(encoding="utf-8")
    for keyword in [
        "论用神",
        "八字用神",
        "专求月令",
        "财官印食",
        "煞伤劫刃",
        "善而顺用",
        "不善而逆用",
        "当顺而顺",
        "当逆而逆",
        "配合得宜",
        "皆贵格",
        "财喜食神以相生",
        "生官以护财",
        "官喜透财以相生",
        "生印以护官",
        "印喜官煞以相生",
        "食喜身旺以相生",
        "论正官",
        "论财",
        "论印",
        "论食神",
        "论伤官",
        "论七杀",
        "格局救应",
    ]:
        assert keyword in text, f"古籍02 缺失关键词: {keyword}"


def test_guji03_qiongtongbaojian():
    """古籍03《穷通宝鉴》：校验调候总论、十天干十二月喜忌。"""
    text = (KNOWLEDGE_DIR / "古籍03_穷通宝鉴十天干十二月喜忌.md").read_text(encoding="utf-8")
    for keyword in [
        "调候总论",
        "寒命宜暖",
        "燥命宜润",
        "调候优先",
        "甲木调候",
        "乙木调候",
        "丙火调候",
        "丁火调候",
        "戊土调候",
        "己土调候",
        "庚金调候",
        "辛金调候",
        "壬水调候",
        "癸水调候",
        "三春",
        "三夏",
        "三秋",
        "三冬",
        "丙火泄秀",
        "癸水润根",
        "丙火暖之",
    ]:
        assert keyword in text, f"古籍03 缺失关键词: {keyword}"


def test_guji04_ditiansui():
    """古籍04《滴天髓》：校验通神论、旺衰论、寒暖论、流通论、十干喜忌赋文。"""
    text = (KNOWLEDGE_DIR / "古籍04_滴天髓注解核心.md").read_text(encoding="utf-8")
    for keyword in [
        "通神论",
        "天道",
        "地道",
        "人道",
        "知命",
        "欲识三元万法宗",
        "坤元合德机缄通",
        "戴天履地人为贵",
        "顺逆之机须理会",
        "旺衰论",
        "能知衰旺之真机",
        "旺中有衰",
        "衰中有旺",
        "寒暖",
        "体用",
        "流通",
        "源流",
        "通关",
        "十干喜忌",
        "甲木参天",
        "脱胎要火",
    ]:
        assert keyword in text, f"古籍04 缺失关键词: {keyword}"


def test_guji05_sanmingtonghui():
    """古籍05《三命通会》：校验天罗地网、岁运并临、咸池桃花等精选条文。"""
    text = (KNOWLEDGE_DIR / "古籍05_三命通会精选条文.md").read_text(encoding="utf-8")
    for keyword in [
        "天罗地网",
        "戌亥为天罗",
        "辰巳为地网",
        "男忌天罗",
        "女忌地网",
        "岁运并临",
        "不死自己死他人",
        "独羊刃七杀为凶",
        "财官印绶俱吉",
        "咸池",
        "桃花",
        "寅午戌见卯",
        "驿马",
        "羊刃",
        "天乙贵人",
        "文昌",
        "华盖",
        "空亡",
        "红鸾",
        "天喜",
        "六冲",
        "三刑",
        "三合",
        "三会",
        "纳音",
    ]:
        assert keyword in text, f"古籍05 缺失关键词: {keyword}"


def test_guji06_shenfengtongkao():
    """古籍06《神峰通考》：校验盖头截脚、财多身弱、六亲断法等实战断语。"""
    text = (KNOWLEDGE_DIR / "古籍06_神峰通考精选.md").read_text(encoding="utf-8")
    for keyword in [
        "盖头说",
        "截脚说",
        "天干克地支",
        "地支克天干",
        "气不流通",
        "财多身弱",
        "富屋贫人",
        "男命六亲断",
        "女命六亲断",
        "有财乃为妻",
        "有官方作子",
        "比劫断",
        "官杀混杂",
        "伤官见官",
        "食神生财",
        "七杀有制",
        "印绶护身",
        "羊刃",
    ]:
        assert keyword in text, f"古籍06 缺失关键词: {keyword}"


def test_guji07_mangpai():
    """古籍07盲派口诀：校验财运婚姻灾厄速断及书房派融合规则。"""
    text = (KNOWLEDGE_DIR / "古籍07_盲派实用口诀.md").read_text(encoding="utf-8")
    for keyword in [
        "财运速断",
        "一财是财",
        "七财从势金玉满堂",
        "食伤生财",
        "比劫夺财",
        "财库",
        "婚姻速断",
        "日柱断婚姻",
        "灾厄速断",
        "六亲速断",
        "事业速断",
        "性格速断",
        "岁运速断",
        "驿马出行断",
        "神煞速断",
        "书房派",
    ]:
        assert keyword in text, f"古籍07 缺失关键词: {keyword}"


def test_phase3_ancient_citations():
    """所有古籍文档均含典籍定位与调用规则小节。"""
    ancient_files = [
        "古籍01_渊海子平核心赋诀.md",
        "古籍02_子平真诠全文摘录.md",
        "古籍03_穷通宝鉴十天干十二月喜忌.md",
        "古籍04_滴天髓注解核心.md",
        "古籍05_三命通会精选条文.md",
        "古籍06_神峰通考精选.md",
        "古籍07_盲派实用口诀.md",
    ]
    for filename in ancient_files:
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        assert "分层调用优先级" in text or "典籍定位" in text, f"{filename} 缺少典籍定位与调用规则"


def test_phase3_ancient_original_text_present():
    """校验古籍原文核心句已录入知识库，确保引经据典素材可用。"""
    all_text = ""
    for md_file in KNOWLEDGE_DIR.glob("*.md"):
        all_text += md_file.read_text(encoding="utf-8")
    for quotation in [
        "人禀天地",
        "欲知贵贱",
        "用神不可损伤",
        "有病方为贵",
        "无伤不是奇",
        "八字用神",
        "专求月令",
        "财官印食",
        "煞伤劫刃",
        "当顺而顺",
        "当逆而逆",
        "能知衰旺之真机",
        "甲木参天",
        "脱胎要火",
        "戌亥为天罗",
        "辰巳为地网",
        "岁运并临",
        "不死自己死他人",
        "财多身弱",
        "富屋贫人",
        "一财是财",
        "七财从势金玉满堂",
    ]:
        assert quotation in all_text, f"知识库缺失古籍原文: {quotation}"


# ==================== 第四阶段实战辅助文档校验（24-27） ====================


def test_phase4_docs_present():
    """第四阶段新增的 4 份实战辅助文档均存在且非空。"""
    expected_files = [
        "24_标准分析流程.md",
        "25_术语白话对照表.md",
        "26_问答模板库.md",
        "27_命例案例库.md",
    ]
    for filename in expected_files:
        path = KNOWLEDGE_DIR / filename
        assert path.exists(), f"文档缺失: {filename}"
        assert path.stat().st_size > 0, f"文档为空: {filename}"


def test_doc24_standard_flow_expanded():
    """24_标准分析流程：校验八步法、排盘、定旺衰、定格局、取用神、查岁运、断事、建议。"""
    text = (KNOWLEDGE_DIR / "24_标准分析流程.md").read_text(encoding="utf-8")
    for keyword in [
        "标准分析流程",
        "八步法",
        "核生辰",
        "排四柱",
        "定旺衰",
        "定格局",
        "取用神",
        "查岁运",
        "分宫位断事",
        "综合结论给建议",
        "立春",
        "五虎遁",
        "五鼠遁",
        "早子时",
        "夜子时",
        "得令",
        "得地",
        "得势",
        "真假旺衰",
        "月令本气",
        "杂气月",
        "调候优先",
        "扶抑",
        "通关",
        "善神顺用",
        "恶神逆用",
        "大运",
        "流年",
        "伏吟",
        "反吟",
        "岁运并临",
        "天克地冲",
        "引经据典",
    ]:
        assert keyword in text, f"24 缺失关键词: {keyword}"


def test_doc25_terminology_expanded():
    """25_术语白话对照表：校验天干地支、十神、格局、合冲刑害、岁运、六亲术语白话对照。"""
    text = (KNOWLEDGE_DIR / "25_术语白话对照表.md").read_text(encoding="utf-8")
    for keyword in [
        "天干",
        "地支",
        "六十甲子",
        "五虎遁",
        "五鼠遁",
        "阴阳",
        "五行",
        "相生",
        "相克",
        "年柱",
        "月柱",
        "日柱",
        "时柱",
        "比肩",
        "劫财",
        "食神",
        "伤官",
        "偏财",
        "正财",
        "七杀",
        "正官",
        "偏印",
        "正印",
        "官印相生",
        "伤官见官",
        "食神生财",
        "比劫夺财",
        "官杀混杂",
        "格局",
        "用神",
        "忌神",
        "扶抑用神",
        "调候用神",
        "通关用神",
        "病药论",
        "六合",
        "三合",
        "三会",
        "六冲",
        "三刑",
        "六害",
        "天乙贵人",
        "羊刃",
        "驿马",
        "桃花",
        "华盖",
        "空亡",
        "有病方为贵",
        "无伤不是奇",
        "财多身弱",
        "富屋贫人",
    ]:
        assert keyword in text, f"25 缺失关键词: {keyword}"


def test_doc26_qa_template_expanded():
    """26_问答模板库：校验事业财运、婚恋感情、健康灾厄、子女家庭、学业考试、流年大运问答模板。"""
    text = (KNOWLEDGE_DIR / "26_问答模板库.md").read_text(encoding="utf-8")
    for keyword in [
        "问答模板",
        "标准回答结构",
        "先说结论",
        "再说依据",
        "最后说建议",
        "事业财运",
        "跳槽",
        "创业",
        "财运",
        "婚恋感情",
        "正缘",
        "结婚",
        "复合",
        "离婚",
        "健康灾厄",
        "子女家庭",
        "子女运",
        "子女有出息",
        "学业考试",
        "考试能过吗",
        "流年大运",
        "今年运势",
        "换大运",
        "适合做什么",
        "引经据典",
        "主次区分",
    ]:
        assert keyword in text, f"26 缺失关键词: {keyword}"


def test_doc27_case_library_expanded():
    """27_命例案例库：校验古籍经典命例、典型命局结构示范、命例分析方法。"""
    text = (KNOWLEDGE_DIR / "27_命例案例库.md").read_text(encoding="utf-8")
    for keyword in [
        "命例案例库",
        "命例使用规范",
        "古籍经典命例",
        "渊海子平",
        "侍郎命造",
        "从杀格",
        "滴天髓阐微",
        "任铁樵",
        "浊气",
        "疾病章",
        "三命通会",
        "万民英",
        "典型命局结构示范",
        "官印相生",
        "食神生财",
        "正官格",
        "建禄格",
        "身弱财多",
        "伤官见官",
        "伤官合杀",
        "三刑",
        "时柱喜用",
        "命例分析方法",
        "标准分析流程",
        "多流派融合",
        "主次区分",
        "命例分类索引",
        "富贵命",
        "普通命",
        "贫贱命",
        "不得生搬硬套",
    ]:
        assert keyword in text, f"27 缺失关键词: {keyword}"


def test_phase4_docs_have_classic_citations():
    """第四阶段新增文档均含引用典籍小节。"""
    citation_files = [
        "24_标准分析流程.md",
        "25_术语白话对照表.md",
        "26_问答模板库.md",
        "27_命例案例库.md",
    ]
    for filename in citation_files:
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        assert "引用典籍" in text, f"{filename} 缺少典籍引用"


def test_phase4_practical_quotations_present():
    """校验第四阶段实战辅助文档核心句已录入知识库。"""
    all_text = ""
    for md_file in KNOWLEDGE_DIR.glob("*.md"):
        all_text += md_file.read_text(encoding="utf-8")
    for quotation in [
        "八步法",
        "核生辰",
        "排四柱",
        "定旺衰",
        "定格局",
        "取用神",
        "查岁运",
        "分宫位断事",
        "先说结论",
        "再说依据",
        "最后说建议",
        "官印相生",
        "伤官见官",
        "食神生财",
        "比劫夺财",
        "善神顺用",
        "恶神逆用",
        "当顺而顺",
        "当逆而逆",
    ]:
        assert quotation in all_text, f"知识库缺失实战辅助原文: {quotation}"
