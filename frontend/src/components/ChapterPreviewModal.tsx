import { useEffect, useState } from 'react'
import { Button, InputNumber, Modal, Space, Spin, Tooltip } from 'antd'
import { LeftOutlined, RightOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

interface Props {
  open: boolean
  bookFileUrl: string
  bookTitle: string
  /** 书内物理页范围（0 基，含） */
  pageStart: number
  pageEnd: number
  /** 调整范围后回传（供调节器更新该章节行） */
  onRangeChange: (start: number, end: number) => void
  onClose: () => void
}

/** 章节内容预览：直接渲染整书原文件在 [pageStart, pageEnd] 范围内的实际页面，
 *  书内页码与阅读页 reading_content._pdf_pages 一致（第 page_start+pno+1 页）。 */
export default function ChapterPreviewModal({
  open, bookFileUrl, bookTitle, pageStart, pageEnd, onRangeChange, onClose,
}: Props) {
  const [start, setStart] = useState(pageStart)
  const [end, setEnd] = useState(pageEnd)
  const [numPages, setNumPages] = useState(0)
  const [page, setPage] = useState(pageStart + 1)
  const [zoom, setZoom] = useState(1)

  useEffect(() => {
    if (open) {
      setStart(pageStart); setEnd(pageEnd)
      setPage(pageStart + 1); setZoom(1)
    }
  }, [open, pageStart, pageEnd])

  const total = Math.max(0, end - start + 1)

  return (
    <Modal
      title={<span>内容预览 · {bookTitle}</span>}
      open={open}
      onCancel={onClose}
      footer={null}
      width={900}
    >
      {/* 范围调整 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <span style={{ color: '#666', fontSize: 13 }}>预览书内第</span>
        <InputNumber min={1} max={numPages || undefined} value={start + 1}
          onChange={v => setStart(Math.min(Math.max(0, (Number(v) || 1) - 1), Math.max(0, (numPages || 1) - 1)))} style={{ width: 80 }} />
        <span style={{ color: '#666', fontSize: 13 }}>~</span>
        <InputNumber min={start + 1} max={numPages || undefined} value={end + 1}
          onChange={v => setEnd(Math.max(start, Math.min(Math.max(0, (numPages || 1) - 1), (Number(v) || 1) - 1)))} style={{ width: 80 }} />
        <span style={{ color: '#666', fontSize: 13 }}>页</span>
        <Button size="small" type="primary" onClick={() => { onRangeChange(start, end); setPage(start + 1); setZoom(1) }}>
          应用范围
        </Button>
        <div style={{ flex: 1 }} />
        <Tooltip title="上一页">
          <Button size="small" icon={<LeftOutlined />} disabled={page <= start + 1} onClick={() => setPage(p => p - 1)} />
        </Tooltip>
        <span style={{ color: '#666', fontSize: 12 }}>
          {page}/{Math.max(page, end + 1)}（共 {total} 页）
        </span>
        <Tooltip title="下一页">
          <Button size="small" icon={<RightOutlined />} disabled={page >= end + 1} onClick={() => setPage(p => p + 1)} />
        </Tooltip>
        <Tooltip title="缩小"><Button size="small" icon={<ZoomOutOutlined />} onClick={() => setZoom(z => Math.max(0.5, +(z - 0.25).toFixed(2)))} /></Tooltip>
        <span style={{ color: '#666', fontSize: 12 }}>{Math.round(zoom * 100)}%</span>
        <Tooltip title="放大"><Button size="small" icon={<ZoomInOutlined />} onClick={() => setZoom(z => Math.min(3, +(z + 0.25).toFixed(2)))} /></Tooltip>
      </div>

      <div style={{ maxHeight: '60vh', overflowY: 'auto', display: 'flex', justifyContent: 'center', background: '#f5f5f7', padding: 12, borderRadius: 8 }}>
        <Document
          file={bookFileUrl}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          loading={<Spin style={{ margin: 40 }} />}
        >
          <Page pageNumber={page} scale={zoom} />
        </Document>
      </div>
      <div style={{ color: '#999', fontSize: 12, marginTop: 8, textAlign: 'center' }}>
        当前页书内第 {page} 页（与阅读页页码一致）；调整上方范围后点「应用范围」同步到该章节范围
      </div>
    </Modal>
  )
}
