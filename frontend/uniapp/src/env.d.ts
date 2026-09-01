/// <reference types="@dcloudio/types" />
/// <reference types="vite/client" />

declare namespace WechatMiniprogram {
  function connectSocket(option: UniApp.ConnectSocketOptions): void
  function onSocketOpen(callback: (res: any) => void): void
  function onSocketMessage(callback: (res: { data: string | ArrayBuffer }) => void): void
  function onSocketError(callback: (err: any) => void): void
  function onSocketClose(callback: (res: any) => void): void
  function sendSocketMessage(option: { data: string; success?: () => void; fail?: (err: any) => void }): void
  function closeSocket(option?: { code?: number; reason?: string }): void
}

declare const wx: WechatMiniprogram

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_WS_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}