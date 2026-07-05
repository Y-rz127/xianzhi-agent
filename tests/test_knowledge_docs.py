from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).parents[1] / "app" / "rag" / "knowledge_docs"


def test_rule_cards_exist_with_retrieval_keywords():
    expected = {
        "10_事业财运规则卡.md": ["事业", "财运", "跳槽", "食伤生财"],
        "11_婚恋关系规则卡.md": ["感情", "配偶宫", "复合", "结婚年份"],
        "12_合冲刑害规则卡.md": ["六合", "六冲", "三刑", "自刑"],
        "13_大运流年咨询规则卡.md": ["大运", "流年", "立春", "回答模板"],
    }
    for filename, keywords in expected.items():
        text = (KNOWLEDGE_DIR / filename).read_text(encoding="utf-8")
        for keyword in keywords:
            assert keyword in text
