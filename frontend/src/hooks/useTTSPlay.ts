import { useRef, useState } from 'react'

/** 通用 TTS 播放：POST /api/tts/synthesize → 播放返回的音频。 */
export function useTTSPlay() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [busy, setBusy] = useState(false)

  const stop = () => {
    audioRef.current?.pause()
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null }
    setPlaying(false)
  }

  const play = async (text: string, voice?: string, provider?: string) => {
    if (!text.trim()) return
    setBusy(true)
    try {
      const resp = await fetch('/api/tts/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 2000), voice, provider }),
      })
      if (!resp.ok) {
        const j = await resp.json().catch(() => ({}))
        throw new Error(j.detail || '语音合成失败')
      }
      const blob = await resp.blob()
      stop()
      const url = URL.createObjectURL(blob)
      urlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => { setPlaying(false); if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null } }
      audio.onerror = () => { setPlaying(false); if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null } }
      await audio.play()
      setPlaying(true)
    } catch (e: any) {
      throw e
    } finally {
      setBusy(false)
    }
  }

  return { play, stop, playing, busy }
}
