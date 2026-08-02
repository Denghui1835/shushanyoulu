/**
 * 元气搭子 · 移动端 API 层
 * fetch + FormData + react-native-sse 流式；token 走 SecureStore。
 * 后端地址见 src/config.ts（EXPO_PUBLIC_API_URL / app.json extra.apiBaseUrl）。
 */
import EventSource from 'react-native-sse'
import { API_BASE_URL, fullUrl } from './config'
import { getToken } from './tokenStore'
import { parseSSEData } from '../../shared/sse'

// ---------------------------------------------------------------- 基础请求

async function headers(withJson = true): Promise<Record<string, string>> {
  const h: Record<string, string> = {}
  if (withJson) h['Content-Type'] = 'application/json'
  const token = await getToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: await headers(!!body) }
  if (body !== undefined) init.body = JSON.stringify(body)
  const resp = await fetch(`${API_BASE_URL}${path}`, init)
  if (!resp.ok) {
    let detail = `请求失败 ${resp.status}`
    try {
      const j = await resp.json()
      if (j?.detail) detail = String(j.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

const get = <T>(path: string) => req<T>('GET', path)
const post = <T>(path: string, body?: unknown) => req<T>('POST', path, body)
const put = <T>(path: string, body?: unknown) => req<T>('PUT', path, body)
const del = <T>(path: string) => req<T>('DELETE', path)

async function upload<T>(path: string, form: FormData): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form, headers: await headers(false) })
  if (!resp.ok) {
    let detail = `上传失败 ${resp.status}`
    try {
      const j = await resp.json()
      if (j?.detail) detail = String(j.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

// ---------------------------------------------------------------- SSE 流式（react-native-sse）

function streamSSE(path: string, body: unknown): AsyncGenerator<any> {
  return (async function* () {
    const es = new EventSource(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      pollingInterval: 0,
    })
    const queue: any[] = []
    let done = false
    let error: Error | null = null
    let waiter: (() => void) | null = null

    es.addEventListener('message', (e) => {
      const evt = parseSSEData((e as any).data)
      if (evt) queue.push(evt)
      if (waiter) { const w = waiter; waiter = null; w() }
    })
    es.addEventListener('error', () => { error = new Error('流式连接中断'); done = true; if (waiter) { const w = waiter; waiter = null; w() } })
    es.addEventListener('close', () => { done = true; if (waiter) { const w = waiter; waiter = null; w() } })

    try {
      while (true) {
        if (queue.length) {
          const evt = queue.shift()
          if (evt.type === 'delta') yield evt.content
          else if (evt.type === 'done') return
          else if (evt.type === 'error') throw new Error(evt.content || evt.message || '请求失败')
          else yield evt
        } else if (done) {
          if (error) throw error
          return
        } else {
          await new Promise<void>(res => { waiter = res })
        }
      }
    } finally {
      es.removeAllEventListeners()
      es.close()
    }
  })()
}

// ---------------------------------------------------------------- API

export const api = {
  // 伴学
  getStatus: () => get('/api/companion/status'),
  getProfile: () => get('/api/companion/profile'),
  saveProfile: (data: any) => post('/api/companion/profile', data),
  getSession: () => get('/api/companion/session'),
  getMessages: (sessionId: string) => get(`/api/companion/messages?session_id=${sessionId}`),
  createPlan: (data?: any) => post('/api/companion/plan', data),
  adjustPlan: () => post('/api/companion/plan/adjust'),
  chat: (sessionId: string, message: string) => streamSSE('/api/companion/chat', { session_id: sessionId, message }),

  // 打卡
  getCheckin: () => get('/api/study/checkin'),
  doCheckin: () => post('/api/study/checkin'),

  // 计划
  getPlan: () => get('/api/study/plan'),
  completeTask: (taskId: string) => post(`/api/study/tasks/${taskId}/complete`),

  // 书架 / 项目
  listProjects: () => get('/api/projects'),
  createProject: (data: any) => post('/api/projects', data),
  getProject: (id: string) => get(`/api/projects/${id}`),
  deleteProject: (id: string) => del(`/api/projects/${id}`),
  importProject: (file: any, title?: string) => {
    const fd = new FormData()
    fd.append('file', { uri: file.uri, name: file.name ?? 'project.yqp', type: file.mimeType ?? 'application/octet-stream' } as any)
    if (title) fd.append('title', title)
    return upload('/api/projects/import', fd)
  },
  exportProjectUrl: (id: string) => fullUrl(`/api/projects/export/${id}`),

  // 文档
  listDocuments: () => get('/api/documents'),

  // 题目 / 闪卡
  listQuestions: (docId: string, params?: Record<string, any>) =>
    get(`/api/questions/${docId}?${new URLSearchParams(params).toString()}`),
  generateQuestions: (docId: string, count = 8) => post(`/api/questions/${docId}/generate?count=${count}`),
  gradeQuestion: (qid: string, answer: string) => post(`/api/questions/${qid}/grade`, { user_answer: answer }),
  discardQuestion: (qid: string) => post(`/api/questions/${qid}/discard`),
  restoreQuestion: (qid: string) => post(`/api/questions/${qid}/restore`),
  addToMistakeBook: (qid: string) => post(`/api/questions/${qid}/mistake-book`),
  removeFromMistakeBook: (qid: string) => del(`/api/questions/${qid}/mistake-book`),
  listFlashcards: (docId: string, includeDiscarded = false) =>
    get(`/api/flashcards/${docId}?include_discarded=${includeDiscarded}`),
  generateFlashcards: (docId: string, count = 15) => post(`/api/flashcards/${docId}/generate?count=${count}`),
  getDueCards: () => get('/api/flashcards/due'),
  reviewCard: (cardId: string, rating: number) => post(`/api/flashcards/${cardId}/review`, { rating }),
  discardFlashcard: (cardId: string) => post(`/api/flashcards/${cardId}/discard`),
  restoreFlashcard: (cardId: string) => post(`/api/flashcards/${cardId}/restore`),

  // 阅读
  getReadingContent: (docId: string) => get(`/api/reading/${docId}/content`),
  listAnnotations: (docId: string) => get(`/api/reading/${docId}/annotations`),
  createAnnotation: (docId: string, data: any) => post(`/api/reading/${docId}/annotations`, data),
  deleteAnnotation: (annId: string) => del(`/api/reading/annotations/${annId}`),

  // 播客
  getPodcastScript: (docId: string, unitIndex: number) => get(`/api/podcast/${docId}/script?unit_index=${unitIndex}`),
  generatePodcastScript: (docId: string, unitIndex: number) => post(`/api/podcast/${docId}/script?unit_index=${unitIndex}`),
  generatePodcastAudio: (docId: string, unitIndex: number) => post(`/api/podcast/${docId}/audio?unit_index=${unitIndex}`),
  editPodcastScript: (docId: string, unitIndex: number, instruction: string) =>
    post(`/api/podcast/${docId}/edit-script?unit_index=${unitIndex}`, { instruction }),
  savePodcastScript: (docId: string, unitIndex: number, content: string) =>
    put(`/api/podcast/${docId}/script?unit_index=${unitIndex}`, { content }),
  undoPodcastScript: (docId: string, unitIndex: number) => post(`/api/podcast/${docId}/undo-script?unit_index=${unitIndex}`),
  podcastAudioUrl: (docId: string, unitIndex: number) => fullUrl(`/api/podcast/${docId}/audio?unit_index=${unitIndex}`),
  listPodcasts: () => get('/api/podcast/list'),
  deletePodcast: (docId: string, unitIndex: number) => del(`/api/podcast/${docId}?unit_index=${unitIndex}`),

  // 社区
  register: (username: string, password: string) => post('/api/auth/register', { username, password }),
  login: (username: string, password: string) => post('/api/auth/login', { username, password }),
  logout: () => post('/api/auth/logout'),
  me: () => get('/api/auth/me'),
  getPlaza: () => get('/api/community/plaza'),
  publishProject: (id: string) => post(`/api/community/projects/${id}/publish`),
  unpublishProject: (id: string) => post(`/api/community/projects/${id}/unpublish`),
  learnProject: (id: string) => post(`/api/community/plaza/${id}/learn`),
}

export { streamSSE }
