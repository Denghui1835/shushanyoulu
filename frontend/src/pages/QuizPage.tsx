import { useEffect, useState } from 'react'
import { Select, Button, Card, Radio, Input, Tag, message, Empty, Space, Alert } from 'antd'
import { EditOutlined, RightOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

export default function QuizPage() {
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [questions, setQuestions] = useState<any[]>([])
  const [idx, setIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<any>(null)
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
  useEffect(() => { if (docId) load() }, [docId])

  const load = async () => {
    const res = await api.listQuestions(docId)
    setQuestions(res.questions)
    setIdx(0); setAnswer(''); setResult(null)
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
    const q = questions[idx]
    const res = await api.gradeQuestion(q.id, answer)
    setResult(res)
    if (res.correct) message.success('回答正确 🎉 元气值 +5')
  }

  const q = questions[idx]

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <div className="page-card">
        <Space wrap>
          <EditOutlined style={{ color: '#7c5cfc', fontSize: 18 }} />
          <b>练习题</b>
          <Select style={{ width: 260 }} placeholder="选择资料" value={docId || undefined}
            onChange={setDocId} options={docs.map(d => ({ value: d.id, label: d.title }))} />
          <Button type="primary" loading={generating} onClick={generate}>
            {questions.length ? '重新生成题目' : '生成题目'}
          </Button>
        </Space>
      </div>

      {!q ? (
        <div className="page-card"><Empty description="还没有题目，点击「生成题目」开始练习" /></div>
      ) : (
        <div className="page-card">
          <Space style={{ marginBottom: 12 }}>
            <Tag color="purple">{idx + 1} / {questions.length}</Tag>
            <Tag>{q.qtype === 'choice' ? '选择题' : q.qtype === 'fill' ? '填空题' : '简答题'}</Tag>
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

          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            {!result ? (
              <Button type="primary" icon={<RightOutlined />} onClick={submit}>提交</Button>
            ) : (
              <>
                <Alert
                  type={result.correct ? 'success' : 'error'}
                  showIcon
                  message={result.correct ? '回答正确！' : '再想想，正确答案见解析'}
                  description={
                    <div>
                      <div><b>答案：</b>{result.answer}</div>
                      {result.explanation && <div style={{ marginTop: 6 }}><b>解析：</b>{result.explanation}</div>}
                    </div>
                  }
                />
                <Button type="primary" onClick={() => { setIdx(i => i + 1); setAnswer(''); setResult(null) }}>
                  下一题
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
