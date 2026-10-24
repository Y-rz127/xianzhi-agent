#!/usr/bin/env node
/**
 * 检查 npm audit JSON：high/critical 漏洞必须修复或在 audit-allowlist.json 登记。
 *
 * 用法（CI）：
 *   npm audit --package-lock-only --json > /tmp/web-audit.json || true
 *   node scripts/check_npm_audit.mjs /tmp/web-audit.json
 */
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const auditPath = process.argv[2]
if (!auditPath) {
  console.error("用法: node scripts/check_npm_audit.mjs <npm-audit.json>")
  process.exit(2)
}

const here = dirname(fileURLToPath(import.meta.url))
const allowlist = JSON.parse(
  readFileSync(join(here, "..", "audit-allowlist.json"), "utf-8"),
).advisories || {}
// Windows/PowerShell 重定向可能带 UTF-8 BOM，JSON.parse 会失败
const report = JSON.parse(readFileSync(auditPath, "utf-8").replace(/^\uFEFF/, ""))

const failures = []
const used = new Set()
let exempted = 0

for (const [name, vuln] of Object.entries(report.vulnerabilities || {})) {
  const ids = (vuln.via || [])
    .filter((item) => typeof item === "object" && item.url)
    .map((item) => item.url.split("/").pop())

  for (const id of ids) {
    if (id in allowlist) {
      exempted += 1
      used.add(id)
    }
  }

  if (vuln.severity !== "high" && vuln.severity !== "critical") continue
  const unallowed = ids.filter((id) => !(id in allowlist))
  if (ids.length === 0) {
    failures.push(`${name} (${vuln.severity}): 无 advisory 链接，需人工确认`)
  } else if (unallowed.length) {
    failures.push(`${name} (${vuln.severity}): ${unallowed.join(", ")}`)
  }
}

const counts = report.metadata?.vulnerabilities || {}
const stale = Object.keys(allowlist).filter((id) => !used.has(id))

console.log(
  `npm audit: total=${counts.total || 0} critical=${counts.critical || 0} ` +
    `high=${counts.high || 0} moderate=${counts.moderate || 0} low=${counts.low || 0}`,
)
if (exempted) console.log(`已豁免 ${exempted} 条开发期依赖漏洞`)
if (stale.length) console.log(`提示：${stale.length} 条豁免未命中，可删除: ${stale.join(", ")}`)

if (failures.length) {
  console.error(`\n发现 ${failures.length} 个未豁免的 high/critical 漏洞：`)
  for (const line of failures) console.error(`  - ${line}`)
  process.exit(1)
}
console.log("依赖审计通过：没有新增 high/critical 漏洞")
