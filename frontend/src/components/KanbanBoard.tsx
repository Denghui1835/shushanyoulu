import { useEffect, useState, useCallback } from 'react'
import {
  Card, Button, Tag, Modal, Input, Select, DatePicker, Space, message, Empty, Switch, Spin,
  Drawer, Form, Popconfirm, Dropdown,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, MoreOutlined, HolderOutlined,
  ProjectOutlined, SwapOutlined,
} from '@ant-design/icons'
import {
  DndContext, DragOverlay, closestCenter, PointerSensor, useSensor, useSensors,
  type DragStartEvent, type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import dayjs from 'dayjs'
import { api } from '../api'

// ── 类型 ──

interface ColData { id: string; title: string; sort_order: number; is_default: boolean }
interface CardData {
  id: string; column_id: string; title: string; description: string
  priority: string; due_date: string | null; assignee: string
  sort_order: number; plan_task_id: string | null
}
interface BoardState { kanban_enabled: boolean; columns: ColData[]; cards: CardData[] }

const PRIO_COLORS: Record<string, string> = { high: 'red', medium: 'orange', low: 'default' }
const PRIO_LABEL: Record<string, string> = { high: '高', medium: '中', low: '低' }

// ── 可拖拽卡片 ──

function SortableCard({ card, onEdit, onDelete }: {
  card: CardData; onEdit: (c: CardData) => void; onDelete: (id: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.id,
    data: { type: 'card', card },
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }
  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <Card
        size="small"
        style={{ marginBottom: 8, cursor: 'grab' }}
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span {...listeners} style={{ cursor: 'grab', color: '#bbb', fontSize: 12 }}>
              <HolderOutlined />
            </span>
            <span style={{ fontSize: 13, flex: 1 }}>{card.title}</span>
          </div>
        }
        extra={
          <Dropdown menu={{ items: [
            { key: 'edit', icon: <EditOutlined />, label: '编辑', onClick: () => onEdit(card) },
            { key: 'del', icon: <DeleteOutlined />, label: '删除', danger: true, onClick: () => onDelete(card.id) },
          ]}} trigger={['click']}>
            <Button size="small" type="text" icon={<MoreOutlined />} />
          </Dropdown>
        }
      >
        {card.description && (
          <div style={{ fontSize: 12, color: '#666', marginBottom: 6, lineHeight: 1.5 }}>
            {card.description.length > 60 ? card.description.slice(0, 60) + '…' : card.description}
          </div>
        )}
        <Space size={4} wrap>
          <Tag color={PRIO_COLORS[card.priority]} style={{ fontSize: 11 }}>{PRIO_LABEL[card.priority]}</Tag>
          {card.due_date && (
            <Tag color={dayjs(card.due_date).isBefore(dayjs()) ? 'red' : 'blue'} style={{ fontSize: 11 }}>
              {card.due_date.slice(5)}
            </Tag>
          )}
          {card.assignee && (
            <Tag style={{ fontSize: 11 }}>{card.assignee}</Tag>
          )}
        </Space>
      </Card>
    </div>
  )
}

// ── 可拖拽列 ──

function KanbanColumn({ col, cards, onAddCard, onEditCard, onDeleteCard, onRename, onDeleteCol }: {
  col: ColData
  cards: CardData[]
  onAddCard: (colId: string) => void
  onEditCard: (c: CardData) => void
  onDeleteCard: (id: string) => void
  onRename: (colId: string, title: string) => void
  onDeleteCol: (colId: string) => void
}) {
  const [renaming, setRenaming] = useState(false)
  const [newTitle, setNewTitle] = useState(col.title)

  const colCards = cards.filter(c => c.column_id === col.id).sort((a, b) => a.sort_order - b.sort_order)

  return (
    <div style={{
      width: 280, flexShrink: 0, background: '#f5f5f9', borderRadius: 10,
      padding: '10px 10px 6px', display: 'flex', flexDirection: 'column', maxHeight: 'calc(100vh - 240px)',
    }}>
      {/* 列头 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, padding: '0 4px' }}>
        {renaming ? (
          <Input size="small" value={newTitle} autoFocus style={{ width: 140 }}
            onChange={e => setNewTitle(e.target.value)}
            onBlur={() => { onRename(col.id, newTitle); setRenaming(false) }}
            onPressEnter={() => { onRename(col.id, newTitle); setRenaming(false) }}
          />
        ) : (
          <span style={{ fontWeight: 600, fontSize: 13, cursor: 'pointer' }}
            onDoubleClick={() => !col.is_default && setRenaming(true)}>
            {col.title} <span style={{ color: '#999', fontWeight: 400, fontSize: 12 }}>({colCards.length})</span>
          </span>
        )}
        <Space size={2}>
          {!col.is_default && (
            <Popconfirm title="删除此列及其中所有卡片？" onConfirm={() => onDeleteCol(col.id)}>
              <Button size="small" type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      </div>

      {/* 卡片列表 */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 60, padding: '0 2px' }}>
        <SortableContext items={colCards.map(c => c.id)} strategy={verticalListSortingStrategy}>
          {colCards.map(c => (
            <SortableCard key={c.id} card={c} onEdit={onEditCard} onDelete={onDeleteCard} />
          ))}
        </SortableContext>
        {colCards.length === 0 && (
          <div style={{ textAlign: 'center', padding: 20, color: '#ccc', fontSize: 12 }}>
            拖拽卡片到此处
          </div>
        )}
      </div>

      {/* 新建按钮 */}
      <Button type="dashed" size="small" block icon={<PlusOutlined />}
        style={{ marginTop: 6, borderColor: '#d9d9d9' }}
        onClick={() => onAddCard(col.id)}>
        新建任务
      </Button>
    </div>
  )
}

// ── 卡片编辑 Drawer ──

function CardDrawer({ open, card, onClose, onSave }: {
  open: boolean; card: CardData | null; onClose: () => void; onSave: (data: any) => void
}) {
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [priority, setPriority] = useState('medium')
  const [dueDate, setDueDate] = useState<string | null>(null)
  const [assignee, setAssignee] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (card) {
      setTitle(card.title); setDesc(card.description); setPriority(card.priority)
      setDueDate(card.due_date); setAssignee(card.assignee)
    } else {
      setTitle(''); setDesc(''); setPriority('medium'); setDueDate(null); setAssignee('')
    }
  }, [card, open])

  const save = async () => {
    if (!title.trim()) { message.warning('请填写任务标题'); return }
    setSaving(true)
    try {
      await onSave({ title: title.trim(), description: desc.trim(), priority, due_date: dueDate, assignee: assignee.trim() })
      onClose()
    } finally { setSaving(false) }
  }

  return (
    <Drawer title={card ? '编辑任务' : '新建任务'} open={open} onClose={onClose} width={380}
      extra={<Button type="primary" loading={saving} onClick={save}>保存</Button>}>
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <div>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>标题</div>
          <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="任务标题" />
        </div>
        <div>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>描述</div>
          <Input.TextArea rows={3} value={desc} onChange={e => setDesc(e.target.value)} placeholder="任务描述（可选）" />
        </div>
        <div>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>优先级</div>
          <Select value={priority} onChange={setPriority} style={{ width: '100%' }}
            options={[{ value: 'high', label: '🔴 高' }, { value: 'medium', label: '🟠 中' }, { value: 'low', label: '🟢 低' }]} />
        </div>
        <div>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>截止日期</div>
          <DatePicker value={dueDate ? dayjs(dueDate) : null} onChange={v => setDueDate(v ? v.format('YYYY-MM-DD') : null)}
            style={{ width: '100%' }} placeholder="选择截止日期" />
        </div>
        <div>
          <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>负责人</div>
          <Input value={assignee} onChange={e => setAssignee(e.target.value)} placeholder="负责人名（可选）" />
        </div>
      </Space>
    </Drawer>
  )
}

// ── 主组件 ──

export default function KanbanBoard({ projectId }: { projectId: string }) {
  const [board, setBoard] = useState<BoardState | null>(null)
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState(false)

  // 拖拽状态
  const [activeCard, setActiveCard] = useState<CardData | null>(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  // 编辑抽屉
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingCard, setEditingCard] = useState<CardData | null>(null)
  const [newCardCol, setNewCardCol] = useState<string>('')

  const load = useCallback(async () => {
    try {
      const d = await api.callRaw(`/projects/${projectId}/kanban`)
      setBoard(d)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const toggle = async (on: boolean) => {
    setToggling(true)
    try {
      await api.callRaw(`/projects/${projectId}/kanban/toggle`, { method: 'PUT', body: { enabled: on } })
      setBoard(b => b ? { ...b, kanban_enabled: on } : null)
    } finally { setToggling(false) }
  }

  const handleDragStart = (e: DragStartEvent) => {
    const card = e.active.data.current?.card as CardData | undefined
    setActiveCard(card || null)
  }

  const handleDragEnd = async (e: DragEndEvent) => {
    setActiveCard(null)
    const { active, over } = e
    if (!over || !board) return

    const activeId = active.id as string
    const overId = over.id as string
    const card = board.cards.find(c => c.id === activeId)
    if (!card) return

    // 判断目标：如果是卡片 → 插入到它上方；如果是列容器 → 放末尾
    let targetColId: string
    let targetSort: number

    const overCard = board.cards.find(c => c.id === overId)
    if (overCard) {
      targetColId = overCard.column_id
      targetSort = overCard.sort_order
    } else {
      // dropped on a column (empty area)
      targetColId = overId
      const colCards = board.cards.filter(c => c.column_id === overId)
      targetSort = colCards.length
    }

    if (card.column_id === targetColId && card.sort_order === targetSort) return

    // Optimistic UI update
    const newCards = board.cards.map(c => {
      if (c.id === activeId) return { ...c, column_id: targetColId, sort_order: targetSort }
      // 调整目标列其他卡片顺序
      if (c.column_id === targetColId && c.sort_order >= targetSort && c.id !== activeId)
        return { ...c, sort_order: c.sort_order + 1 }
      if (c.column_id === card.column_id && c.sort_order > card.sort_order && c.id !== activeId)
        return { ...c, sort_order: c.sort_order - 1 }
      return c
    })
    setBoard({ ...board, cards: newCards })

    try {
      await api.callRaw(`/projects/${projectId}/kanban/cards/${activeId}/move`, {
        method: 'PUT',
        body: { column_id: targetColId, sort_order: targetSort, above_id: overCard?.id || null },
      })
    } catch {
      load() // revert
    }
  }

  // 卡片 CRUD
  const openNewCard = (colId: string) => {
    setEditingCard(null); setNewCardCol(colId); setDrawerOpen(true)
  }
  const openEditCard = (c: CardData) => {
    setEditingCard(c); setNewCardCol(''); setDrawerOpen(true)
  }
  const saveCard = async (data: any) => {
    if (editingCard) {
      await api.callRaw(`/projects/${projectId}/kanban/cards/${editingCard.id}`, { method: 'PUT', body: data })
    } else {
      await api.callRaw(`/projects/${projectId}/kanban/cards`, { method: 'POST', body: { ...data, column_id: newCardCol } })
    }
    load()
  }
  const deleteCard = async (id: string) => {
    await api.callRaw(`/projects/${projectId}/kanban/cards/${id}`, { method: 'DELETE' })
    load()
  }

  // 列 CRUD
  const addColumn = async () => {
    const title = prompt('新列名称：')?.trim()
    if (!title) return
    await api.callRaw(`/projects/${projectId}/kanban/columns`, { method: 'POST', body: { title } })
    load()
  }
  const renameColumn = async (colId: string, title: string) => {
    if (!title.trim()) return
    await api.callRaw(`/projects/${projectId}/kanban/columns/${colId}`, { method: 'PUT', body: { title } })
    load()
  }
  const deleteColumn = async (colId: string) => {
    await api.callRaw(`/projects/${projectId}/kanban/columns/${colId}`, { method: 'DELETE' })
    load()
  }

  // ── render ──

  if (loading) return <Spin style={{ display: 'block', margin: 40 }} />
  if (!board) return <Empty description="加载看板失败" />

  return (
    <div>
      {/* 开关 + 工具栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: '#666' }}>看板视图</span>
        <Switch checked={board.kanban_enabled} loading={toggling} onChange={toggle} />
        {board.kanban_enabled && (
          <>
            <div style={{ flex: 1 }} />
            <Button size="small" icon={<PlusOutlined />} onClick={addColumn}>新增列</Button>
            <Button size="small" onClick={() => {
              api.callRaw(`/projects/${projectId}/kanban/sync-plan-tasks`, { method: 'POST' }).then((r: any) => {
                message.success(`已导入 ${r.imported} 个任务`)
                load()
              })
            }}>从学习计划导入</Button>
          </>
        )}
      </div>

      {!board.kanban_enabled ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          <ProjectOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />
          <p>开启看板来管理这个项目的任务</p>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter}
          onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 16 }}>
            {board.columns.sort((a, b) => a.sort_order - b.sort_order).map(col => (
              <KanbanColumn key={col.id} col={col} cards={board.cards}
                onAddCard={openNewCard} onEditCard={openEditCard} onDeleteCard={deleteCard}
                onRename={renameColumn} onDeleteCol={deleteColumn} />
            ))}
          </div>
          <DragOverlay>
            {activeCard ? (
              <Card size="small" style={{ width: 260, opacity: 0.85 }}>
                {activeCard.title}
              </Card>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      <CardDrawer open={drawerOpen} card={editingCard}
        onClose={() => setDrawerOpen(false)} onSave={saveCard} />
    </div>
  )
}
