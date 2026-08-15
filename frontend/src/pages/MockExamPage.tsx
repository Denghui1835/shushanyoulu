import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button, Card, Radio, Input, Tag, message, Space, Typography, Divider, Modal, Alert, Result, Progress,
} from 'antd'
import {
  ClockCircleOutlined, ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined,
  SendOutlined, ReloadOutlined, FormOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

const { Title, Paragraph, Text } = Typography

interface ExamQ { id: string; qtype: string; question: string; options: string[]; max_score: number }
interface ExamSection { id: string; name: string; max_score: number; questions: ExamQ[] }

function fmtTime(sec: number) {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)}`
}

export default function MockExamPage() {
  const [params] = useSearchParams()
  const subject = params.get('subject') || 'python'   // 科目：python / c
  const [phase, setPhase] = useState<'intro' | 'exam' | 'report'>('intro')
  const [exam, setExam] = useState<{ title: string; duration_seconds: number; pass_line: number; sections: ExamSection[] } | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [remaining, setRemaining] = useState(0)
  const [report, setReport] = useState<any>(null)
  const [submitting, setSubmitting] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const submittedRef = useRef(false)

  useEffect(() => {
    api.getMockExam(subject).then(setExam).catch(() => message.error('模拟卷加载失败，请确认题库已就绪'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject])

  const start = () => {
    if (!exam) return
    submittedRef.current = false
    setAnswers({})
    setReport(null)
    setRemaining(exam.duration_seconds)
    setPhase('exam')
  }

  const submitNow = async (auto = false) => {
    if (submittedRef.current) return
    submittedRef.current = true
    setSubmitting(true)
    try {
      const r = await api.gradeMockExam(answers, subject)
      setReport(r)
      setPhase('report')
      if (auto) message.warning('时间到，已自动交卷')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '交卷失败，请重试')
      submittedRef.current = false
    } finally { setSubmitting(false) }
  }

  // 倒计时
  useEffect(() => {
    if (phase !== 'exam') return
    const timer = setInterval(() => setRemaining(r => (r > 0 ? r - 1 : 0)), 1000)
    return () => clearInterval(timer)
  }, [phase])

  // 到时自动交卷
  useEffect(() => {
    if (phase === 'exam' && remaining <= 0) submitNow(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining, phase])

  // 考试中离开页面提醒
  useEffect(() => {
    if (phase !== 'exam') return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [phase])

  const unanswered = useMemo(() => {
    if (!exam) return 0
    let n = 0
    for (const sec of exam.sections) for (const q of sec.questions) {
      if (!(answers[q.id] || '').trim()) n++
    }
    return n
  }, [exam, answers])

  const setAnswer = (qid: string, val: string) => setAnswers(prev => ({ ...prev, [qid]: val }))

  // ---------------------------------------------------------------- 介绍页
  if (phase === 'intro' || !exam) {
    return (
      <div className="yq-page">
        <div className="yq-section">
          <Title level={3} style={{ marginTop: 0 }}>
            <ThunderboltOutlined style={{ color: '#fa8c16' }} /> 全真模拟考试
          </Title>
          <Paragraph type="secondary">
            严格按照全国计算机等级考试二级 · Python 语言程序设计的真实考试形式模拟：
            限时、题型、分值、合格线全部对齐，交卷自动判分。
          </Paragraph>
          <Divider />
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            <Alert type="info" showIcon message="⏱️ 考试时长" description="机考限时 120 分钟，倒计时结束自动交卷。" />
            <Alert type="info" showIcon message="📋 试卷结构" description="第一部分 单项选择题 40 分（40 题 × 1 分）；第二部分 操作题 60 分（基本操作 3×5 + 简单应用 2×12.5 + 综合应用 1×20）。" />
            <Alert type="info" showIcon message="✅ 合格线" description={`满分 100 分，${exam?.pass_line ?? 60} 分合格（与真实考试一致）。`} />
            <Alert type="warning" showIcon message="✍️ 操作题判分说明" description="操作题按参考答案关键词覆盖率自动给步骤分（近似阅卷），交卷后请对照参考实现自查。" />
            <Alert type="info" showIcon message="📌 题目来源" description="题目为按二级大纲精编的模拟题（与练习题库同源），可反复开卷练习。" />
          </Space>
          <Button type="primary" size="large" icon={<FormOutlined />} style={{ marginTop: 20, width: '100%' }}
            onClick={start} disabled={!exam}>
            开始考试（{fmtTime(exam?.duration_seconds ?? 7200)}）
          </Button>
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------- 成绩单
  if (phase === 'report' && report) {
    return (
      <div className="yq-page">
        <div className="yq-section">
          <Result
            status={report.passed ? 'success' : 'error'}
            title={report.passed ? `🎉 恭喜，${report.total} 分，合格！` : `${report.total} 分，未达合格线`}
            subTitle={`满分 ${report.max_score} 分 · 合格线 ${report.pass_line} 分`}
            extra={[
              <Button key="again" type="primary" icon={<ReloadOutlined />} onClick={start}>再考一次</Button>,
              <Button key="home" onClick={() => setPhase('intro')}>返回说明页</Button>,
            ]}
          />
          <Divider>各题型得分</Divider>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {report.sections.map((s: any) => (
              <Card key={s.id} size="small" style={{ flex: 1, minWidth: 200 }}>
                <Text type="secondary">{s.name}</Text>
                <div style={{ fontSize: 22, fontWeight: 700 }}>
                  {s.score}<Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}> / {s.max_score}</Text>
                </div>
                <Progress percent={Math.round((s.score / s.max_score) * 100)} showInfo={false} strokeColor="#7c5cfc" />
              </Card>
            ))}
          </div>

          <Divider>逐题解析</Divider>
          {report.sections.map((s: any) => (
            <div key={s.id} style={{ marginBottom: 16 }}>
              <Title level={5} style={{ margin: '8px 0' }}>{s.name}</Title>
              {s.questions.map((q: any, i: number) => (
                <Card key={q.id} size="small" style={{ marginBottom: 10 }}>
                  <Space style={{ marginBottom: 6 }}>
                    <Tag color={q.correct ? 'success' : 'error'} icon={q.correct ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
                      {q.correct ? (q.qtype === 'choice' ? '答对' : `≈${q.score}分`) : `+${q.score}分`}
                    </Tag>
                    <Tag>第 {i + 1} 题{q.qtype === 'choice' ? `（${q.max_score}分）` : `（${q.max_score}分）`}</Tag>
                  </Space>
                  <Paragraph style={{ margin: '4px 0' }}><Text strong>{q.question}</Text></Paragraph>
                  <Paragraph style={{ margin: '2px 0' }}>
                    <Text type={q.correct ? 'success' : 'danger'}>你的作答：{q.user_answer || '（未作答）'}</Text>
                  </Paragraph>
                  <Paragraph style={{ margin: '2px 0' }}>
                    <Text>参考答案：{q.answer}</Text>
                  </Paragraph>
                  {q.explanation && (
                    <Paragraph type="secondary" style={{ margin: '4px 0 0 0', whiteSpace: 'pre-wrap' }}>💡 {q.explanation}</Paragraph>
                  )}
                </Card>
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------- 考试中
  const red = remaining <= 300
  return (
    <div className="yq-page">
      {/* 顶部固定：倒计时 + 交卷 */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: '#fff', padding: '10px 0', borderBottom: '1px solid #f0f0f0', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'space-between' }}>
          <Space>
            <ClockCircleOutlined style={{ fontSize: 20, color: red ? '#ff4d4f' : '#7c5cfc' }} />
            <span style={{ fontSize: 22, fontWeight: 700, color: red ? '#ff4d4f' : '#333', fontVariantNumeric: 'tabular-nums' }}>
              {fmtTime(remaining)}
            </span>
          </Space>
          <Space>
            <Tag color={red ? 'error' : 'default'}>未作答 {unanswered} 题</Tag>
            <Button type="primary" icon={<SendOutlined />} loading={submitting} onClick={() => setConfirmOpen(true)}>
              交卷
            </Button>
          </Space>
        </div>
        <Progress percent={100 - Math.round((remaining / (exam.duration_seconds || 1)) * 100)} showInfo={false}
          strokeColor={red ? '#ff4d4f' : '#7c5cfc'} size="small" style={{ marginTop: 6 }} />
      </div>

      {exam.sections.map(sec => (
        <div key={sec.id} style={{ marginBottom: 20 }}>
          <Title level={4} style={{ margin: '0 0 8px 0' }}>
            {sec.name} <Text type="secondary" style={{ fontSize: 13 }}>共 {sec.questions.length} 题</Text>
          </Title>

          {sec.id === 'choice' ? sec.questions.map((q, i) => (
            <Card key={q.id} size="small" style={{ marginBottom: 10 }}>
              <Space style={{ marginBottom: 8 }}>
                <Tag color="purple">{i + 1}</Tag>
                <Text strong>{q.question}</Text>
                <Tag>{q.max_score} 分</Tag>
              </Space>
              <Radio.Group
                style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
                value={answers[q.id]}
                onChange={e => setAnswer(q.id, e.target.value)}
              >
                {q.options.map((opt: string, j: number) => (
                  <Radio key={j} value={opt} style={{ padding: '4px 8px' }}>
                    {String.fromCharCode(65 + j)}. {opt}
                  </Radio>
                ))}
              </Radio.Group>
            </Card>
          )) : sec.questions.map((q, i) => (
            <Card key={q.id} size="small" style={{ marginBottom: 10 }}>
              <Space style={{ marginBottom: 8 }}>
                <Tag color="orange">操作题 {i + 1}</Tag>
                <Text strong>{q.question}</Text>
                <Tag>{q.max_score} 分</Tag>
              </Space>
              <Input.TextArea
                rows={5}
                placeholder="在下方写下你的代码和思路……"
                value={answers[q.id] || ''}
                onChange={e => setAnswer(q.id, e.target.value)}
                style={{ fontFamily: 'Consolas, Monaco, monospace' }}
              />
            </Card>
          ))}
        </div>
      ))}

      <div style={{ textAlign: 'center', padding: '0 0 40px' }}>
        <Button type="primary" size="large" icon={<SendOutlined />} loading={submitting} onClick={() => setConfirmOpen(true)}>
          交卷（还剩 {unanswered} 题未作答）
        </Button>
      </div>

      <Modal
        open={confirmOpen}
        title="确认交卷？"
        okText="确认交卷"
        cancelText="继续作答"
        onOk={() => { setConfirmOpen(false); submitNow(false) }}
        onCancel={() => setConfirmOpen(false)}
      >
        <Paragraph>还有 <b style={{ color: '#ff4d4f' }}>{unanswered}</b> 道题未作答。</Paragraph>
        <Paragraph type="secondary">交卷后立即判分并出成绩单，未答的题按 0 分计。</Paragraph>
      </Modal>
    </div>
  )
}
