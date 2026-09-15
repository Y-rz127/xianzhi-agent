"""架构防回归断言（fitness function）。

把 docs/backend-architecture-review.md 第四节的分层铁律固化成可执行的断言，
使分层决策自动化执行，而不是靠人记住。

设计：**基线棘轮（ratchet）**。重构进行中的现存违规登记在 BASELINE_* 中，
测试要求实际违规数 == 基线数：
  - 新增违规 → 失败（拦住回归）
  - 已修掉的违规未从基线移除 → 失败（强制基线收缩，防止"修了但白名单没清"）
所以每次真修掉一处，必须同步下调基线，基线只减不增。

运行：
    pytest tests/test_architecture.py -v
"""

from __future__ import annotations

import ast
import collections
import os

import pytest

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------- 分层规则 ----------------
# 每个包的禁止依赖目标集合。未列出的方向（同层、向上）视为允许。
FORBIDDEN_TARGETS: dict[str, set[str]] = {
    # core 是最底层基础设施：不得依赖任何业务包
    "core": {"domain", "rag", "db", "memory", "tools", "agent", "api", "sub_app", "tasks", "evaluation"},
    # domain 是纯计算层：只允许自依赖
    "domain": {"core", "rag", "db", "memory", "tools", "agent", "api", "sub_app", "tasks", "evaluation"},
    # 存储 / 检索层：不得反向依赖上层
    "db": {"tools", "agent", "api", "sub_app", "tasks", "evaluation"},
    "memory": {"tools", "agent", "api", "sub_app", "tasks", "evaluation"},
    "rag": {"tools", "agent", "api", "sub_app", "tasks", "evaluation"},
    # 工具层：只许依赖 domain/core/rag
    "tools": {"agent", "api", "sub_app"},
    "evaluation": {"api", "sub_app"},
    "agent": {"api", "sub_app"},
    "tasks": {"api", "sub_app"},
    # sub_app 与 api 是同级入口层，但 api 依赖 sub_app（挂载路由），故 sub_app 不得反向依赖 api
    "sub_app": {"api"},
    "api": set(),
}

# ---------------- 基线（只减不增） ----------------
# 每项都必须有注释说明来源与消除计划；(源包, 目标包) -> 现存违规条数
BASELINE_VIOLATIONS: dict[tuple[str, str], int] = {
    # 全部清零：BAZI_BIRTH_TOOLS 下沉 app.domain.tools_catalog（消除 memory→tools），
    # 报告提示词随使用者迁至 app.tools.report_prompts（消除 tools→agent）。
    # tools 不再依赖 agent，agent→tools 为单向，agent⟷tools 循环一并断开。
}

# 包级循环（无序对，按字母序存）
BASELINE_CYCLES: set[tuple[str, str]] = set()
# 已全部消除：
# ("db", "rag")：detect_domain / DOMAIN_KEYWORDS 下沉 app.domain.domain_keywords，仅剩 rag→db 单向
# ("agent", "tools")：报告提示词迁 tools.report_prompts 后 tools→agent 消失，agent→tools 成单向

# 允许 import * 的模块（门面转发）。门面拆除后必须清空此集合。
# 阶段 4 已拆除 domain.bazi_engine（其 `from app.domain.tables import *` 一并消除），
# 全部符号改为各定义子模块的直连导入。
BASELINE_STAR_IMPORTS: set[str] = set()

# 双导入路径基线：同一符号既从门面导入、又被从子模块直连导入。
# 阶段 4 已拆除最后两处门面（domain.bazi_engine / agent.workflow.xianzhi_workflow），
# 全部符号统一改为各定义子模块的直连导入，故不再存在任何双导入路径。
# 若日后重新引入门面，须同步恢复本集合并登记到下方 _facade_symbol_paths 的 facades 字典。
BASELINE_DUAL_PATH_SYMBOLS: set[str] = set()

# 已删除的模块不得复活（阶段 0 清理成果的守卫）
REMOVED_MODULES = (
    "app.api.state",        # R5 兼容层，生产零引用
    "app.api.tarot_records",  # 0 字节空文件
    # 阶段 2-9：app_config 的 PG 实现迁至 app/db/kv_store.py，
    # core 侧改用 KVStore 协议（app/core/config/kv.py），倒置边消除
    "app.db.app_config",
    # 阶段 2-10：按层归位后删空 —— AppContext 归 app/agent/context.py，
    # client_error / 长度限额归 app/core/http/errors.py
    "app.api.context",
    "app.api.common",
    # 阶段 2-11：no-op 转发层删除，tools 直连 domain.huangli_calc
    "app.sub_app.huangli.huangli_app",
    # 阶段 2-12：异步数据访问门面归位 api 层（app/api/data_access.py），
    # 消除 db → memory 反向依赖；全仓连接池统一到 app/db/pool.py
    "app.db.repository",
    # 阶段 4：两处纯重导出门面拆除，符号统一从各定义子模块直连导入
    "app.domain.bazi_engine",
    "app.agent.workflow.xianzhi_workflow",
)


# ---------------- 扫描实现 ----------------


def _iter_app_files() -> dict[str, str]:
    """{模块名: 绝对路径}，跳过 __pycache__。"""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, APP_DIR).replace("\\", "/")[:-3]
            if rel.endswith("/__init__"):
                rel = rel[:-9]
            out[rel.replace("/", ".")] = full
    return out


def _targets(node: ast.AST, module: str) -> list[str]:
    """还原一条 import 语句的绝对目标模块名列表（仅 app.* 内部）。"""
    found: list[str] = []
    if isinstance(node, ast.ImportFrom):
        if node.level:
            base = module.split(".")[: len(module.split(".")) - node.level]
            if node.module:
                base = base + node.module.split(".")
            found.append(".".join(base))
        elif node.module:
            found.append(node.module)
    elif isinstance(node, ast.Import):
        found.extend(alias.name for alias in node.names)
    return [m for m in found if m == "app" or m.startswith("app.")]


def _scan() -> dict:
    """一次遍历产出全部度量。"""
    violations: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    star_imports: set[str] = set()
    pkg_edges: dict[str, set[str]] = collections.defaultdict(set)

    for module, path in sorted(_iter_app_files().items()):
        source = open(path, encoding="utf-8").read()
        tree = ast.parse(source)
        src_layer = module.split(".")[0]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                star_imports.add(module)
            for target in _targets(node, module):
                internal = target[4:]  # 去掉 "app."
                target_layer = internal.split(".")[0]
                if target_layer == src_layer:
                    continue
                pkg_edges[src_layer].add(target_layer)
                if target_layer in FORBIDDEN_TARGETS.get(src_layer, set()):
                    violations[(src_layer, target_layer)].append(f"{module}:{node.lineno}")

    cycles: set[tuple[str, str]] = set()
    for a in sorted(pkg_edges):
        for b in pkg_edges[a]:
            if a in pkg_edges.get(b, ()):  # b 也依赖 a → 双向
                cycles.add(tuple(sorted((a, b))))

    return {"violations": violations, "star": star_imports, "cycles": cycles}


def _facade_symbol_paths() -> set[str]:
    """找出「同一符号既从门面导入、又被从子模块直连导入」的符号集合。

    门面自身的重导出（facade 文件里 from 子模块 import）不算直连——那是它存在的理由。
    """
    # 阶段 4 已拆除两处门面（domain.bazi_engine / agent.workflow.xianzhi_workflow），
    # 符号统一改为各定义子模块的直连导入，故不再有任何门面需要追踪。
    # 若需重新引入门面，请同步在此登记并恢复 BASELINE_DUAL_PATH_SYMBOLS 闸门。
    facades: dict[str, str] = {}
    # (搜索根, 该根下模块名的前缀)
    search_roots = [(APP_DIR, "app."), (os.path.join(REPO_ROOT, "tests"), "")]
    facade_symbols: dict[str, set[str]] = collections.defaultdict(set)
    direct_symbols: set[str] = set()

    for base, prefix in search_roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, base).replace("\\", "/")[:-3]
                if rel.endswith("/__init__"):
                    rel = rel[:-9]
                if (prefix + rel.replace("/", ".")) in facades:
                    continue  # 门面自身的重导出不计入直连
                try:
                    tree = ast.parse(open(path, encoding="utf-8").read())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom) or not node.module:
                        continue
                    if not node.module.startswith("app."):
                        continue
                    origin = node.module
                    if origin in facades:
                        for alias in node.names:
                            if alias.name != "*":
                                facade_symbols[alias.name].add(origin)
                        continue
                    pkg = next((p for p in facades.values() if origin.startswith(p + ".")), None)
                    if pkg:
                        direct_symbols.update(a.name for a in node.names if a.name != "*")

    return {s for s in facade_symbols if s in direct_symbols}


# ---------------- 断言 ----------------


def test_no_new_layer_violations() -> None:
    """不得出现新的跨层倒置依赖；现存违规数必须等于基线。"""
    actual = _scan()["violations"]
    actual_counts = {k: len(v) for k, v in actual.items()}

    added = {
        k: v
        for k, v in actual_counts.items()
        if k not in BASELINE_VIOLATIONS
    }
    assert not added, (
        "新增了倒置依赖，请改为允许的依赖方向（详见 docs/backend-architecture-review.md 第四节）：\n"
        + "\n".join(f"  {k[0]} -> {k[1]} ({n} 处): {actual[k]}" for k, n in sorted(added.items()))
    )

    shrank = {
        k: (BASELINE_VIOLATIONS[k], actual_counts.get(k, 0))
        for k in BASELINE_VIOLATIONS
        if actual_counts.get(k, 0) < BASELINE_VIOLATIONS[k]
    }
    assert not shrank, (
        "违规已被修掉，但基线未同步下调——请把已消除的条目从 BASELINE_VIOLATIONS 移除或下调：\n"
        + "\n".join(f"  {k[0]} -> {k[1]}: 基线 {old} → 实际 {now}" for k, (old, now) in sorted(shrank.items()))
    )


def test_no_new_package_cycles() -> None:
    """不得出现新的包级循环依赖；现存循环数必须等于基线。"""
    actual = _scan()["cycles"]
    added = actual - BASELINE_CYCLES
    assert not added, f"新增包级循环依赖: {sorted(added)}"

    gone = BASELINE_CYCLES - actual
    assert not gone, f"循环已消除但基线未同步——请从 BASELINE_CYCLES 移除: {sorted(gone)}"


def test_no_new_star_imports() -> None:
    """禁止 `import *`：它让符号来源不可追踪，也使 IDE 跳转失效。"""
    actual = _scan()["star"]
    added = actual - BASELINE_STAR_IMPORTS
    assert not added, f"新增 import *（请改为显式导入）: {sorted(added)}"

    gone = BASELINE_STAR_IMPORTS - actual
    assert not gone, f"import * 已消除但基线未同步——请从 BASELINE_STAR_IMPORTS 移除: {sorted(gone)}"


def test_domain_layer_stays_clean() -> None:
    """domain 是唯一零越层的干净层，必须保持：任何 domain 越层依赖都直接失败。"""
    actual = _scan()["violations"]
    dirty = {k: v for k, v in actual.items() if k[0] == "domain"}
    assert not dirty, f"domain 层出现越层依赖（该层必须纯自洽）: {dirty}"


def test_no_dual_path_symbol_imports() -> None:
    """同一符号不得同时从门面与子模块导入（否则重命名/移动风险翻倍）。

    本测试同时是「门面拆除进度」的度量：集合只减不增，每迁移一个符号必须同步下调基线。
    """
    actual = _facade_symbol_paths()
    added = actual - BASELINE_DUAL_PATH_SYMBOLS
    assert not added, (
        "以下符号新增了第二条导入路径（请统一为直连子模块）：\n  " + ", ".join(sorted(added))
    )

    migrated = BASELINE_DUAL_PATH_SYMBOLS - actual
    assert not migrated, (
        "以下符号已迁移完（不再存在双路径），请从 BASELINE_DUAL_PATH_SYMBOLS 中删除：\n  "
        + ", ".join(sorted(migrated))
    )


@pytest.mark.parametrize("module", REMOVED_MODULES)
def test_removed_modules_not_reintroduced(module: str) -> None:
    """已清理/迁走的模块不得复活。"""
    candidates = [
        os.path.join(REPO_ROOT, module.replace(".", os.sep) + ".py"),
        os.path.join(APP_DIR, module[len("app."):].replace(".", os.sep) + ".py"),
    ]
    assert not any(os.path.exists(p) for p in candidates), (
        f"{module} 已被删除，不应重新引入（若确需恢复，请同步更新本测试）"
    )


def test_only_pool_module_holds_connection_pool() -> None:
    """全仓只允许 `app/db/pool.py` 构造连接池。

    曾出现第二个池：`app/rag/fingerprint.py` 用同一 DSN 自建 ConnectionPool。
    后果是多占空闲连接、关停要分别关两处（漏关即泄漏），且池大小/探活参数各写一套。
    """
    offenders = [
        mod
        for mod, path in _iter_app_files().items()
        if mod != "db.pool" and "ConnectionPool(" in open(path, encoding="utf-8").read()
    ]
    assert not offenders, (
        f"以下模块自建连接池，应改用 app.db.pool.get_pool(): {sorted(offenders)}"
    )


def test_no_shadow_module_beside_converted_package() -> None:
    """已包化的模块不得同时存在同名 .py 影子文件。

    `app/core/config` 已由单文件改为包（settings.py + kv.py）。若 `config.py`
    残留或复活，包与模块同名并存，导入结果取决于文件系统顺序 —— 且 `BACKEND_ROOT`
    的向上查找层数会随之变化，属静默故障。
    """
    converted = ("core/config", "core/http", "domain/shensha_calc")
    for rel in converted:
        shadow = os.path.join(APP_DIR, rel.replace("/", os.sep) + ".py")
        assert not os.path.exists(shadow), (
            f"{rel}.py 与同名包并存，会造成导入歧义与路径锚点漂移，请删除 {shadow}"
        )
        assert os.path.isdir(os.path.join(APP_DIR, rel.replace("/", os.sep))), (
            f"{rel} 应为包（目录），当前不存在"
        )
