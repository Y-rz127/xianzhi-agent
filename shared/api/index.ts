/**
 * 共享 API 层统一出口（R11）。
 *
 * 使用方式：
 * - Web（frontend/）：`import { ... } from '@shared/api'`（vite/tsconfig 别名 @shared → ../../shared）
 * - 小程序（uniapp/）：同上
 *
 * 约束：本目录为纯 TypeScript，禁止引用 DOM / fetch / uni.* 等平台 API；
 * 传输层（鉴权、基址、请求实现）仍由各端 api 模块负责。
 */
export * from './types'
export * from './parsers'
export * from './endpoints'
