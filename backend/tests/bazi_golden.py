"""黄金命盘快照的构建 / 投影 / 比对逻辑（供 test 与 script 共用）。

为什么需要它：`domain/shensha_calc._compute_shensha`（513 行）与
`workflow_messages.check_facts`（451 行）历史上都出过"AST 解析通过、import 成功、
运行静默错"的事故——灾煞/吊客/病符三段曾被缩进错位成永不命中的死代码。
按行拆分这类巨型函数前，必须先有一组"改动前后输出逐字段全等"的锚点。

三条设计决定：

1. **时间必须钉死**。`build_bazi_chart` 的细盘里有"当前岁运"快照，取自系统当天。
   故快照固定 `REFERENCE_DATE`，并显式传 `liunian_start_year` + `today`。
2. **原局神煞要单独取**。`BaziChart.to_dict()` 里**没有** `_compute_shensha(pillars)`
   的结果（它只在 `chart_to_api_dict` 里挂上），而原局神煞正是拆分目标，必须显式调用。
3. **超大且低信息量的段只存指纹**。`xipan.liuyue`（12 月 ×120 年）、
   `xipan.liunian`、`xipan.ganzhiMeta`（60 甲子表）三者合计约占单例 86% 的体积，
   逐字段存会让快照膨胀到不可读。这三段改为存 `{_count, _sha256}`——
   仍然能捕获任何变化（测试会报出是哪一段），需要看内容时用
   `scripts/golden_bazi.py --show <case_id> <path>` 导出。
4. **domain 符号统一从门面 `app.domain.bazi_engine` 导入**。`format_fact_context`
   等符号此前只有门面一条路径，测试若改从子模块导入会凭空制造"同一符号两条路径"
   （`test_architecture.py::test_no_dual_path_symbol_imports` 会直接报错）。
   那 28 个双路径符号要等阶段 4 拆门面时**整体**迁移，新代码不先开分叉。
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.domain.chart_builder import (
    _compute_shensha,
    build_bazi_chart,
    parse_gender,
)
from app.domain.chart_format import format_fact_context

# 快照基准：所有时间相关输出都以这一天为"当下"。
# 改动它 = 全量快照失效，需重新生成并人工确认差异。
REFERENCE_DATE = "2026-09-15"
LIUNIAN_START_YEAR = 2026

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bazi_golden"
CASES_FILE = FIXTURE_DIR / "cases.json"

# 只存指纹的 xipan 段（按体积排序，合计约占单例 86%）
DIGEST_ONLY_XIPAN_KEYS = ("liuyue", "liunian", "ganzhiMeta")

# 必填字段：任何一项缺失都说明命盘结构变了，测试应直接失败而不是静默通过
REQUIRED_TOP_KEYS = (
    "birth",
    "pillars",
    "wuxing",
    "analysis",
    "dayun",
    "liunian",
    "xipan",
    "start_yun",
    "warnings",
)


# ---------------- 取样与构建 ----------------


def load_cases() -> list[dict[str, Any]]:
    data = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    return data["cases"]


# 快照钉死、不允许用例覆盖的参数（否则快照会随日期漂移）
PINNED_PARAMS = ("today", "liunian_start_year")


def case_params(case: dict[str, Any]) -> dict[str, Any]:
    """用例的自定义参数 + 钉死的时间基准。"""
    params = dict(case.get("params") or {})
    clash = [k for k in PINNED_PARAMS if k in params]
    if clash:
        raise AssertionError(f"用例不得覆盖快照钉死参数 {clash}（case={case['id']}）")
    params["liunian_start_year"] = LIUNIAN_START_YEAR
    params["today"] = datetime.date.fromisoformat(REFERENCE_DATE)
    return params


def build_case_chart(case: dict[str, Any]):
    """构建命盘**对象**（非 dict），供需要 BaziChart 实例的测试复用（如 check_facts）。"""
    return build_bazi_chart(case["birth"], case["gender"], **case_params(case))


def find_case(case_id: str) -> dict[str, Any]:
    """按 id 取用例；不存在则报错并列出可选 id。"""
    for case in load_cases():
        if case["id"] == case_id:
            return case
    raise KeyError(f"未找到用例 {case_id}，可选：{[c['id'] for c in load_cases()]}")


def build_case_snapshot(case: dict[str, Any]) -> dict[str, Any]:
    """构建一个命盘的完整快照（已投影）。"""
    chart = build_bazi_chart(case["birth"], case["gender"], **case_params(case))
    chart_dict = _project(chart.to_dict())

    missing = [k for k in REQUIRED_TOP_KEYS if k not in chart_dict]
    if missing:
        raise AssertionError(f"命盘缺少必需字段 {missing}（case={case['id']}）")

    return {
        "id": case["id"],
        "desc": case["desc"],
        "birth": case["birth"],
        "gender": case["gender"],
        "params": case.get("params") or {},
        "chart": chart_dict,
        # 原局神煞：to_dict 里没有，必须显式取（阶段 3 的拆分目标）
        "shensha_pillars": _compute_shensha(chart.pillars, parse_gender(chart.birth.gender)),
        # LLM 事实上下文全文：改动这里会直接影响生成与审核，值得逐字比对
        "fact_context": format_fact_context(chart),
    }


def _project(chart_dict: dict[str, Any]) -> dict[str, Any]:
    """把超大 xipan 段替换为指纹。"""
    out = dict(chart_dict)
    xipan = dict(out.get("xipan") or {})
    for key in DIGEST_ONLY_XIPAN_KEYS:
        if key in xipan:
            xipan[key] = _digest(xipan[key])
    out["xipan"] = xipan
    return out


def _digest(obj: Any) -> dict[str, Any]:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "_digest_only": True,
        "_count": len(obj),
        "_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def raw_xipan_section(case: dict[str, Any], key: str) -> Any:
    """取未投影的 xipan 段（供 `--show` 排查指纹变化）。"""
    chart = build_bazi_chart(case["birth"], case["gender"], **case_params(case))
    return (chart.to_dict().get("xipan") or {}).get(key)


# ---------------- 快照读写 ----------------


def snapshot_path(case_id: str) -> Path:
    return FIXTURE_DIR / f"{case_id}.json"


def write_snapshot(snapshot: dict[str, Any]) -> Path:
    """写入快照；内容无变化则**不落盘**。

    刻意跳过相同内容：`UPDATE_GOLDEN=1` 会遍历全部用例，
    若无条件写盘，全部文件的 mtime 都会更新、`git diff` 变成"全都变了"，
    人工核对时看不出到底哪几例受影响。跳过相同内容后，
    变更范围可以直接从 `git status` / mtime 读出来。
    """
    path = snapshot_path(snapshot["id"])
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == payload:
        return path
    path.write_text(payload, encoding="utf-8")
    return path


def read_snapshot(case_id: str) -> dict[str, Any]:
    return json.loads(snapshot_path(case_id).read_text(encoding="utf-8"))


def update_enabled() -> bool:
    return os.environ.get("UPDATE_GOLDEN", "").strip() not in ("", "0", "false", "False")


# ---------------- 逐字段比对 ----------------


# 列表元素的标识键候选（用于把"长度 20→19"细化成"哪一条没了"）
_IDENTITY_KEYS = ("name", "id", "year", "ganzhi", "date")


def _identity_key(items: Any) -> str | None:
    """若列表元素都是带同一标识键的 dict，返回该键名。

    只用于**长度不同**时定位差异条目；长度相同时仍走逐位比对，
    因为神煞/大运列表的**顺序本身有语义**，按标识索引会掩盖顺序错乱。
    """
    if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
        return None
    for key in _IDENTITY_KEYS:
        if all(key in i for i in items):
            return key
    return None


def diff_paths(expected: Any, actual: Any, path: str = "") -> list[str]:
    """递归比对，返回形如 `xipan.current.liunian` 的差异路径。

    只报告**路径**不报告值，避免把长中文串糊满终端；排查用 `--show`。
    """
    if type(expected) is not type(actual):
        return [f"{path or '<root>'}: 类型 {type(expected).__name__} → {type(actual).__name__}"]

    if isinstance(expected, dict):
        out: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            sub = f"{path}.{key}" if path else key
            if key not in expected:
                out.append(f"{sub}: 新增字段")
            elif key not in actual:
                out.append(f"{sub}: 字段消失")
            else:
                out.extend(diff_paths(expected[key], actual[key], sub))
        return out

    if isinstance(expected, list):
        if len(expected) != len(actual):
            located = _locate_by_identity(expected, actual, path)
            if located:
                return located
            return [f"{path or '<root>'}: 列表长度 {len(expected)} → {len(actual)}"]
        out = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            out.extend(diff_paths(e, a, f"{path}[{i}]"))
        return out

    if expected != actual:
        return [f"{path or '<root>'}: 值已变"]
    return []


def _locate_by_identity(expected: list, actual: list, path: str) -> list[str]:
    """长度变化时，按标识键指出到底是哪几条消失/新增。

    "shensha_pillars: 列表长度 20 → 19" 这种提示定位不到问题；
    报 `shensha_pillars[name=灾煞]: 条目消失` 才能直接指出是哪个神煞不再命中。
    """
    key = _identity_key(expected) or _identity_key(actual)
    if key is None:
        return []

    e_map = {str(i[key]): i for i in expected}
    a_map = {str(i[key]): i for i in actual}
    out: list[str] = []
    for ident in sorted(set(e_map) | set(a_map)):
        sub = f"{path}[{key}={ident}]"
        if ident not in e_map:
            out.append(f"{sub}: 新增条目")
        elif ident not in a_map:
            out.append(f"{sub}: 条目消失")
        else:
            out.extend(diff_paths(e_map[ident], a_map[ident], sub))
    return out


def get_by_path(obj: Any, dotted: str) -> Any:
    """按 `a.b[0].c` 取值（供 --show）。"""
    cur = obj
    for part in dotted.split(".") if dotted else []:
        if "[" in part:
            name, idx = part[:-1].split("[")
            cur = cur[name][int(idx)]
        else:
            cur = cur[part]
    return cur


# ---------------- 神煞名册提取 ----------------


def shensha_names_declared() -> set[str]:
    """从 `shensha_calc` 源码提取「可产出」的神煞名集合。

    两个坑：
    1. 该模块已**包化**，`find_spec().origin` 指向 `__init__.py`（里面没有产出语句），
       必须遍历包内全部模块，否则返回空集、断言形同虚设。
    2. 拆族后产出形式有三种，正则 `add\\("..."` 只能命中第一种：
       `add("X", ...)` 调用、`yield ("X", ...)` 元组、
       查表用的三元组 `("X", TABLE, "desc")`。故用 AST。
    """
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("app.domain.shensha_calc")
    if spec is None:  # pragma: no cover - 模块必然存在
        return set()

    roots = [Path(p) for p in (spec.submodule_search_locations or [])]
    paths = (
        [p for root in roots for p in sorted(root.glob("*.py"))]
        if roots
        else [Path(spec.origin)]
    )

    names: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "add"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                names.add(node.args[0].value)
            elif isinstance(node, ast.Yield) and isinstance(node.value, ast.Tuple) and node.value.elts:
                first = node.value.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.add(first.value)
            elif isinstance(node, ast.Tuple) and len(node.elts) == 3:
                first, second = node.elts[0], node.elts[1]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and isinstance(second, ast.Name)
                ):
                    names.add(first.value)
    return names
