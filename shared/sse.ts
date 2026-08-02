/**
 * SSE 流式解析（纯逻辑，仅依赖标准 ReadableStream / TextDecoder）。
 * Web 端在 frontend/src/api.ts 有同源实现；这里抽成共享供移动端适配。
 *
 * 注意：React Native 的 fetch 对响应流支持有限，移动端优先用 react-native-sse
 * （见 mobile/src/api.ts），此模块作为「事件解析」参考实现，也用于 Web/测试。
 */

/** 解析一段 SSE 响应体为事件对象序列。 */
export async function* readSSE(resp: Response): AsyncGenerator<any> {
  if (!resp.ok || !resp.body) throw new Error(`请求失败: ${resp.status}`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const dataLine = line.split('\n').find(l => l.startsWith('data:'))
      if (!dataLine) continue
      const payload = dataLine.slice(5).trim()
      if (!payload) continue
      try {
        yield JSON.parse(payload)
      } catch { /* 跳过畸形行 */ }
    }
  }
}

/** 从一行 SSE data 载荷中提取事件对象（供 react-native-sse 的 event.data 使用）。 */
export function parseSSEData(payload: string): any {
  try {
    return JSON.parse(payload)
  } catch {
    return null
  }
}

/**
 * 把事件流规整为「增量内容/结束/错误」三类：
 * - {type:'delta'} → 产出 content 字符串
 * - {type:'done'} → 结束
 * - {type:'error'} → 抛错
 * - 其它事件（pipeline/import-book 的 stage）→ 原样产出对象
 */
export async function* consumeSSE(events: AsyncGenerator<any, void, unknown>): AsyncGenerator<any> {
  for await (const evt of events) {
    if (evt.type === 'delta') yield evt.content
    else if (evt.type === 'done') return
    else if (evt.type === 'error') throw new Error(evt.content || evt.message || '请求失败')
    else yield evt
  }
}
