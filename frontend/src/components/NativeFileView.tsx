import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, InputNumber, Segmented, Spin, Space, Tooltip } from 'antd'
import { ZoomInOutlined, ZoomOutOutlined, LeftOutlined, RightOutlined, ColumnWidthOutlined } from '@ant-design/icons'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

interface Props {
  docId: string
  contentType: string
  /** 全页浏览模式（PDF 铺满阅读区） */
  full?: boolean
}

/** 原生文件阅读视图（对标 WPS）：PDF 原生渲染、docx→HTML、md 渲染、txt/pptx 文本。
 *  PDF 默认「适合页宽」渲染（保持自然比例），保留缩放工具条，100% = 原始尺寸。 */
export default function NativeFileView({ docId, contentType, full }: Props) {
  const fileUrl = api.documentFileUrl(docId)
  const [numPages, setNumPages] = useState(0)
  const [page, setPage] = useState(1)
  const [scale, setScale] = useState(1)      // 当前绝对缩放（1 = 原始尺寸）
  const [fitScale, setFitScale] = useState(1) // 适合页宽对应的缩放
  const [autoFit, setAutoFit] = useState(true)
  const [naturalW, setNaturalW] = useState(0)
  const [naturalH, setNaturalH] = useState(0)
  const [containerW, setContainerW] = useState(0)
  const [html, setHtml] = useState('')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  // 翻页方式：单页翻页 / 连续滚动（持久化到 localStorage，重新打开任意 PDF 仍生效）
  const [mode, setMode] = useState<'single' | 'scroll'>(() =>
    localStorage.getItem('pdfReadingMode') === 'scroll' ? 'scroll' : 'single',
  )
  // 连续滚动用：每页包装元素引用 + 滚动节流，用于页码跳转与当前页跟踪
  const pageWrapsRef = useRef<Map<number, HTMLDivElement>>(new Map())
  const scrollRafRef = useRef(0)
  // 连续滚动懒加载：已真正渲染的页码集合（其余只放占位 div，进入视口附近才渲染）
  const [rendered, setRendered] = useState<Set<number>>(new Set())
  const ioRef = useRef<IntersectionObserver | null>(null)

  useEffect(() => { localStorage.setItem('pdfReadingMode', mode) }, [mode])

  const isPdf = contentType === 'pdf'

  // 量取容器宽度，用于「适合页宽」
  const pdfRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)
  const applyScale = (s: number) => { scaleRef.current = s; setScale(s) }

  useEffect(() => {
    // 用 PDF 容器（不含滚动条）测量宽度，避免「页面变高→滚动条出现→宽度变→重适配」的死循环闪烁
    const el = (pdfRef.current || bodyRef.current) as HTMLElement | null
    if (!el) return
    let raf = 0
    const update = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => setContainerW(el.clientWidth))
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => { ro.disconnect(); cancelAnimationFrame(raf) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPdf, docId, contentType])

  // 容器宽 + PDF 自然宽 → 计算适合页宽缩放；自动模式下仅在变化明显时才重设，避免反复重渲染
  useEffect(() => {
    if (containerW > 0 && naturalW > 0) {
      const f = containerW / naturalW
      setFitScale(f)
      if (autoFit && Math.abs(scaleRef.current - f) > 0.005) {
        scaleRef.current = f
        setScale(f)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerW, naturalW])

  const onPageLoad = useCallback((pdfPage: any) => {
    if (!naturalW) {
      try {
        const vp = pdfPage.getViewport({ scale: 1 })
        setNaturalW(vp.width)
        setNaturalH(vp.height)
      } catch { /* ignore */ }
    }
  }, [naturalW])

  const zoomIn = () => { setAutoFit(false); applyScale(Math.min(3, +(scaleRef.current + 0.1).toFixed(2))) }
  const zoomOut = () => { setAutoFit(false); applyScale(Math.max(0.25, +(scaleRef.current - 0.1).toFixed(2))) }
  const fitWidth = () => { setAutoFit(true); applyScale(fitScale) }

  // ---------- 连续滚动：懒加载 / 页码跳转 / 当前页跟踪 ----------
  const setPageWrap = (el: HTMLDivElement | null, n: number) => {
    if (el) { el.dataset.page = String(n); pageWrapsRef.current.set(n, el) }
    else pageWrapsRef.current.delete(n)
  }

  // 懒加载：观察所有页占位元素，进入视口附近（±2 页 + 600px 缓冲）才真正渲染
  useEffect(() => {
    if (mode !== 'scroll' || !numPages) return
    ioRef.current?.disconnect()
    const io = new IntersectionObserver((entries) => {
      setRendered(prev => {
        let changed = false
        const next = new Set(prev)
        for (const en of entries) {
          if (!en.isIntersecting) continue
          const n = Number((en.target as HTMLElement).dataset.page)
          for (let i = Math.max(1, n - 2); i <= Math.min(numPages, n + 2); i++) {
            if (!next.has(i)) { next.add(i); changed = true }
          }
        }
        return changed ? next : prev
      })
    }, { root: bodyRef.current, rootMargin: '600px 0px' })
    ioRef.current = io
    pageWrapsRef.current.forEach(el => io.observe(el))
    return () => io.disconnect()
  }, [mode, numPages])
  const scrollToPage = (n: number) => {
    setPage(n)
    const body = bodyRef.current
    const el = pageWrapsRef.current.get(n)
    if (body && el) {
      const bodyTop = body.getBoundingClientRect().top
      const elTop = el.getBoundingClientRect().top
      body.scrollTop += elTop - bodyTop - 8
    }
  }
  /** 统一翻页入口：单页模式直接渲染目标页；连续滚动模式滚动到目标页 */
  const goToPage = (n: number) => {
    const target = Math.max(1, Math.min(numPages || 1, n || 1))
    if (mode === 'scroll') scrollToPage(target)
    else setPage(target)
  }
  /** 滚动时跟踪当前页（rAF 节流，避免逐帧 setState） */
  const handleScroll = () => {
    if (mode !== 'scroll') return
    cancelAnimationFrame(scrollRafRef.current)
    scrollRafRef.current = requestAnimationFrame(() => {
      const body = bodyRef.current
      if (!body) return
      const bodyTop = body.getBoundingClientRect().top
      let cur = 1
      pageWrapsRef.current.forEach((el, n) => {
        if (el.getBoundingClientRect().top - bodyTop <= 60) cur = n
      })
      if (cur !== page) setPage(cur)
    })
  }
  // 切到连续滚动时定位到当前页
  useEffect(() => {
    if (mode === 'scroll' && numPages) {
      const raf = requestAnimationFrame(() => scrollToPage(page))
      return () => cancelAnimationFrame(raf)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  useEffect(() => {
    setLoading(true)
    if (contentType === 'docx') {
      fetch(fileUrl)
        .then(r => r.arrayBuffer())
        .then(async buf => {
          const mammoth = (await import('mammoth')).default
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf })
          setHtml(value)
        })
        .catch(() => setHtml('<p style="color:#999">docx 渲染失败</p>'))
        .finally(() => setLoading(false))
    } else if (['md', 'markdown', 'txt', 'pptx'].includes(contentType)) {
      api.getReadingContent(docId)
        .then((d: any) => setText(d.units?.map((u: any) => u.text).join('\n\n') || ''))
        .catch(() => setText(''))
        .finally(() => setLoading(false))
    } else {
      setLoading(false) // PDF 交给 react-pdf 处理
    }
  }, [docId, contentType, fileUrl])

  const markdownText = useMemo(() => (['md', 'markdown'].includes(contentType) ? text : ''), [text, contentType])

  return (
    <div className={`yq-native ${full ? 'yq-native-full' : ''}`}>
      <div className="yq-native-toolbar">
        {isPdf ? (
          <>
            <Tooltip title="上一页">
              <Button size="small" icon={<LeftOutlined />} disabled={page <= 1} onClick={() => goToPage(page - 1)} />
            </Tooltip>
            <InputNumber size="small" min={1} max={Math.max(1, numPages)} value={page}
              onChange={v => goToPage(Number(v) || 1)} style={{ width: 70 }} />
            <span style={{ color: '#999', fontSize: 12 }}>/ {numPages || '…'}</span>
            <Tooltip title="下一页">
              <Button size="small" icon={<RightOutlined />} disabled={page >= numPages} onClick={() => goToPage(page + 1)} />
            </Tooltip>
            <div style={{ flex: 1 }} />
            <Tooltip title="缩小">
              <Button size="small" icon={<ZoomOutOutlined />} onClick={zoomOut} />
            </Tooltip>
            <span style={{ color: '#666', fontSize: 13, minWidth: 52, textAlign: 'center' }}>
              {Math.round(scale * 100)}%
            </span>
            <Tooltip title="放大">
              <Button size="small" icon={<ZoomInOutlined />} onClick={zoomIn} />
            </Tooltip>
            <Tooltip title="适合页宽">
              <Button size="small" icon={<ColumnWidthOutlined />} onClick={fitWidth} />
            </Tooltip>
            <Segmented
              size="small" value={mode}
              onChange={v => setMode(v as 'single' | 'scroll')}
              options={[{ value: 'single', label: '单页翻页' }, { value: 'scroll', label: '连续滚动' }]}
            />
          </>
        ) : (
          <span style={{ color: '#999', fontSize: 13 }}>
            {contentType === 'docx' ? 'Word 文档' : contentType === 'md' || contentType === 'markdown' ? 'Markdown' : contentType === 'pptx' ? 'PPT 逐页文本' : '纯文本'}
          </span>
        )}
      </div>

      <div className="yq-native-body" ref={bodyRef} onScroll={handleScroll}>
        {loading ? <Spin style={{ display: 'block', margin: 60 }} /> : isPdf ? (
          mode === 'scroll' ? (
            <div className="yq-native-pdf" ref={pdfRef}>
              <Document
                file={fileUrl}
                onLoadSuccess={({ numPages }) => { setNumPages(numPages); setPage(1); setRendered(new Set([1])) }}
                loading={<Spin style={{ display: 'block', margin: 60 }} />}
                onLoadError={e => console.error('PDF 加载失败', e)}
              >
                {Array.from({ length: Math.max(0, numPages) }, (_, i) => {
                  const n = i + 1
                  const shown = rendered.has(n)
                  // 占位高度按已量得的页高*缩放估计，避免滚动条巨幅跳动；页真正渲染后高度自动纠正
                  const ph = naturalH > 0 ? Math.round(naturalH * scale) : 400
                  return (
                    <div key={n} ref={el => setPageWrap(el, n)}>
                      {shown
                        ? <Page pageNumber={n} scale={scale} onLoadSuccess={onPageLoad} />
                        : <div style={{ minHeight: ph }} />}
                    </div>
                  )
                })}
              </Document>
            </div>
          ) : (
            <div className="yq-native-pdf" ref={pdfRef}>
              <Document
                file={fileUrl}
                onLoadSuccess={({ numPages }) => { setNumPages(numPages); setPage(1); setRendered(new Set([1])) }}
                loading={<Spin style={{ display: 'block', margin: 60 }} />}
                onLoadError={e => console.error('PDF 加载失败', e)}
              >
                <Page pageNumber={page} scale={scale} onLoadSuccess={onPageLoad} />
              </Document>
            </div>
          )
        ) : html ? (
          <div className="yq-native-docx" dangerouslySetInnerHTML={{ __html: html }} />
        ) : markdownText ? (
          <div className="yq-native-md">
            <ReactMarkdown>{markdownText}</ReactMarkdown>
          </div>
        ) : text ? (
          <pre className="yq-native-text">{text}</pre>
        ) : (
          <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>暂不支持该类型原生预览</div>
        )}
      </div>
    </div>
  )
}
