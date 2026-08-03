/**
 * 书山有路 · 共享常量（纯 TS）
 */

/** 闪卡复习评分：1=再次 2=困难 3=良好 4=简单（与后端 FSRS schedule 对应） */
export const REVIEW_RATINGS = [
  { value: 1, label: '很模糊', color: '#999' },
  { value: 2, label: '有点难', color: '#fa8c16' },
  { value: 3, label: '记住了', color: '#1677ff' },
  { value: 4, label: '很简单', color: '#52c41a' },
] as const

/** 题目类型 */
export const QUESTION_TYPES = {
  choice: '选择题',
  fill: '填空题',
  essay: '简答题',
} as const

/** 计划任务类型 */
export const TASK_TYPES = {
  learn: '学习',
  practice: '练习',
  review: '复习',
  chat: '问答',
} as const

/** 文档/章节类型标签颜色（供 UI 取色） */
export const TYPE_TAG_COLOR: Record<string, string> = {
  pdf: '#722ed1',
  docx: '#1677ff',
  md: '#52c41a',
  txt: '#8c8c8c',
  pptx: '#fa8c16',
  blank: '#d48806',
}

/**
 * 项目导出/导入 `.yqp` 格式规范（zip）：
 *   manifest.json — {format_version, exported_at, project:{title,description,icon}}
 *   data.json     — {documents, chunks, knowledge, questions, quiz_records,
 *                    flashcards, summaries, annotations, podcasts}
 *   files/<docid>_<名> — 章节原文件
 *   audio/<scriptid>.mp3 — 播客音频
 * 导出时整书原文件（book_file_path）跳过（与章节重复、体积大）。
 */
export const YQP_FORMAT_VERSION = 1
