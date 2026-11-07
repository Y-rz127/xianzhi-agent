"""文本清洗工具：LLM 输出后处理。

- 移除 thinking... response 推理过程标签（Qwen3 等推理模型）
- 处理未闭合的 thinking 标签（流式中断场景）
- 检测并移除完全重复的内容（think 块泄漏兜底）
- 剥离模型回显的用户输入边界标记（`--- USER INPUT BEGIN/END ---`）
"""
from __future__ import annotations

import re

from app.core.logger import log

# 编译正则，避免每次调用重新编译
_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$", re.IGNORECASE)

# 防御：剥离模型回显的用户输入边界标记（防止 LLM 把 "--- USER INPUT BEGIN/END ---" 原样当作回答输出）
_USER_INPUT_BOUNDARY_RE = re.compile(
    r"---\s*USER\s+INPUT\s+BEGIN\s*---[\s\S]*?---\s*USER\s+INPUT\s+END\s*---"
)

# 检索资料隔离标记：模型可能把标记原样复述给用户，只剥标记、保留正文
_DATA_MARKER_RE = re.compile(r"<<<\s*/?\s*DATA_(?:BEGIN|END)[^>]*>>>", re.IGNORECASE)


def strip_think_marks(content: str) -> str:
    """移除 ReAct/思考式标记块（[思考]…[/思考]、<thinking>…</thinking> 等），含未闭合残尾。

    与 ThinkStreamGuard 同开/闭标签口径：流式发送侧由 guard 过滤，返回的完整文本
    用本函数做同口径清洗，保证「用户看到的」与「落库/防重放缓存」一致。
    clean_think_tags 只处理 <thinking> 族；本函数额外覆盖 [思考]/[行动]/[观察] 族。
    """
    if not content:
        return content
    for op, cl in zip(_THINK_OPEN_MARKS, _THINK_CLOSE_MARKS):
        content = re.sub(re.escape(op) + r"[\s\S]*?" + re.escape(cl), "", content)
        content = re.sub(re.escape(op) + r"[\s\S]*$", "", content)
    return content.strip()


def clean_think_tags(content: str) -> str:
    """移除 LLM 输出中的 thinking 推理过程标签（含未闭合的流式中断场景）。"""
    if not content:
        return content
    content = _THINK_BLOCK_RE.sub("", content)
    content = _THINK_OPEN_RE.sub("", content)
    return content.strip()


def dedupe_content(content: str) -> str:
    """检测内容前后完全重复（推理模型 think 块泄漏），只保留前半部分。"""
    content = content.strip()
    if len(content) < 100:
        return content
    mid = len(content) // 2
    first_half = content[:mid].strip()
    second_half = content[mid:].strip()
    if first_half == second_half and len(first_half) > 50:
        log.warning("检测到 LLM 输出内容重复，已去重（长度 {}）", len(first_half))
        return first_half
    return content


def strip_user_input_boundary(content: str) -> str:
    """移除 LLM 回答里回显的 ```--- USER INPUT BEGIN/END ---``` 边界块及其包裹的复述内容。

    用户输入被 `_wrap_user_input` 包上边界标记以防指令注入；若模型把整段标记连同
    用户原话一并当回答输出，这里一次性剥掉，保证用户永远看不到内部标记。
    所有生成路径（Workflow / 闲聊短路）都应调用，统一防护、避免各自为政漏剥。

    **注意方向**：这里是把 `--- BEGIN --- ... --- END ---` **整块删掉**（连正文一起），
    只适合"清洗模型输出"。要**取出**被包裹的正文（落库去重、回显还原），用
    `app.agent.core.base_agent.unwrap_user_input` —— 用反了会拿到空串，去重永远不命中。
    """
    if not content:
        return content
    cleaned = _USER_INPUT_BOUNDARY_RE.sub("", content)
    cleaned = _DATA_MARKER_RE.sub("", cleaned)
    # 清理剥离后可能残留的多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


# ───────────────────────── 流式发送守卫 ─────────────────────────

# 流式下「生成完整后再 clean_think_tags」失效——token 已经逐块出去了。
# 思考标记开/闭标签配对。
# 口径必须与 clean_think_tags / strip_think_marks 一致，否则「发给用户的」与「落库的」不同：
# - "<think>...</think>"（Qwen3/DashScope 实际输出，**无字母 g**）——最常见，漏掉它会把
#   模型内心推理原样发给用户；
# - "<thinking>...</thinking>"（部分服务端/前端 isThinking 口径）；
# - "[思考]/[行动]/[观察]"（本项目 ReAct 协议，前端 isThinking 也认这三个）。
_THINK_OPEN_MARKS = ("<think>", "<thinking>", "[思考]", "[行动]", "[观察]")
_THINK_CLOSE_MARKS = ("</think>", "</thinking>", "[/思考]", "[/行动]", "[/观察]")


class ThinkStreamGuard:
    """逐 token 发送前的思考块过滤：滞后窗口内识别开标签 → 抑制直到闭标签。

    文本后处理（clean_think_tags）只能作用于完整文本；流式模式下 token 已发出，
    必须在发送侧拦一道。原理：开标签最多 7 字符，滞后窗口（默认 16 字符）保证
    开标签完整落在窗口内可被识别；识别后进入抑制态，吞掉直到配对的闭标签结束。

    兼容跨 chunk 断裂：抑制态只保留「闭标签长度-1」的尾部字符，避免闭标签被
    拆在两次 feed 之间导致永久吞掉后续正文。生成结束调用 flush() 放行窗口内
    剩余正文；抑制态未闭合的残余（思考没写完）直接丢弃。
    """

    def __init__(self, lag: int = 16) -> None:
        self._lag = max(lag, 8)
        self._pending = ""
        # None=正常态；非 None=处于思考块内，等待这个闭标签出现。
        self._suppress_close: str | None = None

    @staticmethod
    def _find_open(text: str) -> tuple[int, str] | None:
        best_i, best_close = -1, ""
        for op, cl in zip(_THINK_OPEN_MARKS, _THINK_CLOSE_MARKS):
            i = text.find(op)
            if i >= 0 and (best_i < 0 or i < best_i):
                best_i, best_close = i, cl
        return (best_i, best_close) if best_i >= 0 else None

    def feed(self, text: str) -> str:
        """喂入增量文本，返回应发给用户的正文（可能为空/多段）。

        状态机：
        - 正常态：命中开标签 → 先吐出开标签之前的正文，转入抑制态；
        - 抑制态：命中闭标签 → 丢弃闭标签及其之前的内容（思考块），恢复正常态，
          **闭标签之后的内容必须继续走正常路径**（不能一起丢掉）；
        - 抑制态未命中闭标签 → 整段吞掉，只保留尾部窗口用于跨 chunk 识别闭标签；
        - 正常态未命中开标签 → 按滞后窗口吐出正文，保留尾部窗口用于跨 chunk 识别开标签。
        """
        if not text:
            return ""
        self._pending += text
        out: list[str] = []

        while True:
            if self._suppress_close is not None:
                close = self._suppress_close
                i = self._pending.find(close)
                if i < 0:
                    # 仍在思考块内：只保留「闭标签长度-1」尾部（可能含半个闭标签），
                    # 其余（含思考内容）一律吞掉，**绝不能当正文发出**。
                    keep = len(close) - 1
                    self._pending = self._pending[-keep:] if keep > 0 else ""
                    break
                self._suppress_close = None
                self._pending = self._pending[i + len(close) :]
                continue

            hit = self._find_open(self._pending)
            if hit is None:
                break
            i, close = hit
            out.append(self._pending[:i])
            self._pending = self._pending[i:]
            self._suppress_close = close

        if self._suppress_close is None and len(self._pending) > self._lag:
            # 正常态：按滞后窗口吐出正文（保留尾部窗口用于跨 chunk 识别开标签）
            out.append(self._pending[: -self._lag])
            self._pending = self._pending[-self._lag :]
        return "".join(out)

    def flush(self) -> str:
        """生成结束：放行窗口内残余正文；未闭合的抑制残余丢弃。"""
        if self._suppress_close is not None:
            self._suppress_close = None
            self._pending = ""
            return ""
        out, self._pending = self._pending, ""
        return out


# ─────────────────── 用户输入边界标记的流式过滤 ───────────────────

# 与 strip_user_input_boundary 的正则同口径（允许 "--- USER INPUT BEGIN ---" 的空格变体）。
# 边界块可能跨 chunk，故发送侧需要一个与 ThinkStreamGuard 同构的滞后窗口守卫。
_USER_INPUT_BEGIN_RE = re.compile(r"---\s*USER\s+INPUT\s+BEGIN\s*---")
_USER_INPUT_END_RE = re.compile(r"---\s*USER\s+INPUT\s+END\s*---")


class UserInputBoundaryGuard:
    """流式剥除模型回显的 USER INPUT 边界块（含被包裹的用户原话）。

    与 ``strip_user_input_boundary`` 同口径（整块删除，含中间正文），
    区别只在于按 chunk 增量处理：命中 BEGIN 后进入抑制态，直到 END 才恢复输出。

    - 跨 chunk：BEGIN/END 被拆到不同 chunk 时，靠滞后窗口（默认 64 字符，
      远大于标记本身长度）保证标记完整落窗后才判定；
    - 未闭合：生成结束时仍在抑制态 → 残余全部丢弃（与 strip 版"整块删"一致，
      因为无法确定块尾，落库侧同样会被 strip 版删掉这一段）。
    """

    def __init__(self, lag: int = 64) -> None:
        self._lag = max(lag, 32)
        self._pending = ""
        self._suppressing = False

    def feed(self, text: str, final: bool = False) -> str:
        """喂入增量文本，返回可发给用户的正文。final=True 表示生成结束。"""
        if text:
            self._pending += text
        out: list[str] = []
        while True:
            if self._suppressing:
                m = _USER_INPUT_END_RE.search(self._pending)
                if m is None:
                    # 还没看到 END：保留尾部窗口（可能含半个 END 标记），其余丢弃
                    keep = 24
                    self._pending = self._pending[-keep:] if keep > 0 else ""
                    return "".join(out).lstrip("\n")
                self._suppressing = False
                self._pending = self._pending[m.end() :]
                continue
            m = _USER_INPUT_BEGIN_RE.search(self._pending)
            if m is None:
                break
            out.append(self._pending[: m.start()])
            self._suppressing = True
            self._pending = self._pending[m.end() :]

        if not out:
            if final:
                # 结束时不在抑制态：pending 是正文，全部放行
                out.append(self._pending)
                self._pending = ""
            elif len(self._pending) > self._lag:
                send, self._pending = self._pending[: -self._lag], self._pending[-self._lag :]
                out.append(send)
        else:
            if final:
                out.append(self._pending)
                self._pending = ""
            elif len(self._pending) > self._lag:
                out.append(self._pending[: -self._lag])
                self._pending = self._pending[-self._lag :]
        # 剥除边界块后可能留下首尾空行：与落库侧 strip_user_input_boundary 的
        # .strip() 口径对齐，保证「用户看到的」与「落库的」逐字一致。
        return "".join(out).strip("\n")
