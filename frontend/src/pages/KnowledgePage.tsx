import { useEffect, useState } from 'react'
import { Select, Tree, Button, Empty, message, Spin, Space, Tag } from 'antd'
import { AppstoreOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

export default function KnowledgePage() {
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [tree, setTree] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [params] = useSearchParams()

  const loadDocs = async () => {
    const d = await api.listDocuments()
    setDocs(d)
    const fromUrl = params.get('doc')
    if (fromUrl && d.some((x: any) => x.id === fromUrl)) setDocId(fromUrl)
    else if (d.length > 0 && !docId) setDocId(d[0].id)
  }
  useEffect(() => { loadDocs() }, [])
  useEffect(() => { if (docId) loadTree() }, [docId])

  const loadTree = async () => {
    setLoading(true)
    try {
      const res = await api.getKnowledgeTree(docId)
      setTree(res.tree)
    } finally { setLoading(false) }
  }

  const generate = async () => {
    setGenerating(true)
    try {
      const res = await api.generateKnowledgeTree(docId)
      setTree(res.tree)
      message.success(`知识树生成完成，共 ${res.count} 个节点`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败')
    } finally { setGenerating(false) }
  }

  const convert = (nodes: any[]): any[] => nodes.map(n => ({
    key: n.id,
    title: n.summary ? `${n.title} — ${n.summary}` : n.title,
    children: convert(n.children || []),
  }))

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="page-card">
        <Space wrap>
          <AppstoreOutlined style={{ color: '#7c5cfc', fontSize: 18 }} />
          <b>知识树</b>
          <Select
            style={{ width: 280 }} placeholder="选择资料" value={docId || undefined}
            onChange={setDocId} options={docs.map(d => ({ value: d.id, label: d.title }))}
          />
          <Button type="primary" loading={generating} onClick={generate}>
            {tree.length ? '重新生成知识树' : '生成知识树'}
          </Button>
        </Space>
        <Tag style={{ marginTop: 8 }} color="purple">AI 自动提炼这份资料的知识结构</Tag>
      </div>

      <div className="page-card">
        {loading ? <Spin /> : tree.length === 0 ? (
          <Empty description="还没有知识树，点击「生成知识树」让 AI 帮你梳理" />
        ) : (
          <Tree defaultExpandAll showLine treeData={convert(tree)} />
        )}
      </div>
    </div>
  )
}
