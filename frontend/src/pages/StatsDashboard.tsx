import { useEffect, useState } from 'react'
import { Card, Col, Row, Spin, Statistic, Progress, Empty, Tag } from 'antd'
import {
  ThunderboltOutlined, FireOutlined, CheckCircleOutlined, TrophyOutlined,
  RiseOutlined, CalendarOutlined,
} from '@ant-design/icons'
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { api } from '../api'

interface DashboardData {
  overview: {
    total_learning_days: number
    monthly_learning_days: number
    streak: number
    total_quiz_count: number
    quiz_accuracy: number
    total_reviewed_cards: number
    recent_quiz_count: number
    recent_reviewed_cards: number
    total_points: number
  }
  charts: {
    daily_quiz: { date: string; count: number }[]
    daily_review: { date: string; count: number }[]
    daily_tasks: { date: string; count: number }[]
    points_curve: { date: string; daily: number; cumulative: number }[]
    accuracy_trend: { week: string; total: number; correct: number; accuracy: number }[]
  }
  weakness: { document_id: string; doc_title: string; wrong_count: number }[]
  activity_breakdown: { kind: string; label: string; count: number }[]
}

const COLORS = ['#7c5cfc', '#52c41a', '#1890ff', '#fa8c16', '#ff4d4f', '#722ed1']

export default function StatsDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => { load() }, [])

  const load = async () => {
    setLoading(true); setErr('')
    try {
      const d = await api.getDashboardStats()
      setData(d)
    } catch (e: any) {
      setErr(e?.message || '加载失败')
    } finally { setLoading(false) }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />
  if (err || !data) return (
    <div style={{ textAlign: 'center', padding: 80, color: '#999' }}>
      <h3>加载统计看板失败</h3>
      <p>{err || '暂无数据，开始学习后统计就会出现在这里'}</p>
    </div>
  )

  const { overview, charts, weakness, activity_breakdown } = data

  // Merge daily quiz + review into one dataset for stacked bar
  const dailyMerged = charts.daily_quiz.map((q, i) => ({
    date: q.date,
    做题: q.count,
    复习: charts.daily_review[i]?.count || 0,
    任务: charts.daily_tasks[i]?.count || 0,
  }))

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginTop: 0 }}>
        <RiseOutlined style={{ color: '#7c5cfc', marginRight: 8 }} />
        学习统计看板
        <span style={{ fontSize: 13, color: '#999', fontWeight: 400, marginLeft: 12 }}>
          近 4 周数据
        </span>
      </h2>

      {/* ── 概览卡片 ── */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="累计学习天数" value={overview.total_learning_days} prefix={<CalendarOutlined />} suffix="天" /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="连续打卡" value={overview.streak} prefix={<FireOutlined />} suffix="天" valueStyle={{ color: '#fa8c16' }} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="做题正确率" value={overview.quiz_accuracy} prefix={<CheckCircleOutlined />} suffix="%" valueStyle={{ color: overview.quiz_accuracy >= 60 ? '#52c41a' : '#ff4d4f' }} /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="总复习卡片" value={overview.total_reviewed_cards} prefix={<ThunderboltOutlined />} suffix="张" /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="本月打卡" value={overview.monthly_learning_days} prefix={<CalendarOutlined />} suffix="天" /></Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card size="small"><Statistic title="元气值" value={overview.total_points} prefix={<TrophyOutlined />} valueStyle={{ color: '#7c5cfc' }} /></Card>
        </Col>
      </Row>

      {/* ── 图表区 ── */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {/* 元气值累积曲线 */}
        <Col xs={24} lg={12}>
          <Card size="small" title="⚡ 元气值累积趋势">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={charts.points_curve}>
                <defs>
                  <linearGradient id="pointsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#7c5cfc" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#7c5cfc" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" fontSize={11} tick={{ fill: '#999' }} />
                <YAxis fontSize={11} tick={{ fill: '#999' }} />
                <Tooltip />
                <Area type="monotone" dataKey="cumulative" stroke="#7c5cfc" fill="url(#pointsGrad)" name="累积元气值" />
              </AreaChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        {/* 每日活动量 */}
        <Col xs={24} lg={12}>
          <Card size="small" title="📊 每日学习活动">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={dailyMerged}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" fontSize={10} tick={{ fill: '#999' }} />
                <YAxis fontSize={11} tick={{ fill: '#999' }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="做题" fill="#1890ff" radius={[2, 2, 0, 0]} />
                <Bar dataKey="复习" fill="#52c41a" radius={[2, 2, 0, 0]} />
                <Bar dataKey="任务" fill="#fa8c16" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {/* 正确率趋势 */}
        <Col xs={24} md={12}>
          <Card size="small" title="🎯 每周正确率">
            {charts.accuracy_trend.length === 0 ? (
              <Empty description="还没有做题记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={charts.accuracy_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="week" fontSize={10} tick={{ fill: '#999' }} />
                  <YAxis domain={[0, 100]} fontSize={11} tick={{ fill: '#999' }} unit="%" />
                  <Tooltip formatter={(v: any) => `${v}%`} />
                  <Line type="monotone" dataKey="accuracy" stroke="#7c5cfc" strokeWidth={2}
                    dot={{ r: 4 }} name="正确率" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>

        {/* 活动分布饼图 */}
        <Col xs={24} md={12}>
          <Card size="small" title="🍩 活动类型分布">
            {activity_breakdown.length === 0 ? (
              <Empty description="还没有活动记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={activity_breakdown} cx="50%" cy="50%" innerRadius={45} outerRadius={75}
                    dataKey="count" nameKey="label" label={({ label, count }: any) => `${label} ${count}`}>
                    {activity_breakdown.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
      </Row>

      {/* ── 薄弱点分析 ── */}
      {weakness.length > 0 && (
        <Card size="small" title="🔍 知识薄弱点（错题最多的资料）" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
            {weakness.map(w => (
              <div key={w.document_id} style={{
                background: '#fff7f0', border: '1px solid #ffd8bf',
                borderRadius: 8, padding: '10px 16px', minWidth: 180, flex: 1,
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{w.doc_title}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Tag color="red">{w.wrong_count} 道错题</Tag>
                  <Progress percent={Math.min(100, Math.round(w.wrong_count / Math.max(1, overview.total_quiz_count) * 100))}
                    size="small" style={{ flex: 1, marginBottom: 0 }}
                    strokeColor="#ff4d4f" showInfo={false} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
