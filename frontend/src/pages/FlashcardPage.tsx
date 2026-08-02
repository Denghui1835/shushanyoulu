import { useEffect, useState } from 'react'
import { Button, Card, Tag, message, Empty, Space, Select, Progress } from 'antd'
import { ThunderboltOutlined, ReloadOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

export default function FlashcardPage() {
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [mode, setMode] = useState<'due' | 'doc'>('due')
  const [cards, setCards] = useState<any[]>([])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(0)
  const [generating, setGenerating] = useState(false)
  const [params] = useSearchParams()

  const loadDocs = async () => {
    const d = await api.listDocuments()
    setDocs(d)
    const fromUrl = params.get('doc')
    if (fromUrl && d.some((x: any) => x.id === fromUrl)) setDocId(fromUrl)
    else if (d.length) setDocId(d[0].id)
  }
  useEffect(() => { loadDocs() }, [])

  const loadDue = async () => {
    const res = await api.getDueCards()
    setCards(res.flashcards)
    setIdx(0); setDone(0); setFlipped(false)
    setMode('due')
  }
  useEffect(() => { loadDue() }, [])

  const loadDoc = async () => {
    if (!docId) return
    const res = await api.listFlashcards(docId)
    setCards(res.flashcards)
    setIdx(0); setDone(0); setFlipped(false)
    setMode('doc')
  }
  useEffect(() => { if (docId) loadDoc() }, [docId])

  const generate = async () => {
    setGenerating(true)
    try {
      const res = await api.generateFlashcards(docId, 15)
      message.success(`闪卡生成完成，共 ${res.count} 张`)
      loadDoc()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败')
    } finally { setGenerating(false) }
  }

  const review = async (rating: number) => {
    const card = cards[idx]
    await api.reviewCard(card.id, rating)
    setDone(d => d + 1)
    if (idx + 1 < cards.length) {
      setIdx(idx + 1)
      setFlipped(false)
    } else {
      setCards([])
    }
  }

  const card = cards[idx]
  const RATINGS = [
    { v: 1, label: '很模糊', color: 'default' },
    { v: 2, label: '有点难', color: 'orange' },
    { v: 3, label: '记住了', color: 'blue' },
    { v: 4, label: '很简单', color: 'green' },
  ]

  return (
    <div style={{ maxWidth: 680, margin: '0 auto' }}>
      <div className="page-card">
        <Space wrap>
          <ThunderboltOutlined style={{ color: '#7c5cfc', fontSize: 18 }} />
          <b>闪卡复习</b>
          <Select style={{ width: 240 }} placeholder="选择资料" value={docId || undefined}
            onChange={setDocId} options={docs.map(d => ({ value: d.id, label: d.title }))} />
          <Button onClick={generate} loading={generating}>生成闪卡</Button>
          <Button type="primary" onClick={loadDue}><ReloadOutlined /> 复习到期的</Button>
        </Space>
      </div>

      {!card ? (
        <div className="page-card">
          <Empty
            description={mode === 'due' ? '太棒了！今天该复习的卡片都复习完了 🎉' : '这份资料还没有闪卡，点「生成闪卡」创建'}
          />
          <div style={{ textAlign: 'center' }}>
            <Button type="primary" onClick={loadDue}>看看待复习</Button>
          </div>
        </div>
      ) : (
        <div className="page-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Tag color="purple">{idx + 1} / {cards.length}</Tag>
            <Tag>{card.reps > 0 ? `复习了 ${card.reps} 次` : '新卡片'}</Tag>
          </div>

          <Card
            style={{ cursor: 'pointer', minHeight: 180, textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            onClick={() => setFlipped(f => !f)}
            styles={{ body: { display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 180 } }}
          >
            <div style={{ fontSize: 20, lineHeight: 1.8 }}>
              {flipped ? card.back : card.front}
            </div>
          </Card>
          <div style={{ textAlign: 'center', color: '#999', fontSize: 12, marginTop: 8 }}>
            点击卡片翻转{flipped ? '' : '，回忆答案后再翻'}
          </div>

          {flipped && (
            <div style={{ marginTop: 16 }}>
              <div style={{ textAlign: 'center', marginBottom: 8, color: '#999', fontSize: 13 }}>
                这次记得怎么样？
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                {RATINGS.map(r => (
                  <Button key={r.v} size="large" style={{ minWidth: 90 }} onClick={() => review(r.v)}>
                    {r.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
