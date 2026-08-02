import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Tag, Space, Empty, Spin, Popconfirm, message, Progress, Collapse } from 'antd'
import { SoundOutlined, DeleteOutlined, ReloadOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { api } from '../api'

interface PodcastItem {
  id: string
  document_id: string
  unit_index: number
  doc_title: string
  unit_title: string
  content: string
  status: 'generating' | 'done' | 'error'
  error: string
  has_audio: boolean
  audio_seconds: number
  updated_at: string
}

/** 我的播客：按文档分组的播客库，可播放 / 删除 / 重新生成文稿。 */
export default function PodcastLibraryPage() {
  const [podcasts, setPodcasts] = useState<PodcastItem[]>([])
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.listPodcasts()
      setPodcasts(res.podcasts || [])
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const remove = async (p: PodcastItem) => {
    await api.deletePodcast(p.document_id, p.unit_index)
    message.success('已删除')
    load()
  }

  const regenerate = async (p: PodcastItem) => {
    const key = `${p.document_id}:${p.unit_index}`
    setRegenerating(r => ({ ...r, [key]: true }))
    try {
      await api.generatePodcastScript(p.document_id, p.unit_index)
      message.success('文稿已重新生成')
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '重新生成失败')
    } finally {
      setRegenerating(r => ({ ...r, [key]: false }))
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  // 按文档分组整理
  const groups = new Map<string, { title: string; items: PodcastItem[] }>()
  for (const p of podcasts) {
    if (!groups.has(p.document_id)) groups.set(p.document_id, { title: p.doc_title, items: [] })
    groups.get(p.document_id)!.items.push(p)
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="page-card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SoundOutlined style={{ fontSize: 26, color: '#7c5cfc' }} />
        <div>
          <h2 style={{ margin: 0 }}>我的播客</h2>
          <div style={{ color: '#999', fontSize: 13 }}>按章节生成的 AI 播客都在这里，可随时回听或整理</div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </div>
      </div>

      {podcasts.length === 0 ? (
        <div className="page-card" style={{ textAlign: 'center', padding: 60 }}>
          <Empty description="还没有播客。去「阅读」页选一章，点「AI 播客」生成吧" />
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[...groups.entries()].map(([docId, g]) => (
            <div key={docId}>
              <h3 style={{ margin: '4px 0 10px', color: '#555' }}>
                📖 {g.title} <Tag color="purple">{g.items.length} 期</Tag>
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {g.items.map(p => (
                  <PodcastCard
                    key={p.id} p={p}
                    regenerating={!!regenerating[`${p.document_id}:${p.unit_index}`]}
                    onDelete={() => remove(p)}
                    onRegenerate={() => regenerate(p)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PodcastCard({ p, regenerating, onDelete, onRegenerate }: {
  p: PodcastItem
  regenerating: boolean
  onDelete: () => void
  onRegenerate: () => void
}) {
  const minutes = p.audio_seconds ? Math.max(1, Math.round(p.audio_seconds / 60)) : 0
  return (
    <Card size="small" className="yq-book-card" style={{ borderColor: '#ece6ff' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <PlayCircleOutlined style={{ color: '#7c5cfc', fontSize: 20 }} />
        <b>{p.unit_title}</b>
        {p.status === 'done' ? (
          <>
            <Tag color="green">{p.has_audio ? `音频 · 约 ${minutes} 分钟` : '有文稿'}</Tag>
            {!p.has_audio && <Tag>未合成音频</Tag>}
          </>
        ) : p.status === 'generating' ? (
          <Tag color="processing">生成中</Tag>
        ) : (
          <Tag color="red">失败</Tag>
        )}
        <span style={{ fontSize: 12, color: '#bbb' }}>{p.updated_at?.slice(0, 16).replace('T', ' ')}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button size="small" icon={<ReloadOutlined />} loading={regenerating} onClick={onRegenerate}>
            重新生成文稿
          </Button>
          <Popconfirm title={`删除「${p.unit_title}」这期播客？`} onConfirm={onDelete}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </div>
      </div>

      {p.status === 'error' && (
        <div style={{ marginTop: 8, color: '#ff4d4f', fontSize: 13 }}>⚠️ {p.error}</div>
      )}

      {p.has_audio && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
          <audio controls src={api.podcastAudioUrl(p.document_id, p.unit_index)}
            preload="none" style={{ width: '100%', height: 34 }} />
        </div>
      )}

      <Collapse
        ghost size="small" style={{ marginTop: 6 }}
        items={[{
          key: 'script',
          label: <span style={{ fontSize: 12, color: '#8c6ff0' }}>查看文稿（{p.content.length} 字）</span>,
          children: <div style={{ fontSize: 13, lineHeight: 1.8, whiteSpace: 'pre-wrap', maxHeight: 240, overflowY: 'auto' }}>{p.content}</div>,
        }]}
      />
    </Card>
  )
}
