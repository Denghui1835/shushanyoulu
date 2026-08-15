import { useEffect, useState } from 'react'
import {
  Card, Avatar, Button, Form, Input, InputNumber, Tag, Space, message, Spin, Popconfirm, Alert, Result,
} from 'antd'
import { UserOutlined, ApiOutlined, LogoutOutlined, WechatOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, setAuthToken, getAuthToken } from '../api'

/** 个人中心：资料 + 统计 + 自有 API Key + 微信绑定 + 退出登录。 */
export default function ProfilePage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  // API Key 设置
  const [apiKeyInfo, setApiKeyInfo] = useState<any>(null)
  const [keyForm] = Form.useForm()
  const [savingKey, setSavingKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const navigate = useNavigate()

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
      setApiKeyInfo(await api.getApiKey())
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

  const saveKey = async (testOnly = false) => {
    const v = await keyForm.validateFields()
    if (testOnly) {
      setTesting(true)
      try { const r = await api.testApiKey(v); message.success(r.message || '连接成功') }
      catch (e: any) { message.error(e?.response?.data?.detail || '连接失败') }
      finally { setTesting(false) }
      return
    }
    setSavingKey(true)
    try {
      const r = await api.saveApiKey(v)
      message.success(`已保存，后续 AI 功能将使用你的 Key${r.masked_key ? `（${r.masked_key}）` : ''}`)
      setApiKeyInfo(await api.getApiKey())
      keyForm.resetFields()
    } catch (e: any) { message.error(e?.response?.data?.detail || '保存失败') }
    finally { setSavingKey(false) }
  }

  const removeKey = async () => {
    await api.deleteApiKey()
    message.success('已删除，AI 功能回退到系统默认 Key')
    setApiKeyInfo(await api.getApiKey())
  }

  const logout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    setAuthToken('')
    setData(null)
    message.success('已退出登录')
    navigate('/')
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  if (!getAuthToken()) {
    return (
      <div className="yq-page">
        <div className="yq-section yq-empty-state">
          <UserOutlined style={{ fontSize: 48, color: '#7c5cfc' }} />
          <h3 style={{ marginTop: 12 }}>登录后才能查看个人中心</h3>
          <p style={{ color: '#999' }}>去「作品社区」注册/登录，第一个注册的账号会成为主人</p>
          <Button type="primary" onClick={() => navigate('/community')}>去登录</Button>
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
            {data.user.api_key_set && <Tag color="blue"><ApiOutlined /> 已配置自有 Key</Tag>}
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

      {/* API 设置（用户自理 Key → 开源免费） */}
      <div className="yq-section">
        <div className="yq-section-title"><ApiOutlined /> API 设置（使用自己的 Key）</div>
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="填写你自己的 API Key 后，所有 AI 功能将使用你的 Key 调用，费用由你自理的 Key 承担；不填则使用系统默认 Key。" />
        {apiKeyInfo?.configured && (
          <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f6ffed', borderRadius: 8, border: '1px solid #b7eb8f' }}>
            <CheckCircleOutlined style={{ color: '#52c41a' }} /> 当前已配置：{apiKeyInfo.masked_key}
            {apiKeyInfo.base_url && ` · ${apiKeyInfo.base_url}`}
            {apiKeyInfo.model && ` · ${apiKeyInfo.model}`}
            <Popconfirm title="删除后 AI 功能回退到系统默认 Key？" onConfirm={removeKey}>
              <Button size="small" danger style={{ marginLeft: 8 }}>删除</Button>
            </Popconfirm>
          </div>
        )}
        <Form form={keyForm} layout="vertical">
          <Form.Item name="api_key" label="API Key" rules={[{ required: true, message: '请输入 API Key' }]}>
            <Input.Password placeholder="sk-..." autoComplete="new-password" />
          </Form.Item>
          <Space size={16} wrap>
            <Form.Item name="base_url" label="API Base URL"><Input placeholder="https://api.deepseek.com" style={{ width: 280 }} /></Form.Item>
            <Form.Item name="model" label="模型名"><Input placeholder="deepseek-chat" style={{ width: 180 }} /></Form.Item>
          </Space>
          <Space>
            <Button type="primary" loading={savingKey} onClick={() => saveKey()}>保存</Button>
            <Button loading={testing} onClick={() => saveKey(true)}>测试连接</Button>
          </Space>
        </Form>
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
