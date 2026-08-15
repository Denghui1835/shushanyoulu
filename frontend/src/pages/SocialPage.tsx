import { useEffect, useState } from 'react'
import { Button, Tag, Spin, message, Empty, Space, Tooltip } from 'antd'
import { LikeOutlined, TrophyOutlined, FireOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '../api'
import PageHeader from '../components/PageHeader'

const KIND_META: Record<string, { label: string; color: string }> = {
  checkin: { label: '打卡', color: 'orange' },
  task: { label: '任务', color: 'green' },
  lesson: { label: '课程', color: 'purple' },
  mock: { label: '模拟', color: 'blue' },
}

const MEDALS = ['🥇', '🥈', '🥉']

export default function SocialPage() {
  const [feed, setFeed] = useState<any[]>([])
  const [board, setBoard] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [f, b] = await Promise.all([api.getSocialFeed(), api.getSocialLeaderboard()])
      setFeed(f?.items || [])
      setBoard(b?.items || [])
    } catch {
      message.error('加载社交动态失败，请确认后端已启动')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const like = async (post: any) => {
    try {
      const r = await api.likeSocialPost(post.id)
      setFeed(list => list.map(x => x.id === post.id
        ? { ...x, liked_by_me: r.liked, like_count: r.like_count } : x))
      if (r.liked) message.success(`已给「${post.username}」加油，元气 +1 ⚡`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  return (
    <div className="yq-page">
      <PageHeader
        icon={<span>🌱</span>}
        title="一起学"
        subtitle="打卡、任务、课程、模拟会自动生成动态——看看伙伴们在学什么，互相点赞加油"
      />

      {/* 本周学习榜 */}
      <div className="yq-section">
        <div className="yq-section-title"><TrophyOutlined /> 本周学习榜（近 7 天）</div>
        {board.length === 0 ? (
          <div className="yq-empty-state">
            <div className="yq-empty-icon">🏆</div>
            <p>榜单还是空的，去打卡、完成任务攒元气值上榜吧</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {board.slice(0, 5).map((u, i) => (
              <div key={u.user_id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
                  borderRadius: 12, background: i === 0 ? '#fffbe6' : i < 3 ? '#f6f5ff' : '#fafafa',
                  border: i === 0 ? '1px solid #ffe58f' : '1px solid #f0f0f0',
                }}
              >
                <span style={{ fontSize: 22, width: 34, textAlign: 'center' }}>
                  {i < 3 ? MEDALS[i] : <span style={{ color: '#999' }}>{i + 1}</span>}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <b>{u.name}</b>
                  {u.checkins > 0 && (
                    <Tag color="orange" style={{ marginLeft: 6 }}>
                      <FireOutlined /> {u.checkins} 天打卡
                    </Tag>
                  )}
                </div>
                <span style={{ fontWeight: 700, color: '#7c5cfc' }}>{u.points} ⚡</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 学习动态流 */}
      <div className="yq-section">
        <div className="yq-section-title"><span>💬</span> 学习动态</div>
        {feed.length === 0 ? (
          <div className="yq-empty-state">
            <div className="yq-empty-icon">🌱</div>
            <p>还没有学习动态。先去打个卡、完成任务或学一节课，进步会被记录下来</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {feed.map((p: any) => {
              const meta = KIND_META[p.kind] || { label: '学习', color: 'default' }
              return (
                <div key={p.id} style={{
                  display: 'flex', gap: 12, padding: '12px 14px',
                  border: '1px solid #f0f0f0', borderRadius: 12,
                  transition: 'box-shadow .2s', background: '#fff',
                }}>
                  <div style={{
                    width: 40, height: 40, flexShrink: 0, borderRadius: '50%',
                    background: '#f0edff', color: '#7c5cfc', fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17,
                  }}>
                    {(p.username || '学')[0]}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Space size={6} wrap style={{ marginBottom: 2 }}>
                      <b>{p.username}</b>
                      <Tag color={meta.color} style={{ marginInlineEnd: 0 }}>{meta.label}</Tag>
                      <span style={{ fontSize: 12, color: '#9aa1ad' }}>
                        {p.created_at ? dayjs(p.created_at).format('MM/DD HH:mm') : ''}
                      </span>
                      {p.points > 0 && <Tag color="gold">+{p.points} ⚡</Tag>}
                    </Space>
                    <div style={{ color: '#333', lineHeight: 1.6 }}>{p.content}</div>
                  </div>
                  <div style={{ flexShrink: 0 }}>
                    <Tooltip title={p.mine ? '不能给自己点赞哦' : (p.liked_by_me ? '取消鼓励' : '给 TA 加油')}>
                      <Button
                        size="small"
                        type={p.liked_by_me ? 'primary' : 'default'}
                        icon={<LikeOutlined />}
                        disabled={p.mine}
                        onClick={() => like(p)}
                      >
                        {p.like_count > 0 ? p.like_count : '鼓励'}
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
