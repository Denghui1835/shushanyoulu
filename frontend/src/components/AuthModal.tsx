import { useState } from 'react'
import { Modal, Tabs, Form, Input, Button, Alert, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { api, setAuthToken } from '../api'

type Mode = 'login' | 'register'

/** 登录/注册表单本体 —— 弹窗与 /login 页共用，避免两处各写一遍。 */
export function AuthForm({ defaultTab = 'login', onSuccess }: {
  defaultTab?: Mode
  onSuccess?: (user: any) => void
}) {
  const [tab, setTab] = useState<Mode>(defaultTab)
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const submit = async (mode: Mode) => {
    const v = await form.validateFields()
    setLoading(true)
    try {
      const r = mode === 'login'
        ? await api.login(v.username, v.password)
        : await api.register(v.username, v.password)
      setAuthToken(r.token)
      message.success(mode === 'login' ? `欢迎回来，${r.user.name}` : `注册成功，欢迎你，${r.user.name}`)
      form.resetFields()
      onSuccess?.(r.user)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || (mode === 'login' ? '登录失败' : '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <Tabs
        activeKey={tab}
        onChange={k => setTab(k as Mode)}
        items={[{ key: 'login', label: '登录' }, { key: 'register', label: '注册' }]}
      />
      {tab === 'register' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 14 }}
          message="第一个注册的账号 = 主人"
          description="本机第一次注册的账号会自动继承现有全部书架、计划与聊天记录；此后注册的账号从零开始，可浏览广场、一键学习公开课程。"
        />
      )}
      <Form form={form} layout="vertical" onFinish={() => submit(tab)} requiredMark={false}>
        <Form.Item
          name="username"
          rules={[{ required: true, message: '请输入用户名' }, { min: 2, message: '用户名至少 2 个字符' }]}
        >
          <Input prefix={<UserOutlined />} placeholder="用户名" size="large" autoComplete="username" />
        </Form.Item>
        <Form.Item
          name="password"
          rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少 6 位' }]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="密码（至少 6 位）"
            size="large"
            autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
            onPressEnter={() => form.submit()}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" size="large" block loading={loading}>
          {tab === 'login' ? '登录' : '注册并登录'}
        </Button>
      </Form>
    </div>
  )
}

/** 顶栏「登录/注册」触发的弹窗。 */
export default function AuthModal({ open, onClose, onSuccess }: {
  open: boolean
  onClose: () => void
  onSuccess?: (user: any) => void
}) {
  return (
    <Modal open={open} onCancel={onClose} footer={null} width={400} destroyOnClose title={null}>
      <div style={{ paddingTop: 6 }}>
        <AuthForm onSuccess={u => { onClose(); onSuccess?.(u) }} />
      </div>
    </Modal>
  )
}