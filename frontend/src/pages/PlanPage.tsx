import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Tag, Button, Timeline, Empty, message, Spin, Popconfirm, Result } from 'antd'
import { CheckOutlined, ThunderboltOutlined, ClockCircleOutlined, SyncOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '../api'

const TYPE_LABEL: Record<string, { text: string; color: string }> = {
  learn: { text: '学习', color: 'purple' },
  practice: { text: '练习', color: 'blue' },
  review: { text: '复习', color: 'orange' },
  chat: { text: '问答', color: 'green' },
}

export default function PlanPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<any>({ plan: null, tasks: [] })
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')

  const load = async () => {
    setLoading(true)
    setLoadErr('')
    try {
      const d = await api.getPlan()
      setData(d)
    } catch (e: any) {
      setLoadErr(e?.response?.data?.detail || e?.message || '加载失败')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const complete = async (task: any) => {
    await api.completeTask(task.id)
    message.success('任务完成，元气值 +5 ⚡')
    load()
  }

  const [adjusting, setAdjusting] = useState(false)
  const adjust = async () => {
    setAdjusting(true)
    try {
      await api.adjustPlan()
      message.success('计划已根据你的进度动态调整')
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '调整失败')
    } finally { setAdjusting(false) }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  if (loadErr) return (
    <Result status="error" title="加载失败" subTitle={loadErr}
      extra={<Button type="primary" onClick={load}>重试</Button>} />
  )

  const { plan, tasks } = data

  if (!plan) {
    return (
      <div className="page-card" style={{ textAlign: 'center', padding: 60 }}>
        <ThunderboltOutlined style={{ fontSize: 56, color: '#7c5cfc' }} />
        <h2 style={{ marginTop: 16 }}>还没有学习计划</h2>
        <p style={{ color: '#999' }}>
          去「伴学首页」告诉书山有路你的目标，它就会为你量身制定一份学习计划
        </p>
        <Button type="primary" onClick={() => navigate('/')}>去制定计划</Button>
      </div>
    )
  }

  const doneCount = tasks.filter((t: any) => t.status === 'done').length
  const today = dayjs().format('YYYY-MM-DD')

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="page-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <h2 style={{ margin: 0 }}>{plan.title}</h2>
            <p style={{ color: '#666', marginTop: 8 }}>{plan.summary}</p>
          </div>
          <Tag color="purple">{plan.status === 'active' ? '进行中' : plan.status}</Tag>
        </div>
        <div style={{ marginTop: 12, color: '#999', fontSize: 13 }}>
          共 {plan.total_days} 天 · 已完成 {doneCount}/{tasks.length} 项任务
        </div>
        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button type="primary" size="small" icon={<ThunderboltOutlined />}
            onClick={() => navigate('/plan/wizard')}>
            ✨ AI 一键生成计划表
          </Button>
          <Popconfirm title="按当前进度重排剩余学习安排？已掌握的内容会压缩，薄弱点会补上" onConfirm={adjust}>
            <Button size="small" icon={<SyncOutlined />} loading={adjusting}>按进度调整计划</Button>
          </Popconfirm>
        </div>
      </div>

      <div className="page-card">
        <h3 style={{ marginTop: 0 }}>每日任务</h3>
        <Timeline
          items={tasks.map((t: any) => {
            const type = TYPE_LABEL[t.type] || { text: t.type, color: 'default' }
            const isToday = t.scheduled_date === today
            const done = t.status === 'done'
            return {
              color: done ? 'green' : isToday ? 'purple' : 'gray',
              dot: done ? <CheckOutlined style={{ color: '#52c41a' }} /> : <ClockCircleOutlined />,
              children: (
                <div style={{ paddingBottom: 8 }}>
                  <Space2 t={t} type={type} isToday={isToday} done={done} onComplete={() => complete(t)} />
                </div>
              ),
            }
          })}
        />
      </div>
    </div>
  )
}

function Space2({ t, type, isToday, done, onComplete }: any) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
      <div>
        <Tag color={done ? 'green' : type.color}>
          {type.text}
          {isToday && !done && ' · 今天'}
        </Tag>
        <b>{t.title}</b>
        {t.description && (
          <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>{t.description}</div>
        )}
      </div>
      {!done && (
        <Button size="small" icon={<CheckOutlined />} onClick={onComplete}>完成</Button>
      )}
    </div>
  )
}
