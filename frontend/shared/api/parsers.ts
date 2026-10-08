/**
 * 排盘文本解析器：从后端返回的可读文本中提取结构化数据。
 *
 * R11 共享 API 层：纯函数，Web/小程序共用（原 frontend 与 uniapp 各维护一份）。
 * 仅当接口降级返回文本（无结构化 chartData）时使用。
 */
import type { DayunItem, Pillar, ShenshaItem, WuxingItem } from './types'

export function parsePillars(text: string): Pillar[] {
  if (!text) return []
  const result: Pillar[] = []
  const re = /(年柱|月柱|日柱|时柱)[:\s]*([^\s(]+)\s*\(([^)]+)\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    result.push({ name: m[1], ganzhi: m[2].trim(), nayin: m[3].trim() })
  }
  return result
}

export function parseWuxing(text: string): WuxingItem[] {
  if (!text) return []
  const colors: Record<string, string> = {
    金: '#d4af37', 木: '#4a7c3a', 水: '#3a6ea5', 火: '#c0392b', 土: '#8b6f47',
  }
  const result: WuxingItem[] = []
  const m = text.match(/['"]?金['"]?\s*[:=]\s*(\d+).*?['"]?木['"]?\s*[:=]\s*(\d+).*?['"]?水['"]?\s*[:=]\s*(\d+).*?['"]?火['"]?\s*[:=]\s*(\d+).*?['"]?土['"]?\s*[:=]\s*(\d+)/s)
  if (m) {
    const vals = [parseInt(m[1]), parseInt(m[2]), parseInt(m[3]), parseInt(m[4]), parseInt(m[5])]
    const names = ['金', '木', '水', '火', '土']
    names.forEach((n, i) => result.push({ name: n, count: vals[i], color: colors[n] }))
  }
  return result
}

export function parseDayun(text: string): DayunItem[] {
  if (!text) return []
  const result: DayunItem[] = []
  const re = /(\d+)[\s-~至~到](\d+)岁?\s*([^\s]+)\s*(\d+)-(\d+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    result.push({ year: m[3], ganzhi: m[3], startAge: parseInt(m[1]), startYear: parseInt(m[4]) })
  }
  return result
}

export function parseShensha(text: string): ShenshaItem[] {
  if (!text) return []
  const result: ShenshaItem[] = []
  const re = /([^\n:：]+)[：:]\s*([^\n]+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const name = m[1].trim()
    if (name && name.length < 20 && !name.includes('柱') && !name.includes('五行')) {
      result.push({ name, description: m[2].trim() })
    }
  }
  return result.slice(0, 8)
}
