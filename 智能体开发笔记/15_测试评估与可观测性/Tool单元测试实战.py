"""Tool 单元测试示例。

运行方式：
pytest "15_测试评估与可观测性/Tool单元测试实战.py"
"""

from __future__ import annotations

import pytest
from langchain.tools import tool


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


def test_multiply_direct_invoke() -> None:
    assert multiply.invoke({"a": 6, "b": 7}) == 42


def test_multiply_schema_rejects_missing_arg() -> None:
    with pytest.raises(Exception):
        multiply.invoke({"a": 6})

