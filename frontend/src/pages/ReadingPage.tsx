import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Select, Button, Space, Switch, Modal, Input, message, Spin, Tag, Tooltip, Segmented, Empty, Drawer,
} from 'antd'
import {
  LeftOutlined, RightOutlined, SoundOutlined, ReadOutlined, BookOutlined, PlayCircleOutlined, PauseCircleOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import ReadingUnit, { cleanText, type Range } from '../components/ReadingUnit'
import NativeFileView from '../components/NativeFileView'
import AnnotationPanel, { type Annotation } from '../components/AnnotationPanel'
import SummaryPanel, { type SummaryItem } from '../components/SummaryPanel'
import PodcastPanel from '../components/PodcastPanel'
import BlankView from '../components/BlankView'
import DrawingOverlay from '../components/DrawingOverlay'
import { useTTSPlay } from '../hooks/useTTSPlay'

interface Unit {
  index: number
  unit_type: string
  title: string
  text: string
}

export default function ReadingPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [units, setUnits] = useState<Unit[]>([])
  const [cur, setCur] = useState(0)
  const [loadingContent, setLoadingContent] = useState(false)
  const [loadErr, setLoadErr] = useState('')
  const [blankEnabled, setBlankEnabled] = useState(false)  // 按书配置：是否开启「关键词挖空」

  // 批注
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [pendingAnn, setPendingAnn] = useState<{ start: number; end: number; text: string } | null>(null)
  const [annDraft, setAnnDraft] = useState('')
  const [jump, setJump] = useState<{ unit: number; start: number; end: number } | null>(null)

  // 总结（overall/page/story/concept，后两者为章节级）
  const [overallOn, setOverallOn] = useState(false)
  const [pageOn, setPageOn] = useState(false)
  const [summaries, setSummaries] = useState<Record<string, SummaryItem>>({})
  const [genOverall, setGenOverall] = useState(false)
  const [genPage, setGenPage] = useState(false)
  const [genStory, setGenStory] = useState(false)
  const [genConcept, setGenConcept] = useState(false)
  const generatingRef = useRef<Set<string>>(new Set())

  // 百宝箱（可折叠悬浮面板）
  const [baibaoOpen, setBaibaoOpen] = useState(false)
  // 批注/总结/AI播客：顶部细导航栏 + 右侧抽屉（原常驻右侧栏改版）
  const [sidebarTab, setSidebarTab] = useState('ann')
  const [panelOpen, setPanelOpen] = useState(false)

  // 阅读视图：原文件（原生渲染） / 文本（可批注） / 挖空（关键词背诵）
  const [viewMode, setViewMode] = useState<'native' | 'text' | 'blank'>('native')
  // 自由绘制模式（由百宝箱「绘制工具」控制）：PDF 在原文件视图，非 PDF 在文本视图
  const [drawing, setDrawing] = useState(false)
  // 听书：TTS 朗读本页
  const tts = useTTSPlay()

  const curUnit = units[cur]
  const currentContentType = docs.find((d: any) => d.id === docId)?.content_type || 'pdf'
  // PDF 全页浏览：原文件视图 + PDF 时铺满阅读区、隐藏侧栏
  const isPdfFull = viewMode === 'native' && currentContentType === 'pdf'
  const summaryKey = (scope: string, unit?: number) => (scope === 'page' ? `page:${unit}` : scope)

  // 绘制仅在对应视图生效：PDF→原文件，非 PDF→文本；否则自动退出
  useEffect(() => {
    const ok = (currentContentType === 'pdf' && viewMode === 'native')
      || (currentContentType !== 'pdf' && viewMode === 'text')
    if (!ok) setDrawing(false)
  }, [viewMode, currentContentType])

  // ---------- 初始化 ----------
  useEffect(() => { loadDocs() }, [])

  const loadDocs = async () => {
    const d = await api.listDocuments()
    setDocs(d)
    const fromUrl = params.get('doc')
    if (fromUrl && d.some((x: any) => x.id === fromUrl)) setDocId(fromUrl)
    else if (d.length) setDocId(d[0].id)
  }

  useEffect(() => { if (docId) loadDocData() }, [docId])

  const loadDocData = async () => {
    setLoadingContent(true)
    setLoadErr('')
    setCur(0); setJump(null)
    try {
      const [content, anns, sums] = await Promise.all([
        api.getReadingContent(docId),
        api.listAnnotations(docId),
        api.listSummaries(docId),
      ])
      setUnits(content.units)
      setBlankEnabled(!!content.blank_enabled)
      setAnnotations(anns)
      const map: Record<string, SummaryItem> = {}
      for (const s of sums) map[summaryKey(s.scope, s.unit_index ?? undefined)] = s
      setSummaries(map)
    } catch (e: any) {
      setLoadErr(e?.response?.data?.detail || e?.message || '加载内容失败，请稍后重试')
    } finally { setLoadingContent(false) }
  }

  // ---------- 总结生成 ----------
  const ensureSummary = useCallback(async (scope: 'overall' | 'page' | 'story' | 'concept') => {
    if (!docId) return
    const key = summaryKey(scope, cur)
    if (summaries[key]?.status === 'done' || summaries[key]?.status === 'generating') return
    if (generatingRef.current.has(key)) return
    generatingRef.current.add(key)
    if (scope === 'overall') setGenOverall(true)
    else if (scope === 'page') setGenPage(true)
    else if (scope === 'story') setGenStory(true)
    else setGenConcept(true)
    try {
      const s = await api.generateSummary(docId, scope, scope === 'page' ? cur : undefined)
      setSummaries(m => ({ ...m, [key]: s }))
    } finally {
      generatingRef.current.delete(key)
      if (scope === 'overall') setGenOverall(false)
      else if (scope === 'page') setGenPage(false)
      else if (scope === 'story') setGenStory(false)
      else setGenConcept(false)
    }
  }, [docId, cur, summaries])

  // 页级总结跟随当前页
  useEffect(() => { if (pageOn && curUnit) ensureSummary('page') }, [cur, pageOn, curUnit])

  const toggleOverall = (on: boolean) => {
    setOverallOn(on)
    if (on) { setSidebarTab('sum'); setPanelOpen(true); ensureSummary('overall') }  // 弹出「总结」抽屉看进度
  }
  const togglePage = (on: boolean) => {
    setPageOn(on)
    if (on) { setSidebarTab('sum'); setPanelOpen(true); ensureSummary('page') }
  }

  const overallItem = summaries['overall'] || null
  const pageItem = summaries[`page:${cur}`] || null
  const storyItem = summaries['story'] || null
  const conceptItem = summaries['concept'] || null

  // ---------- 百宝箱入口 ----------
  // 打开面板：顶部导航栏页签 → 设当前页签 + 弹出抽屉；已打开同一页签则收起
  const openPanel = (tab: string) => {
    if (panelOpen && sidebarTab === tab) { setPanelOpen(false); return }
    if (isPdfFull) setViewMode('text')  // 全页浏览时切回文本视图，避免抽屉叠在 PDF 上
    setSidebarTab(tab)
    setPanelOpen(true)
  }
  const onGenerateStory = async () => {
    setSidebarTab('sum')
    setPanelOpen(true)
    await ensureSummary('story')
  }
  const onGenerateConcept = async () => {
    setSidebarTab('sum')
    setPanelOpen(true)
    await ensureSummary('concept')
  }
  const onOpenPodcast = () => openPanel('podcast')

  // ---------- 批注 ----------
  const onSelectText = (start: number, end: number, text: string) => {
    setPendingAnn({ start, end, text })
    setAnnDraft('')
  }

  const saveAnnotation = async () => {
    if (!docId || !pendingAnn || !curUnit) return
    await api.createAnnotation(docId, {
      unit_type: curUnit.unit_type,
      unit_index: curUnit.index,
      start_offset: pendingAnn.start,
      end_offset: pendingAnn.end,
      selected_text: pendingAnn.text,
      content: annDraft,
    })
    setPendingAnn(null)
    message.success('批注已添加')
    const anns = await api.listAnnotations(docId)
    setAnnotations(anns)
  }

  const editAnnotation = async (ann: Annotation, content: string) => {
    await api.updateAnnotation(ann.id, content)
    message.success('已保存')
    setAnnotations(anns => anns.map(a => a.id === ann.id ? { ...a, content } : a))
  }

  const deleteAnnotation = async (id: string) => {
    await api.deleteAnnotation(id)
    message.success('已删除')
    setAnnotations(anns => anns.filter(a => a.id !== id))
  }

  const jumpToAnnotation = (ann: Annotation) => {
    setCur(ann.unit_index)
    setJump({ unit: ann.unit_index, start: ann.start_offset, end: ann.end_offset })
  }

  // 渲染用的清洗文本（批注偏移一致）
  const displayText = useMemo(() => cleanText(curUnit?.text || ''), [curUnit])

  // ---------- 渲染 ----------
  const highlightRanges: Range[] = []
  // 批注跳转高亮
  if (jump && jump.unit === cur) highlightRanges.push({ start: jump.start, end: jump.end })

  return (
    <div style={{ maxWidth: isPdfFull ? '100%' : 1100, margin: '0 auto' }}>
      {/* 顶部栏 */}
      <div className={isPdfFull ? 'yq-topbar-full' : 'page-card'} style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        {(() => {
          const currentDoc = docs.find((d: any) => d.id === docId)
          return currentDoc?.project_id ? (
            <Button type="text" icon={<LeftOutlined />} onClick={() => navigate(`/project/${currentDoc.project_id}`)}>
              返回项目
            </Button>
          ) : (
            <Button type="text" icon={<LeftOutlined />} onClick={() => navigate('/bookshelf')}>
              返回书架
            </Button>
          )
        })()}
        <BookOutlined style={{ color: '#7c5cfc', fontSize: 18 }} />
        <Select
          style={{ width: 220 }} value={docId || undefined} placeholder="选择资料"
          onChange={setDocId} options={docs.map((d: any) => ({ value: d.id, label: d.title }))}
        />
        <Button icon={<LeftOutlined />} disabled={cur <= 0} onClick={() => setCur(c => c - 1)} />
        <Tag color="purple">{units.length ? `${cur + 1} / ${units.length}` : '-'}</Tag>
        <Button icon={<RightOutlined />} disabled={cur >= units.length - 1} onClick={() => setCur(c => c + 1)} />

        <div style={{ flex: 1 }} />

        <Tooltip title="整体总结开关">
          <Space size={4}><ReadOutlined /><Switch checked={overallOn} onChange={toggleOverall} size="small" /><span style={{ fontSize: 12 }}>整体总结</span></Space>
        </Tooltip>
        <Tooltip title="每页总结开关，翻页自动切换">
          <Space size={4}><ReadOutlined /><Switch checked={pageOn} onChange={togglePage} size="small" /><span style={{ fontSize: 12 }}>每页总结</span></Space>
        </Tooltip>
        <Tooltip title="AI 播客：按当前章节生成双主播对谈音频">
          <Button type="primary" ghost icon={<SoundOutlined />} onClick={onOpenPodcast}>
            AI 播客
          </Button>
        </Tooltip>
        <Tooltip title="TTS 朗读本页（听书）">
          <Button icon={tts.playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />} loading={tts.busy}
            onClick={() => {
              if (tts.playing) { tts.stop(); return }
              if (curUnit?.text) tts.play(curUnit.text).catch(() => {})
            }}>
            {tts.playing ? '停止朗读' : '朗读本页'}
          </Button>
        </Tooltip>
        <Segmented
          value={viewMode}
          onChange={v => setViewMode(v as 'native' | 'text' | 'blank')}
          options={[
            { value: 'native', label: '原文件' },
            { value: 'text', label: '文本' },
            ...(blankEnabled ? [{ value: 'blank' as const, label: '挖空' }] : []),
          ]}
          size="small"
        />
      </div>

      {/* 批注/总结/AI播客：顶部细导航栏（sticky，正文滚动时保持不动，不再占用右侧大块空间） */}
      {!isPdfFull && docId && (
        <div className="yq-read-navbar">
          <span style={{ fontSize: 12, color: '#8c6ff0', background: '#f4f0ff', padding: '1px 8px', borderRadius: 10, marginRight: 4 }}>
            AI 工具
          </span>
          {[
            { key: 'ann', icon: <ReadOutlined />, label: `批注 (${annotations.length})` },
            { key: 'sum', icon: <FileTextOutlined />, label: '总结' },
            { key: 'podcast', icon: <SoundOutlined />, label: 'AI 播客' },
          ].map(t => (
            <Button key={t.key} type={panelOpen && sidebarTab === t.key ? 'primary' : 'text'} size="small"
              icon={t.icon} onClick={() => openPanel(t.key)}>
              {t.label}
            </Button>
          ))}
          <span style={{ fontSize: 11, color: '#bbb', marginLeft: 8 }}>点按页签在右侧展开，正文不再被挤占</span>
        </div>
      )}

      <div style={isPdfFull
        ? { display: 'flex', gap: 0, alignItems: 'stretch', minHeight: 'calc(100vh - 180px)' }
        : { display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 阅读区：PDF 全页浏览时全宽无卡片 */}
        <div className={isPdfFull ? 'yq-reading-full' : 'page-card'} style={{ flex: 1, minWidth: 0 }}>
          {loadingContent ? <div style={{ textAlign: 'center', padding: 60, color: '#999' }}><Spin /><div style={{ marginTop: 12 }}>正在加载内容…</div></div> : loadErr ? (
            <div style={{ textAlign: 'center', padding: 60 }}>
              <h3 style={{ color: '#ff4d4f' }}>加载失败</h3>
              <p style={{ color: '#999' }}>{loadErr}</p>
              <Button onClick={loadDocData}>重试</Button>
            </div>
          ) : !curUnit ? (
            <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
              先在「资料库」上传一份文档
              <div style={{ marginTop: 12 }}>
                <Button onClick={() => navigate('/bookshelf')}>去上传资料</Button>
              </div>
            </div>
          ) : viewMode === 'native' ? (
            <NativeFileView docId={docId} contentType={currentContentType} full={isPdfFull}
              drawing={drawing} onDrawingChange={setDrawing} />
          ) : viewMode === 'blank' ? (
            <BlankView docId={docId} unitIndex={cur} />
          ) : (
            <>
              <h3 style={{ marginTop: 0 }}>{curUnit.title}</h3>
              <div style={{ position: 'relative' }}>
                <ReadingUnit
                  text={displayText}
                  highlightRanges={highlightRanges}
                  onSelect={onSelectText}
                />
                {/* 非 PDF（PPT/MD/DOCX/TXT）：在文本视图上按阅读单元叠加绘制层 */}
                {currentContentType !== 'pdf' && (
                  <DrawingOverlay docId={docId} unitIndex={cur} enabled={drawing}
                    onClose={() => setDrawing(false)} />
                )}
              </div>
            </>
          )}
        </div>

      </div>

      {/* 批注/总结/AI播客 内容抽屉（原右侧栏按需弹出，正文不再被挤占） */}
      <Drawer
        title={sidebarTab === 'ann' ? `批注 (${annotations.length})`
          : sidebarTab === 'sum' ? '总结' : 'AI 播客'}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        width={Math.min(400, window.innerWidth * 0.92)}
      >
        {sidebarTab === 'ann' && (
          <AnnotationPanel
            annotations={annotations.filter(a => a.document_id === docId)}
            unitTitleOf={idx => units[idx]?.title || `第 ${idx + 1} 节`}
            onJump={jumpToAnnotation} onEdit={editAnnotation} onDelete={deleteAnnotation}
          />
        )}
        {sidebarTab === 'sum' && (
          <SummaryPanel
            overall={overallItem} page={pageItem} story={storyItem} concept={conceptItem}
            onGenerateOverall={() => ensureSummary('overall')}
            onGeneratePage={() => ensureSummary('page')}
            onGenerateStory={onGenerateStory}
            onGenerateConcept={onGenerateConcept}
            onOpenPodcast={onOpenPodcast}
            generatingOverall={genOverall} generatingPage={genPage}
            generatingStory={genStory} generatingConcept={genConcept}
            unitTitle={curUnit?.title || ''}
          />
        )}
        {sidebarTab === 'podcast' && (curUnit ? (
          <PodcastPanel docId={docId} unitIndex={curUnit.index} unitTitle={curUnit.title} />
        ) : (
          <Empty description="当前没有可生成播客的内容" />
        ))}
      </Drawer>

      {/* 百宝箱（可折叠悬浮面板） */}
      <div className={`yq-baibao ${baibaoOpen ? 'open' : ''}`}>
        {!baibaoOpen ? (
          <Button
            type="primary" shape="circle" size="large" className="yq-baibao-fab"
            onClick={() => setBaibaoOpen(true)} title="百宝箱"
          >
            🧰
          </Button>
        ) : (
          <div className="yq-baibao-panel">
            <div className="yq-baibao-header">
              <b>🧰 百宝箱</b>
              <span className="yq-baibao-close" onClick={() => setBaibaoOpen(false)} title="收起">✕</span>
            </div>
            <div className="yq-baibao-grid">
              <div className="yq-baibao-tile" onClick={() => {
                if (viewMode !== 'text') { setViewMode('text'); message.info('批注请在「文本」视图进行') }
                openPanel('ann')
              }}><span className="tile-icon">💬</span><span className="tile-label">批注</span></div>
              <div className="yq-baibao-tile" onClick={() => {
                const target = currentContentType === 'pdf' ? 'native' : 'text'
                if (viewMode !== target) setViewMode(target)
                setDrawing(d => !d)
              }}><span className="tile-icon">✏️</span><span className="tile-label">绘制</span></div>
              <div className="yq-baibao-tile" onClick={onOpenPodcast}><span className="tile-icon">🎙️</span><span className="tile-label">AI 播客</span></div>
              <div className="yq-baibao-tile" onClick={onGenerateStory}><span className="tile-icon">📖</span><span className="tile-label">章节总结</span></div>
              <div className="yq-baibao-tile" onClick={onGenerateConcept}><span className="tile-icon">🧠</span><span className="tile-label">概念总结</span></div>
              <div className="yq-baibao-tile" onClick={() => navigate(`/quiz?doc=${docId}`)}><span className="tile-icon">✅</span><span className="tile-label">练习题</span></div>
              <div className="yq-baibao-tile" onClick={() => navigate(`/flashcards?doc=${docId}`)}><span className="tile-icon">🃏</span><span className="tile-label">闪卡</span></div>
              <div className="yq-baibao-tile" onClick={() => navigate(`/knowledge?doc=${docId}`)}><span className="tile-icon">🌳</span><span className="tile-label">知识树</span></div>
            </div>
          </div>
        )}
      </div>

      {/* 添加批注弹窗 */}
      <Modal
        title="添加批注"
        open={!!pendingAnn}
        onOk={saveAnnotation}
        onCancel={() => setPendingAnn(null)}
        okText="保存" cancelText="取消"
      >
        <div style={{ fontSize: 12, color: '#8c6ff0', background: '#f4f0ff', padding: '6px 10px', borderRadius: 6, marginBottom: 10 }}>
          「{pendingAnn?.text}」
        </div>
        <Input.TextArea rows={4} value={annDraft} onChange={e => setAnnDraft(e.target.value)}
          placeholder="写下你的想法、疑问或笔记…" />
      </Modal>
    </div>
  )
}
