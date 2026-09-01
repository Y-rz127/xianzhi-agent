"""神煞计算：以四柱 + 月支推算全部神煞命中。"""
from __future__ import annotations

from app.domain.models import Pillar
from app.domain.tables import (
    BA_ZHUAN,
    BING_FU,
    BRANCH_ORDER,
    CHONG_ZHI,
    CI_GUAN,
    DE_XIU,
    DIAO_KE,
    FU_XING,
    GONG_LU,
    GU_CHEN,
    GU_LUAN,
    GUA_SU,
    GUO_YIN,
    HONG_LUAN,
    HONG_YAN,
    HUA_GAI,
    JIANG_XING,
    JIE_SHA,
    JIN_SHEN,
    JIN_YU,
    JIU_CHOU,
    KUI_GANG,
    LIU_XIA,
    LIU_XIU,
    LU_SHEN,
    PI_MA,
    SAN_QI,
    SANG_MEN,
    SEASON_OF_BRANCH,
    SHI_E_DA_BAI,
    SHI_LING,
    SI_FEI,
    TAI_JI,
    TAO_HUA,
    TIAN_CHU,
    TIAN_DE_HE,
    TIAN_DE_IS_BRANCH,
    TIAN_DE_MONTH,
    TIAN_DI_ZHUAN,
    TIAN_SHE,
    TIAN_XI,
    TIAN_YI,
    TIAN_YI_MED,
    WANG_SHEN,
    WEN_CHANG,
    XUE_REN,
    XUE_TANG,
    YANG_REN,
    YI_MA,
    YIN_CHA_YANG_CUO,
    YUE_DE_HE,
    YUE_DE_MONTH,
    ZAI_SHA,
    ZHENG_CI_GUAN,
    ZHENG_XUE_TANG,
)


def _zhi_to_month_index(zhi: str) -> int:
    """地支 → 农历月份索引。寅=1, 卯=2, ..., 子=11, 丑=12"""
    m = {"寅": 1, "卯": 2, "辰": 3, "巳": 4, "午": 5, "未": 6,
         "申": 7, "酉": 8, "戌": 9, "亥": 10, "子": 11, "丑": 12}
    return m.get(zhi, 0)


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

    # 一、以日干/年干查的神煞
    year_nayin_wx = pillars[0].nayin[-1] if pillars[0].nayin else ""

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

    # 学堂/词馆：按年柱纳音查月日时三柱（不含年柱自身）；
    # 正学堂/正词馆为精确位（干支全配），同柱命中"正X"时不再报"X"
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
            if p.zhi in cg and p.name not in zheng_cg_pillars:
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

    # 二、以月支查的神煞（天德、月德 — 需四柱天干见对应字）
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
        # 月德贵人只查四柱天干：口诀"亥卯未月甲干栖"中的"干"即天干，查藏干会误报三合木局
        for c in yuede_chars:
            for p in pillars:
                if p.gan == c:
                    add("月德贵人", "天干见{}，化煞解厄".format(c), p.name)

    # 天德合：卯/午/酉/子月天德是地支，天德合查 p.zhi；其余月天德是天干，天德合查 p.gan
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

    # 三、以年支/日支查的神煞（排除自身柱位：年支查时排除年柱、日支查时排除日柱）
    for key_zhi, skip_idx in ((year_zhi, 0), (day_zhi, 2)):

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

    # 四、以年支查的专属神煞（吊客/病符/天医等传统只以年支查）
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

    # 血刃（以月支查四柱，含月柱自身）："亥月→亥"自映射，不能像余三支那样跳过月柱
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
        gou = _adv(year_zhi, 3)
        jiao = _adv(year_zhi, -3)
    else:
        gou = _adv(year_zhi, -3)
        jiao = _adv(year_zhi, 3)
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

    # 五、特殊组合类神煞（日柱组合 / 日柱纳音 / 日时配合等）
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

    # 三奇贵人：天干顺次连续、不可颠倒间隔，仅认 年-月-日 / 月-日-时 两个连续窗口
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

    # 童子煞：依月令季节 + 年柱纳音，判断日/时支是否落口诀「春秋寅子贵，冬夏卯未辰；金木马卯合，水火鸡犬多；土命逢辰巳」
    def _check_tongzi(zhi: str) -> bool:
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

    if _check_tongzi(day_zhi):
        add("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "日柱")
    if len(pillars) > 3 and _check_tongzi(pillars[3].zhi):
        add("童子煞", "运气多阻、易遇小人，婚姻迟缓，宜修道艺", "时柱")

    # 飞刃（羊刃对冲位）
    if yangren:
        feiren_zhi = CHONG_ZHI.get(yangren, "")
        if feiren_zhi:
            for p in pillars:
                if p.zhi == feiren_zhi:
                    add("飞刃", f"羊刃{yangren}对冲{feiren_zhi}，刚烈更甚、主突发伤害", p.name)

    # 六、空亡（年柱+日柱旬空双查，任一落空即标记）
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
