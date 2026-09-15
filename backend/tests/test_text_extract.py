"""流式/WS 文本归一化的单测 + 去重回归守卫。

背景：`normalize_chunk_text` / `normalize_ws_payload_text` 原先在
hehun / liuyao / ziwei 三个子应用里各复制了一份（逐字节相同的 6 份，共 174 行），
任一处修 bug 都不会同步到其余处。现已收敛到 app/core/text_extract.py。

本文件做两件事：
1. 参数化覆盖四类输入（list / dict / 超长 / 对象 repr），锁住归一化口径；
2. 守卫：子应用内不得再出现本地副本（防"以后又复制一份"）。

注意：tarot 另有一套行为不同的实现（见 app/core/text_extract.py 模块 docstring），
不在本测试的守卫范围内。
"""

from __future__ import annotations

import ast
import os

import pytest

from app.core.text_extract import normalize_chunk_text, normalize_ws_payload_text

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# 子应用中不得再出现本地副本的函数名
DEDUPED_FUNCTIONS = ("_normalize_chunk_text", "_normalize_ws_payload_text", "normalize_chunk_text",
                     "normalize_ws_payload_text")


# ---------------- normalize_chunk_text ----------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, ""),
        ("", ""),
        ("  hi  ", "hi"),
        # 注意：str 输入是直接透传的——长度/噪声防护只作用于下方的兜底分支
        ("x" * 250, "x" * 250),
        ("<__main__.Obj object at 0x7f>", "<__main__.Obj object at 0x7f>"),
        ("object at 0x1", "object at 0x1"),
        ([], ""),
        (["a", "b"], "a b"),
        ([{"text": "t1"}, "t2"], "t1 t2"),
        ([{"other": "x"}], ""),                 # list 内无 text 字段 → 无内容
        (["", "  "], ""),
        ({}, ""),
        ({"text": "abc"}, "abc"),
        ({"text": "  pad  "}, "pad"),
        ({"content": "c"}, "c"),
        ({"delta": "d"}, "d"),
        ({"result": "r"}, "r"),
        ({"a": "short"}, ""),                   # 兜底要求 > 20 字符
        ({"a": "y" * 25}, "y" * 25),
        ({"a": "<xml>"}, ""),                   # 以 "<" 开头视为噪声
        # chunk 版不含 choices 分支，OpenAI 风格载荷取不到内容
        ({"choices": [{"delta": {"content": "x"}}]}, ""),
        (123, "123"),
        (1.5, "1.5"),
        (object(), ""),                         # repr 含 "object at 0x"
    ],
)
def test_normalize_chunk_text(raw, expected) -> None:
    assert normalize_chunk_text(raw) == expected


# ---------------- normalize_ws_payload_text ----------------


@pytest.mark.parametrize(
    "data, expected",
    [
        (None, ""),
        ("", ""),
        ("  hi  ", "hi"),
        ("x" * 250, "x" * 250),                 # 同 chunk 版：str 直接透传
        ({"text": "abc"}, "abc"),
        ({"text": "  pad  "}, "pad"),
        ({"content": "c"}, "c"),
        # WS 版独有的 OpenAI 兼容分支
        ({"choices": [{"delta": {"content": "from-choices"}}]}, "from-choices"),
        ({"choices": []}, ""),
        ({"choices": "notalist"}, ""),          # choices 非 list → 落到兜底，短串不足阈值
        ({"a": "short"}, ""),
        ({"a": "y" * 25}, "y" * 25),
        ({"a": "<xml>"}, ""),
        ({"a": "z" * 25 + "object at 0x"}, ""),  # 兜底额外排除 object repr
        (123, "123"),
        (object(), ""),
    ],
)
def test_normalize_ws_payload_text(data, expected) -> None:
    assert normalize_ws_payload_text(data) == expected


def test_noise_guard_only_applies_to_fallback_branch() -> None:
    """记录一处刻意的行为不对称：噪声串作为 str 传入时原样保留。

    同一个"对象 repr"文本，直接当 str 传会返回原串，而作为其他对象传入
    会走兜底分支被丢弃。调用方传的都是 `chunk.content`，命中哪条分支取决于
    模型把 content 给成 str 还是对象，故这里显式固化，避免后人"顺手统一"改坏。
    """
    noisy = "<__main__.Obj object at 0x7f>"
    assert normalize_chunk_text(noisy) == noisy
    assert normalize_chunk_text(noisy.encode()) == ""   # bytes → 兜底分支 → 丢弃


def test_ws_version_handles_choices_but_chunk_version_does_not() -> None:
    """两个函数的差异点：只有 WS 版识别 {"choices":[{"delta":...}]} 结构。"""
    payload = {"choices": [{"delta": {"content": "hi"}}]}
    assert normalize_ws_payload_text(payload) == "hi"
    assert normalize_chunk_text(payload) == ""


# ---------------- 去重回归守卫 ----------------


def test_sub_apps_do_not_redefine_normalizers() -> None:
    """子应用内不得再定义本地副本——否则重复代码会重新长回来。"""
    offenders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(APP_DIR, "sub_app")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        # tarot 的变体属已知的待统一项，暂不纳入守卫
        if os.path.basename(dirpath) == "tarot":
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in DEDUPED_FUNCTIONS:
                    rel = os.path.relpath(path, APP_DIR).replace("\\", "/")
                    offenders.append(f"{rel}:{node.lineno} {node.name}")
    assert not offenders, (
        "子应用内又出现了归一化函数的本地定义，请改用 app.core.text_extract：\n  "
        + "\n  ".join(offenders)
    )
