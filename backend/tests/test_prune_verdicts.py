"""`scripts/prune_verdicts.py` 的判据：哪些终审行已经取不到。

纯函数部分单测（不连库）。为什么要测：删裁决是**不可逆的运维动作**，
判据写错会连"当前版本的有效裁决"一起清掉，之后每张盘都要重花一次 LLM 调用。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "prune_verdicts", _BACKEND / "scripts" / "prune_verdicts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


PRUNE = _load_script()
CURRENT = "20261024.1"


def _row(engine="20261024.1", prompt="v9", status="ok"):
    return {
        "chart_hash": "h",
        "birth_time": "2004-06-22 07:28",
        "gender": "男",
        "engine_version": engine,
        "prompt_version": prompt,
        "status": status,
        "created_at": "",
    }


def test_current_engine_and_prompt_is_kept():
    bad, why = PRUNE.is_obsolete(_row(), CURRENT)
    assert bad is False and why == ""


def test_old_engine_is_obsolete_even_with_current_prompt():
    """引擎一 bump，旧引擎上的行永久取不到（缓存按 engine_version 过滤）。"""
    bad, why = PRUNE.is_obsolete(_row(engine="20261012.1"), CURRENT)
    assert bad is True and "engine" in why


def test_min_prompt_prunes_older_prompt():
    assert PRUNE.is_obsolete(_row(prompt="v7"), CURRENT, "v8")[0] is True
    assert PRUNE.is_obsolete(_row(prompt="v8"), CURRENT, "v8")[0] is False
    # v10 > v8：按数字比，不能被字符串比较坑掉
    assert PRUNE.is_obsolete(_row(prompt="v10"), CURRENT, "v8")[0] is False


def test_missing_or_unparsable_versions_count_as_obsolete():
    assert PRUNE.is_obsolete(_row(engine=None), CURRENT)[0] is True
    assert PRUNE.is_obsolete(_row(prompt=""), CURRENT, "v8")[0] is True
    assert PRUNE.is_obsolete(_row(prompt="garbage"), CURRENT, "v8")[0] is True


def test_invalid_status_alone_is_not_a_reason():
    """只有版本口径决定去留；`invalid` 状态的行若版本当前仍保留（排查要留证据）。"""
    assert PRUNE.is_obsolete(_row(status="invalid"), CURRENT)[0] is False
