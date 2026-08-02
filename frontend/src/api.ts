import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

export const api = {
  // companion
  getStatus: () => http.get('/companion/status').then(r => r.data),
  getProfile: () => http.get('/companion/profile').then(r => r.data),
  saveProfile: (data: any) => http.post('/companion/profile', data).then(r => r.data),
  getSession: () => http.get('/companion/session').then(r => r.data),
  getMessages: (sessionId: string) =>
    http.get('/companion/messages', { params: { session_id: sessionId } }).then(r => r.data),
  createPlan: (data?: any) => http.post('/companion/plan', data).then(r => r.data),

  // projects（书架中的书）
  listProjects: () => http.get('/projects').then(r => r.data),
  createProject: (data: any) => http.post('/projects', data).then(r => r.data),
  getProject: (id: string) => http.get(`/projects/${id}`).then(r => r.data),
  updateProject: (id: string, data: any) => http.put(`/projects/${id}`, data).then(r => r.data),
  deleteProject: (id: string) => http.delete(`/projects/${id}`).then(r => r.data),
  reorderProjectDocs: (id: string, document_ids: string[]) =>
    http.post(`/projects/${id}/reorder`, { document_ids }).then(r => r.data),
  /** 新建分组（部分/卷）：可把指定章节纳入分组 */
  createGroup: (projectId: string, data: { title: string; chapter_ids?: string[] }) =>
    http.post(`/projects/${projectId}/groups`, data).then(r => r.data),
  /** 语音助手：对话 + 提议章节修改（SSE）。 */
  agentChat: (projectId: string, message: string, history: any[]) =>
    streamSSE(`/api/projects/${projectId}/agent`, { message, history }),
  importBook: (projectId: string, file: File, startPage?: number, endPage?: number) => {
    const fd = new FormData()
    fd.append('file', file)
    if (startPage) fd.append('start_page', String(startPage))
    if (endPage) fd.append('end_page', String(endPage))
    return streamSSEForm(`/api/projects/${projectId}/import-book`, fd)
  },
  // 手动建章（空白 / 划页）/ 章节分页调节 / 空白章节上传
  createProjectChapter: (projectId: string, data: any) =>
    http.post(`/projects/${projectId}/chapters`, data).then(r => r.data),
  syncProjectChapters: (projectId: string, chapters: any[]) =>
    http.post(`/projects/${projectId}/chapters/sync`, { chapters }).then(r => r.data),
  attachChapterFile: (projectId: string, documentId: string, file: File, chapterTitle?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (chapterTitle) fd.append('chapter_title', chapterTitle)
    return http.post(`/projects/${projectId}/chapters/${documentId}/attach`, fd).then(r => r.data)
  },
  /** 文档原文件 URL（阅读页原生视图 / 前端渲染用） */
  documentFileUrl: (docId: string) => `/api/documents/${docId}/file`,
  /** 章节所属整书原文件 URL（章节内容预览用） */
  documentBookFileUrl: (docId: string) => `/api/documents/${docId}/book-file`,

  // documents
  listDocuments: (projectId?: string) =>
    http.get('/documents', { params: { project_id: projectId } }).then(r => r.data),
  uploadDocument: (file: File, opts?: { project_id?: string; chapter_title?: string }) => {
    const fd = new FormData()
    fd.append('file', file)
    if (opts?.project_id) fd.append('project_id', opts.project_id)
    if (opts?.chapter_title) fd.append('chapter_title', opts.chapter_title)
    return http.post('/documents/upload', fd).then(r => r.data)
  },
  updateDocument: (id: string, data: any) =>
    http.put(`/documents/${id}`, data).then(r => r.data),
  deleteDocument: (id: string) => http.delete(`/documents/${id}`).then(r => r.data),

  // knowledge
  getKnowledgeTree: (docId: string) => http.get(`/knowledge/${docId}`).then(r => r.data),
  generateKnowledgeTree: (docId: string) =>
    http.post(`/knowledge/${docId}/generate`).then(r => r.data),

  // questions
  listQuestions: (docId: string, params?: { include_discarded?: boolean; mistake_book?: boolean }) =>
    http.get(`/questions/${docId}`, { params }).then(r => r.data),
  generateQuestions: (docId: string, count = 8) =>
    http.post(`/questions/${docId}/generate`, null, { params: { count } }).then(r => r.data),
  gradeQuestion: (qid: string, userAnswer: string) =>
    http.post(`/questions/${qid}/grade`, { user_answer: userAnswer }).then(r => r.data),
  // 题目管理：弃用/恢复、错题本
  discardQuestion: (qid: string) => http.post(`/questions/${qid}/discard`).then(r => r.data),
  restoreQuestion: (qid: string) => http.post(`/questions/${qid}/restore`).then(r => r.data),
  addToMistakeBook: (qid: string) => http.post(`/questions/${qid}/mistake-book`).then(r => r.data),
  removeFromMistakeBook: (qid: string) =>
    http.delete(`/questions/${qid}/mistake-book`).then(r => r.data),
  getMistakeQuestions: () => http.get('/questions/mistakes').then(r => r.data),

  // flashcards
  listFlashcards: (docId: string, include_discarded = false) =>
    http.get(`/flashcards/${docId}`, { params: { include_discarded } }).then(r => r.data),
  generateFlashcards: (docId: string, count = 15) =>
    http.post(`/flashcards/${docId}/generate`, null, { params: { count } }).then(r => r.data),
  getDueCards: () => http.get('/flashcards/due').then(r => r.data),
  reviewCard: (cardId: string, rating: number) =>
    http.post(`/flashcards/${cardId}/review`, { rating }).then(r => r.data),
  // 闪卡管理：弃用/恢复/删除
  discardFlashcard: (cardId: string) => http.post(`/flashcards/${cardId}/discard`).then(r => r.data),
  restoreFlashcard: (cardId: string) => http.post(`/flashcards/${cardId}/restore`).then(r => r.data),
  deleteFlashcard: (cardId: string) => http.delete(`/flashcards/${cardId}`).then(r => r.data),

  // pipeline
  runPipeline: (docId: string) => http.post(`/pipeline/${docId}/run`).then(r => r.data),

  // study
  getPlan: () => http.get('/study/plan').then(r => r.data),
  completeTask: (taskId: string) =>
    http.post(`/study/tasks/${taskId}/complete`).then(r => r.data),
  getActivity: () => http.get('/study/activity').then(r => r.data),

  // reading: content
  getReadingContent: (docId: string) =>
    http.get(`/reading/${docId}/content`).then(r => r.data),
  // reading: annotations
  listAnnotations: (docId: string) =>
    http.get(`/reading/${docId}/annotations`).then(r => r.data),
  createAnnotation: (docId: string, data: any) =>
    http.post(`/reading/${docId}/annotations`, data).then(r => r.data),
  updateAnnotation: (annId: string, content: string) =>
    http.put(`/reading/annotations/${annId}`, { content }).then(r => r.data),
  deleteAnnotation: (annId: string) =>
    http.delete(`/reading/annotations/${annId}`).then(r => r.data),
  // reading: summaries
  listSummaries: (docId: string) =>
    http.get(`/reading/${docId}/summaries`).then(r => r.data),
  generateSummary: (docId: string, scope: string, unitIndex?: number) =>
    http.post(`/reading/${docId}/summarize`, { scope, unit_index: unitIndex }).then(r => r.data),

  // AI 播客（每阅读单元独立一条）：文稿生成/查询、音频生成/试听
  getPodcastScript: (docId: string, unitIndex: number) =>
    http.get(`/podcast/${docId}/script`, { params: { unit_index: unitIndex } }).then(r => r.data),
  generatePodcastScript: (docId: string, unitIndex: number) =>
    http.post(`/podcast/${docId}/script`, null, { params: { unit_index: unitIndex } }).then(r => r.data),
  generatePodcastAudio: (docId: string, unitIndex: number) =>
    http.post(`/podcast/${docId}/audio`, null, { params: { unit_index: unitIndex } }).then(r => r.data),
  podcastAudioUrl: (docId: string, unitIndex: number) =>
    `/api/podcast/${docId}/audio?unit_index=${unitIndex}`,
  // 播客库：列表 / 删除
  listPodcasts: () => http.get('/podcast/list').then(r => r.data),
  deletePodcast: (docId: string, unitIndex: number) =>
    http.delete(`/podcast/${docId}`, { params: { unit_index: unitIndex } }).then(r => r.data),
  // 文稿修改：打字/语音输入修改要求
  editPodcastScript: (docId: string, unitIndex: number, instruction: string) =>
    http.post(`/podcast/${docId}/edit-script`, { instruction }, { params: { unit_index: unitIndex } }).then(r => r.data),
}

/** 解析 SSE 响应为事件对象序列。 */
async function* readSSE(resp: Response): AsyncGenerator<any> {
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
      try { yield JSON.parse(payload) } catch { /* 跳过畸形行 */ }
    }
  }
}

/**
 * 消费 SSE 事件流。
 * - delta 事件 → 产出 content 字符串（对话流式用）
 * - done → 结束
 * - error → 抛错
 * - 其他事件（pipeline/import-book 的 stage 事件）→ 原样产出事件对象
 */
export async function* streamSSE(url: string, body: any): AsyncGenerator<any> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  for await (const evt of readSSE(resp)) {
    if (evt.type === 'delta') yield evt.content
    else if (evt.type === 'done') return
    else if (evt.type === 'error') throw new Error(evt.content || evt.message || '请求失败')
    else yield evt
  }
}

/** 同上，但用 FormData（multipart）发起，用于整书导入等。
 *  注意：done 事件也产出（内含 message/warnings，供导入页展示），由调用方结束循环。 */
export async function* streamSSEForm(url: string, formData: FormData): AsyncGenerator<any> {
  const resp = await fetch(url, { method: 'POST', body: formData })
  for await (const evt of readSSE(resp)) {
    if (evt.type === 'delta') yield evt.content
    else if (evt.type === 'error') throw new Error(evt.content || evt.message || '请求失败')
    else yield evt
  }
}
