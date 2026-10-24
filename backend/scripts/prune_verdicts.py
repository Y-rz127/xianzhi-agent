"""清理取不到的旧终审裁决（`chart_verdicts`）。

为什么需要
----------
裁决缓存的命中条件是 **(chart_hash, engine_version, prompt_version) 三者全等**。
引擎或提示词一 bump，旧行就永久取不到，成为纯死重 —— 还会在排查时误导人：
"明明写着 v9 的裁决，怎么还在重判？"（因为它绑在旧引擎上）。

2026-10-24 现场：105 行里 104 行取不到（v6/v7 共 82 行 + 旧引擎上的 v8/v9 共 22 行），
其中还夹着真太阳时修方向**之前**留下的错误校正产物（2004-06-22 08:05 / 08:50 那两行）。

用法
----
    python scripts/prune_verdicts.py                 # 只看会删什么（默认 dry-run）
    python scripts/prune_verdicts.py --apply         # 备份后真删
    python scripts/prune_verdicts.py --min-prompt v8 # 额外把低于 v8 的一并清掉
    python scripts/prune_verdicts.py --apply --no-backup

**始终先备份**：默认把待删行整行 dump 到 `backend/data/backup_chart_verdicts_*.json`。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.domain.analysis_calc import ENGINE_VERSION  # noqa: E402

_COLUMNS = (
    "chart_hash",
    "birth_time",
    "gender",
    "engine_version",
    "prompt_version",
    "status",
    "created_at",
)


def _version_num(ver: str) -> int | None:
    """'v8' → 8；解析不出来返回 None（当作最旧处理）。"""
    try:
        return int(str(ver).strip().lstrip("vV"))
    except (TypeError, ValueError):
        return None


def is_obsolete(row: dict, current_engine: str, min_prompt: str = "") -> tuple[bool, str]:
    """该行是否已取不到。返回 (是否删除, 原因)。纯函数，便于单测。

    - 引擎版本不等于当前引擎 → 删（缓存按引擎版本过滤）；
    - 给了 `min_prompt` 且提示词版本更低 → 删（用户/维护者显式要清的口径）；
    - 给一个也解析不了的版本号 → 当最旧处理，删。
    """
    engine = (row.get("engine_version") or "").strip()
    if engine != current_engine:
        return True, f"engine {engine or '空'} ≠ 当前 {current_engine}"
    if min_prompt:
        keep_min = _version_num(min_prompt) or 0
        prompt = _version_num(row.get("prompt_version") or "") or 0
        if prompt < keep_min:
            return True, f"prompt {row.get('prompt_version')} < {min_prompt}"
    return False, ""


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn, connect_timeout=5)


def main() -> int:
    from app.core.config import settings

    ap = argparse.ArgumentParser(description="清理 chart_verdicts 中取不到的旧裁决")
    ap.add_argument("--apply", action="store_true", help="真删（默认 dry-run，只打印）")
    ap.add_argument("--min-prompt", default="", help="额外删除提示词版本低于它的行，如 v8")
    ap.add_argument("--current-engine", default=ENGINE_VERSION, help="视作当前的引擎版本")
    ap.add_argument("--dsn", default=settings.postgres_connection_string, help="PG 连接串")
    ap.add_argument("--backup-dir", default=os.path.join(BACKEND_DIR, "data"), help="备份目录")
    ap.add_argument("--no-backup", action="store_true", help="不写备份（不推荐）")
    args = ap.parse_args()

    conn = _connect(args.dsn)
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(_COLUMNS)} FROM chart_verdicts ORDER BY created_at")
    rows = [dict(zip(_COLUMNS, r)) for r in cur.fetchall()]
    print(f"总行数 {len(rows)}（当前引擎 {args.current_engine}"
          f"{'，保留提示词 ≥ ' + args.min_prompt if args.min_prompt else ''}）")

    judged = [(r, is_obsolete(r, args.current_engine, args.min_prompt)) for r in rows]
    victims = [r for r, (bad, _) in judged if bad]
    keep = [r for r, (bad, _) in judged if not bad]

    dist: dict[tuple, int] = {}
    for r in rows:
        key = (r["engine_version"] or "空", r["prompt_version"] or "空", r["status"] or "空")
        dist[key] = dist.get(key, 0) + 1
    print("当前分布（引擎 / 提示词 / 状态 → 行数）:")
    for key in sorted(dist):
        print(f"  {key[0]:<12} {key[1]:<4} {key[2]:<8} {dist[key]}")

    print(f"\n将删除 {len(victims)} 行，保留 {len(keep)} 行")
    reasons: dict[str, int] = {}
    for _r, (_bad, why) in judged:
        if why:
            reasons[why] = reasons.get(why, 0) + 1
    for why, n in sorted(reasons.items()):
        print(f"  - {why}: {n} 行")
    for r in keep:
        print(f"  保留 {r['chart_hash']} {r['birth_time']} {r['gender']}"
              f" engine={r['engine_version']} prompt={r['prompt_version']}")

    if not victims:
        print("没有需要清理的行。")
        return 0
    if not args.apply:
        print("\n（dry-run）确认无误后加 --apply 真删；默认会先备份。")
        return 0

    if not args.no_backup:
        os.makedirs(args.backup_dir, exist_ok=True)
        path = os.path.join(
            args.backup_dir,
            f"backup_chart_verdicts_{datetime.datetime.now():%Y%m%d_%H%M%S}.json",
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [{k: str(v) if isinstance(v, datetime.datetime) else v for k, v in r.items()}
                 for r in victims],
                f,
                ensure_ascii=False,
                indent=1,
            )
        print("已备份 →", path)

    # 按 chart_hash + 版本精确删：不重算判据，避免"打印的"和"删的"不是同一批
    deleted = 0
    for r in victims:
        cur.execute(
            """
            DELETE FROM chart_verdicts
            WHERE chart_hash = %s AND engine_version = %s AND prompt_version = %s
            """,
            (r["chart_hash"], r["engine_version"], r["prompt_version"]),
        )
        deleted += cur.rowcount
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM chart_verdicts")
    print(f"已删除 {deleted} 行；剩余 {cur.fetchone()[0]} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
