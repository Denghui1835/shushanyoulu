import { useCallback, useEffect, useMemo, useState } from 'react'
import { Select, Space, Spin, Empty, Segmented, message, Button, Tag, Tooltip } from 'antd'
import { SoundOutlined, HistoryOutlined, BookOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import ListenPlayer, { EpisodeStatusTag, fmt, type ListenEpisode } from '../components/ListenPlayer'

const VOICES = [
  { label: '晓晓 · 女声', value: 'zh-CN-XiaoxiaoNeural' },
  { label: '云希 · 男声', value: 'zh-CN-YunxiNeural' },
  { label: '云扬 · 男声', value: 'zh-CN-YunyangNeural' },
  { label: '晓北 · 东北女声', value: 'zh-CN-liaoning-XiaobeiNeural' },
]
const SPEEDS = [
  { label: '0.75×', value: 0.75 }, { label: '1×', value: 1 },
  { label: '1.25×', value: 1.25 }, { label: '1.5×', value: 1.5 },
]

interface Chapter {
  document_id: string; title: string; planned: boolean
  episode_count: number; done_count: number
  episodes: ListenEpisode[]
}

/**
 * 听读页：**书 → 章 → 讲**。
 *
 * 一本书就是一张专辑，一章是一讲或几讲（长章按字数自动切，见 backend/core/episodes.py），
 * 所有讲串成一条队列，所以能跨章连播、能断点续听。
 *
 * 为什么要从「页」升到「讲」：PDF 的天然单位是物理页，可没人想「听第 37 页」——
 * 人想听的是**一讲**，通勤路上放完一段，回来还在讲同一件事。
 */
export default function ListenPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const [projects, setProjects] = useState<any[]>([])
  const [projectId, setProjectId] = useState('')
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [voice, setVoice] = useState(VOICES[0].value)
  const [speed, setSpeed] = useState(1)
  const [loading, setLoading] = useState(false)
  const [busyChapter, setBusyChapter] = useState('')
  const [index, setIndex] = useState(0)
  const [curPage, setCurPage] = useState<number | null>(null)
  const [resume, setResume] = useState<any>(null)

  // ---------- 载入书目 ----------
  useEffect(() => {
    (async () => {
      try {
        const ps = await api.listProjects()
        setProjects(ps || [])
        const fromUrl = params.get('project')
        const pick = (fromUrl && (ps || []).some((x: any) => x.id === fromUrl))
          ? fromUrl : (ps?.[0]?.id || '')
        setProjectId(pick)
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '书目加载失败')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadAlbum = useCallback(async (pid: string) => {
    const a = await api.listenAlbum(pid)
    setChapters(a?.chapters || [])
    return a?.chapters || []
  }, [])

  // ---------- 载入这本书的目录（只查库，不解析 PDF） ----------
  useEffect(() => {
    if (!projectId) return
    let alive = true
    setLoading(true)
    ;(async () => {
      try {
        const chs = await loadAlbum(projectId)
        if (!alive) return
        const c = await api.listenContinue(projectId).catch(() => null)
        setResume(c?.items?.[0] || null)
        void chs
      } catch (e: any) {
        if (alive) message.error(e?.response?.data?.detail || '目录加载失败')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [projectId, loadAlbum])

  // ---------- 整本书的讲串成一条播放队列（章序 → 讲序） ----------
  const queue: ListenEpisode[] = useMemo(
    () => chapters.flatMap(c => c.episodes || []),
    [chapters])

  const chapterOf = useMemo(() => {
    const m = new Map<string, string>()
    chapters.forEach(c => (c.episodes || []).forEach(e => m.set(e.id, c.title)))
    return m
  }, [chapters])

  // 队列变了（生成完一讲/新规划一章）就把当前播放位置对齐到「哪一讲」
  const curId = queue[Math.min(index, Math.max(0, queue.length - 1))]?.id
  useEffect(() => {
    if (!curId && queue.length) setIndex(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.length])

  // ---------- 点某一章：没规划过就先规划 ----------
  const openChapter = async (ch: Chapter) => {
    let chs = chapters
    if (!ch.planned) {
      setBusyChapter(ch.document_id)
      try {
        await api.listenEpisodes(ch.document_id, { voice, speed })
        chs = await loadAlbum(projectId)
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '这一章打不开（可能是扫描图片页，提不出正文）')
        setBusyChapter('')
        return
      }
      setBusyChapter('')
    }
    // 定位到这一章的第一讲
    const flat = chs.flatMap((c: Chapter) => c.episodes || [])
    const first = (chs.find((c: Chapter) => c.document_id === ch.document_id)?.episodes || [])[0]
    if (first) setIndex(Math.max(0, flat.findIndex(e => e.id === first.id)))
  }

  const onEpisodeReady = useCallback((id: string, patch: Partial<ListenEpisode>) => {
    setChapters(prev => prev.map(c => {
      const eps = c.episodes || []
      if (!eps.some(e => e.id === id)) return c
      const next = eps.map(e => (e.id === id ? { ...e, ...patch } : e))
      return {
        ...c,
        episodes: next,
        done_count: next.filter(e => e.ready).length,
      }
    }))
  }, [])

  const goResume = async () => {
    if (!resume) return
    // 「继续收听」可能是别的章里的讲：先确保那一讲在队列里
    const ch = chapters.find(c => (c.episodes || []).some(e => e.id === resume.id))
    if (!ch) {
      const doc = chapters.find(c => c.document_id === resume.document_id)
      if (doc) await openChapter(doc)
      else return
    }
    const flat = (await loadAlbum(projectId)).flatMap((c: Chapter) => c.episodes || [])
    const i = flat.findIndex((e: ListenEpisode) => e.id === resume.id)
    if (i >= 0) setIndex(i)
  }

  const totalEp = queue.length
  const doneEp = queue.filter(e => e.ready).length
  const totalSec = queue.reduce((a, e) => a + (e.ready ? e.duration || 0 : 0), 0)

  return (
    <div className="yq-page">
      <div className="yq-section" style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <SoundOutlined style={{ fontSize: 20, color: '#7c5cfc' }} />
          <h2 style={{ margin: 0 }}>听读</h2>
          <span style={{ color: '#999', fontSize: 13 }}>听是主线，读跟着走</span>
          <div style={{ flex: 1 }} />
          {resume && (
            <Tooltip title={`上次听到：${resume.title}`}>
              <Button icon={<HistoryOutlined />} onClick={goResume}>继续收听</Button>
            </Tooltip>
          )}
          <Select
            style={{ width: 260 }} placeholder="选一本书" value={projectId || undefined}
            onChange={v => {
              setProjectId(v); setIndex(0); setResume(null)
              setParams(prev => { const p = new URLSearchParams(prev); p.set('project', v); return p })
            }}
            options={projects.map((d: any) => ({ label: d.title, value: d.id }))}
            showSearch optionFilterProp="label"
          />
          <Select style={{ width: 130 }} value={voice} onChange={setVoice} options={VOICES} />
          <Segmented value={speed} onChange={v => setSpeed(v as number)} options={SPEEDS} />
        </div>
      </div>

      {loading ? (
        <Spin size="large" style={{ display: 'block', marginTop: 100 }} />
      ) : !chapters.length ? (
        <Empty description="这本书还没有章节" style={{ marginTop: 80 }} />
      ) : (
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          {/* 左：章目录 */}
          <div className="yq-section" style={{ width: 268, flexShrink: 0, maxHeight: '76vh', overflowY: 'auto' }}>
            <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>
              {totalEp
                ? `${chapters.length} 章 · ${doneEp}/${totalEp} 讲已备好 · ${fmt(totalSec)}`
                : `${chapters.length} 章 · 还没开始听`}
            </div>
            {chapters.map(ch => (
              <div
                key={ch.document_id}
                onClick={() => openChapter(ch)}
                style={{
                  padding: '8px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 4,
                  background: ch.document_id === queue[index]?.document_id ? '#f0ebff' : 'transparent',
                  borderLeft: ch.document_id === queue[index]?.document_id
                    ? '3px solid #7c5cfc' : '3px solid transparent',
                }}
                title={ch.title}
              >
                <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {busyChapter === ch.document_id ? <Spin size="small" /> : <BookOutlined style={{ marginRight: 6, color: '#bbb' }} />}
                  {ch.title}
                </div>
                <div style={{ fontSize: 11, color: ch.planned && ch.done_count === ch.episode_count ? '#52c41a' : '#bbb', marginTop: 2 }}>
                  {ch.planned
                    ? `${ch.episode_count} 讲 · 已备好 ${ch.done_count}`
                    : '点开才规划讲次'}
                </div>
              </div>
            ))}
          </div>

          {/* 右：播放器（含这一章/这本书的讲列表） */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 16 }}>
            {totalEp ? (
              <>
                <ListenPlayer
                  queue={queue}
                  index={Math.min(index, queue.length - 1)}
                  onIndexChange={setIndex}
                  onEpisodeReady={onEpisodeReady}
                  voice={voice}
                  speed={speed}
                  subtitleOf={ep => chapterOf.get(ep.id) || ''}
                  onPageChange={setCurPage}
                />
                {/* 讲列表（整本书，可跨章连播） */}
                <div className="yq-section" style={{ width: 264, flexShrink: 0, maxHeight: '76vh', overflowY: 'auto' }}>
                  <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>讲列表</div>
                  {chapters.filter(c => c.planned).map(ch => (
                    <div key={ch.document_id} style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 11, color: '#bbb', margin: '4px 0' }}>{ch.title}</div>
                      {(ch.episodes || []).map(e => {
                        const i = queue.findIndex(q => q.id === e.id)
                        return (
                          <div
                            key={e.id}
                            onClick={() => setIndex(i)}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 6,
                              padding: '6px 8px', borderRadius: 6, cursor: 'pointer',
                              background: i === index ? '#f0ebff' : 'transparent',
                            }}
                            title={e.title}
                          >
                            <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {e.title}
                            </span>
                            <EpisodeStatusTag ep={e} />
                          </div>
                        )
                      })}
                    </div>
                  ))}
                  {curPage !== null && (
                    <div style={{ fontSize: 11, color: '#bbb', marginTop: 8 }}>
                      正在念第 {curPage + 1} 页
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="yq-section" style={{ flex: 1 }}>
                <Empty
                  description="点左边任意一章开始——首次会把它规划成几讲（长章自动切），听的时候不用管"
                  style={{ marginTop: 60 }}
                >
                  <Space>
                    {chapters.slice(0, 3).map(ch => (
                      <Button key={ch.document_id} onClick={() => openChapter(ch)}>{ch.title}</Button>
                    ))}
                    <Tag color="purple" style={{ marginInlineStart: 8 }}>建议从第一章开始</Tag>
                  </Space>
                </Empty>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}