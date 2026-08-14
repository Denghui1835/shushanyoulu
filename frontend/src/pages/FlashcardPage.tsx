import { useEffect, useRef, useState } from 'react'
import { Button, Card, Tag, message, Empty, Space, Select, Segmented, Popconfirm } from 'antd'
import { ThunderboltOutlined, ReloadOutlined, DeleteOutlined, UndoOutlined, SoundOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useTTSPlay } from '../hooks/useTTSPlay'

type Filter = 'due' | 'all' | 'discarded'

export default function FlashcardPage() {
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [filter, setFilter] = useState<Filter>('due')
  const [cards, setCards] = useState<any[]>([])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [reviewed, setReviewed] = useState(0)
  const [generating, setGenerating] = useState(false)
  const [params] = useSearchParams()
  const tts = useTTSPlay()

  const loadDocs = async () => {
    const d = await api.listDocuments()
    setDocs(d)
    const fromUrl = params.get('doc')
    if (fromUrl && d.some((x: any) => x.id === fromUrl)) setDocId(fromUrl)
    else if (d.length) setDocId(d[0].id)
  }
  useEffect(() => { loadDocs() }, [])

  const load = async () => {
    let res: any
    if (filter === 'due') {
      res = await api.getDueCards()
    } else {
      if (!docId) return
      const withDiscarded = await api.listFlashcards(docId, true)
      if (filter === 'discarded') res = { flashcards: withDiscarded.flashcards.filter((c: any) => c.discarded) }
      else res = withDiscarded
    }
    setCards(res.flashcards)
    setIdx(0); setFlipped(false)
    if (res.flashcards.length > 0) setReviewed(0)  // 有新卡片才清零，否则保留上一轮计数
  }
  useEffect(() => { load() }, [filter, docId])

  const generate = async () => {
    setGenerating(true)
    try {
      const res = await api.generateFlashcards(docId, 15)
      message.success(`闪卡生成完成，共 ${res.count} 张`)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败')
    } finally { setGenerating(false) }
  }

  const review = async (rating: number) => {
    const card = cards[idx]
    await api.reviewCard(card.id, rating)
    setReviewed(r => r + 1)
    if (idx + 1 < cards.length) {
      setIdx(idx + 1)
      setFlipped(false)
    } else {
      setCards([])  // 走完成页
    }
  }

  const discard = async (card: any) => {
    await api.discardFlashcard(card.id)
    message.success('已弃用（可在「已弃用」里恢复）')
    load()
  }
  const restore = async (card: any) => {
    await api.restoreFlashcard(card.id)
    message.success('已恢复')
    load()
  }
  const del = async (card: any) => {
    await api.deleteFlashcard(card.id)
    message.success('已彻底删除')
    load()
  }

  const card = cards[idx]
  const finished = !card && reviewed > 0
  const RATINGS = [
    { v: 1, label: '很模糊', color: 'danger' as const },
    { v: 2, label: '有点难', color: 'orange' as const },
    { v: 3, label: '记住了', color: 'primary' as const },
    { v: 4, label: '很简单', color: 'green' as const },
  ]

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>
      <div className="page-card">
        <Space wrap>
          <ThunderboltOutlined style={{ color: '#7c5cfc', fontSize: 18 }} />
          <b>闪卡复习</b>
          <Select style={{ width: 220 }} placeholder="选择资料" value={docId || undefined}
            onChange={setDocId} options={docs.map(d => ({ value: d.id, label: d.title }))} />
          {filter === 'all' && (
            <Button onClick={generate} loading={generating}>生成闪卡</Button>
          )}
          {filter === 'all' && (
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          )}
        </Space>
        <div style={{ marginTop: 10 }}>
          <Segmented
            value={filter} onChange={v => setFilter(v as Filter)}
            options={[
              { value: 'due', label: '待复习' },
              { value: 'all', label: `全部 (${filter === 'all' ? cards.length : ''})` },
              { value: 'discarded', label: '已弃用' },
            ]}
          />
        </div>
      </div>

      {finished ? (
        <div className="page-card" style={{ textAlign: 'center', padding: 50 }}>
          <h2 style={{ marginTop: 0 }}>
            {filter === 'due' ? '今天的复习完成啦 🎉' : '本组复习完成 🎉'}
          </h2>
          <p style={{ color: '#666', fontSize: 15 }}>
            本次复习 <b>{reviewed}</b> 张卡片
          </p>
          <Space style={{ marginTop: 8 }}>
            <Button type="primary" icon={<ReloadOutlined />} onClick={load}>再看一遍</Button>
            {filter !== 'due' && (
              <Button onClick={() => { setFilter('due'); setCards([]); setReviewed(0) }}>去复习到期的</Button>
            )}
          </Space>
        </div>
      ) : !card ? (
        <div className="page-card">
          <Empty
            description={
              filter === 'due' ? '太棒了！今天该复习的卡片都复习完了 🎉'
              : filter === 'all' ? '这份资料还没有闪卡，点「生成闪卡」创建'
              : '还没有弃用的闪卡'
            }
          />
          {filter === 'all' && (
            <div style={{ textAlign: 'center' }}>
              <Button type="primary" onClick={generate}>生成闪卡</Button>
            </div>
          )}
          {filter === 'due' && (
            <div style={{ textAlign: 'center' }}>
              <Button type="primary" onClick={() => setFilter('all')}>看看全部卡片</Button>
            </div>
          )}
        </div>
      ) : (
        <div className="page-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Tag color="purple">{idx + 1} / {cards.length}</Tag>
            <Tag>{card.reps > 0 ? `复习了 ${card.reps} 次` : '新卡片'}</Tag>
          </div>

          <Card
            style={{ cursor: 'pointer', minHeight: 220, textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}
            onClick={() => setFlipped(f => !f)}
            styles={{ body: { display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 220 } }}
          >
            {!flipped && <div style={{ position: 'absolute', bottom: 8, right: 12, fontSize: 11, color: '#bbb' }}>点击翻转↗</div>}
            {flipped ? (
              <div style={{ fontSize: 18, lineHeight: 1.8 }}>{card.back}</div>
            ) : (
              <div>
                {/* 图形化记忆提示：大 emoji + 联想画面 */}
                {card.visual && (
                  <div style={{ fontSize: 40, marginBottom: 8 }}>{card.visual.split(' ')[0]}</div>
                )}
                <div style={{ fontSize: 20, lineHeight: 1.8 }}>{card.front}</div>
                {card.visual && (
                  <div style={{ fontSize: 12, color: '#8c6ff0', marginTop: 8, opacity: 0.8 }}>{card.visual}</div>
                )}
              </div>
            )}
          </Card>
          <div style={{ textAlign: 'center', color: '#999', fontSize: 12, marginTop: 8 }}>
            点击卡片翻转{flipped ? '' : '，回忆答案后再翻'}
          </div>
          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <Button size="small" icon={<SoundOutlined />} loading={tts.busy}
              onClick={() => {
                if (tts.playing) { tts.stop(); return }
                tts.play(flipped ? card.back : card.front).catch(() => {})
              }}>
              {tts.playing ? '停止朗读' : '朗读'}
            </Button>
          </div>

          {flipped && (
            <div style={{ marginTop: 16 }}>
              <div style={{ textAlign: 'center', marginBottom: 8, color: '#999', fontSize: 13 }}>
                这次记得怎么样？
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                {RATINGS.map(r => (
                  <Button key={r.v} size="large" color={r.color} variant="solid" style={{ minWidth: 90 }} onClick={() => review(r.v)}>
                    {r.label}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* 管理：弃用 / 恢复 / 删除 */}
          <div style={{ marginTop: 14, borderTop: '1px solid #f0f0f0', paddingTop: 10, display: 'flex', justifyContent: 'flex-end' }}>
            {filter === 'discarded' ? (
              <Space size={8}>
                <Button size="small" icon={<UndoOutlined />} onClick={() => restore(card)}>恢复</Button>
                <Popconfirm title="彻底删除这张闪卡？不可恢复" onConfirm={() => del(card)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>彻底删除</Button>
                </Popconfirm>
              </Space>
            ) : (
              <Popconfirm title="弃用这张闪卡？它会被隐藏，可在「已弃用」里恢复" onConfirm={() => discard(card)}>
                <Button size="small" danger icon={<DeleteOutlined />}>弃用</Button>
              </Popconfirm>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
