from app.tools.rag_search import expand_knowledge_queries


def test_expand_knowledge_queries_for_career_and_liunian():
    queries = expand_knowledge_queries("今年适合跳槽换工作吗")

    assert "今年适合跳槽换工作吗" in queries
    assert any("事业" in q or "工作变动" in q for q in queries)
    assert any("大运流年" in q or "流年" in q for q in queries)


def test_expand_knowledge_queries_dedupes_and_limits():
    queries = expand_knowledge_queries("事业 财运 感情 婚姻 大运 用神")

    assert len(queries) <= 4
    assert len(queries) == len(set(queries))
