import { useEffect, useState } from 'react'
import {
  Button, Modal, Form, Input, InputNumber, Upload, Progress, message, Popconfirm,
  Empty, Spin, Space, Tag, Tooltip, List, Select, Segmented, Checkbox, Switch, Result,
} from 'antd'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import {
  ArrowUpOutlined, ArrowDownOutlined, EditOutlined, DeleteOutlined,
  PlusOutlined, ThunderboltOutlined, BookOutlined, AppstoreOutlined,
  EditFilled, ThunderboltFilled, ReadOutlined, FileTextOutlined, ColumnWidthOutlined,
  EyeOutlined, AudioOutlined, DownOutlined, RightOutlined, FolderOutlined,
  BulbOutlined, SoundOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { api, streamSSE } from '../api'
import ChapterPreviewModal from '../components/ChapterPreviewModal'
import VoiceAgentPanel from '../components/VoiceAgentPanel'
import KanbanBoard from '../components/KanbanBoard'

// 与 NativeFileView 相同的 worker（pdfjs-dist@4.8.69 与 react-pdf 内部一致）
GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

interface Chapter {
  id: string
  title: string
  filename: string
  content_type: string
  chunk_count: number
  chapter_title: string
  sort_order: number
  book_file?: boolean
  /** 该书参考章节 id（= project.books[].ref_document_id），用于定位整书原文件 */
  book_ref_document_id?: string | null
  /** 目录层级：所属分组 id（group 节点为 null） */
  parent_id?: string | null
  /** 是否分组节点（部分/卷），无内容只作目录分组 */
  is_group?: boolean
  page_start?: number | null
  page_end?: number | null
  knowledge_count: number
  question_count: number
  flashcard_count: number
}

/** 扁平章节列表 → 树：top 为顶层（分组+顶层章节），childrenOf[group_id] 为分组下章节。 */
function buildTree(docs: Chapter[]) {
  const byId: Record<string, Chapter> = {}
  docs.forEach(d => { byId[d.id] = d })
  const top: Chapter[] = []
  const childrenOf: Record<string, Chapter[]> = {}
  docs.forEach(d => {
    if (d.parent_id && byId[d.parent_id]) (childrenOf[d.parent_id] ??= []).push(d)
    else top.push(d)
  })
  const bySort = (a: Chapter, b: Chapter) => a.sort_order - b.sort_order
  top.sort(bySort)
  Object.values(childrenOf).forEach(arr => arr.sort(bySort))
  return { top, childrenOf }
}

/** 树的展示顺序（分组在前，其子章节跟在后面），供重排与渲染。 */
function flattenTree(docs: Chapter[]): Chapter[] {
  const { top, childrenOf } = buildTree(docs)
  const out: Chapter[] = []
  for (const n of top) {
    out.push(n)
    if (n.is_group) out.push(...(childrenOf[n.id] || []))
  }
  return out
}

/** 整书元数据（多书混排时每本各自的页数与参考章节） */
interface BookMeta {
  ref_document_id: string
  title: string
  total_pages: number | null
  chapter_count: number
}

const TYPE_TAG: Record<string, string> = { pdf: 'purple', docx: 'blue', md: 'green', txt: 'default', pptx: 'orange', blank: 'gold' }

// 书 → 模拟考试科目（仅这些科目有题库/模拟配置）
const MOCK_SUBJECTS: Record<string, string> = { 'Python程序设计': 'python', 'C语言程序设计': 'c' }

// 有课程大纲（老教授课堂）可用的学科
const COURSE_SUBJECTS = ['Python程序设计', 'C语言程序设计', '数学建模', '数学分析', '高等代数', '数理统计', '3DGS']

/** 调节器页带按书着色（下标对应 books 顺序） */
const BOOK_COLORS = ['#7c5cfc', '#36a3f7', '#52c41a', '#fa8c16', '#eb2f96']

/** 调节器里可编辑的章节行（document_id 为空 = 待新建的切片章节） */
interface RegChapter {
  key: string
  document_id: string | null
  /** 该行所属整书的参考章节 id：已有章节取其书；新建切片章节据此确定来源整书 */
  source_document_id: string | null
  title: string
  page_start: number
  page_end: number
}

export default function ProjectDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<any>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [loading, setLoading] = useState(true)

  const [editOpen, setEditOpen] = useState(false)
  const [editForm] = Form.useForm()

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadForm] = Form.useForm()

  const [pipeChapter, setPipeChapter] = useState<Chapter | null>(null)
  const [pipeProgress, setPipeProgress] = useState(0)
  const [pipeMsg, setPipeMsg] = useState('')

  // 整书导入（按目录分章；两步：选文件→页码范围→导入）
  const [bookOpen, setBookOpen] = useState(false)
  const [bookImporting, setBookImporting] = useState(false)
  const [bookProgress, setBookProgress] = useState(0)
  const [bookMsg, setBookMsg] = useState('')
  const [bookEntries, setBookEntries] = useState<{ title: string; page_number: number }[]>([])
  const [bookFile, setBookFile] = useState<File | null>(null)
  const [bookTotal, setBookTotal] = useState(0)
  const [bookStart, setBookStart] = useState(1)
  const [bookEnd, setBookEnd] = useState(1)
  const [bookLastHint, setBookLastHint] = useState('')

  const bookKey = () => `yq-book-import:${id}`

  // 新建章节（空白 / 划页）
  const [createOpen, setCreateOpen] = useState(false)
  const [createMode, setCreateMode] = useState<'blank' | 'slice'>('blank')
  const [createForm] = Form.useForm()
  const [creating, setCreating] = useState(false)
  const watchSource = Form.useWatch('source_document_id', createForm)

  // 章节分页调节器
  const [regOpen, setRegOpen] = useState(false)
  const [regChapters, setRegChapters] = useState<RegChapter[]>([])
  // 调节器「新建章节」的目标书（多书混排时选）
  const [newBookRef, setNewBookRef] = useState<string>('')

  // 章节内容预览：打开整书原文件预览某章页码范围，调整后回写调节器行
  const [preview, setPreview] = useState<{ key: string; docId: string; bookTitle: string; pageStart: number; pageEnd: number } | null>(null)

  // 语音助手（对话 + 提议章节修改）
  const [agentOpen, setAgentOpen] = useState(false)
  const [projView, setProjView] = useState<'chapters' | 'kanban'>('chapters')

  // 目录层级：折叠的分组 + 新建分组弹窗
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [groupOpen, setGroupOpen] = useState(false)
  const [groupForm] = Form.useForm()

  // 空白章节上传资料
  const [attachChapter, setAttachChapter] = useState<Chapter | null>(null)
  const [attaching, setAttaching] = useState(false)
  const [attachForm] = Form.useForm()

  const [loadErr, setLoadErr] = useState('')

  const load = async () => {
    setLoading(true)
    setLoadErr('')
    try {
      const d = await api.getProject(id)
      setProject(d.project)
      setChapters(d.documents)
    } catch (e: any) {
      setLoadErr(e?.response?.data?.detail || e?.message || '加载项目失败')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [id])

  // 多书元数据与按书查找（调节器/划页建章共用）
  const books: BookMeta[] = project?.books || []
  const bookByRef = (refId?: string | null) => books.find(b => b.ref_document_id === refId)
  // 划页建章：选中来源章节后取该书总页数做上限
  const srcChapter = chapters.find(c => c.id === watchSource)
  const srcTotal = bookByRef(srcChapter?.book_ref_document_id)?.total_pages || 0

  // ---------- 项目编辑 ----------
  const openEdit = () => {
    editForm.setFieldsValue(project)
    setEditOpen(true)
  }
  const saveProject = async () => {
    const values = await editForm.validateFields()
    await api.updateProject(id, values)
    message.success('已保存')
    setEditOpen(false)
    load()
  }
  const removeProject = async () => {
    await api.deleteProject(id)
    message.success('项目已删除')
    navigate('/bookshelf')
  }

  // ---------- 导入章节 ----------
  const customUpload = async (opt: any) => {
    setUploading(true)
    try {
      const chapter_title = uploadForm.getFieldValue('chapter_title') || ''
      await api.uploadDocument(opt.file, { project_id: id, chapter_title })
      message.success('章节已导入，开始学习吧')
      setUploadOpen(false)
      uploadForm.resetFields()
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '上传失败')
    } finally { setUploading(false) }
  }

  // ---------- 整书导入（识别目录→按章切分；页码范围分批） ----------
  const handleBookFileSelect = async (file: File) => {
    try {
      setBookFile(file)
      setBookMsg('正在读取页数…')
      const pdf = await getDocument(await file.arrayBuffer()).promise
      const total = pdf.numPages
      setBookTotal(total)
      // 记忆上次导入范围：默认续导
      let start = 1
      let end = total
      let hint = ''
      const lastRaw = localStorage.getItem(bookKey())
      if (lastRaw) {
        try {
          const last = JSON.parse(lastRaw)
          if (last.filename === file.name) {
            if (last.end < total) {
              start = last.end + 1
              hint = `上次导入了第 ${last.start}-${last.end} 页，本次默认继续`
            } else {
              hint = `上次已导入全书（第 ${last.start}-${last.end} 页）`
            }
          }
        } catch { /* 忽略损坏的本地记录 */ }
      }
      setBookStart(start)
      setBookEnd(end)
      setBookLastHint(hint)
      setBookMsg('')
    } catch {
      setBookFile(null)
      message.error('无法读取 PDF 页数，请确认文件有效')
    }
  }

  const runBookImport = async () => {
    if (!bookFile) { message.warning('请先选择 PDF 文件'); return }
    setBookImporting(true)
    setBookProgress(5)
    setBookMsg(`正在上传整书（第 ${bookStart}-${bookEnd} 页）…`)
    setBookEntries([])
    try {
      for await (const evt of api.importBook(id, bookFile, bookStart, bookEnd)) {
        if (evt.type === 'toc') {
          if (evt.status === 'done') {
            setBookEntries(evt.entries || [])
            setBookProgress(40)
            const src = evt.source === 'toc_page' ? '识别到目录页' : 'AI 归纳（无目录页）'
            setBookMsg(`${evt.message} · ${src}`)
          } else {
            setBookMsg(evt.message || '正在识别目录…')
          }
        } else if (evt.type === 'chapter') {
          setBookProgress(60)
          setBookMsg(evt.message)
        } else if (evt.type === 'done') {
          setBookProgress(100)
          setBookMsg(evt.message)
          if (evt.warnings?.length) message.warning(`分章完成，但有 ${evt.warnings.length} 条提示：${evt.warnings[0]}`)
          else message.success(evt.message)
        } else if (evt.type === 'error') {
          setBookProgress(100)
          setBookMsg(`⚠️ ${evt.message}`)
        }
      }
      // 记住本次导入范围，便于分批续导
      localStorage.setItem(bookKey(), JSON.stringify({ filename: bookFile.name, start: bookStart, end: bookEnd }))
    } catch (e: any) {
      setBookProgress(100)
      setBookMsg(`⚠️ ${e.message || '导入中断'}`)
    } finally {
      setBookImporting(false)
      load()
    }
  }

  // ---------- 新建章节（空白 / 划页） ----------
  const openCreate = () => {
    createForm.resetFields()
    setCreateMode('blank')
    setCreateOpen(true)
  }
  const submitCreate = async () => {
    const values = await createForm.validateFields()
    setCreating(true)
    try {
      const payload: any = { mode: createMode, title: values.title }
      if (createMode === 'slice') {
        payload.source_document_id = values.source_document_id
        payload.page_start = values.page_start
        payload.page_end = values.page_end
      }
      const doc = await api.createProjectChapter(id, payload)
      message.success(`章节「${doc.chapter_title || doc.title}」已创建`)
      setCreateOpen(false)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    } finally { setCreating(false) }
  }

  // ---------- 章节分页调节器 ----------
  const openReg = () => {
    setRegChapters(
      chapters
        .filter((c: any) => c.book_file && typeof c.page_start === 'number' && typeof c.page_end === 'number')
        .sort((a: any, b: any) => a.sort_order - b.sort_order)
        .map((c: any) => ({
          key: c.id, document_id: c.id, source_document_id: c.book_ref_document_id || null,
          title: c.chapter_title || c.title, page_start: c.page_start, page_end: c.page_end,
        })),
    )
    setNewBookRef(books[0]?.ref_document_id || '')
    setRegOpen(true)
  }
  const updateReg = (key: string, patch: Partial<RegChapter>) =>
    setRegChapters(list => list.map(r => (r.key === key ? { ...r, ...patch } : r)))

  const regSplit = (row: RegChapter) => {
    // 拆分：弹出切点（在 start+1 ~ end 之间）
    Modal.confirm({
      title: `拆分「${row.title}」`,
      content: (
        <div>
          <div style={{ marginBottom: 8, color: '#999', fontSize: 13 }}>
            当前范围第 {row.page_start + 1}-{row.page_end + 1} 页，在第几页后拆开？
          </div>
          <InputNumber style={{ width: '100%' }} min={row.page_start + 2} max={row.page_end + 1}
            defaultValue={Math.floor((row.page_start + row.page_end) / 2) + 1} id="yq-split-point" />
        </div>
      ),
      okText: '拆分', cancelText: '取消',
      onOk: () => {
        const el = document.getElementById('yq-split-point') as HTMLInputElement | null
        const p = el ? Number(el.value) : 0
        const splitAt = p - 1  // 0 基切点（后半段起点）
        if (!splitAt || splitAt <= row.page_start || splitAt > row.page_end) {
          message.warning('切点需在章节范围内')
          return Promise.reject()
        }
        const half2: RegChapter = {
          key: `new-${Date.now()}-${row.page_end}`, document_id: null,
          source_document_id: row.source_document_id,
          title: `${row.title}（续）`, page_start: splitAt, page_end: row.page_end,
        }
        setRegChapters(list => {
          const idx = list.findIndex(r => r.key === row.key)
          const next = [...list]
          next[idx] = { ...row, page_end: splitAt - 1 }
          next.splice(idx + 1, 0, half2)
          return next
        })
      },
    })
  }

  const regDelete = (row: RegChapter) => {
    setRegChapters(list => list.filter(r => r.key !== row.key))
  }

  const regAddNew = () => {
    const book = bookByRef(newBookRef) || books[0]
    const total = book?.total_pages || 0
    if (!total) { message.warning('该书没有有效的整书页数，无法新建章节'); return }
    // 该书内第一个未被覆盖的页作为新章节默认范围
    const covered = new Set<number>()
    regChapters
      .filter(r => r.source_document_id === book.ref_document_id)
      .forEach(r => { for (let i = r.page_start; i <= r.page_end; i++) covered.add(i) })
    let p = 0
    while (p < total && covered.has(p)) p++
    if (p >= total) { message.warning('该书全部页面均已覆盖，无需新建'); return }
    const end = Math.min(p + 2, total - 1)
    setRegChapters(list => [...list, {
      key: `new-${Date.now()}-${p}`, document_id: null, source_document_id: book.ref_document_id,
      title: `第 ${list.length + 1} 章`, page_start: p, page_end: end,
    }])
  }

  const saveReg = async () => {
    for (const r of regChapters) {
      const total = bookByRef(r.source_document_id)?.total_pages || 0
      if (!total || r.page_start < 0 || r.page_end >= total || r.page_start > r.page_end) {
        message.error(`章节「${r.title}」页码非法（${r.page_start + 1}-${r.page_end + 1}，应在所属书 1-${total}）`)
        return
      }
    }
    try {
      const res = await api.syncProjectChapters(id, regChapters.map(r => ({
        document_id: r.document_id,
        // 新建切片章节（document_id 为空）需带来源整书的参考章节 id
        source_document_id: r.document_id ? undefined : r.source_document_id,
        title: r.title, page_start: r.page_start, page_end: r.page_end,
      })))
      setProject(res.project)
      setChapters(res.documents)
      message.success('章节范围已保存并重切')
      setRegOpen(false)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  }

  // ---------- 空白章节上传资料 ----------
  const attachSave = async (opt: any) => {
    setAttaching(true)
    try {
      const chapterTitle = attachForm.getFieldValue('chapter_title') || ''
      const doc = await api.attachChapterFile(id, attachChapter!.id, opt.file, chapterTitle)
      message.success(`「${doc.chapter_title || doc.title}」资料已上传`)
      setAttachChapter(null)
      attachForm.resetFields()
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '上传失败')
    } finally { setAttaching(false) }
  }

  // ---------- 章节操作 ----------
  /** 同级内上下移动（分组内章节只在分组内移动） */
  const moveChapter = async (docId: string, dir: 1 | -1) => {
    const { top, childrenOf } = buildTree(chapters)
    const item = chapters.find(c => c.id === docId)
    if (!item) return
    const siblings = item.parent_id ? (childrenOf[item.parent_id] || []) : top
    const idx = siblings.findIndex(c => c.id === docId)
    const tgt = idx + dir
    if (tgt < 0 || tgt >= siblings.length) return
    const a = siblings[idx], b = siblings[tgt]
    const next = chapters.map(c => {
      if (c.id === a.id) return { ...c, sort_order: b.sort_order }
      if (c.id === b.id) return { ...c, sort_order: a.sort_order }
      return c
    })
    setChapters(next)
    await api.reorderProjectDocs(id, flattenTree(next).map(c => c.id))
  }

  // ---------- 目录分组（部分/卷） ----------
  const openGroup = () => { groupForm.resetFields(); setGroupOpen(true) }
  const submitGroup = async () => {
    const values = await groupForm.validateFields()
    const title = (values.title || '').trim()
    if (!title) { message.warning('请输入分组标题'); return }
    try {
      await api.createGroup(id, { title, chapter_ids: values.chapter_ids || [] })
      message.success('分组已创建')
      setGroupOpen(false)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    }
  }
  const moveChapterInto = async (docId: string, parentId: string | null) => {
    try {
      await api.updateDocument(docId, { parent_id: parentId })
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '移动失败')
    }
  }
  const removeGroup = async (g: Chapter) => {
    // 只删分组，其下章节保留并移到顶层
    try {
      const children = chapters.filter(c => c.parent_id === g.id)
      for (const ch of children) await api.updateDocument(ch.id, { parent_id: null })
      await api.deleteDocument(g.id)
      message.success('分组已删除，章节保留在顶层')
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const editChapter = async (c: Chapter) => {
    Modal.confirm({
      title: '编辑章节',
      content: <ChapterEdit c={c} onSave={async (title, chapter_title) => {
        await api.updateDocument(c.id, { title, chapter_title })
        message.success('已保存')
        load()
      }} />,
      okText: '保存', cancelText: '取消',
    })
  }

  const removeChapter = async (c: Chapter) => {
    await api.deleteDocument(c.id)
    message.success('章节已删除')
    load()
  }

  // ---------- 一键生成 ----------
  const runPipeline = async (c: Chapter) => {
    setPipeChapter(c)
    setPipeProgress(0)
    setPipeMsg('准备开始…')
    try {
      for await (const evt of streamSSE(`/api/pipeline/${c.id}/run`, {})) {
        const e = typeof evt === 'string' ? JSON.parse(evt) : evt
        // 后端 pipeline 事件字段是 stage（非 type），兼容两者
        const stage = e.stage || e.type
        if (stage === 'knowledge') { setPipeProgress(25); setPipeMsg('生成知识树…') }
        else if (stage === 'knowledge_done') { setPipeProgress(40); setPipeMsg(`知识树完成（${e.count} 节点）`) }
        else if (stage === 'quiz') { setPipeProgress(55); setPipeMsg('生成题目…') }
        else if (stage === 'quiz_done') { setPipeProgress(70); setPipeMsg(`题目完成（${e.count} 道）`) }
        else if (stage === 'flashcards') { setPipeProgress(80); setPipeMsg('生成闪卡…') }
        else if (stage === 'flashcards_done') { setPipeProgress(90); setPipeMsg(`闪卡完成（${e.count} 张）`) }
        else if (stage === 'done') { setPipeProgress(100); setPipeMsg('全部生成完成 🎉') }
        else if (stage === 'error') { setPipeProgress(100); setPipeMsg(`⚠️ ${e.message || '生成失败'}`) }
      }
    } catch { setPipeMsg('⚠️ 生成中断，请重试') }
    load()
  }

  const toggleCollapse = (gid: string) => {
    setCollapsed(prev => {
      const next = new Set(prev)
      if (next.has(gid)) next.delete(gid); else next.add(gid)
      return next
    })
  }

  /** 叶子章节行（含「移入分组」选择） */
  const renderLeaf = (c: Chapter, canUp: boolean, canDown: boolean, inGroup: boolean) => {
    const groups = chapters.filter(x => x.is_group)
    return (
      <div key={c.id} className="page-card yq-chapter-item" style={{ display: 'block', padding: 12, marginLeft: inGroup ? 28 : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <BookOutlined style={{ fontSize: 20, color: '#7c5cfc' }} />
          <div style={{ flex: 1, minWidth: 180 }}>
            <b>{c.chapter_title || c.title}</b>
            {c.chapter_title && c.chapter_title !== c.title && (
              <div style={{ fontSize: 12, color: '#999' }}>{c.filename}</div>
            )}
            <Space size={4} style={{ marginTop: 4 }}>
              <Tag color={TYPE_TAG[c.content_type] || 'default'}>{c.content_type}</Tag>
              {c.book_file && typeof c.page_start === 'number' && typeof c.page_end === 'number' && (
                <Tag color="cyan">第 {c.page_start + 1}-{c.page_end + 1} 页</Tag>
              )}
              <Tag>{c.chunk_count} 片段</Tag>
              {c.knowledge_count > 0 && <Tag color="purple">知识 {c.knowledge_count}</Tag>}
              {c.question_count > 0 && <Tag color="blue">题 {c.question_count}</Tag>}
              {c.flashcard_count > 0 && <Tag color="orange">卡 {c.flashcard_count}</Tag>}
            </Space>
          </div>

          <Space size={4}>
            <Tooltip title="阅读（批注/总结/听书）"><Button icon={<ReadOutlined />} onClick={() => navigate(`/reading?doc=${c.id}`)} /></Tooltip>
            <Tooltip title="知识树"><Button icon={<AppstoreOutlined />} onClick={() => navigate(`/knowledge?doc=${c.id}`)} /></Tooltip>
            <Tooltip title="练习"><Button icon={<EditFilled />} onClick={() => navigate(`/quiz?doc=${c.id}`)} /></Tooltip>
            <Tooltip title="闪卡"><Button icon={<ThunderboltFilled />} onClick={() => navigate(`/flashcards?doc=${c.id}`)} /></Tooltip>
            <Tooltip title="一键生成（知识树+题目+闪卡）"><Button icon={<ThunderboltOutlined />} onClick={() => runPipeline(c)} /></Tooltip>
          </Space>

          <Space size={2}>
            {c.content_type === 'blank' && (
              <Button size="small" icon={<FileTextOutlined />} onClick={() => { setAttachChapter(c); attachForm.resetFields() }}>
                上传资料
              </Button>
            )}
            <Tooltip title="移入分组">
              <Select
                size="small" style={{ width: 110 }}
                value={c.parent_id || ''}
                onChange={v => moveChapterInto(c.id, v || null)}
                options={[{ value: '', label: '顶层' }, ...groups.map(g => ({ value: g.id, label: (g.chapter_title || g.title).slice(0, 10) }))]}
              />
            </Tooltip>
            <Button size="small" type="text" icon={<ArrowUpOutlined />} disabled={!canUp} onClick={() => moveChapter(c.id, -1)} />
            <Button size="small" type="text" icon={<ArrowDownOutlined />} disabled={!canDown} onClick={() => moveChapter(c.id, 1)} />
            <Button size="small" type="text" icon={<EditOutlined />} onClick={() => editChapter(c)} />
            <Popconfirm title="删除该章节？" onConfirm={() => removeChapter(c)}>
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        </div>
      </div>
    )
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  if (loadErr || !project) return (
    <Result status="error" title="加载项目失败" subTitle={loadErr || '项目不存在'}
      extra={<Button type="primary" onClick={load}>重试</Button>} />
  )

  return (
    <div className="yq-page">
      {/* 项目头 */}
      <div className="page-card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 44 }}>{project?.icon || '📚'}</span>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            {project?.title}
            <Button size="small" type="text" icon={<EditOutlined />} onClick={openEdit} />
            <Popconfirm title="删除整个项目及其全部章节？" onConfirm={removeProject}>
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </h2>
          <div style={{ color: '#666', marginTop: 4 }}>{project?.description || '—'}</div>
          <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>
            共 {chapters.filter(c => !c.is_group).length} 个章节
            {chapters.some(c => c.is_group) ? `、${chapters.filter(c => c.is_group).length} 个分组` : ''}
          </div>
        </div>
        <Space>
          <Button icon={<AudioOutlined />} onClick={() => setAgentOpen(true)}>
            语音助手
          </Button>
          <Button icon={<BookOutlined />} onClick={() => setBookOpen(true)}>
            导入整本书
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            导入章节
          </Button>
          <Button icon={<PlusOutlined />} onClick={openCreate}>
            新建章节
          </Button>
          <Button icon={<FolderOutlined />} onClick={openGroup}>
            新建分组
          </Button>
          {project?.book_total_pages ? (
            <Button icon={<ColumnWidthOutlined />} onClick={openReg}>
              调节章节范围
            </Button>
          ) : null}
        </Space>
      </div>

      {/* 学习工具：按书聚合（从零学 → 练 → 考，入门到模拟） */}
      <div className="yq-section" style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, marginRight: 4 }}>🧰 学习工具：</span>
        {COURSE_SUBJECTS.includes(project?.subject || '') && (
          <Button type="primary" ghost icon={<BookOutlined />} onClick={() => navigate(`/course?subject=${encodeURIComponent(project.subject)}`)}>
            老教授课堂
          </Button>
        )}
        <Button type="primary" ghost icon={<BulbOutlined />} onClick={() => navigate(`/lesson?category=${project?.category || ''}&sub=${project?.category_sub || ''}`)}>
          深度教学
        </Button>
        <Button icon={<EditFilled />} onClick={() => {
          const qc = chapters.find(c => !c.is_group && (c.title || '').includes('题库'))
            || chapters.find(c => !c.is_group && (c.question_count || 0) > 0)
          navigate(qc ? `/quiz?doc=${qc.id}` : '/quiz')
        }}>
          刷题练习
        </Button>
        <Button icon={<SoundOutlined />} onClick={() => navigate(`/podcasts?project=${id}`)}>
          播客
        </Button>
        {(() => {
          const mockSubject = MOCK_SUBJECTS[project?.subject || '']
          const hasBank = chapters.some(c => (c.title || '').includes('题库'))
          if (!mockSubject || !hasBank) return null
          return (
            <Button icon={<ClockCircleOutlined />} onClick={() => navigate(`/mock-exam?subject=${mockSubject}`)}>
              全真模拟
            </Button>
          )
        })()}
      </div>

      {/* 视图切换：章节 / 看板 */}
      <div className="yq-section" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Segmented
          value={projView}
          onChange={v => setProjView(v as 'chapters' | 'kanban')}
          options={[
            { value: 'chapters', label: '📖 章节' },
            { value: 'kanban', label: '📋 看板' },
          ]}
        />
      </div>

      {/* 目录（章节视图） */}
      {projView === 'chapters' && (chapters.length === 0 ? (
        <div className="yq-section yq-empty-state">
          <div className="yq-empty-icon">📖</div>
          <Empty description="这本书还没有章节，可导入整本 PDF（自动按目录分章），或单章导入 PPT / 讲义" />
          <Space style={{ marginTop: 12 }}>
            <Button type="primary" icon={<BookOutlined />} onClick={() => setBookOpen(true)}>
              导入整本书
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
              导入单个章节
            </Button>
          </Space>
        </div>
      ) : (() => {
        const tree = buildTree(chapters)
        return (
          <div className="yq-chapter-list" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {tree.top.map((c, i) => {
              if (c.is_group) {
                const children = tree.childrenOf[c.id] || []
                const expanded = !collapsed.has(c.id)
                const canUp = i > 0
                const canDown = i < tree.top.length - 1
                return (
                  <div key={c.id}>
                    <div className="page-card yq-chapter-item" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px' }}>
                      <Button type="text" size="small" icon={expanded ? <DownOutlined /> : <RightOutlined />}
                        onClick={() => toggleCollapse(c.id)} />
                      <FolderOutlined style={{ fontSize: 20, color: '#7c5cfc' }} />
                      <b style={{ flex: 1 }}>{c.chapter_title || c.title}</b>
                      {typeof c.page_start === 'number' && typeof c.page_end === 'number' && (
                        <Tag color="cyan">第 {c.page_start + 1}-{c.page_end + 1} 页</Tag>
                      )}
                      <Tag>{children.length} 章</Tag>
                      <Space size={2}>
                        <Button size="small" type="text" icon={<ArrowUpOutlined />} disabled={!canUp} onClick={() => moveChapter(c.id, -1)} />
                        <Button size="small" type="text" icon={<ArrowDownOutlined />} disabled={!canDown} onClick={() => moveChapter(c.id, 1)} />
                        <Button size="small" type="text" icon={<EditOutlined />} onClick={() => editChapter(c)} />
                        <Popconfirm title="删除分组？其下章节会保留并移到顶层" onConfirm={() => removeGroup(c)}>
                          <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>
                    {expanded && children.map((ch, ci) => renderLeaf(ch, ci > 0, ci < children.length - 1, true))}
                  </div>
                )
              }
              return renderLeaf(c, i > 0, i < tree.top.length - 1, false)
            })}
          </div>
        )
      })())}

      {/* 看板视图 */}
      {projView === 'kanban' && (
        <div className="page-card">
          <KanbanBoard projectId={id} />
        </div>
      )}

      {/* 编辑项目 */}
      <Modal title="编辑项目" open={editOpen} onOk={saveProject} onCancel={() => setEditOpen(false)} okText="保存" cancelText="取消">
        <Form form={editForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="title" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="简介">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="icon" label="封面图标">
            <Input maxLength={8} />
          </Form.Item>
          <Form.Item name="blank_enabled" label="关键词挖空背诵" valuePropName="checked"
            tooltip="开启后，阅读页会多出「挖空」视图，把关键词藏起来死记硬背">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 导入章节 */}
      <Modal
        title="导入章节"
        open={uploadOpen}
        footer={null}
        onCancel={() => setUploadOpen(false)}
      >
        <Form form={uploadForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="chapter_title" label="章节标题（可选，如：第 3 讲 集合论）">
            <Input placeholder="留空则用文件名" />
          </Form.Item>
        </Form>
        <Upload.Dragger
          customRequest={customUpload}
          accept=".pdf,.docx,.md,.markdown,.txt,.pptx"
          showUploadList={false}
          disabled={uploading}
        >
          <p style={{ fontSize: 36, margin: 0 }}><FileTextOutlined style={{ color: '#7c5cfc' }} /></p>
          <p style={{ fontWeight: 600 }}>点击或拖拽上传本项目的章节资料</p>
          <p style={{ color: '#999' }}>PDF / Word / Markdown / TXT / PPT，上传后自动解析</p>
        </Upload.Dragger>
      </Modal>

      {/* 一键生成进度 */}
      <Modal title={`一键生成 · ${pipeChapter?.chapter_title || pipeChapter?.title}`} open={!!pipeChapter} footer={null} onCancel={() => setPipeChapter(null)}>
        <Progress percent={pipeProgress} status={pipeProgress === 100 ? 'success' : 'active'} />
        <div style={{ textAlign: 'center', color: '#666', marginTop: 12 }}>{pipeMsg}</div>
      </Modal>

      {/* 导入整本书（按目录分章；两步：选文件 → 页码范围 → 导入） */}
      <Modal
        title="导入整本书 · 自动分章"
        open={bookOpen}
        footer={null}
        onCancel={() => setBookOpen(false)}
        width={560}
      >
        <Upload.Dragger
          beforeUpload={(file) => { handleBookFileSelect(file as File); return false }}
          accept=".pdf"
          showUploadList={false}
          disabled={bookImporting}
        >
          <p style={{ fontSize: 36, margin: 0 }}><BookOutlined style={{ color: '#7c5cfc' }} /></p>
          <p style={{ fontWeight: 600 }}>选择整书 PDF，自动识别目录并按章切分</p>
          <p style={{ color: '#999' }}>有目录页 → 按目录分章；无目录页 → AI 归纳目录；切分结果可在下方人工修正</p>
        </Upload.Dragger>

        {/* 页码范围选择 */}
        {bookFile && !bookImporting && bookTotal > 0 && (
          <div style={{ marginTop: 16, background: '#f7f7fb', borderRadius: 10, padding: 12 }}>
            <div style={{ marginBottom: 8 }}>
              《{bookFile.name}》共 <b>{bookTotal}</b> 页
              {bookLastHint && (
                <div style={{ color: '#7c5cfc', fontSize: 12, marginTop: 4 }}>{bookLastHint}</div>
              )}
            </div>
            <Space wrap>
              <span>导入第</span>
              <InputNumber min={1} max={bookTotal} value={bookStart}
                onChange={v => setBookStart(Math.max(1, Number(v) || 1))} style={{ width: 80 }} />
              <span>~</span>
              <InputNumber min={1} max={bookTotal} value={bookEnd}
                onChange={v => setBookEnd(Math.min(bookTotal, Math.max(bookStart, Number(v) || bookTotal)))} style={{ width: 80 }} />
              <span>页</span>
              <Button type="primary" icon={<BookOutlined />} onClick={runBookImport}>
                开始导入
              </Button>
            </Space>
          </div>
        )}

        {(bookImporting || bookProgress >= 100) && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={bookProgress} status={bookProgress === 100 ? 'success' : 'active'} />
            <div style={{ color: '#666', marginTop: 8 }}>{bookMsg}</div>
            {bookEntries.length > 0 && (
              <div style={{ marginTop: 12, maxHeight: 180, overflowY: 'auto', fontSize: 13 }}>
                {bookEntries.map((e, i) => (
                  <div key={i} style={{ padding: '3px 0' }}>
                    <Tag color="purple">{i + 1}</Tag> {e.title} <span style={{ color: '#999' }}>· 第 {e.page_number} 页</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 新建分组（部分/卷） */}
      <Modal title="新建分组（部分/卷）" open={groupOpen} onOk={submitGroup} onCancel={() => setGroupOpen(false)} okText="创建" cancelText="取消">
        <Form form={groupForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="title" label="分组标题" rules={[{ required: true, message: '请输入分组标题' }]}>
            <Input placeholder="如：上卷 / 第一部分" />
          </Form.Item>
          <Form.Item name="chapter_ids" label="纳入哪些章节（可选，之后也能用章节行的「移入分组」调整）">
            <Select mode="multiple" allowClear placeholder="选择要放进该分组的章节"
              options={chapters.filter(c => !c.is_group).map(c => ({ value: c.id, label: c.chapter_title || c.title }))}
              optionFilterProp="label" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建章节（空白 / 划页） */}
      <Modal title="新建章节" open={createOpen} onOk={submitCreate} confirmLoading={creating}
        onCancel={() => setCreateOpen(false)} okText="创建" cancelText="取消">
        <Segmented
          block value={createMode} onChange={v => setCreateMode(v as 'blank' | 'slice')}
          options={[{ value: 'blank', label: '空白章节' }, { value: 'slice', label: '划页建章' }]}
          style={{ marginBottom: 16 }}
        />
        <Form form={createForm} layout="vertical">
          <Form.Item name="title" label="章节标题" rules={[{ required: true, message: '请输入章节标题' }]}>
            <Input placeholder="如：第 3 讲 集合论" />
          </Form.Item>
          {createMode === 'slice' && (
            <>
              <Form.Item name="source_document_id" label="来源整书（从哪个整书拆分章节）"
                rules={[{ required: true, message: '请选择来源整书' }]}>
                <Select
                  placeholder="选择已整书导入的章节（引用其整书）"
                  options={chapters.filter((c: any) => c.book_file)
                    .map((c: any) => ({ value: c.id, label: c.chapter_title || c.title }))}
                />
              </Form.Item>
              <Space style={{ width: '100%' }}>
                <Form.Item name="page_start" label={`起始页（1-${srcTotal || '?'}）`}
                  rules={[{ required: true, message: '起始页' }]}>
                  <InputNumber min={1} max={srcTotal || undefined} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="page_end" label="结束页" rules={[{ required: true, message: '结束页' }]}>
                  <InputNumber min={1} max={srcTotal || undefined} style={{ width: '100%' }} />
                </Form.Item>
              </Space>
              <div style={{ color: '#999', fontSize: 12 }}>
                {srcTotal
                  ? `共 ${srcTotal} 页；可从整书任选连续页作为一章`
                  : '先选择来源整书，再指定页码范围'}
              </div>
            </>
          )}
        </Form>
      </Modal>

      {/* 章节分页调节器 */}
      <Modal title="章节分页调节器" open={regOpen} onCancel={() => setRegOpen(false)} width={820}
        footer={[
          <Space key="add">
            {books.length > 1 && (
              <Select size="small" style={{ width: 130 }} value={newBookRef}
                onChange={v => setNewBookRef(v)} placeholder="目标书"
                options={books.map(b => ({ value: b.ref_document_id, label: b.title }))} />
            )}
            <Button icon={<PlusOutlined />} onClick={regAddNew}>新建章节（未覆盖页）</Button>
          </Space>,
          <Button key="cancel" onClick={() => setRegOpen(false)}>取消</Button>,
          <Button key="save" type="primary" onClick={saveReg}>保存并重切</Button>,
        ]}
      >
        <div style={{ marginBottom: 10, color: '#999', fontSize: 13 }}>
          {books.length} 本书 · {regChapters.length} 个章节；相邻章节范围允许重叠（边界页可同时归属两章）
        </div>
        {/* 页带可视化：每本书一条，按各自总页数 */}
        {books.map((b, bi) => {
          const rows = regChapters.filter(r => r.source_document_id === b.ref_document_id)
          if (!rows.length) return null
          const total = b.total_pages || 0
          const color = BOOK_COLORS[bi % BOOK_COLORS.length]
          return (
            <div key={b.ref_document_id} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>
                《{b.title}》共 <b>{total}</b> 页 · {rows.length} 章
              </div>
              <div style={{ display: 'flex', height: 24, borderRadius: 6, overflow: 'hidden', background: '#f0f0f0' }}>
                {rows.map(r => {
                  const w = total ? Math.max(2, ((r.page_end - r.page_start + 1) / total) * 100) : 2
                  return <Tooltip key={r.key} title={`${r.title}：第 ${r.page_start + 1}-${r.page_end + 1} 页`}>
                    <div style={{ width: `${w}%`, background: color, opacity: 0.75, borderRight: '1px solid #fff' }} />
                  </Tooltip>
                })}
              </div>
            </div>
          )
        })}

        <div style={{ maxHeight: 340, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {regChapters.map((r, i) => {
            const next = regChapters[i + 1]
            const shared = !!next && r.source_document_id === next.source_document_id && r.page_end >= next.page_start
            const book = bookByRef(r.source_document_id)
            const total = book?.total_pages || 0
            const max0 = Math.max(0, total - 1)
            const bi = Math.max(0, books.findIndex(b => b.ref_document_id === r.source_document_id))
            return (
              <div key={r.key} className="yq-reg-row" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Tag color="purple" style={{ margin: 0 }}>{i + 1}</Tag>
                {books.length > 1 && (
                  <Tag style={{ margin: 0, border: 'none', background: `${BOOK_COLORS[bi % BOOK_COLORS.length]}22`, color: '#555' }}>
                    {book?.title || '?'}
                  </Tag>
                )}
                <Input style={{ width: 160 }} value={r.title}
                  onChange={e => updateReg(r.key, { title: e.target.value })} />
                <span style={{ color: '#999' }}>第</span>
                <InputNumber min={1} max={total || 1} value={r.page_start + 1}
                  onChange={v => updateReg(r.key, { page_start: Math.min(max0, Math.max(0, (Number(v) || 1) - 1)) })} style={{ width: 70 }} />
                <span style={{ color: '#999' }}>~</span>
                <InputNumber min={1} max={total || 1} value={r.page_end + 1}
                  onChange={v => updateReg(r.key, { page_end: Math.min(max0, Math.max(r.page_start, (Number(v) || 1) - 1)) })} style={{ width: 70 }} />
                <span style={{ color: '#999' }}>页</span>
                {next && r.source_document_id === next.source_document_id && (
                  <Checkbox
                    checked={shared}
                    onChange={e => updateReg(r.key, { page_end: e.target.checked ? next.page_start : next.page_start - 1 })}
                  >
                    第 {next.page_start + 1} 页同时归属下一章
                  </Checkbox>
                )}
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                  {r.source_document_id && (
                    <Button size="small" icon={<EyeOutlined />} onClick={() => setPreview({
                      key: r.key, docId: r.source_document_id!, bookTitle: book?.title || '整书',
                      pageStart: r.page_start, pageEnd: r.page_end,
                    })}>预览</Button>
                  )}
                  <Button size="small" onClick={() => regSplit(r)}>拆分</Button>
                  <Popconfirm title={`删除「${r.title}」？其批注/总结/题目/闪卡将一并清理`} onConfirm={() => regDelete(r)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </span>
              </div>
            )
          })}
        </div>
      </Modal>

      {/* 章节内容预览：整书原文件在章节范围内的实际页面 */}
      <ChapterPreviewModal
        open={!!preview}
        bookFileUrl={preview ? api.documentBookFileUrl(preview.docId) : ''}
        bookTitle={preview?.bookTitle || ''}
        pageStart={preview?.pageStart || 0}
        pageEnd={preview?.pageEnd || 0}
        onRangeChange={(s, e) => { if (preview) updateReg(preview.key, { page_start: s, page_end: e }) }}
        onClose={() => setPreview(null)}
      />

      {/* 语音助手 */}
      <Modal title="🎙 语音助手" open={agentOpen} onCancel={() => setAgentOpen(false)} footer={null} width={560}>
        <VoiceAgentPanel projectId={id} onApplied={load} />
      </Modal>

      {/* 空白章节上传资料 */}
      <Modal title={`上传资料 · ${attachChapter?.chapter_title || attachChapter?.title}`}
        open={!!attachChapter} footer={null} onCancel={() => setAttachChapter(null)}>
        <Form form={attachForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="chapter_title" label="章节标题（可选）">
            <Input placeholder="留空则沿用当前标题" />
          </Form.Item>
        </Form>
        <Upload.Dragger customRequest={attachSave} accept=".pdf,.docx,.md,.markdown,.txt,.pptx"
          showUploadList={false} disabled={attaching}>
          <p style={{ fontSize: 36, margin: 0 }}><FileTextOutlined style={{ color: '#7c5cfc' }} /></p>
          <p style={{ fontWeight: 600 }}>为该空白章节上传资料</p>
          <p style={{ color: '#999' }}>PDF / Word / Markdown / TXT / PPT</p>
        </Upload.Dragger>
      </Modal>
    </div>
  )
}

function ChapterEdit({ c, onSave }: { c: Chapter; onSave: (title: string, chapter_title: string) => void }) {
  const [title, setTitle] = useState(c.title)
  const [chapterTitle, setChapterTitle] = useState(c.chapter_title)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="文档标题" />
      <Input value={chapterTitle} onChange={e => setChapterTitle(e.target.value)} placeholder="章节标题（如：第 2 章）" />
      <Button type="primary" onClick={() => onSave(title, chapterTitle)}>保存</Button>
    </div>
  )
}
