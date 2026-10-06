import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Input, Modal, Popconfirm, Result, Space, Spin, Table, Tag, Tooltip, message,
} from 'antd'
import { SafetyOutlined, ReloadOutlined, DeleteOutlined, StopOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { api, getAuthToken } from '../api'
import PageHeader from '../components/PageHeader'

interface AdminUser {
  id: string
  username: string
  name: string
  created_at: string | null
  last_activity_at: string | null
  project_count: number
  session_count: number
  is_admin: boolean
  is_active: boolean
  has_password: boolean
  has_wechat: boolean
  is_self: boolean
}

const fmtTime = (t: string | null) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '—')

/**
 * /admin 用户管理（仅管理员）。
 *
 * 三层守卫：没登录 → 去登录；登录了但不是管理员 → 403；管理员 → 列表。
 * 后端每个接口都挂了 require_admin，所以这里的守卫只是为了不让人看见白屏/报错，
 * 真正的权限判定在服务端。
 */
export default function AdminPage() {
  const navigate = useNavigate()
  const loggedIn = !!getAuthToken()
  const [checking, setChecking] = useState(true)
  const [isAdmin, setIsAdmin] = useState(false)
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  // 重置密码
  const [pwdTarget, setPwdTarget] = useState<AdminUser | null>(null)
  const [pwd, setPwd] = useState('')
  const [pwdBusy, setPwdBusy] = useState(false)

  // 删除
  const [delTarget, setDelTarget] = useState<AdminUser | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const [delBusy, setDelBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.adminListUsers())
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  // 先确认身份，再决定渲染哪一层
  useEffect(() => {
    if (!loggedIn) { setChecking(false); return }
    let alive = true
    api.me()
      .then(r => { if (alive) setIsAdmin(!!r?.user?.is_admin) })
      .catch(() => { if (alive) setIsAdmin(false) })
      .finally(() => { if (alive) setChecking(false) })
    return () => { alive = false }
  }, [loggedIn])

  useEffect(() => { if (isAdmin) load() }, [isAdmin, load])

  if (!loggedIn) {
    return (
      <Result
        status="403"
        title="需要登录"
        subTitle="用户管理仅对管理员开放，请先用管理员账号登录。"
        extra={<Button type="primary" onClick={() => navigate('/login')}>去登录</Button>}
      />
    )
  }
  if (checking) return <div style={{ padding: 80, textAlign: 'center' }}><Spin /></div>
  if (!isAdmin) {
    return (
      <Result
        status="403"
        title="403"
        subTitle="这个页面只有管理员能进。当前账号没有管理权限。"
        extra={<Button onClick={() => navigate('/')}>回首页</Button>}
      />
    )
  }

  const doResetPassword = async () => {
    if (!pwdTarget) return
    if (pwd.length < 6) { message.warning('密码至少 6 位'); return }
    setPwdBusy(true)
    try {
      const r = await api.adminResetPassword(pwdTarget.id, pwd)
      message.success(`已重设密码，并强制下线 ${r.revoked_tokens ?? 0} 个会话`)
      setPwdTarget(null); setPwd('')
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '重置失败')
    } finally { setPwdBusy(false) }
  }

  const doSetActive = async (u: AdminUser, active: boolean) => {
    try {
      const r = await api.adminSetActive(u.id, active)
      message.success(active
        ? `已启用「${u.username}」`
        : `已停用「${u.username}」，并踢下线 ${r.revoked_tokens ?? 0} 个会话`)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  const openDelete = async (u: AdminUser) => {
    setDelTarget(u); setConfirmName(''); setPreview(null); setPreviewBusy(true)
    try {
      setPreview(await api.adminDeletePreview(u.id))
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '无法读取删除预览')
    } finally { setPreviewBusy(false) }
  }

  const doDelete = async () => {
    if (!delTarget) return
    setDelBusy(true)
    try {
      await api.adminDeleteUser(delTarget.id, confirmName.trim())
      message.success(`已删除账号「${delTarget.username}」及其全部数据`)
      setDelTarget(null)
      load()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    } finally { setDelBusy(false) }
  }

  const columns: any[] = [
    {
      title: '用户名', dataIndex: 'username', width: 170,
      render: (v: string, r: AdminUser) => (
        <Space size={6}>
          <span style={{ fontWeight: 600 }}>{v || '（无用户名）'}</span>
          {r.is_admin && <Tag color="gold">管理员</Tag>}
          {r.is_self && <Tag>我</Tag>}
        </Space>
      ),
    },
    { title: '昵称', dataIndex: 'name', width: 130, render: (v: string) => v || '—' },
    {
      title: '状态', dataIndex: 'is_active', width: 100,
      render: (v: boolean) => v
        ? <Tag color="green">正常</Tag>
        : <Tag color="red">已停用</Tag>,
    },
    {
      title: '登录方式', width: 120,
      render: (_: any, r: AdminUser) => (
        <Space size={4} wrap>
          {r.has_password && <Tag>密码</Tag>}
          {r.has_wechat && <Tag color="cyan">微信</Tag>}
          {!r.has_password && !r.has_wechat && <span style={{ color: '#999' }}>—</span>}
        </Space>
      ),
    },
    { title: '注册时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '最后活跃', dataIndex: 'last_activity_at', width: 160,
      render: (v: string | null) => (v ? fmtTime(v) : <span style={{ color: '#999' }}>从未</span>),
    },
    { title: '仓库', dataIndex: 'project_count', width: 80, align: 'center' },
    {
      title: '会话', dataIndex: 'session_count', width: 80, align: 'center',
      render: (v: number) => (
        <Tooltip title="当前有效的登录令牌数，也就是还在线/未退出的设备数">
          <span>{v}</span>
        </Tooltip>
      ),
    },
    {
      title: '操作', width: 250, fixed: 'right',
      render: (_: any, r: AdminUser) => (
        <Space size={4} wrap>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => { setPwdTarget(r); setPwd('') }}>
            重置密码
          </Button>
          {r.is_active ? (
            <Popconfirm
              title={`停用「${r.username}」？`}
              description="该账号将无法登录，且已登录的会话会被全部踢下线。"
              okText="停用" okButtonProps={{ danger: true }} cancelText="取消"
              onConfirm={() => doSetActive(r, false)}
              disabled={r.is_self}
            >
              <Button size="small" danger icon={<StopOutlined />} disabled={r.is_self}>停用</Button>
            </Popconfirm>
          ) : (
            <Button size="small" icon={<PlayCircleOutlined />} onClick={() => doSetActive(r, true)}>
              启用
            </Button>
          )}
          <Button
            size="small" danger icon={<DeleteOutlined />}
            disabled={r.is_self}
            onClick={() => openDelete(r)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="yq-page">
      <PageHeader
        icon={<SafetyOutlined />}
        title="用户管理"
        subtitle="重置密码 / 停用 / 删除账号。删除不可逆，操作前请先看清预览。"
        extra={<Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>}
      />

      {data?.warning && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="封禁在当前模式下拦不住人" description={data.warning} />
      )}

      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message={`共 ${data?.total ?? 0} 个账号，其中管理员 ${data?.admin_count ?? 0} 个`}
        description="「重置密码」会把该账号已登录的会话全部踢下线；「停用」同样会踢下线，且该账号无法再登录。"
      />

      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={data?.users ?? []}
        scroll={{ x: 1180 }}
        pagination={false}
      />

      {/* 重置密码 */}
      <Modal
        open={!!pwdTarget}
        title={`重置密码：${pwdTarget?.username || ''}`}
        okText="确认重置" cancelText="取消"
        confirmLoading={pwdBusy}
        onOk={doResetPassword}
        onCancel={() => { setPwdTarget(null); setPwd('') }}
      >
        <p style={{ color: '#666' }}>
          设置新密码后，该账号所有已登录的会话会立刻失效，需要用新密码重新登录。
        </p>
        <Input.Password
          placeholder="新密码（至少 6 位）"
          value={pwd}
          onChange={e => setPwd(e.target.value)}
          onPressEnter={doResetPassword}
        />
      </Modal>

      {/* 删除账号 */}
      <Modal
        open={!!delTarget}
        title={`删除账号：${delTarget?.username || ''}`}
        okText="永久删除"
        cancelText="取消"
        confirmLoading={delBusy}
        okButtonProps={{ danger: true, disabled: !preview || !!preview?.blocked_reason || confirmName.trim() !== (delTarget?.username || '') }}
        onOk={doDelete}
        onCancel={() => setDelTarget(null)}
      >
        {previewBusy ? <Spin /> : preview ? (
          <>
            {preview.blocked_reason ? (
              <Alert type="error" showIcon style={{ marginBottom: 12 }}
                message="这个账号不能删除" description={preview.blocked_reason} />
            ) : (
              <Alert type="error" showIcon style={{ marginBottom: 12 }}
                message="删除不可逆" description="该账号及其名下全部数据将被永久删除，无法恢复。" />
            )}

            <div style={{ marginBottom: 8, fontWeight: 600 }}>将要删除的数据：</div>
            <ul style={{ margin: '0 0 12px', paddingLeft: 20, color: '#555' }}>
              {Object.entries(preview.counts || {}).map(([k, v]) => (
                <li key={k}>{k}：<b>{v as number}</b></li>
              ))}
              {!Object.keys(preview.counts || {}).length && <li>（没有其他数据）</li>}
            </ul>

            {!!(preview.projects || []).length && (
              <>
                <div style={{ marginBottom: 8, fontWeight: 600 }}>名下的仓库（会一并删除）：</div>
                <ul style={{ margin: '0 0 12px', paddingLeft: 20, color: '#555' }}>
                  {preview.projects.map((p: any) => (
                    <li key={p.id}>{p.title || '(无标题)'} <span style={{ color: '#999' }}>· {p.visibility}</span></li>
                  ))}
                </ul>
              </>
            )}

            <p style={{ marginBottom: 4 }}>请输入该账号的用户名 <b>{delTarget?.username}</b> 以确认：</p>
            <Input
              value={confirmName}
              onChange={e => setConfirmName(e.target.value)}
              placeholder={delTarget?.username || ''}
            />
          </>
        ) : <span style={{ color: '#999' }}>读取中…</span>}
      </Modal>
    </div>
  )
}
