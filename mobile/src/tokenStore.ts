/**
 * 社区登录 token 存储：expo-secure-store（替代 Web 的 localStorage）。
 * 内存缓存避免每次读 SecureStore。
 */
import * as SecureStore from 'expo-secure-store'

const KEY = 'yq_auth_token'
let cache: string | null = null

export async function getToken(): Promise<string | null> {
  if (cache === null) {
    cache = await SecureStore.getItemAsync(KEY)
  }
  return cache
}

export async function setToken(token: string | null): Promise<void> {
  cache = token
  if (token) await SecureStore.setItemAsync(KEY, token)
  else await SecureStore.deleteItemAsync(KEY)
}

export async function clearToken(): Promise<void> {
  cache = null
  await SecureStore.deleteItemAsync(KEY)
}
