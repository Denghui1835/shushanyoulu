import { useEffect, useMemo, useState } from 'react'
import { Select, Button, Radio, Input, Tag, message, Empty, Space, Alert, Segmented, Popconfirm, InputNumber } from 'antd'
import { EditOutlined, RightOutlined, DeleteOutlined, UndoOutlined, StarOutlined, ReloadOutlined, SearchOutlined, ShakeOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'

type Filter = 'all' | 'mistake' | 'discarded'

export default function QuizPage() {
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [questions, setQuestions] = useState<any[]>([])
  const [idx, setIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<any>(null)
  const [correctCount, setCorrectCount] = useState(0)
  const [generating, setGenerating] = useState(false)
  const [params] = useSearchParams()
  const [keyword, setKeyword] = useState('')              // 考点关键词筛选
  const [randomOrder, setRandomOrder] = useState<number[] | null>(null)  // 随机组卷顺序
  const [randomN, setRandomN] = useState(10)              // 随机组卷题数

  const loadDocs = async () => {
    const d = await api.listDocuments()
    setDocs(d)
    const fromUrl = params.get('doc')
    if (fromUrl && d.some((x: any) => x.id === fromUrl)) setDocId(fromUrl)
    else {
      // 默认优先落到题库章节（有现成题目可直接刷），否则取第一个
      const bank = d.find((x: any) => (x.title || '').includes('题库'))
      setDocId(bank ? bank.id : (d[0]?.id || ''))
    }
  }
  useEffect(() => { loadDocs() }, [])

  const load = async () => {
    if (!docId) return
    const opts: any = {}
    if (filter === 'mistake') opts.mistake_book = true
    if (filter === 'discarded') opts.include_discarded = true
    const res = await api.listQuestions(docId, opts)
    setQuestions(res.questions)
    setRandomOrder(null)
    setIdx(0); setAnswer(''); setResult(null); setCorrectCount(0)
  }
  useEffect(() => { if (docId) load() }, [docId, filter])

  // 考点关键词筛选（按题干过滤）
  const filtered = useMemo(() => {
    if (!keyword.trim()) return questions
    const k = keyword.trim().toLowerCase()
    return questions.filter((q: any) => (q.question || '').toLowerCase().includes(k))
  }, [questions, keyword])

  // 展示列表：随机组卷时按打乱顺序取前 N 道
  const display = useMemo(() => {
    if (!randomOrder) return filtered
    return randomOrder.map(i => filtered[i]).filter(Boolean)
  }, [filtered, randomOrder])

  const shuffle = () => {
    const n = Math.min(randomN, filtered.length)
    const order = Array.from({ length: filtered.length }, (_, i) => i)
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[order[i], order[j]] = [order[j], order[i]]
    }
    setRandomOrder(order.slice(0, n))
    setIdx(0); setAnswer(''); setResult(null); setCorrectCount(0)
  }

  const generate = async () => {
    setGenerating(true)
    try {
      await api.generateQuestions(docId, 8)
      message.success('题目生成完成')
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败')
    } finally { setGenerating(false) }
  }

  const submit = async () => {
    if (!answer.trim()) { message.warning('先填写答案'); return }
    const res = await api.gradeQuestion(display[idx].id, answer)
    setResult(res)
    if (res.correct) { setCorrectCount(c => c + 1); message.success('回答正确 🎉') }
  }

  // ---------- 题目管理 ----------
  const discard = async (q: any) => {
    await api.discardQuestion(q.id)
    message.success('已弃用（可在「已弃用」里恢复）')
    load()
  }
  const restore = async (q: any) => {
    await api.restoreQuestion(q.id)
    message.success('已恢复')
    load()
  }
  const toggleMistake = async (q: any) => {
    if (q.in_mistake_book) await api.removeFromMistakeBook(q.id)
    else await api.addToMistakeBook(q.id)
    message.success(q.in_mistake_book ? '已移出错题本' : '已加入错题本')
    load()
  }

  const q = display[idx]
  const finished = display.length > 0 && idx >= display.length

  const FILTER_OPTS = [
    { value: 'all', label: `全部 (${display.length})` },
    { value: 'mistake', label: '错题本' },
    { value: 'discarded', label: '已弃用' },
  ]

  return (
    <div className="yq-page">
      <PageHeader
        icon={<EditOutlined />}
        title="练习题"
        subtitle="选择资料刷题，填空 / 简答由 AI 阅卷点评，做错的题收进错题本"
        extra={
          <>
            <Select style={{ width: 240 }} placeholder="选择资料" value={docId || undefined}
              onChange={setDocId} options={docs.map(d => ({ value: d.id, label: d.title }))} />
            {filter === 'all' && (
              <Button type="primary" loading={generating} onClick={generate}>
                {questions.length ? '再生成一批' : '生成题目'}
              </Button>
            )}
          </>
        }
      />
      <div className="yq-section">
        <Segmented value={filter} onChange={v => setFilter(v as Filter)} options={FILTER_OPTS} />
        <Space wrap style={{ marginTop: 12 }}>
          <Input
            allowClear placeholder="按考点筛选（如：列表 / 指针）"
            prefix={<SearchOutlined />} value={keyword}
            onChange={e => { setKeyword(e.target.value); setIdx(0); setAnswer(''); setResult(null); setCorrectCount(0) }}
            style={{ width: 220 }}
          />
          <InputNumber min={5} max={50} value={randomN} onChange={v => v && setRandomN(v)} style={{ width: 78 }} addonBefore="抽" />
          <Button icon={<ShakeOutlined />} onClick={shuffle} disabled={filtered.length === 0}>
            {randomOrder ? '重新随机组卷' : '随机组卷'}
          </Button>
          {randomOrder && <Tag color="geekblue">随机 {display.length} 题（共 {filtered.length} 题）</Tag>}
        </Space>
      </div>

      {finished ? (
        <div className="yq-section yq-empty-state">
          <h2 style={{ marginTop: 0 }}>本次练习完成 🎉</h2>
          <p style={{ color: '#666', fontSize: 15 }}>
            共 <b>{display.length}</b> 题，答对 <b style={{ color: '#52c41a' }}>{correctCount}</b> 题
          </p>
          <p style={{ color: '#999', fontSize: 13 }}>
            做错的题可点「加入错题本」收录，方便日后集中复习
          </p>
          <Space style={{ marginTop: 8 }}>
            <Button type="primary" icon={<ReloadOutlined />}
              onClick={() => { setIdx(0); setAnswer(''); setResult(null); setCorrectCount(0) }}>
              重新练习
            </Button>
            <Button onClick={() => setFilter('mistake')}>去错题本</Button>
          </Space>
        </div>
      ) : !q ? (
        <div className="yq-section yq-empty-state">
          <div className="yq-empty-icon">📝</div>
          <Empty
            description={
              filter === 'all' ? '还没有题目，点击「生成题目」开始练习'
              : filter === 'mistake' ? '错题本是空的，做错的题点「加入错题本」就会出现在这里'
              : '还没有弃用的题目'
            }
          />
        </div>
      ) : (
        <div className="yq-section">
          <Space style={{ marginBottom: 12 }}>
            <Tag color="purple">{idx + 1} / {questions.length}</Tag>
            <Tag>{q.qtype === 'choice' ? '选择题' : q.qtype === 'fill' ? '填空题' : '简答题'}</Tag>
            {q.in_mistake_book && <Tag color="gold">错题本</Tag>}
          </Space>
          <h3>{q.question}</h3>

          {q.qtype === 'choice' ? (
            <Radio.Group
              style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}
              value={answer} onChange={e => setAnswer(e.target.value)} disabled={!!result}
            >
              {q.options.map((opt: string, i: number) => (
                <Radio key={i} value={opt} style={{ padding: '6px 10px' }}>
                  {String.fromCharCode(65 + i)}. {opt}
                </Radio>
              ))}
            </Radio.Group>
          ) : (
            <Input.TextArea
              rows={3} value={answer} onChange={e => setAnswer(e.target.value)}
              placeholder="写下你的答案" disabled={!!result}
            />
          )}

          <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            {!result ? (
              <Button type="primary" icon={<RightOutlined />} onClick={submit}>提交</Button>
            ) : (
              <>
                <Alert
                  style={{ flex: 1 }}
                  type={result.correct ? 'success' : 'error'}
                  showIcon
                  message={result.correct ? '回答正确！' : '再想想，正确答案见解析'}
                  description={
                    <div>
                      <div><b>答案：</b>{result.answer}</div>
                      {result.comment && <div style={{ marginTop: 6 }}><b>阅卷点评：</b>{result.comment}</div>}
                      {result.explanation && <div style={{ marginTop: 6 }}><b>解析：</b>{result.explanation}</div>}
                    </div>
                  }
                />
                <Button type="primary" onClick={() => { setIdx(i => i + 1); setAnswer(''); setResult(null) }}>
                  {idx + 1 >= questions.length ? '完成' : '下一题'}
                </Button>
              </>
            )}
          </div>

          {/* 题目管理：弃用 / 错题本 */}
          <div style={{ marginTop: 14, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
            {q.discarded ? (
              <Button size="small" icon={<UndoOutlined />} onClick={() => restore(q)}>恢复</Button>
            ) : (
              <Space size={8}>
                <Popconfirm title="弃用这道题？它会被隐藏，可在「已弃用」里恢复" onConfirm={() => discard(q)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>弃用</Button>
                </Popconfirm>
                <Button
                  size="small" type={q.in_mistake_book ? 'primary' : 'default'} icon={<StarOutlined />}
                  onClick={() => toggleMistake(q)}
                >
                  {q.in_mistake_book ? '移出错题本' : '加入错题本'}
                </Button>
              </Space>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
