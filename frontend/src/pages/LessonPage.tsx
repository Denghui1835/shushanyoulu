import { useEffect, useState } from 'react'
import {
  Card, Input, Button, Tag, Typography, message, Space, Select, Divider, Progress, List, Radio,
} from 'antd'
import {
  PlayCircleOutlined, SendOutlined, StopOutlined, BulbOutlined, CheckCircleOutlined, CloseCircleOutlined, PlusOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'

const { TextArea } = Input
const { Title, Paragraph, Text } = Typography

interface CurriculumItem { topic: string; desc: string; subject_key?: string }

export default function LessonPage() {
  const [params] = useSearchParams()
  const [curriculum, setCurriculum] = useState<Record<string, Record<string, CurriculumItem[]>>>({})
  const [category, setCategory] = useState(params.get('category') || '')   // 一级：门类（可从书里带过来）
  const [categorySub, setCategorySub] = useState(params.get('sub') || '')  // 二级：子学科
  const [manualTopic, setManualTopic] = useState('')

  const [lessonId, setLessonId] = useState<string | null>(null)
  const [teach, setTeach] = useState('')
  const [question, setQuestion] = useState('')
  const [options, setOptions] = useState<string[]>([])   // 选择题选项（空=开放式，回退文本框）
  const [selected, setSelected] = useState<number | null>(null)  // 选中的选项下标
  const [answer, setAnswer] = useState('')
  const [round, setRound] = useState(0)
  const [maxRounds, setMaxRounds] = useState(6)
  const [verdict, setVerdict] = useState<{ correct: boolean; comment: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [progress, setProgress] = useState<Record<string, string>>({})   // topic → status

  useEffect(() => {
    api.getCurriculum().then(setCurriculum).catch(() => { /* backend not ready */ })
    api.getLessonProgress().then(r => {
      const m: Record<string, string> = {}
      ;(r.items || []).forEach((p: any) => { if (!m[p.topic] || p.status === 'mastered') m[p.topic] = p.status })
      setProgress(m)
    }).catch(() => { /* backend not ready */ })
  }, [])

  const toggleStatus = (topic: string) => {
    const cur = progress[topic]
    const next = cur === 'mastered' ? 'review' : 'mastered'   // 已掌握 ↔ 待复习
    api.setLessonProgress({ subject: categorySub || category, topic, status: next })
      .then(() => { setProgress(p => ({ ...p, [topic]: next })) })
      .catch(() => message.error('标记失败'))
  }

  const subCats = curriculum[category] || {}
  const topics = subCats[categorySub] || []
  const masteredCount = topics.filter(t => progress[t.topic] === 'mastered').length

  const start = async (topic: string, subjectKey?: string) => {
    if (!topic.trim()) { message.warning('选一个知识点呀'); return }
    setLoading(true); setVerdict(null); setDone(false)
    try {
      // 优先用目录项自带的真实学科键，命中 内容库/{学科}/ 里的精选选择题卡；没有则退回子学科名
      const r = await api.startLesson({ subject: subjectKey || categorySub || category, topic })
      setLessonId(r.lesson_id)
      setTeach(r.teach); setQuestion(r.question)
      setOptions(r.options || []); setSelected(null)
      setRound(r.round); setMaxRounds(r.max_rounds)
      setAnswer('')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '开启教学失败，稍后再试')
    } finally { setLoading(false) }
  }

  const submit = async () => {
    if (!lessonId) return
    const isMcq = options.length > 0
    if (isMcq && selected == null) { message.warning('先选一个选项再提交'); return }
    if (!isMcq && !answer.trim()) { message.warning('先写下你的回答，再提交'); return }
    setLoading(true)
    try {
      const r = await api.answerLesson({ lesson_id: lessonId, answer: isMcq ? String(selected) : answer })
      setVerdict({ correct: r.correct, comment: r.comment })
      if (r.step === 'done') {
        setDone(true)
        message.success(r.message || '这一课收官啦！')
      } else {
        setTeach(r.teach); setQuestion(r.question)
        setOptions(r.options || []); setSelected(null)
        setRound(r.round); setMaxRounds(r.max_rounds)
        setAnswer('')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '作答处理失败')
    } finally { setLoading(false) }
  }

  const end = async () => {
    if (!lessonId) return
    try { await api.endLesson(lessonId) } catch { /* ignore */ }
    setDone(true)
    message.info('好呀，先到这儿，想学了随时回来！')
  }

  return (
    <div className="yq-page">
      <PageHeader
        icon={<BulbOutlined />}
        title="深度教学"
        subtitle="一对一私教：AI 先讲、再考、判断你的回答、点评纠正。选一门课，从目录里挑一个知识点开课吧～"
      />

      {/* 选课区 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>选学科：</Text>
            <Select
              value={category}
              onChange={c => { setCategory(c); setCategorySub('') }}
              style={{ width: 120 }}
              placeholder="学科门类"
              options={Object.keys(curriculum).map(c => ({ value: c, label: c }))}
            />
            {category && (
              <Select
                value={categorySub}
                onChange={setCategorySub}
                style={{ width: 170 }}
                placeholder="一级学科"
                options={Object.keys(subCats).map(s => ({ value: s, label: s }))}
              />
            )}
            {lessonId && !done && (
              <Button danger size="small" icon={<StopOutlined />} onClick={end}>结束当前教学</Button>
            )}
          </Space>

          {topics.length > 0 && (
            <>
              <Space style={{ marginBottom: 8 }} size={12}>
                <Text type="secondary">学习进度</Text>
                <Progress
                  style={{ width: 180 }}
                  percent={Math.round((masteredCount / topics.length) * 100)}
                  size="small"
                  strokeColor="#52c41a"
                  format={() => `${masteredCount}/${topics.length} 已掌握`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>点知识点卡片右上角可标记「已掌握/待复习」</Text>
              </Space>
              <List
                size="small"
                grid={{ gutter: 12, column: 2 }}
                dataSource={topics}
                renderItem={(item: CurriculumItem) => {
                  const st = progress[item.topic]
                  return (
                    <List.Item>
                      <Card
                        size="small"
                        hoverable
                        onClick={() => !lessonId && start(item.topic, item.subject_key)}
                        style={{ cursor: lessonId && !done ? 'not-allowed' : 'pointer', opacity: lessonId && !done ? 0.5 : 1 }}
                      >
                        <Space direction="vertical" size={0} style={{ width: '100%' }}>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                            <Text strong>{item.topic}</Text>
                            {st && (
                              <Tag
                                color={st === 'mastered' ? 'success' : 'warning'}
                                style={{ margin: 0, cursor: 'pointer' }}
                                onClick={(e) => { e.stopPropagation(); toggleStatus(item.topic) }}
                              >
                                {st === 'mastered' ? '✅ 已掌握' : '🔁 待复习'}
                              </Tag>
                            )}
                          </Space>
                          <Text type="secondary" style={{ fontSize: 12 }}>{item.desc}</Text>
                        </Space>
                      </Card>
                    </List.Item>
                  )
                }}
              />
            </>
          )}

          <Divider plain style={{ margin: '8px 0' }}>或</Divider>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              placeholder="目录里没有？自己输入想学的知识点"
              value={manualTopic}
              onChange={e => setManualTopic(e.target.value)}
              onPressEnter={() => start(manualTopic)}
              disabled={!!lessonId && !done}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => start(manualTopic)}
              disabled={!!lessonId && !done}>
              开始教学
            </Button>
          </Space.Compact>
        </Space>
      </Card>

      {/* 教学区 */}
      {lessonId && (
        <>
          {done ? (
            <Card>
              <Paragraph style={{ textAlign: 'center', margin: '24px 0' }}>
                🎉 <Text strong>这一课就到这啦！</Text><br />
                <Text type="secondary">每次教学都会记录进你的学习动态，攒元气值哦。</Text>
              </Paragraph>
            </Card>
          ) : (
            <Card
              size="small"
              title={
                <Space>
                  <span>第 {round} / {maxRounds} 轮</span>
                  <Tag color="orange">{categorySub || category || '深度教学'}</Tag>
                </Space>
              }
            >
              <div style={{ background: '#fffbe6', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
                <Text strong><BulbOutlined style={{ color: '#faad14' }} /> 先听我讲</Text>
                <Paragraph style={{ margin: '8px 0 0 0', whiteSpace: 'pre-wrap' }}>{teach}</Paragraph>
              </div>

              <div style={{ background: '#f0f5ff', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
                <Text strong><CheckCircleOutlined style={{ color: '#1677ff' }} /> 考考你</Text>
                <Paragraph style={{ margin: '8px 0 0 0', whiteSpace: 'pre-wrap' }}>{question}</Paragraph>
              </div>

              {options.length > 0 ? (
                <Radio.Group
                  value={selected}
                  onChange={e => setSelected(e.target.value)}
                  disabled={!!verdict}
                  style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}
                >
                  {options.map((o, i) => (
                    <Radio key={i} value={i} style={{ whiteSpace: 'pre-wrap' }}>
                      {String.fromCharCode(65 + i)}. {o}
                    </Radio>
                  ))}
                </Radio.Group>
              ) : (
                <TextArea
                  rows={3}
                  placeholder="用你自己的话写下回答……"
                  value={answer}
                  onChange={e => setAnswer(e.target.value)}
                  disabled={!!verdict}
                  style={{ marginBottom: 8 }}
                />
              )}
              <Space>
                <Button type="primary" icon={<SendOutlined />} onClick={submit} loading={loading}
                  disabled={!!verdict}>
                  提交答案
                </Button>
                {verdict && (
                  <Button onClick={() => { setVerdict(null); setSelected(null) }}>下一题</Button>
                )}
              </Space>

              {verdict && (
                <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Tag color={verdict.correct ? 'success' : 'error'} icon={verdict.correct ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
                      {verdict.correct ? '答对啦！' : '还差一点'}
                    </Tag>
                    <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{verdict.comment}</Paragraph>
                  </Space>
                </div>
              )}
            </Card>
          )}

          <div style={{ marginTop: 12 }}>
            <Progress percent={Math.round((round / maxRounds) * 100)} showInfo={false}
              strokeColor={{ from: '#108ee9', to: '#87d068' }} />
          </div>
        </>
      )}
    </div>
  )
}
