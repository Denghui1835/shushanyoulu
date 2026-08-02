import { useEffect, useState } from 'react'
import { Card, Button, Modal, Form, Input, Select, Empty, Popconfirm, message, Spin } from 'antd'
import { PlusOutlined, ReadOutlined, DeleteOutlined, FolderOpenOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

interface Project {
  id: string
  title: string
  description: string
  icon: string
  document_count: number
}

const ICONS = ['📚', '👑', '🧠', '📐', '🗂️', '🎓', '💡', '📈']

export default function BookshelfPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    try { setProjects(await api.listProjects()) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const create = async () => {
    const values = await form.validateFields()
    setCreating(true)
    try {
      const p = await api.createProject({ ...values, icon: values.icon || '📚' })
      message.success(`项目「${p.title}」已创建`)
      setCreateOpen(false)
      form.resetFields()
      navigate(`/project/${p.id}`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败')
    } finally { setCreating(false) }
  }

  const remove = async (p: Project) => {
    const r = await api.deleteProject(p.id)
    message.success(`已删除「${p.title}」${r.deleted_documents ? `，同时清理 ${r.deleted_documents} 个章节` : ''}`)
    load()
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <div className="page-card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <ReadOutlined style={{ fontSize: 26, color: '#7c5cfc' }} />
        <div>
          <h2 style={{ margin: 0 }}>我的书架</h2>
          <div style={{ color: '#999', fontSize: 13 }}>每个项目就是一本「书」，打开书才能看到章节与功能</div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            创建项目
          </Button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="page-card" style={{ textAlign: 'center', padding: 60 }}>
          <Empty description="书架还是空的，创建一个学习项目吧，比如《推理王国》" />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)} style={{ marginTop: 12 }}>
            创建第一个项目
          </Button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14 }}>
          {projects.map(p => (
            <Card
              key={p.id} hoverable
              className="yq-book-card"
              onClick={() => navigate(`/project/${p.id}`)}
              actions={[
                <FolderOpenOutlined key="open" onClick={(e) => { e.stopPropagation(); navigate(`/project/${p.id}`) }} />,
                <Popconfirm key="del" title={`删除项目「${p.title}」？其下章节将一并删除`} onConfirm={(e) => { e?.stopPropagation(); remove(p) }}>
                  <DeleteOutlined onClick={(e) => e.stopPropagation()} />
                </Popconfirm>,
              ]}
            >
              <Card.Meta
                avatar={<span style={{ fontSize: 34 }}>{p.icon || '📚'}</span>}
                title={p.title}
                description={
                  <div>
                    <div style={{ color: '#666', minHeight: 40 }}>{p.description || '—'}</div>
                    <div style={{ marginTop: 6, fontSize: 12, color: '#999' }}>
                      共 {p.document_count} 个章节
                    </div>
                  </div>
                }
              />
            </Card>
          ))}
        </div>
      )}

      <Modal
        title="创建学习项目"
        open={createOpen}
        onOk={create}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        okText="创建并打开"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="title" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="例如：推理王国" />
          </Form.Item>
          <Form.Item name="description" label="简介（可选）">
            <Input.TextArea rows={2} placeholder="这门课/这本书学的是什么？" />
          </Form.Item>
          <Form.Item name="icon" label="封面图标" initialValue="📚">
            <Select options={ICONS.map(i => ({ value: i, label: <span style={{ fontSize: 20 }}>{i}</span> }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
