import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Select, Button, Space, Switch, Tabs, Modal, Input, message, Spin, Tag, Tooltip, Segmented,
} from 'antd'
import {
  LeftOutlined, RightOutlined, SoundOutlined, ReadOutlined, BookOutlined,
  FileTextOutlined, EditFilled, ThunderboltFilled,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import ReadingUnit, { cleanText, type Range } from '../components/ReadingUnit'
import NativeFileView from '../components/NativeFileView'
import AnnotationPanel, { type Annotation } from '../components/AnnotationPanel'
import SummaryPanel, { type SummaryItem } from '../components/SummaryPanel'
import TTSControls from '../components/TTSControls'
import { useTTS, splitSentences, type TTSSource } from '../hooks/useTTS'

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

  // 朗读
  const [ttsOn, setTtsOn] = useState(false)
  const [ttsSource, setTtsSource] = useState<TTSSource>('original')
  const tts = useTTS({
    onSentenceChange: (idx) => {
      // 高亮当前朗读句（仅原文模式有意义）
      if (ttsSourceRef.current === 'original') ttsSentenceRef.current = idx
    },
  })
  const ttsSourceRef = useRef<TTSSource>('original')
  ttsSourceRef.current = ttsSource
  const ttsSentenceRef = useRef(-1)

  // 百宝箱（可折叠悬浮面板）
  const [baibaoOpen, setBaibaoOpen] = useState(false)
  const [sidebarTab, setSidebarTab] = useState('ann')

  // 阅读视图：原文件（原生渲染） / 文本（可批注）
  const [viewMode, setViewMode] = useState<'native' | 'text'>('native')

  const curUnit = units[cur]
  const currentContentType = docs.find((d: any) => d.id === docId)?.content_type || 'pdf'
  // PDF 全页浏览：原文件视图 + PDF 时铺满阅读区、隐藏侧栏
  const isPdfFull = viewMode === 'native' && currentContentType === 'pdf'
  const summaryKey = (scope: string, unit?: number) => (scope === 'page' ? `page:${unit}` : scope)

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
    setCur(0); setJump(null); tts.stop(); ttsSentenceRef.current = -1
    try {
      const [content, anns, sums] = await Promise.all([
        api.getReadingContent(docId),
        api.listAnnotations(docId),
        api.listSummaries(docId),
      ])
      setUnits(content.units)
      setAnnotations(anns)
      const map: Record<string, SummaryItem> = {}
      for (const s of sums) map[summaryKey(s.scope, s.unit_index ?? undefined)] = s
      setSummaries(map)
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
    if (on) ensureSummary('overall')
  }
  const togglePage = (on: boolean) => {
    setPageOn(on)
    if (on) ensureSummary('page')
  }

  const overallItem = summaries['overall'] || null
  const pageItem = summaries[`page:${cur}`] || null
  const storyItem = summaries['story'] || null
  const conceptItem = summaries['concept'] || null

  // ---------- 百宝箱入口 ----------
  const onGenerateStory = async () => {
    setSidebarTab('sum')
    await ensureSummary('story')
  }
  const onGenerateConcept = async () => {
    setSidebarTab('sum')
    await ensureSummary('concept')
  }
  const onListenStory = async () => {
    const s = summaries['story']
    if (s?.status !== 'done') { message.info('先生成听书式总结'); return }
    setTtsSource('story')
    await tts.play(s.content, 0)
  }

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

  // 渲染与朗读共用清洗文本，保证句子高亮偏移一致
  const displayText = useMemo(() => cleanText(curUnit?.text || ''), [curUnit])

  const playTTS = async () => {
    if (!curUnit) return
    if (tts.state === 'paused') { tts.resume(); return }
    if (tts.state === 'playing') { tts.pause(); return }
    let text = displayText
    if (ttsSource === 'summary') {
      const s = summaries[`page:${cur}`]
      if (s?.status === 'done') text = s.content
      else if (!s) { message.info('先生成本页总结，或先朗读原文'); return }
      else { message.info('总结还在生成中或生成失败'); return }
    } else if (ttsSource === 'story') {
      const s = summaries['story']
      if (s?.status === 'done') text = s.content
      else { message.info('先生成「章节总结 · 听书式」，或先朗读原文'); return }
    }
    await tts.play(text, 0)
  }

  // 翻页联动：朗读中自动切到新页内容
  useEffect(() => {
    if (ttsOn && curUnit && (tts.state === 'playing' || tts.state === 'paused') && ttsSource === 'original') {
      if (displayText) { tts.stop(); ttsSentenceRef.current = -1; tts.play(displayText, 0) }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cur, curUnit?.index])

  useEffect(() => () => tts.stop(), [])

  // ---------- 渲染 ----------
  const highlightRanges: Range[] = []
  // 批注跳转高亮
  if (jump && jump.unit === cur) highlightRanges.push({ start: jump.start, end: jump.end })
  // 朗读当前句高亮（原文模式）
  const speakRanges: Range[] = []
  if (ttsSource === 'original' && ttsSentenceRef.current >= 0 && tts.total > 0) {
    const sent = tts.sentences[ttsSentenceRef.current]
    if (sent) speakRanges.push({ start: sent.start, end: sent.end })
  }

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
        <Tooltip title="听书朗读">
          <Button
            type={ttsOn ? 'primary' : 'default'} icon={<SoundOutlined />}
            onClick={() => setTtsOn(o => !o)}
          >
            朗读
          </Button>
        </Tooltip>
        <Segmented
          value={viewMode}
          onChange={v => setViewMode(v as 'native' | 'text')}
          options={[
            { value: 'native', label: '原文件' },
            { value: 'text', label: '文本' },
          ]}
          size="small"
        />
      </div>

      <div style={isPdfFull
        ? { display: 'flex', gap: 0, alignItems: 'stretch', minHeight: 'calc(100vh - 180px)' }
        : { display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 阅读区：PDF 全页浏览时全宽无卡片 */}
        <div className={isPdfFull ? 'yq-reading-full' : 'page-card'} style={{ flex: 1, minWidth: 0 }}>
          {loadingContent ? <Spin style={{ display: 'block', margin: 60 }} /> : !curUnit ? (
            <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>先在「资料库」上传一份文档</div>
          ) : viewMode === 'native' ? (
            <NativeFileView docId={docId} contentType={currentContentType} full={isPdfFull} />
          ) : (
            <>
              <h3 style={{ marginTop: 0 }}>{curUnit.title}</h3>
              <ReadingUnit
                text={displayText}
                highlightRanges={highlightRanges}
                speakRanges={speakRanges}
                onSelect={onSelectText}
              />
            </>
          )}
        </div>

        {/* 侧栏：PDF 全页浏览时隐藏 */}
        {!isPdfFull && docId && (
          <div className="page-card" style={{ width: 340, flexShrink: 0 }}>
            <Tabs
              size="small"
              activeKey={sidebarTab}
              onChange={setSidebarTab}
              items={[
                {
                  key: 'ann', label: `批注 (${annotations.length})`,
                  children: (
                    <AnnotationPanel
                      annotations={annotations.filter(a => a.document_id === docId)}
                      unitTitleOf={idx => units[idx]?.title || `第 ${idx + 1} 节`}
                      onJump={jumpToAnnotation} onEdit={editAnnotation} onDelete={deleteAnnotation}
                    />
                  ),
                },
                {
                  key: 'sum', label: '总结',
                  children: (
                    <SummaryPanel
                      overall={overallItem} page={pageItem} story={storyItem} concept={conceptItem}
                      onGenerateOverall={() => ensureSummary('overall')}
                      onGeneratePage={() => ensureSummary('page')}
                      onGenerateStory={onGenerateStory}
                      onGenerateConcept={onGenerateConcept}
                      onListenStory={onListenStory}
                      generatingOverall={genOverall} generatingPage={genPage}
                      generatingStory={genStory} generatingConcept={genConcept}
                      unitTitle={curUnit?.title || ''}
                    />
                  ),
                },
              ]}
            />
          </div>
        )}
      </div>

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
              <Button size="small" type="text" onClick={() => setBaibaoOpen(false)}>收起 ✕</Button>
            </div>
            <div className="yq-baibao-entries">
              <Button icon={<BookOutlined />} onClick={() => {
                if (viewMode !== 'text') { setViewMode('text'); message.info('批注请在「文本」视图进行') }
                setSidebarTab('ann')
              }}>批注工具</Button>
              <Button icon={<SoundOutlined />} onClick={onGenerateStory}>章节总结 · 听书式</Button>
              <Button icon={<FileTextOutlined />} onClick={onGenerateConcept}>概念总结</Button>
              <Button icon={<EditFilled />} onClick={() => navigate(`/quiz?doc=${docId}`)}>练习题</Button>
              <Button icon={<ThunderboltFilled />} onClick={() => navigate(`/flashcards?doc=${docId}`)}>闪卡</Button>
            </div>
          </div>
        )}
      </div>

      {/* 朗读控制条 */}
      {ttsOn && curUnit && (
        <TTSControls
          state={tts.state} currentIndex={tts.currentIndex} total={tts.total}
          rate={tts.rate} source={ttsSource}
          disabled={!curUnit}
          onSourceChange={setTtsSource}
          onPlayPause={playTTS} onStop={tts.stop} onPrev={tts.prev} onNext={tts.next}
          onRateChange={tts.setRate}
        />
      )}

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
