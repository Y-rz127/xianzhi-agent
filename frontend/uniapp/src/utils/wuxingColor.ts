/** 五行 → 文字色（前端单一事实源）：终审五神等"按五行上色"的文字共用一套。
 *
 * 这套色值与页面里已有的干支字色（`ganWx` / `zhiWx`，BaziCard 与命盘详情页同值）严格一致：
 * 天干「甲」是绿、地支「子」是蓝，那么五神里的「木」「水」就该是同一个绿和蓝，
 * 否则同一个页面里"木"会出现两种绿。
 *
 * 明度是照着**文字**选的（两套主题下都够对比）。五行柱那类大色块另用后端
 * `chart_builder.chart_to_api_dict` 下发的深色（#d4af37 / #4a7c3a …），两者不要互换：
 * 深绿当字太闷，亮绿当块太飘。
 */
export const WUXING_TEXT_COLORS: Record<string, string> = {
  金: '#fbbf24',
  木: '#4ade80',
  水: '#60a5fa',
  火: '#f87171',
  土: '#d4a574',
}

/** 取某五行的文字色；非五行（空串等）返回空串，调用方沿用默认色。 */
export function wuxingColor(name: string): string {
  return WUXING_TEXT_COLORS[(name || '').trim()] || ''
}

/**
 * 取某五行的"淡底 + 描边"样式（月令旺衰这类小胶囊用）。
 * 小程序对 8 位 hex（#RRGGBBAA）支持不稳，这里显式转 rgba。
 */
export function wuxingTintStyle(name: string): Record<string, string> {
  const color = wuxingColor(name)
  if (!color) return {}
  const r = parseInt(color.slice(1, 3), 16)
  const g = parseInt(color.slice(3, 5), 16)
  const b = parseInt(color.slice(5, 7), 16)
  const rgba = (alpha: number) => `rgba(${r}, ${g}, ${b}, ${alpha})`
  return { color, borderColor: rgba(0.38), background: rgba(0.1) }
}

/** 把「金、木」这类五神串拆成单个五行，逐字上色用。 */
export function splitWuxing(value: string): string[] {
  return (value || '')
    .split(/[、,，/\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}
