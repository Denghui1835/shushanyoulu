import { useEffect, useMemo, useState } from 'react'
import {
  Card, Avatar, Button, Form, Input, InputNumber, Tag, Space, message, Spin, Popconfirm, Alert, Result,
} from 'antd'
import { UserOutlined, ApiOutlined, LogoutOutlined, WechatOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, setAuthToken, getAuthToken } from '../api'
import ProviderConfigCard from '../components/ProviderConfigCard'

/** HTTP 方法的配色（接口清单用）。 */
const METHOD_COLOR: Record<string, string> = {
  GET: 'green', POST: 'blue', PUT: 'orange', PATCH: 'gold', DELETE: 'red',
}

/** 个人中心：资料 + 统计 + 自有 API Key + API 接口总览 + 微信绑定 + 退出登录。 */
export default function ProfilePage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  // 服务商配置（按能力分档：文本 / 视觉 / 语音）
  const [presets, setPresets] = useState<any>({})
  const [capLabels, setCapLabels] = useState<any>({})
  const [providerConfigs, setProviderConfigs] = useState<any>(null)
  // API 接口总览（本服务对外提供了哪些 HTTP 接口）
  const [routeGroups, setRouteGroups] = useState<any[]>([])
  const [routeTotal, setRouteTotal] = useState(0)
  const [routeQ, setRouteQ] = useState('')
  const navigate = useNavigate()

  const loadProviders = async () => {
    try {
      setProviderConfigs(await api.getProviderConfigs())
    } catch { /* 拿不到不该让整页挂掉 */ }
  }

  const load = async () => {
    if (!getAuthToken()) { setLoading(false); return }
    setLoading(true)
    try {
      const p = await api.getProfileInfo()
      setData(p)
      form.setFieldsValue({
        name: p.user.name, goal: p.user.goal, goal_detail: p.user.goal_detail,
        daily_minutes: p.user.daily_minutes,
      })
      try {
        const pre = await api.getProviderPresets()
        setPresets(pre.capabilities || {})
        setCapLabels(pre.labels || {})
      } catch { /* 忽略 */ }
      await loadProviders()
      // 接口总览单独兜错：拿不到它不该让整个设置页变成「加载失败」
      try {
        const rt = await api.getApiRoutes()
        setRouteGroups(rt.groups || [])
        setRouteTotal(rt.total || 0)
      } catch { /* 忽略 */ }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载失败')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const save = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try { await api.updateProfileInfo(v); message.success('已保存'); load() }
    catch (e: any) { message.error(e?.response?.data?.detail || '保存失败') }
    finally { setSaving(false) }
  }

  const logout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    setAuthToken('')
    setData(null)
    message.success('已退出登录')
    navigate('/')
  }

  // 按关键词过滤接口（方法 / 路径 / 说明都能搜），过滤后为空的组不显示。
  // 必须放在下面那几个 return 之前——hook 不能有条件地调用。
  const shownGroups = useMemo(() => {
    const q = routeQ.trim().toLowerCase()
    if (!q) return routeGroups
    return routeGroups
      .map(g => ({
        ...g,
        routes: (g.routes || []).filter((r: any) =>
          `${r.method} ${r.path} ${r.summary}`.toLowerCase().includes(q)),
      }))
      .filter(g => g.routes.length)
  }, [routeGroups, routeQ])
  const shownCount = shownGroups.reduce((a: number, g: any) => a + g.routes.length, 0)

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  if (!getAuthToken()) {
    return (
      <div className="yq-page">
        <div className="yq-section yq-empty-state">
          <UserOutlined style={{ fontSize: 48, color: '#7c5cfc' }} />
          <h3 style={{ marginTop: 12 }}>登录后才能查看个人中心</h3>
          <p style={{ color: '#999' }}>第一个注册的账号会成为主人，继承现有的全部书架与数据</p>
          <Button type="primary" onClick={() => navigate('/login')}>去登录 / 注册</Button>
        </div>
      </div>
    )
  }

  if (!data) {
    return <Result status="warning" title="加载失败" subTitle="服务器暂时无响应，请稍后重试"
      extra={<Button type="primary" onClick={() => { setLoading(true); load() }}>重试</Button>} />
  }

  const s = data.stats || {}

  return (
    <div className="yq-page">
      {/* 头像 + 基本信息 */}
      <div className="yq-section" style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <Avatar size={72} style={{ background: '#7c5cfc', fontSize: 32 }}>
          {(data.user.name || '书')[0]}
        </Avatar>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0 }}>{data.user.name}</h2>
          <Space style={{ marginTop: 6 }} wrap>
            <Tag color="purple">@{data.user.username || '本地用户'}</Tag>
            <Tag color={data.user.wechat_bound ? 'green' : 'default'}>
              {data.user.login_method === 'wechat' ? '微信登录' : data.user.wechat_bound ? '已绑定微信' : '用户名密码'}
            </Tag>
            {data.user.providers_configured?.text && (
              <Tag color="blue"><ApiOutlined /> 已配置自有文本模型</Tag>
            )}
            {data.user.providers_configured?.tts && (
              <Tag color="purple">已配置自有语音</Tag>
            )}
          </Space>
          <div style={{ color: '#666', marginTop: 6 }}>
            {data.user.goal ? `目标：${data.user.goal}` : '还没有学习目标'}
          </div>
        </div>
        <Button icon={<LogoutOutlined />} onClick={logout}>退出登录</Button>
      </div>

      {/* 统计卡片 */}
      <div className="yq-status-grid" style={{ marginTop: 12 }}>
        {[
          { num: s.projects ?? 0, label: '项目' },
          { num: s.questions ?? 0, label: '题目' },
          { num: s.flashcards ?? 0, label: '闪卡' },
          { num: s.podcasts ?? 0, label: '播客' },
          { num: s.streak ?? 0, label: '连续打卡' },
          { num: `⚡${s.points ?? 0}`, label: '元气值' },
        ].map(c => (
          <div key={c.label} className="yq-stat-card">
            <div className="num">{c.num}</div>
            <div className="label">{c.label}</div>
          </div>
        ))}
      </div>

      {/* 资料编辑 */}
      <div className="yq-section">
        <div className="yq-section-title">学习资料</div>
        <Form form={form} layout="vertical">
          <Space size={16} wrap align="start">
            <Form.Item name="name" label="昵称"><Input style={{ width: 200 }} /></Form.Item>
            <Form.Item name="daily_minutes" label="每天可投入(分钟)"><InputNumber min={5} max={600} /></Form.Item>
          </Space>
          <Form.Item name="goal" label="学习目标"><Input placeholder="如：考取教师资格证" /></Form.Item>
          <Form.Item name="goal_detail" label="目标详情"><Input.TextArea rows={2} /></Form.Item>
          <Button type="primary" onClick={save} loading={saving}>保存</Button>
        </Form>
      </div>

      {/* AI 服务商（按能力分档：文本 / 视觉 / 语音） */}
      <div className="yq-section">
        <div className="yq-section-title"><ApiOutlined /> AI 服务商（使用自己的 Key）</div>
        <Alert type="info" showIcon style={{ marginBottom: 14 }}
          message="三档可以分别配、也可以都不配"
          description="各家的能力并不通用：DeepSeek 只有文本模型、没有语音；语音则有不花钱的 edge 档，不需要任何 Key。所以这里按「文本 / 视觉 / 语音」分开配置，配哪档用哪档，不配就回退系统默认。费用由你自己的 Key 承担。" />
        {!providerConfigs ? (
          <Spin />
        ) : (
          ['text', 'vision', 'tts'].map(cap => (
            <ProviderConfigCard
              key={cap}
              capability={cap}
              label={capLabels[cap] || cap}
              hint={{
                text: '用于对话、摘要、出题、学习计划等所有文字类功能。',
                vision: '用于图片识别。不配则「看图」相关功能不可用（不会偷偷用文本模型顶替）。',
                tts: '用于听读与播客配音。不配则使用免费的 edge 音色。',
              }[cap] || ''}
              presets={presets[cap] || []}
              config={providerConfigs[cap]}
              onChanged={() => { loadProviders(); api.getProfileInfo().then(setData).catch(() => {}) }}
            />
          ))
        )}
      </div>

      {/* API 接口总览（开发者参考，随代码自动更新） */}
      <div className="yq-section">
        <div className="yq-section-title">
          <ApiOutlined /> API 接口
          {routeTotal > 0 && (
            <span style={{ color: '#999', fontWeight: 400, fontSize: 13, marginLeft: 8 }}>
              共 {routeTotal} 个接口 · {routeGroups.length} 组
            </span>
          )}
        </div>
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="本服务对外提供的全部 HTTP 接口，从后端接口定义自动生成，不会过时。在线试调可用后端的 /docs（Swagger）或 /redoc。" />
        <Input
          placeholder="搜索：路径 / 说明 / GET、POST…"
          allowClear value={routeQ} onChange={e => setRouteQ(e.target.value)}
          style={{ maxWidth: 380, marginBottom: 10 }}
        />
        {!routeGroups.length ? (
          <div style={{ color: '#bbb', fontSize: 13 }}>
            拿不到接口清单（后端未更新或无响应）。
          </div>
        ) : !shownCount ? (
          <div style={{ color: '#bbb', fontSize: 13 }}>没有匹配「{routeQ}」的接口。</div>
        ) : (
          <div style={{ maxHeight: 460, overflowY: 'auto', paddingRight: 6 }}>
            {shownGroups.map((g: any) => (
              <div key={g.tag} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 13, color: '#666', margin: '4px 0 6px' }}>
                  <b>{g.label}</b>
                  <span style={{ color: '#bbb', marginLeft: 6 }}>{g.routes.length} 个</span>
                </div>
                {g.routes.map((r: any) => (
                  <div
                    key={`${r.method} ${r.path}`}
                    style={{
                      display: 'flex', alignItems: 'baseline', gap: 8,
                      padding: '3px 0', fontSize: 13,
                      opacity: r.deprecated ? 0.5 : 1,
                    }}
                    title={r.deprecated ? '已弃用' : undefined}
                  >
                    <Tag
                      color={METHOD_COLOR[r.method] || 'default'}
                      style={{ width: 62, textAlign: 'center', marginInlineEnd: 0, flexShrink: 0 }}
                    >{r.method}</Tag>
                    <code style={{
                      color: '#531dab', background: '#f9f0ff', borderRadius: 4,
                      padding: '1px 6px', flexShrink: 0,
                    }}>{r.path}</code>
                    {r.summary && (
                      <span style={{ color: '#888', minWidth: 0 }}>{r.summary}</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 微信绑定 */}
      <div className="yq-section">
        <div className="yq-section-title"><WechatOutlined /> 微信绑定</div>
        {data.user.wechat_bound ? (
          <Space>
            <Tag color="green">已绑定微信</Tag>
            <Popconfirm title="解绑微信？" onConfirm={async () => {
              await api.wechatUnbind(); message.success('已解绑'); load()
            }}>
              <Button size="small" danger>解绑</Button>
            </Popconfirm>
          </Space>
        ) : (
          <div>
            <p style={{ color: '#999', fontSize: 13 }}>微信登录需在微信开放平台配置后启用（WECHAT_APP_ID / SECRET），当前为预留接口。</p>
            <Button size="small" disabled>绑定微信</Button>
          </div>
        )}
      </div>
    </div>
  )
}
