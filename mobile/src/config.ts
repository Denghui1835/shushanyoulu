/**
 * 移动端后端地址配置（可切换）。
 *
 * 优先级（从高到低）：
 *   1. process.env.EXPO_PUBLIC_API_URL  —— 构建时注入（.env 文件，Expo 自动加载 EXPO_PUBLIC_*）
 *   2. app.json 的 extra.apiBaseUrl      —— 见 mobile/app.json
 *   3. 默认占位（开发机局域网 IP，改成你的后端电脑 IP）
 *
 * 用法：在 mobile/.env 写 EXPO_PUBLIC_API_URL=http://192.168.x.x:8000 重启即可切后端。
 */
import Constants from 'expo-constants'

function resolveBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL
  if (fromEnv) return fromEnv.replace(/\/+$/, '')
  const extra = (Constants.expoConfig?.extra as Record<string, string> | undefined) ?? {}
  if (extra.apiBaseUrl) return String(extra.apiBaseUrl).replace(/\/+$/, '')
  return 'http://192.168.1.100:8000'
}

export const API_BASE_URL = resolveBaseUrl()

/** 组装完整后端 URL（音频流 / 文件下载用）。 */
export function fullUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}
