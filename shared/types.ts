/**
 * 元气搭子 · 共享类型定义（纯 TS，不依赖任何浏览器/DOM/RN API）
 * 供移动端(Expo)使用；Web 端暂不改动，类型以这里为准。
 */

/** 学习项目（书架中的书） */
export interface Project {
  id: string
  title: string
  description: string
  icon: string
  document_count: number
  created_at: string
}

/** 整书元数据（多书混排时每本各自的页数与参考章节） */
export interface BookMeta {
  ref_document_id: string
  title: string
  total_pages: number | null
  chapter_count: number
}

/** 项目详情 */
export interface ProjectDetail {
  project: {
    id: string
    title: string
    description: string
    icon: string
    created_at: string
    book_total_pages: number | null
    books: BookMeta[]
  }
  documents: Chapter[]
}

/** 章节（= 归属于项目的文档） */
export interface Chapter {
  id: string
  title: string
  filename: string
  content_type: string
  chunk_count: number
  chapter_title: string
  sort_order: number
  parent_id: string | null
  is_group: boolean
  book_file: boolean
  book_ref_document_id: string | null
  page_start: number | null
  page_end: number | null
  knowledge_count: number
  question_count: number
  flashcard_count: number
}

/** 闪卡 */
export interface Flashcard {
  id: string
  document_id: string
  front: string
  back: string
  visual: string
  status: string
  due_at: string | null
  reps: number
  lapses: number
  discarded: boolean
}

/** 题目 */
export interface Question {
  id: string
  document_id: string
  qtype: 'choice' | 'fill' | 'essay'
  question: string
  options: string[]
  answer: string
  explanation: string
  source_text: string
  discarded: boolean
  in_mistake_book: boolean
  doc_title?: string
}

/** 播客文稿 */
export interface PodcastScript {
  id: string | null
  document_id: string
  unit_index: number
  content: string
  status: 'none' | 'generating' | 'done' | 'error'
  error: string
  has_audio: boolean
  can_undo: boolean
  audio_seconds: number
  updated_at: string | null
}

/** 伴学状态（首页） */
export interface CompanionStatus {
  user: { name: string; goal: string; daily_minutes: number; onboarded: boolean }
  plan: { title: string; summary: string; total_days: number; progress: { done: number; total: number } } | null
  today_tasks: { id: string; title: string; type: string; status: string }[]
  due_cards_count: number
  due_cards_preview: { front: string; back: string }[]
  points: number
  recent_activity: { kind: string; detail: string; at: string }[]
}

/** 打卡 */
export interface CheckIn {
  checked_today: boolean
  streak: number
  total: number
  points_gained?: number
}

/** 学习计划 */
export interface StudyPlan {
  plan: { id: string; title: string; summary: string; total_days: number; status: string } | null
  tasks: { id: string; day: number; scheduled_date: string; title: string; description: string; type: string; status: string }[]
}

/** 阅读单元 */
export interface ReadingUnit {
  index: number
  unit_type: 'page' | 'chunk'
  title: string
  text: string
}

/** 社区广场条目 */
export interface PlazaItem {
  id: string
  title: string
  description?: string
  icon?: string
  author?: string
  chapter_count: number
}

/** 社区我的项目 */
export interface MyProject {
  id: string
  title: string
  description: string
  icon: string
  is_public: boolean
}

/** 当前用户 + 我的项目 */
export interface MeInfo {
  user: { id: string; username: string; name: string }
  projects: MyProject[]
}
