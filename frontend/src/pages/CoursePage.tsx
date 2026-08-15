import { useEffect, useState } from 'react'
import { Card, Button, Space, Tag, Typography, Input, message, Progress, Spin, Empty, List } from 'antd'
import {
  CheckOutlined, PlayCircleOutlined, RightOutlined, BookOutlined, TrophyOutlined, WarningOutlined, BulbOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import PageHeader from '../components/PageHeader'

const { Title, Paragraph, Text } = Typography
const { TextArea } = Input

type Phase = 'lecture' | 'practice' | 'check' | 'done'

/** 老教授课堂：一对一交互式授课（一小节知识点 → 真题示例 → 练习 → 检验提问） */
export default function CoursePage() {
  const [params] = useSearchParams()
  const subject = params.get('subject') || ''
  const [outline, setOutline] = useState<any>(null)
  const [topic, setTopic] = useState('')
  const [phase, setPhase] = useState<Phase>('lecture')
  const [lesson, setLesson] = useState<any>(null)
  const [answer, setAnswer] = useState('')
  const [feedback, setFeedback] = useState<any>(null)
  const [attempt, setAttempt] = useState(1)
  const [doneInfo, setDoneInfo] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const loadOutline = async () => {
    const o = await api.getCourseOutline(subject)
    setOutline(o)
    return o
  }

  const openTopic = async (t: string) => {
    setTopic(t); setPhase('lecture'); setLesson(null); setAnswer('')
    setFeedback(null); setAttempt(1); setDoneInfo(null)
    setLoading(true)
    try {
      const l = await api.startCourseLesson(subject, t)
      setLesson(l)
    } catch (e: any) { message.error(e?.response?.data?.detail || '开课失败') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!subject) return
    loadOutline().then(o => {
      if (o.current_index < o.total) openTopic(o.topics[o.current_index].topic)
    }).catch(() => { /* backend not ready */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject])

  const submit = async (kind: 'practice' | 'check') => {
    if (!answer.trim()) { message.warning('先写下你的答案，老教授等着呢'); return }
    setLoading(true)
    try {
      const r = await api.answerCourseLesson(subject, { topic, kind, answer, attempt })
      setFeedback(r)
      setAnswer('')
      if (r.correct && kind === 'practice') {
        message.success('练习答对！老教授给你点赞 🎉')
      } else if (r.correct && kind === 'check') {
        message.success('检验通过，本节掌握！')
        const c = await api.completeCourseLesson(subject, topic)
        setDoneInfo(c)
        setPhase('done')
        loadOutline().then(o => { setOutline(o) })
      } else {
        setAttempt(a => a + 1)
        if (r.reveal) message.info('老教授给出了参考答案，先看懂再继续')
      }
    } catch (e: any) { message.error(e?.response?.data?.detail || '提交失败') }
    finally { setLoading(false) }
  }

  if (!subject) return (
    <div className="yq-page">
      <div className="yq-section yq-empty-state">
        <div className="yq-empty-icon">🎓</div>
        <p>缺少课程科目，请从书架中的课程书进入</p>
        <Button type="primary" onClick={() => window.history.back()}>返回</Button>
      </div>
    </div>
  )
  if (!outline) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  return (
    <div className="yq-page">
      <PageHeader
        icon={<BookOutlined />}
        title={`老教授课堂 · ${subject}`}
        subtitle="12 年 NCRE 阅卷经验 · 一小节知识点 → 真题示例 → 练习 → 提问，一对一教到懂"
        extra={<Text type="secondary">已掌握 {outline.topics.filter((t: any) => t.done).length}/{outline.total} 节</Text>}
      />

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 大纲侧栏 */}
        <div style={{ width: 240, flexShrink: 0 }}>
          <Card size="small" title="课程大纲">
            <List
              size="small"
              dataSource={outline.topics}
              renderItem={(t: any, i: number) => (
                <List.Item
                  style={{ cursor: 'pointer', padding: '6px 8px', borderRadius: 6,
                    background: i === outline.current_index ? '#fffbe6' : 'transparent',
                    opacity: t.done ? 0.85 : 1 }}
                  onClick={() => openTopic(t.topic)}
                >
                  <Space>
                    {t.done ? <CheckOutlined style={{ color: '#52c41a' }} />
                      : i === outline.current_index ? <PlayCircleOutlined style={{ color: '#fa8c16' }} />
                      : <Tag style={{ border: 'none' }}>{i + 1}</Tag>}
                    <Text style={{ fontSize: 13 }} delete={t.done}>{t.topic}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </div>

        {/* 授课区 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {phase === 'done' ? (
            <Card>
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <TrophyOutlined style={{ fontSize: 44, color: '#faad14' }} />
                <Title level={3} style={{ margin: '12px 0 4px' }}>本节掌握！</Title>
                <Text type="secondary">「{topic}」已标记为已掌握，恭喜你稳步前进。</Text>
              </div>
              <div style={{ textAlign: 'center', marginTop: 12 }}>
                <Button type="primary" icon={<RightOutlined />} onClick={() => {
                  if (doneInfo?.next_topic) openTopic(doneInfo.next_topic)
                  else message.success('全部课程学完啦！去「全真模拟」检验成果吧')
                }}>
                  {doneInfo?.next_topic ? `下一节：${doneInfo.next_topic}` : '全部完成 🎉'}
                </Button>
              </div>
            </Card>
          ) : !lesson ? (
            <Card><Spin style={{ display: 'block', margin: '40px auto' }} /></Card>
          ) : (
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              {/* 第 1 步：讲解 */}
              {phase === 'lecture' && (
                <Card
                  title={<Space><Text strong>{topic}</Text><Tag color="gold">一小节知识点</Tag></Space>}
                >
                  <div className="yq-md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{lesson.lecture}</ReactMarkdown>
                  </div>
                  {lesson.traps?.length > 0 && (
                    <Card size="small" style={{ marginTop: 12, background: '#fff1f0', borderColor: '#ffa39e' }}>
                      <Space direction="vertical" size={4}>
                        <Text strong style={{ color: '#cf1322' }}><WarningOutlined /> 扣分陷阱 / 阅卷要点</Text>
                        {lesson.traps.map((t: string, i: number) => (
                          <Text key={i} style={{ fontSize: 13 }}>· {t}</Text>
                        ))}
                      </Space>
                    </Card>
                  )}
                  <Button type="primary" icon={<RightOutlined />} style={{ marginTop: 14 }}
                    onClick={() => setPhase('practice')}>
                    我学会了，做课堂练习
                  </Button>
                </Card>
              )}

              {/* 第 2 步：练习 */}
              {phase === 'practice' && (
                <Card title={<Space><Text strong>课堂练习</Text><Tag color="blue">动手写</Tag></Space>}>
                  <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{lesson.practice}</Paragraph>
                  <TextArea rows={5} value={answer} onChange={e => setAnswer(e.target.value)}
                    placeholder="写下你的代码/思路（第 3 次还不对，老教授才会给参考答案）"
                    style={{ fontFamily: 'Consolas, Monaco, monospace' }} disabled={feedback?.correct} />
                  {feedback && (
                    <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 10 }}>
                      <Tag color={feedback.correct ? 'success' : 'warning'}>
                        {feedback.correct ? '✅ 答对！' : `第 ${attempt - 1} 次作答`}
                      </Tag>
                      <Paragraph style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>{feedback.feedback}</Paragraph>
                      {feedback.reveal && feedback.reference && (
                        <div style={{ marginTop: 8, background: '#f6ffed', borderRadius: 8, padding: 12 }}>
                          <Text strong style={{ color: '#389e0d' }}>💡 参考答案（先看懂，再自己写一遍）</Text>
                          <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', fontFamily: 'Consolas, Monaco, monospace' }}>
                            {feedback.reference}
                          </Paragraph>
                        </div>
                      )}
                    </div>
                  )}
                  <Space style={{ marginTop: 12 }}>
                    {!feedback?.correct && (
                      <Button type="primary" icon={<RightOutlined />} loading={loading} onClick={() => submit('practice')}>
                        提交练习
                      </Button>
                    )}
                    {feedback?.correct && (
                      <Button type="primary" onClick={() => { setPhase('check'); setFeedback(null); setAnswer(''); setAttempt(1) }}>
                        检验提问 →
                      </Button>
                    )}
                  </Space>
                </Card>
              )}

              {/* 第 3 步：检验 */}
              {phase === 'check' && (
                <Card title={<Space><Text strong>检验提问</Text><Tag color="purple">考核心</Tag></Space>}>
                  <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{lesson.check}</Paragraph>
                  <TextArea rows={3} value={answer} onChange={e => setAnswer(e.target.value)}
                    placeholder="用你自己的话回答" disabled={feedback?.correct} />
                  {feedback && (
                    <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 10 }}>
                      <Tag color={feedback.correct ? 'success' : 'warning'}>
                        {feedback.correct ? '✅ 检验通过' : '再想想'}
                      </Tag>
                      <Paragraph style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>{feedback.feedback}</Paragraph>
                      {feedback.reveal && feedback.reference && (
                        <div style={{ marginTop: 8, background: '#f6ffed', borderRadius: 8, padding: 12 }}>
                          <Text strong style={{ color: '#389e0d' }}>💡 参考答案要点</Text>
                          <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>{feedback.reference}</Paragraph>
                        </div>
                      )}
                    </div>
                  )}
                  <Space style={{ marginTop: 12 }}>
                    {!feedback?.correct && (
                      <Button type="primary" icon={<RightOutlined />} loading={loading} onClick={() => submit('check')}>
                        提交检验
                      </Button>
                    )}
                  </Space>
                </Card>
              )}
            </Space>
          )}
        </div>
      </div>
    </div>
  )
}
