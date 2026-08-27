from app.liuyao.liuyao_app import cast


def test_number_cast_returns_complete_hexagram():
    result = cast("numbers", [17, 29])

    assert result["method"] == "numbers"
    assert len(result["lines"]) == 6
    assert result["original"]["name"]
    assert all(line["value"] in {6, 7, 8, 9} for line in result["lines"])


def test_time_cast_is_a_valid_six_line_result():
    result = cast("time")

    assert result["method"] == "time"
    assert len(result["movingLines"]) <= 6
    assert result["changed"] is None or result["changed"]["name"]
