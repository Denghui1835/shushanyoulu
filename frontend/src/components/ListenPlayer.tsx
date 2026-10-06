import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Slider, Space, Spin, Tag, Tooltip, Alert, Progress } from 'antd'
import {
  LeftOutlined, RightOutlined, PlayCircleOutlined, PauseCircleOutlined,
  ReloadOutlined, ReadOutlined, StepBackwardOutlined, StepForwardOutlined,
  LoadingOutlined, CheckCircleFilled, ExclamationCircleFilled,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, streamSSEGet } from '../api'

export interface ListenEpisode {
  id: string
  document_id: string
  project_id?: string
  title: string
  seq: number
  span_start?: number
  span_end?: number | null
  status: string
  ready: boolean
  duration: number
  sentence_count: number
  position_ms: number
  finished: boolean
  error?: string
  failed_segments?: number
  audio_url?: string
}

interface Sentence { text: string; start: number | null; end: number | null }

interface Props {
  /** 播放顺序：整本书的讲按章序串成一条队列，所以能跨章连播 */
  queue: ListenEpisode[]
  index: number
  onIndexChange: (i: number) => void
  /** 某一讲生成完成后回传，让上层刷新列表上的状态 */
  onEpisodeReady?: (id: string, patch: Partial<ListenEpisode>) => void
  voice?: string
  speed?: number
  /** 每讲显示所属章名（连播跨章时看得出来） */
  subtitleOf?: (ep: ListenEpisode) => string
  /** 当前句所在页变化时回调（「去阅读页」用） */
  onPageChange?: (page: number | null) => void
}

const SAVE_INTERVAL_MS = 10000

/**
 * 听读播放器：原文逐句高亮 + 点句跳转 + 连播 + 断点续听。
 *
 * 为什么不用 `<audio controls>`：原生控件给不了「听是主线、读跟着走」——
 * 高亮、点句跳转、跨章连播、断点续听都要自己管。原生 `<audio>` 只留作出声的引擎。
 */
export default function ListenPlayer({
  queue, index, onIndexChange, onEpisodeReady, voice, speed, subtitleOf, onPageChange,
}: Props) {
  const navigate = useNavigate()
  const ep = queue[index]

  const [sentences, setSentences] = useState<Sentence[]>([])
  const [units, setUnits] = useState<number[]>([])
  const [audioUrl, setAudioUrl] = useState('')
  const [duration, setDuration] = useState(0)
  const [curTime, setCurTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(0)
  const [err, setErr] = useState('')
  const [gen, setGen] = useState<{ done: number; total: number } | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const lastSaveRef = useRef(0)
  const resumeAtRef = useRef(0)
  // 记录当前这一讲，供卸载/切讲时把进度写回去
  const curRef = useRef<{ id: string; pos: number }>({ id: '', pos: 0 })
  curRef.current = { id: ep?.id || '', pos: curTime }

  const saveProgress = useCallback((episodeId: string, pos: number, finished = false) => {
    if (!episodeId) return
    api.listenSaveProgress(episodeId, { position_ms: Math.round(pos * 1000), finished })
      .catch(() => { /* 进度回写失败不值得打扰用户 */ })
  }, [])

  // ---------- 换讲：载入详情；没生成就先生成 ----------
  useEffect(() => {
    if (!ep) return
    let alive = true
    const ac = new AbortController()

    setLoading(true); setErr(''); setFailed(0)
    setSentences([]); setUnits([]); setAudioUrl(''); setCurTime(0); setDuration(0)
    setPlaying(false); setGen(null)
    onPageChange?.(null)

    ;(async () => {
      try {
        let detail = await api.listenEpisodeDetail(ep.id)
        if (!alive) return

        // 还没生成 → 起任务 + 追进度
        if (!detail.ready) {
          setGen({ done: detail.progress_done || 0, total: detail.progress_total || 0 })
          await api.listenEpisodeGenerate(ep.id)
          for await (const evt of streamSSEGet(api.listenEpisodeEventsUrl(ep.id), ac.signal)) {
            if (!alive) return
            if (evt.stage === 'progress') {
              setGen({ done: evt.done || 0, total: evt.total || 0 })
            } else if (evt.stage === 'error' || evt.stage === 'timeout') {
              setErr(evt.error || '生成失败')
              onEpisodeReady?.(ep.id, { status: 'error', error: evt.error })
              break
            } else if (evt.stage === 'done') {
              detail = await api.listenEpisodeDetail(ep.id)
              break
            }
          }
          if (!alive) return
        }

        setGen(null)
        if (!detail.ready) {
          if (!detail.error) setErr('这一讲还没生成好')
          setLoading(false)
          return
        }

        setSentences(detail.sentences || [])
        setUnits(detail.sentence_units || [])
        setDuration(detail.duration || 0)
        setFailed(detail.failed_segments || 0)
        setErr(detail.error || '')
        setAudioUrl(api.listenEpisodeAudioUrl(ep.id))
        // 断点续听：听完的从头放，没听完的接着放（最后 10 秒算听完了）
        const pos = (detail.position_ms || 0) / 1000
        resumeAtRef.current = (pos > 5 && pos < (detail.duration || 0) - 10) ? pos : 0
        onEpisodeReady?.(ep.id, {
          ready: true, status: 'done', duration: detail.duration || 0,
          sentence_count: (detail.sentences || []).length,
          failed_segments: detail.failed_segments || 0,
        })
        setLoading(false)
      } catch (e: any) {
        if (!alive) return
        setLoading(false)
        setGen(null)
        setErr(e?.response?.data?.detail || e?.message || '加载失败')
      }
    })()

    return () => {
      alive = false
      ac.abort()
      // 离开这一讲：把进度写回，下次接着听
      const { id, pos } = curRef.current
      if (id === ep.id && pos > 0) saveProgress(id, pos)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep?.id])

  // ---------- 当前句：二分查找（只在有时间的句子上找） ----------
  const timedIdx = useMemo(
    () => sentences.reduce<number[]>((a, s, i) => (s.start !== null ? (a.push(i), a) : a), []),
    [sentences])

  const activeIdx = useMemo(() => {
    if (!timedIdx.length) return -1
    let lo = 0, hi = timedIdx.length - 1, ans = -1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      const s = sentences[timedIdx[mid]]
      if ((s.start as number) <= curTime) { ans = timedIdx[mid]; lo = mid + 1 } else { hi = mid - 1 }
    }
    if (ans >= 0) {
      const s = sentences[ans]
      // 过了这句的尾巴还没进下一句（段间停顿）就不亮，免得高亮一直挂在上一句
      if (s.end !== null && curTime > (s.end as number) + 0.4) return -1
    }
    return ans
  }, [sentences, timedIdx, curTime])

  useEffect(() => {
    onPageChange?.(activeIdx >= 0 ? (units[activeIdx] ?? null) : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx])

  useEffect(() => {
    if (activeIdx < 0 || !autoScrollRef.current || !playing) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-si="${activeIdx}"]`)
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [activeIdx, playing])

  // ---------- 音频事件 ----------
  const onTimeUpdate = (t: number) => {
    setCurTime(t)
    if (Date.now() - lastSaveRef.current > SAVE_INTERVAL_MS) {
      lastSaveRef.current = Date.now()
      saveProgress(ep?.id || '', t)
    }
  }

  const seekTo = (s: Sentence) => {
    if (s.start === null || !audioRef.current) return
    autoScrollRef.current = false
    audioRef.current.currentTime = s.start
    setCurTime(s.start)
    audioRef.current.play().catch(() => {})
    setTimeout(() => { autoScrollRef.current = true }, 900)
  }

  const goto = (delta: number, autoplay = true) => {
    const next = index + delta
    if (next < 0 || next >= queue.length) return
    const { id, pos } = curRef.current
    if (id && pos > 0) saveProgress(id, pos)
    onIndexChange(next)
    if (autoplay) setTimeout(() => audioRef.current?.play().catch(() => {}), 200)
  }

  const jumpTo = (sec: number) => {
    if (!audioRef.current) return
    audioRef.current.currentTime = Math.max(0, Math.min(sec, duration || sec))
    setCurTime(audioRef.current.currentTime)
  }

  if (!ep) return null

  const pending = loading || !!gen
  const genPct = gen?.total ? Math.round((gen.done / gen.total) * 100) : 0
  const curPage = activeIdx >= 0 ? units[activeIdx] : null

  return (
    <div className="yq-section" style={{ flex: 1, minWidth: 0 }}>
      {/* 头部：切讲 / 播放 / 进度 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
        <Tooltip title="上一讲">
          <Button icon={<LeftOutlined />} disabled={index <= 0} onClick={() => goto(-1)} />
        </Tooltip>
        <Button
          type="primary" shape="circle" size="large"
          icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          onClick={() => {
            const a = audioRef.current
            if (!a || !audioUrl) return
            playing ? a.pause() : a.play().catch(() => {})
          }}
          disabled={pending || !audioUrl}
        />
        <Tooltip title="下一讲">
          <Button icon={<RightOutlined />} disabled={index >= queue.length - 1} onClick={() => goto(1)} />
        </Tooltip>
        <Tooltip title="后退 15 秒"><Button icon={<StepBackwardOutlined />} onClick={() => jumpTo(curTime - 15)} disabled={!audioUrl} /></Tooltip>
        <Tooltip title="前进 30 秒"><Button icon={<StepForwardOutlined />} onClick={() => jumpTo(curTime + 30)} disabled={!audioUrl} /></Tooltip>
        <span style={{ color: '#666', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
          {fmt(curTime)} / {fmt(duration || 0)}
        </span>
        <div style={{ flex: 1 }} />
        <Button
          size="small" type="link" icon={<ReadOutlined />} disabled={!ep.document_id}
          onClick={() => navigate(`/reading?doc=${ep.document_id}${curPage !== null ? `&unit=${curPage}` : ''}`)}
        >去阅读页{curPage !== null ? `（第 ${curPage + 1} 页）` : ''}</Button>
      </div>

      <Slider
        min={0} max={Math.max(duration, 1)} step={0.1} value={curTime}
        tooltip={{ formatter: v => fmt(v || 0) }}
        onChange={v => { if (audioRef.current) { audioRef.current.currentTime = v; setCurTime(v) } }}
        disabled={!audioUrl}
      />

      <div style={{ fontSize: 13, color: '#999', marginBottom: 8, minHeight: 20 }}>
        <span style={{ color: '#7c5cfc' }}>{`第 ${index + 1} / ${queue.length} 讲`}</span>
        {' · '}{ep.title}
        {subtitleOf && <span style={{ marginLeft: 6, color: '#bbb' }}>{subtitleOf(ep)}</span>}
      </div>

      {/* 生成中 */}
      {gen && (
        <div style={{ marginBottom: 10 }}>
          <Space>
            <LoadingOutlined />
            <span style={{ fontSize: 13, color: '#666' }}>
              正在生成这一讲
              {gen.total ? `（${gen.done}/${gen.total} 段，约 ${Math.max(1, Math.ceil((gen.total - gen.done) * 2 / 60))} 分钟）` : '…'}
            </span>
          </Space>
          <Progress percent={genPct} size="small" status="active" />
          <div style={{ fontSize: 12, color: '#aaa' }}>
            生成在服务器上进行，可以离开本页，稍后回来接着听。
          </div>
        </div>
      )}

      {err && <Alert type="warning" showIcon style={{ marginBottom: 10 }} message={err} />}
      {!err && failed > 0 && (
        <Alert
          type="info" showIcon style={{ marginBottom: 10 }}
          message={`这一讲有 ${failed} 处没合成出来（多为代码块/公式），对应句子不高亮、但文字照常显示`}
        />
      )}

      <audio
        ref={audioRef}
        src={audioUrl || undefined}
        preload="auto"
        onPlay={() => setPlaying(true)}
        onPause={() => { setPlaying(false); saveProgress(ep.id, curRef.current.pos) }}
        onTimeUpdate={e => onTimeUpdate((e.target as HTMLAudioElement).currentTime)}
        onLoadedMetadata={e => {
          const a = e.target as HTMLAudioElement
          if (Number.isFinite(a.duration)) setDuration(a.duration)
          // 恢复断点：等元数据到了再设 currentTime，否则会被忽略
          if (resumeAtRef.current > 0) {
            a.currentTime = resumeAtRef.current
            setCurTime(resumeAtRef.current)
            resumeAtRef.current = 0
          }
        }}
        onEnded={() => {
          setPlaying(false)
          saveProgress(ep.id, duration || 0, true)   // 听完了 → 不再出现在「继续收听」
          if (index < queue.length - 1) goto(1, true)
        }}
        style={{ display: 'none' }}
      />

      {/* 原文：一句一个 span，点哪句从哪句听 */}
      <div
        ref={listRef}
        style={{
          maxHeight: '54vh', overflowY: 'auto', lineHeight: 2.1, fontSize: 16,
          padding: '2px', borderTop: '1px solid #f0f0f0', paddingTop: 12,
        }}
      >
        {pending ? (
          <div style={{ padding: '24px 0', textAlign: 'center' }}><Spin /></div>
        ) : sentences.length ? (
          sentences.map((s, i) => (
            <span
              key={i}
              data-si={i}
              onClick={() => seekTo(s)}
              style={{
                cursor: s.start === null ? 'default' : 'pointer',
                padding: '2px 3px', borderRadius: 4,
                background: i === activeIdx ? '#ffe58f' : 'transparent',
                color: s.start === null ? '#bbb' : 'inherit',
                transition: 'background .15s',
              }}
              title={s.start === null ? '这句没有音频' : `跳到 ${fmt(s.start)}`}
            >{s.text}</span>
          ))
        ) : (
          <span style={{ color: '#bbb' }}>这一讲没有可朗读的正文。</span>
        )}
      </div>

      <div style={{ marginTop: 10, color: '#aaa', fontSize: 12 }}>
        点任意一句从那里开始听；当前朗读的句子自动高亮；一讲放完自动接下一讲。
      </div>
    </div>
  )
}

export function fmt(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

/** 讲的状态徽标（列表和播放列表共用）。 */
export function EpisodeStatusTag({ ep }: { ep: ListenEpisode }) {
  if (ep.ready) {
    return (
      <Tag icon={<CheckCircleFilled />} color="success" style={{ marginInlineEnd: 0 }}>
        {ep.failed_segments ? `部分 ${fmt(ep.duration)}` : fmt(ep.duration)}
      </Tag>
    )
  }
  if (ep.status === 'error') {
    return <Tag icon={<ExclamationCircleFilled />} color="error" style={{ marginInlineEnd: 0 }}>失败</Tag>
  }
  if (ep.status === 'running') {
    return <Tag icon={<LoadingOutlined />} color="processing" style={{ marginInlineEnd: 0 }}>生成中</Tag>
  }
  return <Tag style={{ marginInlineEnd: 0 }}>未生成</Tag>
}