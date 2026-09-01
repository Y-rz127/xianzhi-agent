/**
 * 中国省市区三级联动数据（R11 二期：已上收至仓库根 shared/utils/region-data.ts，
 * Web 端与小程序端共用同一份数据，口径变更只需改 shared 一处）。
 * 本文件为兼容垫片：保持既有 `@/utils/region-data` 导入路径不变。
 */
export type { City, District, MatchedCity, Province } from '@shared/utils/region-data'
export { matchCityByName, regionData } from '@shared/utils/region-data'
