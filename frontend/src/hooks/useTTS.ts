import { useCallback, useEffect, useRef, useState } from 'react'

export type TTSState = 'idle' | 'playing' | 'paused'
export type TTSSource = 'original' | 'summary' | 'story'

export interface Sentence {
  start: number
  end: number
  text: string
}

/** 按中文/英文句子边界切分，返回带原文偏移的句子列表。 */
export function splitSentences(text: string): Sentence[] {
  const sentences: Sentence[] = []
  const re = /[^。！？!?；;\n]+[。！？!?；;\n]*/g
  let m: RegExpExecArray | null
  let last = 0
  while ((m = re.exec(text)) !== null) {
    const s = m.index
    const e = m.index + m[0].length
    sentences.push({ start: s, end: e, text: m[0].trim() })
    last = e
  }
  if (last < text.length && text.slice(last).trim()) {
    sentences.push({ start: last, end: text.length, text: text.slice(last).trim() })
  }
  return sentences.filter(s => s.text.length > 0)
}

let cachedZhVoice: SpeechSynthesisVoice | null | undefined = undefined

function pickZhVoice(): SpeechSynthesisVoice | null {
  if (typeof speechSynthesis === 'undefined') return null
  if (cachedZhVoice !== undefined) return cachedZhVoice
  const voices = speechSynthesis.getVoices()
  const zh = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith('zh'))
  // 优先女声、桌面高质量语音
  const preferred = zh.find(v => /xiaoxiao|huihui|yaoyao|xiaoyi|xiaomo|xiaohan/i.test(v.name))
    || zh.find(v => /female|woman|xiaoyan|tingting/i.test(v.name))
    || zh[0]
  cachedZhVoice = preferred || null
  return cachedZhVoice
}

if (typeof speechSynthesis !== 'undefined') {
  speechSynthesis.addEventListener?.('voiceschanged', () => { cachedZhVoice = undefined })
}

interface UseTTSOptions {
  /** 当前句切换时回调（用于高亮） */
  onSentenceChange?: (index: number) => void
}

export function useTTS({ onSentenceChange }: UseTTSOptions = {}) {
  const [state, setState] = useState<TTSState>('idle')
  const [currentIndex, setCurrentIndex] = useState(0)
  const [rate, setRateState] = useState(1)
  const [sentences, setSentences] = useState<Sentence[]>([])

  const speechRef = useRef<{ text: string; index: number }>({ text: '', index: 0 })
  const rateRef = useRef(1)
  const onSentenceRef = useRef(onSentenceChange)
  onSentenceRef.current = onSentenceChange

  const cancelAndWait = (delay = 50) =>
    new Promise<void>(resolve => {
      speechSynthesis.cancel()
      // Chromium bug：cancel() 后立即 speak() 会丢音频，需等一小段
      setTimeout(resolve, delay)
    })

  const speakAt = useCallback(async (index: number) => {
    const { text } = speechRef.current
    if (!text) return
    const list = sentences.length ? sentences : splitSentences(text)
    if (index < 0) index = 0
    if (index >= list.length) { stop(); return }
    await cancelAndWait()
    speechRef.current.index = index
    setCurrentIndex(index)
    onSentenceRef.current?.(index)

    const utter = new SpeechSynthesisUtterance(list[index].text)
    utter.lang = 'zh-CN'
    utter.rate = rateRef.current
    const voice = pickZhVoice()
    if (voice) utter.voice = voice
    utter.onend = () => {
      if (index + 1 < list.length) speakAt(index + 1)
      else setState('idle')
    }
    utter.onerror = () => { setState('idle') }
    setState('playing')
    speechSynthesis.speak(utter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sentences, rate])

  /** 开始/重新朗读一段文本。可指定从第几句开始。
    传入的 text 需已用 cleanText 清洗，保证句子偏移与渲染文本一致。 */
  const play = useCallback(async (text: string, startIndex = 0) => {
    const clean = (text || '').trim()
    if (!clean) return
    speechRef.current = { text: clean, index: startIndex }
    const list = splitSentences(clean)
    setSentences(list)
    await speakAt(startIndex)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speakAt])

  const pause = useCallback(() => {
    speechSynthesis.pause()
    setState('paused')
  }, [])

  const resume = useCallback(() => {
    speechSynthesis.resume()
    setState('playing')
  }, [])

  const stop = useCallback(() => {
    speechSynthesis.cancel()
    speechRef.current = { text: '', index: 0 }
    setState('idle')
    setCurrentIndex(0)
  }, [])

  const next = useCallback(() => {
    speakAt(currentIndex + 1)
  }, [speakAt, currentIndex])

  const prev = useCallback(() => {
    speakAt(Math.max(0, currentIndex - 1))
  }, [speakAt, currentIndex])

  const setRate = useCallback((r: number) => {
    rateRef.current = r
    setRateState(r)
    // 播放中调整语速：用新语速重播当前句
    if (state === 'playing' && speechRef.current.text) {
      speakAt(currentIndex)
    }
  }, [speakAt, state, currentIndex])

  useEffect(() => () => { speechSynthesis.cancel() }, [])

  return { state, currentIndex, rate, sentences, total: sentences.length, play, pause, resume, stop, next, prev, setRate }
}
