import { useRef } from 'react'

export type Range = { start: number; end: number }

export interface HlRange extends Range {
  cls?: string
}

/**
 * 阅读视图展示与朗读共用的清洗文本：去掉 markdown 记号，保留正文。
 * 清洗必须是确定性的，保证渲染、批注偏移、朗读句子偏移三者一致。
 */
export function cleanText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '（代码块）')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')     // 标题符号，保留标题文字
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '• ') // 列表符转为圆点
    .trim()
}

/** 依据高亮区间把文本切成片段；区间重叠时后面的 cls 优先（如朗读优先于批注）。 */
function buildSegments(text: string, ranges: HlRange[]): Array<{ text: string; cls: string }> {
  const pts = new Set<number>([0, text.length])
  for (const r of ranges) {
    if (r.start >= 0 && r.end <= text.length && r.end > r.start) {
      pts.add(r.start)
      pts.add(r.end)
    }
  }
  const points = [...pts].sort((a, b) => a - b)
  const segs: Array<{ text: string; cls: string }> = []
  for (let i = 0; i < points.length - 1; i++) {
    const s = points[i]
    const e = points[i + 1]
    if (e <= s) continue
    let cls = ''
    for (const r of ranges) {
      if (r.start <= s && e <= r.end) cls = r.cls || ''
    }
    segs.push({ text: text.slice(s, e), cls })
  }
  return segs
}

/**
 * 把 DOM 选区换算为文本内的字符偏移。
 * 依赖容器的所有字符都以文本节点形式存在（white-space: pre-wrap 保证换行也在文本里）。
 */
export function computeCharOffsets(container: HTMLElement, sel: Selection): Range | null {
  if (!sel.anchorNode || !sel.focusNode) return null
  if (!container.contains(sel.anchorNode) || !container.contains(sel.focusNode)) return null

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)

  let anchorGlobal = -1
  let focusGlobal = -1
  let cum = 0
  for (const n of nodes) {
    const len = n.data.length
    if (n === sel.anchorNode) anchorGlobal = cum + Math.min(sel.anchorOffset, len)
    if (n === sel.focusNode) focusGlobal = cum + Math.min(sel.focusOffset, len)
    cum += len
  }
  if (anchorGlobal < 0 || focusGlobal < 0) return null
  return { start: Math.min(anchorGlobal, focusGlobal), end: Math.max(anchorGlobal, focusGlobal) } as Range
}

interface Props {
  text: string
  /** 批注跳转等普通高亮 */
  highlightRanges?: Range[]
  /** 朗读当前句高亮（蓝色，优先于普通高亮） */
  speakRanges?: Range[]
  /** 用户选中文本后回调：(start, end, selectedText) */
  onSelect?: (start: number, end: number, selectedText: string) => void
  className?: string
}

export default function ReadingUnit({ text, highlightRanges = [], speakRanges = [], onSelect, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  const ranges: HlRange[] = [
    ...(highlightRanges || []).map(r => ({ start: r.start, end: r.end, cls: 'reading-hl' })),
    ...(speakRanges || []).map(r => ({ start: r.start, end: r.end, cls: 'reading-hl speaking' })),
  ]
  const segments = buildSegments(text, ranges)

  const handleMouseUp = () => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !onSelect || !containerRef.current) return
    const range = computeCharOffsets(containerRef.current, sel)
    if (!range) return
    const selected = text.slice(range.start, range.end)
    if (selected.trim()) onSelect(range.start, range.end, selected)
  }

  return (
    <div
      ref={containerRef}
      className={`reading-unit ${className || ''}`}
      style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 15, userSelect: 'text' }}
      onMouseUp={handleMouseUp}
    >
      {segments.map((seg, i) =>
        seg.cls
          ? <mark key={i} className={seg.cls}>{seg.text}</mark>
          : <span key={i}>{seg.text}</span>,
      )}
    </div>
  )
}
