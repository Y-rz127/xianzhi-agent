"""上游 LLM 的**配置类错误**识别、一次性上报与子模型启动探活。

为什么需要这个模块
------------------
上游对"模型能力与请求参数不匹配"的拒绝是**永久性**的：同一个请求重试多少次都一样，
而且失败点往往藏在某个兜底分支里。2026-09-19 的现场：

    reviewer 用 glm-5.3，而 `main.py::_make_model` 把 `enable_thinking` 写死 False
    → 每一轮审核都 400 `InvalidParameter ... the enable_thinking parameter is restricted to True`
    → `_llm_review` 的 except 吞掉，返回 `FactCheckResult(ok=True, source="regex_fallback")`
    → 日志里只有一行 WARNING，答案照常输出，**第二层（LLM）审核实际上从未运行**。

这里做三件事，让这类错误不再以"静默降级"的形式存在：

1. `is_thinking_restricted()`：把它与"网络抖动/限流"这类**偶发**失败区分开 ——
   偶发失败继续走 WARNING + 降级重试，永久性配置错误走 ERROR + 独立指标。
2. `report_once()`：永久性错误每轮都会复现，按 key 只报一次，避免刷屏把日志淹掉
   （刷屏的结果是没人看，等同于没报）。
3. `probe_sub_models()`：启动时对意图拆解 / Reviewer 两个子模型各发一次最小请求。
   若发现"该模型只接受思考模式"，自动改成 `enable_thinking=True` 重建并复探，
   把静默失败变成**启动即自愈 + 一条明确的环境变量提示**。

放 `core/` 是因为它只依赖 logger 与 langchain 消息类型，不碰任何业务包
（`test_architecture.py` 要求 core 不得依赖业务层）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from langchain_core.messages import HumanMessage

from app.core.logger import log

# 探活请求的提示词：内容不重要，只看上游是否**接受**这次请求
_PING = "ping"

# 上游文案里唯一稳定的锚点：参数名本身要在。
# 后缀判据刻意收窄到"限制/只支持"语义，避免把"enable_thinking 不被支持"这类
# 别的 400 也当成同一类问题（那类的修法是**去掉**参数，不是改成 True）。
_THINKING_PARAM = "enable_thinking"
_THINKING_MARKERS = ("restricted", "only support", "only accept", "must be true", "只能为", "仅支持", "限制为")


def is_thinking_restricted(exc: BaseException | str) -> bool:
    """上游是否在说「这个模型只接受 enable_thinking=True」。

    实测文案：``InternalError.Algo.InvalidParameter: The value of the enable_thinking
    parameter is restricted to True.``
    """
    text = str(exc).lower()
    if _THINKING_PARAM not in text:
        return False
    return any(marker in text for marker in _THINKING_MARKERS)


# ---- 同一 key 只报一次 ----

_reported: set[str] = set()
_reported_lock = threading.Lock()


def report_once(key: str, level: str, message: str, *args: Any) -> bool:
    """同一 key 只输出一次日志，返回本次是否真的输出了。

    用于**永久性**错误：它们在每一轮请求里复现，逐轮打印只会把日志刷满。
    偶发错误不要用这个（那些正需要看频率）。
    """
    with _reported_lock:
        if key in _reported:
            return False
        _reported.add(key)
    getattr(log, level)(message, *args)
    return True


def reset_reported_once(key: str | None = None) -> None:
    """清掉"已报过"的标记（测试用；进程内一般不需要）。"""
    with _reported_lock:
        if key is None:
            _reported.clear()
        else:
            _reported.discard(key)


# ---- 子模型启动探活 ----


@dataclass
class SubModelSpec:
    """一个待探活的子模型。

    Args:
        label: 人类可读用途（日志用），如「意图拆解」。
        attr: `AppContext` 上的字段名 —— 探活纠正后就地替换（首次请求前完成，会话 Agent 随后才按需创建）。
        env_key: 对应的环境变量名，用于在提示里直接给出该改哪一行。
        model_name: 模型名（留空的角色不会进这个列表）。
        enable_thinking: 当前配置的思考开关。
        rebuild: 用新的思考开关重建模型实例（保证除该开关外其余参数与运行时完全一致）。
    """

    label: str
    attr: str
    env_key: str
    model_name: str
    enable_thinking: bool
    rebuild: Callable[[bool], Any]
    model: Any = None


@dataclass
class ProbeResult:
    label: str
    model_name: str
    ok: bool
    enable_thinking: bool
    fixed: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


def _ping(model: Any) -> None:
    """一次最小请求：只为确认上游接受这组参数，不关心内容。"""
    model.invoke([HumanMessage(content=_PING)])


def probe_sub_models(specs: Sequence[SubModelSpec], app_ctx: Any = None) -> list[ProbeResult]:
    """逐个探活子模型；**不抛异常**（跑在启动后台任务里，探活失败不该影响服务）。

    只在识别到"该模型只接受思考模式"时自动纠正（改 True 重建 + 复探），
    其余失败原样报 ERROR —— 不猜测、不静默改配置。
    """
    results: list[ProbeResult] = []
    for spec in specs:
        result = ProbeResult(
            label=spec.label,
            model_name=spec.model_name,
            ok=False,
            enable_thinking=spec.enable_thinking,
        )
        try:
            model = spec.model if spec.model is not None else spec.rebuild(spec.enable_thinking)
        except Exception as e:  # noqa: BLE001 —— 构造失败同样只上报
            result.error = f"构造失败: {e}"
            log.error("[探活] {} 模型 {} 重建失败（不影响服务）: {}", spec.label, spec.model_name, e)
            results.append(result)
            continue
        try:
            _ping(model)
            result.ok = True
            log.info(
                "[探活] {} 模型 {} 可用（enable_thinking={}）",
                spec.label,
                spec.model_name,
                spec.enable_thinking,
            )
        except Exception as e:  # noqa: BLE001 —— 探活必须吞掉一切，只如实上报
            result.error = str(e)
            if not is_thinking_restricted(e):
                log.error(
                    "[探活] {} 模型 {} 不可用（不是 thinking 配置问题，请照原文排查）: {}",
                    spec.label,
                    spec.model_name,
                    e,
                )
            elif spec.enable_thinking:
                # 已经开着思考还被拒：说明不是这个开关的问题，别再自动改
                log.error(
                    "[探活] {} 模型 {} 已配 enable_thinking=true 仍被拒，请照原文排查: {}",
                    spec.label,
                    spec.model_name,
                    e,
                )
            else:
                try:
                    fixed_model = spec.rebuild(True)
                    _ping(fixed_model)
                except Exception as e2:  # noqa: BLE001
                    result.error = str(e2)
                    log.error(
                        "[探活] {} 模型 {} 切成 enable_thinking=true 后仍失败: {}",
                        spec.label,
                        spec.model_name,
                        e2,
                    )
                else:
                    result.ok = True
                    result.fixed = True
                    result.enable_thinking = True
                    spec.model = fixed_model
                    if app_ctx is not None:
                        setattr(app_ctx, spec.attr, fixed_model)
                    log.warning(
                        "[探活] {} 模型 {} **只接受思考模式**，已自动改 enable_thinking=true 重建生效。\n"
                        "  → 请在 .env 显式写上 {}_ENABLE_THINKING=true（自动纠正只在本次进程内有效，"
                        "配置仍写着 false 时下次启动会再走一遍探活）",
                        spec.label,
                        spec.model_name,
                        spec.env_key.removesuffix("_ENABLE_THINKING"),
                    )
        results.append(result)
    return results
