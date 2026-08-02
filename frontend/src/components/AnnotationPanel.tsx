import { useState } from 'react'
import { Empty, Button, Modal, Input, Tag, Tooltip } from 'antd'
import { EditOutlined, DeleteOutlined, PushpinOutlined } from '@ant-design/icons'

export interface Annotation {
  id: string
  document_id: string
  unit_type: string
  unit_index: number
  start_offset: number
  end_offset: number
  selected_text: string
  content: string
}

interface Props {
  annotations: Annotation[]
  unitTitleOf: (index: number) => string
  onJump: (ann: Annotation) => void
  onEdit: (ann: Annotation, content: string) => void
  onDelete: (id: string) => void
}

export default function AnnotationPanel({ annotations, unitTitleOf, onJump, onEdit, onDelete }: Props) {
  const [editing, setEditing] = useState<Annotation | null>(null)
  const [draft, setDraft] = useState('')

  if (annotations.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选中文本即可添加批注" />
  }

  const openEdit = (ann: Annotation) => {
    setEditing(ann)
    setDraft(ann.content)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {annotations.map(a => (
        <div
          key={a.id}
          className="ann-item"
          onClick={() => onJump(a)}
          style={{ cursor: 'pointer' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <PushpinOutlined style={{ color: '#7c5cfc' }} />
            <Tag color="purple" style={{ margin: 0 }}>{unitTitleOf(a.unit_index)}</Tag>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 2 }}>
              <Tooltip title="编辑"><Button size="small" type="text" icon={<EditOutlined />} onClick={e => { e.stopPropagation(); openEdit(a) }} /></Tooltip>
              <Tooltip title="删除"><Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={e => { e.stopPropagation(); onDelete(a.id) }} /></Tooltip>
            </span>
          </div>
          <div style={{ fontSize: 12, color: '#8c6ff0', background: '#f4f0ff', padding: '4px 8px', borderRadius: 6, marginBottom: 6 }}>
            「{a.selected_text.length > 40 ? a.selected_text.slice(0, 40) + '…' : a.selected_text}」
          </div>
          <div style={{ fontSize: 13, color: '#444', lineHeight: 1.6 }}>{a.content}</div>
        </div>
      ))}

      <Modal
        title="编辑批注"
        open={!!editing}
        onOk={() => { if (editing) { onEdit(editing, draft); setEditing(null) } }}
        onCancel={() => setEditing(null)}
        okText="保存"
        cancelText="取消"
      >
        <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>
          「{editing?.selected_text}」
        </div>
        <Input.TextArea rows={4} value={draft} onChange={e => setDraft(e.target.value)} placeholder="批注内容" />
      </Modal>
    </div>
  )
}
