import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Space, Spin, message, Tooltip } from 'antd'
import { EyeOutlined, EyeInvisibleOutlined, ReloadOutlined } from '@ant-design/icons'
import { api } from '../api'

interface Blank { keyword: string; positions: { start: number; end: number }[] }
interface Mark { start: number; end: number; keyword: string; key: string }

interface Props {
  docId: string
  unitIndex: number
}

/** 关键词挖空背诵（纯死记）：关键词替换为可点击空白，点击显示/隐藏。 */
export default function BlankView({ docId, unitIndex }: Props) {
  const [data, setData] = useState<{ title: string; text: string; blanks: Blank[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [revealed, setRevealed] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.getBlankContent(docId, unitIndex))
      setRevealed(new Set())
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败')
    } finally { setLoading(false) }
  }, [docId, unitIndex])

  useEffect(() => { load() }, [load])

  const marks = useMemo<Mark[]>(() => {
    const arr: Mark[] = []
    data?.blanks.forEach(b => b.positions.forEach(p => arr.push({
      start: p.start, end: p.end, keyword: b.keyword, key: `${p.start}-${p.end}`,
    })))
    return arr.sort((a, b) => a.start - b.start)
  }, [data])

  const segments = useMemo(() => {
    if (!data) return []
    const out: ({ text: string; mark?: Mark })[ ] = []
    let pos = 0
    for (const m of marks) {
      if (m.start > pos) out.push({ text: data.text.slice(pos, m.start) })
      out.push({ text: '', mark: m })
      pos = m.end
    }
    if (pos < data.text.length) out.push({ text: data.text.slice(pos) })
    return out
  }, [data, marks])

  const toggle = (m: Mark) => setRevealed(prev => {
    const n = new Set(prev)
    if (n.has(m.key)) n.delete(m.key); else n.add(m.key)
    return n
  })

  if (loading && !data) return <Spin style={{ display: 'block', margin: 40 }} />

  if (!data) return null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <b>🔒 关键词挖空</b>
        <span style={{ color: '#999', fontSize: 12 }}>点击空白显示/隐藏，先自己回忆再对照</span>
        <div style={{ marginLeft: 'auto' }}>
          <Space size={6}>
            <Button size="small" icon={<EyeOutlined />} onClick={() => setRevealed(new Set(marks.map(m => m.key)))}>全部显示</Button>
            <Button size="small" icon={<EyeInvisibleOutlined />} onClick={() => setRevealed(new Set())}>全部隐藏</Button>
            <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>重新生成</Button>
          </Space>
        </div>
      </div>

      <div style={{ fontSize: 15, lineHeight: 2.2, whiteSpace: 'pre-wrap', userSelect: 'text' }}>
        {segments.map((s, i) => s.mark ? (
          <Tooltip key={i} title="点击显示/隐藏">
            <span onClick={() => toggle(s.mark!)} style={{ cursor: 'pointer', margin: '0 1px' }}>
              {revealed.has(s.mark.key) ? (
                <b style={{ color: '#7c5cfc', background: '#f4f0ff', padding: '0 4px', borderRadius: 4 }}>
                  {s.mark.keyword}
                </b>
              ) : (
                <span style={{
                  display: 'inline-block', minWidth: 36, padding: '0 3px', textAlign: 'center',
                  borderBottom: '2px solid #7c5cfc', color: '#c0b8ea',
                }}>
                  {'＿'.repeat(Math.max(1, s.mark.keyword.length))}
                </span>
              )}
            </span>
          </Tooltip>
        ) : (
          <span key={i}>{s.text}</span>
        ))}
      </div>

      <div style={{ marginTop: 10, color: '#bbb', fontSize: 12 }}>
        共挖空 {marks.length} 处 · {data.blanks.length} 个关键词
      </div>
    </div>
  )
}
