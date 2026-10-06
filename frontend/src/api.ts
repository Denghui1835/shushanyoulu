import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

// 社区登录 token（localStorage 持久化，axios 自动带上 Authorization）
let authToken = localStorage.getItem('yq_token') || ''
if (authToken) http.defaults.headers.common['Authorization'] = `Bearer ${authToken}`
export const setAuthToken = (token: string) => {
  authToken = token || ''
  if (authToken) {
    localStorage.setItem('yq_token', authToken)
    http.defaults.headers.common['Authorization'] = `Bearer ${authToken}`
  } else {
    localStorage.removeItem('yq_token')
    delete http.defaults.headers.common['Authorization']
  }
}
export const getAuthToken = () => authToken

export const api = {
  // 社区账号
  register: (username: string, password: string) =>
    http.post('/auth/register', { username, password }).then(r => r.data),
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }).then(r => r.data),
  logout: () => http.post('/auth/logout').then(r => r.data),
  me: () => http.get('/auth/me').then(r => r.data),
  // 社区广场
  getCategories: () => http.get('/community/categories').then(r => r.data),
  getPlaza: (params?: any) => http.get('/community/plaza', { params }).then(r => r.data),
  publishProject: (id: string) => http.post(`/community/projects/${id}/publish`).then(r => r.data),
  unpublishProject: (id: string) => http.post(`/community/projects/${id}/unpublish`).then(r => r.data),
  patchProject: (id: string, data: any) => http.patch(`/community/projects/${id}`, data).then(r => r.data),
  learnProject: (id: string) => http.post(`/community/plaza/${id}/learn`).then(r => r.data),
  getPlazaDetail: (id: string) => http.get(`/community/plaza/${id}`).then(r => r.data),
  starProject: (id: string) => http.post(`/community/plaza/${id}/star`).then(r => r.data),
  unstarProject: (id: string) => http.post(`/community/plaza/${id}/unstar`).then(r => r.data),
  forkProject: (id: string) => http.post(`/community/plaza/${id}/fork`).then(r => r.data),
getSuggestions: (id: string) => http.get(`/community/plaza/${id}/suggestions`).then(r => r.data),
createSuggestion: (id: string, content: string) => http.post(`/community/plaza/${id}/suggestions`, { content }).then(r => r.data),
// 一起学（学习动态 / 点赞鼓励 / 排行榜）
getSocialFeed: (limit = 50) => http.get('/social/feed', { params: { limit } }).then(r => r.data),
likeSocialPost: (postId: string) => http.post(`/social/posts/${postId}/like`).then(r => r.data),
getSocialLeaderboard: (days = 7) => http.get('/social/leaderboard', { params: { days } }).then(r => r.data),
acceptSuggestion: (pid: string, sid: string) => http.post(`/community/projects/${pid}/suggestions/${sid}/accept`).then(r => r.data),
  applySuggestion: (pid: string, sid: string) => http.post(`/community/projects/${pid}/suggestions/${sid}/applied`).then(r => r.data),
  rejectSuggestion: (pid: string, sid: string) => http.post(`/community/projects/${pid}/suggestions/${sid}/reject`).then(r => r.data),

  // 个人中心
  getProfileInfo: () => http.get('/profile').then(r => r.data),
  updateProfileInfo: (data: any) => http.patch('/profile', data).then(r => r.data),
  getApiKey: () => http.get('/profile/apikey').then(r => r.data),
  saveApiKey: (data: any) => http.put('/profile/apikey', data).then(r => r.data),
  deleteApiKey: () => http.delete('/profile/apikey').then(r => r.data),
  testApiKey: (data: any) => http.post('/profile/apikey/test', data).then(r => r.data),
  // 服务商配置（按能力分档：text / vision / tts）
  getProviderPresets: () => http.get('/profile/provider-presets').then(r => r.data),
  getProviderConfigs: () => http.get('/profile/providers').then(r => r.data),
  saveProviderConfig: (capability: string, data: any) =>
    http.put(`/profile/providers/${capability}`, data).then(r => r.data),
  deleteProviderConfig: (capability: string) =>
    http.delete(`/profile/providers/${capability}`).then(r => r.data),
  testProviderConfig: (data: any) => http.post('/profile/providers/test', data).then(r => r.data),
  listProviderModels: (data: any) => http.post('/profile/providers/models', data).then(r => r.data),
  // 系统 / 元信息（设置页的「API 接口」用）
  getApiRoutes: () => http.get('/system/routes').then(r => r.data),
  // 管理后台（仅管理员；非管理员后端一律 403）
  adminListUsers: () => http.get('/admin/users').then(r => r.data),
  adminResetPassword: (uid: string, newPassword: string) =>
    http.post(`/admin/users/${uid}/reset-password`, { new_password: newPassword }).then(r => r.data),
  adminSetActive: (uid: string, isActive: boolean) =>
    http.post(`/admin/users/${uid}/active`, { is_active: isActive }).then(r => r.data),
  adminDeletePreview: (uid: string) => http.get(`/admin/users/${uid}/delete-preview`).then(r => r.data),
  adminDeleteUser: (uid: string, confirmUsername: string) =>
    http.post(`/admin/users/${uid}/delete`, { confirm_username: confirmUsername }).then(r => r.data),
  // 微信绑定
  wechatBind: (code: string) => http.post('/auth/wechat/bind', { code }).then(r => r.data),
  wechatUnbind: () => http.post('/auth/wechat/unbind').then(r => r.data),
  // companion
  getStatus: () => http.get('/companion/status').then(r => r.data),
  getStudyContext: () => http.get('/study/context').then(r => r.data),
  setStudyContext: (data: { project_id?: string; project_title?: string; subject?: string; topic?: string }) =>
    http.post('/study/context', data).then(r => r.data),
  getProfile: () => http.get('/companion/profile').then(r => r.data),
  saveProfile: (data: any) => http.post('/companion/profile', data).then(r => r.data),
  getSession: () => http.get('/companion/session').then(r => r.data),
  getMessages: (sessionId: string) =>
    http.get('/companion/messages', { params: { session_id: sessionId } }).then(r => r.data),
  createPlan: (data?: any) => http.post('/companion/plan', data).then(r => r.data),
  adjustPlan: () => http.post('/companion/plan/adjust').then(r => r.data),
  generateWizardPlan: (data: { courses: string[]; time_slots: string[]; daily_minutes: number; total_days: number }) =>
    http.post('/companion/plan/wizard', data).then(r => r.data),

  // 深度教学（讲→考→判→评）
  getCurriculum: () => http.get('/lesson/curriculum').then(r => r.data),
  getLessonProgress: () => http.get('/lesson/progress').then(r => r.data),
  setLessonProgress: (data: { subject: string; topic: string; status: string }) =>
    http.post('/lesson/progress', data).then(r => r.data),

  // 老教授课堂（一对一交互式授课）
  getCourseOutline: (subject: string) => http.get('/course', { params: { subject } }).then(r => r.data),
  startCourseLesson: (subject: string, topic: string) =>
    http.post('/course/lesson', { topic }, { params: { subject } }).then(r => r.data),
  answerCourseLesson: (subject: string, data: { topic: string; kind: string; answer: string; attempt: number }) =>
    http.post('/course/answer', data, { params: { subject } }).then(r => r.data),
  completeCourseLesson: (subject: string, topic: string) =>
    http.post('/course/complete', { topic }, { params: { subject } }).then(r => r.data),
  startLesson: (data: { subject: string; topic: string }) =>
    http.post('/lesson/start', data).then(r => r.data),
  answerLesson: (data: { lesson_id: string; answer: string }) =>
    http.post('/lesson/answer', data).then(r => r.data),
  endLesson: (id: string) => http.post(`/lesson/${id}/end`).then(r => r.data),

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
  // 作品社区：导出/导入
  exportProjectUrl: (id: string) => `/api/projects/export/${id}`,
  importProject: (file: File, title?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (title) fd.append('title', title)
    return http.post('/projects/import', fd).then(r => r.data)
  },
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
  // 全真模拟考试（严格仿 NCRE-2：120 分钟、40 选择 + 60 操作；subject=python/c）
  getMockExam: (subject = 'python') => http.get('/questions/mock', { params: { subject } }).then(r => r.data),
  gradeMockExam: (answers: Record<string, string>, subject = 'python') =>
    http.post('/questions/mock/grade', { answers, subject }).then(r => r.data),
  getMockHistory: () => http.get('/questions/mock/history').then(r => r.data),

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
  // 每日打卡
  getCheckin: () => http.get('/study/checkin').then(r => r.data),
  doCheckin: () => http.post('/study/checkin').then(r => r.data),

  // reading: content
  getReadingContent: (docId: string) =>
    http.get(`/reading/${docId}/content`).then(r => r.data),

  // 听读：原文逐句朗读 + 逐句时间轴
  listenStatus: (docId: string, params?: { voice?: string; speed?: number }) =>
    http.get('/listen/status', { params: { document_id: docId, ...params } }).then(r => r.data),
  listenPrepare: (data: { document_id: string; unit_index: number; voice?: string; speed?: number }) =>
    http.post('/listen/prepare', data).then(r => r.data),

  // 听读：讲（Episode）—— 播放列表/连播/断点续听的单位
  listenAlbum: (projectId: string, kind = 'read') =>
    http.get('/listen/album', { params: { project_id: projectId, kind } }).then(r => r.data),
  listenEpisodes: (docId: string, params?: { kind?: string; voice?: string; speed?: number }) =>
    http.get('/listen/episodes', { params: { document_id: docId, ...params } }).then(r => r.data),
  listenEpisodeDetail: (id: string) =>
    http.get(`/listen/episodes/${id}`).then(r => r.data),
  /** 开始生成；立刻返回（202），进度走 listenEpisodeEvents */
  listenEpisodeGenerate: (id: string) =>
    http.post(`/listen/episodes/${id}/generate`).then(r => r.data),
  listenEpisodeEventsUrl: (id: string) => `/api/listen/episodes/${id}/events`,
  listenEpisodeAudioUrl: (id: string) => `/api/listen/episodes/${id}/audio`,
  listenSaveProgress: (id: string, data: { position_ms: number; finished?: boolean }) =>
    http.put(`/listen/episodes/${id}/progress`, data).then(r => r.data),
  listenContinue: (projectId?: string) =>
    http.get('/listen/continue', { params: { project_id: projectId } }).then(r => r.data),

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
  // 关键词挖空背诵
  getBlankContent: (docId: string, unitIndex: number) =>
    http.get(`/reading/${docId}/blank`, { params: { unit_index: unitIndex } }).then(r => r.data),
  // PDF 自由绘制批注
  listDrawings: (docId: string) => http.get(`/reading/${docId}/drawings`).then(r => r.data),
  saveDrawings: (docId: string, unitIndex: number, strokes: any[]) =>
    http.post(`/reading/${docId}/drawings/${unitIndex}`, { strokes }).then(r => r.data),
  clearDrawings: (docId: string, unitIndex: number) =>
    http.delete(`/reading/${docId}/drawings/${unitIndex}`).then(r => r.data),

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
  // 文稿修改：打字/语音输入修改要求（AI 辅助）
  editPodcastScript: (docId: string, unitIndex: number, instruction: string) =>
    http.post(`/podcast/${docId}/edit-script`, { instruction }, { params: { unit_index: unitIndex } }).then(r => r.data),
  // 文稿手动保存（直接编辑，不经 AI）
  savePodcastScript: (docId: string, unitIndex: number, content: string) =>
    http.put(`/podcast/${docId}/script`, { content }, { params: { unit_index: unitIndex } }).then(r => r.data),
  // 撤回上一步修改
  undoPodcastScript: (docId: string, unitIndex: number) =>
    http.post(`/podcast/${docId}/undo-script`, null, { params: { unit_index: unitIndex } }).then(r => r.data),

  // 统计看板
  getDashboardStats: () => http.get('/stats/dashboard').then(r => r.data),

  // 通用裸调用（看板等动态路径用；http 已含 /api baseURL）
  callRaw: (path: string, opts?: { method?: string; body?: any }) => {
    const method = (opts?.method || 'GET').toLowerCase()
    const url = path.startsWith('/') ? path : `/${path}`
    if (method === 'get') return http.get(url).then(r => r.data)
    if (method === 'delete') return http.delete(url).then(r => r.data)
    if (method === 'put') return http.put(url, opts?.body).then(r => r.data)
    return http.post(url, opts?.body).then(r => r.data)
  },
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
 * 消费 **GET** 型 SSE（听读讲生成进度用）。
 *
 * 已经有的是 POST 型 streamSSE——生成进度是「开始」和「看进度」两步分开的，
 * 进度这条要能反复重连（换标签页/刷新都在看同一场生成），所以是 GET。
 * 完成后主动关闭连接：浏览器的 EventSource 会自己重连，这里用 fetch 流手动控制。
 */
export async function* streamSSEGet(url: string, signal?: AbortSignal): AsyncGenerator<any> {
  const resp = await fetch(url, { headers: { Accept: 'text/event-stream' }, signal })
  for await (const evt of readSSE(resp)) yield evt
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
