import { useEffect, useRef, useState } from 'react'
import {
  Input, Button, Space, Card, Tag, Progress, Modal, Form, InputNumber, message, Spin, Tooltip,
} from 'antd'
import {
  SendOutlined, ThunderboltOutlined, CalendarOutlined, CheckOutlined, PlusOutlined, FireOutlined, RightOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate } from 'react-router-dom'
import { api, streamSSE } from '../api'
import PageHeader from '../components/PageHeader'

type Msg = { id: string; role: string; content: string; streaming?: boolean }

export default function CompanionPage({ onActivity }: { onActivity?: () => void }) {
  const navigate = useNavigate()
  const [sessionId, setSessionId] = useState('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState<any>(null)
  const [checkin, setCheckin] = useState<any>(null)
  const [loadError, setLoadError] = useState(false)
  const [dataReady, setDataReady] = useState(false)  // 区分"加载中"与"数据为空"
  const [planOpen, setPlanOpen] = useState(false)
  const [ctx, setCtx] = useState<any>(null)
  const [planning, setPlanning] = useState(false)
  const [profileForm] = Form.useForm()
  const bodyRef = useRef<HTMLDivElement>(null)
  const sendingRef = useRef(false)

  const loadStatus = async () => {
    try {
      const s = await api.getStatus()
      setStatus(s)
      setLoadError(false)
      profileForm.setFieldsValue({
        goal: s.user?.goal,
        goal_detail: s.user?.goal_detail,
        daily_minutes: s.user?.daily_minutes,
      })
      if (!s.user?.onboarded) setPlanOpen(true)
      const c = await api.getCheckin()
      setCheckin(c)
    } catch {
      setLoadError(true)
    }
  }

  useEffect(() => {
    api.getStudyContext().then(r => setCtx(r?.context || null)).catch(() => {})
  }, [])

  const doCheckin = async () => {
    try {
      const r = await api.doCheckin()
      setCheckin(r)
      message.success(`打卡成功！连续 ${r.streak} 天，元气值 +${r.points_gained} ⚡`)
      onActivity?.()
      loadStatus()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '打卡失败')
    }
  }

  const init = async () => {
    const s = await api.getSession()
    setSessionId(s.id)
    const msgs = await api.getMessages(s.id)
    if (msgs.length === 0) {
      setMessages([{
        id: 'greeting', role: 'assistant',
        content: '你好呀！我是**小书虫** 🐛 我会陪你一起学习、练习、复习，还会主动提醒你该做什么。\n\n我们先互相认识一下：你最近想攻克什么目标？每天大概能投入多少时间？把学习资料上传后，我就能为你量身制定学习计划啦。',
      }])
    } else {
      setMessages(msgs)
    }
    await loadStatus()
    setDataReady(true)
  }

  useEffect(() => { init() }, [])
  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight }) }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || sending || !sessionId) return
    setInput('')
    const assistantId = `a${Date.now()}`
    const userMsg: Msg = { id: `u${Date.now()}`, role: 'user', content: text }
    setMessages(m => [...m, userMsg, { id: assistantId, role: 'assistant', content: '', streaming: true }])
    setSending(true)
    sendingRef.current = true
    try {
      for await (const delta of streamSSE('/api/companion/chat', { session_id: sessionId, message: text })) {
        setMessages(m => m.map(x =>
          x.id === assistantId ? { ...x, content: x.content + delta } : x))
      }
    } catch (e: any) {
      setMessages(m => m.map(x =>
        x.id === assistantId ? { ...x, content: `⚠️ ${e.message}`, streaming: false } : x))
    } finally {
      setSending(false)
      sendingRef.current = false
      // remove streaming marker on last assistant message
      setMessages(m => m.map(x => (x as any).streaming ? { ...x, streaming: false } : x))
      onActivity?.()
      loadStatus()
    }
  }

  const createPlan = async () => {
    const values = await profileForm.validateFields()
    setPlanning(true)
    try {
      await api.saveProfile(values)
      const res = await api.createPlan(values)
      message.success(`计划「${res.plan.title}」已生成，快去看看今天要做什么！`)
      setPlanOpen(false)
      onActivity?.()
      loadStatus()
      const s = await api.getStatus()
      setStatus(s)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '计划生成失败')
    } finally {
      setPlanning(false)
    }
  }

  const completeTask = async (taskId: string) => {
    await api.completeTask(taskId)
    message.success('任务完成，元气值 +5 ⚡')
    onActivity?.()
    loadStatus()
  }

  if (!dataReady) return <Spin style={{ display: 'block', marginTop: 120 }} size="large" />

  if (loadError) return (
    <div style={{ maxWidth: 400, margin: '80px auto', textAlign: 'center' }}>
      <h3>⚠️ 无法连接到后端</h3>
      <p style={{ color: '#999' }}>请确认后端服务已启动（start.bat），然后重试</p>
      <Button type="primary" onClick={() => { setLoadError(false); setDataReady(false); init() }}>重新加载</Button>
    </div>
  )

  if (!status) return <Spin style={{ display: 'block', marginTop: 120 }} size="large" />

  const todayTasks = status.today_tasks || []
  const plan = status.plan

  return (
    <div className="yq-page">
      <PageHeader
        icon={<span>🐛</span>}
        title="伴学首页"
        subtitle={
          status.user?.goal
            ? `当前目标：${status.user.goal}${status.plan ? ` · ${status.plan.progress?.done ?? 0}/${status.plan.progress?.total ?? 0} 天` : ''}`
            : '告诉小书虫你的学习目标，一起制定专属计划'
        }
        extra={
          <>
            <span style={{ color: '#fa8c16', fontSize: 13, whiteSpace: 'nowrap' }}>
              🔥 连续打卡 {dataReady ? (checkin?.streak ?? 0) : '…'} 天
            </span>
            <Button
              type={checkin?.checked_today ? 'default' : 'primary'}
              icon={<FireOutlined />}
              disabled={checkin?.checked_today}
              onClick={doCheckin}
            >
              {checkin?.checked_today ? '已打卡' : '今日打卡'}
            </Button>
            <Tooltip title={!status.user?.goal ? '请先在下方对话中告诉小书虫你的学习目标' : (plan ? '重新生成学习计划' : '根据目标生成个性化学习计划')}>
              <Button
                type="primary" ghost icon={<ThunderboltOutlined />}
                disabled={!status.user?.goal} onClick={() => setPlanOpen(true)}
              >
                {plan ? '重新制定计划' : '生成学习计划'}
              </Button>
            </Tooltip>
          </>
        }
      />

      {/* 继续学习 */}
      {ctx && (
        <div className="yq-section" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 26 }}>🚀</span>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontWeight: 600 }}>继续学习</div>
            <div style={{ color: '#999', fontSize: 13, marginTop: 2 }}>
              {ctx.topic
                ? `${ctx.subject || ''} · ${ctx.topic}`
                : ctx.project_title || '上次学到的位置'}
            </div>
          </div>
          <Button
            type="primary" icon={<RightOutlined />}
            onClick={() => navigate(
              ctx.project_id
                ? `/project/${ctx.project_id}`
                : ctx.subject ? `/course?subject=${encodeURIComponent(ctx.subject)}` : '/bookshelf',
            )}
          >
            继续
          </Button>
        </div>
      )}

      {/* 状态卡片 */}
      <div className="yq-status-grid">
        <div className="yq-stat-card">
          <div className="num">{plan ? `${plan.progress?.done ?? 0}/${plan.progress?.total ?? 0}` : '—'}</div>
          <div className="label">计划进度</div>
        </div>
        <div className="yq-stat-card">
          <div className="num" style={{ color: status.due_cards_count ? '#ff6b6b' : '#7c5cfc' }}>
            {status.due_cards_count}
          </div>
          <div className="label">待复习闪卡</div>
        </div>
        <div className="yq-stat-card">
          <div className="num">⚡{status.points}</div>
          <div className="label">累计元气值</div>
        </div>
        <div className="yq-stat-card">
          <div className="num">{todayTasks.length}</div>
          <div className="label">今日任务</div>
        </div>
      </div>

      {/* 今日任务快捷操作 */}
      {todayTasks.length > 0 && (
        <div className="yq-section">
          <Space direction="vertical" style={{ width: '100%' }}>
            <div className="yq-section-title">
              <CalendarOutlined />
              <span>今日任务</span>
              {plan && <Tag color="purple" style={{ marginLeft: 4 }}>{plan.title}</Tag>}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {todayTasks.map((t: any) => (
                <Tag
                  key={t.title + t.status}
                  color={t.status === 'done' ? 'green' : t.type === 'review' ? 'orange' : t.type === 'practice' ? 'blue' : 'purple'}
                  style={{ padding: '4px 10px', fontSize: 13 }}
                  closable={t.status !== 'done'}
                  closeIcon={<CheckOutlined />}
                  onClose={() => completeTask(t.id || t.title)}
                >
                  {t.status === 'done' ? '✅' : ''} {t.title}
                </Tag>
              ))}
            </div>
          </Space>
        </div>
      )}

      {/* 对话区 */}
      <div className="yq-chat">
        <div className="yq-chat-header">
          <span style={{ fontSize: 22 }}>🐛</span>
          <div>
            <b>小书虫</b>
            <div style={{ fontSize: 12, color: '#999' }}>
              {status.user?.goal ? `目标：${status.user.goal}` : '先聊聊你的学习目标吧'}
            </div>
          </div>
        </div>

        <div className="yq-chat-body" ref={bodyRef}>
          {messages.map((m: any) => (
            <div key={m.id} className={`yq-msg ${m.role}`}>
              <div className="avatar">{m.role === 'user' ? '🙂' : '🐛'}</div>
              <div className="bubble">
                {m.content ? (
                  <div className="yq-md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  <Spin size="small" />
                )}
                {m.streaming && m.content && <span style={{ marginLeft: 4 }}>▍</span>}
              </div>
            </div>
          ))}
        </div>

        <div className="yq-chat-input">
          <Input
            size="large"
            placeholder="告诉小书虫你想学什么，或问任何问题…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onPressEnter={send}
            disabled={sending}
          />
          <Button
            type="primary" size="large" icon={<SendOutlined />}
            onClick={send} loading={sending} disabled={!input.trim()}
          >
            发送
          </Button>
          <div style={{ fontSize: 11, color: '#bbb', textAlign: 'right', marginTop: 3 }}>Enter 发送 · Shift+Enter 换行</div>
        </div>
      </div>

      {/* 引导弹窗 */}
      <Modal
        title={<Space><ThunderboltOutlined style={{ color: '#7c5cfc' }} />认识一下，好为你定制学习计划</Space>}
        open={planOpen}
        onOk={createPlan}
        confirmLoading={planning}
        onCancel={() => setPlanOpen(false)}
        okText="生成学习计划"
        cancelText="先聊聊"
      >
        <Form form={profileForm} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="goal" label="学习目标" rules={[{ required: true, message: '请填写你的学习目标' }]}>
            <Input placeholder="例如：考取高中数学教师资格证" />
          </Form.Item>
          <Form.Item name="goal_detail" label="目标详情（可选）">
            <Input placeholder="例如：科目二教育知识与能力，9月考试" />
          </Form.Item>
          <Form.Item name="daily_minutes" label="每天能投入多少时间（分钟）？">
            <InputNumber min={5} max={600} style={{ width: '100%' }} placeholder="例如 45" />
          </Form.Item>
          <div style={{ color: '#999', fontSize: 12 }}>
            <PlusOutlined /> 提示：先去「资料库」上传学习资料，计划会更贴合你的内容
          </div>
        </Form>
      </Modal>
    </div>
  )
}
