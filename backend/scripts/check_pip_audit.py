"""检查 pip-audit JSON，只放行 allowlist 中 package==version 的既有漏洞。

用法（CI）：
    python -m pip_audit -r requirements.lock -f json -o /tmp/pip-audit.json || true
    python scripts/check_pip_audit.py --audit-json /tmp/pip-audit.json

allowlist 按包名+精确版本匹配：依赖升级后旧条目自动失效，新版本漏洞仍会被拦截。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-json", required=True, help="pip-audit 的 JSON 输出")
    parser.add_argument(
        "--allowlist",
        default=str(_BACKEND_ROOT / "security-audit-allowlist.json"),
        help="豁免清单（默认 backend/security-audit-allowlist.json）",
    )
    args = parser.parse_args()

    report = _load(Path(args.audit_json))
    allow_entries = _load(Path(args.allowlist)).get("packages", [])
    allowed = {(str(e.get("name", "")).lower(), str(e.get("version", ""))) for e in allow_entries}

    violations: list[str] = []
    exempted = 0
    used: set[tuple[str, str]] = set()
    for dep in report.get("dependencies", []):
        vulns = dep.get("vulns") or []
        if not vulns:
            continue
        key = (str(dep.get("name", "")).lower(), str(dep.get("version", "")))
        if key in allowed:
            exempted += len(vulns)
            used.add(key)
            continue
        for v in vulns:
            fix = ", ".join(v.get("fix_versions") or []) or "无修复版本"
            violations.append(
                f"{dep.get('name')}=={dep.get('version')} {v.get('id')}（修复版本: {fix}）"
            )

    stale = sorted(allowed - used)
    if exempted:
        print(f"已豁免 {exempted} 条既有漏洞（{len(used)} 个冻结包版本）")
    if stale:
        print(f"提示：{len(stale)} 条豁免未命中（依赖可能已升级，可删除对应条目）: {stale}")
    if violations:
        print(f"\n发现 {len(violations)} 条未豁免漏洞：", file=sys.stderr)
        for line in violations:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print("依赖审计通过：没有新增漏洞")
    return 0


if __name__ == "__main__":
    sys.exit(main())
