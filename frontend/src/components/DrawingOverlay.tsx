import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Space, Tooltip, Segmented } from 'antd'
import { UndoOutlined, RedoOutlined, DeleteOutlined } from '@ant-design/icons'
import { api } from '../api'

interface Point { x: number; y: number }
interface Stroke { id: string; tool: 'pen' | 'highlighter'; color: string; size: number; points: Point[] }

interface Props {
  docId: string
  unitIndex: number
  enabled: boolean
  /** 退出绘制模式（由阅读页百宝箱触发） */
  onClose?: () => void
}

const COLORS = ['#e74c3c', '#f39c12', '#2ecc71', '#3498db', '#7c5cfc', '#333333']
const TOOL_BTN = { pen: '✏️ 画笔', highlighter: '🖍️ 荧光笔' }

/** PDF 自由绘制图层：叠加在原 PDF 页面上，坐标归一化(0-1)存储，随文档保存。 */
export default function DrawingOverlay({ docId, unitIndex, enabled, onClose }: Props) {
  const [strokes, setStrokes] = useState<Stroke[]>([])
  const [current, setCurrent] = useState<Stroke | null>(null)
  const [tool, setTool] = useState<'pen' | 'highlighter'>('pen')
  const [color, setColor] = useState(COLORS[0])
  const [size, setSize] = useState(2)
  const [eraser, setEraser] = useState(false)
  const [eraserMode, setEraserMode] = useState<'point' | 'stroke'>('stroke')
  const [sizeW, setSizeW] = useState(0)
  const [sizeH, setSizeH] = useState(0)
  const [dirty, setDirty] = useState(false)
  // 撤销/重做历史
  const undoStack = useRef<Stroke[][]>([])
  const redoStack = useRef<Stroke[][]>([])
  const boxRef = useRef<HTMLDivElement>(null)
  const drawing = useRef(false)

  // 量取叠加层显示尺寸（随页面缩放）
  useEffect(() => {
    const el = boxRef.current
    if (!el) return
    const update = () => { setSizeW(el.clientWidth); setSizeH(el.clientHeight) }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const load = useCallback(async () => {
    try {
      const d = await api.listDrawings(docId)
      const item = d.items.find((x: any) => x.unit_index === unitIndex)
      setStrokes(item?.strokes || [])
      undoStack.current = []
      redoStack.current = []
    } catch { setStrokes([]) }
  }, [docId, unitIndex])

  useEffect(() => {
    if (enabled) { load(); setDirty(false) }
  }, [enabled, load])

  // 自动保存（防抖）
  useEffect(() => {
    if (!dirty || !enabled) return
    const t = setTimeout(async () => {
      try { await api.saveDrawings(docId, unitIndex, strokes) } catch { /* ignore */ }
      setDirty(false)
    }, 500)
    return () => clearTimeout(t)
  }, [dirty, strokes, enabled, docId, unitIndex])

  const getPos = (e: React.PointerEvent): Point => {
    const rect = boxRef.current!.getBoundingClientRect()
    return { x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height }
  }

  const onDown = (e: React.PointerEvent) => {
    if (!enabled) return
    if (e.button !== 0) return   // 只响应左键(0)；右键(2)/中键(1)不绘制
    e.preventDefault()
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
    drawing.current = true
    setCurrent({ id: `s${Date.now()}`, tool, color, size, points: [getPos(e)] })
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drawing.current) return
    const p = getPos(e)
    setCurrent(c => (c ? { ...c, points: [...c.points, p] } : c))
  }
  const onUp = () => {
    if (!drawing.current) return
    drawing.current = false
    if (current) {
      undoStack.current.push(strokes)
      redoStack.current = []
      if (eraser) {
        // 橡皮擦：对现有笔迹应用擦除
        const threshold = 0.02
        const ep = current.points
        const next = eraserMode === 'point'
          ? applyPointErase(strokes, ep, threshold)
          : applyStrokeErase(strokes, ep, threshold)
        setStrokes(next)
      } else {
        setStrokes(s => [...s, current])
      }
      setCurrent(null)
      setDirty(true)
    }
  }

  const undo = () => {
    if (!undoStack.current.length) return
    redoStack.current.push(strokes)
    setStrokes(undoStack.current.pop()!)
    setDirty(true)
  }
  const redo = () => {
    if (!redoStack.current.length) return
    undoStack.current.push(strokes)
    setStrokes(redoStack.current.pop()!)
    setDirty(true)
  }
  const clear = () => {
    undoStack.current.push(strokes)
    redoStack.current = []
    setStrokes([])
    setDirty(true)
  }

  const pathD = (s: Stroke) => {
    return s.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${(p.x * sizeW).toFixed(1)} ${(p.y * sizeH).toFixed(1)}`).join(' ')
  }

  if (!enabled) return null

  return (
    <>
      {/* 叠加图层：铺在 PDF 页面上，捕获指针 */}
      <div
        ref={boxRef}
        style={{
          position: 'absolute', inset: 0, touchAction: 'none', cursor: eraser ? 'cell' : 'crosshair',
          userSelect: 'none', zIndex: 5,
        }}
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}
        onContextMenu={(e) => e.preventDefault()}   // 阻止默认右键菜单，避免抢走焦点打断绘制
      >
        <svg width={sizeW} height={sizeH} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {strokes.map(s => (
            <path key={s.id} d={pathD(s)} fill="none"
              stroke={s.color}
              strokeWidth={s.tool === 'highlighter' ? s.size * 8 : s.size}
              strokeLinecap="round" strokeLinejoin="round"
              opacity={s.tool === 'highlighter' ? 0.55 : 1}
              style={s.tool === 'highlighter' ? { mixBlendMode: 'multiply' } : undefined} />
          ))}
          {current && (
            <path d={pathD(current)} fill="none"
              stroke={eraser ? 'rgba(255,255,255,0.6)' : current.color}
              strokeWidth={(current.tool === 'highlighter' ? current.size * 8 : current.size)}
              strokeLinecap="round" strokeLinejoin="round"
              opacity={current.tool === 'highlighter' ? 0.55 : 1}
              style={current.tool === 'highlighter' ? { mixBlendMode: 'multiply' } : undefined} />
          )}
        </svg>
      </div>

      {/* 绘制工具条（悬浮在页面右下） */}
      <div style={{ position: 'absolute', right: 8, top: 8, zIndex: 6, background: '#fff', borderRadius: 10, padding: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.15)', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Segmented size="small" value={eraser ? 'eraser' : tool}
          onChange={v => { if (v === 'eraser') { setEraser(true) } else { setEraser(false); setTool(v as 'pen' | 'highlighter') } }}
          options={[{ value: 'pen', label: '✏️' }, { value: 'highlighter', label: '🖍️' }, { value: 'eraser', label: '🧹' }]} />
        {!eraser && (
          <>
            <Space size={4} wrap>
              {COLORS.map(c => (
                <span key={c} onClick={() => setColor(c)}
                  style={{ width: 18, height: 18, borderRadius: 9, background: c, cursor: 'pointer', border: color === c ? '2px solid #333' : '2px solid transparent' }} />
              ))}
            </Space>
            <Space size={4}>
              <span style={{ fontSize: 12 }}>粗</span>
              <input type="range" min={1} max={8} value={size} onChange={e => setSize(Number(e.target.value))} style={{ width: 70 }} />
              <span style={{ fontSize: 12 }}>细</span>
            </Space>
          </>
        )}
        {eraser && (
          <Segmented size="small" value={eraserMode} onChange={v => setEraserMode(v as 'point' | 'stroke')}
            options={[{ value: 'stroke', label: '笔画擦' }, { value: 'point', label: '点擦' }]} />
        )}
        <Space size={4}>
          <Tooltip title="撤销"><Button size="small" icon={<UndoOutlined />} onClick={undo} disabled={!undoStack.current.length} /></Tooltip>
          <Tooltip title="重做"><Button size="small" icon={<RedoOutlined />} onClick={redo} disabled={!redoStack.current.length} /></Tooltip>
          <Tooltip title="清空本页"><Button size="small" danger icon={<DeleteOutlined />} onClick={clear} /></Tooltip>
        </Space>
        <div style={{ fontSize: 11, color: '#999', textAlign: 'center' }}>
          {dirty ? '保存中…' : '已保存'} · {TOOL_BTN[eraser ? 'pen' : tool]}
        </div>
        {onClose && <Button size="small" block onClick={onClose}>✅ 完成</Button>}
      </div>
    </>
  )
}

// ---------------- 橡皮擦

function dist(a: Point, b: Point) { return Math.hypot(a.x - b.x, a.y - b.y) }

/** 笔画擦：橡皮擦路径碰到哪条笔迹就整条删除。 */
function applyStrokeErase(strokes: Stroke[], eraserPts: Point[], threshold: number): Stroke[] {
  return strokes.filter(s => !s.points.some(p => eraserPts.some(ep => dist(ep, p) < threshold)))
}

/** 点擦：把笔迹上被擦到的一段去掉，剩余部分拆成多条新笔迹（更精细）。 */
function applyPointErase(strokes: Stroke[], eraserPts: Point[], threshold: number): Stroke[] {
  const out: Stroke[] = []
  for (const s of strokes) {
    let seg: Point[] = []
    const flush = () => {
      if (seg.length >= 2) out.push({ ...s, id: `${s.id}-p${out.length}`, points: seg })
      seg = []
    }
    for (const p of s.points) {
      if (eraserPts.some(ep => dist(ep, p) < threshold)) flush()
      else seg.push(p)
    }
    flush()
  }
  return out
}
