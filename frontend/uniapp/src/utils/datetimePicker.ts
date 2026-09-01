export type DatePickerIndex = [number, number, number]
export type TimePickerIndex = [number, number]

export interface DateParts {
  year: number
  month: number
  day: number
}

export function pad2(n: number): string {
  return n < 10 ? '0' + n : '' + n
}

export function getLocalDateParts(date = new Date()): DateParts {
  return {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
  }
}

export function formatDateParts(parts: DateParts): string {
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`
}

export function getLocalDateString(date = new Date()): string {
  return formatDateParts(getLocalDateParts(date))
}

export function makeYearRange(maxYear: number, pastYears = 100): number[] {
  const years: number[] = []
  for (let year = maxYear - pastYears; year <= maxYear; year++) years.push(year)
  return years
}

export function getMonthOptions(year: number, maxDate?: DateParts): number[] {
  const lastMonth = maxDate && year === maxDate.year ? maxDate.month : 12
  return Array.from({ length: lastMonth }, (_, i) => i + 1)
}

export function getDayOptions(year: number, month: number, maxDate?: DateParts): number[] {
  let lastDay = new Date(year, month, 0).getDate()
  if (maxDate && year === maxDate.year && month === maxDate.month) {
    lastDay = Math.min(lastDay, maxDate.day)
  }
  return Array.from({ length: lastDay }, (_, i) => i + 1)
}

export function normalizeDateIndex(
  index: number[] | DatePickerIndex,
  years: number[],
  maxDate?: DateParts,
): DatePickerIndex {
  const yearIndex = clamp(index[0] ?? 0, 0, Math.max(years.length - 1, 0))
  const year = years[yearIndex] ?? maxDate?.year ?? getLocalDateParts().year
  const monthOptions = getMonthOptions(year, maxDate)
  const monthIndex = clamp(index[1] ?? 0, 0, Math.max(monthOptions.length - 1, 0))
  const month = monthOptions[monthIndex] ?? 1
  const dayOptions = getDayOptions(year, month, maxDate)
  const dayIndex = clamp(index[2] ?? 0, 0, Math.max(dayOptions.length - 1, 0))
  return [yearIndex, monthIndex, dayIndex]
}

export function dateIndexToString(
  index: number[] | DatePickerIndex,
  years: number[],
  maxDate?: DateParts,
): string {
  const [yearIndex, monthIndex, dayIndex] = normalizeDateIndex(index, years, maxDate)
  const year = years[yearIndex] ?? maxDate?.year ?? getLocalDateParts().year
  const month = getMonthOptions(year, maxDate)[monthIndex] ?? 1
  const day = getDayOptions(year, month, maxDate)[dayIndex] ?? 1
  return formatDateParts({ year, month, day })
}

export function dateStringToIndex(
  value: string,
  years: number[],
  maxDate?: DateParts,
): DatePickerIndex {
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(value)
  if (!match) {
    return normalizeDateIndex([years.length - 1, 0, 0], years, maxDate)
  }

  const minYear = years[0] ?? Number(match[1])
  const maxYear = years[years.length - 1] ?? Number(match[1])
  const year = clamp(Number(match[1]), minYear, maxYear)
  const yearIndex = Math.max(years.indexOf(year), 0)
  const monthOptions = getMonthOptions(year, maxDate)
  const month = clamp(Number(match[2]), 1, monthOptions[monthOptions.length - 1] ?? 12)
  const monthIndex = Math.max(monthOptions.indexOf(month), 0)
  const dayOptions = getDayOptions(year, month, maxDate)
  const day = clamp(Number(match[3]), 1, dayOptions[dayOptions.length - 1] ?? 1)
  const dayIndex = Math.max(dayOptions.indexOf(day), 0)
  return [yearIndex, monthIndex, dayIndex]
}

export function normalizeTimeIndex(index: number[] | TimePickerIndex): TimePickerIndex {
  return [
    clamp(index[0] ?? 0, 0, 23),
    clamp(index[1] ?? 0, 0, 59),
  ]
}

export function timeIndexToString(index: number[] | TimePickerIndex): string {
  const [hour, minute] = normalizeTimeIndex(index)
  return `${pad2(hour)}:${pad2(minute)}`
}

export function timeStringToIndex(value: string): TimePickerIndex {
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(value)
  if (!match) return [0, 0]
  return normalizeTimeIndex([Number(match[1]), Number(match[2])])
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min
  return Math.min(Math.max(Math.trunc(value), min), max)
}
