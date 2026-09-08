/**
 * 细盘「选中态」匹配与折叠取数的纯函数集合。
 *
 * 放在共享层的原因：这些判断只依赖 payload 的字段形状，一旦某字段（如 chart.dayun[].index）
 * 缺失或改名，出问题的表现是"界面静默显示错误内容"，而不是报错——最难查的就是这类。
 * 集中成函数后，后端契约测试可以钉住它们依赖的字段确实存在。
 *
 * 约束：纯 TS，不得引用 DOM / uni.* / fetch（见 index.ts 的共享层说明）。
 */

/** 大运项的最小结构：chart.dayun 与 xipan.dayun 都满足 */
export interface DayunLike {
  ganzhi: string
  startYear: number | string
  /** xipan.dayun 一直有；chart.dayun 由后端序列化补上 */
  index?: number
}

/**
 * 是否同一步大运。
 * 优先比 index；任一侧缺 index 时退回「干支 + 起始年」——起始年必须一起比，
 * 否则 60 年一循环的干支会在不同大运段上撞名。
 */
export function isSameDayun(item: DayunLike, sel?: DayunLike | null): boolean {
  if (!sel) return false
  if (typeof item.index === 'number' && typeof sel.index === 'number') {
    return item.index === sel.index
  }
  return item.ganzhi === sel.ganzhi && String(item.startYear) === String(sel.startYear)
}

/**
 * 折叠态取数：展开时给全量，收起时只给选中项。
 *
 * 关键约束：确实存在选中项、却一条都没匹配上时返回空数组。
 * 早先的写法是「匹配不到就退回全量」，结果 chart.dayun 少了 index 之后
 * `undefined === 2` 恒为 false，界面永远显示全部大运——字段缺陷被伪装成了显示逻辑。
 */
export function collapseBySelection<T>(
  rows: T[],
  picked: T[],
  showAll: boolean,
  hasSelection: boolean,
): T[] {
  if (showAll) return rows
  if (picked.length) return picked
  return hasSelection ? [] : rows
}
