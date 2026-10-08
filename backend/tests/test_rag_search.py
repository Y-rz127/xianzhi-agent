from app.tools.rag_search import _humanize_source, expand_knowledge_queries


def test_expand_knowledge_queries_for_career_and_liunian():
    queries = expand_knowledge_queries("今年适合跳槽换工作吗")

    assert "今年适合跳槽换工作吗" in queries
    assert any("事业" in q or "工作变动" in q for q in queries)
    assert any("大运流年" in q or "流年" in q for q in queries)


def test_expand_knowledge_queries_dedupes_and_limits():
    queries = expand_knowledge_queries("事业 财运 感情 婚姻 大运 用神")

    assert len(queries) <= 4
    assert len(queries) == len(set(queries))


def test_humanize_source_internal_docs_have_no_book_quote():
    """规则卡/断法/流程/命例库等内部参考文档不应包含书名号《》，避免 LLM 误用「《XX规则卡》原文：」格式引用。"""
    internal_files = [
        "10_事业财运规则卡.md",
        "11_婚恋关系规则卡.md",
        "12_合冲刑害规则卡.md",
        "13_大运流年咨询规则卡.md",
        "14_格局完整体系.md",
        "16_健康伤病断法.md",
        "20_子女子嗣断法.md",
        "24_标准分析流程.md",
        "27_命例案例库.md",
    ]
    for f in internal_files:
        label = _humanize_source(f)
        assert "《" not in label and "》" not in label, f"{f} 标签包含书名号: {label}"


def test_humanize_source_ancient_books_preserve_book_quote():
    """真正古籍保留书名号，以便 LLM 以「《典籍名》原文：」格式引用。"""
    ancient_files = [
        ("古籍01_渊海子平核心赋诀.md", "《渊海子平》"),
        ("古籍02_子平真诠全文摘录.md", "《子平真诠》"),
        ("古籍03_穷通宝鉴十天干十二月喜忌.md", "《穷通宝鉴》"),
        ("古籍04_滴天髓注解核心.md", "《滴天髓》"),
        ("古籍05_三命通会精选条文.md", "《三命通会》"),
        ("古籍06_神峰通考精选.md", "《神峰通考》"),
    ]
    for f, expected_book in ancient_files:
        label = _humanize_source(f)
        assert label.startswith("古籍·"), f"{f} 应以'古籍·'开头: {label}"
        assert expected_book in label, f"{f} 标签应含 {expected_book}: {label}"


def test_humanize_source_handles_empty_and_unknown():
    assert _humanize_source("") == "未分类"
    # 未登记的来源降级为去掉序号的纯文本
    assert _humanize_source("99_某未登记文档.md") == "某未登记文档"
