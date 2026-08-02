import { useEffect, useState } from 'react'
import { Card, Button, Tag, Empty, Spin, message, Space, Input, Tabs, Popconfirm } from 'antd'
import { GlobalOutlined, DownloadOutlined, LogoutOutlined, CheckCircleOutlined, UndoOutlined, UserOutlined } from '@ant-design/icons'
import { api, setAuthToken, getAuthToken } from '../api'

interface PlazaItem {
  id: string
  title: string
  description?: string
  icon?: string
  author?: string
  chapter_count: number
}

/** 作品社区：登录/注册 → 广场浏览 + 我的项目发布（往智谱「公开项目广场」靠拢）。 */
export default function CommunityPage() {
  const [me, setMe] = useState<any>(null)          // {user, projects}
  const [plaza, setPlaza] = useState<PlazaItem[]>([])
  const [loading, setLoading] = useState(true)
  const [learnBusy, setLearnBusy] = useState<Record<string, boolean>>({})
  const [pubBusy, setPubBusy] = useState<Record<string, boolean>>({})

  const loadAll = async () => {
    setLoading(true)
    try {
      const p = await api.getPlaza()
      setPlaza(p.items || [])
      if (getAuthToken()) {
        const m = await api.me().catch(() => { setAuthToken(''); return null })
        setMe(m)
      } else {
        setMe(null)
      }
    } finally { setLoading(false) }
  }
  useEffect(() => { loadAll() }, [])

  const doLogout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    setAuthToken('')
    setMe(null)
    setPlaza([])
    message.success('已退出登录')
  }

  const learn = async (id: string) => {
    setLearnBusy(s => ({ ...s, [id]: true }))
    try {
      const r = await api.learnProject(id)
      message.success(`已把「${r.title}」学习到你的书架！`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '学习失败')
    } finally { setLearnBusy(s => ({ ...s, [id]: false })) }
  }

  const togglePublish = async (p: any) => {
    setPubBusy(s => ({ ...s, [p.id]: true }))
    try {
      if (p.is_public) await api.unpublishProject(p.id)
      else await api.publishProject(p.id)
      message.success(p.is_public ? '已取消发布（转为私有）' : '已发布到广场！')
      setMe(await api.me())
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    } finally { setPubBusy(s => ({ ...s, [p.id]: false })) }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  if (!me) return <AuthForm onSuccess={loadAll} />

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* 头部 + 用户 */}
      <div className="page-card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <GlobalOutlined style={{ fontSize: 26, color: '#7c5cfc' }} />
        <div>
          <h2 style={{ margin: 0 }}>作品社区</h2>
          <div style={{ color: '#999', fontSize: 13 }}>
            浏览广场项目，一键学习到你的书架；也能发布自己的项目
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag color="purple"><UserOutlined /> {me.user?.username}</Tag>
          <Button size="small" icon={<LogoutOutlined />} onClick={doLogout}>退出</Button>
        </div>
      </div>

      {/* 我的项目（发布/取消发布） */}
      <div className="page-card" style={{ marginTop: 12 }}>
        <b>📦 我的项目</b>
        <div style={{ color: '#999', fontSize: 12, marginTop: 2 }}>
          发布后其他用户能在广场看到并一键学习
        </div>
        {me.projects?.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="你还没有项目（第一个注册的账号会自动拥有本地书架）" />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12, marginTop: 10 }}>
            {me.projects.map((p: any) => (
              <Card key={p.id} size="small" className="yq-book-card">
                <span style={{ fontSize: 28 }}>{p.icon || '📦'}</span>
                <b>{p.title}</b>
                <div style={{ color: '#666', fontSize: 12, minHeight: 36 }}>{p.description || '—'}</div>
                <Space style={{ marginTop: 6 }}>
                  {p.is_public
                    ? <Tag color="green"><CheckCircleOutlined /> 已公开</Tag>
                    : <Tag>私有</Tag>}
                  {p.is_public ? (
                    <Popconfirm title="取消发布，转为私有？" onConfirm={() => togglePublish(p)}>
                      <Button size="small" icon={<UndoOutlined />} loading={!!pubBusy[p.id]}>取消发布</Button>
                    </Popconfirm>
                  ) : (
                    <Button size="small" type="primary" icon={<CheckCircleOutlined />} loading={!!pubBusy[p.id]} onClick={() => togglePublish(p)}>
                      发布到广场
                    </Button>
                  )}
                </Space>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* 广场 */}
      <div className="page-card" style={{ marginTop: 12 }}>
        <b>🌐 广场 · 大家都在学</b>
        <div style={{ color: '#999', fontSize: 12, marginTop: 2 }}>点「一键学习」会复制一份到你的书架</div>
        {plaza.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="广场还没有公开项目，发布第一个吧" />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12, marginTop: 10 }}>
            {plaza.map(item => (
              <Card key={item.id} size="small" className="yq-book-card">
                <span style={{ fontSize: 28 }}>{item.icon || '📦'}</span>
                <b>{item.title}</b>
                <div style={{ color: '#666', fontSize: 12, minHeight: 36 }}>{item.description || '—'}</div>
                <Space style={{ marginTop: 6 }}>
                  <Tag color="purple">{item.author}</Tag>
                  <Tag>{item.chapter_count} 章</Tag>
                </Space>
                <div style={{ marginTop: 8 }}>
                  <Button type="primary" size="small" icon={<DownloadOutlined />}
                    loading={!!learnBusy[item.id]} onClick={() => learn(item.id)}>
                    一键学习
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- 登录 / 注册

function AuthForm({ onSuccess }: { onSuccess: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (username.trim().length < 2) { message.warning('用户名至少 2 个字符'); return }
    if (password.length < 6) { message.warning('密码至少 6 位'); return }
    setBusy(true)
    try {
      const r = mode === 'login'
        ? await api.login(username.trim(), password)
        : await api.register(username.trim(), password)
      setAuthToken(r.token)
      message.success(mode === 'login' ? '登录成功' : '注册成功！第一个账号已成为社区主人，继承了本地数据')
      onSuccess()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    } finally { setBusy(false) }
  }

  return (
    <div style={{ maxWidth: 420, margin: '80px auto' }}>
      <div className="page-card">
        <div style={{ textAlign: 'center', marginBottom: 12 }}>
          <GlobalOutlined style={{ fontSize: 40, color: '#7c5cfc' }} />
          <h2 style={{ margin: '8px 0 0' }}>作品社区</h2>
          <div style={{ color: '#999', fontSize: 13 }}>登录后发布项目、浏览广场、一键学习</div>
        </div>
        <Tabs
          activeKey={mode} onChange={v => setMode(v as 'login' | 'register')}
          centered items={[
            { key: 'login', label: '登录' },
            { key: 'register', label: '注册' },
          ]}
        />
        {mode === 'register' && (
          <div style={{ background: '#f4f0ff', borderRadius: 6, padding: '6px 10px', fontSize: 12, color: '#8c6ff0', marginBottom: 10 }}>
            第一个注册的账号会成为社区主人，自动继承本地现有的书架数据。
          </div>
        )}
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="用户名" value={username} onChange={e => setUsername(e.target.value)}
            onPressEnter={submit} size="large" />
          <Input.Password placeholder="密码（至少 6 位）" value={password}
            onChange={e => setPassword(e.target.value)} onPressEnter={submit} size="large" />
          <Button type="primary" block size="large" loading={busy} onClick={submit}>
            {mode === 'login' ? '登录' : '注册并进入'}
          </Button>
        </Space>
      </div>
    </div>
  )
}
