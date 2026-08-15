import { useEffect, useState } from 'react'
import {
  Card, Tag, Button, message, Space, Typography, Spin, Empty, Input, List, Divider, Popconfirm,
} from 'antd'
import {
  StarOutlined, ForkOutlined, ReadOutlined, FileTextOutlined, UserOutlined,
  MessageOutlined, CheckOutlined, CloseOutlined, ArrowLeftOutlined, RocketOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { api, getAuthToken } from '../api'

const { Title, Paragraph, Text } = Typography

interface Suggestion { id: string; username: string; content: string; status: string; created_at: string }
interface Chapter { id: string; title: string }
interface Course {
  id: string; title: string; description?: string; icon?: string; subject?: string
  category?: string; category_sub?: string; category_label?: string
  author?: string; chapter_count: number; learn_count?: number; star_count?: number; fork_count?: number
}

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  open: { text: '待处理', color: 'orange' },
  accepted: { text: '已采纳', color: 'blue' },
  applied: { text: '已应用', color: 'green' },
  rejected: { text: '已拒绝', color: 'default' },
}

export default function CourseDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const loggedIn = !!getAuthToken()

  const [course, setCourse] = useState<Course | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [sugInput, setSugInput] = useState('')
  const [starred, setStarred] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const d = await api.getPlazaDetail(id!)
      setCourse(d.course)
      setChapters(d.chapters || [])
      setSuggestions(d.suggestions || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '课程不存在')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [id])

  const needLogin = () => {
    if (!loggedIn) { message.warning('请先登录再操作'); return true }
    return false
  }

  const toggleStar = async () => {
    if (needLogin()) return
    setBusy(true)
    try {
      const r = starred ? await api.unstarProject(id!) : await api.starProject(id!)
      setStarred(!starred)
      setCourse(c => c ? { ...c, star_count: (c.star_count || 0) + (starred ? -1 : 1) } : c)
      message.success(starred ? '已取消收藏' : '⭐ 收藏成功！')
    } catch (e: any) { message.error(e?.response?.data?.detail || '操作失败') }
    finally { setBusy(false) }
  }

  const doFork = async () => {
    if (needLogin()) return
    setBusy(true)
    try {
      const r = await api.forkProject(id!)
      setCourse(c => c ? { ...c, fork_count: (c.fork_count || 0) + 1 } : c)
      message.success(`已 Fork「${r.title}」到你的书架！`)
      navigate('/bookshelf')
    } catch (e: any) { message.error(e?.response?.data?.detail || 'Fork 失败') }
    finally { setBusy(false) }
  }

  const doLearn = async () => {
    if (needLogin()) return
    setBusy(true)
    try {
      const r = await api.learnProject(id!)
      setCourse(c => c ? { ...c, learn_count: (c.learn_count || 0) + 1 } : c)
      message.success(`「${r.title}」已加入你的书架，去学习吧！`)
      navigate('/bookshelf')
    } catch (e: any) { message.error(e?.response?.data?.detail || '学习失败') }
    finally { setBusy(false) }
  }

  const submitSug = async () => {
    if (needLogin()) return
    if (!sugInput.trim()) { message.warning('写下你的建议吧'); return }
    setBusy(true)
    try {
      await api.createSuggestion(id!, sugInput.trim())
      setSugInput('')
      message.success('建议已提交，等作者处理～')
      load()
    } catch (e: any) { message.error(e?.response?.data?.detail || '提交失败') }
    finally { setBusy(false) }
  }

  const actSug = async (sid: string, kind: 'accept' | 'apply' | 'reject') => {
    try {
      const fn = kind === 'accept' ? api.acceptSuggestion : kind === 'apply' ? api.applySuggestion : api.rejectSuggestion
      await fn(id!, sid)
      message.success(kind === 'accept' ? '已采纳' : kind === 'apply' ? '已标记应用' : '已拒绝')
      load()
    } catch (e: any) { message.error(e?.response?.data?.detail || '操作失败（仅作者可操作）') }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
  if (!course) return (
    <div className="yq-page">
      <div className="yq-section yq-empty-state">
        <div className="yq-empty-icon">📕</div>
        <p>课程不存在或已被删除</p>
        <Button onClick={() => navigate('/community')}>返回社区广场</Button>
      </div>
    </div>
  )

  return (
    <div className="yq-page">
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/community')} style={{ marginBottom: 12 }}>返回广场</Button>

      {/* 封面 + 信息 */}
      <Card style={{ borderRadius: 12, overflow: 'hidden' }} styles={{ body: { padding: 0 } }}>
        <div style={{
          background: `linear-gradient(135deg,#667eea 0%,#764ba2 100%)`,
          height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 60,
        }}>{course.icon || '📘'}</div>
        <div style={{ padding: 20 }}>
          <Title level={3} style={{ margin: '0 0 4px' }}>{course.title}</Title>
          <Space size={8} wrap style={{ marginBottom: 10 }}>
            <Tag color="geekblue">{course.category_label || course.subject || '未分类'}</Tag>
            <Text type="secondary"><UserOutlined /> {course.author || '匿名'}</Text>
            <Text type="secondary"><FileTextOutlined /> {course.chapter_count} 章</Text>
          </Space>
          <Paragraph style={{ color: '#555' }}>{course.description || '暂无简介'}</Paragraph>

          {/* 操作区（GitHub 式） */}
          <Space wrap>
            <Button icon={<ReadOutlined />} type="primary" onClick={doLearn} loading={busy}>
              开始学习
            </Button>
            <Button icon={<StarOutlined />} onClick={toggleStar} loading={busy}
              type={starred ? 'primary' : 'default'}>
              {starred ? '已收藏' : '收藏'} {course.star_count || 0}
            </Button>
            <Popconfirm title="Fork 一份到你的空间？可自由修改" onConfirm={doFork}>
              <Button icon={<ForkOutlined />} loading={busy}>Fork {course.fork_count || 0}</Button>
            </Popconfirm>
          </Space>

          {/* 统计条 */}
          <div style={{ marginTop: 12, display: 'flex', gap: 16, color: '#888', fontSize: 13 }}>
            <span>📖 学习 {course.learn_count || 0} 人</span>
            <span>⭐ 收藏 {course.star_count || 0}</span>
            <span>🍴 Fork {course.fork_count || 0}</span>
          </div>
        </div>
      </Card>

      {/* 章节/知识点 */}
      <Card size="small" title={`📚 内容（${chapters.length} 章）`} style={{ marginTop: 16 }}>
        {chapters.length === 0 ? <Text type="secondary">作者还没添加章节内容</Text> : (
          <List size="small" dataSource={chapters} renderItem={(c, i) => (
            <List.Item><Text>{i + 1}. {c.title}</Text></List.Item>
          )} />
        )}
      </Card>

      {/* 修改建议（GitHub PR/issue 式） */}
      <Card size="small" title={<span><MessageOutlined /> 修改建议（{suggestions.length}）</span>}
        style={{ marginTop: 16 }} extra={
          <Text type="secondary" style={{ fontSize: 12 }}>像 GitHub 一样，给这门课提改进建议</Text>
        }>
        <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
          <Input
            placeholder="对这门课有什么改进建议？比如：某章讲得不清楚、希望补充例子……"
            value={sugInput}
            onChange={e => setSugInput(e.target.value)}
            onPressEnter={submitSug}
            disabled={busy}
          />
          <Button type="primary" icon={<MessageOutlined />} onClick={submitSug} loading={busy}>提建议</Button>
        </Space.Compact>

        {suggestions.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有建议，来当第一个提建议的人吧" />
        ) : (
          <List size="small" dataSource={suggestions} renderItem={s => {
            const st = STATUS_LABEL[s.status] || STATUS_LABEL.open
            return (
              <List.Item actions={[
                s.status === 'open' && (
                  <Space size={4} key="ops">
                    <Popconfirm title="采纳该建议？" onConfirm={() => actSug(s.id, 'accept')}>
                      <Button size="small" type="text" icon={<CheckOutlined />}>采纳</Button>
                    </Popconfirm>
                    <Button size="small" type="text" icon={<RocketOutlined />} onClick={() => actSug(s.id, 'apply')}>已应用</Button>
                    <Popconfirm title="拒绝该建议？" onConfirm={() => actSug(s.id, 'reject')}>
                      <Button size="small" type="text" icon={<CloseOutlined />}>拒绝</Button>
                    </Popconfirm>
                  </Space>
                ),
              ]}>
                <List.Item.Meta
                  title={<Space><Text strong>{s.username}</Text><Tag color={st.color}>{st.text}</Tag></Space>}
                  description={s.content}
                />
              </List.Item>
            )
          }} />
        )}
      </Card>
    </div>
  )
}
