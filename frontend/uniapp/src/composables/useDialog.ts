/**
 * useDialog - 主题化弹窗（替代 uni.showModal）
 *
 * 为什么不用 uni.showModal：它是微信原生弹窗，永远白底黑字，不随 .t-dark 换肤
 * （chart-detail 页早就踩过这个坑并改用自定义弹层，见该页 528 行注释）。
 *
 * 用法：
 *  1. 页面根节点挂一个 <ThemeDialog />（模块级单例状态，同屏只会有一处在显示）；
 *  2. 任意位置 `const { confirm, content } = await showDialog({ title, content })`。
 *
 * Promise 语义与 uni.showModal 的 success 回调对齐：confirm=false 表示取消/点遮罩。
 */
import { reactive } from 'vue'

export interface DialogOptions {
  title?: string
  /** 正文；editable 为真时作为输入框初值 */
  content?: string
  /** 带输入框（对应 uni.showModal 的 editable: true） */
  editable?: boolean
  placeholder?: string
  maxlength?: number
  confirmText?: string
  cancelText?: string
  /** 危险操作（删除/退出）：确认按钮走朱砂底 */
  danger?: boolean
}

export interface DialogResult {
  confirm: boolean
  /** editable 弹窗的输入内容，已 trim；非输入弹窗恒为 '' */
  content: string
}

/** 组件内消费的响应式状态（模块级单例：小程序没有全局根节点可挂） */
const state = reactive({
  visible: false,
  title: '',
  content: '',
  editable: false,
  placeholder: '',
  maxlength: 40,
  confirmText: '确定',
  cancelText: '取消',
  danger: false,
})

let _resolve: ((r: DialogResult) => void) | null = null

export function useDialogState() {
  return state
}

export function showDialog(opts: DialogOptions): Promise<DialogResult> {
  // 上一个弹窗还挂着（理论上不会：关闭时必 settle）——先按取消结算，避免 Promise 泄漏
  if (_resolve) {
    const stale = _resolve
    _resolve = null
    stale({ confirm: false, content: '' })
  }
  Object.assign(state, {
    visible: true,
    title: opts.title ?? '',
    content: opts.content ?? '',
    editable: !!opts.editable,
    placeholder: opts.placeholder ?? '',
    maxlength: opts.maxlength ?? 40,
    confirmText: opts.confirmText ?? '确定',
    cancelText: opts.cancelText ?? '取消',
    danger: !!opts.danger,
  })
  return new Promise<DialogResult>((resolve) => { _resolve = resolve })
}

function settle(result: DialogResult) {
  state.visible = false
  const fn = _resolve
  _resolve = null
  fn?.(result)
}

/** 组件确认按钮回调：关闭弹窗并把输入内容交还给 showDialog() 的 Promise */
export function dialogConfirm(input: string) {
  settle({ confirm: true, content: (input || '').trim() })
}

export function dialogCancel() {
  settle({ confirm: false, content: '' })
}
